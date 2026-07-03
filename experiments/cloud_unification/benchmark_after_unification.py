from __future__ import annotations

import csv
import json
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
FORESTVOL_ROOT = ROOT / "projects" / "ForestVol"
BACKEND = FORESTVOL_ROOT / "backend"
DATA_ROOT = FORESTVOL_ROOT / "data"
if not BACKEND.exists():
    ROOT = Path("/app")
    FORESTVOL_ROOT = ROOT
    BACKEND = ROOT / "backend"
    DATA_ROOT = ROOT / "data"
if str(BACKEND.parent) not in sys.path:
    sys.path.insert(0, str(BACKEND.parent))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.config import Settings, get_settings  # noqa: E402
from backend.app.services.cloud_provider import load_pipeline_point_cloud  # noqa: E402
from backend.app.services.mesh_service import generate_preliminary_volumetry, mesh_artifacts_to_session_payload  # noqa: E402

from experiments.cloud_unification.cloud_provider_adapter import PRODUCTION_SESSIONS  # noqa: E402


OUT = ROOT / "experiments" / "cloud_unification"
GT_VOLUME_M3 = 119.74
OLD_PRODUCTIVE_REPORTS = {
    "set1": DATA_ROOT / "pdi_productive_migration_hito05_set1.json",
    "set2": DATA_ROOT / "pdi_productive_migration_hito05_set2.json",
}
OLD_BENCHMARK_JSON = DATA_ROOT / "volume_estimator_benchmark" / "benchmark_volume_estimators.json"


def settings_for_root() -> Settings:
    settings = get_settings()
    if settings.processed_path.exists() and settings.upload_path.exists():
        return settings
    return Settings(
        version=settings.version,
        backend_port=settings.backend_port,
        nodeodm_url=settings.nodeodm_url,
        nodeodm_timeout_seconds=settings.nodeodm_timeout_seconds,
        nodeodm_data_path=settings.nodeodm_data_path,
        min_images=settings.min_images,
        max_images=settings.max_images,
        max_image_size_mb=settings.max_image_size_mb,
        max_session_size_gb=settings.max_session_size_gb,
        upload_path=DATA_ROOT / "uploads",
        processed_path=DATA_ROOT / "processed",
        export_path=DATA_ROOT / "exports",
        calibration_confidence_threshold=settings.calibration_confidence_threshold,
        calibration_marker_size_cm=settings.calibration_marker_size_cm,
    )


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def session(session_id: str, settings: Settings) -> dict[str, Any]:
    path = settings.upload_path / session_id / "session.json"
    if not path.exists():
        raise FileNotFoundError(f"missing_session_json:{path}")
    return read_json(path)


def scale_from_session(payload: dict[str, Any]) -> tuple[float | None, str | None]:
    scale_evidence = payload.get("scale_evidence") or {}
    if scale_evidence.get("scale_certified"):
        return 1.0, str(scale_evidence.get("reason") or "certified_metric_point_cloud")
    return None, None


def old_productive(dataset: str) -> dict[str, Any]:
    data = read_json(OLD_PRODUCTIVE_REPORTS[dataset])
    final = data.get("final") or {}
    return {
        "volume_m3": final.get("volume_m3"),
        "confidence_score": final.get("confidence_score"),
        "confidence_level": final.get("confidence_level"),
        "error_percentage": final.get("error_percentage"),
        "point_count": ((final.get("quality_gates") or [{}])[9].get("value") if final.get("quality_gates") else None),
    }


def old_experimental_pdi() -> dict[str, Any]:
    data = read_json(OLD_BENCHMARK_JSON)
    out: dict[str, Any] = {}
    for row in data.get("rows", []):
        if row.get("method") == "Point Density Integration":
            out[row["dataset"]] = {
                "volume_m3": row.get("volume_m3"),
                "percent_error": row.get("percent_error"),
                "input_cloud": data.get("datasets", {}).get(row["dataset"], {}).get("input_cloud"),
                "point_count": data.get("datasets", {}).get(row["dataset"], {}).get("point_count"),
            }
    return out


