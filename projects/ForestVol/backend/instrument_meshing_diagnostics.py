from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from backend.app.services import mesh_service


SESSION_ID = "b6b04af0-122f-4fcc-af8a-cc553ca5e28d"
SESSION_PATH = Path("/app/data/uploads") / SESSION_ID / "session.json"
POINT_CLOUD_PATH = Path("/app/data/processed") / SESSION_ID / "point_cloud.ply"
BASE_OUTPUT_DIR = Path("/app/data/processed") / SESSION_ID / "surface_closure_diagnostics"
OUTPUT_DIR = BASE_OUTPUT_DIR


def _new_output_dir() -> Path:
    if not BASE_OUTPUT_DIR.exists():
        return BASE_OUTPUT_DIR
    index = 2
    while True:
        candidate = BASE_OUTPUT_DIR.with_name(f"{BASE_OUTPUT_DIR.name}_{index}")
        if not candidate.exists():
            return candidate
        index += 1


def _relative_delta(value: float | None, reference: float | None) -> float | None:
    if value is None or reference in (None, 0):
        return None
    return round(abs(float(value) - float(reference)) / abs(float(reference)), 6)


def _edge_counts(mesh) -> dict[tuple[int, int], int]:
    triangles = np.asarray(mesh.triangles, dtype=int)
    counts: dict[tuple[int, int], int] = {}
    for tri in triangles:
        for a, b in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])):
            edge = tuple(sorted((int(a), int(b))))
            counts[edge] = counts.get(edge, 0) + 1
    return counts


def _boundary_loops(mesh) -> list[list[int]]:
    boundary_edges = [edge for edge, count in _edge_counts(mesh).items() if count == 1]
    adjacency: dict[int, list[int]] = {}
    for a, b in boundary_edges:
        adjacency.setdefault(a, []).append(b)
        adjacency.setdefault(b, []).append(a)

    unused = set(boundary_edges)
    loops: list[list[int]] = []
    while unused:
        start, nxt = unused.pop()
        loop = [start, nxt]
        previous = start
        current = nxt
        while current != start:
            candidates = [v for v in adjacency.get(current, []) if v != previous]
            if not candidates:
                break
            following = candidates[0]
            edge = tuple(sorted((current, following)))
            if edge not in unused and following != start:
                break
            if edge in unused:
                unused.remove(edge)
            previous, current = current, following
            if current != start:
                loop.append(current)
            if len(loop) > len(boundary_edges) + 1:
                break
        loops.append(loop)
    return loops


def _classify_boundary_loops(mesh) -> dict:
    vertices = np.asarray(mesh.vertices, dtype=float)
    bbox = mesh.get_axis_aligned_bounding_box()
    extent = np.asarray(bbox.get_extent(), dtype=float)
    diagonal = float(np.linalg.norm(extent))
    loops = _boundary_loops(mesh)
    edge_counts = _edge_counts(mesh)
    boundary_degree: dict[int, int] = {}
    for (a, b), count in edge_counts.items():
        if count == 1:
            boundary_degree[a] = boundary_degree.get(a, 0) + 1
            boundary_degree[b] = boundary_degree.get(b, 0) + 1
    classified = []
    totals: dict[str, int] = {}

    for index, loop in enumerate(loops):
        pts = vertices[loop]
        loop_extent = pts.max(axis=0) - pts.min(axis=0)
        perimeter = 0.0
        for current, following in zip(loop, loop[1:] + loop[:1]):
            perimeter += float(np.linalg.norm(vertices[current] - vertices[following]))
        closure_distance = float(np.linalg.norm(vertices[loop[0]] - vertices[loop[-1]])) if len(loop) > 1 else 0.0
        degree_values = [boundary_degree.get(vertex, 0) for vertex in loop]
        touches_bbox = bool(np.any(np.isclose(pts, vertices.min(axis=0), atol=max(diagonal * 0.002, 1e-6))) or np.any(np.isclose(pts, vertices.max(axis=0), atol=max(diagonal * 0.002, 1e-6))))

        if len(loop) >= 3 and perimeter <= max(diagonal * 0.08, 0.15):
            category = "hueco_pequeno_cerrable"
        elif touches_bbox and perimeter >= max(diagonal * 0.15, 0.4):
            category = "borde_real_del_objeto_o_corte_de_captura"
        elif max(degree_values or [0]) > 2 or closure_distance > max(diagonal * 0.03, 0.05):
            category = "discontinuidad_estructural"
        else:
            category = "error_de_reconstruccion"

        totals[category] = totals.get(category, 0) + 1
        classified.append(
            {
                "loop": index,
                "category": category,
                "edge_count": len(loop),
                "perimeter_m": round(perimeter, 4),
                "extent_m": [round(float(v), 4) for v in loop_extent.tolist()],
                "closure_distance_m": round(closure_distance, 4),
                "touches_bbox_extreme": touches_bbox,
            }
        )

    return {
        "boundary_loop_count": len(loops),
        "category_counts": totals,
        "loops": classified,
    }


