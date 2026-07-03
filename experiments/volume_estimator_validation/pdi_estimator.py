from __future__ import annotations

import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import open3d as o3d
from scipy import ndimage
from scipy.spatial import ConvexHull, cKDTree


DEFAULT_VOXEL_SIZE_M = 0.25


@dataclass(frozen=True)
class PDIResult:
    volume_m3: float
    voxel_size_m: float
    density_threshold_points_per_voxel: int
    hull_density_points_per_m3: float
    hull_volume_m3: float
    solid_voxels: int
    occupied_voxels: int
    dense_voxels: int
    execution_time_seconds: float


def read_point_cloud(path: Path) -> np.ndarray:
    cloud = o3d.io.read_point_cloud(str(path))
    points = np.asarray(cloud.points, dtype=np.float64)
    return preprocess_points(points)


def preprocess_points(points: np.ndarray) -> np.ndarray:
    if points.ndim != 2 or points.shape[1] != 3:
        raise ValueError("PDI input must be an Nx3 point cloud.")
    finite = points[np.all(np.isfinite(points), axis=1)]
    if len(finite) < 4:
        raise ValueError("PDI requires at least four finite points.")
    return np.asarray(finite, dtype=np.float64)


def occupancy_grid(points: np.ndarray, voxel_size_m: float) -> tuple[np.ndarray, np.ndarray]:
    origin = points.min(axis=0) - 4 * voxel_size_m
    dims = np.ceil((points.max(axis=0) + 4 * voxel_size_m - origin) / voxel_size_m).astype(int) + 1
    idx = np.floor((points - origin) / voxel_size_m).astype(np.int32)
    grid = np.zeros(tuple(dims.tolist()), dtype=bool)
    grid[idx[:, 0], idx[:, 1], idx[:, 2]] = True
    return grid, origin


def solid_from_occupancy(occupancy: np.ndarray) -> np.ndarray:
    structure = ndimage.generate_binary_structure(3, 2)
    shell = ndimage.binary_dilation(occupancy, structure=structure, iterations=2)
    solid = ndimage.binary_fill_holes(shell)
    solid = ndimage.binary_closing(solid, structure=structure, iterations=1)
    solid = ndimage.binary_fill_holes(solid)
    labels, count = ndimage.label(solid, structure=structure)
    if count > 1:
        sizes = np.bincount(labels.ravel())
        sizes[0] = 0
        solid = labels == int(np.argmax(sizes))
    return solid


def estimate_volume(points: np.ndarray, voxel_size_m: float = DEFAULT_VOXEL_SIZE_M) -> PDIResult:
    points = preprocess_points(points)
    start = time.perf_counter()
    hull_volume = float(ConvexHull(points).volume)
    hull_density = len(points) / hull_volume if hull_volume > 0 else 0.0
    occupancy, origin = occupancy_grid(points, voxel_size_m)
    counts = np.zeros_like(occupancy, dtype=np.int32)
    idx = np.floor((points - origin) / voxel_size_m).astype(np.int32)
    np.add.at(counts, (idx[:, 0], idx[:, 1], idx[:, 2]), 1)
    threshold = max(1, int(np.ceil(hull_density * (voxel_size_m ** 3) * 0.35)))
    dense = counts >= threshold
    solid = solid_from_occupancy(dense)
    elapsed = time.perf_counter() - start
    return PDIResult(
        volume_m3=float(np.count_nonzero(solid) * (voxel_size_m ** 3)),
        voxel_size_m=float(voxel_size_m),
        density_threshold_points_per_voxel=int(threshold),
        hull_density_points_per_m3=float(hull_density),
        hull_volume_m3=float(hull_volume),
        solid_voxels=int(np.count_nonzero(solid)),
        occupied_voxels=int(np.count_nonzero(occupancy)),
        dense_voxels=int(np.count_nonzero(dense)),
        execution_time_seconds=float(elapsed),
    )


