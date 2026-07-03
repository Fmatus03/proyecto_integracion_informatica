from __future__ import annotations

import json
import math
import os
from collections import Counter, defaultdict, deque
from pathlib import Path

import numpy as np
import open3d as o3d
from scipy import ndimage

from experiments.cloud_unification.cloud_provider_adapter import load_dataset_cloud_source


ROOT = Path(os.environ.get("VOLUME_ROOT") or Path.cwd())
OUT = Path(os.environ.get("VOLUME_OUT") or Path(__file__).resolve().parent / "outputs")
VOXEL_SIZE_M = float(os.environ.get("VOXEL_SIZE_M") or "0.25")
DATASETS = {
    "set1": {
        "cloud": load_dataset_cloud_source("set1").path,
        "poisson": ROOT / "data/processed/a3c36266-f866-402f-8bc8-1c2b59b4a4ce/surface_closure_diagnostics/poisson_raw.ply",
        "pipeline_volume_m3": 156.9277,
    },
    "set2": {
        "cloud": load_dataset_cloud_source("set2").path,
        "poisson": ROOT / "data/processed/b6b04af0-122f-4fcc-af8a-cc553ca5e28d/surface_closure_diagnostics_2/poisson_raw.ply",
        "pipeline_volume_m3": 46.7197,
    },
}


FACE_DEFS = [
    ((-1, 0, 0), [(0, 0, 0), (0, 0, 1), (0, 1, 1), (0, 1, 0)]),
    ((1, 0, 0), [(1, 0, 0), (1, 1, 0), (1, 1, 1), (1, 0, 1)]),
    ((0, -1, 0), [(0, 0, 0), (1, 0, 0), (1, 0, 1), (0, 0, 1)]),
    ((0, 1, 0), [(0, 1, 0), (0, 1, 1), (1, 1, 1), (1, 1, 0)]),
    ((0, 0, -1), [(0, 0, 0), (0, 1, 0), (1, 1, 0), (1, 0, 0)]),
    ((0, 0, 1), [(0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)]),
]


def _edge_counts(mesh: o3d.geometry.TriangleMesh) -> Counter:
    faces = np.asarray(mesh.triangles, dtype=np.int64)
    edges = np.sort(np.vstack((faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]])), axis=1)
    return Counter(map(tuple, edges.tolist()))


def _component_count(mesh: o3d.geometry.TriangleMesh) -> int:
    faces = np.asarray(mesh.triangles, dtype=np.int64)
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


def _mesh_metrics(mesh: o3d.geometry.TriangleMesh) -> dict:
    edge_counts = _edge_counts(mesh)
    bbox = mesh.get_axis_aligned_bounding_box()
    watertight = bool(mesh.is_watertight())
    volume = float(mesh.get_volume()) if watertight else None
    return {
        "vertices": int(len(mesh.vertices)),
        "triangles": int(len(mesh.triangles)),
        "boundary_edges": int(sum(1 for count in edge_counts.values() if count == 1)),
        "non_manifold_edges": int(sum(1 for count in edge_counts.values() if count > 2)),
        "non_manifold_vertices": int(len(mesh.get_non_manifold_vertices())),
        "orientable": bool(mesh.is_orientable()),
        "watertight": watertight,
        "bbox_extent": [round(float(v), 6) for v in np.asarray(bbox.get_extent()).tolist()],
        "area": round(float(mesh.get_surface_area()), 6),
        "volume": None if volume is None or math.isnan(volume) else round(volume, 6),
        "components_connected": _component_count(mesh),
    }


