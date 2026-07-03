from __future__ import annotations

import csv
import json
import math
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import open3d as o3d
from scipy.spatial import cKDTree


ROOT = Path(os.environ.get("FORESTVOL_ROOT", "/app"))
BACKEND = ROOT / "backend"
if not BACKEND.exists():
    BACKEND = ROOT / "projects" / "ForestVol" / "backend"
DATA_ROOT = ROOT / "data"
if not DATA_ROOT.exists():
    DATA_ROOT = ROOT / "projects" / "ForestVol" / "data"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.services import mesh_service  # noqa: E402


OUTPUT_DIR = ROOT / "experiments" / "pipeline_diagnostics"
GT_VOLUME_M3 = 119.74
NODEODM_METRICS_PATH = Path(os.environ.get("NODEODM_OPEN_SFM_METRICS", "/tmp/nodeodm_opensfm_metrics.json"))


@dataclass(frozen=True)
class DatasetConfig:
    name: str
    image_dir: Path
    productive_session: str
    productive_cloud: Path
    benchmark_cloud: Path
    productive_report: Path
    benchmark_volume_m3: float


DATASETS = [
    DatasetConfig(
        name="set1",
        image_dir=ROOT / "projects" / "ForestVol" / "set_imagenes+guia" / "set_fotos_castillo_de_madera",
        productive_session="b3c14c84-b660-407f-817f-1fc185ce3e9c",
        productive_cloud=DATA_ROOT
        / "processed"
        / "b3c14c84-b660-407f-817f-1fc185ce3e9c"
        / "point_cloud.ply",
        benchmark_cloud=DATA_ROOT
        / "processed"
        / "a3c36266-f866-402f-8bc8-1c2b59b4a4ce"
        / "surface_closure_diagnostics"
        / "poisson_input_cloud.ply",
        productive_report=DATA_ROOT / "pdi_productive_migration_hito05_set1.json",
        benchmark_volume_m3=97.375,
    ),
    DatasetConfig(
        name="set2",
        image_dir=ROOT / "projects" / "ForestVol" / "set_imagenes+guia" / "set_fotos_castillo_de_madera_2",
        productive_session="723f91e2-b1b5-43f7-b336-6816d8300509",
        productive_cloud=DATA_ROOT
        / "processed"
        / "723f91e2-b1b5-43f7-b336-6816d8300509"
        / "point_cloud.ply",
        benchmark_cloud=DATA_ROOT
        / "processed"
        / "b6b04af0-122f-4fcc-af8a-cc553ca5e28d"
        / "surface_closure_diagnostics_2"
        / "poisson_input_cloud.ply",
        productive_report=DATA_ROOT / "pdi_productive_migration_hito05_set2.json",
        benchmark_volume_m3=132.671875,
    ),
]


def as_jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): as_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [as_jsonable(v) for v in value]
    if isinstance(value, np.ndarray):
        return as_jsonable(value.tolist())
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, Path):
        return str(value)
    return value


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"available": False, "path": str(path)}
    return json.loads(path.read_text(encoding="utf-8"))


def load_nodeodm_metrics() -> dict[str, Any]:
    if NODEODM_METRICS_PATH.exists():
        return read_json(NODEODM_METRICS_PATH)
    return {}


def image_metrics(image_dir: Path) -> dict[str, Any]:
    suffixes = {".jpg", ".jpeg", ".png", ".tif", ".tiff"}
    files = [p for p in image_dir.rglob("*") if p.is_file() and p.suffix.lower() in suffixes]
    resolutions: dict[str, int] = {}
    samples: list[dict[str, Any]] = []
    for path in files:
        image = o3d.io.read_image(str(path))
        arr = np.asarray(image)
        if arr.ndim < 2:
            continue
        height, width = int(arr.shape[0]), int(arr.shape[1])
        key = f"{width}x{height}"
        resolutions[key] = resolutions.get(key, 0) + 1
        if len(samples) < 8:
            samples.append({"file": str(path), "width": width, "height": height})
    return {
        "image_dir": str(image_dir),
        "image_count": len(files),
        "resolutions": resolutions,
        "sample_images": samples,
        "discarded_images": 0,
        "discard_reason": "No upload/reconstruction discard list was present in the persisted artifacts.",
    }


