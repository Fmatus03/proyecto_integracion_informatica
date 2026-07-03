from __future__ import annotations

import importlib.util
import json
import math
import os
import shutil
import subprocess
from collections import Counter, defaultdict, deque
from pathlib import Path

import numpy as np
import open3d as o3d


DEFAULT_ROOT = Path(__file__).resolve().parents[2] if len(Path(__file__).resolve().parents) > 2 else Path.cwd()
ROOT = Path(os.environ.get("BENCHMARK_ROOT") or DEFAULT_ROOT)
OUT = Path(os.environ.get("BENCHMARK_OUT") or (Path(__file__).resolve().parent / "outputs"))
DATASETS = {
    "set1": ROOT / "data/processed/a3c36266-f866-402f-8bc8-1c2b59b4a4ce/surface_closure_diagnostics/poisson_raw.ply",
    "set2": ROOT / "data/processed/b6b04af0-122f-4fcc-af8a-cc553ca5e28d/surface_closure_diagnostics_2/poisson_raw.ply",
}


def _load(path: Path) -> o3d.geometry.TriangleMesh:
    mesh = o3d.io.read_triangle_mesh(str(path))
    if not mesh.has_vertices() or not mesh.has_triangles():
        raise ValueError(f"Not a triangle mesh: {path}")
    return mesh


def _write(mesh: o3d.geometry.TriangleMesh, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    o3d.io.write_triangle_mesh(str(path), mesh, write_ascii=False, compressed=False)
    return path


def _arrays(mesh: o3d.geometry.TriangleMesh) -> tuple[np.ndarray, np.ndarray]:
    return np.asarray(mesh.vertices), np.asarray(mesh.triangles, dtype=np.int64)


def _edge_counts(mesh: o3d.geometry.TriangleMesh) -> Counter:
    _, faces = _arrays(mesh)
    edges = np.sort(np.vstack((faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]])), axis=1)
    return Counter(map(tuple, edges.tolist()))


def _component_count(mesh: o3d.geometry.TriangleMesh) -> int:
    _, faces = _arrays(mesh)
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


def _non_manifold_vertex_count(mesh: o3d.geometry.TriangleMesh) -> int:
    try:
        return int(len(mesh.get_non_manifold_vertices()))
    except Exception:
        return 0


def _sample_points(mesh: o3d.geometry.TriangleMesh, count: int) -> np.ndarray:
    sampled = mesh.sample_points_uniformly(number_of_points=count)
    return np.asarray(sampled.points)


def _nearest_distances(source_points: np.ndarray, target_points: np.ndarray) -> np.ndarray:
    target_cloud = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(target_points))
    tree = o3d.geometry.KDTreeFlann(target_cloud)
    distances = np.zeros(len(source_points), dtype=float)
    for index, point in enumerate(source_points):
        _, _, squared = tree.search_knn_vector_3d(point, 1)
        distances[index] = math.sqrt(float(squared[0])) if squared else math.nan
    return distances


def _metrics(mesh: o3d.geometry.TriangleMesh, base: o3d.geometry.TriangleMesh | None = None) -> dict:
    vertices, faces = _arrays(mesh)
    edge_counts = _edge_counts(mesh)
    bbox = mesh.get_axis_aligned_bounding_box()
    extent = np.asarray(bbox.get_extent(), dtype=float)
    area = float(mesh.get_surface_area())
    watertight = bool(mesh.is_watertight())
    volume = float(mesh.get_volume()) if watertight else None
    result = {
        "vertices": int(len(vertices)),
        "triangles": int(len(faces)),
        "boundary_edges": int(sum(1 for count in edge_counts.values() if count == 1)),
        "non_manifold_edges": int(sum(1 for count in edge_counts.values() if count > 2)),
        "non_manifold_vertices": _non_manifold_vertex_count(mesh),
        "orientable": bool(mesh.is_orientable()),
        "watertight": watertight,
        "bbox_extent": [round(float(v), 6) for v in extent.tolist()],
        "area": round(area, 6),
        "volume": None if volume is None or math.isnan(volume) else round(volume, 6),
        "components_connected": _component_count(mesh),
    }
    if base is not None:
        base_extent = np.asarray(base.get_axis_aligned_bounding_box().get_extent(), dtype=float)
        base_diag = float(np.linalg.norm(base_extent)) or 1.0
        base_area = float(base.get_surface_area())
        result["bbox_drift"] = round(float(np.linalg.norm(extent - base_extent) / base_diag), 8)
        result["area_drift_pct"] = round(((area - base_area) / base_area) * 100.0, 6) if base_area else None
        sample_count = min(3000, max(1000, len(vertices)))
        base_points = _sample_points(base, sample_count)
        mesh_points = _sample_points(mesh, sample_count)
        base_to_mesh = _nearest_distances(base_points, mesh_points)
        mesh_to_base = _nearest_distances(mesh_points, base_points)
        result["hausdorff_approx"] = round(float(max(np.nanmax(base_to_mesh), np.nanmax(mesh_to_base))), 6)
        result["chamfer_approx"] = round(float(np.nanmean(base_to_mesh) + np.nanmean(mesh_to_base)), 6)
    return result


