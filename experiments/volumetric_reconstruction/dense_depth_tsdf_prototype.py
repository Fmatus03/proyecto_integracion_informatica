from __future__ import annotations

import json
import math
import os
import struct
from collections import Counter, defaultdict, deque
from pathlib import Path

import numpy as np
import open3d as o3d
from scipy import ndimage
from scipy.spatial.transform import Rotation

from ray_integration import integrate_free_space_rays, merge_tsdf_with_ray_update
from sccr_camera_refinement import refine_cameras_self_consistent
from validation_alignment_layer import validate_and_align_depthmaps

from experiments.cloud_unification.cloud_provider_adapter import load_dataset_cloud_source


ROOT = Path(os.environ.get("DENSE_TSDF_ROOT") or Path.cwd())
NODEODM_ROOT = Path(os.environ.get("NODEODM_ROOT") or "/nodeodm-data")
OUT = Path(os.environ.get("DENSE_TSDF_OUT") or Path(__file__).resolve().parent / "dense_depth_tsdf_outputs")
GRID_STEP_M = float(os.environ.get("DENSE_TSDF_GRID_STEP_M") or "0.35")
TRUNCATION_M = float(os.environ.get("DENSE_TSDF_TRUNCATION_M") or str(GRID_STEP_M * 4.0))
MAX_DEPTHMAPS = int(os.environ.get("DENSE_TSDF_MAX_DEPTHMAPS") or "12")
DEPTH_STRIDE = int(os.environ.get("DENSE_TSDF_DEPTH_STRIDE") or "8")
MIN_WEIGHT = float(os.environ.get("DENSE_TSDF_MIN_WEIGHT") or "2.0")
ENABLE_RAY_CARVING = os.environ.get("DENSE_TSDF_ENABLE_RAY_CARVING", "0") == "1"
RAY_PIXEL_STRIDE = int(os.environ.get("DENSE_TSDF_RAY_PIXEL_STRIDE") or "18")
RAY_WEIGHT_SCALE = float(os.environ.get("DENSE_TSDF_RAY_WEIGHT_SCALE") or "1.0")
ENABLE_ALIGNMENT_LAYER = os.environ.get("DENSE_TSDF_ENABLE_ALIGNMENT_LAYER", "0") == "1"
ALIGNMENT_MIN_COVERAGE = float(os.environ.get("DENSE_TSDF_ALIGNMENT_MIN_COVERAGE") or "0.02")
ALIGNMENT_MAX_ERROR_M = float(os.environ.get("DENSE_TSDF_ALIGNMENT_MAX_ERROR_M") or "2.5")
ENABLE_SCCR_LAYER = os.environ.get("DENSE_TSDF_ENABLE_SCCR_LAYER", os.environ.get("DENSE_TSDF_ENABLE_SCCR", "0")) == "1"
SCCR_ITERATIONS = int(os.environ.get("DENSE_TSDF_SCCR_ITERATIONS") or "2")
SCCR_SAMPLE_STRIDE = int(os.environ.get("DENSE_TSDF_SCCR_SAMPLE_STRIDE") or "16")
SCCR_TRANSLATION_STEP_M = float(os.environ.get("DENSE_TSDF_SCCR_TRANSLATION_STEP_M") or "0.08")
SCCR_ROTATION_STEP_DEG = float(os.environ.get("DENSE_TSDF_SCCR_ROTATION_STEP_DEG") or "0.35")
SCCR_MIN_SCORE = float(os.environ.get("DENSE_TSDF_SCCR_MIN_SCORE") or "0.35")
SCCR_REJECT_SCORE = float(os.environ.get("DENSE_TSDF_SCCR_REJECT_SCORE") or "0.12")

