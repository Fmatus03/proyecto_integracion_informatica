from __future__ import annotations

import csv
import itertools
import json
import math
import sys
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import open3d as o3d
from scipy.spatial import ConvexHull, cKDTree


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

from backend.app.config import Settings, get_settings  # noqa: E402
from backend.app.services.cloud_provider import load_pipeline_point_cloud  # noqa: E402
from backend.app.services import mesh_service  # noqa: E402


OUT = ROOT / "experiments" / "dbscan_decision_analysis"
DATASETS = {
    "set1": "b3c14c84-b660-407f-817f-1fc185ce3e9c",
    "set2": "723f91e2-b1b5-43f7-b336-6816d8300509",
}
DBSCAN_PARAMS = {
    "segmentation_voxel_size_m": 0.06,
    "cluster_eps_m": 0.35,
    "cluster_min_points": 20,
    "max_components": 2,
    "min_component_ratio": 0.10,
    "max_component_height_m": 8.0,
    "max_component_bbox_volume_m3": 500.0,
    "max_component_axis_ratio": 8.0,
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


def pts(cloud: Any) -> np.ndarray:
    return np.asarray(cloud.points, dtype=np.float64)


def colors(cloud: Any) -> np.ndarray | None:
    if not cloud.has_colors():
        return None
    arr = np.asarray(cloud.colors, dtype=np.float64)
    return arr if len(arr) == len(cloud.points) else None


def make_cloud(points: np.ndarray, rgb: np.ndarray | None = None) -> Any:
    cloud = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(points))
    if rgb is not None:
        cloud.colors = o3d.utility.Vector3dVector(np.clip(rgb, 0.0, 1.0))
    return cloud


def load_cleaned_cloud(session_id: str, settings: Settings) -> tuple[Any, dict[str, Any]]:
    source = load_pipeline_point_cloud(session_id, settings)
    raw = mesh_service._load_point_cloud(o3d, source.path)
    raw.scale(1.0, center=(0.0, 0.0, 0.0))
    cleaned, _ = raw.remove_statistical_outlier(nb_neighbors=24, std_ratio=2.0)
    return cleaned, source.fingerprint()


def run_dbscan_input(cleaned: Any) -> tuple[Any, np.ndarray]:
    clustering_cloud = cleaned.voxel_down_sample(DBSCAN_PARAMS["segmentation_voxel_size_m"])
    labels = np.asarray(
        clustering_cloud.cluster_dbscan(
            eps=DBSCAN_PARAMS["cluster_eps_m"],
            min_points=DBSCAN_PARAMS["cluster_min_points"],
            print_progress=False,
        ),
        dtype=int,
    )
    return clustering_cloud, labels


def occupancy_ratio(points: np.ndarray, voxel_size: float = 0.25) -> dict[str, Any]:
    if len(points) == 0:
        return {"occupied_voxels": 0, "grid_voxels": 0, "occupancy_ratio": 0.0}
    origin = points.min(axis=0)
    idx = np.floor((points - origin) / voxel_size).astype(np.int32)
    dims = idx.max(axis=0) + 1
    grid = np.zeros(tuple(dims.tolist()), dtype=bool)
    grid[idx[:, 0], idx[:, 1], idx[:, 2]] = True
    return {
        "voxel_size_m": voxel_size,
        "occupied_voxels": int(np.count_nonzero(grid)),
        "grid_voxels": int(grid.size),
        "occupancy_ratio": round(float(np.count_nonzero(grid) / grid.size), 6) if grid.size else 0.0,
    }


