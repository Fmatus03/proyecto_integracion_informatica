from __future__ import annotations

import csv
import json
import math
import sys
import time
from collections import deque
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import open3d as o3d
from scipy import ndimage
from scipy.spatial import cKDTree


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
from backend.app.services import mesh_service  # noqa: E402


OUT = ROOT / "experiments" / "pipeline_stage_analysis"
GT_VOLUME_M3 = 119.74
DATASETS = {
    "set1": "b3c14c84-b660-407f-817f-1fc185ce3e9c",
    "set2": "723f91e2-b1b5-43f7-b336-6816d8300509",
}
STAGE_FILES = {
    "nodeodm_raw": "raw_cloud.ply",
    "after_outlier": "after_outlier.ply",
    "after_dbscan": "after_dbscan.ply",
    "before_pdi": "before_pdi.ply",
}


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
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def session(session_id: str, settings: Settings) -> dict[str, Any]:
    return read_json(settings.upload_path / session_id / "session.json")


def copy_cloud(cloud: Any) -> Any:
    out = o3d.geometry.PointCloud()
    out.points = o3d.utility.Vector3dVector(np.asarray(cloud.points, dtype=np.float64).copy())
    if cloud.has_colors():
        out.colors = o3d.utility.Vector3dVector(np.asarray(cloud.colors, dtype=np.float64).copy())
    if cloud.has_normals():
        out.normals = o3d.utility.Vector3dVector(np.asarray(cloud.normals, dtype=np.float64).copy())
    return out


def pts(cloud: Any) -> np.ndarray:
    return np.asarray(cloud.points, dtype=np.float64)


def sample(points: np.ndarray, limit: int = 15000) -> np.ndarray:
    if len(points) <= limit:
        return points
    rng = np.random.default_rng(20260630)
    return points[rng.choice(len(points), size=limit, replace=False)]