DATASETS = {
    "set1": {
        "task": "56396d01-c139-445e-ba50-55644781e877",
        "processed_cloud": load_dataset_cloud_source("set1").path,
        "poisson": ROOT / "data/processed/a3c36266-f866-402f-8bc8-1c2b59b4a4ce/surface_closure_diagnostics/poisson_raw.ply",
        "voxel": ROOT / "data/volumetric_reconstruction_outputs/set1/voxel_solid_surface.ply",
        "point_sdf": ROOT / "data/tsdf_sdf_outputs/set1/sdf_marching_tetrahedra_mesh.ply",
        "pseudo_tsdf": ROOT / "data/camera_tsdf_outputs/set1/camera_ray_tsdf_mesh.ply",
    },
    "set2": {
        "task": "002ca5e3-6eca-4aba-b3e2-623f97878136",
        "processed_cloud": load_dataset_cloud_source("set2").path,
        "poisson": ROOT / "data/processed/b6b04af0-122f-4fcc-af8a-cc553ca5e28d/surface_closure_diagnostics_2/poisson_raw.ply",
        "voxel": ROOT / "data/volumetric_reconstruction_outputs/set2/voxel_solid_surface.ply",
        "point_sdf": ROOT / "data/tsdf_sdf_outputs/set2/sdf_marching_tetrahedra_mesh.ply",
        "pseudo_tsdf": ROOT / "data/camera_tsdf_outputs/set2/camera_ray_tsdf_mesh.ply",
    },
}

TETS = np.asarray([[0, 5, 1, 6], [0, 1, 2, 6], [0, 2, 3, 6], [0, 3, 7, 6], [0, 7, 4, 6], [0, 4, 5, 6]], dtype=np.int32)
CUBE_CORNERS = np.asarray([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0], [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1]], dtype=np.int32)


def _read_dmap(path: Path) -> dict:
    data = path.read_bytes()
    if data[:2] != b"DR":
        raise ValueError(f"Unsupported dmap magic: {path}")
    width, height, depth_width, depth_height = struct.unpack("<4I", data[4:20])
    depth_min, depth_max = struct.unpack("<2f", data[20:28])
    name_len = struct.unpack("<H", data[28:30])[0]
    image_name = data[30:30 + name_len].decode("utf-8", errors="replace")
    payload_offset = 30 + name_len + 196
    pixel_count = int(depth_width * depth_height)
    payload = np.frombuffer(data, dtype="<f4", offset=payload_offset, count=pixel_count * 5).reshape(pixel_count, 5)
    depth = payload[:, 0].reshape((depth_height, depth_width))
    depth = np.where(np.isfinite(depth) & (depth > 0) & (depth >= depth_min) & (depth <= depth_max), depth, np.nan)
    return {
        "path": str(path),
        "image_name": Path(image_name).name,
        "width": int(width),
        "height": int(height),
        "depth_width": int(depth_width),
        "depth_height": int(depth_height),
        "depth_min": float(depth_min),
        "depth_max": float(depth_max),
        "depth": depth,
        "valid_ratio": float(np.count_nonzero(np.isfinite(depth)) / depth.size),
    }


def _edge_counts(mesh: o3d.geometry.TriangleMesh) -> Counter:
    faces = np.asarray(mesh.triangles, dtype=np.int64)
    if len(faces) == 0:
        return Counter()
    edges = np.sort(np.vstack((faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]])), axis=1)
    return Counter(map(tuple, edges.tolist()))


def _component_count(mesh: o3d.geometry.TriangleMesh) -> int:
    faces = np.asarray(mesh.triangles, dtype=np.int64)
    if len(faces) == 0:
        return 0
    edge_to_faces: dict[tuple[int, int], list[int]] = defaultdict(list)
    for face_id, face in enumerate(faces):
        for a, b in ((face[0], face[1]), (face[1], face[2]), (face[2], face[0])):
            edge_to_faces[tuple(sorted((int(a), int(b))))].append(face_id)
    graph: list[list[int]] = [[] for _ in range(len(faces))]
    for face_ids in edge_to_faces.values():
        for face_id in face_ids:
            graph[face_id].extend(other for other in face_ids if other != face_id)
    seen = np.zeros(len(faces), dtype=bool)
    components = 0
    for start in range(len(faces)):
        if seen[start]:
            continue
        components += 1
        queue: deque[int] = deque([start])
        seen[start] = True
        while queue:
            current = queue.popleft()
            for nxt in graph[current]:
                if not seen[nxt]:
                    seen[nxt] = True
                    queue.append(nxt)
    return components