def bbox_metrics(points: np.ndarray) -> dict[str, Any]:
    mins = points.min(axis=0)
    maxs = points.max(axis=0)
    extent = maxs - mins
    safe_extent = np.maximum(extent, 1e-9)
    volume = float(np.prod(safe_extent))
    return {
        "bbox_min": [round(float(v), 6) for v in mins.tolist()],
        "bbox_max": [round(float(v), 6) for v in maxs.tolist()],
        "bbox_extent_m": [round(float(v), 6) for v in extent.tolist()],
        "bbox_volume_m3": round(volume, 6),
        "bbox_aspect_ratio": round(float(safe_extent.max() / safe_extent.min()), 6),
        "bbox_axis_order": ["x", "y", "z"],
    }


def nearest_neighbor_metrics(points: np.ndarray, sample_limit: int = 12000) -> dict[str, Any]:
    sample = points
    if len(points) > sample_limit:
        sample = points[np.linspace(0, len(points) - 1, sample_limit).astype(int)]
    distances, _ = cKDTree(sample).query(sample, k=2)
    nn = distances[:, 1]
    nn = nn[np.isfinite(nn) & (nn > 0)]
    if len(nn) == 0:
        return {
            "median_nn_m": None,
            "mean_nn_m": None,
            "local_density_cv": None,
            "isolated_point_ratio": 1.0,
            "outlier_ratio": 1.0,
        }
    q1, q3 = np.quantile(nn, [0.25, 0.75])
    iqr = q3 - q1
    outlier_limit = q3 + 1.5 * iqr
    isolated_limit = max(float(np.median(nn)) * 4.0, outlier_limit)
    return {
        "median_nn_m": round(float(np.median(nn)), 6),
        "mean_nn_m": round(float(np.mean(nn)), 6),
        "local_density_cv": round(float(np.std(nn) / np.mean(nn)), 6) if np.mean(nn) else None,
        "isolated_point_ratio": round(float(np.mean(nn > isolated_limit)), 6),
        "outlier_ratio": round(float(np.mean(nn > outlier_limit)), 6),
        "nn_outlier_limit_m": round(float(outlier_limit), 6),
    }


def coverage_metrics(points: np.ndarray, bins: int = 6) -> dict[str, Any]:
    mins = points.min(axis=0)
    extent = np.maximum(points.max(axis=0) - mins, 1e-9)
    normalized = np.clip((points - mins) / extent, 0.0, 0.999999)
    idx = np.floor(normalized * bins).astype(np.int32)
    grid = np.zeros((bins, bins, bins), dtype=bool)
    grid[idx[:, 0], idx[:, 1], idx[:, 2]] = True
    occupied = int(np.count_nonzero(grid))
    total = int(grid.size)
    interior = grid[1:-1, 1:-1, 1:-1]
    face_ratios = {
        "x_min": float(np.mean(grid[0, :, :])),
        "x_max": float(np.mean(grid[-1, :, :])),
        "y_min": float(np.mean(grid[:, 0, :])),
        "y_max": float(np.mean(grid[:, -1, :])),
        "z_min": float(np.mean(grid[:, :, 0])),
        "z_max": float(np.mean(grid[:, :, -1])),
    }
    lateral = [face_ratios[key] for key in ("x_min", "x_max", "y_min", "y_max")]
    return {
        "coverage_grid_bins": bins,
        "spatial_coverage_ratio": round(float(occupied / total), 6),
        "interior_hole_ratio": round(float(np.mean(~interior)), 6) if interior.size else None,
        "lateral_coverage_ratio": round(float(np.mean(lateral)), 6),
        "top_coverage_ratio": round(face_ratios["z_max"], 6),
        "bottom_coverage_ratio": round(face_ratios["z_min"], 6),
        "face_coverage_ratios": {key: round(value, 6) for key, value in face_ratios.items()},
    }


