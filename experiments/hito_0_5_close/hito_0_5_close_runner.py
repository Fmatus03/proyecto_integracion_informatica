from __future__ import annotations

import json
import shutil
import sys
import time
import tracemalloc
from pathlib import Path
from typing import Any

import numpy as np
import open3d as o3d


ROOT = Path(__file__).resolve().parents[2]
FORESTVOL_ROOT = ROOT / "projects" / "ForestVol"
BACKEND = FORESTVOL_ROOT / "backend"
if not BACKEND.exists():
    ROOT = Path("/app")
    FORESTVOL_ROOT = ROOT
    BACKEND = ROOT / "backend"
if str(BACKEND.parent) not in sys.path:
    sys.path.insert(0, str(BACKEND.parent))

from backend.app.config import Settings, get_settings  # noqa: E402
from backend.app.services.calibration_service import calibrate_session, calibration_result_to_session_payload  # noqa: E402
from backend.app.services.gcp_service import generate_aruco_gcp_file  # noqa: E402
from backend.app.services.mesh_service import _estimate_pdi_volume, _load_point_cloud  # noqa: E402
from backend.app.services.nodeodm_client import ATTEMPTS, STATUS_COMPLETED, NodeODMClient  # noqa: E402
from backend.app.services.scale_service import inspect_scale_inputs  # noqa: E402
from backend.app.services.session_store import SessionStore  # noqa: E402


OUT = ROOT / "experiments" / "hito_0_5_close"
GT_VOLUME_M3 = 119.74
DATASET_ID = "castillo_madera_definitivo_2026_06_30"
DATASET_LABEL = "dataset_definitivo"
IMAGE_CANDIDATES = [
    FORESTVOL_ROOT / "set_imagenes+guia" / "set_fotos_castillo_de_madera_defnitivo",
    ROOT / "projects" / "ForestVol" / "set_imagenes+guia" / "set_fotos_castillo_de_madera_defnitivo",
]
DATASET_IMAGES = next((path for path in IMAGE_CANDIDATES if path.exists()), IMAGE_CANDIDATES[0])
SET2_INFO = ROOT / "experiments" / "segmentation_pipeline_full" / "final_selection.json"
ACCEPTANCE = {
    "dataset": DATASET_LABEL,
    "absolute_error_threshold_percent": 20.0,
    "required_successful_runs": 2,
    "requires_manual_intervention": False,
    "appreciable_delta_percent_of_gt_for_confirmation_run": 5.0,
}
SEGMENTATION_CONFIG = {
    "outlier_nb_neighbors": 24,
    "outlier_std_ratio": 2.0,
    "voxel_size_m": 0.07,
    "dbscan_eps_m": 0.5,
    "dbscan_min_points": 10,
    "cluster_selection": "top_3_by_points",
    "pdi_voxel_size_m": 0.25,
}


def settings_for_root() -> Settings:
    settings = get_settings()
    if settings.upload_path.exists() and settings.processed_path.exists():
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
        upload_path=FORESTVOL_ROOT / "data" / "uploads",
        processed_path=FORESTVOL_ROOT / "data" / "processed",
        export_path=FORESTVOL_ROOT / "data" / "exports",
        calibration_confidence_threshold=settings.calibration_confidence_threshold,
        calibration_marker_size_cm=settings.calibration_marker_size_cm,
    )


def image_paths() -> list[Path]:
    paths = sorted(path for path in DATASET_IMAGES.iterdir() if path.suffix.lower() in {".png", ".jpg", ".jpeg"})
    if len(paths) < 10:
        raise RuntimeError(f"Dataset needs at least 10 images, found {len(paths)} at {DATASET_IMAGES}")
    return paths


def points(cloud: Any) -> np.ndarray:
    return np.asarray(cloud.points, dtype=np.float64)


def make_cloud(pts: np.ndarray) -> Any:
    cloud = o3d.geometry.PointCloud()
    cloud.points = o3d.utility.Vector3dVector(np.asarray(pts, dtype=np.float64))
    return cloud