def _distance_metrics(mesh: o3d.geometry.TriangleMesh, reference: o3d.geometry.TriangleMesh) -> dict:
    if len(mesh.triangles) == 0 or len(reference.triangles) == 0:
        return {"hausdorff_approx": None, "chamfer_approx": None}
    count = 2500
    a = np.asarray(mesh.sample_points_uniformly(number_of_points=count).points)
    b = np.asarray(reference.sample_points_uniformly(number_of_points=count).points)
    tree_a = o3d.geometry.KDTreeFlann(o3d.geometry.PointCloud(o3d.utility.Vector3dVector(a)))
    tree_b = o3d.geometry.KDTreeFlann(o3d.geometry.PointCloud(o3d.utility.Vector3dVector(b)))
    da = np.zeros(count, dtype=float)
    db = np.zeros(count, dtype=float)
    for i, point in enumerate(a):
        _, _, sq = tree_b.search_knn_vector_3d(point, 1)
        da[i] = math.sqrt(float(sq[0]))
    for i, point in enumerate(b):
        _, _, sq = tree_a.search_knn_vector_3d(point, 1)
        db[i] = math.sqrt(float(sq[0]))
    return {"hausdorff_approx": round(float(max(da.max(), db.max())), 6), "chamfer_approx": round(float(da.mean() + db.mean()), 6)}


def _mesh_metrics(mesh: o3d.geometry.TriangleMesh, reference: o3d.geometry.TriangleMesh | None = None) -> dict:
    edges = _edge_counts(mesh)
    bbox = mesh.get_axis_aligned_bounding_box()
    extent = np.asarray(bbox.get_extent(), dtype=float)
    area = float(mesh.get_surface_area()) if len(mesh.triangles) else 0.0
    watertight = bool(mesh.is_watertight()) if len(mesh.triangles) else False
    volume = float(mesh.get_volume()) if watertight else None
    result = {
        "vertices": int(len(mesh.vertices)),
        "triangles": int(len(mesh.triangles)),
        "boundary_edges": int(sum(1 for c in edges.values() if c == 1)),
        "non_manifold_edges": int(sum(1 for c in edges.values() if c > 2)),
        "non_manifold_vertices": int(len(mesh.get_non_manifold_vertices())) if len(mesh.vertices) else 0,
        "orientable": bool(mesh.is_orientable()) if len(mesh.triangles) else False,
        "watertight": watertight,
        "bbox_extent": [round(float(v), 6) for v in extent.tolist()],
        "area": round(area, 6),
        "volume": None if volume is None or math.isnan(volume) else round(volume, 6),
        "components_connected": _component_count(mesh),
    }
    if reference is not None and len(reference.triangles):
        ref_extent = np.asarray(reference.get_axis_aligned_bounding_box().get_extent(), dtype=float)
        ref_diag = float(np.linalg.norm(ref_extent)) or 1.0
        ref_area = float(reference.get_surface_area())
        result["bbox_drift_vs_poisson"] = round(float(np.linalg.norm(extent - ref_extent) / ref_diag), 8)
        result["area_drift_vs_poisson_pct"] = round(((area - ref_area) / ref_area) * 100.0, 6) if ref_area else None
        result.update(_distance_metrics(mesh, reference))
    return result


def _camera_matrix(camera: dict) -> np.ndarray:
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


def _project(points_world: np.ndarray, rotation_vec: list[float], translation: list[float], camera: dict) -> tuple[np.ndarray, np.ndarray]:
    r = Rotation.from_rotvec(np.asarray(rotation_vec, dtype=float)).as_matrix()
    t = np.asarray(translation, dtype=float)
    cam = (r @ points_world.T).T + t
    z = cam[:, 2]
    k = _camera_matrix(camera)
    u = k[0, 0] * (cam[:, 0] / z) + k[0, 2]
    v = k[1, 1] * (cam[:, 1] / z) + k[1, 2]
    return np.column_stack((u, v)), z


def _load_sfm(task: str) -> dict:
    recon = json.loads((NODEODM_ROOT / task / "opensfm/reconstruction.json").read_text(encoding="utf-8"))[0]
    points = np.asarray([p["coordinates"] for p in recon["points"].values()], dtype=float)
    return {"reconstruction": recon, "points": points}