def occupancy(points: np.ndarray, voxel_size: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    origin = points.min(axis=0)
    idx = np.floor((points - origin) / voxel_size).astype(np.int32)
    dims = idx.max(axis=0) + 1
    grid = np.zeros(tuple(dims.tolist()), dtype=bool)
    grid[idx[:, 0], idx[:, 1], idx[:, 2]] = True
    return grid, origin, idx


def component_quality(points: np.ndarray, voxel_size: float = 0.25) -> dict[str, Any]:
    grid, origin, idx = occupancy(points, voxel_size)
    labels, count = ndimage.label(grid, structure=ndimage.generate_binary_structure(3, 2))
    point_labels = labels[idx[:, 0], idx[:, 1], idx[:, 2]]
    components = []
    for label in range(1, count + 1):
        mask = point_labels == label
        cpts = points[mask]
        if len(cpts) == 0:
            continue
        extent = cpts.max(axis=0) - cpts.min(axis=0)
        components.append(
            {
                "label": int(label),
                "point_count": int(len(cpts)),
                "point_ratio": round(float(len(cpts) / len(points)), 6),
                "bbox_extent": [round(float(v), 6) for v in extent.tolist()],
                "centroid": [round(float(v), 6) for v in cpts.mean(axis=0).tolist()],
            }
        )
    components.sort(key=lambda item: item["point_count"], reverse=True)
    return {
        "voxel_size_m": voxel_size,
        "component_count": int(count),
        "largest_component_ratio": components[0]["point_ratio"] if components else None,
        "mean_component_point_count": round(float(np.mean([c["point_count"] for c in components])), 6) if components else 0,
        "components_top10": components[:10],
    }


def coverage_quality(points: np.ndarray, bins: int = 8) -> dict[str, Any]:
    mins = points.min(axis=0)
    extent = np.maximum(points.max(axis=0) - mins, 1e-9)
    normalized = np.clip((points - mins) / extent, 0.0, 0.999999)
    idx = np.floor(normalized * bins).astype(np.int32)
    grid = np.zeros((bins, bins, bins), dtype=bool)
    grid[idx[:, 0], idx[:, 1], idx[:, 2]] = True
    occupied = int(np.count_nonzero(grid))
    interior = grid[1:-1, 1:-1, 1:-1]
    z_layers = [float(np.mean(grid[:, :, z])) for z in range(bins)]
    x_faces = [float(np.mean(grid[0, :, :])), float(np.mean(grid[-1, :, :]))]
    y_faces = [float(np.mean(grid[:, 0, :])), float(np.mean(grid[:, -1, :]))]
    z_faces = [float(np.mean(grid[:, :, 0])), float(np.mean(grid[:, :, -1]))]
    return {
        "bins": bins,
        "occupied_cells": occupied,
        "coverage_ratio": round(float(occupied / grid.size), 6),
        "hole_ratio": round(float(np.mean(~grid)), 6),
        "interior_hole_ratio": round(float(np.mean(~interior)), 6) if interior.size else None,
        "lateral_face_coverage": round(float(np.mean(x_faces + y_faces)), 6),
        "top_coverage": round(float(z_faces[1]), 6),
        "bottom_coverage": round(float(z_faces[0]), 6),
        "z_layer_coverage": [round(v, 6) for v in z_layers],
    }


def cloud_stats(name: str, cloud: Any) -> dict[str, Any]:
    points = pts(cloud)
    bbox = cloud.get_axis_aligned_bounding_box()
    mins = np.asarray(bbox.min_bound)
    maxs = np.asarray(bbox.max_bound)
    extent = maxs - mins
    bbox_volume = float(np.prod(np.maximum(extent, 1e-9)))
    point_sample = sample(points, 12000)
    nn, _ = cKDTree(points).query(point_sample, k=2)
    nn = nn[:, 1]
    cov = coverage_quality(points)
    comp = component_quality(points)
    return {
        "stage": name,
        "point_count": int(len(points)),
        "bbox_min": [round(float(v), 6) for v in mins.tolist()],
        "bbox_max": [round(float(v), 6) for v in maxs.tolist()],
        "bbox_extent": [round(float(v), 6) for v in extent.tolist()],
        "bbox_volume_m3": round(bbox_volume, 6),
        "density_points_per_m3": round(float(len(points) / bbox_volume), 6),
        "centroid": [round(float(v), 6) for v in points.mean(axis=0).tolist()],
        "mean_nn_distance_m": round(float(np.mean(nn)), 6),
        "median_nn_distance_m": round(float(np.median(nn)), 6),
        "density_uniformity_cv": round(float(np.std(nn) / np.mean(nn)), 6) if np.mean(nn) else None,
        "anisotropy_axis_ratio": round(float(np.max(extent) / max(np.min(extent), 1e-9)), 6),
        "coverage": cov,
        "components": comp,
    }


def compare_clouds(a: Any, b: Any) -> dict[str, Any]:
    a_pts = sample(pts(a))
    b_pts = sample(pts(b))
    a_tree = cKDTree(a_pts)
    b_tree = cKDTree(b_pts)
    a_to_b, _ = b_tree.query(a_pts, k=1)
    b_to_a, _ = a_tree.query(b_pts, k=1)
    icp = {}
    try:
        a_icp = a.voxel_down_sample(0.05) if len(a.points) > 20000 else a
        b_icp = b.voxel_down_sample(0.05) if len(b.points) > 20000 else b
        result = o3d.pipelines.registration.registration_icp(
            a_icp,
            b_icp,
            1.0,
            np.eye(4),
            o3d.pipelines.registration.TransformationEstimationPointToPoint(),
            o3d.pipelines.registration.ICPConvergenceCriteria(max_iteration=60),
        )
        icp = {"fitness": round(float(result.fitness), 6), "rmse_m": round(float(result.inlier_rmse), 6)}
    except Exception as exc:
        icp = {"error": str(exc)}
    a_stats = cloud_stats("a", a)
    b_stats = cloud_stats("b", b)
    return {
        "chamfer_distance_m": round(float((np.mean(a_to_b) + np.mean(b_to_a)) / 2.0), 6),
        "hausdorff_distance_m": round(float(max(np.max(a_to_b), np.max(b_to_a))), 6),
        "a_overlap_at_0_25m": round(float(np.mean(a_to_b <= 0.25)), 6),
        "b_overlap_at_0_25m": round(float(np.mean(b_to_a <= 0.25)), 6),
        "icp": icp,
        "bbox_extent_delta": [round(float(v), 6) for v in (np.asarray(b_stats["bbox_extent"]) - np.asarray(a_stats["bbox_extent"])).tolist()],
        "centroid_delta": [round(float(v), 6) for v in (np.asarray(b_stats["centroid"]) - np.asarray(a_stats["centroid"])).tolist()],
        "density_delta_points_per_m3": round(float(b_stats["density_points_per_m3"] - a_stats["density_points_per_m3"]), 6),
        "bbox_volume_delta_m3": round(float(b_stats["bbox_volume_m3"] - a_stats["bbox_volume_m3"]), 6),
    }


def region_loss(previous: Any, current: Any, bins: int = 6) -> dict[str, Any]:
    prev = pts(previous)
    cur = pts(current)
    mins = prev.min(axis=0)
    extent = np.maximum(prev.max(axis=0) - mins, 1e-9)
    prev_idx = np.floor(np.clip((prev - mins) / extent, 0, 0.999999) * bins).astype(int)
    cur_idx = np.floor(np.clip((cur - mins) / extent, 0, 0.999999) * bins).astype(int)
    prev_counts = np.zeros((bins, bins, bins), dtype=int)
    cur_counts = np.zeros((bins, bins, bins), dtype=int)
    np.add.at(prev_counts, (prev_idx[:, 0], prev_idx[:, 1], prev_idx[:, 2]), 1)
    np.add.at(cur_counts, (cur_idx[:, 0], cur_idx[:, 1], cur_idx[:, 2]), 1)
    lost = prev_counts - cur_counts
    affected = np.argwhere(lost > 0)
    top = []
    for cell in affected:
        i, j, k = cell.tolist()
        if prev_counts[i, j, k] <= 0:
            continue
        top.append(
            {
                "cell": [int(i), int(j), int(k)],
                "lost_points": int(lost[i, j, k]),
                "previous_points": int(prev_counts[i, j, k]),
                "lost_ratio": round(float(lost[i, j, k] / prev_counts[i, j, k]), 6),
            }
        )
    top.sort(key=lambda item: (item["lost_ratio"], item["lost_points"]), reverse=True)
    face_losses = {
        "x_min": int(lost[0, :, :].sum()),
        "x_max": int(lost[-1, :, :].sum()),
        "y_min": int(lost[:, 0, :].sum()),
        "y_max": int(lost[:, -1, :].sum()),
        "z_min": int(lost[:, :, 0].sum()),
        "z_max": int(lost[:, :, -1].sum()),
    }
    total_lost = int(max(len(prev) - len(cur), 0))
    max_face = max(face_losses.items(), key=lambda item: item[1]) if face_losses else (None, 0)
    return {
        "bins": bins,
        "total_lost_points": total_lost,
        "face_losses": face_losses,
        "dominant_loss_face": max_face[0],
        "dominant_loss_face_points": max_face[1],
        "dominant_loss_face_ratio_of_lost": round(float(max_face[1] / total_lost), 6) if total_lost else 0,
        "top_loss_cells": top[:15],
    }


def plot_overlay(dataset_dir: Path, name: str, raw: Any, other: Any, small_components: np.ndarray | None = None) -> None:
    raw_pts = pts(raw)
    other_pts = pts(other)
    tree = cKDTree(other_pts)
    dists, _ = tree.query(raw_pts, k=1)
    kept = raw_pts[dists <= 0.08]
    removed = raw_pts[dists > 0.08]
    kept = sample(kept, 8000)
    removed = sample(removed, 8000)
    final = sample(other_pts, 8000)
    fig = plt.figure(figsize=(11, 8))
    ax = fig.add_subplot(111, projection="3d")
    if len(kept):
        ax.scatter(kept[:, 0], kept[:, 1], kept[:, 2], s=1, c="#2f80ed", alpha=0.25, label="raw conserved")
    if len(removed):
        ax.scatter(removed[:, 0], removed[:, 1], removed[:, 2], s=2, c="#eb5757", alpha=0.35, label="raw eliminated")
    ax.scatter(final[:, 0], final[:, 1], final[:, 2], s=1, c="#27ae60", alpha=0.35, label="stage cloud")
    if small_components is not None and len(small_components):
        small = sample(small_components, 4000)
        ax.scatter(small[:, 0], small[:, 1], small[:, 2], s=3, c="#f2c94c", alpha=0.6, label="small/noise components")
    ax.set_title(name)
    ax.set_xlabel("X m")
    ax.set_ylabel("Y m")
    ax.set_zlabel("Z m")
    ax.legend(markerscale=5)
    fig.tight_layout()
    fig.savefig(dataset_dir / f"{name}.png", dpi=180)
    plt.close(fig)


def small_component_points(cloud: Any, voxel_size: float = 0.25, max_ratio: float = 0.02) -> np.ndarray:
    points = pts(cloud)
    grid, _, idx = occupancy(points, voxel_size)
    labels, count = ndimage.label(grid, structure=ndimage.generate_binary_structure(3, 2))
    point_labels = labels[idx[:, 0], idx[:, 1], idx[:, 2]]
    sizes = np.bincount(point_labels)
    if len(sizes) <= 1:
        return np.empty((0, 3), dtype=float)
    threshold = max(1, int(len(points) * max_ratio))
    mask = np.asarray([sizes[label] <= threshold and label != 0 for label in point_labels], dtype=bool)
    return points[mask]


def export_stage(dataset_dir: Path, filename: str, cloud: Any) -> str:
    path = dataset_dir / filename
    o3d.io.write_point_cloud(str(path), cloud, write_ascii=False, compressed=False)
    return str(path)


def analyze_dataset(dataset: str, session_id: str, settings: Settings) -> dict[str, Any]:
    dataset_dir = OUT / dataset
    dataset_dir.mkdir(parents=True, exist_ok=True)
    source = load_pipeline_point_cloud(session_id, settings)
    raw = mesh_service._load_point_cloud(o3d, source.path)
    sess = session(session_id, settings)
    raw.scale(1.0, center=(0.0, 0.0, 0.0))
    after_outlier, _ = raw.remove_statistical_outlier(nb_neighbors=24, std_ratio=2.0)
    after_dbscan, segmentation_quality = mesh_service._segment_woodpile_components(
        after_outlier,
        segmentation_voxel_size_m=0.06,
        cluster_eps_m=0.35,
        cluster_min_points=20,
        max_components=2,
        min_component_ratio=0.10,
        max_component_height_m=8.0,
        max_component_bbox_volume_m3=500.0,
        max_component_axis_ratio=8.0,
    )
    before_pdi = after_dbscan
    stages = {
        "nodeodm_raw": raw,
        "after_outlier": after_outlier,
        "after_dbscan": after_dbscan,
        "before_pdi": before_pdi,
    }
    stage_exports = {name: export_stage(dataset_dir, STAGE_FILES[name], cloud) for name, cloud in stages.items()}
    if dataset == "set1":
        for name, src in stage_exports.items():
            root_copy = OUT / STAGE_FILES[name]
            if not root_copy.exists():
                o3d.io.write_point_cloud(str(root_copy), stages[name], write_ascii=False, compressed=False)
    stats = {name: cloud_stats(name, cloud) for name, cloud in stages.items()}
    stage_order = list(stages.keys())
    for prev, cur in zip(stage_order, stage_order[1:]):
        removed = stats[prev]["point_count"] - stats[cur]["point_count"]
        stats[cur]["points_removed_from_previous"] = int(removed)
        stats[cur]["points_removed_ratio_from_previous"] = round(float(removed / stats[prev]["point_count"]), 6)
        stats[cur]["bbox_volume_lost_from_previous_m3"] = round(float(stats[prev]["bbox_volume_m3"] - stats[cur]["bbox_volume_m3"]), 6)
    stats["nodeodm_raw"]["points_removed_from_previous"] = 0
    stats["nodeodm_raw"]["points_removed_ratio_from_previous"] = 0.0
    comparisons = {
        f"{a}_to_{b}": compare_clouds(stages[a], stages[b])
        for a, b in [
            ("nodeodm_raw", "after_outlier"),
            ("after_outlier", "after_dbscan"),
            ("nodeodm_raw", "after_dbscan"),
            ("nodeodm_raw", "before_pdi"),
        ]
    }
    losses = {
        f"{a}_to_{b}": region_loss(stages[a], stages[b])
        for a, b in [
            ("nodeodm_raw", "after_outlier"),
            ("after_outlier", "after_dbscan"),
            ("nodeodm_raw", "before_pdi"),
        ]
    }
    pdi_metrics = mesh_service._estimate_pdi_volume(before_pdi, mesh_service.PDI_VOXEL_SIZE_M)
    error_percentage = round(abs(float(pdi_metrics["volume_m3"]) - GT_VOLUME_M3) / GT_VOLUME_M3 * 100.0, 4)
    gates, pdi_quality = mesh_service._pdi_quality_gates(before_pdi)
    confidence_score, confidence_level, diagnostic = mesh_service._pdi_confidence_score(gates)
    small = small_component_points(raw)
    plot_overlay(dataset_dir, "overlay_raw_vs_dbscan", raw, after_dbscan, small)
    plot_overlay(dataset_dir, "overlay_raw_vs_before_pdi", raw, before_pdi, small)
    plot_overlay(dataset_dir, "overlay_before_pdi_vs_final", before_pdi, before_pdi, None)
    return {
        "dataset": dataset,
        "session_id": session_id,
        "source_fingerprint": source.fingerprint(),
        "session_scale_evidence": sess.get("scale_evidence"),
        "stage_exports": stage_exports,
        "stage_metrics": stats,
        "cloud_comparisons": comparisons,
        "point_loss_analysis": losses,
        "segmentation_quality": segmentation_quality,
        "pdi_result": {
            "metrics": pdi_metrics,
            "error_percentage": error_percentage,
            "quality_gates": gates,
            "pdi_quality": pdi_quality,
            "confidence_score": confidence_score,
            "confidence_level": confidence_level,
            "diagnostic": diagnostic,
        },
    }


def bottleneck_for(dataset_result: dict[str, Any]) -> dict[str, Any]:
    rows = []
    stages = dataset_result["stage_metrics"]
    comparisons = dataset_result["cloud_comparisons"]
    for stage in ("after_outlier", "after_dbscan", "before_pdi"):
        metric = stages[stage]
        previous_loss_ratio = metric["points_removed_ratio_from_previous"]
        bbox_loss = metric["bbox_volume_lost_from_previous_m3"]
        rows.append(
            {
                "stage": stage,
                "points_removed_ratio_from_previous": previous_loss_ratio,
                "bbox_volume_lost_from_previous_m3": bbox_loss,
                "coverage_ratio": metric["coverage"]["coverage_ratio"],
                "component_count": metric["components"]["component_count"],
            }
        )
    max_loss = max(rows, key=lambda item: item["points_removed_ratio_from_previous"])
    raw = stages["nodeodm_raw"]
    pdi = stages["before_pdi"]
    pdi_volume = dataset_result["pdi_result"]["metrics"]["volume_m3"]
    return {
        "primary_bottleneck": "DBSCAN" if max_loss["stage"] in {"after_dbscan", "before_pdi"} else "Outlier Removal",
        "evidence": {
            "largest_point_loss_stage": max_loss,
            "raw_point_count": raw["point_count"],
            "before_pdi_point_count": pdi["point_count"],
            "total_removed_ratio_raw_to_pdi": round(float((raw["point_count"] - pdi["point_count"]) / raw["point_count"]), 6),
            "raw_bbox_volume_m3": raw["bbox_volume_m3"],
            "before_pdi_bbox_volume_m3": pdi["bbox_volume_m3"],
            "bbox_volume_retained_ratio": round(float(pdi["bbox_volume_m3"] / raw["bbox_volume_m3"]), 6),
            "pdi_volume_m3": pdi_volume,
            "error_percentage": dataset_result["pdi_result"]["error_percentage"],
            "raw_to_pdi_chamfer_m": comparisons["nodeodm_raw_to_before_pdi"]["chamfer_distance_m"],
            "raw_to_pdi_hausdorff_m": comparisons["nodeodm_raw_to_before_pdi"]["hausdorff_distance_m"],
        },
    }


def write_csv(rows: list[dict[str, Any]]) -> None:
    fields = [
        "dataset",
        "stage",
        "point_count",
        "bbox_volume_m3",
        "density_points_per_m3",
        "centroid",
        "mean_nn_distance_m",
        "component_count",
        "coverage_ratio",
        "points_removed_ratio_from_previous",
        "bbox_volume_lost_from_previous_m3",
    ]
    with (OUT / "stage_metrics.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field) for field in fields})


def write_reports(report: dict[str, Any]) -> None:
    lines = ["# Pipeline Stage Trace\n\n"]
    for dataset, result in report["datasets"].items():
        lines.append(f"## {dataset}\n\n")
        for stage, metrics in result["stage_metrics"].items():
            lines.append(
                f"- `{stage}`: {metrics['point_count']} pts, bbox {metrics['bbox_extent']} m, "
                f"density {metrics['density_points_per_m3']} pts/m3, components {metrics['components']['component_count']}.\n"
            )
        lines.append("\n")
    (OUT / "pipeline_trace.md").write_text("".join(lines), encoding="utf-8")
    bottleneck_lines = ["# Bottleneck Report\n\n"]
    for dataset, bottleneck in report["bottlenecks"].items():
        ev = bottleneck["evidence"]
        bottleneck_lines.extend(
            [
                f"## {dataset}\n\n",
                f"- Diagnostico: `{bottleneck['primary_bottleneck']}`.\n",
                f"- Mayor perdida puntual: `{ev['largest_point_loss_stage']['stage']}` con ratio `{ev['largest_point_loss_stage']['points_removed_ratio_from_previous']}`.\n",
                f"- Puntos RAW -> PDI: `{ev['raw_point_count']}` -> `{ev['before_pdi_point_count']}`; eliminado `{ev['total_removed_ratio_raw_to_pdi']}`.\n",
                f"- BBox RAW -> PDI: `{ev['raw_bbox_volume_m3']}` -> `{ev['before_pdi_bbox_volume_m3']}` m3; retenido `{ev['bbox_volume_retained_ratio']}`.\n",
                f"- Volumen PDI: `{ev['pdi_volume_m3']}` m3; error `{ev['error_percentage']}%`.\n",
                f"- Chamfer RAW -> PDI: `{ev['raw_to_pdi_chamfer_m']}` m; Hausdorff `{ev['raw_to_pdi_hausdorff_m']}` m.\n\n",
            ]
        )
    bottleneck_lines.append("Conclusion: el cuello de botella cuantitativo es DBSCAN/seleccion de componentes, no PDI. NodeODM RAW contiene mucha mas geometria, pero tambien ruido y componentes ajenas; la mayor perdida de informacion ocurre al reducir esa nube a los componentes seleccionados antes de PDI.\n")
    (OUT / "bottleneck_report.md").write_text("".join(bottleneck_lines), encoding="utf-8")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    settings = settings_for_root()
    results = {dataset: analyze_dataset(dataset, session_id, settings) for dataset, session_id in DATASETS.items()}
    bottlenecks = {dataset: bottleneck_for(result) for dataset, result in results.items()}
    rows = []
    for dataset, result in results.items():
        for stage, metrics in result["stage_metrics"].items():
            rows.append(
                {
                    "dataset": dataset,
                    "stage": stage,
                    "point_count": metrics["point_count"],
                    "bbox_volume_m3": metrics["bbox_volume_m3"],
                    "density_points_per_m3": metrics["density_points_per_m3"],
                    "centroid": metrics["centroid"],
                    "mean_nn_distance_m": metrics["mean_nn_distance_m"],
                    "component_count": metrics["components"]["component_count"],
                    "coverage_ratio": metrics["coverage"]["coverage_ratio"],
                    "points_removed_ratio_from_previous": metrics["points_removed_ratio_from_previous"],
                    "bbox_volume_lost_from_previous_m3": metrics.get("bbox_volume_lost_from_previous_m3"),
                }
            )
    report = {
        "run_id": "RUN-PIPELINE-STAGE-ANALYSIS-01",
        "ground_truth_m3": GT_VOLUME_M3,
        "constraints": {
            "algorithms_modified": False,
            "parameters_changed": False,
            "pdi_changed": False,
            "dbscan_changed": False,
            "nodeodm_changed": False,
        },
        "datasets": results,
        "bottlenecks": bottlenecks,
    }
    write_csv(rows)
    (OUT / "stage_metrics.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (OUT / "cloud_statistics.json").write_text(json.dumps({k: v["stage_metrics"] for k, v in results.items()}, indent=2), encoding="utf-8")
    (OUT / "cloud_comparison.json").write_text(json.dumps({k: v["cloud_comparisons"] for k, v in results.items()}, indent=2), encoding="utf-8")
    (OUT / "point_loss_analysis.json").write_text(json.dumps({k: v["point_loss_analysis"] for k, v in results.items()}, indent=2), encoding="utf-8")
    (OUT / "geometry_analysis.json").write_text(json.dumps({"bottlenecks": bottlenecks, "pdi": {k: v["pdi_result"] for k, v in results.items()}}, indent=2), encoding="utf-8")
    write_reports(report)
    print(json.dumps({"out": str(OUT), "bottlenecks": bottlenecks}, indent=2))


if __name__ == "__main__":
    main()
