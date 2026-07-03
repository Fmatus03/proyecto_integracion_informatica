from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from backend.app.services import mesh_service
from backend.instrument_meshing_diagnostics import (
    POINT_CLOUD_PATH,
    SESSION_ID,
    SESSION_PATH,
    _prepare_mesh_input,
)


BASE_OUTPUT_DIR = Path("/app/data/processed") / SESSION_ID / "boundary_edge_forensics"
OUTPUT_DIR = BASE_OUTPUT_DIR
FROZEN_TARGET_MESH = (
    Path("/app/data/processed")
    / SESSION_ID
    / "surface_closure_diagnostics_2"
    / "poisson_controlled_hole_fill.ply"
)


def _new_output_dir() -> Path:
    if not BASE_OUTPUT_DIR.exists():
        return BASE_OUTPUT_DIR
    index = 2
    while True:
        candidate = BASE_OUTPUT_DIR.with_name(f"{BASE_OUTPUT_DIR.name}_{index}")
        if not candidate.exists():
            return candidate
        index += 1


def _triangle_normals(vertices: np.ndarray, triangles: np.ndarray) -> np.ndarray:
    if triangles.size == 0:
        return np.empty((0, 3), dtype=float)
    a = vertices[triangles[:, 0]]
    b = vertices[triangles[:, 1]]
    c = vertices[triangles[:, 2]]
    normals = np.cross(b - a, c - a)
    lengths = np.linalg.norm(normals, axis=1)
    valid = lengths > 1e-12
    normals[valid] = normals[valid] / lengths[valid, None]
    normals[~valid] = 0.0
    return normals


def _edge_face_map(triangles: np.ndarray) -> dict[tuple[int, int], list[int]]:
    mapping: dict[tuple[int, int], list[int]] = {}
    for face_index, tri in enumerate(triangles):
        for a, b in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])):
            key = tuple(sorted((int(a), int(b))))
            mapping.setdefault(key, []).append(int(face_index))
    return mapping


def _component_labels(mesh: Any) -> tuple[np.ndarray, np.ndarray]:
    try:
        labels, counts, _areas = mesh.cluster_connected_triangles()
        return np.asarray(labels, dtype=int), np.asarray(counts, dtype=int)
    except Exception:
        return np.full((len(mesh.triangles),), -1, dtype=int), np.asarray([], dtype=int)


def _boundary_edges(mesh: Any) -> list[tuple[int, int]]:
    triangles = np.asarray(mesh.triangles, dtype=int)
    return sorted(edge for edge, faces in _edge_face_map(triangles).items() if len(faces) == 1)


def _boundary_paths(boundary_edges: list[tuple[int, int]]) -> list[dict[str, Any]]:
    adjacency: dict[int, list[int]] = {}
    for a, b in boundary_edges:
        adjacency.setdefault(a, []).append(b)
        adjacency.setdefault(b, []).append(a)

    unused = {edge for edge in boundary_edges}
    paths: list[dict[str, Any]] = []
    while unused:
        endpoints = [v for v, neighbors in adjacency.items() if len(neighbors) == 1 and any(tuple(sorted((v, n))) in unused for n in neighbors)]
        if endpoints:
            start = min(endpoints)
            current = start
            previous = None
            vertices = [start]
            edges: list[tuple[int, int]] = []
            while True:
                candidates = [
                    n
                    for n in adjacency.get(current, [])
                    if n != previous and tuple(sorted((current, n))) in unused
                ]
                if not candidates:
                    break
                nxt = min(candidates)
                edge = tuple(sorted((current, nxt)))
                unused.remove(edge)
                edges.append(edge)
                previous, current = current, nxt
                vertices.append(current)
            paths.append({"vertices": vertices, "edges": edges, "closed": False})
            continue

        first_edge = min(unused)
        start, current = first_edge
        previous = start
        unused.remove(first_edge)
        vertices = [start, current]
        edges = [first_edge]
        closed = False
        while True:
            candidates = [
                n
                for n in adjacency.get(current, [])
                if n != previous and tuple(sorted((current, n))) in unused
            ]
            if not candidates:
                closed = start in adjacency.get(current, [])
                break
            nxt = min(candidates)
            edge = tuple(sorted((current, nxt)))
            unused.remove(edge)
            edges.append(edge)
            previous, current = current, nxt
            if current == start:
                closed = True
                break
            vertices.append(current)
        paths.append({"vertices": vertices, "edges": edges, "closed": closed})
    return paths