def validate_source(dataset: str, session_id: str, settings: Settings) -> dict[str, Any]:
    source = load_pipeline_point_cloud(session_id, settings)
    sess = session(session_id, settings)
    stored_path = Path(sess["point_cloud_path"])
    if not stored_path.is_absolute():
        candidates = [
            stored_path.resolve(),
            (settings.upload_path.parent.parent / stored_path).resolve(),
            (settings.upload_path.parent / stored_path).resolve(),
        ]
        stored_path = next((candidate for candidate in candidates if candidate.exists()), candidates[0])
    expected = (settings.processed_path / session_id / "point_cloud.ply").resolve()
    fingerprint = source.fingerprint()
    checks = {
        "canonical_path": str(expected),
        "session_point_cloud_path": str(stored_path),
        "provider_path": str(source.path),
        "sha256": source.sha256,
        "point_count": source.point_count,
        "bbox_extent": fingerprint["bbox_extent"],
        "centroid": fingerprint["centroid"],
        "path_match": source.path.resolve() == expected == stored_path.resolve(),
    }
    if not checks["path_match"]:
        raise RuntimeError(f"cloud_source_mismatch_before_benchmark:{dataset}:{checks}")
    return {"dataset": dataset, "session_id": session_id, **checks}


def run_dataset(dataset: str, settings: Settings) -> dict[str, Any]:
    session_id = PRODUCTION_SESSIONS[dataset]
    validation = validate_source(dataset, session_id, settings)
    sess = session(session_id, settings)
    scale, scale_source = scale_from_session(sess)
    output_dir = OUT / "outputs" / dataset
    output_dir.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    artifacts = generate_preliminary_volumetry(
        Path(validation["provider_path"]),
        output_dir,
        scale_px_per_cm=(sess.get("calibration") or {}).get("scale_px_per_cm"),
        ground_truth_volume_m3=GT_VOLUME_M3,
        point_cloud_scale_m_per_unit=scale,
        scale_source=scale_source,
        legacy_mesh_enabled=False,
    )
    elapsed = time.perf_counter() - started
    payload = mesh_artifacts_to_session_payload(artifacts)
    source_after = load_pipeline_point_cloud(session_id, settings).fingerprint()
    before = {key: validation[key] for key in ("sha256", "point_count", "bbox_extent", "centroid")}
    after = {key: source_after[key] for key in ("sha256", "point_count", "bbox_extent", "centroid")}
    if before != after:
        raise RuntimeError(f"cloud_source_changed_during_benchmark:{dataset}:{before}:{after}")
    gates = payload.get("quality_gates") or []
    gate_counts = {status: sum(1 for gate in gates if gate.get("status") == status) for status in ("PASS", "WARNING", "FAIL")}
    return {
        "dataset": dataset,
        "session_id": session_id,
        "cloud_validation": validation,
        "volume_m3": payload["volume_m3"],
        "error_percentage": payload["error_percentage"],
        "confidence_score": payload["confidence_score"],
        "confidence_level": payload["confidence_level"],
        "quality_gate_counts": gate_counts,
        "quality_gates": gates,
        "pdi_metrics": payload["pdi_metrics"],
        "bounding_box_m": payload["bounding_box_m"],
        "elapsed_seconds": round(float(elapsed), 6),
        "point_count": validation["point_count"],
    }