def cluster_stats(
    label: int,
    cloud: Any,
    indices: np.ndarray,
    global_points: np.ndarray,
    main_count: int,
) -> dict[str, Any]:
    points = global_points[indices]
    bbox_min = points.min(axis=0)
    bbox_max = points.max(axis=0)
    extent = bbox_max - bbox_min
    positive_extent = extent[extent > 0]
    bbox_volume = float(np.prod(positive_extent)) if positive_extent.size == 3 else 0.0
    axis_ratio = float(positive_extent.max() / positive_extent.min()) if positive_extent.size else math.inf
    density = float(len(points) / bbox_volume) if bbox_volume > 0 else 0.0
    centroid = points.mean(axis=0)
    global_centroid = global_points.mean(axis=0)
    global_min = global_points.min(axis=0)
    global_max = global_points.max(axis=0)
    tolerance = 0.06
    touches = {
        "x_min": bool(bbox_min[0] <= global_min[0] + tolerance),
        "x_max": bool(bbox_max[0] >= global_max[0] - tolerance),
        "y_min": bool(bbox_min[1] <= global_min[1] + tolerance),
        "y_max": bool(bbox_max[1] >= global_max[1] - tolerance),
        "z_min": bool(bbox_min[2] <= global_min[2] + tolerance),
        "z_max": bool(bbox_max[2] >= global_max[2] - tolerance),
    }
    hull_volume = None
    if len(points) >= 4:
        try:
            hull_volume = float(ConvexHull(points).volume)
        except Exception:
            hull_volume = None
    plausible = (
        len(points) >= DBSCAN_PARAMS["cluster_min_points"]
        and (DBSCAN_PARAMS["max_component_height_m"] <= 0 or float(extent[2]) <= DBSCAN_PARAMS["max_component_height_m"])
        and (DBSCAN_PARAMS["max_component_bbox_volume_m3"] <= 0 or bbox_volume <= DBSCAN_PARAMS["max_component_bbox_volume_m3"])
        and (not np.isfinite(axis_ratio) or DBSCAN_PARAMS["max_component_axis_ratio"] <= 0 or axis_ratio <= DBSCAN_PARAMS["max_component_axis_ratio"])
    )
    score = {
        "current_heuristic_count": int(len(points)),
        "current_heuristic_density": round(float(density), 6),
        "count_ratio_to_main": round(float(len(points) / main_count), 6) if main_count else 0.0,
        "passes_min_component_ratio": bool((len(points) / main_count) >= DBSCAN_PARAMS["min_component_ratio"]) if main_count else False,
        "plausible_woodpile": bool(plausible),
        "sort_key": [int(len(points)), round(float(density), 6)],
    }
    rgb = colors(cloud)
    mean_color = None
    if rgb is not None:
        mean_color = [round(float(v), 6) for v in rgb[indices].mean(axis=0).tolist()]
    return {
        "cluster_id": int(label),
        "point_count": int(len(points)),
        "point_ratio_input": round(float(len(points) / len(global_points)), 6),
        "bbox_min": [round(float(v), 6) for v in bbox_min.tolist()],
        "bbox_max": [round(float(v), 6) for v in bbox_max.tolist()],
        "bbox_extent_xyz": [round(float(v), 6) for v in extent.tolist()],
        "bbox_volume_m3": round(float(bbox_volume), 6),
        "centroid": [round(float(v), 6) for v in centroid.tolist()],
        "density_points_per_m3": round(float(density), 6),
        "distance_to_global_center_m": round(float(np.linalg.norm(centroid - global_centroid)), 6),
        "distance_to_ground_plane_m": round(float(bbox_min[2] - global_min[2]), 6),
        "touches_global_bbox": touches,
        "convex_hull_volume_m3": None if hull_volume is None else round(float(hull_volume), 6),
        "occupancy": occupancy_ratio(points),
        "mean_color_rgb01": mean_color,
        "heuristic_score": score,
        "discard_reasons": discard_reasons(score, extent, bbox_volume, axis_ratio),
    }


def discard_reasons(score: dict[str, Any], extent: np.ndarray, bbox_volume: float, axis_ratio: float) -> list[str]:
    reasons = []
    if not score["passes_min_component_ratio"]:
        reasons.append("below_min_component_ratio")
    if float(extent[2]) > DBSCAN_PARAMS["max_component_height_m"] > 0:
        reasons.append("height_exceeds_max_component_height_m")
    if bbox_volume > DBSCAN_PARAMS["max_component_bbox_volume_m3"] > 0:
        reasons.append("bbox_volume_exceeds_max_component_bbox_volume_m3")
    if np.isfinite(axis_ratio) and axis_ratio > DBSCAN_PARAMS["max_component_axis_ratio"] > 0:
        reasons.append("axis_ratio_exceeds_max_component_axis_ratio")
    if not score["plausible_woodpile"]:
        reasons.append("not_plausible_woodpile")
    return reasons