def _pca_loop_area(points: np.ndarray, closed: bool) -> float | None:
    if not closed or len(points) < 3:
        return None
    centered = points - points.mean(axis=0)
    try:
        _, _, vh = np.linalg.svd(centered, full_matrices=False)
    except np.linalg.LinAlgError:
        return None
    projected = centered @ vh[:2].T
    x = projected[:, 0]
    y = projected[:, 1]
    area = 0.5 * abs(float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))))
    return area


def _diameter(points: np.ndarray) -> float:
    if len(points) < 2:
        return 0.0
    deltas = points[:, None, :] - points[None, :, :]
    return float(np.linalg.norm(deltas, axis=2).max())


def _bbox_delta(candidate: dict[str, float], reference: dict[str, float]) -> dict[str, float]:
    return {
        key: round(abs(candidate[key] - reference[key]) / max(abs(reference[key]), 1e-9), 8)
        for key in candidate
    }


def _safe_delta(value: float | None, reference: float | None) -> float | None:
    if value is None or reference in (None, 0):
        return None
    return round(float(value) - float(reference), 6)


def _make_mesh_with_loop_closed(o3d: Any, mesh: Any, loop: dict[str, Any]) -> tuple[Any, dict[str, Any]]:
    if not loop["closed"] or len(loop["vertices"]) < 3:
        return o3d.geometry.TriangleMesh(mesh), {
            "applied": False,
            "reason": "loop_is_open_or_has_less_than_3_vertices",
        }
    triangles = np.asarray(mesh.triangles, dtype=int)
    vertices = loop["vertices"]
    anchor = vertices[0]
    added = [[anchor, vertices[i], vertices[i + 1]] for i in range(1, len(vertices) - 1)]
    simulated = o3d.geometry.TriangleMesh(mesh)
    simulated.triangles = o3d.utility.Vector3iVector(np.vstack([triangles, np.asarray(added, dtype=int)]))
    simulated.remove_degenerate_triangles()
    simulated.remove_duplicated_triangles()
    simulated.remove_unreferenced_vertices()
    if hasattr(simulated, "orient_triangles"):
        try:
            simulated.orient_triangles()
        except Exception:
            pass
    simulated.compute_vertex_normals()
    return simulated, {"applied": True, "method": "fan_triangulation_single_loop", "added_triangles": len(added)}


def _classify_loop(loop: dict[str, Any], mesh_metrics: dict[str, Any], loop_metrics: dict[str, Any], normal_stats: dict[str, Any]) -> tuple[str, list[str]]:
    reasons: list[str] = []
    if not loop["closed"]:
        reasons.append("boundary_path_is_open_not_a_closed_hole")
        if loop_metrics["touches_bbox_extreme"]:
            return "corte_producido_por_captura_fotogrametrica", reasons
        return "error_topologico", reasons
    if loop_metrics["edge_count"] < 3:
        reasons.append("closed_loop_has_less_than_3_edges")
        return "triangulos_degenerados", reasons
    if normal_stats["adjacent_face_normal_min_dot"] is not None and normal_stats["adjacent_face_normal_min_dot"] < 0.25:
        reasons.append("adjacent_normals_are_inconsistent")
        return "normales_inconsistentes", reasons
    if loop_metrics["perimeter_m"] <= 0.08 * mesh_metrics["bbox_diagonal_m"]:
        reasons.append("small_closed_loop_relative_to_bbox")
        return "hueco_pequeno_cerrable", reasons
    if loop_metrics["touches_bbox_extreme"]:
        reasons.append("loop_touches_global_bbox_extreme")
        return "borde_real_del_objeto", reasons
    reasons.append("closed_loop_large_or_ambiguous")
    return "discontinuidad_estructural", reasons


