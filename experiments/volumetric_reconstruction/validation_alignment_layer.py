from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.spatial import cKDTree
from scipy.spatial.transform import Rotation


@dataclass(frozen=True)
class AlignmentResult:
    depthmaps: list[dict]
    scale_correction: float
    offset_correction: np.ndarray
    camera_metrics: list[dict]
    rejected_frames: list[dict]
    accepted_frames: list[dict]
    drift_report: dict


def camera_matrix(camera: dict) -> np.ndarray:
    width = float(camera["width"])
    height = float(camera["height"])
    scale = max(width, height)
    return np.asarray(
        [
            [float(camera["focal_x"]) * scale, 0.0, width / 2.0 + float(camera.get("c_x", 0.0)) * scale],
            [0.0, float(camera["focal_y"]) * scale, height / 2.0 + float(camera.get("c_y", 0.0)) * scale],
            [0.0, 0.0, 1.0],
        ],
        dtype=float,
    )


def sfm_to_metric(points: np.ndarray, scale: float, sfm_center: np.ndarray, metric_center: np.ndarray) -> np.ndarray:
    return (points - sfm_center) * scale + metric_center


def _sample_depth_pixels(depth: np.ndarray, stride: int, max_samples: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    valid = np.isfinite(depth) & (depth > 0)
    ys, xs = np.where(valid)
    if len(xs) == 0:
        return np.empty(0, dtype=int), np.empty(0, dtype=int), np.empty(0, dtype=float)
    order = np.arange(len(xs))[::max(stride, 1)]
    if len(order) > max_samples:
        order = order[np.linspace(0, len(order) - 1, max_samples).astype(int)]
    return xs[order], ys[order], depth[ys[order], xs[order]]


def _depth_points_sfm(dm: dict, stride: int, max_samples: int) -> np.ndarray:
    xs, ys, depth = _sample_depth_pixels(dm["depth"], stride, max_samples)
    if len(xs) == 0:
        return np.empty((0, 3), dtype=float)
    camera = dm["camera"]
    k = camera_matrix(camera)
    scale_x = float(camera["width"]) / float(dm["depth_width"])
    scale_y = float(camera["height"]) / float(dm["depth_height"])
    u = xs.astype(float) * scale_x
    v = ys.astype(float) * scale_y
    x = (u - k[0, 2]) / k[0, 0] * depth
    y = (v - k[1, 2]) / k[1, 1] * depth
    points_cam = np.column_stack((x, y, depth))
    rot = Rotation.from_rotvec(np.asarray(dm["shot"]["rotation"], dtype=float)).as_matrix()
    trans = np.asarray(dm["shot"]["translation"], dtype=float)
    return (rot.T @ (points_cam - trans).T).T


def _coverage_ratio(points_metric: np.ndarray, bbox_min: np.ndarray, bbox_max: np.ndarray) -> float:
    if len(points_metric) == 0:
        return 0.0
    inside = np.all((points_metric >= bbox_min) & (points_metric <= bbox_max), axis=1)
    return float(np.count_nonzero(inside) / len(points_metric))


def _discontinuity_score(depth: np.ndarray) -> float:
    valid = np.isfinite(depth) & (depth > 0)
    if np.count_nonzero(valid) < 32:
        return 1.0
    dzx = np.abs(np.diff(np.where(valid, depth, np.nan), axis=1))
    dzy = np.abs(np.diff(np.where(valid, depth, np.nan), axis=0))
    vals = np.concatenate((dzx[np.isfinite(dzx)], dzy[np.isfinite(dzy)]))
    if len(vals) == 0:
        return 1.0
    scale = np.nanmedian(depth[valid])
    return float(np.nanmedian(vals) / max(scale, 1e-6))


def validate_and_align_depthmaps(
    depthmaps: list[dict],
    sfm_points: np.ndarray,
    processed_points_metric: np.ndarray,
    scale_sfm_to_metric: float,
    sfm_center: np.ndarray,
    metric_center: np.ndarray,
    grid_origin: np.ndarray,
    grid_dims: np.ndarray,
    grid_step_m: float,
    sample_stride: int = 12,
    max_samples_per_frame: int = 2500,
    min_coverage_ratio: float = 0.02,
    max_reprojection_error_m: float = 2.5,
) -> AlignmentResult:
    bbox_min = np.asarray(grid_origin, dtype=float)
    bbox_max = bbox_min + (np.asarray(grid_dims, dtype=float) - 1.0) * float(grid_step_m)
    tree = cKDTree(processed_points_metric)

    raw_frame_points: list[np.ndarray] = []
    frame_records: list[tuple[dict, np.ndarray, dict]] = []
    camera_metrics: list[dict] = []

    for dm in depthmaps:
        points_sfm = _depth_points_sfm(dm, sample_stride, max_samples_per_frame)
        points_metric = sfm_to_metric(points_sfm, scale_sfm_to_metric, sfm_center, metric_center)
        coverage = _coverage_ratio(points_metric, bbox_min, bbox_max)
        if len(points_metric):
            nn, _ = tree.query(points_metric, k=1, workers=-1)
            reproj_error = float(np.median(nn))
            stability = float(np.var(np.clip(nn, 0.0, max_reprojection_error_m)) / (max_reprojection_error_m ** 2))
        else:
            reproj_error = float("inf")
            stability = 1.0
        discontinuity = _discontinuity_score(dm["depth"])
        metric = {
            "file": dm.get("path", ""),
            "shot_id": dm.get("shot_id"),
            "valid_ratio": round(float(dm.get("valid_ratio", 0.0)), 6),
            "sampled_points": int(len(points_metric)),
            "voxel_coverage_ratio": round(coverage, 6),
            "reprojection_error_median_m": None if not np.isfinite(reproj_error) else round(reproj_error, 6),
            "depth_discontinuity_score": round(discontinuity, 6),
            "tsdf_contribution_variance_proxy": round(stability, 6),
        }
        raw_frame_points.append(points_metric)
        frame_records.append((dm, points_metric, metric))
        camera_metrics.append(metric)

    all_points = np.vstack([p for p in raw_frame_points if len(p)]) if any(len(p) for p in raw_frame_points) else np.empty((0, 3))
    if len(all_points) >= 8:
        depth_center = np.median(all_points, axis=0)
        target_center = np.median(processed_points_metric, axis=0)
        depth_extent = np.percentile(all_points, 95, axis=0) - np.percentile(all_points, 5, axis=0)
        target_extent = np.percentile(processed_points_metric, 95, axis=0) - np.percentile(processed_points_metric, 5, axis=0)
        ratios = target_extent[np.where(depth_extent > 1e-9)] / depth_extent[np.where(depth_extent > 1e-9)]
        scale_correction = float(np.clip(np.median(ratios[np.isfinite(ratios)]), 0.5, 2.0)) if ratios.size else 1.0
        offset_correction = target_center - (depth_center - metric_center) * scale_correction - metric_center
    else:
        depth_center = np.zeros(3, dtype=float)
        target_center = np.median(processed_points_metric, axis=0)
        scale_correction = 1.0
        offset_correction = np.zeros(3, dtype=float)

    accepted: list[dict] = []
    rejected: list[dict] = []
    corrected_depthmaps: list[dict] = []
    for dm, points_metric, metric in frame_records:
        err = metric["reprojection_error_median_m"]
        coverage = float(metric["voxel_coverage_ratio"])
        bad = err is None or err > max_reprojection_error_m or coverage < min_coverage_ratio
        enriched = dict(metric)
        enriched["bad_frame"] = bool(bad)
        if bad:
            enriched["reason"] = "low_coverage_or_high_reprojection_error"
            rejected.append(enriched)
            continue
        stability = float(metric["tsdf_contribution_variance_proxy"])
        weight_multiplier = float(np.clip(coverage / (1.0 + stability), 0.05, 1.0))
        dm2 = dict(dm)
        dm2["alignment_weight_multiplier"] = weight_multiplier
        accepted.append({**enriched, "weight_multiplier": round(weight_multiplier, 6)})
        corrected_depthmaps.append(dm2)

    drift_report = {
        "depth_center_metric": [round(float(v), 6) for v in depth_center.tolist()],
        "target_center_metric": [round(float(v), 6) for v in target_center.tolist()],
        "scale_correction": round(float(scale_correction), 6),
        "offset_correction_m": [round(float(v), 6) for v in offset_correction.tolist()],
        "input_frame_count": len(depthmaps),
        "accepted_frame_count": len(accepted),
        "rejected_frame_count": len(rejected),
        "median_reprojection_error_m": round(float(np.median([m["reprojection_error_median_m"] for m in camera_metrics if m["reprojection_error_median_m"] is not None])), 6) if any(m["reprojection_error_median_m"] is not None for m in camera_metrics) else None,
        "mean_voxel_coverage_ratio": round(float(np.mean([m["voxel_coverage_ratio"] for m in camera_metrics])), 6) if camera_metrics else 0.0,
    }

    return AlignmentResult(
        depthmaps=corrected_depthmaps,
        scale_correction=scale_correction,
        offset_correction=offset_correction,
        camera_metrics=camera_metrics,
        rejected_frames=rejected,
        accepted_frames=accepted,
        drift_report=drift_report,
    )
