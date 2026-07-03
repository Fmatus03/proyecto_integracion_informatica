from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.spatial.transform import Rotation


@dataclass(frozen=True)
class SCCRResult:
    depthmaps: list[dict]
    camera_metrics_before: list[dict]
    camera_metrics_after: list[dict]
    accepted_frames: list[dict]
    rejected_frames: list[dict]
    refinement_report: dict


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


def metric_to_sfm(points: np.ndarray, scale: float, sfm_center: np.ndarray, metric_center: np.ndarray) -> np.ndarray:
    return (points - metric_center) / scale + sfm_center


def _sample_depth_pixels(depth: np.ndarray, stride: int, max_samples: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    valid = np.isfinite(depth) & (depth > 0)
    ys, xs = np.where(valid)
    if len(xs) == 0:
        return np.empty(0, dtype=int), np.empty(0, dtype=int), np.empty(0, dtype=float)
    order = np.arange(len(xs))[::max(int(stride), 1)]
    if len(order) > max_samples:
        order = order[np.linspace(0, len(order) - 1, max_samples).astype(int)]
    return xs[order], ys[order], depth[ys[order], xs[order]]


def _depth_points_sfm(dm: dict, rotvec: np.ndarray, translation: np.ndarray, stride: int, max_samples: int) -> np.ndarray:
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
    rot = Rotation.from_rotvec(rotvec).as_matrix()
    return (rot.T @ (points_cam - translation).T).T


def _project_sfm(points_sfm: np.ndarray, rotvec: np.ndarray, translation: np.ndarray, camera: dict) -> tuple[np.ndarray, np.ndarray]:
    rot = Rotation.from_rotvec(rotvec).as_matrix()
    cam = (rot @ points_sfm.T).T + translation
    z = cam[:, 2]
    k = camera_matrix(camera)
    with np.errstate(divide="ignore", invalid="ignore"):
        u = k[0, 0] * (cam[:, 0] / z) + k[0, 2]
        v = k[1, 1] * (cam[:, 1] / z) + k[1, 2]
    return np.column_stack((u, v)), z


def _sample_depth_nearest(dm: dict, uv: np.ndarray) -> np.ndarray:
    camera = dm["camera"]
    scale_x = float(dm["depth_width"]) / float(camera["width"])
    scale_y = float(dm["depth_height"]) / float(camera["height"])
    x = np.rint(uv[:, 0] * scale_x).astype(int)
    y = np.rint(uv[:, 1] * scale_y).astype(int)
    valid = (x >= 0) & (x < int(dm["depth_width"])) & (y >= 0) & (y < int(dm["depth_height"]))
    sampled = np.full(len(uv), np.nan, dtype=float)
    sampled[valid] = dm["depth"][y[valid], x[valid]]
    return sampled


def _nearest_grid_values(
    points_metric: np.ndarray,
    tsdf_grid: np.ndarray,
    weight_grid: np.ndarray,
    origin: np.ndarray,
    grid_step_m: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    dims = np.asarray(tsdf_grid.shape, dtype=np.int32)
    ijk = np.rint((points_metric - origin) / float(grid_step_m)).astype(np.int32)
    valid = np.all((ijk >= 0) & (ijk < dims), axis=1)
    values = np.full(len(points_metric), np.nan, dtype=float)
    weights = np.zeros(len(points_metric), dtype=float)
    if np.any(valid):
        idx = ijk[valid]
        values[valid] = tsdf_grid[idx[:, 0], idx[:, 1], idx[:, 2]]
        weights[valid] = weight_grid[idx[:, 0], idx[:, 1], idx[:, 2]]
    return values, weights, valid


def _surface_points_metric(
    tsdf_grid: np.ndarray,
    weight_grid: np.ndarray,
    origin: np.ndarray,
    grid_step_m: float,
    max_points: int,
    min_weight: float,
) -> np.ndarray:
    mask = (np.abs(tsdf_grid) <= 0.18) & (weight_grid >= min_weight)
    idx = np.argwhere(mask)
    if len(idx) == 0:
        mask = np.abs(tsdf_grid) <= 0.08
        idx = np.argwhere(mask)
    if len(idx) == 0:
        return np.empty((0, 3), dtype=float)
    if len(idx) > max_points:
        idx = idx[np.linspace(0, len(idx) - 1, max_points).astype(int)]
    return origin + idx.astype(float) * float(grid_step_m)


def _evaluate_pose(
    dm: dict,
    rotvec: np.ndarray,
    translation: np.ndarray,
    tsdf_grid: np.ndarray,
    weight_grid: np.ndarray,
    surface_points_sfm: np.ndarray,
    origin: np.ndarray,
    grid_step_m: float,
    truncation_m: float,
    scale_sfm_to_metric: float,
    sfm_center: np.ndarray,
    metric_center: np.ndarray,
    min_weight: float,
    sample_stride: int,
    max_samples_per_frame: int,
) -> dict:
    depth_points_sfm = _depth_points_sfm(dm, rotvec, translation, sample_stride, max_samples_per_frame)
    if len(depth_points_sfm):
        points_metric = sfm_to_metric(depth_points_sfm, scale_sfm_to_metric, sfm_center, metric_center)
        tsdf_values, grid_weights, inside = _nearest_grid_values(points_metric, tsdf_grid, weight_grid, origin, grid_step_m)
        known = inside & np.isfinite(tsdf_values) & (grid_weights >= min_weight)
        if np.any(known):
            depth_error_m = float(np.median(np.abs(tsdf_values[known])) * truncation_m)
            stability = float(np.var(np.clip(np.abs(tsdf_values[known]), 0.0, 1.0)))
        else:
            depth_error_m = float("inf")
            stability = 1.0
        occupancy = float(np.count_nonzero(known) / len(depth_points_sfm))
        voxel_coverage = float(np.count_nonzero(inside) / len(depth_points_sfm))
    else:
        depth_error_m = float("inf")
        stability = 1.0
        occupancy = 0.0
        voxel_coverage = 0.0

    surface_depth_error_m = float("inf")
    silhouette_overlap = 0.0
    visible_surface = 0
    if len(surface_points_sfm):
        uv, z = _project_sfm(surface_points_sfm, rotvec, translation, dm["camera"])
        w, h = float(dm["camera"]["width"]), float(dm["camera"]["height"])
        visible = (z > 0) & (uv[:, 0] >= 0) & (uv[:, 0] < w) & (uv[:, 1] >= 0) & (uv[:, 1] < h)
        visible_surface = int(np.count_nonzero(visible))
        if visible_surface:
            sampled = _sample_depth_nearest(dm, uv[visible])
            valid_depth = np.isfinite(sampled)
            silhouette_overlap = float(np.count_nonzero(valid_depth) / visible_surface)
            if np.any(valid_depth):
                surface_depth_error_m = float(np.median(np.abs(sampled[valid_depth] - z[visible][valid_depth])) * scale_sfm_to_metric)

    depth_score = 0.0 if not np.isfinite(depth_error_m) else float(np.exp(-depth_error_m / max(truncation_m, 1e-9)))
    surface_score = 0.0 if not np.isfinite(surface_depth_error_m) else float(np.exp(-surface_depth_error_m / max(truncation_m, 1e-9)))
    camera_score = (
        0.42 * depth_score
        + 0.22 * occupancy
        + 0.18 * silhouette_overlap
        + 0.10 * voxel_coverage
        + 0.08 * (1.0 - min(stability, 1.0))
    )
    objective = (
        (depth_error_m if np.isfinite(depth_error_m) else truncation_m * 4.0)
        + 0.35 * (surface_depth_error_m if np.isfinite(surface_depth_error_m) else truncation_m * 4.0)
        + (1.0 - occupancy) * truncation_m * 0.20
        + stability * truncation_m * 0.10
    )
    return {
        "camera_score": float(np.clip(camera_score, 0.0, 1.0)),
        "objective_m": float(objective),
        "depth_alignment_error_m": None if not np.isfinite(depth_error_m) else round(depth_error_m, 6),
        "surface_depth_error_m": None if not np.isfinite(surface_depth_error_m) else round(surface_depth_error_m, 6),
        "voxel_occupancy_agreement": round(occupancy, 6),
        "voxel_coverage_ratio": round(voxel_coverage, 6),
        "silhouette_overlap": round(silhouette_overlap, 6),
        "tsdf_alignment_stability": round(1.0 - min(stability, 1.0), 6),
        "visible_surface_samples": visible_surface,
        "sampled_depth_points": int(len(depth_points_sfm)),
    }


def _candidate_poses(
    rotvec: np.ndarray,
    translation: np.ndarray,
    translation_step_sfm: float,
    rotation_step_deg: float,
) -> list[tuple[np.ndarray, np.ndarray, str, float, float]]:
    candidates: list[tuple[np.ndarray, np.ndarray, str, float, float]] = [(rotvec.copy(), translation.copy(), "identity", 0.0, 0.0)]
    axes = np.eye(3, dtype=float)
    for axis_id, axis in enumerate(axes):
        for sign in (-1.0, 1.0):
            delta = axis * translation_step_sfm * sign
            candidates.append((rotvec.copy(), translation + delta, f"translate_{axis_id}_{int(sign)}", float(np.linalg.norm(delta)), 0.0))
    for axis_id, axis in enumerate(axes):
        for sign in (-1.0, 1.0):
            drot = Rotation.from_rotvec(axis * np.deg2rad(rotation_step_deg) * sign)
            base = Rotation.from_rotvec(rotvec)
            new_rot = (drot * base).as_rotvec()
            candidates.append((new_rot, translation.copy(), f"rotate_{axis_id}_{int(sign)}", 0.0, float(np.deg2rad(rotation_step_deg))))
    return candidates


def refine_cameras_self_consistent(
    depthmaps: list[dict],
    tsdf: np.ndarray,
    weights: np.ndarray,
    grid_origin: np.ndarray,
    grid_dims: np.ndarray,
    grid_step_m: float,
    truncation_m: float,
    scale_sfm_to_metric: float,
    sfm_center: np.ndarray,
    metric_center: np.ndarray,
    min_weight: float,
    iterations: int = 2,
    sample_stride: int = 16,
    max_samples_per_frame: int = 1800,
    surface_sample_count: int = 2400,
    translation_step_m: float = 0.08,
    rotation_step_deg: float = 0.35,
    min_score: float = 0.35,
    reject_score: float = 0.12,
) -> SCCRResult:
    """Refine camera poses using only local TSDF/depth self-consistency.

    This is intentionally not bundle adjustment. It performs small, regularized
    coordinate-search updates per camera, using the coarse TSDF as the consistency
    reference and preserving the rest of the volumetric pipeline unchanged.
    """
    dims = tuple(int(v) for v in np.asarray(grid_dims, dtype=np.int32).tolist())
    tsdf_grid = tsdf.reshape(dims)
    weight_grid = weights.reshape(dims)
    surface_metric = _surface_points_metric(tsdf_grid, weight_grid, np.asarray(grid_origin, dtype=float), grid_step_m, surface_sample_count, min_weight)
    surface_sfm = metric_to_sfm(surface_metric, scale_sfm_to_metric, sfm_center, metric_center) if len(surface_metric) else np.empty((0, 3), dtype=float)

    current: list[dict] = []
    before_metrics: list[dict] = []
    for dm in depthmaps:
        shot = dm["shot"]
        rotvec = np.asarray(shot["rotation"], dtype=float)
        translation = np.asarray(shot["translation"], dtype=float)
        metric = _evaluate_pose(
            dm,
            rotvec,
            translation,
            tsdf_grid,
            weight_grid,
            surface_sfm,
            np.asarray(grid_origin, dtype=float),
            grid_step_m,
            truncation_m,
            scale_sfm_to_metric,
            sfm_center,
            metric_center,
            min_weight,
            sample_stride,
            max_samples_per_frame,
        )
        record = {"dm": dm, "rotvec": rotvec, "translation": translation, "initial": metric, "updates": []}
        current.append(record)
        before_metrics.append({"file": dm.get("path", ""), "shot_id": dm.get("shot_id"), **_rounded_metric(metric)})

    translation_step_sfm = float(translation_step_m) / max(float(scale_sfm_to_metric), 1e-9)
    for iteration in range(max(int(iterations), 0)):
        step_decay = 0.65 ** iteration
        for record in current:
            baseline = _evaluate_pose(
                record["dm"],
                record["rotvec"],
                record["translation"],
                tsdf_grid,
                weight_grid,
                surface_sfm,
                np.asarray(grid_origin, dtype=float),
                grid_step_m,
                truncation_m,
                scale_sfm_to_metric,
                sfm_center,
                metric_center,
                min_weight,
                sample_stride,
                max_samples_per_frame,
            )
            best = baseline
            best_pose = (record["rotvec"], record["translation"])
            best_name = "identity"
            for cand_rot, cand_t, name, delta_t_sfm, delta_rot_rad in _candidate_poses(
                record["rotvec"],
                record["translation"],
                translation_step_sfm * step_decay,
                rotation_step_deg * step_decay,
            ):
                metric = _evaluate_pose(
                    record["dm"],
                    cand_rot,
                    cand_t,
                    tsdf_grid,
                    weight_grid,
                    surface_sfm,
                    np.asarray(grid_origin, dtype=float),
                    grid_step_m,
                    truncation_m,
                    scale_sfm_to_metric,
                    sfm_center,
                    metric_center,
                    min_weight,
                    sample_stride,
                    max_samples_per_frame,
                )
                regularized_objective = metric["objective_m"] + delta_t_sfm * scale_sfm_to_metric * 0.20 + delta_rot_rad * truncation_m * 0.40
                if regularized_objective < best["objective_m"] - max(0.005, truncation_m * 0.002):
                    best = {**metric, "objective_m": regularized_objective}
                    best_pose = (cand_rot, cand_t)
                    best_name = name
            if best_name != "identity":
                record["updates"].append(
                    {
                        "iteration": iteration + 1,
                        "update": best_name,
                        "score_before": round(float(baseline["camera_score"]), 6),
                        "score_after": round(float(best["camera_score"]), 6),
                        "objective_before_m": round(float(baseline["objective_m"]), 6),
                        "objective_after_m": round(float(best["objective_m"]), 6),
                    }
                )
                record["rotvec"], record["translation"] = best_pose

    refined_depthmaps: list[dict] = []
    after_metrics: list[dict] = []
    accepted: list[dict] = []
    rejected: list[dict] = []
    for record in current:
        dm = record["dm"]
        metric = _evaluate_pose(
            dm,
            record["rotvec"],
            record["translation"],
            tsdf_grid,
            weight_grid,
            surface_sfm,
            np.asarray(grid_origin, dtype=float),
            grid_step_m,
            truncation_m,
            scale_sfm_to_metric,
            sfm_center,
            metric_center,
            min_weight,
            sample_stride,
            max_samples_per_frame,
        )
        enriched = {
            "file": dm.get("path", ""),
            "shot_id": dm.get("shot_id"),
            **_rounded_metric(metric),
            "updates": record["updates"],
        }
        after_metrics.append(enriched)
        if metric["camera_score"] < reject_score:
            rejected.append({**enriched, "reason": "sccr_score_below_reject_threshold"})
            continue
        dm2 = dict(dm)
        shot2 = dict(dm["shot"])
        shot2["rotation"] = [float(v) for v in record["rotvec"].tolist()]
        shot2["translation"] = [float(v) for v in record["translation"].tolist()]
        dm2["shot"] = shot2
        prior_weight = float(dm2.get("alignment_weight_multiplier", 1.0))
        score_weight = float(np.clip(metric["camera_score"] / max(min_score, 1e-6), 0.05, 1.0))
        dm2["sccr_camera_score"] = float(metric["camera_score"])
        dm2["alignment_weight_multiplier"] = float(np.clip(prior_weight * score_weight, 0.05, 1.0))
        accepted.append({**enriched, "weight_multiplier": round(dm2["alignment_weight_multiplier"], 6)})
        refined_depthmaps.append(dm2)

    before_scores = [m["camera_score"] for m in before_metrics]
    after_scores = [m["camera_score"] for m in after_metrics]
    before_errors = [m["depth_alignment_error_m"] for m in before_metrics if m["depth_alignment_error_m"] is not None]
    after_errors = [m["depth_alignment_error_m"] for m in after_metrics if m["depth_alignment_error_m"] is not None]
    report = {
        "input_frame_count": len(depthmaps),
        "accepted_frame_count": len(accepted),
        "rejected_frame_count": len(rejected),
        "iterations": int(iterations),
        "translation_step_m": float(translation_step_m),
        "rotation_step_deg": float(rotation_step_deg),
        "surface_sample_count": int(len(surface_metric)),
        "mean_camera_score_before": round(float(np.mean(before_scores)), 6) if before_scores else 0.0,
        "mean_camera_score_after": round(float(np.mean(after_scores)), 6) if after_scores else 0.0,
        "median_depth_alignment_error_before_m": round(float(np.median(before_errors)), 6) if before_errors else None,
        "median_depth_alignment_error_after_m": round(float(np.median(after_errors)), 6) if after_errors else None,
        "pose_update_count": int(sum(len(r["updates"]) for r in current)),
    }
    return SCCRResult(
        depthmaps=refined_depthmaps,
        camera_metrics_before=before_metrics,
        camera_metrics_after=after_metrics,
        accepted_frames=accepted,
        rejected_frames=rejected,
        refinement_report=report,
    )


def _rounded_metric(metric: dict) -> dict:
    result = {}
    for key, value in metric.items():
        if key == "objective_m":
            continue
        if isinstance(value, float):
            result[key] = None if not np.isfinite(value) else round(value, 6)
        else:
            result[key] = value
    return result