def _edge_and_loop_records(o3d: Any, mesh: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    vertices = np.asarray(mesh.vertices, dtype=float)
    triangles = np.asarray(mesh.triangles, dtype=int)
    vertex_normals = np.asarray(mesh.vertex_normals, dtype=float)
    if vertex_normals.shape != vertices.shape:
        mesh.compute_vertex_normals()
        vertex_normals = np.asarray(mesh.vertex_normals, dtype=float)
    face_normals = _triangle_normals(vertices, triangles)
    edge_faces = _edge_face_map(triangles)
    face_components, component_counts = _component_labels(mesh)
    boundary = _boundary_edges(mesh)
    paths = _boundary_paths(boundary)
    edge_to_loop = {edge: loop_index for loop_index, path in enumerate(paths) for edge in path["edges"]}

    bbox = mesh.get_axis_aligned_bounding_box()
    bbox_min = np.asarray(bbox.get_min_bound(), dtype=float)
    bbox_max = np.asarray(bbox.get_max_bound(), dtype=float)
    bbox_extent = np.asarray(bbox.get_extent(), dtype=float)
    bbox_diagonal = float(np.linalg.norm(bbox_extent))
    bbox_tol = max(bbox_diagonal * 0.002, 1e-6)
    mesh_metrics = mesh_service._mesh_topology_metrics(mesh)
    mesh_metrics["bbox_diagonal_m"] = round(bbox_diagonal, 6)

    edge_records = []
    for edge_id, (a, b) in enumerate(boundary):
        adjacent_faces = edge_faces[(a, b)]
        component = int(face_components[adjacent_faces[0]]) if len(adjacent_faces) == 1 and len(face_components) else None
        edge_vec = vertices[b] - vertices[a]
        adjacent_normals = [face_normals[index].tolist() for index in adjacent_faces]
        adjacent_face_vertices = [triangles[index].astype(int).tolist() for index in adjacent_faces]
        adjacent_face_edge_incidences = []
        for face_vertices in adjacent_face_vertices:
            face_edges = [
                tuple(sorted((face_vertices[0], face_vertices[1]))),
                tuple(sorted((face_vertices[1], face_vertices[2]))),
                tuple(sorted((face_vertices[2], face_vertices[0]))),
            ]
            adjacent_face_edge_incidences.append(
                [
                    {
                        "vertices": [int(edge_vertex) for edge_vertex in face_edge],
                        "incidence_count": len(edge_faces.get(face_edge, [])),
                        "is_boundary_edge": len(edge_faces.get(face_edge, [])) == 1,
                    }
                    for face_edge in face_edges
                ]
            )
        record = {
            "edge_id": f"BE-{edge_id:03d}",
            "loop_id": f"BL-{edge_to_loop[(a, b)]:03d}",
            "vertices": [int(a), int(b)],
            "endpoints": {
                "a": [round(float(v), 6) for v in vertices[a].tolist()],
                "b": [round(float(v), 6) for v in vertices[b].tolist()],
            },
            "length_m": round(float(np.linalg.norm(edge_vec)), 6),
            "vertex_normals": {
                "a": [round(float(v), 6) for v in vertex_normals[a].tolist()],
                "b": [round(float(v), 6) for v in vertex_normals[b].tolist()],
            },
            "adjacent_faces": adjacent_faces,
            "adjacent_face_vertices": adjacent_face_vertices,
            "adjacent_face_normals": [[round(float(v), 6) for v in normal] for normal in adjacent_normals],
            "adjacent_face_edge_incidences": adjacent_face_edge_incidences,
            "connected_component": component,
            "component_triangle_count": None if component is None or component < 0 or component >= len(component_counts) else int(component_counts[component]),
        }
        edge_records.append(record)

    loop_records = []
    for loop_index, path in enumerate(paths):
        loop_vertices = path["vertices"]
        pts = vertices[loop_vertices]
        perimeter = float(sum(np.linalg.norm(vertices[a] - vertices[b]) for a, b in path["edges"]))
        centroid = pts.mean(axis=0)
        extent = pts.max(axis=0) - pts.min(axis=0)
        touches_bbox = bool(np.any(np.isclose(pts, bbox_min, atol=bbox_tol)) or np.any(np.isclose(pts, bbox_max, atol=bbox_tol)))
        face_indices = sorted({face for edge in path["edges"] for face in edge_faces[edge]})
        components = sorted({int(face_components[face]) for face in face_indices}) if len(face_components) else []
        normals = face_normals[face_indices] if face_indices else np.empty((0, 3), dtype=float)
        dots = []
        for i in range(len(normals)):
            for j in range(i + 1, len(normals)):
                dots.append(float(np.dot(normals[i], normals[j])))
        normal_stats = {
            "adjacent_face_count": len(face_indices),
            "adjacent_face_normal_min_dot": None if not dots else round(min(dots), 6),
            "adjacent_face_normal_mean_dot": None if not dots else round(float(np.mean(dots)), 6),
        }
        loop_metrics = {
            "edge_count": len(path["edges"]),
            "vertex_count": len(loop_vertices),
            "closed": bool(path["closed"]),
            "perimeter_m": round(perimeter, 6),
            "diameter_m": round(_diameter(pts), 6),
            "approx_area_m2": None if _pca_loop_area(pts, bool(path["closed"])) is None else round(float(_pca_loop_area(pts, bool(path["closed"]))), 8),
            "centroid_m": [round(float(v), 6) for v in centroid.tolist()],
            "extent_m": [round(float(v), 6) for v in extent.tolist()],
            "touches_bbox_extreme": touches_bbox,
            "connected_components": components,
        }
        category, reasons = _classify_loop(path, mesh_metrics, loop_metrics, normal_stats)
        loop_records.append(
            {
                "loop_id": f"BL-{loop_index:03d}",
                "boundary_edge_ids": [record["edge_id"] for record in edge_records if record["loop_id"] == f"BL-{loop_index:03d}"],
                "vertices": [int(v) for v in loop_vertices],
                "metrics": loop_metrics,
                "normal_stats": normal_stats,
                "classification": category,
                "classification_evidence": reasons,
            }
        )
    return edge_records, loop_records


def _simulate_individual_loop_closures(o3d: Any, mesh: Any, loops: list[dict[str, Any]]) -> list[dict[str, Any]]:
    base = mesh_service._mesh_topology_metrics(mesh)
    simulations = []
    for loop in loops:
        simulated, step = _make_mesh_with_loop_closed(o3d, mesh, {"closed": loop["metrics"]["closed"], "vertices": loop["vertices"]})
        metrics = mesh_service._mesh_topology_metrics(simulated)
        ply_path = OUTPUT_DIR / f"simulation_{loop['loop_id']}.ply"
        if step["applied"]:
            o3d.io.write_triangle_mesh(str(ply_path), simulated, write_ascii=False, compressed=False)
        simulations.append(
            {
                "loop_id": loop["loop_id"],
                "applied": step["applied"],
                "method": step.get("method"),
                "reason": step.get("reason"),
                "artifact": str(ply_path) if step["applied"] else None,
                "delta": {
                    "volume_m3": _safe_delta(metrics["volume_m3"], base["volume_m3"]),
                    "surface_area_m2": _safe_delta(metrics["surface_area_m2"], base["surface_area_m2"]),
                    "bbox_delta_ratio": _bbox_delta(metrics["bounding_box_m"], base["bounding_box_m"]),
                    "components": None if metrics["components"] is None or base["components"] is None else int(metrics["components"] - base["components"]),
                    "boundary_edges": int(metrics["boundary_edges"] - base["boundary_edges"]),
                },
                "metrics_after_single_loop_closure": metrics,
                "expected_impact": {
                    "bounding_box": "none_expected" if max(_bbox_delta(metrics["bounding_box_m"], base["bounding_box_m"]).values()) == 0 else "bbox_changed",
                    "surface_area": "local_patch_only" if abs(_safe_delta(metrics["surface_area_m2"], base["surface_area_m2"]) or 0) < 1.0 else "large_surface_change",
                    "volume": "not_available_until_watertight" if metrics["volume_m3"] is None else "volume_available_after_single_loop",
                    "topology": "reduces_boundary_edges" if metrics["boundary_edges"] < base["boundary_edges"] else "does_not_reduce_boundary_edges",
                },
            }
        )
    return simulations


def _project(points: np.ndarray, axes: tuple[np.ndarray, np.ndarray], size: tuple[int, int], margin: int = 30) -> np.ndarray:
    projected = np.column_stack([points @ axes[0], points @ axes[1]])
    mins = projected.min(axis=0)
    span = np.maximum(projected.max(axis=0) - mins, 1e-9)
    scale = min((size[0] - 2 * margin) / span[0], (size[1] - 2 * margin) / span[1])
    xy = (projected - mins) * scale + margin
    xy[:, 1] = size[1] - xy[:, 1]
    return xy


def _draw_view(name: str, mesh: Any, loops: list[dict[str, Any]], edges: list[dict[str, Any]], axes: tuple[np.ndarray, np.ndarray]) -> str:
    vertices = np.asarray(mesh.vertices, dtype=float)
    triangles = np.asarray(mesh.triangles, dtype=int)
    points = _project(vertices, axes, (1200, 900))
    image = Image.new("RGB", (1200, 900), "white")
    draw = ImageDraw.Draw(image)
    edge_set = set()
    for tri in triangles[:: max(1, len(triangles) // 25000)]:
        for a, b in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])):
            edge = tuple(sorted((int(a), int(b))))
            if edge in edge_set:
                continue
            edge_set.add(edge)
            pa = tuple(points[edge[0]].astype(int))
            pb = tuple(points[edge[1]].astype(int))
            draw.line([pa, pb], fill=(218, 218, 218), width=1)

    palette = [(220, 30, 30), (35, 120, 220), (30, 160, 80), (190, 90, 20), (140, 60, 180), (0, 150, 150)]
    edge_by_id = {record["edge_id"]: record for record in edges}
    for index, loop in enumerate(loops):
        color = palette[index % len(palette)]
        loop_points = []
        for edge_id in loop["boundary_edge_ids"]:
            a, b = edge_by_id[edge_id]["vertices"]
            pa = tuple(points[a].astype(int))
            pb = tuple(points[b].astype(int))
            draw.line([pa, pb], fill=color, width=5)
            loop_points.extend([points[a], points[b]])
        if loop_points:
            center = np.asarray(loop_points).mean(axis=0).astype(int)
            label = loop["loop_id"].replace("BL-", "")
            draw.ellipse([center[0] - 13, center[1] - 13, center[0] + 13, center[1] + 13], fill=color)
            draw.text((center[0] - 7, center[1] - 8), label, fill="white")

    draw.text((18, 16), name, fill=(0, 0, 0))
    path = OUTPUT_DIR / f"{name}.png"
    image.save(path)
    return str(path)