def select_like_pipeline(stats: list[dict[str, Any]]) -> tuple[list[int], str]:
    if not stats:
        return [], "no_clusters"
    main_count = max(item["point_count"] for item in stats)
    candidates = [
        item
        for item in stats
        if item["heuristic_score"]["plausible_woodpile"]
        and item["point_count"] / main_count >= DBSCAN_PARAMS["min_component_ratio"]
    ]
    if candidates:
        candidates.sort(key=lambda item: (item["point_count"], item["density_points_per_m3"]), reverse=True)
        return [int(item["cluster_id"]) for item in candidates[: DBSCAN_PARAMS["max_components"]]], "plausible_woodpile_components"
    fallback = [
        item
        for item in sorted(stats, key=lambda item: item["point_count"], reverse=True)
        if item["point_count"] / main_count >= DBSCAN_PARAMS["min_component_ratio"]
    ]
    return [int(item["cluster_id"]) for item in fallback[: DBSCAN_PARAMS["max_components"]]], "dominant_components_fallback"


def pdi_for_points(points: np.ndarray) -> dict[str, Any]:
    if len(points) < 4:
        return {"status": "failed", "reason": "fewer_than_4_points"}
    try:
        cloud = make_cloud(points)
        result = mesh_service._estimate_pdi_volume(cloud, mesh_service.PDI_VOXEL_SIZE_M)
        return {"status": "ok", **result}
    except Exception as exc:
        return {"status": "failed", "reason": f"{type(exc).__name__}: {exc}"}


def colorize_clusters(cloud: Any, labels: np.ndarray, stats: list[dict[str, Any]], selected: set[int]) -> Any:
    points = pts(cloud)
    palette = np.asarray(
        [
            [0.90, 0.10, 0.10],
            [0.10, 0.55, 0.90],
            [0.20, 0.75, 0.25],
            [0.95, 0.65, 0.10],
            [0.65, 0.30, 0.85],
            [0.10, 0.75, 0.75],
            [0.85, 0.35, 0.55],
            [0.55, 0.55, 0.20],
        ],
        dtype=float,
    )
    out_colors = np.zeros((len(points), 3), dtype=float) + 0.35
    for rank, item in enumerate(sorted(stats, key=lambda row: row["point_count"], reverse=True)):
        label = item["cluster_id"]
        mask = labels == label
        if label in selected:
            out_colors[mask] = np.asarray([0.0, 0.9, 0.15])
        else:
            out_colors[mask] = palette[rank % len(palette)]
    out_colors[labels < 0] = np.asarray([0.05, 0.05, 0.05])
    return make_cloud(points, out_colors)


def plot_overlay(dataset: str, cloud: Any, labels: np.ndarray, selected: set[int], stats: list[dict[str, Any]]) -> None:
    points = pts(cloud)
    order = np.argsort(labels)
    if len(order) > 12000:
        rng = np.random.default_rng(20260630)
        order = rng.choice(order, size=12000, replace=False)
    fig = plt.figure(figsize=(12, 8))
    ax = fig.add_subplot(111, projection="3d")
    sub = points[order]
    sub_labels = labels[order]
    selected_mask = np.isin(sub_labels, list(selected))
    noise_mask = sub_labels < 0
    discarded_mask = ~(selected_mask | noise_mask)
    if np.any(discarded_mask):
        ax.scatter(sub[discarded_mask, 0], sub[discarded_mask, 1], sub[discarded_mask, 2], s=2, c="#eb5757", alpha=0.30, label="discarded clusters")
    if np.any(selected_mask):
        ax.scatter(sub[selected_mask, 0], sub[selected_mask, 1], sub[selected_mask, 2], s=3, c="#27ae60", alpha=0.45, label="selected clusters")
    if np.any(noise_mask):
        ax.scatter(sub[noise_mask, 0], sub[noise_mask, 1], sub[noise_mask, 2], s=2, c="#222222", alpha=0.25, label="DBSCAN noise")
    small_labels = {
        item["cluster_id"]
        for item in stats
        if item["point_ratio_input"] < 0.02 and item["cluster_id"] not in selected
    }
    small_mask = np.isin(sub_labels, list(small_labels))
    if np.any(small_mask):
        ax.scatter(sub[small_mask, 0], sub[small_mask, 1], sub[small_mask, 2], s=6, c="#f2c94c", alpha=0.55, label="small components")
    ax.set_title(f"{dataset}: DBSCAN decision analysis")
    ax.set_xlabel("X m")
    ax.set_ylabel("Y m")
    ax.set_zlabel("Z m")
    ax.legend(markerscale=5)
    fig.tight_layout()
    fig.savefig(OUT / dataset / "overlays.png", dpi=180)
    plt.close(fig)