def component_metrics(points: np.ndarray, voxel_size_m: float = DEFAULT_VOXEL_SIZE_M) -> dict[str, Any]:
    occupancy, _ = occupancy_grid(points, voxel_size_m)
    labels, count = ndimage.label(occupancy, structure=ndimage.generate_binary_structure(3, 2))
    sizes = np.bincount(labels.ravel()) if count else np.asarray([0])
    if len(sizes) > 1:
        sizes[0] = 0
    dominant = int(sizes.max()) if len(sizes) else 0
    occupied = int(np.count_nonzero(occupancy))
    return {
        "voxel_components": int(count),
        "dominant_component_voxel_ratio": round(float(dominant / occupied), 6) if occupied else 0.0,
        "occupied_voxels": occupied,
    }


def _status(value: float, warning: float, fail: float, higher_is_worse: bool = True) -> str:
    if higher_is_worse:
        if value >= fail:
            return "FAIL"
        if value >= warning:
            return "WARNING"
        return "PASS"
    if value <= fail:
        return "FAIL"
    if value <= warning:
        return "WARNING"
    return "PASS"


def _gate(name: str, status: str, metric: str, value: Any, explanation: str) -> dict[str, Any]:
    return {"gate": name, "status": status, "metric": metric, "value": value, "explanation": explanation}


def quality_gates(points: np.ndarray, voxel_size_m: float = DEFAULT_VOXEL_SIZE_M) -> dict[str, Any]:
    points = preprocess_points(points)
    bbox = bbox_metrics(points)
    nn = nearest_neighbor_metrics(points)
    coverage = coverage_metrics(points)
    components = component_metrics(points, voxel_size_m)
    bbox_volume = max(float(bbox["bbox_volume_m3"]), 1e-9)
    mean_density = len(points) / bbox_volume
    metrics = {
        "point_count": int(len(points)),
        "mean_density_points_per_m3": round(float(mean_density), 6),
        **bbox,
        **nn,
        **coverage,
        **components,
    }
    gates = [
        _gate("segmentation.isolated_points", _status(float(nn["isolated_point_ratio"]), 0.03, 0.08), "isolated_point_ratio", nn["isolated_point_ratio"], "High isolated-point ratio indicates possible background leakage or sparse segmentation."),
        _gate("segmentation.outliers", _status(float(nn["outlier_ratio"]), 0.10, 0.20), "outlier_ratio", nn["outlier_ratio"], "Nearest-neighbor outliers expand support and can inflate PDI volume."),
        _gate("segmentation.mean_density", _status(float(mean_density), 15.0, 8.0, higher_is_worse=False), "mean_density_points_per_m3", round(float(mean_density), 6), "Low global density increases sensitivity to voxelization."),
        _gate("segmentation.bbox_aspect", _status(float(bbox["bbox_aspect_ratio"]), 4.5, 7.0), "bbox_aspect_ratio", bbox["bbox_aspect_ratio"], "Extreme bounding-box ratios can indicate missing views or background contamination."),
        _gate("coverage.spatial_distribution", _status(float(coverage["spatial_coverage_ratio"]), 0.08, 0.04, higher_is_worse=False), "spatial_coverage_ratio", coverage["spatial_coverage_ratio"], "Low occupied-cell coverage suggests incomplete spatial support."),
        _gate("coverage.interior_holes", _status(float(coverage["interior_hole_ratio"]), 0.82, 0.92), "interior_hole_ratio", coverage["interior_hole_ratio"], "High empty-interior ratio is a proxy for large holes or missing regions."),
        _gate("coverage.lateral", _status(float(coverage["lateral_coverage_ratio"]), 0.18, 0.10, higher_is_worse=False), "lateral_coverage_ratio", coverage["lateral_coverage_ratio"], "Low lateral coverage can cause structured underestimation."),
        _gate("coverage.top", _status(float(coverage["top_coverage_ratio"]), 0.15, 0.08, higher_is_worse=False), "top_coverage_ratio", coverage["top_coverage_ratio"], "Low top coverage can indicate missing upper surface observations."),
        _gate("coverage.bottom", _status(float(coverage["bottom_coverage_ratio"]), 0.08, 0.03, higher_is_worse=False), "bottom_coverage_ratio", coverage["bottom_coverage_ratio"], "Low bottom coverage is expected in aerial capture but still reduces volumetric confidence."),
        _gate("geometry.point_count", _status(float(len(points)), 10000.0, 5000.0, higher_is_worse=False), "point_count", int(len(points)), "Low point count reduces estimator stability."),
        _gate("geometry.components", _status(float(components["voxel_components"]), 150.0, 300.0), "voxel_components", components["voxel_components"], "Many disconnected occupied components indicate fragmentation or background leakage."),
        _gate("geometry.spatial_consistency", _status(float(components["dominant_component_voxel_ratio"]), 0.70, 0.50, higher_is_worse=False), "dominant_component_voxel_ratio", components["dominant_component_voxel_ratio"], "Low dominant-component ratio indicates fragmented spatial support."),
    ]
    counts = {"PASS": 0, "WARNING": 0, "FAIL": 0}
    for gate in gates:
        counts[gate["status"]] += 1
    return {"metrics": metrics, "gates": gates, "gate_counts": counts}