def _visualizations(mesh: Any, loops: list[dict[str, Any]], edges: list[dict[str, Any]]) -> dict[str, str]:
    axes = {
        "orthographic_xy": (np.array([1.0, 0.0, 0.0]), np.array([0.0, 1.0, 0.0])),
        "orthographic_xz": (np.array([1.0, 0.0, 0.0]), np.array([0.0, 0.0, 1.0])),
        "orthographic_yz": (np.array([0.0, 1.0, 0.0]), np.array([0.0, 0.0, 1.0])),
        "view_3d_isometric": (
            np.array([1.0, -1.0, 0.0]) / math.sqrt(2.0),
            np.array([1.0, 1.0, 2.0]) / math.sqrt(6.0),
        ),
    }
    return {name: _draw_view(name, mesh, loops, edges, axis_pair) for name, axis_pair in axes.items()}


def _prepare_controlled_fill_mesh(o3d: Any) -> tuple[Any, dict[str, Any]]:
    session = json.loads(SESSION_PATH.read_text(encoding="utf-8"))
    mesh_input = _prepare_mesh_input(o3d, session)
    poisson_raw = mesh_service._poisson_mesh(o3d, mesh_input, depth=8, density_quantile=0.01)
    poisson_recovered, repair_cycles, recovery_report = mesh_service._recover_poisson_mesh(o3d, o3d.geometry.TriangleMesh(poisson_raw))
    filled = poisson_recovered
    fill_steps = []
    for attempt in range(1, 4):
        filled, step = mesh_service._fill_boundary_edge_loops(o3d, filled)
        step["attempt"] = attempt
        fill_steps.append(step)
        if not step.get("applied"):
            break
    return filled, {
        "repair_cycles": repair_cycles,
        "recovery_report": recovery_report,
        "fill_steps": fill_steps,
    }