def points_from_cloud(cloud: Any) -> np.ndarray:
    return np.asarray(cloud.points, dtype=np.float64)


def cloud_stats(cloud: Any, name: str) -> dict[str, Any]:
    points = points_from_cloud(cloud)
    if len(points) == 0:
        return {"name": name, "point_count": 0}
    bbox = cloud.get_axis_aligned_bounding_box()
    mins = np.asarray(bbox.min_bound, dtype=float)
    maxs = np.asarray(bbox.max_bound, dtype=float)
    extent = np.asarray(bbox.get_extent(), dtype=float)
    positive_extent = extent[extent > 0]
    bbox_volume = float(np.prod(positive_extent)) if positive_extent.size == 3 else 0.0
    density = float(len(points) / bbox_volume) if bbox_volume > 0 else 0.0
    tree = cKDTree(points)
    sample = points
    if len(points) > 12000:
        sample = points[np.linspace(0, len(points) - 1, 12000).astype(int)]
    nn, _ = tree.query(sample, k=2)
    nn = nn[:, 1]
    histograms = {}
    for axis, label in enumerate(("x", "y", "z")):
        hist, edges = np.histogram(points[:, axis], bins=20)
        histograms[label] = {"counts": hist.astype(int).tolist(), "edges": [round(float(v), 6) for v in edges.tolist()]}
    return {
        "name": name,
        "point_count": int(len(points)),
        "bbox_min": [round(float(v), 6) for v in mins.tolist()],
        "bbox_max": [round(float(v), 6) for v in maxs.tolist()],
        "bbox_extent": [round(float(v), 6) for v in extent.tolist()],
        "bbox_volume_m3": round(bbox_volume, 6),
        "density_points_per_m3": round(density, 6),
        "mean_nn_distance_m": round(float(np.mean(nn)), 6),
        "median_nn_distance_m": round(float(np.median(nn)), 6),
        "std_xyz": [round(float(v), 6) for v in np.std(points, axis=0).tolist()],
        "centroid": [round(float(v), 6) for v in np.mean(points, axis=0).tolist()],
        "histograms": histograms,
    }


def downsample_points(points: np.ndarray, limit: int = 12000) -> np.ndarray:
    if len(points) <= limit:
        return points
    rng = np.random.default_rng(20260629)
    return points[rng.choice(len(points), size=limit, replace=False)]


def cloud_distance_metrics(source: np.ndarray, target: np.ndarray, overlap_threshold_m: float = 0.25) -> dict[str, Any]:
    src = downsample_points(source)
    tgt = downsample_points(target)
    src_tree = cKDTree(src)
    tgt_tree = cKDTree(tgt)
    src_to_tgt, _ = tgt_tree.query(src, k=1)
    tgt_to_src, _ = src_tree.query(tgt, k=1)
    chamfer = float(np.mean(src_to_tgt) + np.mean(tgt_to_src)) / 2.0
    hausdorff = float(max(np.max(src_to_tgt), np.max(tgt_to_src)))
    return {
        "sample_size_source": int(len(src)),
        "sample_size_target": int(len(tgt)),
        "chamfer_distance_m": round(chamfer, 6),
        "hausdorff_distance_m": round(hausdorff, 6),
        "productive_to_benchmark_mean_m": round(float(np.mean(src_to_tgt)), 6),
        "benchmark_to_productive_mean_m": round(float(np.mean(tgt_to_src)), 6),
        "productive_overlap_ratio_at_0_25m": round(float(np.mean(src_to_tgt <= overlap_threshold_m)), 6),
        "benchmark_overlap_ratio_at_0_25m": round(float(np.mean(tgt_to_src <= overlap_threshold_m)), 6),
    }