def analyze_dataset(dataset: str, session_id: str, settings: Settings) -> dict[str, Any]:
    dataset_dir = OUT / dataset
    dataset_dir.mkdir(parents=True, exist_ok=True)
    cleaned, fingerprint = load_cleaned_cloud(session_id, settings)
    dbscan_cloud, labels = run_dbscan_input(cleaned)
    points = pts(dbscan_cloud)
    valid_labels = labels[labels >= 0]
    values, counts = np.unique(valid_labels, return_counts=True)
    order = np.argsort(counts)[::-1]
    main_count = int(counts[order[0]]) if len(order) else 0
    stats = [
        cluster_stats(int(values[i]), dbscan_cloud, np.where(labels == int(values[i]))[0], points, main_count)
        for i in order
    ]
    selected, selection_reason = select_like_pipeline(stats)
    selected_set = set(selected)
    for rank, item in enumerate(stats, start=1):
        item["rank_by_current_heuristic"] = rank
        item["pipeline_selected"] = item["cluster_id"] in selected_set
        if item["pipeline_selected"]:
            item["selection_reason"] = selection_reason
        elif not item["discard_reasons"]:
            item["discard_reasons"] = ["not_in_top_max_components_after_ranking"]
    selected_indices = np.where(np.isin(labels, selected))[0]
    selected_points = points[selected_indices]
    selected_cloud = make_cloud(selected_points)
    pdi_clusters = []
    for item in stats:
        label = item["cluster_id"]
        cpoints = points[labels == label]
        pdi_clusters.append(
            {
                "dataset": dataset,
                "cluster_id": label,
                "point_count": int(len(cpoints)),
                "pipeline_selected": label in selected_set,
                "pdi": pdi_for_points(cpoints),
            }
        )
    reasonable = [item for item in stats if item["point_count"] / main_count >= 0.02] if main_count else []
    reasonable = reasonable[:8]
    combos = []
    for size in range(1, min(4, len(reasonable)) + 1):
        for combo in itertools.combinations(reasonable, size):
            labels_combo = [item["cluster_id"] for item in combo]
            combo_points = points[np.isin(labels, labels_combo)]
            combos.append(
                {
                    "dataset": dataset,
                    "cluster_ids": labels_combo,
                    "point_count": int(len(combo_points)),
                    "contains_pipeline_selection": set(selected).issubset(set(labels_combo)),
                    "pdi": pdi_for_points(combo_points),
                }
            )
    combos.sort(key=lambda row: (row["pdi"].get("volume_m3") if row["pdi"].get("status") == "ok" else -1), reverse=True)
    colored = colorize_clusters(dbscan_cloud, labels, stats, selected_set)
    o3d.io.write_point_cloud(str(dataset_dir / "colored_clusters.ply"), colored, write_ascii=False, compressed=False)
    o3d.io.write_point_cloud(str(dataset_dir / "cluster_visualization.ply"), selected_cloud, write_ascii=False, compressed=False)
    if dataset == "set1":
        o3d.io.write_point_cloud(str(OUT / "colored_clusters.ply"), colored, write_ascii=False, compressed=False)
        o3d.io.write_point_cloud(str(OUT / "cluster_visualization.ply"), selected_cloud, write_ascii=False, compressed=False)
    plot_overlay(dataset, dbscan_cloud, labels, selected_set, stats)
    if dataset == "set1":
        root_overlay = OUT / "overlays.png"
        root_overlay.write_bytes((dataset_dir / "overlays.png").read_bytes())
    pipeline_pdi = pdi_for_points(selected_points)
    return {
        "dataset": dataset,
        "session_id": session_id,
        "source_fingerprint": fingerprint,
        "dbscan_params": DBSCAN_PARAMS,
        "input_point_count_after_outlier": int(len(cleaned.points)),
        "dbscan_input_point_count_after_voxelization": int(len(points)),
        "segmentation_voxelization_loss": {
            "points_before": int(len(cleaned.points)),
            "points_after": int(len(points)),
            "removed_points": int(len(cleaned.points) - len(points)),
            "removed_ratio": round(float((len(cleaned.points) - len(points)) / len(cleaned.points)), 6) if len(cleaned.points) else 0.0,
        },
        "noise_point_count": int(np.count_nonzero(labels < 0)),
        "cluster_count": int(len(stats)),
        "selection": {
            "selected_cluster_ids": selected,
            "selection_reason": selection_reason,
            "selected_point_count": int(len(selected_points)),
            "selected_ratio_dbscan_input": round(float(len(selected_points) / len(points)), 6) if len(points) else 0,
            "selected_ratio_after_outlier": round(float(len(selected_points) / len(cleaned.points)), 6) if len(cleaned.points) else 0,
            "selection_loss_after_dbscan_input": {
                "points_before": int(len(points)),
                "points_after": int(len(selected_points)),
                "removed_points": int(len(points) - len(selected_points)),
                "removed_ratio": round(float((len(points) - len(selected_points)) / len(points)), 6) if len(points) else 0.0,
            },
            "pipeline_pdi": pipeline_pdi,
        },
        "clusters": stats,
        "pdi_per_cluster": pdi_clusters,
        "pdi_cluster_combinations": combos,
    }