def _robust_alignment(sfm_points: np.ndarray, processed_points: np.ndarray) -> tuple[float, np.ndarray, np.ndarray, np.ndarray]:
    finite = sfm_points[np.all(np.isfinite(sfm_points), axis=1)]
    lo, hi = np.percentile(finite, [2.0, 98.0], axis=0)
    robust = finite[np.all((finite >= lo) & (finite <= hi), axis=1)]
    sfm_center = np.median(robust, axis=0)
    proc_center = np.median(processed_points, axis=0)
    sfm_extent = np.percentile(robust, 95, axis=0) - np.percentile(robust, 5, axis=0)
    proc_extent = np.percentile(processed_points, 95, axis=0) - np.percentile(processed_points, 5, axis=0)
    ratios = proc_extent[np.where(sfm_extent > 1e-9)] / sfm_extent[np.where(sfm_extent > 1e-9)]
    scale = float(np.median(ratios[np.isfinite(ratios)])) if ratios.size else 1.0
    return scale, sfm_center, proc_center, robust


def _select_depthmaps(task: str, recon: dict) -> list[dict]:
    depth_dir = NODEODM_ROOT / task / "opensfm/undistorted/openmvs/depthmaps"
    maps = []
    for path in sorted(depth_dir.glob("depth*.dmap")):
        try:
            dm = _read_dmap(path)
        except Exception:
            continue
        stem = dm["image_name"]
        if stem.lower().endswith(".tif"):
            stem = stem[:-4]
        elif stem.lower().endswith(".tiff"):
            stem = stem[:-5]
        shot = recon["shots"].get(stem)
        if shot is None:
            continue
        dm["shot_id"] = stem
        dm["shot"] = shot
        dm["camera"] = recon["cameras"][shot["camera"]]
        maps.append(dm)
    maps.sort(key=lambda item: item["valid_ratio"], reverse=True)
    return maps[:MAX_DEPTHMAPS]