def icp_metrics(source_cloud: Any, target_cloud: Any) -> dict[str, Any]:
    source = source_cloud
    target = target_cloud
    if len(source.points) > 12000:
        source = source.voxel_down_sample(0.05)
    if len(target.points) > 12000:
        target = target.voxel_down_sample(0.05)
    try:
        result = o3d.pipelines.registration.registration_icp(
            source,
            target,
            1.0,
            np.eye(4),
            o3d.pipelines.registration.TransformationEstimationPointToPoint(),
            o3d.pipelines.registration.ICPConvergenceCriteria(max_iteration=60),
        )
        return {
            "fitness": round(float(result.fitness), 6),
            "inlier_rmse_m": round(float(result.inlier_rmse), 6),
            "transformation": np.asarray(result.transformation).round(6).tolist(),
        }
    except Exception as exc:
        return {"available": False, "error": str(exc)}


def load_cloud(path: Path) -> Any:
    cloud = o3d.io.read_point_cloud(str(path))
    if cloud.is_empty():
        raise RuntimeError(f"Empty point cloud: {path}")
    return cloud


def record_stage(rows: list[dict[str, Any]], dataset: str, stage: str, cloud: Any, details: dict[str, Any] | None = None) -> dict[str, Any]:
    stats = cloud_stats(cloud, stage)
    row = {
        "dataset": dataset,
        "stage": stage,
        "point_count": stats.get("point_count"),
        "bbox_x_m": stats.get("bbox_extent", [None, None, None])[0],
        "bbox_y_m": stats.get("bbox_extent", [None, None, None])[1],
        "bbox_z_m": stats.get("bbox_extent", [None, None, None])[2],
        "bbox_volume_m3": stats.get("bbox_volume_m3"),
        "density_points_per_m3": stats.get("density_points_per_m3"),
        "mean_nn_distance_m": stats.get("mean_nn_distance_m"),
        "median_nn_distance_m": stats.get("median_nn_distance_m"),
    }
    if details:
        row.update(details)
    rows.append(row)
    return stats


