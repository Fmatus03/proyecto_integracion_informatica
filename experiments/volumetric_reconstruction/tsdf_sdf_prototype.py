from __future__ import annotations

import json
import math
import os
from collections import Counter, defaultdict, deque
from pathlib import Path

import numpy as np
import open3d as o3d
from scipy import ndimage
from scipy.spatial import cKDTree

from experiments.cloud_unification.cloud_provider_adapter import load_dataset_cloud_source


ROOT = Path(os.environ.get("SDF_ROOT") or Path.cwd())
OUT = Path(os.environ.get("SDF_OUT") or Path(__file__).resolve().parent / "tsdf_outputs")
GRID_STEP_M = float(os.environ.get("SDF_GRID_STEP_M") or "0.25")
TRUNCATION_M = float(os.environ.get("SDF_TRUNCATION_M") or str(GRID_STEP_M * 3.0))

DATASETS = {
    "set1": {
        "cloud": load_dataset_cloud_source("set1").path,
        "poisson": ROOT / "data/processed/a3c36266-f866-402f-8bc8-1c2b59b4a4ce/surface_closure_diagnostics/poisson_raw.ply",
        "voxel": ROOT / "data/volumetric_reconstruction_outputs/set1/voxel_solid_surface.ply",
    },
    "set2": {
        "cloud": load_dataset_cloud_source("set2").path,
        "poisson": ROOT / "data/processed/b6b04af0-122f-4fcc-af8a-cc553ca5e28d/surface_closure_diagnostics_2/poisson_raw.ply",
        "voxel": ROOT / "data/volumetric_reconstruction_outputs/set2/voxel_solid_surface.ply",
    },
}

TETS = np.asarray(
    [
        [0, 5, 1, 6],
        [0, 1, 2, 6],
        [0, 2, 3, 6],
        [0, 3, 7, 6],
        [0, 7, 4, 6],
        [0, 4, 5, 6],
    ],
    dtype=np.int32,
)
CUBE_CORNERS = np.asarray(
    [
        [0, 0, 0],
        [1, 0, 0],
        [1, 1, 0],
        [0, 1, 0],
        [0, 0, 1],
        [1, 0, 1],
        [1, 1, 1],
        [0, 1, 1],
    ],
    dtype=np.int32,
)


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


def _sample_points(mesh: o3d.geometry.TriangleMesh, count: int) -> np.ndarray:
    return np.asarray(mesh.sample_points_uniformly(number_of_points=count).points)


def _chamfer_hausdorff(candidate: o3d.geometry.TriangleMesh, reference: o3d.geometry.TriangleMesh) -> dict:
    if len(candidate.triangles) == 0 or len(reference.triangles) == 0:
        return {"hausdorff_approx": None, "chamfer_approx": None}
    count = 2500
    a = _sample_points(candidate, count)
    b = _sample_points(reference, count)
    tree_a = o3d.geometry.KDTreeFlann(o3d.geometry.PointCloud(o3d.utility.Vector3dVector(a)))
    tree_b = o3d.geometry.KDTreeFlann(o3d.geometry.PointCloud(o3d.utility.Vector3dVector(b)))
    da = []
    db = []
    for p in a:
        _, _, sq = tree_b.search_knn_vector_3d(p, 1)
        da.append(math.sqrt(float(sq[0])))
    for p in b:
        _, _, sq = tree_a.search_knn_vector_3d(p, 1)
        db.append(math.sqrt(float(sq[0])))
    da_arr = np.asarray(da)
    db_arr = np.asarray(db)
    return {
        "hausdorff_approx": round(float(max(da_arr.max(), db_arr.max())), 6),
        "chamfer_approx": round(float(da_arr.mean() + db_arr.mean()), 6),
    }


