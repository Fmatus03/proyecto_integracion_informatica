from __future__ import annotations

import json
import math
import os
from collections import Counter, defaultdict, deque
from pathlib import Path

import numpy as np
import open3d as o3d
from scipy.spatial import cKDTree
from scipy.spatial.transform import Rotation

from experiments.cloud_unification.cloud_provider_adapter import load_dataset_cloud_source


ROOT = Path(os.environ.get("CAMERA_TSDF_ROOT") or Path.cwd())
NODEODM_ROOT = Path(os.environ.get("NODEODM_ROOT") or "/nodeodm-data")
OUT = Path(os.environ.get("CAMERA_TSDF_OUT") or Path(__file__).resolve().parent / "camera_tsdf_outputs")
GRID_STEP_M = float(os.environ.get("CAMERA_TSDF_GRID_STEP_M") or "0.35")
TRUNCATION_M = float(os.environ.get("CAMERA_TSDF_TRUNCATION_M") or str(GRID_STEP_M * 4.0))
MAX_CAMERAS = int(os.environ.get("CAMERA_TSDF_MAX_CAMERAS") or "10")
PROJECTION_RADIUS_PX = float(os.environ.get("CAMERA_TSDF_PROJECTION_RADIUS_PX") or "35")

DATASETS = {
    "set1": {
        "task": "56396d01-c139-445e-ba50-55644781e877",
        "processed_cloud": load_dataset_cloud_source("set1").path,
        "poisson": ROOT / "data/processed/a3c36266-f866-402f-8bc8-1c2b59b4a4ce/surface_closure_diagnostics/poisson_raw.ply",
        "voxel": ROOT / "data/volumetric_reconstruction_outputs/set1/voxel_solid_surface.ply",
        "point_sdf": ROOT / "data/tsdf_sdf_outputs/set1/sdf_marching_tetrahedra_mesh.ply",
    },
    "set2": {
        "task": "002ca5e3-6eca-4aba-b3e2-623f97878136",
        "processed_cloud": load_dataset_cloud_source("set2").path,
        "poisson": ROOT / "data/processed/b6b04af0-122f-4fcc-af8a-cc553ca5e28d/surface_closure_diagnostics_2/poisson_raw.ply",
        "voxel": ROOT / "data/volumetric_reconstruction_outputs/set2/voxel_solid_surface.ply",
        "point_sdf": ROOT / "data/tsdf_sdf_outputs/set2/sdf_marching_tetrahedra_mesh.ply",
    },
}

TETS = np.asarray([[0, 5, 1, 6], [0, 1, 2, 6], [0, 2, 3, 6], [0, 3, 7, 6], [0, 7, 4, 6], [0, 4, 5, 6]], dtype=np.int32)
CUBE_CORNERS = np.asarray([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0], [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1]], dtype=np.int32)


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
    return {
        "hausdorff_approx": round(float(max(da.max(), db.max())), 6),
        "chamfer_approx": round(float(da.mean() + db.mean()), 6),
    }


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


def _load_sfm(task: str) -> dict:
    recon_path = NODEODM_ROOT / task / "opensfm/reconstruction.json"
    recon = json.loads(recon_path.read_text(encoding="utf-8"))[0]
    points = np.asarray([p["coordinates"] for p in recon["points"].values()], dtype=float)
    return {"reconstruction": recon, "points": points}


def _robust_alignment(sfm_points: np.ndarray, processed_points: np.ndarray) -> tuple[float, np.ndarray, np.ndarray, np.ndarray]:
    finite = sfm_points[np.all(np.isfinite(sfm_points), axis=1)]
    lo, hi = np.percentile(finite, [2.0, 98.0], axis=0)
    mask = np.all((finite >= lo) & (finite <= hi), axis=1)
    robust = finite[mask]
    sfm_center = np.median(robust, axis=0)
    proc_center = np.median(processed_points, axis=0)
    sfm_extent = np.percentile(robust, 95, axis=0) - np.percentile(robust, 5, axis=0)
    proc_extent = np.percentile(processed_points, 95, axis=0) - np.percentile(processed_points, 5, axis=0)
    ratios = proc_extent[np.where(sfm_extent > 1e-9)] / sfm_extent[np.where(sfm_extent > 1e-9)]
    scale = float(np.median(ratios[np.isfinite(ratios)])) if ratios.size else 1.0
    return scale, sfm_center, proc_center, robust