def instrument_productive_pipeline(cfg: DatasetConfig, rows: list[dict[str, Any]]) -> dict[str, Any]:
    productive_report = read_json(cfg.productive_report)
    raw = load_cloud(cfg.productive_cloud)
    stages: dict[str, Any] = {}
    stages["nodeodm_raw_point_cloud"] = record_stage(rows, cfg.name, "nodeodm_raw_point_cloud", raw)

    scale_factor_m, scale_quality = mesh_service._resolve_metric_point_cloud_scale(
        point_cloud_scale_m_per_unit=1.0,
        scale_source="gcp_or_nodeodm_metric_output",
        scale_px_per_cm=None,
    )
    scaled = raw.scale(scale_factor_m, center=(0.0, 0.0, 0.0))
    stages["metric_scaled_cloud"] = record_stage(
        rows,
        cfg.name,
        "metric_scaled_cloud",
        scaled,
        {"scale_factor_m_per_unit": scale_factor_m},
    )

    before_cleanup_count = len(scaled.points)
    cleaned = scaled
    cleanup_steps: list[dict[str, Any]] = []
    voxel_size_m = None
    if voxel_size_m and voxel_size_m > 0:
        before = len(cleaned.points)
        cleaned = cleaned.voxel_down_sample(voxel_size_m)
        cleanup_steps.append({"filter": "voxel_downsample", "before": before, "after": len(cleaned.points)})
    before = len(cleaned.points)
    cleaned, _ = cleaned.remove_statistical_outlier(nb_neighbors=24, std_ratio=2.0)
    cleanup_steps.append({"filter": "statistical_outlier", "before": before, "after": len(cleaned.points)})
    for step in cleanup_steps:
        step["removed"] = int(step["before"] - step["after"])
        step["removed_ratio"] = round(float(step["removed"] / step["before"]), 6) if step["before"] else None
    stages["cleaned_cloud"] = record_stage(
        rows,
        cfg.name,
        "cleaned_cloud",
        cleaned,
        {
            "points_removed_from_previous": before_cleanup_count - len(cleaned.points),
            "removed_ratio_from_previous": round(float((before_cleanup_count - len(cleaned.points)) / before_cleanup_count), 6)
            if before_cleanup_count
            else None,
        },
    )

    before_segmentation_count = len(cleaned.points)
    segmented, segmentation_quality = mesh_service._segment_woodpile_components(
        cleaned,
        segmentation_voxel_size_m=0.06,
        cluster_eps_m=0.35,
        cluster_min_points=20,
        max_components=2,
        min_component_ratio=0.10,
        max_component_height_m=8.0,
        max_component_bbox_volume_m3=500.0,
        max_component_axis_ratio=8.0,
    )
    stages["pdi_input_cloud"] = record_stage(
        rows,
        cfg.name,
        "pdi_input_cloud",
        segmented,
        {
            "points_removed_from_previous": before_segmentation_count - len(segmented.points),
            "removed_ratio_from_previous": round(
                float((before_segmentation_count - len(segmented.points)) / before_segmentation_count), 6
            )
            if before_segmentation_count
            else None,
        },
    )

    o3d.io.write_point_cloud(str(OUTPUT_DIR / f"{cfg.name}_productive_pdi_input.ply"), segmented)
    pdi = mesh_service._estimate_pdi_volume(segmented, mesh_service.PDI_VOXEL_SIZE_M)
    quality_gates, pdi_quality = mesh_service._pdi_quality_gates(segmented)
    confidence_score, confidence_level, diagnostic = mesh_service._pdi_confidence_score(quality_gates)
    nodeodm_points = stages["nodeodm_raw_point_cloud"]["point_count"]
    pdi_points = stages["pdi_input_cloud"]["point_count"]
    return {
        "productive_report_path": str(cfg.productive_report),
        "productive_report": productive_report,
        "scale_quality": scale_quality,
        "cleanup_steps": cleanup_steps,
        "segmentation_quality": segmentation_quality,
        "stages": stages,
        "pdi_metrics_recomputed": pdi,
        "quality_gates_recomputed": quality_gates,
        "pdi_quality_recomputed": pdi_quality,
        "confidence_recomputed": {
            "score": confidence_score,
            "level": confidence_level,
            "diagnostic": diagnostic,
        },
        "percentage_points_removed_nodeodm_to_pdi": round(float((nodeodm_points - pdi_points) / nodeodm_points * 100.0), 4)
        if nodeodm_points
        else None,
    }


def benchmark_cloud_metrics(cfg: DatasetConfig, rows: list[dict[str, Any]]) -> dict[str, Any]:
    benchmark = load_cloud(cfg.benchmark_cloud)
    stats = record_stage(rows, cfg.name, "benchmark_experimental_pdi_input", benchmark)
    pdi = mesh_service._estimate_pdi_volume(benchmark, mesh_service.PDI_VOXEL_SIZE_M)
    return {
        "path": str(cfg.benchmark_cloud),
        "stats": stats,
        "pdi_metrics_recomputed": pdi,
        "benchmark_reference_volume_m3": cfg.benchmark_volume_m3,
    }


def compare_clouds(cfg: DatasetConfig, productive_pdi_path: Path) -> dict[str, Any]:
    productive = load_cloud(productive_pdi_path)
    benchmark = load_cloud(cfg.benchmark_cloud)
    prod_stats = cloud_stats(productive, "productive_pdi_input")
    bench_stats = cloud_stats(benchmark, "benchmark_experimental_pdi_input")
    prod_pts = points_from_cloud(productive)
    bench_pts = points_from_cloud(benchmark)
    distances = cloud_distance_metrics(prod_pts, bench_pts)
    icp = icp_metrics(productive, benchmark)
    return {
        "productive_cloud": str(productive_pdi_path),
        "benchmark_cloud": str(cfg.benchmark_cloud),
        "productive_stats": prod_stats,
        "benchmark_stats": bench_stats,
        "point_count_ratio_productive_to_benchmark": round(prod_stats["point_count"] / bench_stats["point_count"], 6),
        "point_count_delta": int(prod_stats["point_count"] - bench_stats["point_count"]),
        "bbox_extent_delta_m": [
            round(float(p - b), 6) for p, b in zip(prod_stats["bbox_extent"], bench_stats["bbox_extent"], strict=True)
        ],
        "bbox_volume_ratio_productive_to_benchmark": round(prod_stats["bbox_volume_m3"] / bench_stats["bbox_volume_m3"], 6)
        if bench_stats["bbox_volume_m3"]
        else None,
        "density_ratio_productive_to_benchmark": round(
            prod_stats["density_points_per_m3"] / bench_stats["density_points_per_m3"], 6
        )
        if bench_stats["density_points_per_m3"]
        else None,
        "distance_metrics": distances,
        "icp_metrics": icp,
    }