def _mesh_metrics(mesh: o3d.geometry.TriangleMesh, reference: o3d.geometry.TriangleMesh | None = None) -> dict:
    edge_counts = _edge_counts(mesh)
    bbox = mesh.get_axis_aligned_bounding_box()
    extent = np.asarray(bbox.get_extent(), dtype=float)
    area = float(mesh.get_surface_area()) if len(mesh.triangles) else 0.0
    watertight = bool(mesh.is_watertight()) if len(mesh.triangles) else False
    volume = float(mesh.get_volume()) if watertight else None
    result = {
        "vertices": int(len(mesh.vertices)),
        "triangles": int(len(mesh.triangles)),
        "boundary_edges": int(sum(1 for count in edge_counts.values() if count == 1)),
        "non_manifold_edges": int(sum(1 for count in edge_counts.values() if count > 2)),
        "non_manifold_vertices": int(len(mesh.get_non_manifold_vertices())) if len(mesh.vertices) else 0,
        "orientable": bool(mesh.is_orientable()) if len(mesh.triangles) else False,
        "watertight": watertight,
        "bbox_extent": [round(float(v), 6) for v in extent.tolist()],
        "area": round(area, 6),
        "volume": None if volume is None or math.isnan(volume) else round(volume, 6),
        "components_connected": _component_count(mesh),
    }
    if reference is not None:
        ref_extent = np.asarray(reference.get_axis_aligned_bounding_box().get_extent(), dtype=float)
        ref_diag = float(np.linalg.norm(ref_extent)) or 1.0
        ref_area = float(reference.get_surface_area())
        result["bbox_drift_vs_poisson"] = round(float(np.linalg.norm(extent - ref_extent) / ref_diag), 8)
        result["area_drift_vs_poisson_pct"] = round(((area - ref_area) / ref_area) * 100.0, 6) if ref_area else None
        result.update(_chamfer_hausdorff(mesh, reference))
    return result


def _dominant_solid(points: np.ndarray, grid_step: float) -> tuple[np.ndarray, np.ndarray]:
    padding = 4 * grid_step
    origin = points.min(axis=0) - padding
    max_bound = points.max(axis=0) + padding
    dims = np.ceil((max_bound - origin) / grid_step).astype(int) + 1
    indices = np.floor((points - origin) / grid_step).astype(int)
    occupancy = np.zeros(tuple(dims.tolist()), dtype=bool)
    occupancy[indices[:, 0], indices[:, 1], indices[:, 2]] = True
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
    return solid, origin


def _build_signed_distance(points: np.ndarray, solid: np.ndarray, origin: np.ndarray, grid_step: float) -> np.ndarray:
    axes = [origin[i] + np.arange(solid.shape[i], dtype=float) * grid_step for i in range(3)]
    xx, yy, zz = np.meshgrid(axes[0], axes[1], axes[2], indexing="ij")
    query = np.column_stack((xx.ravel(), yy.ravel(), zz.ravel()))
    distances, _ = cKDTree(points).query(query, k=1, workers=-1)
    sdf = distances.reshape(solid.shape)
    sdf[solid] *= -1.0
    return np.clip(sdf, -TRUNCATION_M, TRUNCATION_M)


def _interp(p0: np.ndarray, p1: np.ndarray, v0: float, v1: float) -> np.ndarray:
    denom = v0 - v1
    t = 0.5 if abs(denom) < 1e-12 else v0 / denom
    return p0 + np.clip(t, 0.0, 1.0) * (p1 - p0)


def _polygonise_tet(points: np.ndarray, values: np.ndarray) -> list[list[np.ndarray]]:
    inside = values < 0.0
    inside_ids = np.where(inside)[0].tolist()
    outside_ids = np.where(~inside)[0].tolist()
    if len(inside_ids) == 0 or len(inside_ids) == 4:
        return []
    tris: list[list[np.ndarray]] = []
    if len(inside_ids) == 1:
        i = inside_ids[0]
        verts = [_interp(points[i], points[o], values[i], values[o]) for o in outside_ids]
        tris.append(verts)
    elif len(inside_ids) == 3:
        o = outside_ids[0]
        verts = [_interp(points[i], points[o], values[i], values[o]) for i in inside_ids]
        tris.append([verts[0], verts[2], verts[1]])
    else:
        i0, i1 = inside_ids
        o0, o1 = outside_ids
        p0 = _interp(points[i0], points[o0], values[i0], values[o0])
        p1 = _interp(points[i0], points[o1], values[i0], values[o1])
        p2 = _interp(points[i1], points[o0], values[i1], values[o0])
        p3 = _interp(points[i1], points[o1], values[i1], values[o1])
        tris.append([p0, p1, p2])
        tris.append([p1, p3, p2])
    return tris