def _voxel_solid(points: np.ndarray, voxel_size: float) -> tuple[np.ndarray, np.ndarray]:
    padding_voxels = 4
    min_bound = points.min(axis=0) - padding_voxels * voxel_size
    max_bound = points.max(axis=0) + padding_voxels * voxel_size
    dims = np.ceil((max_bound - min_bound) / voxel_size).astype(int) + 1
    indices = np.floor((points - min_bound) / voxel_size).astype(int)
    grid = np.zeros(tuple(dims.tolist()), dtype=bool)
    grid[indices[:, 0], indices[:, 1], indices[:, 2]] = True
    structure = ndimage.generate_binary_structure(3, 2)
    shell = ndimage.binary_dilation(grid, structure=structure, iterations=2)
    solid = ndimage.binary_fill_holes(shell)
    solid = ndimage.binary_closing(solid, structure=structure, iterations=1)
    solid = ndimage.binary_fill_holes(solid)
    labels, count = ndimage.label(solid, structure=structure)
    if count > 1:
        sizes = np.bincount(labels.ravel())
        sizes[0] = 0
        solid = labels == int(np.argmax(sizes))
    return solid, min_bound


def _surface_from_voxels(solid: np.ndarray, origin: np.ndarray, voxel_size: float) -> o3d.geometry.TriangleMesh:
    vertices: list[tuple[float, float, float]] = []
    vertex_index: dict[tuple[int, int, int], int] = {}
    triangles: list[tuple[int, int, int]] = []

    def vindex(coord: tuple[int, int, int]) -> int:
        if coord not in vertex_index:
            vertex_index[coord] = len(vertices)
            vertices.append(tuple((origin + np.asarray(coord, dtype=float) * voxel_size).tolist()))
        return vertex_index[coord]

    filled = np.argwhere(solid)
    dims = np.asarray(solid.shape)
    for cell in filled:
        x, y, z = (int(v) for v in cell)
        for direction, corners in FACE_DEFS:
            neighbor = cell + np.asarray(direction)
            outside = np.any(neighbor < 0) or np.any(neighbor >= dims) or not solid[tuple(neighbor)]
            if not outside:
                continue
            ids = [vindex((x + cx, y + cy, z + cz)) for cx, cy, cz in corners]
            triangles.append((ids[0], ids[1], ids[2]))
            triangles.append((ids[0], ids[2], ids[3]))

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
    solid, origin = _voxel_solid(points, VOXEL_SIZE_M)
    mesh = _surface_from_voxels(solid, origin, VOXEL_SIZE_M)
    out_dir = OUT / name
    out_dir.mkdir(parents=True, exist_ok=True)
    mesh_path = out_dir / "voxel_solid_surface.ply"
    o3d.io.write_triangle_mesh(str(mesh_path), mesh, write_ascii=False, compressed=False)

    poisson = o3d.io.read_triangle_mesh(str(cfg["poisson"]))
    poisson_metrics = _mesh_metrics(poisson)
    voxel_metrics = _mesh_metrics(mesh)
    voxel_volume_count = int(np.count_nonzero(solid))
    voxel_metrics["voxel_count"] = voxel_volume_count
    voxel_metrics["voxel_volume_estimate_m3"] = round(voxel_volume_count * (VOXEL_SIZE_M ** 3), 6)
    voxel_metrics["volume_drift_vs_pipeline_pct"] = round(
        ((voxel_metrics["volume"] - cfg["pipeline_volume_m3"]) / cfg["pipeline_volume_m3"]) * 100.0,
        6,
    ) if voxel_metrics["volume"] is not None else None

    return {
        "point_cloud": str(cfg["cloud"]),
        "poisson_baseline": str(cfg["poisson"]),
        "output_mesh": str(mesh_path),
        "input_points": int(len(points)),
        "voxel_size_m": VOXEL_SIZE_M,
        "pipeline_volume_reference_m3": cfg["pipeline_volume_m3"],
        "poisson_metrics": poisson_metrics,
        "volumetric_metrics": voxel_metrics,
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    report = {
        "method": "binary voxel solid from point cloud with external face extraction",
        "not_pipeline_integration": True,
        "datasets": {name: run_dataset(name, cfg) for name, cfg in DATASETS.items()},
    }
    path = OUT / "volumetric_voxel_results.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