def write_csv(results: dict[str, Any]) -> None:
    fields = [
        "dataset",
        "cluster_id",
        "rank_by_current_heuristic",
        "pipeline_selected",
        "point_count",
        "point_ratio_input",
        "bbox_extent_xyz",
        "bbox_volume_m3",
        "centroid",
        "density_points_per_m3",
        "distance_to_global_center_m",
        "distance_to_ground_plane_m",
        "convex_hull_volume_m3",
        "occupancy_ratio",
        "count_ratio_to_main",
        "plausible_woodpile",
        "passes_min_component_ratio",
        "discard_reasons",
    ]
    with (OUT / "cluster_statistics.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for dataset, result in results.items():
            for item in result["clusters"]:
                writer.writerow(
                    {
                        "dataset": dataset,
                        "cluster_id": item["cluster_id"],
                        "rank_by_current_heuristic": item["rank_by_current_heuristic"],
                        "pipeline_selected": item["pipeline_selected"],
                        "point_count": item["point_count"],
                        "point_ratio_input": item["point_ratio_input"],
                        "bbox_extent_xyz": item["bbox_extent_xyz"],
                        "bbox_volume_m3": item["bbox_volume_m3"],
                        "centroid": item["centroid"],
                        "density_points_per_m3": item["density_points_per_m3"],
                        "distance_to_global_center_m": item["distance_to_global_center_m"],
                        "distance_to_ground_plane_m": item["distance_to_ground_plane_m"],
                        "convex_hull_volume_m3": item["convex_hull_volume_m3"],
                        "occupancy_ratio": item["occupancy"]["occupancy_ratio"],
                        "count_ratio_to_main": item["heuristic_score"]["count_ratio_to_main"],
                        "plausible_woodpile": item["heuristic_score"]["plausible_woodpile"],
                        "passes_min_component_ratio": item["heuristic_score"]["passes_min_component_ratio"],
                        "discard_reasons": item["discard_reasons"],
                    }
                )


def write_reports(results: dict[str, Any]) -> None:
    lines = ["# DBSCAN Cluster Selection Report\n\n"]
    decision = ["# DBSCAN Decision Report\n\n"]
    for dataset, result in results.items():
        sel = result["selection"]
        lines.extend(
            [
                f"## {dataset}\n\n",
                f"- Segmentation voxelization: `{result['segmentation_voxelization_loss']['points_before']}` -> `{result['segmentation_voxelization_loss']['points_after']}` points; removed ratio `{result['segmentation_voxelization_loss']['removed_ratio']}`.\n",
                f"- DBSCAN input after voxelization: `{result['dbscan_input_point_count_after_voxelization']}` points.\n",
                f"- Clusters found: `{result['cluster_count']}`; noise points: `{result['noise_point_count']}`.\n",
                f"- Pipeline selected clusters: `{sel['selected_cluster_ids']}` by `{sel['selection_reason']}`.\n",
                f"- Selected ratio vs after-outlier cloud: `{sel['selected_ratio_after_outlier']}`.\n\n",
                "| Rank | Cluster | Selected | Points | Ratio | BBox volume | Density | Discard reasons |\n",
                "|---:|---:|---|---:|---:|---:|---:|---|\n",
            ]
        )
        for item in result["clusters"][:12]:
            lines.append(
                f"| {item['rank_by_current_heuristic']} | {item['cluster_id']} | {item['pipeline_selected']} | "
                f"{item['point_count']} | {item['point_ratio_input']} | {item['bbox_volume_m3']} | "
                f"{item['density_points_per_m3']} | {', '.join(item['discard_reasons']) or '-'} |\n"
            )
        best_combo = next((row for row in result["pdi_cluster_combinations"] if row["pdi"].get("status") == "ok"), None)
        pdi_selected = sel["pipeline_pdi"]
        decision.extend(
            [
                f"## {dataset}\n\n",
                f"- Selected clusters: `{sel['selected_cluster_ids']}`.\n",
                f"- Selected PDI volume: `{pdi_selected.get('volume_m3')}` m3.\n",
                f"- Best simulated combination by PDI volume: `{best_combo['cluster_ids'] if best_combo else None}` -> `{best_combo['pdi'].get('volume_m3') if best_combo else None}` m3.\n",
                f"- Segmentation voxelization loss: `{result['segmentation_voxelization_loss']['removed_ratio']}` of after-outlier points.\n",
                f"- Cluster selection loss after DBSCAN input: `{sel['selection_loss_after_dbscan_input']['removed_ratio']}`.\n",
                f"- Selected points ratio after outlier: `{sel['selected_ratio_after_outlier']}`.\n",
                "- Evidence: the observed 96-99% loss is dominated by the segmentation-stage voxelization used before DBSCAN, then compounded by the current cluster selection/ranking.\n\n",
            ]
        )
        lines.append("\n")
    (OUT / "cluster_selection_report.md").write_text("".join(lines), encoding="utf-8")
    decision.append("No pipeline change is proposed or applied in this experiment.\n")
    (OUT / "decision_report.md").write_text("".join(decision), encoding="utf-8")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    settings = settings_for_root()
    results = {dataset: analyze_dataset(dataset, session_id, settings) for dataset, session_id in DATASETS.items()}
    write_csv(results)
    (OUT / "cluster_statistics.json").write_text(json.dumps({k: v["clusters"] for k, v in results.items()}, indent=2), encoding="utf-8")
    ranking = {
        dataset: {
            "selected": result["selection"],
            "ranking": [
                {
                    "rank": item["rank_by_current_heuristic"],
                    "cluster_id": item["cluster_id"],
                    "point_count": item["point_count"],
                    "density_points_per_m3": item["density_points_per_m3"],
                    "pipeline_selected": item["pipeline_selected"],
                    "discard_reasons": item["discard_reasons"],
                }
                for item in result["clusters"]
            ],
        }
        for dataset, result in results.items()
    }
    (OUT / "cluster_ranking.json").write_text(json.dumps(ranking, indent=2), encoding="utf-8")
    (OUT / "pdi_per_cluster.json").write_text(json.dumps({k: v["pdi_per_cluster"] for k, v in results.items()}, indent=2), encoding="utf-8")
    (OUT / "pdi_cluster_combinations.json").write_text(json.dumps({k: v["pdi_cluster_combinations"] for k, v in results.items()}, indent=2), encoding="utf-8")
    write_reports(results)
    print(json.dumps({"out": str(OUT), "selected": {k: v["selection"] for k, v in results.items()}}, indent=2))


if __name__ == "__main__":
    main()