def confidence_score(quality_report: dict[str, Any], stability_cv: float | None = None) -> dict[str, Any]:
    score = 100.0
    reasons: list[str] = []
    penalties = {"WARNING": 5.0, "FAIL": 15.0}
    for gate in quality_report["gates"]:
        penalty = penalties.get(gate["status"], 0.0)
        score -= penalty
        if penalty:
            reasons.append(f"{gate['gate']}: {gate['status']} ({gate['explanation']})")
    if stability_cv is not None:
        if stability_cv >= 0.25:
            score -= 10.0
            reasons.append("estimator.stability: WARNING (cross-set coefficient of variation is high).")
        elif stability_cv >= 0.15:
            score -= 5.0
            reasons.append("estimator.stability: WARNING (cross-set coefficient of variation is moderate).")
    score = max(0.0, min(100.0, score))
    if score >= 80:
        level = "HIGH"
    elif score >= 60:
        level = "MEDIUM"
    elif score >= 40:
        level = "LOW"
    else:
        level = "CRITICAL"
    return {
        "score_percent": round(float(score), 2),
        "level": level,
        "diagnosis": reasons or ["No quality gate produced WARNING or FAIL."],
        "uses_ground_truth": False,
    }


def result_to_dict(result: PDIResult) -> dict[str, Any]:
    return {
        "volume_m3": round(result.volume_m3, 6),
        "voxel_size_m": result.voxel_size_m,
        "density_threshold_points_per_voxel": result.density_threshold_points_per_voxel,
        "hull_density_points_per_m3": round(result.hull_density_points_per_m3, 6),
        "hull_volume_m3": round(result.hull_volume_m3, 6),
        "solid_voxels": result.solid_voxels,
        "occupied_voxels": result.occupied_voxels,
        "dense_voxels": result.dense_voxels,
        "execution_time_seconds": round(result.execution_time_seconds, 6),
    }


def confidence_from_bootstrap(points: np.ndarray, trials: int = 5, removal_ratio: float = 0.05) -> dict[str, Any]:
    volumes = []
    rng = np.random.default_rng(20260629)
    for _ in range(trials):
        keep = int(math.floor(len(points) * (1.0 - removal_ratio)))
        idx = rng.choice(len(points), size=max(4, keep), replace=False)
        volumes.append(estimate_volume(points[np.sort(idx)]).volume_m3)
    arr = np.asarray(volumes, dtype=float)
    return {
        "bootstrap_trials": trials,
        "removal_ratio": removal_ratio,
        "volume_mean_m3": round(float(arr.mean()), 6),
        "volume_std_m3": round(float(arr.std(ddof=1)), 6) if len(arr) > 1 else 0.0,
        "volume_cv": round(float(arr.std(ddof=1) / arr.mean()), 6) if len(arr) > 1 and arr.mean() else 0.0,
    }