def _build_grid(processed_points: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    padding = 1.5
    origin = processed_points.min(axis=0) - padding
    max_bound = processed_points.max(axis=0) + padding
    dims = np.ceil((max_bound - origin) / GRID_STEP_M).astype(int) + 1
    axes = [origin[i] + np.arange(dims[i], dtype=float) * GRID_STEP_M for i in range(3)]
    xx, yy, zz = np.meshgrid(axes[0], axes[1], axes[2], indexing="ij")
    return origin, dims, np.column_stack((xx.ravel(), yy.ravel(), zz.ravel()))


def _sample_depth(depth: np.ndarray, uv: np.ndarray, camera: dict, dm: dict) -> np.ndarray:
    scale_x = dm["depth_width"] / float(camera["width"])
    scale_y = dm["depth_height"] / float(camera["height"])
    x = np.rint(uv[:, 0] * scale_x).astype(int)
    y = np.rint(uv[:, 1] * scale_y).astype(int)
    valid = (x >= 0) & (x < dm["depth_width"]) & (y >= 0) & (y < dm["depth_height"])
    sampled = np.full(len(uv), np.nan, dtype=float)
    sampled[valid] = depth[y[valid], x[valid]]
    return sampled


def _integrate_dense_tsdf(grid_metric: np.ndarray, grid_sfm: np.ndarray, depthmaps: list[dict]) -> tuple[np.ndarray, np.ndarray]:
    tsdf_sum = np.zeros(len(grid_metric), dtype=np.float64)
    weight_sum = np.zeros(len(grid_metric), dtype=np.float64)
    for dm in depthmaps:
        uv, z = _project(grid_sfm, dm["shot"]["rotation"], dm["shot"]["translation"], dm["camera"])
        w, h = float(dm["camera"]["width"]), float(dm["camera"]["height"])
        visible = (z > 0) & (uv[:, 0] >= 0) & (uv[:, 0] < w) & (uv[:, 1] >= 0) & (uv[:, 1] < h)
        idx_all = np.where(visible)[0]
        if not len(idx_all):
            continue
        sampled = _sample_depth(dm["depth"], uv[idx_all], dm["camera"], dm)
        valid_depth = np.isfinite(sampled)
        idx = idx_all[valid_depth]
        if not len(idx):
            continue
        signed = sampled[valid_depth] - z[idx]
        band = signed >= -TRUNCATION_M
        idx = idx[band]
        signed = signed[band]
        if not len(idx):
            continue
        tsdf = np.clip(signed / TRUNCATION_M, -1.0, 1.0)
        # Weight decays behind the observed surface and can be attenuated by
        # the optional validation/alignment layer on a per-frame basis.
        frame_weight = float(dm.get("alignment_weight_multiplier", 1.0))
        weights = (1.0 / (1.0 + np.abs(signed) / TRUNCATION_M)) * frame_weight
        tsdf_sum[idx] += tsdf * weights
        weight_sum[idx] += weights
    fused = np.ones(len(grid_metric), dtype=np.float64)
    known = weight_sum >= MIN_WEIGHT
    fused[known] = tsdf_sum[known] / weight_sum[known]
    return fused, weight_sum


def _close_unknown_volume(tsdf: np.ndarray, weights: np.ndarray, dims: np.ndarray) -> np.ndarray:
    values = tsdf.reshape(tuple(dims.tolist())).copy()
    known_inside = (values < 0) & (weights.reshape(tuple(dims.tolist())) >= MIN_WEIGHT)
    structure = ndimage.generate_binary_structure(3, 2)
    labels, count = ndimage.label(known_inside, structure=structure)
    if count > 1:
        sizes = np.bincount(labels.ravel())
        sizes[0] = 0
        known_inside = labels == int(np.argmax(sizes))
    filled = ndimage.binary_fill_holes(ndimage.binary_closing(known_inside, structure=structure, iterations=1))
    values[filled & ~known_inside] = -0.05
    values[~filled & (weights.reshape(tuple(dims.tolist())) < MIN_WEIGHT)] = 1.0
    return values.ravel()


def _interp(p0: np.ndarray, p1: np.ndarray, v0: float, v1: float) -> np.ndarray:
    denom = v0 - v1
    t = 0.5 if abs(denom) < 1e-12 else v0 / denom
    return p0 + np.clip(t, 0.0, 1.0) * (p1 - p0)


def _polygonise_tet(points: np.ndarray, values: np.ndarray) -> list[list[np.ndarray]]:
    inside = values < 0.0
    ins = np.where(inside)[0].tolist()
    outs = np.where(~inside)[0].tolist()
    if len(ins) == 0 or len(ins) == 4:
        return []
    if len(ins) == 1:
        i = ins[0]
        return [[_interp(points[i], points[o], values[i], values[o]) for o in outs]]
    if len(ins) == 3:
        o = outs[0]
        verts = [_interp(points[i], points[o], values[i], values[o]) for i in ins]
        return [[verts[0], verts[2], verts[1]]]
    i0, i1 = ins
    o0, o1 = outs
    p0 = _interp(points[i0], points[o0], values[i0], values[o0])
    p1 = _interp(points[i0], points[o1], values[i0], values[o1])
    p2 = _interp(points[i1], points[o0], values[i1], values[o0])
    p3 = _interp(points[i1], points[o1], values[i1], values[o1])
    return [[p0, p1, p2], [p1, p3, p2]]


def _marching_tetrahedra(values_flat: np.ndarray, origin: np.ndarray, dims: np.ndarray) -> o3d.geometry.TriangleMesh:
    values = values_flat.reshape(tuple(dims.tolist()))
    vertices: list[np.ndarray] = []
    triangles: list[tuple[int, int, int]] = []
    vertex_map: dict[tuple[int, int, int], int] = {}

    def add_vertex(point: np.ndarray) -> int:
        key = tuple(np.round(point / (GRID_STEP_M * 1e-5)).astype(int).tolist())
        if key not in vertex_map:
            vertex_map[key] = len(vertices)
            vertices.append(point)
        return vertex_map[key]

    for ix in range(int(dims[0] - 1)):
        for iy in range(int(dims[1] - 1)):
            for iz in range(int(dims[2] - 1)):
                base = np.asarray([ix, iy, iz], dtype=np.int32)
                corner_idx = CUBE_CORNERS + base
                vals = np.asarray([values[tuple(idx)] for idx in corner_idx], dtype=float)
                if np.all(vals >= 0.0) or np.all(vals < 0.0):
                    continue
                coords = origin + corner_idx.astype(float) * GRID_STEP_M
                for tet in TETS:
                    for tri in _polygonise_tet(coords[tet], vals[tet]):
                        ids = tuple(add_vertex(p) for p in tri)
                        if len(set(ids)) == 3:
                            triangles.append(ids)
    if not vertices or not triangles:
        return o3d.geometry.TriangleMesh()
    mesh = o3d.geometry.TriangleMesh(
        o3d.utility.Vector3dVector(np.asarray(vertices, dtype=float)),
        o3d.utility.Vector3iVector(np.asarray(triangles, dtype=np.int32)),
    )
    mesh.remove_duplicated_vertices()
    mesh.remove_degenerate_triangles()
    mesh.remove_unreferenced_vertices()
    mesh.orient_triangles()
    mesh.compute_vertex_normals()
    return mesh


def run_dataset(name: str, cfg: dict) -> dict:
    sfm = _load_sfm(cfg["task"])
    processed_cloud = o3d.io.read_point_cloud(str(cfg["processed_cloud"]))
    processed_points = np.asarray(processed_cloud.points, dtype=float)
    scale, sfm_center, proc_center, robust_sfm_points = _robust_alignment(sfm["points"], processed_points)
    origin, dims, grid_metric = _build_grid(processed_points)
    depthmaps = _select_depthmaps(cfg["task"], sfm["reconstruction"])
    alignment_report = {"enabled": False}
    if ENABLE_ALIGNMENT_LAYER:
        alignment = validate_and_align_depthmaps(
            depthmaps=depthmaps,
            sfm_points=robust_sfm_points,
            processed_points_metric=processed_points,
            scale_sfm_to_metric=scale,
            sfm_center=sfm_center,
            metric_center=proc_center,
            grid_origin=origin,
            grid_dims=dims,
            grid_step_m=GRID_STEP_M,
            min_coverage_ratio=ALIGNMENT_MIN_COVERAGE,
            max_reprojection_error_m=ALIGNMENT_MAX_ERROR_M,
        )
        depthmaps = alignment.depthmaps
        scale *= alignment.scale_correction
        proc_center = proc_center + alignment.offset_correction
        alignment_report = {
            "enabled": True,
            "min_coverage_ratio": ALIGNMENT_MIN_COVERAGE,
            "max_reprojection_error_m": ALIGNMENT_MAX_ERROR_M,
            "drift_report": alignment.drift_report,
            "accepted_frames": alignment.accepted_frames,
            "rejected_frames": alignment.rejected_frames,
            "camera_metrics": alignment.camera_metrics,
        }
    grid_sfm = (grid_metric - proc_center) / scale + sfm_center
    fused_tsdf, weights = _integrate_dense_tsdf(grid_metric, grid_sfm, depthmaps)
    closed_tsdf = _close_unknown_volume(fused_tsdf, weights, dims)
    known = weights >= MIN_WEIGHT
    raw_diag = {
        "known_voxels": int(np.count_nonzero(known)),
        "known_negative_voxels": int(np.count_nonzero((fused_tsdf < 0) & known)),
        "known_positive_voxels": int(np.count_nonzero((fused_tsdf >= 0) & known)),
        "closed_negative_voxels": int(np.count_nonzero(closed_tsdf < 0)),
        "closed_positive_voxels": int(np.count_nonzero(closed_tsdf >= 0)),
        "raw_tsdf_min": round(float(np.min(fused_tsdf[known])), 6) if np.any(known) else None,
        "raw_tsdf_max": round(float(np.max(fused_tsdf[known])), 6) if np.any(known) else None,
    }
    mesh = _marching_tetrahedra(closed_tsdf, origin, dims)
    coarse_fused_tsdf = fused_tsdf.copy()
    coarse_weights = weights.copy()
    coarse_closed_tsdf = closed_tsdf.copy()
    coarse_mesh = mesh
    coarse_raw_diag = dict(raw_diag)
    coarse_known_voxel_ratio = round(float(np.count_nonzero(coarse_weights >= MIN_WEIGHT) / len(coarse_weights)), 6)

    sccr_report = {"enabled": False}
    if ENABLE_SCCR_LAYER:
        sccr = refine_cameras_self_consistent(
            depthmaps=depthmaps,
            tsdf=coarse_fused_tsdf,
            weights=coarse_weights,
            grid_origin=origin,
            grid_dims=dims,
            grid_step_m=GRID_STEP_M,
            truncation_m=TRUNCATION_M,
            scale_sfm_to_metric=scale,
            sfm_center=sfm_center,
            metric_center=proc_center,
            min_weight=MIN_WEIGHT,
            iterations=SCCR_ITERATIONS,
            sample_stride=SCCR_SAMPLE_STRIDE,
            translation_step_m=SCCR_TRANSLATION_STEP_M,
            rotation_step_deg=SCCR_ROTATION_STEP_DEG,
            min_score=SCCR_MIN_SCORE,
            reject_score=SCCR_REJECT_SCORE,
        )
        sccr_report = {
            "enabled": True,
            "refinement_report": sccr.refinement_report,
            "camera_metrics_before": sccr.camera_metrics_before,
            "camera_metrics_after": sccr.camera_metrics_after,
            "accepted_frames": sccr.accepted_frames,
            "rejected_frames": sccr.rejected_frames,
            "coarse_known_voxel_ratio": coarse_known_voxel_ratio,
            "coarse_tsdf_diagnostics": coarse_raw_diag,
        }
        if sccr.depthmaps:
            depthmaps = sccr.depthmaps
            fused_tsdf, weights = _integrate_dense_tsdf(grid_metric, grid_sfm, depthmaps)
            closed_tsdf = _close_unknown_volume(fused_tsdf, weights, dims)
            known = weights >= MIN_WEIGHT
            raw_diag = {
                "known_voxels": int(np.count_nonzero(known)),
                "known_negative_voxels": int(np.count_nonzero((fused_tsdf < 0) & known)),
                "known_positive_voxels": int(np.count_nonzero((fused_tsdf >= 0) & known)),
                "closed_negative_voxels": int(np.count_nonzero(closed_tsdf < 0)),
                "closed_positive_voxels": int(np.count_nonzero(closed_tsdf >= 0)),
                "raw_tsdf_min": round(float(np.min(fused_tsdf[known])), 6) if np.any(known) else None,
                "raw_tsdf_max": round(float(np.max(fused_tsdf[known])), 6) if np.any(known) else None,
            }
            mesh = _marching_tetrahedra(closed_tsdf, origin, dims)
        else:
            sccr_report["fallback_reason"] = "all_frames_rejected; coarse TSDF retained"

    ray_report = None
    refined_tsdf = None
    refined_weights = None
    refined_mesh = None
    if ENABLE_RAY_CARVING:
        ray_update = integrate_free_space_rays(
            depthmaps=depthmaps,
            grid_origin=origin,
            grid_dims=dims,
            grid_step_m=GRID_STEP_M,
            truncation_m=TRUNCATION_M,
            scale_sfm_to_metric=scale,
            sfm_center=sfm_center,
            metric_center=proc_center,
            pixel_stride=RAY_PIXEL_STRIDE,
        )
        refined_tsdf_raw, refined_weights = merge_tsdf_with_ray_update(
            fused_tsdf,
            weights,
            ray_update,
            ray_weight_scale=RAY_WEIGHT_SCALE,
        )
        refined_tsdf = _close_unknown_volume(refined_tsdf_raw, refined_weights, dims)
        refined_mesh = _marching_tetrahedra(refined_tsdf, origin, dims)
        ray_report = {
            "enabled": True,
            "pixel_stride": RAY_PIXEL_STRIDE,
            "ray_weight_scale": RAY_WEIGHT_SCALE,
            "rays_integrated": ray_update.rays_integrated,
            "free_space_voxels": ray_update.free_space_voxels,
            "surface_voxels": ray_update.surface_voxels,
            "visibility_voxels": int(np.count_nonzero(ray_update.visibility_mask)),
            "ray_known_voxel_ratio": round(float(np.count_nonzero(ray_update.weights > 0) / len(ray_update.weights)), 6),
            "refined_known_voxel_ratio": round(float(np.count_nonzero(refined_weights >= MIN_WEIGHT) / len(refined_weights)), 6),
        }
    else:
        ray_report = {"enabled": False}

    out_dir = OUT / name
    out_dir.mkdir(parents=True, exist_ok=True)
    grid_path = out_dir / "dense_depth_tsdf_grid.npz"
    mesh_path = out_dir / "dense_depth_tsdf_mesh.ply"
    refined_grid_path = out_dir / "ray_refined_tsdf_grid.npz"
    refined_mesh_path = out_dir / "ray_refined_tsdf_mesh.ply"
    np.savez_compressed(grid_path, tsdf=closed_tsdf.reshape(tuple(dims.tolist())), raw_tsdf=fused_tsdf.reshape(tuple(dims.tolist())), weights=weights.reshape(tuple(dims.tolist())), origin=origin, grid_step_m=GRID_STEP_M, truncation_m=TRUNCATION_M)
    o3d.io.write_triangle_mesh(str(mesh_path), mesh, write_ascii=False, compressed=False)
    if refined_tsdf is not None and refined_mesh is not None and refined_weights is not None:
        np.savez_compressed(refined_grid_path, tsdf=refined_tsdf.reshape(tuple(dims.tolist())), weights=refined_weights.reshape(tuple(dims.tolist())), origin=origin, grid_step_m=GRID_STEP_M, truncation_m=TRUNCATION_M)
        o3d.io.write_triangle_mesh(str(refined_mesh_path), refined_mesh, write_ascii=False, compressed=False)

    poisson = o3d.io.read_triangle_mesh(str(cfg["poisson"]))
    return {
        "task_uuid": cfg["task"],
        "alignment": {
            "scale_sfm_to_metric": scale,
            "sfm_center": [round(float(v), 6) for v in sfm_center.tolist()],
            "metric_center": [round(float(v), 6) for v in proc_center.tolist()],
        },
        "depthmaps_used": [{"file": Path(dm["path"]).name, "shot_id": dm["shot_id"], "valid_ratio": round(dm["valid_ratio"], 6), "depth_size": [dm["depth_width"], dm["depth_height"]], "sccr_camera_score": round(float(dm["sccr_camera_score"]), 6) if "sccr_camera_score" in dm else None} for dm in depthmaps],
        "validation_alignment": alignment_report,
        "sccr_camera_refinement": sccr_report,
        "grid_shape": [int(v) for v in dims.tolist()],
        "grid_step_m": GRID_STEP_M,
        "truncation_m": TRUNCATION_M,
        "known_voxel_ratio": round(float(np.count_nonzero(weights >= MIN_WEIGHT) / len(weights)), 6),
        "tsdf_diagnostics": raw_diag,
        "tsdf_grid": str(grid_path),
        "dense_depth_tsdf_mesh": str(mesh_path),
        "ray_integration": ray_report,
        "ray_refined_tsdf_grid": str(refined_grid_path) if refined_tsdf is not None else None,
        "ray_refined_tsdf_mesh": str(refined_mesh_path) if refined_mesh is not None else None,
        "poisson_metrics": _mesh_metrics(poisson),
        "voxel_metrics": _mesh_metrics(o3d.io.read_triangle_mesh(str(cfg["voxel"])), poisson),
        "point_sdf_metrics": _mesh_metrics(o3d.io.read_triangle_mesh(str(cfg["point_sdf"])), poisson),
        "pseudo_depth_camera_tsdf_metrics": _mesh_metrics(o3d.io.read_triangle_mesh(str(cfg["pseudo_tsdf"])), poisson),
        "sccr_coarse_dense_depth_tsdf_metrics": _mesh_metrics(coarse_mesh, poisson) if ENABLE_SCCR_LAYER else None,
        "dense_depth_tsdf_metrics": _mesh_metrics(mesh, poisson),
        "ray_refined_dense_depth_tsdf_metrics": _mesh_metrics(refined_mesh, poisson) if refined_mesh is not None else None,
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    report = {
        "method": "dense-depth camera TSDF from OpenMVS .dmap depth maps and OpenSfM poses",
        "not_pipeline_integration": True,
        "depth_source": "OpenMVS .dmap dense depth maps; first float32 channel used as per-pixel depth",
        "dmap_reader": "DR header, image path, 196-byte camera metadata block, 5 float32 channels per pixel",
        "ray_integration_layer_enabled": ENABLE_RAY_CARVING,
        "validation_alignment_layer_enabled": ENABLE_ALIGNMENT_LAYER,
        "sccr_camera_refinement_layer_enabled": ENABLE_SCCR_LAYER,
        "datasets": {name: run_dataset(name, cfg) for name, cfg in DATASETS.items()},
    }
    path = OUT / "dense_depth_tsdf_results.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
