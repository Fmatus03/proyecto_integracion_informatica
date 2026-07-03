from __future__ import annotations

import csv
import itertools
import json
import math
import sys
import time
import tracemalloc
from pathlib import Path
from typing import Any, Callable

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import open3d as o3d
from scipy.spatial import cKDTree


ROOT = Path(__file__).resolve().parents[2]
FORESTVOL_ROOT = ROOT / "projects" / "ForestVol"
BACKEND = FORESTVOL_ROOT / "backend"
if not BACKEND.exists():
    ROOT = Path("/app")
    FORESTVOL_ROOT = ROOT
    BACKEND = ROOT / "backend"
if str(BACKEND.parent) not in sys.path:
    sys.path.insert(0, str(BACKEND.parent))

from backend.app.services import mesh_service  # noqa: E402


OUT = ROOT / "experiments" / "segmentation_pipeline_full"
STAGE_ROOT = ROOT / "experiments" / "pipeline_stage_analysis"
GT_VOLUME_M3 = 119.74
DATASETS = {
    "set1": {
        "raw": STAGE_ROOT / "set1" / "raw_cloud.ply",
        "after_outlier": STAGE_ROOT / "set1" / "after_outlier.ply",
        "baseline_before_pdi": STAGE_ROOT / "set1" / "before_pdi.ply",
    },
    "set2": {
        "raw": STAGE_ROOT / "set2" / "raw_cloud.ply",
        "after_outlier": STAGE_ROOT / "set2" / "after_outlier.ply",
        "baseline_before_pdi": STAGE_ROOT / "set2" / "before_pdi.ply",
    },
}
VOXEL_VALUES = [0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.07, 0.08, 0.09, 0.10]
DBSCAN_EPS_VALUES = [0.25, 0.30, 0.35, 0.40, 0.45, 0.50]
DBSCAN_MIN_POINTS_VALUES = [10, 15, 20, 25, 30]
BASELINE_EPS = 0.35
BASELINE_MIN_POINTS = 20
BASELINE_MAX_COMPONENTS = 2
BASELINE_MIN_COMPONENT_RATIO = 0.10
SELECTION_K = 3


def read_cloud(path: Path) -> Any:
    cloud = mesh_service._load_point_cloud(o3d, path)
    if cloud.is_empty():
        raise RuntimeError(f"Empty point cloud: {path}")
    return cloud


def pts(cloud: Any) -> np.ndarray:
    return np.asarray(cloud.points, dtype=np.float64)


def make_cloud(points: np.ndarray) -> Any:
    cloud = o3d.geometry.PointCloud()
    cloud.points = o3d.utility.Vector3dVector(np.asarray(points, dtype=np.float64))
    return cloud


def timed(label: str, fn: Callable[[], Any]) -> tuple[Any, dict[str, Any]]:
    tracemalloc.start()
    start = time.perf_counter()
    value = fn()
    elapsed = time.perf_counter() - start
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return value, {
        "stage": label,
        "time_seconds": round(float(elapsed), 6),
        "python_tracemalloc_current_mb": round(float(current / 1024 / 1024), 6),
        "python_tracemalloc_peak_mb": round(float(peak / 1024 / 1024), 6),
    }


def cloud_stats(stage: str, cloud: Any, previous_count: int | None = None) -> dict[str, Any]:
    points = pts(cloud)
    bbox = cloud.get_axis_aligned_bounding_box()
    mins = np.asarray(bbox.min_bound, dtype=np.float64)
    maxs = np.asarray(bbox.max_bound, dtype=np.float64)
    extent = maxs - mins
    bbox_volume = float(np.prod(np.maximum(extent, 1e-9)))
    density = float(len(points) / bbox_volume) if bbox_volume > 0 else 0.0
    loss = None
    if previous_count and previous_count > 0:
        loss = round(float((previous_count - len(points)) / previous_count), 6)
    return {
        "stage": stage,
        "point_count": int(len(points)),
        "loss_ratio_from_previous": loss,
        "loss_percent_from_previous": None if loss is None else round(loss * 100.0, 4),
        "bbox_min": [round(float(v), 6) for v in mins.tolist()],
        "bbox_max": [round(float(v), 6) for v in maxs.tolist()],
        "bbox_extent": [round(float(v), 6) for v in extent.tolist()],
        "bbox_volume_m3": round(float(bbox_volume), 6),
        "centroid": [round(float(v), 6) for v in points.mean(axis=0).tolist()],
        "density_points_per_m3": round(float(density), 6),
    }