def first_divergence(productive: dict[str, Any], benchmark: dict[str, Any], comparison: dict[str, Any]) -> dict[str, Any]:
    bench_points = benchmark["stats"]["point_count"]
    bench_bbox = benchmark["stats"]["bbox_volume_m3"]
    stages = productive["stages"]
    ordered = ["nodeodm_raw_point_cloud", "cleaned_cloud", "pdi_input_cloud"]
    for stage in ordered:
        stats = stages[stage]
        point_delta_ratio = abs(stats["point_count"] - bench_points) / bench_points if bench_points else math.inf
        bbox_delta_ratio = abs(stats["bbox_volume_m3"] - bench_bbox) / bench_bbox if bench_bbox else math.inf
        if point_delta_ratio >= 0.10 or bbox_delta_ratio >= 0.10:
            reason = {
                "stage": stage,
                "point_delta_ratio_vs_benchmark": round(float(point_delta_ratio), 6),
                "bbox_volume_delta_ratio_vs_benchmark": round(float(bbox_delta_ratio), 6),
                "stage_point_count": stats["point_count"],
                "benchmark_point_count": bench_points,
                "stage_bbox_volume_m3": stats["bbox_volume_m3"],
                "benchmark_bbox_volume_m3": bench_bbox,
            }
            if stage == "nodeodm_raw_point_cloud":
                reason["bottleneck"] = "OpenSfM/NodeODM reconstruction output differs before productive filtering."
            elif stage == "cleaned_cloud":
                reason["bottleneck"] = "Productive cleanup/filtering is the first significant divergence."
            else:
                reason["bottleneck"] = "Productive DBSCAN woodpile segmentation immediately before PDI is the first significant divergence."
            return reason
    return {
        "stage": "no_significant_stage_delta_by_threshold",
        "bottleneck": "No stage crossed the fixed 10% point-count/bbox-volume divergence threshold.",
        "cloud_distance_metrics": comparison["distance_metrics"],
    }


def plot_overlay(cfg: DatasetConfig, productive_pdi_path: Path) -> None:
    prod = downsample_points(points_from_cloud(load_cloud(productive_pdi_path)), 5000)
    bench = downsample_points(points_from_cloud(load_cloud(cfg.benchmark_cloud)), 5000)
    fig = plt.figure(figsize=(10, 8))
    ax = fig.add_subplot(111, projection="3d")
    ax.scatter(bench[:, 0], bench[:, 1], bench[:, 2], s=2, c="#2f80ed", alpha=0.35, label="benchmark")
    ax.scatter(prod[:, 0], prod[:, 1], prod[:, 2], s=2, c="#eb5757", alpha=0.35, label="productive")
    ax.set_title(f"{cfg.name}: benchmark vs productive PDI input")
    ax.set_xlabel("X m")
    ax.set_ylabel("Y m")
    ax.set_zlabel("Z m")
    ax.legend()
    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / f"{cfg.name}_cloud_overlay.png", dpi=180)
    plt.close(fig)