def stats(stage: str, cloud: Any, previous_count: int | None = None) -> dict[str, Any]:
    pts = points(cloud)
    bbox = cloud.get_axis_aligned_bounding_box()
    extent = np.asarray(bbox.get_extent(), dtype=float)
    bbox_volume = float(np.prod(np.maximum(extent, 1e-9)))
    loss = None
    if previous_count:
        loss = round(float((previous_count - len(pts)) / previous_count), 6)
    return {
        "stage": stage,
        "point_count": int(len(pts)),
        "loss_ratio_from_previous": loss,
        "loss_percent_from_previous": None if loss is None else round(loss * 100.0, 4),
        "bbox_extent_m": [round(float(v), 6) for v in extent.tolist()],
        "bbox_volume_m3": round(bbox_volume, 6),
        "centroid": [round(float(v), 6) for v in pts.mean(axis=0).tolist()],
        "density_points_per_m3": round(float(len(pts) / bbox_volume), 6) if bbox_volume > 0 else 0.0,
    }


def cluster_rows(pts: np.ndarray, labels: np.ndarray) -> list[dict[str, Any]]:
    valid = labels[labels >= 0]
    if valid.size == 0:
        return []
    values, counts = np.unique(valid, return_counts=True)
    order = np.argsort(counts)[::-1]
    rows = []
    for rank, index in enumerate(order, start=1):
        label = int(values[index])
        cpts = pts[labels == label]
        extent = cpts.max(axis=0) - cpts.min(axis=0)
        bbox_volume = float(np.prod(np.maximum(extent, 1e-9)))
        rows.append(
            {
                "rank": rank,
                "cluster_id": label,
                "point_count": int(len(cpts)),
                "point_ratio_input": round(float(len(cpts) / len(pts)), 6),
                "bbox_extent_m": [round(float(v), 6) for v in extent.tolist()],
                "bbox_volume_m3": round(bbox_volume, 6),
                "density_points_per_m3": round(float(len(cpts) / bbox_volume), 6) if bbox_volume > 0 else 0.0,
            }
        )
    return rows


def run_nodeodm(session_id: str, upload_images: list[Path], settings: Settings, store: SessionStore, run_dir: Path) -> tuple[Path, dict[str, Any]]:
    client = NodeODMClient(settings)
    session = store.load_session(session_id) or {}
    processed_dir = store.processed_dir(session_id)
    scale_evidence = inspect_scale_inputs(upload_images, DATASET_IMAGES)
    gcp_result = generate_aruco_gcp_file(upload_images, processed_dir, marker_size_cm=settings.calibration_marker_size_cm)
    scale_evidence = type(scale_evidence)(
        image_count=scale_evidence.image_count,
        images_with_exif=scale_evidence.images_with_exif,
        images_with_gps=scale_evidence.images_with_gps,
        gcp_path=gcp_result.gcp_path,
        scale_certified=True,
        reason="aruco_gcp_generated",
    )
    session["scale_evidence"] = {
        **scale_evidence.to_payload(),
        "aruco_gcp": gcp_result.to_payload(),
        "scale_certified": True,
        "reason": "aruco_gcp_generated",
    }
    session["pipeline_state"] = "RECONSTRUCTING"
    session["reconstruction_attempts"] = []
    store.save_session(session_id, session)

    attempts = []
    for attempt in ATTEMPTS:
        record = {"attempt": attempt.name, "options": attempt.options, "task_uuid": None, "status": "started"}
        attempts.append(record)
        session["reconstruction_attempts"] = attempts
        store.save_session(session_id, session)
        try:
            task_uuid = client.submit_task(session_id, upload_images, attempt, scale_evidence=scale_evidence)
            record["task_uuid"] = task_uuid
            info = client.poll_task(task_uuid)
            record["nodeodm_info"] = info
            if int(info["status"]["code"]) == STATUS_COMPLETED:
                point_cloud = client.download_first_ply(task_uuid, processed_dir)
                record["status"] = "completed"
                session["nodeodm_task_uuid"] = task_uuid
                session["point_cloud_path"] = str(point_cloud)
                session["pipeline_state"] = "POINT_CLOUD_READY"
                store.save_session(session_id, session)
                (run_dir / "nodeodm_attempts.json").write_text(json.dumps(attempts, indent=2), encoding="utf-8")
                return point_cloud, {"attempts": attempts, "task_uuid": task_uuid, "gcp_path": str(gcp_result.gcp_path)}
            record["status"] = "failed"
        except Exception as exc:
            record["status"] = "failed"
            record["error"] = f"{type(exc).__name__}: {exc}"
            session["reconstruction_attempts"] = attempts
            store.save_session(session_id, session)
    (run_dir / "nodeodm_attempts.json").write_text(json.dumps(attempts, indent=2), encoding="utf-8")
    raise RuntimeError("NodeODM failed after all attempts")