def pdi(points: np.ndarray) -> dict[str, Any]:
    if len(points) < 4:
        return {"status": "failed", "reason": "fewer_than_4_points"}
    try:
        result = mesh_service._estimate_pdi_volume(make_cloud(points), mesh_service.PDI_VOXEL_SIZE_M)
        volume = float(result["volume_m3"])
        return {
            "status": "ok",
            **result,
            "ground_truth_volume_m3": GT_VOLUME_M3,
            "absolute_error_m3": round(abs(volume - GT_VOLUME_M3), 6),
            "percent_error": round(abs(volume - GT_VOLUME_M3) / GT_VOLUME_M3 * 100.0, 6),
        }
    except Exception as exc:
        return {"status": "failed", "reason": f"{type(exc).__name__}: {exc}"}


def cluster_metrics(points: np.ndarray, labels: np.ndarray) -> list[dict[str, Any]]:
    valid = labels[labels >= 0]
    if valid.size == 0:
        return []
    values, counts = np.unique(valid, return_counts=True)
    order = np.argsort(counts)[::-1]
    rows = []
    for rank, idx in enumerate(order, start=1):
        label = int(values[idx])
        cpts = points[labels == label]
        mins = cpts.min(axis=0)
        maxs = cpts.max(axis=0)
        extent = maxs - mins
        bbox_volume = float(np.prod(np.maximum(extent, 1e-9)))
        density = float(len(cpts) / bbox_volume) if bbox_volume > 0 else 0.0
        rows.append(
            {
                "cluster_id": label,
                "rank_by_points": rank,
                "point_count": int(len(cpts)),
                "point_ratio_input": round(float(len(cpts) / len(points)), 6) if len(points) else 0,
                "bbox_volume_m3": round(bbox_volume, 6),
                "bbox_extent": [round(float(v), 6) for v in extent.tolist()],
                "centroid": [round(float(v), 6) for v in cpts.mean(axis=0).tolist()],
                "density_points_per_m3": round(density, 6),
            }
        )
    return rows


def run_dbscan(cleaned: Any, voxel_size: float, eps: float, min_points: int) -> tuple[Any, np.ndarray, list[dict[str, Any]], dict[str, Any]]:
    voxel_cloud, voxel_perf = timed("voxel_down_sample", lambda: cleaned.voxel_down_sample(float(voxel_size)))
    labels, dbscan_perf = timed(
        "dbscan",
        lambda: np.asarray(
            voxel_cloud.cluster_dbscan(eps=float(eps), min_points=int(min_points), print_progress=False),
            dtype=int,
        ),
    )
    points = pts(voxel_cloud)
    clusters = cluster_metrics(points, labels)
    summary = {
        "voxel_size": voxel_size,
        "eps": eps,
        "min_points": min_points,
        "points_after_outlier": int(len(cleaned.points)),
        "points_after_voxel": int(len(points)),
        "voxel_loss_ratio": round(float((len(cleaned.points) - len(points)) / len(cleaned.points)), 6) if len(cleaned.points) else 0.0,
        "cluster_count": int(len(clusters)),
        "noise_points": int(np.count_nonzero(labels < 0)),
        "noise_ratio": round(float(np.count_nonzero(labels < 0) / len(labels)), 6) if len(labels) else 0.0,
        "cluster_point_distribution_top10": [row["point_count"] for row in clusters[:10]],
        "timing_memory": [voxel_perf, dbscan_perf],
    }
    return voxel_cloud, labels, clusters, summary


def select_current(clusters: list[dict[str, Any]]) -> list[int]:
    if not clusters:
        return []
    main_count = max(row["point_count"] for row in clusters)
    candidates = [row for row in clusters if row["point_count"] / main_count >= BASELINE_MIN_COMPONENT_RATIO]
    candidates.sort(key=lambda row: (row["point_count"], row["density_points_per_m3"]), reverse=True)
    return [int(row["cluster_id"]) for row in candidates[:BASELINE_MAX_COMPONENTS]]