def plot_histograms(cfg: DatasetConfig, productive_pdi_path: Path) -> None:
    prod = points_from_cloud(load_cloud(productive_pdi_path))
    bench = points_from_cloud(load_cloud(cfg.benchmark_cloud))
    fig, axes = plt.subplots(1, 3, figsize=(14, 4))
    for axis, label in enumerate(("X", "Y", "Z")):
        axes[axis].hist(bench[:, axis], bins=35, alpha=0.55, label="benchmark", color="#2f80ed")
        axes[axis].hist(prod[:, axis], bins=35, alpha=0.55, label="productive", color="#eb5757")
        axes[axis].set_title(f"{label} distribution")
        axes[axis].set_xlabel("meters")
        axes[axis].set_ylabel("points")
    axes[0].legend()
    fig.suptitle(f"{cfg.name}: XYZ histograms")
    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / f"{cfg.name}_xyz_histograms.png", dpi=180)
    plt.close(fig)


def plot_evolution(rows: list[dict[str, Any]]) -> None:
    for metric, filename, ylabel in [
        ("point_count", "point_count_evolution.png", "points"),
        ("bbox_volume_m3", "bbox_volume_evolution.png", "bbox volume m3"),
    ]:
        fig, ax = plt.subplots(figsize=(11, 5))
        for dataset in sorted({row["dataset"] for row in rows}):
            subset = [row for row in rows if row["dataset"] == dataset]
            ax.plot([row["stage"] for row in subset], [row[metric] for row in subset], marker="o", label=dataset)
        ax.set_ylabel(ylabel)
        ax.set_title(metric.replace("_", " ").title())
        ax.tick_params(axis="x", rotation=25)
        ax.legend()
        fig.tight_layout()
        fig.savefig(OUTPUT_DIR / filename, dpi=180)
        plt.close(fig)