def write_csv(path: Path, rows: list[dict[str, Any]], old_exp: dict[str, Any]) -> None:
    fields = [
        "dataset",
        "session_id",
        "sha256",
        "point_count",
        "bbox_extent",
        "centroid",
        "new_volume_m3",
        "new_error_percentage",
        "new_confidence_score",
        "new_confidence_level",
        "gate_pass",
        "gate_warning",
        "gate_fail",
        "old_experimental_volume_m3",
        "old_experimental_error_percentage",
        "old_productive_volume_m3",
        "old_productive_error_percentage",
        "elapsed_seconds",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            old_prod = old_productive(row["dataset"])
            exp = old_exp.get(row["dataset"], {})
            gates = row["quality_gate_counts"]
            writer.writerow(
                {
                    "dataset": row["dataset"],
                    "session_id": row["session_id"],
                    "sha256": row["cloud_validation"]["sha256"],
                    "point_count": row["point_count"],
                    "bbox_extent": row["cloud_validation"]["bbox_extent"],
                    "centroid": row["cloud_validation"]["centroid"],
                    "new_volume_m3": row["volume_m3"],
                    "new_error_percentage": row["error_percentage"],
                    "new_confidence_score": row["confidence_score"],
                    "new_confidence_level": row["confidence_level"],
                    "gate_pass": gates["PASS"],
                    "gate_warning": gates["WARNING"],
                    "gate_fail": gates["FAIL"],
                    "old_experimental_volume_m3": exp.get("volume_m3"),
                    "old_experimental_error_percentage": exp.get("percent_error"),
                    "old_productive_volume_m3": old_prod.get("volume_m3"),
                    "old_productive_error_percentage": old_prod.get("error_percentage"),
                    "elapsed_seconds": row["elapsed_seconds"],
                }
            )


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# Benchmark After Cloud Unification\n\n",
        "Benchmark ejecutado usando exclusivamente `CloudProvider -> data/processed/<session>/point_cloud.ply`.\n\n",
        "| Dataset | SHA256 | Puntos | Volumen nuevo | Error % | Confidence | Gates P/W/F | Volumen benchmark antiguo | Volumen productivo antiguo |\n",
        "|---|---|---:|---:|---:|---|---|---:|---:|\n",
    ]
    for row in report["datasets"]:
        exp = report["old_experimental_pdi"].get(row["dataset"], {})
        prod = report["old_productive"].get(row["dataset"], {})
        gates = row["quality_gate_counts"]
        lines.append(
            f"| {row['dataset']} | `{row['cloud_validation']['sha256'][:12]}...` | {row['point_count']} | "
            f"{row['volume_m3']} | {row['error_percentage']} | {row['confidence_score']} {row['confidence_level']} | "
            f"{gates['PASS']}/{gates['WARNING']}/{gates['FAIL']} | {exp.get('volume_m3')} | {prod.get('volume_m3')} |\n"
        )
    lines.extend(
        [
            "\n## Validacion de equivalencia\n\n",
            "Cada fila fue validada antes de ejecutar volumetria. Si SHA256, ruta canonical, cantidad de puntos, bbox o centroide no coincidian con la fuente productiva, el benchmark abortaba.\n",
            "\n## Decision\n\n",
            f"- Equivalencia benchmark-produccion: `{report['validation']['all_sources_match']}`\n",
            "- PDI, DBSCAN, NodeODM, OpenSfM y parametros no fueron modificados.\n",
        ]
    )
    path.write_text("".join(lines), encoding="utf-8")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    settings = settings_for_root()
    old_exp = old_experimental_pdi()
    rows = [run_dataset(dataset, settings) for dataset in ("set1", "set2")]
    validation = {
        "all_sources_match": True,
        "validated_fields": ["sha256", "point_count", "bbox_extent", "centroid", "canonical_path"],
        "sources": [row["cloud_validation"] for row in rows],
    }
    report = {
        "run_id": "RUN-CLOUD-UNIFICATION-BENCHMARK-01",
        "ground_truth_m3": GT_VOLUME_M3,
        "validation": validation,
        "old_experimental_pdi": old_exp,
        "old_productive": {dataset: old_productive(dataset) for dataset in ("set1", "set2")},
        "datasets": rows,
    }
    (OUT / "benchmark_after_unification.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    write_csv(OUT / "benchmark_after_unification.csv", rows, old_exp)
    write_markdown(OUT / "benchmark_after_unification.md", report)
    (OUT / "validation_report.md").write_text(
        "# Cloud Source Validation\n\n"
        "Resultado: PASS. Los benchmarks posteriores a la unificacion consumen exactamente el `point_cloud.ply` productivo mediante CloudProvider.\n\n"
        + json.dumps(validation, indent=2),
        encoding="utf-8",
    )
    print(json.dumps({"out": str(OUT), "validation": validation}, indent=2))


if __name__ == "__main__":
    main()