def _transform(points: np.ndarray, scale: float, sfm_center: np.ndarray, proc_center: np.ndarray) -> np.ndarray:
    return (points - sfm_center) * scale + proc_center


def _project(points_world: np.ndarray, rotation_vec: list[float], translation: list[float], camera: dict) -> tuple[np.ndarray, np.ndarray]:
    r = Rotation.from_rotvec(np.asarray(rotation_vec, dtype=float)).as_matrix()
    t = np.asarray(translation, dtype=float)
    cam = (r @ points_world.T).T + t
    z = cam[:, 2]
    k = _camera_matrix(camera)
    u = k[0, 0] * (cam[:, 0] / z) + k[0, 2]
    v = k[1, 1] * (cam[:, 1] / z) + k[1, 2]
    return np.column_stack((u, v)), z


def _select_cameras(recon: dict, sfm_points: np.ndarray) -> list[dict]:
    cameras = recon["cameras"]
    selected = []
    for shot_id, shot in recon["shots"].items():
        camera = cameras[shot["camera"]]
        uv, z = _project(sfm_points, shot["rotation"], shot["translation"], camera)
        w, h = float(camera["width"]), float(camera["height"])
        visible = (z > 0) & (uv[:, 0] >= 0) & (uv[:, 0] < w) & (uv[:, 1] >= 0) & (uv[:, 1] < h)
        count = int(np.count_nonzero(visible))
        if count >= 100:
            selected.append({"shot_id": shot_id, "shot": shot, "camera": camera, "visible_points": count})
    selected.sort(key=lambda item: item["visible_points"], reverse=True)
    return selected[:MAX_CAMERAS]