def _root_cause(edges: list[dict[str, Any]], loops: list[dict[str, Any]], simulations: list[dict[str, Any]]) -> dict[str, Any]:
    open_loops = [loop for loop in loops if not loop["metrics"]["closed"]]
    remaining_after_simulation = [sim for sim in simulations if sim["applied"] and sim["metrics_after_single_loop_closure"]["boundary_edges"] > 0]
    if open_loops:
        return {
            "cause": "open_boundary_paths_after_loop_filling_not_closed_holes",
            "evidence": [
                f"{len(open_loops)} boundary path(s) are open and cannot be fan-triangulated as closed holes",
                f"{len(edges)} boundary edges remain after three deterministic fill attempts",
                "Open3D loop filling helper only closes closed boundary cycles; open paths remain boundary by definition",
            ],
            "excluded_causes": {
                "ground_truth": "not_used",
                "gcp_or_calibration": "not_modified",
                "segmentation": "not_rerun",
                "alpha_shape": "not_involved",
            },
        }
    if remaining_after_simulation:
        return {
            "cause": "closed_loops_do_not_individually_resolve_topology",
            "evidence": [
                "At least one individual loop closure leaves boundary edges or non-manifold topology",
                "The issue is topological rather than volumetric",
            ],
        }
    return {
        "cause": "small_closed_holes_remaining_after_attempt_limit",
        "evidence": [
            "All remaining loops are closed and individually closable",
            "The previous three-attempt limit stopped before full deterministic closure",
        ],
    }