def write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    fields = sorted({key for row in rows for key in row.keys()})
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def write_report(results: dict[str, Any]) -> None:
    lines = [
        "# Pipeline Cloud Diagnostics",
        "",
        "Restricciones respetadas: no se modifico PDI, NodeODM, OpenSfM ni parametros productivos. El diagnostico replica la preparacion productiva solo para medir.",
        "",
        "## Decision diagnostica",
        "",
    ]
    for name, dataset in results["datasets"].items():
        fd = dataset["first_divergence"]
        comp = dataset["cloud_comparison"]
        prod = comp["productive_stats"]
        bench = comp["benchmark_stats"]
        lines.extend(
            [
                f"### {name}",
                "",
                f"- Primer punto de divergencia: `{fd['stage']}`.",
                f"- Cuello de botella: {fd['bottleneck']}",
                f"- Puntos productivos PDI: {prod['point_count']} vs benchmark: {bench['point_count']} (ratio {comp['point_count_ratio_productive_to_benchmark']}).",
                f"- BBox productivo: {prod['bbox_extent']} m vs benchmark: {bench['bbox_extent']} m.",
                f"- Densidad productiva: {prod['density_points_per_m3']} pts/m3 vs benchmark: {bench['density_points_per_m3']} pts/m3.",
                f"- Chamfer: {comp['distance_metrics']['chamfer_distance_m']} m; Hausdorff: {comp['distance_metrics']['hausdorff_distance_m']} m.",
                f"- Solapamiento productivo->benchmark @0.25m: {comp['distance_metrics']['productive_overlap_ratio_at_0_25m']}.",
                f"- ICP fitness: {comp['icp_metrics'].get('fitness')}; ICP RMSE: {comp['icp_metrics'].get('inlier_rmse_m')} m.",
                "",
            ]
        )
        cleanup = dataset["productive_pipeline"]["cleanup_steps"]
        segmentation = dataset["productive_pipeline"]["segmentation_quality"]
        opensfm = dataset["opensfm_nodeodm"]
        lines.extend(
            [
                "OpenSfM / NodeODM:",
                "",
                f"- task UUID: {opensfm.get('nodeodm_task_uuid')}",
                f"- camaras reconstruidas: {opensfm.get('reconstructed_shots_from_reconstruction_json') or opensfm.get('reconstruction_statistics', {}).get('reconstructed_shots_count')}",
                f"- landmarks reconstruidos: {opensfm.get('landmarks_from_reconstruction_json') or opensfm.get('reconstruction_statistics', {}).get('reconstructed_points_count')}",
                f"- tracks/observaciones: {opensfm.get('reconstruction_statistics', {}).get('observations_count')}",
                f"- reprojection error px: {opensfm.get('reprojection_error_pixels')}",
                "",
                "Filtros productivos medidos:",
                "",
                *[
                    f"- {step['filter']}: {step['before']} -> {step['after']} puntos; eliminado {step['removed_ratio'] * 100:.2f}%."
                    for step in cleanup
                ],
                f"- segmentacion DBSCAN: selecciono {segmentation.get('selected_point_count')} puntos; labels {segmentation.get('selected_labels')}; razon {segmentation.get('selection_reason')}.",
                "",
            ]
        )
    lines.extend(
        [
            "## Artefactos",
            "",
            "- `pipeline_diagnostics.json`",
            "- `pipeline_metrics.csv`",
            "- `cloud_comparison.json`",
            "- `cloud_statistics.json`",
            "- `*_cloud_overlay.png`",
            "- `*_xyz_histograms.png`",
            "- `point_count_evolution.png`",
            "- `bbox_volume_evolution.png`",
        ]
    )
    (OUTPUT_DIR / "pipeline_report.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    started = time.perf_counter()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    metric_rows: list[dict[str, Any]] = []
    results: dict[str, Any] = {
        "run_id": "RUN-PIPELINE-CLOUD-DIAGNOSTICS-01",
        "created_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "root": str(ROOT),
        "ground_truth_volume_m3": GT_VOLUME_M3,
        "nodeodm_opensfm_metrics": load_nodeodm_metrics(),
        "datasets": {},
    }
    cloud_comparison: dict[str, Any] = {}
    cloud_statistics: dict[str, Any] = {}

    for cfg in DATASETS:
        productive = instrument_productive_pipeline(cfg, metric_rows)
        benchmark = benchmark_cloud_metrics(cfg, metric_rows)
        productive_pdi_path = OUTPUT_DIR / f"{cfg.name}_productive_pdi_input.ply"
        comparison = compare_clouds(cfg, productive_pdi_path)
        divergence = first_divergence(productive, benchmark, comparison)
        images = image_metrics(cfg.image_dir)
        nodeodm_opensfm = results["nodeodm_opensfm_metrics"].get(cfg.name) or {
            "opensfm_artifacts_available": False,
            "nodeodm_internal_artifacts_available": False,
            "note": "Persisted backend artifacts include the downloaded NodeODM point_cloud.ply but not OpenSfM reconstruction/tracks/stats files. Camera/landmark/track/reprojection metrics could not be recovered from current persisted artifacts.",
        }
        results["datasets"][cfg.name] = {
            "input": images,
            "opensfm_nodeodm": nodeodm_opensfm,
            "productive_pipeline": productive,
            "benchmark_experimental": benchmark,
            "cloud_comparison": comparison,
            "first_divergence": divergence,
        }
        cloud_comparison[cfg.name] = comparison
        cloud_statistics[cfg.name] = {
            "productive_stages": productive["stages"],
            "benchmark": benchmark["stats"],
        }
        plot_overlay(cfg, productive_pdi_path)
        plot_histograms(cfg, productive_pdi_path)

    plot_evolution(metric_rows)
    results["elapsed_seconds"] = round(time.perf_counter() - started, 3)
    write_csv(metric_rows, OUTPUT_DIR / "pipeline_metrics.csv")
    (OUTPUT_DIR / "pipeline_diagnostics.json").write_text(json.dumps(as_jsonable(results), indent=2), encoding="utf-8")
    (OUTPUT_DIR / "cloud_comparison.json").write_text(json.dumps(as_jsonable(cloud_comparison), indent=2), encoding="utf-8")
    (OUTPUT_DIR / "cloud_statistics.json").write_text(json.dumps(as_jsonable(cloud_statistics), indent=2), encoding="utf-8")
    write_report(results)
    print(json.dumps({"output_dir": str(OUTPUT_DIR), "elapsed_seconds": results["elapsed_seconds"]}, indent=2))


if __name__ == "__main__":
    main()