def _build_grid(processed_points: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    padding = 1.5
    origin = processed_points.min(axis=0) - padding
    max_bound = processed_points.max(axis=0) + padding
    dims = np.ceil((max_bound - origin) / GRID_STEP_M).astype(int) + 1
    axes = [origin[i] + np.arange(dims[i], dtype=float) * GRID_STEP_M for i in range(3)]
    xx, yy, zz = np.meshgrid(axes[0], axes[1], axes[2], indexing="ij")
    return origin, np.column_stack((xx.ravel(), yy.ravel(), zz.ravel()))


def _integrate_camera_tsdf(grid_points_metric: np.ndarray, grid_points_sfm: np.ndarray, sfm_points: np.ndarray, selected_cameras: list[dict]) -> tuple[np.ndarray, np.ndarray]:
    tsdf_sum = np.zeros(len(grid_points_metric), dtype=np.float64)
    weight_sum = np.zeros(len(grid_points_metric), dtype=np.float64)
    for item in selected_cameras:
        shot = item["shot"]
        camera = item["camera"]
        uv_pts, z_pts = _project(sfm_points, shot["rotation"], shot["translation"], camera)
        w, h = float(camera["width"]), float(camera["height"])
        valid_pts = (z_pts > 0) & (uv_pts[:, 0] >= 0) & (uv_pts[:, 0] < w) & (uv_pts[:, 1] >= 0) & (uv_pts[:, 1] < h)
        if np.count_nonzero(valid_pts) < 100:
            continue
        tree = cKDTree(uv_pts[valid_pts])
        valid_depths = z_pts[valid_pts]
        uv_grid, z_grid = _project(grid_points_sfm, shot["rotation"], shot["translation"], camera)
        valid_grid = (z_grid > 0) & (uv_grid[:, 0] >= 0) & (uv_grid[:, 0] < w) & (uv_grid[:, 1] >= 0) & (uv_grid[:, 1] < h)
        candidate_idx = np.where(valid_grid)[0]
        if not len(candidate_idx):
            continue
        dist_px, nn = tree.query(uv_grid[candidate_idx], k=1)
        close = dist_px <= PROJECTION_RADIUS_PX
        if not np.any(close):
            continue
        idx = candidate_idx[close]
        observed_depth = valid_depths[nn[close]]
        signed = observed_depth - z_grid[idx]
        # Positive is free space before observed surface; negative is behind observed depth.
        tsdf = np.clip(signed / TRUNCATION_M, -1.0, 1.0)
        near_band = signed >= -TRUNCATION_M
        idx = idx[near_band]
        tsdf = tsdf[near_band]
        weights = 1.0 / (1.0 + dist_px[close][near_band] / PROJECTION_RADIUS_PX)
        tsdf_sum[idx] += tsdf * weights
        weight_sum[idx] += weights
    fused = np.ones(len(grid_points_metric), dtype=np.float64)
    known = weight_sum > 0
    fused[known] = tsdf_sum[known] / weight_sum[known]
    return fused, weight_sum


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
    selected_cameras = _select_cameras(sfm["reconstruction"], robust_sfm_points)
    origin, grid_metric = _build_grid(processed_points)
    dims = np.ceil((processed_points.max(axis=0) + 1.5 - origin) / GRID_STEP_M).astype(int) + 1
    grid_sfm = (grid_metric - proc_center) / scale + sfm_center
    fused_tsdf, weights = _integrate_camera_tsdf(grid_metric, grid_sfm, robust_sfm_points, selected_cameras)
    mesh = _marching_tetrahedra(fused_tsdf, origin, dims)

    out_dir = OUT / name
    out_dir.mkdir(parents=True, exist_ok=True)
    grid_path = out_dir / "camera_ray_tsdf_grid.npz"
    mesh_path = out_dir / "camera_ray_tsdf_mesh.ply"
    np.savez_compressed(grid_path, tsdf=fused_tsdf.reshape(tuple(dims.tolist())), weights=weights.reshape(tuple(dims.tolist())), origin=origin, grid_step_m=GRID_STEP_M, truncation_m=TRUNCATION_M)
    o3d.io.write_triangle_mesh(str(mesh_path), mesh, write_ascii=False, compressed=False)

    poisson = o3d.io.read_triangle_mesh(str(cfg["poisson"]))
    voxel = o3d.io.read_triangle_mesh(str(cfg["voxel"]))
    point_sdf = o3d.io.read_triangle_mesh(str(cfg["point_sdf"]))
    return {
        "task_uuid": cfg["task"],
        "alignment": {
            "scale_sfm_to_metric": scale,
            "sfm_center": [round(float(v), 6) for v in sfm_center.tolist()],
            "metric_center": [round(float(v), 6) for v in proc_center.tolist()],
        },
        "cameras_used": [{"shot_id": c["shot_id"], "visible_points": c["visible_points"]} for c in selected_cameras],
        "grid_shape": [int(v) for v in dims.tolist()],
        "grid_step_m": GRID_STEP_M,
        "truncation_m": TRUNCATION_M,
        "known_voxel_ratio": round(float(np.count_nonzero(weights > 0) / len(weights)), 6),
        "tsdf_grid": str(grid_path),
        "camera_tsdf_mesh": str(mesh_path),
        "poisson_metrics": _mesh_metrics(poisson),
        "voxel_metrics": _mesh_metrics(voxel, poisson),
        "point_sdf_metrics": _mesh_metrics(point_sdf, poisson),
        "camera_tsdf_metrics": _mesh_metrics(mesh, poisson),
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    report = {
        "method": "ray-based camera TSDF from OpenSfM poses/intrinsics with approximate depth from SfM point reprojection",
        "not_pipeline_integration": True,
        "depth_source": "synthetic sparse depth maps from SfM landmark reprojection; OpenMVS .dmap files detected but not decoded in runtime",
        "datasets": {name: run_dataset(name, cfg) for name, cfg in DATASETS.items()},
    }
    path = OUT / "camera_tsdf_results.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