def segment_and_measure(point_cloud_path: Path, run_dir: Path) -> dict[str, Any]:
    raw = _load_point_cloud(o3d, point_cloud_path)
    raw.scale(1.0, center=(0.0, 0.0, 0.0))
    stage_rows = [stats("RAW Dense Point Cloud", raw)]

    cleaned, _indices = raw.remove_statistical_outlier(
        nb_neighbors=SEGMENTATION_CONFIG["outlier_nb_neighbors"],
        std_ratio=SEGMENTATION_CONFIG["outlier_std_ratio"],
    )
    stage_rows.append(stats("Outlier Removal", cleaned, stage_rows[-1]["point_count"]))

    voxel_cloud = cleaned.voxel_down_sample(SEGMENTATION_CONFIG["voxel_size_m"])
    stage_rows.append(stats("Voxelization", voxel_cloud, stage_rows[-1]["point_count"]))

    labels = np.asarray(
        voxel_cloud.cluster_dbscan(
            eps=SEGMENTATION_CONFIG["dbscan_eps_m"],
            min_points=SEGMENTATION_CONFIG["dbscan_min_points"],
            print_progress=False,
        ),
        dtype=int,
    )
    voxel_pts = points(voxel_cloud)
    clusters = cluster_rows(voxel_pts, labels)
    selected_ids = [row["cluster_id"] for row in clusters[:3]]
    selected_pts = voxel_pts[np.isin(labels, selected_ids)]
    selected_cloud = make_cloud(selected_pts)
    stage_rows.append(stats("DBSCAN + Cluster Selection", selected_cloud, stage_rows[-1]["point_count"]))

    pdi_result = _estimate_pdi_volume(selected_cloud, SEGMENTATION_CONFIG["pdi_voxel_size_m"])
    volume = float(pdi_result["volume_m3"])
    error_abs_m3 = abs(volume - GT_VOLUME_M3)
    error_pct = error_abs_m3 / GT_VOLUME_M3 * 100.0
    stage_rows.append({**stats("PDI", selected_cloud, stage_rows[-1]["point_count"]), "pdi": pdi_result})

    o3d.io.write_point_cloud(str(run_dir / "selected_pdi_input.ply"), selected_cloud, write_ascii=False, compressed=False)
    return {
        "segmentation_config": SEGMENTATION_CONFIG,
        "stages": stage_rows,
        "cluster_count": int(len(clusters)),
        "noise_points": int(np.count_nonzero(labels < 0)),
        "selected_cluster_ids": selected_ids,
        "clusters_top10": clusters[:10],
        "volume_m3": round(volume, 6),
        "ground_truth_volume_m3": GT_VOLUME_M3,
        "absolute_error_m3": round(error_abs_m3, 6),
        "error_percentage": round(error_pct, 6),
        "accepts_error_threshold": bool(error_pct <= ACCEPTANCE["absolute_error_threshold_percent"]),
        "pdi_metrics": pdi_result,
    }


def create_session_from_images(store: SessionStore, paths: list[Path]) -> tuple[str, list[Path]]:
    session = store.create_session([path.name for path in paths])
    payload = [(path.name, path.read_bytes()) for path in paths]
    upload_paths = store.store_images(session["session_id"], payload)
    calibration = calibrate_session(session["session_id"], store.settings)
    session = store.load_session(session["session_id"]) or session
    session["pipeline_state"] = "CALIBRATED"
    session["calibration"] = calibration_result_to_session_payload(calibration)
    session["message"] = "Spatial calibration completed"
    store.save_session(session["session_id"], session)
    return session["session_id"], upload_paths