def _mesh_png(name: str, mesh, title: str) -> str | None:
    points = np.asarray(mesh.vertices)
    if points.size == 0:
        return None
    pairs = {"xy": (0, 1), "xz": (0, 2), "yz": (1, 2)}
    img = Image.new("RGB", (900, 300), "white")
    draw = ImageDraw.Draw(img)
    for panel_index, (label, (a, b)) in enumerate(pairs.items()):
        x0 = panel_index * 300
        sub = points[:, [a, b]]
        mins = sub.min(axis=0)
        span = np.maximum(sub.max(axis=0) - mins, 1e-9)
        norm = (sub - mins) / span
        px = (norm[:, 0] * 276 + x0 + 12).astype(int)
        py = ((1.0 - norm[:, 1]) * 264 + 24).astype(int)
        step = max(1, len(px) // 50000)
        for x, y in zip(px[::step], py[::step]):
            draw.point((int(x), int(y)), fill=(120, 35, 35))
        draw.rectangle([x0 + 8, 20, x0 + 292, 292], outline=(30, 30, 30))
        draw.text((x0 + 12, 6), f"{title} {label.upper()}", fill=(0, 0, 0))
    path = OUTPUT_DIR / name
    img.save(path)
    return str(path)


def _snapshot(o3d, key: str, mesh, reference_mesh=None) -> dict:
    ply_path = OUTPUT_DIR / f"{key}.ply"
    o3d.io.write_triangle_mesh(str(ply_path), mesh, write_ascii=False, compressed=False)
    metrics = mesh_service._mesh_topology_metrics(mesh)
    acceptance = mesh_service._mesh_acceptance_evaluation(o3d, mesh, reference_mesh=reference_mesh)
    boundary = _classify_boundary_loops(mesh)
    return {
        "surface": key,
        "artifact": str(ply_path),
        "preview": _mesh_png(f"{key}.png", mesh, key),
        "metrics": metrics,
        "acceptance": acceptance,
        "boundary_classification": boundary,
    }


def _prepare_mesh_input(o3d, session: dict):
    mesh_cfg = session["mesh"]["point_cloud_quality"]["segmentation"]
    scale_cfg = session["mesh"]["point_cloud_quality"]["scale"]
    cloud = mesh_service._load_point_cloud(o3d, POINT_CLOUD_PATH)
    cloud.scale(float(scale_cfg["point_cloud_scale_m_per_unit"]), center=(0.0, 0.0, 0.0))
    cloud = mesh_service._clean_point_cloud(
        cloud,
        voxel_size_m=None,
        outlier_neighbors=24,
        outlier_std_ratio=2.0,
        min_retained_ratio=0.70,
    )
    clustering_cloud = cloud.voxel_down_sample(float(mesh_cfg["voxel_size_m"]))
    labels = np.asarray(
        clustering_cloud.cluster_dbscan(
            eps=float(mesh_cfg["cluster_eps_m"]),
            min_points=int(mesh_cfg["cluster_min_points"]),
            print_progress=False,
        )
    )
    selected_labels = [int(v) for v in mesh_cfg["selected_labels"]]
    selected_indices = np.where(np.isin(labels, selected_labels))[0]
    mesh_input = clustering_cloud.select_by_index(selected_indices.tolist())
    mesh_service._prepare_normals(
        o3d,
        mesh_input,
        normal_radius_m=0.05,
        normal_max_nn=48,
        recompute_normals=True,
    )
    return mesh_input


def _compare_surfaces(surfaces: list[dict]) -> list[dict]:
    raw = surfaces[0]["metrics"]
    rows = []
    for surface in surfaces:
        metrics = surface["metrics"]
        rows.append(
            {
                "surface": surface["surface"],
                "watertight": metrics["watertight"],
                "volume_m3": metrics["volume_m3"],
                "surface_area_m2": metrics["surface_area_m2"],
                "surface_volume_ratio": metrics["surface_volume_ratio"],
                "bbox_m": metrics["bounding_box_m"],
                "bbox_volume_m3": metrics["bbox_volume_m3"],
                "bbox_volume_delta_vs_raw": _relative_delta(metrics["bbox_volume_m3"], raw["bbox_volume_m3"]),
                "surface_area_delta_vs_raw": _relative_delta(metrics["surface_area_m2"], raw["surface_area_m2"]),
                "volume_delta_vs_raw": _relative_delta(metrics["volume_m3"], raw["volume_m3"]),
                "boundary_edges": metrics["boundary_edges"],
                "components": metrics["components"],
                "dominant_triangle_percentage": surface["acceptance"]["dominant_triangle_percentage"],
                "accepted_by_final_surface_criteria": surface["acceptance"]["accepted"],
                "rejection_reasons": surface["acceptance"]["reasons"],
            }
        )
    return rows


def _architecture_decision(comparison: list[dict]) -> dict:
    accepted = [row for row in comparison if row["accepted_by_final_surface_criteria"]]
    if accepted:
        selected = accepted[0]["surface"]
        return {
            "decision": "calculate_volume_from_poisson_derived_closed_surface",
            "selected_surface": selected,
            "alpha_shape_role": "baseline_only",
            "poisson_vertex_hull_role": "diagnostic_only",
            "reason": "accepted_by_topology_component_bbox_and_surface_volume_criteria_without_alpha_primary_fallback",
        }

    return {
        "decision": "do_not_publish_volume_until_hybrid_surface_is_implemented",
        "selected_surface": None,
        "recommended_strategy": "dominant_poisson_component_with_controlled_boundary_loop_filling_then_acceptance_metrics",
        "alpha_shape_role": "baseline_only_not_primary",
        "poisson_vertex_hull_role": "rejected_as_global_envelope_if_shape_metrics_drift",
        "reason": "no_surface_satisfied_closure_and_shape_preservation_criteria",
    }


def main() -> None:
    global OUTPUT_DIR
    OUTPUT_DIR = _new_output_dir()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=False)

    session = json.loads(SESSION_PATH.read_text(encoding="utf-8"))
    o3d = mesh_service._require_open3d()
    mesh_input = _prepare_mesh_input(o3d, session)
    o3d.io.write_point_cloud(str(OUTPUT_DIR / "poisson_input_cloud.ply"), mesh_input, write_ascii=False, compressed=False)

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

    vertex_hull = mesh_service._poisson_vertex_hull(o3d, poisson_recovered)
    alpha_shape, alpha_m = mesh_service._alpha_shape_mesh(
        o3d,
        mesh_input,
        alpha_min_m=1.5,
        alpha_max_m=3.0,
        alpha_extent_ratio=0.52,
    )

    surfaces = [
        _snapshot(o3d, "poisson_raw", poisson_raw),
        _snapshot(o3d, "poisson_recovered", poisson_recovered, reference_mesh=poisson_raw),
        _snapshot(o3d, "poisson_controlled_hole_fill", filled, reference_mesh=poisson_raw),
    ]
    if vertex_hull is not None:
        surfaces.append(_snapshot(o3d, "poisson_vertex_hull_legacy_recovery", vertex_hull, reference_mesh=poisson_raw))
    if alpha_shape is not None:
        surfaces.append(_snapshot(o3d, "alpha_shape_baseline", alpha_shape, reference_mesh=poisson_raw))

    comparison = _compare_surfaces(surfaces)
    report = {
        "session_id": SESSION_ID,
        "output_dir": str(OUTPUT_DIR),
        "constraints": {
            "ground_truth_used_for_acceptance": False,
            "gcp_or_calibration_modified": False,
            "segmentation_rerun": False,
            "alpha_shape_primary_solution": False,
        },
        "parameters": {
            "poisson_depth": 8,
            "density_quantile": 0.01,
            "alpha_m": None if alpha_m is None else round(float(alpha_m), 4),
        },
        "repair_cycles": repair_cycles,
        "poisson_recovery_report": recovery_report,
        "controlled_fill_steps": fill_steps,
        "surfaces": surfaces,
        "comparison_table": comparison,
        "strategy_evaluation": {
            "controlled_hole_filling": "preferred_when_boundary_loops_are_small_closed_and_bbox_surface_area_drift_stays_below_acceptance_thresholds",
            "constrained_surface_reconstruction": "candidate_next_step_when_poisson_has_structural_discontinuities_but_dominant_component_is_stable",
            "smoothing_remesh_preserve_local_volume": "secondary_cleanup_after_closure_not_a_closure_strategy_by_itself",
            "isotropic_remeshing_before_closure": "useful_for_regularizing_triangles_but_risky_if_it_moves_open_boundaries_before_classification",
        },
        "acceptance_criteria": surfaces[0]["acceptance"]["criteria"],
        "architecture_decision": _architecture_decision(comparison),
    }
    (OUTPUT_DIR / "surface_closure_diagnostics.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"output_dir": str(OUTPUT_DIR), "architecture_decision": report["architecture_decision"]}, indent=2))


if __name__ == "__main__":
    main()