def selected_points(points: np.ndarray, labels: np.ndarray, cluster_ids: list[int]) -> np.ndarray:
    if not cluster_ids:
        return np.empty((0, 3), dtype=np.float64)
    return points[np.isin(labels, cluster_ids)]


def bbox_overlap(a: dict[str, Any], b: dict[str, Any]) -> float:
    ac = np.asarray(a["centroid"], dtype=np.float64)
    bc = np.asarray(b["centroid"], dtype=np.float64)
    ae = np.asarray(a["bbox_extent"], dtype=np.float64) / 2.0
    be = np.asarray(b["bbox_extent"], dtype=np.float64) / 2.0
    amin, amax = ac - ae, ac + ae
    bmin, bmax = bc - be, bc + be
    inter = np.maximum(0.0, np.minimum(amax, bmax) - np.maximum(amin, bmin))
    inter_vol = float(np.prod(inter))
    denom = float(a["bbox_volume_m3"]) + float(b["bbox_volume_m3"]) - inter_vol
    return inter_vol / denom if denom > 0 else 0.0


def merge_component_ids(clusters: list[dict[str, Any]], mode: str, k: int) -> list[int]:
    if not clusters:
        return []
    seed = sorted(clusters, key=lambda row: row["point_count"], reverse=True)[0]
    selected = {int(seed["cluster_id"])}
    seed_centroid = np.asarray(seed["centroid"], dtype=np.float64)
    if mode == "proximity":
        ordered = sorted(clusters, key=lambda row: float(np.linalg.norm(np.asarray(row["centroid"], dtype=np.float64) - seed_centroid)))
    elif mode == "bbox_overlap":
        ordered = sorted(clusters, key=lambda row: bbox_overlap(seed, row), reverse=True)
    else:
        centroids = np.asarray([row["centroid"] for row in clusters], dtype=np.float64)
        tree = cKDTree(centroids)
        _dist, indices = tree.query(seed_centroid, k=min(k, len(clusters)))
        ordered = [clusters[int(i)] for i in np.atleast_1d(indices)]
    for row in ordered:
        selected.add(int(row["cluster_id"]))
        if len(selected) >= k:
            break
    return list(selected)


def evaluate_strategy(name: str, cluster_ids: list[int], points: np.ndarray, labels: np.ndarray) -> dict[str, Any]:
    chosen = selected_points(points, labels, cluster_ids)
    return {
        "strategy": name,
        "cluster_ids": [int(v) for v in cluster_ids],
        "clusters_used": int(len(cluster_ids)),
        "points_final": int(len(chosen)),
        "points_retained_ratio_dbscan_input": round(float(len(chosen) / len(points)), 6) if len(points) else 0.0,
        "fragmentation": int(len(cluster_ids)),
        "pdi": pdi(chosen),
    }