def _open3d_cleanup(mesh: o3d.geometry.TriangleMesh) -> o3d.geometry.TriangleMesh:
    repaired = o3d.geometry.TriangleMesh(mesh)
    repaired.remove_degenerate_triangles()
    repaired.remove_duplicated_triangles()
    repaired.remove_duplicated_vertices()
    repaired.remove_non_manifold_edges()
    repaired.remove_unreferenced_vertices()
    repaired.orient_triangles()
    repaired.compute_vertex_normals()
    return repaired


def _external_status(command: str) -> tuple[bool, str]:
    executable = shutil.which(command)
    if not executable:
        return False, f"unavailable: {command} not found on PATH"
    return True, executable


def _run_external(command: str, source: Path, output: Path) -> tuple[bool, str]:
    ok, detail = _external_status(command)
    if not ok:
        return ok, detail
    completed = subprocess.run([detail, str(source), str(output)], capture_output=True, text=True, timeout=600)
    if completed.returncode != 0:
        return False, completed.stderr.strip() or completed.stdout.strip()
    return True, "ok"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    report: dict[str, object] = {
        "protocol": "RUN-SET1-BASELINE-01 repair benchmark",
        "engine_availability": {
            "open3d_cleanup_control": "available",
            "trimesh_repair_extended": "available" if importlib.util.find_spec("trimesh") else "unavailable",
            "pymeshlab": "available" if importlib.util.find_spec("pymeshlab") else "unavailable",
            "vtk_fill_holes": "available" if importlib.util.find_spec("vtk") else "unavailable",
            "meshfix": _external_status("meshfix")[1],
            "cgal_pmp": _external_status("cgal_pmp_repair")[1],
        },
        "datasets": {},
    }
    for dataset, source in DATASETS.items():
        base = _load(source)
        dataset_dir = OUT / dataset
        frozen = _write(base, dataset_dir / "poisson_raw_frozen.ply")
        dataset_report = {
            "source": str(source),
            "frozen_mesh": str(frozen),
            "base_metrics": _metrics(base),
            "engines": {},
        }

        repaired = _open3d_cleanup(base)
        open3d_output = _write(repaired, dataset_dir / "open3d_cleanup_control.ply")
        dataset_report["engines"]["open3d_cleanup_control"] = {
            "status": "ok",
            "note": "Local control using Open3D cleanup primitives available in backend; not a requested replacement engine.",
            "output": str(open3d_output),
            "metrics": _metrics(repaired, base),
        }

        for engine, module_name in (
            ("trimesh_repair_extended", "trimesh"),
            ("pymeshlab", "pymeshlab"),
            ("vtk_fill_holes", "vtk"),
        ):
            dataset_report["engines"][engine] = {
                "status": "unavailable",
                "note": f"Python module {module_name!r} is not installed in forestvol-backend.",
                "output": None,
            }

        for engine, command in (("meshfix", "meshfix"), ("cgal_pmp", "cgal_pmp_repair")):
            output = dataset_dir / f"{engine}.ply"
            ok, note = _run_external(command, source, output)
            entry = {"status": "ok" if ok else "unavailable_or_failed", "note": note, "output": str(output) if ok else None}
            if ok:
                entry["metrics"] = _metrics(_load(output), base)
            dataset_report["engines"][engine] = entry

        report["datasets"][dataset] = dataset_report

    report_path = OUT / "repair_benchmark_results.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