def _marching_tetrahedra(sdf: np.ndarray, origin: np.ndarray, grid_step: float) -> o3d.geometry.TriangleMesh:
    vertex_map: dict[tuple[int, int, int], int] = {}
    vertices: list[np.ndarray] = []
    triangles: list[tuple[int, int, int]] = []

    def add_vertex(point: np.ndarray) -> int:
        key = tuple(np.round(point / (grid_step * 1e-5)).astype(int).tolist())
        if key not in vertex_map:
            vertex_map[key] = len(vertices)
            vertices.append(point)
        return vertex_map[key]

    dims = np.asarray(sdf.shape) - 1
    for ix in range(int(dims[0])):
        for iy in range(int(dims[1])):
            for iz in range(int(dims[2])):
                base = np.asarray([ix, iy, iz], dtype=np.int32)
                corner_idx = CUBE_CORNERS + base
                values = np.asarray([sdf[tuple(idx)] for idx in corner_idx], dtype=float)
                if np.all(values >= 0.0) or np.all(values < 0.0):
                    continue
                coords = origin + corner_idx.astype(float) * grid_step
                for tet in TETS:
                    for tri in _polygonise_tet(coords[tet], values[tet]):
                        ids = tuple(add_vertex(point) for point in tri)
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
    cloud = o3d.io.read_point_cloud(str(cfg["cloud"]))
    points = np.asarray(cloud.points, dtype=float)
    solid, origin = _dominant_solid(points, GRID_STEP_M)
    sdf = _build_signed_distance(points, solid, origin, GRID_STEP_M)
    mesh = _marching_tetrahedra(sdf, origin, GRID_STEP_M)

    out_dir = OUT / name
    out_dir.mkdir(parents=True, exist_ok=True)
    sdf_path = out_dir / "sdf_grid.npz"
    mesh_path = out_dir / "sdf_marching_tetrahedra_mesh.ply"
    np.savez_compressed(sdf_path, sdf=sdf, origin=origin, grid_step_m=GRID_STEP_M, truncation_m=TRUNCATION_M)
    o3d.io.write_triangle_mesh(str(mesh_path), mesh, write_ascii=False, compressed=False)

    poisson = o3d.io.read_triangle_mesh(str(cfg["poisson"]))
    voxel = o3d.io.read_triangle_mesh(str(cfg["voxel"]))
    return {
        "input_points": int(len(points)),
        "grid_shape": [int(v) for v in sdf.shape],
        "grid_step_m": GRID_STEP_M,
        "truncation_m": TRUNCATION_M,
        "sdf_grid": str(sdf_path),
        "sdf_mesh": str(mesh_path),
        "poisson_metrics": _mesh_metrics(poisson),
        "voxel_metrics": _mesh_metrics(voxel, poisson),
        "sdf_tsdf_metrics": _mesh_metrics(mesh, poisson),
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    report = {
        "method": "point-cloud SDF with TSDF truncation and marching tetrahedra extraction",
        "not_pipeline_integration": True,
        "sign_source": "dominant volumetric inside/outside prior from segmented point cloud",
        "distance_source": "continuous nearest-neighbor distance to metric point cloud",
        "datasets": {name: run_dataset(name, cfg) for name, cfg in DATASETS.items()},
    }
    path = OUT / "tsdf_sdf_results.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