def _technical_decision(loops: list[dict[str, Any]], simulations: list[dict[str, Any]]) -> dict[str, Any]:
    all_closed = all(loop["metrics"]["closed"] for loop in loops)
    all_simulated_reduce = all((not sim["applied"]) or sim["delta"]["boundary_edges"] < 0 for sim in simulations)
    no_bbox_change = all(max(sim["delta"]["bbox_delta_ratio"].values()) == 0 for sim in simulations)
    if all_closed and all_simulated_reduce and no_bbox_change:
        return {
            "option": "A",
            "answer": "Si. Los boundary edges restantes son recuperables sin alterar significativamente la geometria.",
        }
    return {
        "option": "B",
        "answer": "No. Los boundary edges representan una limitacion estructural de la reconstruccion y justifican desarrollar una nueva estrategia de superficie hibrida o constrained.",
    }


def main() -> None:
    global OUTPUT_DIR
    OUTPUT_DIR = _new_output_dir()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=False)
    o3d = mesh_service._require_open3d()
    if FROZEN_TARGET_MESH.exists():
        mesh = o3d.io.read_triangle_mesh(str(FROZEN_TARGET_MESH))
        provenance = {
            "source": "frozen_surface_closure_diagnostics_2_artifact",
            "frozen_target_mesh": str(FROZEN_TARGET_MESH),
            "reason": "analyze_the_exact_6_boundary_edge_mesh_from_previous_docker_validation",
        }
    else:
        mesh, provenance = _prepare_controlled_fill_mesh(o3d)
        provenance["source"] = "reconstructed_controlled_fill_mesh"
    mesh.compute_vertex_normals()
    mesh_path = OUTPUT_DIR / "poisson_controlled_hole_fill_target.ply"
    o3d.io.write_triangle_mesh(str(mesh_path), mesh, write_ascii=False, compressed=False)

    edges, loops = _edge_and_loop_records(o3d, mesh)
    simulations = _simulate_individual_loop_closures(o3d, mesh, loops)
    visuals = _visualizations(mesh, loops, edges)
    report = {
        "session_id": SESSION_ID,
        "target_mesh": str(mesh_path),
        "source_point_cloud": str(POINT_CLOUD_PATH),
        "constraints": {
            "ground_truth_used": False,
            "gcp_modified": False,
            "calibration_modified": False,
            "segmentation_modified": False,
            "poisson_algorithm_changed": False,
            "hybrid_surface_implemented": False,
        },
        "provenance": provenance,
        "target_metrics": mesh_service._mesh_topology_metrics(mesh),
        "boundary_edge_count": len(edges),
        "boundary_loop_count": len(loops),
        "boundary_edges": edges,
        "boundary_loops": loops,
        "single_loop_simulations": simulations,
        "visualizations": visuals,
        "root_cause": _root_cause(edges, loops, simulations),
        "technical_decision": _technical_decision(loops, simulations),
    }
    (OUTPUT_DIR / "boundary_edge_forensics.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({
        "output_dir": str(OUTPUT_DIR),
        "boundary_edge_count": len(edges),
        "boundary_loop_count": len(loops),
        "technical_decision": report["technical_decision"],
    }, indent=2))


if __name__ == "__main__":
    main()
