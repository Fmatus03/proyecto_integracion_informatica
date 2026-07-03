from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.spatial.transform import Rotation


@dataclass(frozen=True)
class RayIntegrationResult:
    tsdf_update: np.ndarray
    weights: np.ndarray
    visibility_mask: np.ndarray
    free_space_voxels: int
    surface_voxels: int
    rays_integrated: int


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


def integrate_free_space_rays(
    depthmaps: list[dict],
    grid_origin: np.ndarray,
    grid_dims: np.ndarray,
    grid_step_m: float,
    truncation_m: float,
    scale_sfm_to_metric: float,
    sfm_center: np.ndarray,
    metric_center: np.ndarray,
    pixel_stride: int = 12,
    free_space_weight: float = 0.35,
    surface_weight: float = 1.0,
    max_depth_quantile: float = 0.98,
) -> RayIntegrationResult:
    """Integrate camera-ray free-space evidence into a TSDF-shaped grid.

    This module is intentionally additive: it returns a separate TSDF update and
    weights. Callers decide how to merge it with their base TSDF.

    Sign convention matches the existing prototypes: positive is observed free
    space in front of a surface, negative is behind/inside the surface band.
    """
    dims = np.asarray(grid_dims, dtype=np.int32)
    total = int(np.prod(dims))
    tsdf_sum = np.zeros(total, dtype=np.float64)
    weight_sum = np.zeros(total, dtype=np.float64)
    visible = np.zeros(total, dtype=bool)
    free_space_voxels: set[int] = set()
    surface_voxels: set[int] = set()
    rays_integrated = 0

    step = max(float(grid_step_m) * 0.75, 1e-6)
    stride = max(int(pixel_stride), 1)

    for dm in depthmaps:
        depth = dm["depth"]
        valid = np.isfinite(depth) & (depth > 0)
        if not np.any(valid):
            continue
        depth_limit = float(np.nanquantile(depth[valid], max_depth_quantile))
        valid &= depth <= depth_limit
        ys, xs = np.where(valid)
        if len(xs) == 0:
            continue
        xs = xs[::stride]
        ys = ys[::stride]
        sampled_depth = depth[ys, xs]

        camera = dm["camera"]
        k = camera_matrix(camera)
        inv_fx = 1.0 / k[0, 0]
        inv_fy = 1.0 / k[1, 1]
        scale_x = float(camera["width"]) / float(dm["depth_width"])
        scale_y = float(camera["height"]) / float(dm["depth_height"])
        u = xs.astype(float) * scale_x
        v = ys.astype(float) * scale_y
        x_norm = (u - k[0, 2]) * inv_fx
        y_norm = (v - k[1, 2]) * inv_fy

        rot = Rotation.from_rotvec(np.asarray(dm["shot"]["rotation"], dtype=float)).as_matrix()
        trans = np.asarray(dm["shot"]["translation"], dtype=float)
        cam_center_sfm = -rot.T @ trans
        cam_center_metric = sfm_to_metric(cam_center_sfm[None, :], scale_sfm_to_metric, sfm_center, metric_center)[0]

        for xn, yn, z_depth in zip(x_norm, y_norm, sampled_depth):
            hit_cam = np.asarray([xn * z_depth, yn * z_depth, z_depth], dtype=float)
            hit_sfm = rot.T @ (hit_cam - trans)
            hit_metric = sfm_to_metric(hit_sfm[None, :], scale_sfm_to_metric, sfm_center, metric_center)[0]
            vec = hit_metric - cam_center_metric
            ray_len = float(np.linalg.norm(vec))
            if not np.isfinite(ray_len) or ray_len <= grid_step_m:
                continue
            direction = vec / ray_len
            start = max(0.0, ray_len - float(z_depth) * scale_sfm_to_metric)
            # Start near the volume entry if the camera is outside the metric grid.
            sample_count = int(np.ceil(ray_len / step))
            if sample_count <= 1:
                continue
            rays_integrated += 1
            for i in range(sample_count + 1):
                distance = min(ray_len, start + i * step)
                point = cam_center_metric + direction * distance
                idx3 = np.floor((point - grid_origin) / grid_step_m).astype(np.int32)
                if np.any(idx3 < 0) or np.any(idx3 >= dims):
                    continue
                flat = int((idx3[0] * dims[1] + idx3[1]) * dims[2] + idx3[2])
                visible[flat] = True
                signed = ray_len - distance
                if signed > truncation_m:
                    value = 1.0
                    weight = free_space_weight
                    free_space_voxels.add(flat)
                elif signed >= -truncation_m:
                    value = float(np.clip(signed / truncation_m, -1.0, 1.0))
                    weight = surface_weight
                    surface_voxels.add(flat)
                else:
                    continue
                tsdf_sum[flat] += value * weight
                weight_sum[flat] += weight

    tsdf_update = np.ones(total, dtype=np.float64)
    known = weight_sum > 0
    tsdf_update[known] = tsdf_sum[known] / weight_sum[known]
    return RayIntegrationResult(
        tsdf_update=tsdf_update,
        weights=weight_sum,
        visibility_mask=visible,
        free_space_voxels=len(free_space_voxels),
        surface_voxels=len(surface_voxels),
        rays_integrated=rays_integrated,
    )


def merge_tsdf_with_ray_update(
    base_tsdf: np.ndarray,
    base_weights: np.ndarray,
    ray_update: RayIntegrationResult,
    ray_weight_scale: float = 1.0,
) -> tuple[np.ndarray, np.ndarray]:
    """Merge without overwriting the base TSDF."""
    base_tsdf_flat = base_tsdf.reshape(-1)
    base_weights_flat = base_weights.reshape(-1)
    ray_weights = ray_update.weights * float(ray_weight_scale)
    total_weights = base_weights_flat + ray_weights
    merged = np.ones_like(base_tsdf_flat, dtype=np.float64)
    known = total_weights > 0
    merged[known] = (
        base_tsdf_flat[known] * base_weights_flat[known]
        + ray_update.tsdf_update[known] * ray_weights[known]
    ) / total_weights[known]
    return merged, total_weights