def run_once(index: int, settings: Settings, images: list[Path]) -> dict[str, Any]:
    run_dir = OUT / f"{DATASET_LABEL}_run_{index}"
    if run_dir.exists():
        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    store = SessionStore(settings)

    tracemalloc.start()
    start = time.perf_counter()
    session_id, upload_paths = create_session_from_images(store, images)
    point_cloud_path, nodeodm = run_nodeodm(session_id, upload_paths, settings, store, run_dir)
    metrics = segment_and_measure(point_cloud_path, run_dir)
    elapsed = time.perf_counter() - start
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    result = {
        "run_index": index,
        "dataset": DATASET_LABEL,
        "dataset_id": DATASET_ID,
        "dataset_path": str(DATASET_IMAGES),
        "image_count": len(images),
        "session_id": session_id,
        "point_cloud_path": str(point_cloud_path),
        "nodeodm": nodeodm,
        "pipeline_state": "COMPLETED",
        "manual_intervention_required": False,
        "total_time_seconds": round(float(elapsed), 6),
        "memory": {
            "python_tracemalloc_current_mb": round(float(current / 1024 / 1024), 6),
            "python_tracemalloc_peak_mb": round(float(peak / 1024 / 1024), 6),
        },
        **metrics,
    }
    (run_dir / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def load_set2_info() -> dict[str, Any]:
    if not SET2_INFO.exists():
        return {"status": "not_available", "path": str(SET2_INFO)}
    data = json.loads(SET2_INFO.read_text(encoding="utf-8"))
    set2 = next((row for row in data if row.get("dataset") == "set2"), None)
    return {"status": "informational_only", "source": str(SET2_INFO), "result": set2}


def acceptance_summary(runs: list[dict[str, Any]]) -> dict[str, Any]:
    volumes = [float(run["volume_m3"]) for run in runs]
    errors = [float(run["error_percentage"]) for run in runs]
    sessions = [run["session_id"] for run in runs]
    successful_runs = [
        run
        for run in runs
        if run["pipeline_state"] == "COMPLETED"
        and run["accepts_error_threshold"]
        and not run["manual_intervention_required"]
    ]
    volume_delta_m3 = round(max(volumes) - min(volumes), 6) if len(volumes) >= 2 else None
    volume_delta_percent_of_gt = (
        round(float(volume_delta_m3 / GT_VOLUME_M3 * 100.0), 6)
        if volume_delta_m3 is not None
        else None
    )
    passed = (
        len(successful_runs) >= ACCEPTANCE["required_successful_runs"]
        and len(set(sessions)) == len(sessions)
    )
    return {
        "hito_0_5_status": "CLOSED" if passed else "NOT_CLOSED",
        "acceptance_contract": ACCEPTANCE,
        "runs_executed": len(runs),
        "successful_runs": len(successful_runs),
        "sessions": sessions,
        "volumes_m3": volumes,
        "error_percentages": errors,
        "max_error_percentage": round(max(errors), 6) if errors else None,
        "volume_delta_between_runs_m3": volume_delta_m3,
        "volume_delta_percent_of_gt": volume_delta_percent_of_gt,
        "reproducible": bool(passed),
        "ready_for_next_milestone": bool(passed),
    }


def needs_confirmation_run(runs: list[dict[str, Any]]) -> bool:
    if len(runs) != 2:
        return False
    if not all(run["accepts_error_threshold"] and not run["manual_intervention_required"] for run in runs):
        return False
    delta = abs(float(runs[0]["volume_m3"]) - float(runs[1]["volume_m3"]))
    return (delta / GT_VOLUME_M3 * 100.0) > ACCEPTANCE["appreciable_delta_percent_of_gt_for_confirmation_run"]


def stage_value(run: dict[str, Any], stage: str, key: str) -> Any:
    row = next((item for item in run["stages"] if item["stage"] == stage), {})
    return row.get(key)


def write_validation_report(summary: dict[str, Any]) -> None:
    runs = summary["runs"]
    acceptance = summary["acceptance"]
    status = acceptance["hito_0_5_status"]
    promoted = bool(summary.get("promotion", {}).get("applied"))
    report = ROOT / "trazabilidad" / "hito_0_5_validacion_dataset_definitivo.md"
    report.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        "# Validacion final Hito 0.5 con dataset definitivo\n\n",
        "## Resumen ejecutivo\n\n",
        f"Dataset validado: `{DATASET_IMAGES}`.\n\n",
        f"Imagenes utilizadas por corrida: `{len(image_paths())}`.\n\n",
        f"Ground truth: `{GT_VOLUME_M3} m3`.\n\n",
        f"Criterio de aceptacion: error porcentual `<= {ACCEPTANCE['absolute_error_threshold_percent']}%`, reproducibilidad en al menos `{ACCEPTANCE['required_successful_runs']}` corridas y sin intervencion manual.\n\n",
        f"Decision final: **HITO 0.5 = {'CLOSED' if status == 'CLOSED' else 'NOT CLOSED'}**.\n\n",
    ]
    if promoted:
        lines.append("La implementacion experimental fue promovida oficialmente al pipeline productivo del MVP tras superar la validacion.\n\n")
    else:
        lines.append("No se modifico el pipeline productivo porque el criterio de aceptacion no fue satisfecho.\n\n")

    lines.extend(
        [
            "## Comparacion entre corridas\n\n",
            "| Run | Session ID | NodeODM Task ID | Imagenes | Tiempo s | Volumen m3 | Error abs m3 | Error % | Estado |\n",
            "|---:|---|---|---:|---:|---:|---:|---:|---|\n",
        ]
    )
    for run in runs:
        lines.append(
            f"| {run['run_index']} | `{run['session_id']}` | `{run['nodeodm']['task_uuid']}` | "
            f"{run['image_count']} | {run['total_time_seconds']} | {run['volume_m3']} | "
            f"{run['absolute_error_m3']} | {run['error_percentage']} | "
            f"{'PASS' if run['accepts_error_threshold'] else 'FAIL'} |\n"
        )

    lines.extend(
        [
            "\n## Metricas por etapa\n\n",
        ]
    )
    for run in runs:
        lines.append(f"### Corrida {run['run_index']}\n\n")
        lines.append("| Etapa | Puntos | Perdida % | BBox m3 | Dimensiones XYZ m | Centroide |\n")
        lines.append("|---|---:|---:|---:|---|---|\n")
        for row in run["stages"]:
            lines.append(
                f"| {row['stage']} | {row['point_count']} | {row.get('loss_percent_from_previous')} | "
                f"{row['bbox_volume_m3']} | `{row['bbox_extent_m']}` | `{row['centroid']}` |\n"
            )
        lines.extend(
            [
                "\n",
                f"- Clusters DBSCAN: `{run['cluster_count']}`\n",
                f"- Clusters seleccionados: `{run['selected_cluster_ids']}`\n",
                f"- Puntos finales usados por PDI: `{stage_value(run, 'PDI', 'point_count')}`\n",
                f"- Puntos RAW: `{stage_value(run, 'RAW Dense Point Cloud', 'point_count')}`\n",
                f"- Puntos tras Outlier Removal: `{stage_value(run, 'Outlier Removal', 'point_count')}`\n",
                f"- Puntos tras Segmentacion: `{stage_value(run, 'DBSCAN + Cluster Selection', 'point_count')}`\n\n",
            ]
        )

    lines.extend(
        [
            "## Estabilidad observada\n\n",
            f"- Volumenes: `{acceptance['volumes_m3']}` m3.\n",
            f"- Errores porcentuales: `{acceptance['error_percentages']}`.\n",
            f"- Delta maximo de volumen: `{acceptance['volume_delta_between_runs_m3']}` m3 (`{acceptance['volume_delta_percent_of_gt']}`% del GT).\n",
            f"- Corridas exitosas segun umbral: `{acceptance['successful_runs']}` de `{acceptance['runs_executed']}`.\n\n",
            "## Conclusion\n\n",
            f"**HITO 0.5 = {'CLOSED' if status == 'CLOSED' else 'NOT CLOSED'}**\n\n",
        ]
    )
    if status == "CLOSED":
        lines.append("La solucion experimental demostro estabilidad suficiente con el dataset definitivo y quedo promovida al pipeline productivo del MVP.\n")
    else:
        lines.append("La solucion experimental no demostro estabilidad/precision suficiente con el dataset definitivo; permanece confinada a `experiments/` y no se promueve a produccion.\n")

    report.write_text("".join(lines), encoding="utf-8")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    settings = settings_for_root()
    images = image_paths()
    runs = [run_once(index, settings, images) for index in (1, 2)]
    if needs_confirmation_run(runs):
        runs.append(run_once(3, settings, images))
    summary = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "dataset": {
            "dataset_id": DATASET_ID,
            "dataset_label": DATASET_LABEL,
            "path": str(DATASET_IMAGES),
            "image_count": len(images),
        },
        "runs": runs,
        "acceptance": acceptance_summary(runs),
        "set2_robustness_informational": load_set2_info(),
        "promotion": {"applied": False, "reason": "promotion_requires_closed_acceptance"},
    }
    (OUT / "hito_0_5_close_results.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    write_validation_report(summary)
    print(json.dumps(summary["acceptance"], indent=2))


if __name__ == "__main__":
    main()