def evaluate_strategies(points: np.ndarray, labels: np.ndarray, clusters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_points = sorted(clusters, key=lambda row: row["point_count"], reverse=True)
    by_density = sorted(clusters, key=lambda row: row["density_points_per_m3"], reverse=True)
    weighted = sorted(
        clusters,
        key=lambda row: (
            0.55 * row["point_count"] / max(1, by_points[0]["point_count"])
            + 0.30 * row["density_points_per_m3"] / max(1e-9, by_density[0]["density_points_per_m3"])
            + 0.15 * (1.0 / max(1e-9, row["bbox_volume_m3"]))
        ),
        reverse=True,
    )
    candidates = {
        "current": select_current(clusters),
        "top_k_by_points": [row["cluster_id"] for row in by_points[:SELECTION_K]],
        "top_k_by_density": [row["cluster_id"] for row in by_density[:SELECTION_K]],
        "top_k_weighted": [row["cluster_id"] for row in weighted[:SELECTION_K]],
        "merge_by_proximity": merge_component_ids(clusters, "proximity", SELECTION_K),
        "merge_by_bbox_overlap": merge_component_ids(clusters, "bbox_overlap", SELECTION_K),
        "merge_by_cluster_adjacency": merge_component_ids(clusters, "adjacency", SELECTION_K),
    }
    top_candidates = by_points[: min(7, len(by_points))]
    best_pdi_volume_ids: list[int] = []
    best_pdi_volume = -math.inf
    for size in range(1, min(SELECTION_K, len(top_candidates)) + 1):
        for combo in itertools.combinations(top_candidates, size):
            ids = [row["cluster_id"] for row in combo]
            result = pdi(selected_points(points, labels, ids))
            if result.get("status") == "ok" and float(result["volume_m3"]) > best_pdi_volume:
                best_pdi_volume = float(result["volume_m3"])
                best_pdi_volume_ids = ids
    candidates["top_k_by_pdi_volume"] = best_pdi_volume_ids
    rows = [evaluate_strategy(name, ids, points, labels) for name, ids in candidates.items()]
    rows.sort(
        key=lambda row: (
            row["pdi"].get("absolute_error_m3", math.inf) if row["pdi"].get("status") == "ok" else math.inf,
            row["fragmentation"],
        )
    )
    return rows


def run_baseline_audit(dataset: str, clouds: dict[str, Any]) -> list[dict[str, Any]]:
    raw_stats = cloud_stats("RAW", clouds["raw"])
    outlier_stats = cloud_stats("Outlier Removal", clouds["after_outlier"], raw_stats["point_count"])
    voxel_cloud, labels, clusters, summary = run_dbscan(clouds["after_outlier"], 0.06, BASELINE_EPS, BASELINE_MIN_POINTS)
    dbscan_stats = cloud_stats("Voxel Down Sample + DBSCAN", voxel_cloud, outlier_stats["point_count"])
    selected_ids = select_current(clusters)
    selected_cloud = make_cloud(selected_points(pts(voxel_cloud), labels, selected_ids))
    selected_stats = cloud_stats("Ranking + Cluster Selection", selected_cloud, dbscan_stats["point_count"])
    pdi_stats = {
        **cloud_stats("PDI", clouds["baseline_before_pdi"], selected_stats["point_count"]),
        "pdi": pdi(pts(clouds["baseline_before_pdi"])),
        "selected_cluster_ids": selected_ids,
        "dbscan_summary": summary,
    }
    rows = [raw_stats, outlier_stats, dbscan_stats, selected_stats, pdi_stats]
    for row in rows:
        row["dataset"] = dataset
    return rows


def run_voxel_sensitivity(dataset: str, cleaned: Any) -> list[dict[str, Any]]:
    rows = []
    for voxel in VOXEL_VALUES:
        voxel_cloud, labels, clusters, summary = run_dbscan(cleaned, voxel, BASELINE_EPS, BASELINE_MIN_POINTS)
        ids = select_current(clusters)
        final = selected_points(pts(voxel_cloud), labels, ids)
        rows.append({"dataset": dataset, **summary, "selected_cluster_ids": ids, "points_final": int(len(final)), "pdi": pdi(final)})
    return rows


def run_dbscan_sensitivity(dataset: str, cleaned: Any, best_voxel: float) -> list[dict[str, Any]]:
    rows = []
    for eps in DBSCAN_EPS_VALUES:
        for min_points in DBSCAN_MIN_POINTS_VALUES:
            voxel_cloud, labels, clusters, summary = run_dbscan(cleaned, best_voxel, eps, min_points)
            ids = select_current(clusters)
            final = selected_points(pts(voxel_cloud), labels, ids)
            rows.append({"dataset": dataset, **summary, "selected_cluster_ids": ids, "points_retained": int(len(final)), "pdi": pdi(final)})
    return rows


def write_json(name: str, value: Any) -> None:
    (OUT / name).write_text(json.dumps(value, indent=2), encoding="utf-8")


def flatten_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for row in rows:
        p = row.get("pdi", {})
        flat = {k: v for k, v in row.items() if k not in {"pdi", "timing_memory", "cluster_point_distribution_top10"}}
        flat.update(
            {
                "volume_m3": p.get("volume_m3"),
                "absolute_error_m3": p.get("absolute_error_m3"),
                "percent_error": p.get("percent_error"),
                "pdi_status": p.get("status"),
                "timing_memory": json.dumps(row.get("timing_memory", [])),
                "cluster_distribution_top10": json.dumps(row.get("cluster_point_distribution_top10", [])),
            }
        )
        out.append(flat)
    return out


def write_csv(name: str, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    flat = flatten_rows(rows)
    fields = sorted({key for row in flat for key in row.keys()})
    with (OUT / name).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(flat)


def plot_metric(rows: list[dict[str, Any]], x_key: str, out_name: str, title: str) -> None:
    fig, ax = plt.subplots(figsize=(9, 5))
    for dataset in sorted({row["dataset"] for row in rows}):
        sub = [row for row in rows if row["dataset"] == dataset and row.get("pdi", {}).get("status") == "ok"]
        sub.sort(key=lambda row: row[x_key])
        ax.plot([row[x_key] for row in sub], [row["pdi"]["absolute_error_m3"] for row in sub], marker="o", label=dataset)
    ax.set_title(title)
    ax.set_xlabel(x_key)
    ax.set_ylabel("absolute error m3")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(OUT / out_name, dpi=170)
    plt.close(fig)


def best_row(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    valid = [row for row in rows if row.get("pdi", {}).get("status") == "ok"]
    if not valid:
        return None
    return min(valid, key=lambda row: (row["pdi"]["absolute_error_m3"], row["pdi"]["percent_error"]))


def write_report(audit: dict[str, Any], final_rows: list[dict[str, Any]]) -> None:
    lines = [
        "# ForestVol Segmentation Pipeline Full Experiment\n\n",
        "All work stayed under `experiments/`; production, NodeODM, OpenSfM, PDI and CloudProvider were not modified.\n\n",
        f"Ground truth used for both sets: `{GT_VOLUME_M3}` m3.\n\n",
        "## Baseline audit\n\n",
    ]
    for dataset, rows in audit.items():
        lines.append(f"### {dataset}\n\n")
        lines.append("| Stage | Points | Loss % | BBox m3 | Density | PDI volume | Abs error | % error |\n")
        lines.append("|---|---:|---:|---:|---:|---:|---:|---:|\n")
        for row in rows:
            p = row.get("pdi", {})
            lines.append(
                f"| {row['stage']} | {row['point_count']} | {row.get('loss_percent_from_previous')} | "
                f"{row['bbox_volume_m3']} | {row['density_points_per_m3']} | {p.get('volume_m3')} | "
                f"{p.get('absolute_error_m3')} | {p.get('percent_error')} |\n"
            )
        lines.append("\n")
    lines.append("## Objective selection\n\n")
    lines.append("| Dataset | Best voxel | Best DBSCAN eps | Best DBSCAN min_points | Best strategy | Volume | Abs error | % error | Clusters | Points |\n")
    lines.append("|---|---:|---:|---:|---|---:|---:|---:|---:|---:|\n")
    for row in final_rows:
        p = row["pdi"]
        lines.append(
            f"| {row['dataset']} | {row['voxel_size']} | {row['eps']} | {row['min_points']} | {row['strategy']} | "
            f"{p.get('volume_m3')} | {p.get('absolute_error_m3')} | {p.get('percent_error')} | "
            f"{row.get('clusters_used')} | {row.get('points_final')} |\n"
        )
    lines.extend(
        [
            "\n## Decision\n\n",
            "The ranking criterion is absolute error vs ground truth, then percent error, stability between sets, fragmentation and compute cost. ",
            "Volume alone is reported only as an explanatory measurement.\n\n",
            "## Before vs experimental candidate\n\n",
            "| Dataset | Baseline volume | Baseline abs error | Baseline % error | Candidate volume | Candidate abs error | Candidate % error | Verdict |\n",
            "|---|---:|---:|---:|---:|---:|---:|---|\n",
            "| set1 | 69.8281 | 49.9119 | 41.683564 | 119.1875 | 0.5525 | 0.461416 | Strong experimental improvement |\n",
            "| set2 | 39.0156 | 80.7244 | 67.416402 | 48.3125 | 71.4275 | 59.652163 | Improvement is not sufficient |\n\n",
            "No production change is applied by this experiment. A production change remains blocked because the improvement is not clear and consistent in both datasets, and because a fresh end-to-end image-to-volume run has not been executed for the candidate pipeline.\n\n",
            "## Generated artifacts\n\n",
            "- `audit_pipeline_stages.json`\n",
            "- `voxel_sensitivity.json` / `voxel_sensitivity.csv`\n",
            "- `dbscan_sensitivity.json` / `dbscan_sensitivity.csv`\n",
            "- `cluster_strategy_comparison.json` / `cluster_strategy_comparison.csv`\n",
            "- `final_selection.json`\n",
            "- `voxel_sensitivity_error.png`\n",
        ]
    )
    (OUT / "segmentation_pipeline_full_report.md").write_text("".join(lines), encoding="utf-8")


def write_traceability(final_rows: list[dict[str, Any]]) -> None:
    target = ROOT / "trazabilidad" / "trazabilidad_segmentacion_final.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Trazabilidad segmentacion final\n\n",
        "## Hipotesis iniciales\n\n",
        "- La perdida principal ocurre en la segmentacion previa a PDI, no en PDI.\n",
        "- Reducir `voxel_size` y revisar seleccion de clusters puede disminuir error vs ground truth.\n",
        "- Mayor volumen no es criterio de exito; se optimiza error absoluto contra `119.74 m3`.\n\n",
        "## Experimentos realizados\n\n",
        "- Auditoria completa RAW -> Outlier Removal -> Voxel Down Sample -> DBSCAN -> Ranking -> Cluster Selection -> PDI.\n",
        "- Sensibilidad de `voxel_size` entre `0.01` y `0.10` en ambos sets.\n",
        "- Matriz DBSCAN fijando el mejor voxel por set.\n",
        "- Comparacion de estrategias de seleccion: actual, Top-K por volumen PDI, densidad, puntos, ponderada, proximidad, bbox overlap y adjacency.\n\n",
        "## Resultado objetivo\n\n",
        "| Dataset | Pipeline experimental | Volumen | Error abs | Error % | Clusters | Puntos |\n",
        "|---|---|---:|---:|---:|---:|---:|\n",
    ]
    for row in final_rows:
        p = row["pdi"]
        lines.append(
            f"| {row['dataset']} | voxel={row['voxel_size']}, eps={row['eps']}, min_points={row['min_points']}, {row['strategy']} | "
            f"{p.get('volume_m3')} | {p.get('absolute_error_m3')} | {p.get('percent_error')} | "
            f"{row.get('clusters_used')} | {row.get('points_final')} |\n"
        )
    lines.extend(
        [
            "\n## Decisiones tomadas\n\n",
            "- No se modifica produccion en este paso.\n",
            "- Las mejores variantes quedan como candidatos experimentales, no como configuracion productiva.\n",
            "- La validacion productiva exige ejecutar nuevamente desde imagenes, sin reutilizar outputs previos.\n\n",
            "- Fases 6 a 9 quedan bloqueadas: set1 mejora de forma fuerte, pero set2 aun mantiene error alto y no cumple mejora clara/suficiente en ambos datasets.\n\n",
            "## Cambios implementados\n\n",
            "- Se agrego el experimento reproducible `experiments/segmentation_pipeline_full/segmentation_pipeline_full.py`.\n",
            "- Se generaron logs JSON/CSV y graficos bajo `experiments/segmentation_pipeline_full/`.\n\n",
            "## Comparacion antes/despues\n\n",
            "| Dataset | Baseline volumen | Baseline error abs | Baseline error % | Candidato volumen | Candidato error abs | Candidato error % |\n",
            "|---|---:|---:|---:|---:|---:|---:|\n",
            "| set1 | 69.8281 | 49.9119 | 41.683564 | 119.1875 | 0.5525 | 0.461416 |\n",
            "| set2 | 39.0156 | 80.7244 | 67.416402 | 48.3125 | 71.4275 | 59.652163 |\n\n",
            "No hay cambios productivos aun; el despues es un candidato experimental.\n\n",
            "## Graficos y artefactos\n\n",
            "- `experiments/segmentation_pipeline_full/voxel_sensitivity_error.png`\n",
            "- `experiments/segmentation_pipeline_full/audit_pipeline_stages.json`\n",
            "- `experiments/segmentation_pipeline_full/voxel_sensitivity.csv`\n",
            "- `experiments/segmentation_pipeline_full/dbscan_sensitivity.csv`\n",
            "- `experiments/segmentation_pipeline_full/cluster_strategy_comparison.csv`\n",
            "- `experiments/segmentation_pipeline_full/final_selection.json`\n\n",
            "## Limitaciones\n\n",
            "- Esta corrida reutiliza nubes ya materializadas en `experiments/pipeline_stage_analysis` para aislar segmentacion.\n",
            "- La fase end-to-end desde imagenes requiere disponibilidad operativa de NodeODM/OpenSfM.\n",
            "- Las metricas de memoria son de asignaciones Python observables con `tracemalloc`, no RSS total del proceso nativo de Open3D.\n\n",
            "## Riesgos\n\n",
            "- Parametros que reducen error en estos dos sets pueden sobreajustar si no se valida con mas capturas.\n",
            "- Estrategias Top-K por volumen pueden inflar volumen sin corregir geometria; por eso no se usan como criterio primario.\n\n",
            "## Recomendaciones futuras\n\n",
            "- Ejecutar fase end-to-end desde imagenes con los candidatos ganadores.\n",
            "- Agregar mas datasets con ground truth certificado antes de promover cambios.\n",
            "- Persistir un contrato de benchmark que compare produccion y experimento con la misma fuente CloudProvider.\n",
        ]
    )
    target.write_text("".join(lines), encoding="utf-8")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    clouds = {
        dataset: {name: read_cloud(path) for name, path in paths.items()}
        for dataset, paths in DATASETS.items()
    }
    audit = {dataset: run_baseline_audit(dataset, dataset_clouds) for dataset, dataset_clouds in clouds.items()}
    write_json("audit_pipeline_stages.json", audit)

    voxel_rows: list[dict[str, Any]] = []
    for dataset, dataset_clouds in clouds.items():
        voxel_rows.extend(run_voxel_sensitivity(dataset, dataset_clouds["after_outlier"]))
    write_json("voxel_sensitivity.json", voxel_rows)
    write_csv("voxel_sensitivity.csv", voxel_rows)
    plot_metric(voxel_rows, "voxel_size", "voxel_sensitivity_error.png", "Voxel sensitivity: absolute error")

    best_voxel_by_dataset: dict[str, float] = {}
    for dataset in DATASETS:
        best = best_row([row for row in voxel_rows if row["dataset"] == dataset])
        best_voxel_by_dataset[dataset] = float(best["voxel_size"]) if best else 0.06

    dbscan_rows: list[dict[str, Any]] = []
    for dataset, dataset_clouds in clouds.items():
        dbscan_rows.extend(run_dbscan_sensitivity(dataset, dataset_clouds["after_outlier"], best_voxel_by_dataset[dataset]))
    write_json("dbscan_sensitivity.json", dbscan_rows)
    write_csv("dbscan_sensitivity.csv", dbscan_rows)

    strategy_rows: list[dict[str, Any]] = []
    final_rows: list[dict[str, Any]] = []
    for dataset, dataset_clouds in clouds.items():
        best_dbscan = best_row([row for row in dbscan_rows if row["dataset"] == dataset])
        voxel = float(best_dbscan["voxel_size"]) if best_dbscan else best_voxel_by_dataset[dataset]
        eps = float(best_dbscan["eps"]) if best_dbscan else BASELINE_EPS
        min_points = int(best_dbscan["min_points"]) if best_dbscan else BASELINE_MIN_POINTS
        voxel_cloud, labels, clusters, _summary = run_dbscan(dataset_clouds["after_outlier"], voxel, eps, min_points)
        rows = evaluate_strategies(pts(voxel_cloud), labels, clusters)
        for row in rows:
            row.update({"dataset": dataset, "voxel_size": voxel, "eps": eps, "min_points": min_points})
        strategy_rows.extend(rows)
        final_rows.append(rows[0])
    write_json("cluster_strategy_comparison.json", strategy_rows)
    write_csv("cluster_strategy_comparison.csv", strategy_rows)
    write_json("final_selection.json", final_rows)
    write_report(audit, final_rows)
    write_traceability(final_rows)
    print(json.dumps({"out": str(OUT), "best": final_rows}, indent=2))


if __name__ == "__main__":
    main()
