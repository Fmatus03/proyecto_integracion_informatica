from __future__ import annotations

import csv
import json
import os
import time
from collections import Counter, defaultdict, deque
from pathlib import Path

import numpy as np
import open3d as o3d
from scipy import ndimage
from scipy.spatial import ConvexHull, cKDTree

from experiments.cloud_unification.cloud_provider_adapter import load_dataset_cloud_source


ROOT = Path(os.environ.get("VOLUME_BENCHMARK_ROOT") or "/app")
OUT = Path(os.environ.get("VOLUME_BENCHMARK_OUT") or ROOT / "data/volume_estimator_benchmark")
GT_VOLUME_M3 = float(os.environ.get("VOLUME_BENCHMARK_GT_M3") or "119.74")
VOXEL_SIZE_M = float(os.environ.get("VOLUME_BENCHMARK_VOXEL_SIZE_M") or "0.25")
NOISE_TRIALS = int(os.environ.get("VOLUME_BENCHMARK_NOISE_TRIALS") or "5")

DATASETS = {
    "set1": {
        "cloud": load_dataset_cloud_source("set1").path,
        "poisson": None,
        "tsdf_grid": None,
    },
    "set2": {
        "cloud": load_dataset_cloud_source("set2").path,
        "poisson": None,
        "tsdf_grid": None,
    },
}


def read_cloud(path: Path) -> np.ndarray:
    cloud = o3d.io.read_point_cloud(str(path))
    points = np.asarray(cloud.points, dtype=np.float64)
    return points[np.all(np.isfinite(points), axis=1)]


def median_nn(points: np.ndarray) -> float:
    sample = points
    if len(sample) > 8000:
        sample = sample[np.linspace(0, len(sample) - 1, 8000).astype(int)]
    distances, _ = cKDTree(sample).query(sample, k=2, workers=-1)
    vals = distances[:, 1]
    vals = vals[np.isfinite(vals) & (vals > 0)]
    return float(np.median(vals)) if len(vals) else VOXEL_SIZE_M


def edge_counts(mesh: o3d.geometry.TriangleMesh) -> Counter:
    faces = np.asarray(mesh.triangles, dtype=np.int64)
    if len(faces) == 0:
        return Counter()
    edges = np.sort(np.vstack((faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]])), axis=1)
    return Counter(map(tuple, edges.tolist()))


def component_count(mesh: o3d.geometry.TriangleMesh) -> int:
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


def topology(mesh: o3d.geometry.TriangleMesh | None) -> dict:
    if mesh is None:
        return {"components": None, "boundary_edges": None, "non_manifold_edges": None, "non_manifold_vertices": None, "watertight": None, "orientable": None}
    edges = edge_counts(mesh)
    return {
        "components": component_count(mesh),
        "boundary_edges": int(sum(1 for c in edges.values() if c == 1)),
        "non_manifold_edges": int(sum(1 for c in edges.values() if c > 2)),
        "non_manifold_vertices": int(len(mesh.get_non_manifold_vertices())) if len(mesh.vertices) else 0,
        "watertight": bool(mesh.is_watertight()) if len(mesh.triangles) else False,
        "orientable": bool(mesh.is_orientable()) if len(mesh.triangles) else False,
    }


def error_metrics(volume: float | None) -> tuple[float | None, float | None]:
    if volume is None or not np.isfinite(volume):
        return None, None
    absolute = abs(float(volume) - GT_VOLUME_M3)
    return round(absolute, 6), round((absolute / GT_VOLUME_M3) * 100.0, 6)


def occupancy_grid(points: np.ndarray, voxel_size: float) -> tuple[np.ndarray, np.ndarray]:
    origin = points.min(axis=0) - 4 * voxel_size
    dims = np.ceil((points.max(axis=0) + 4 * voxel_size - origin) / voxel_size).astype(int) + 1
    idx = np.floor((points - origin) / voxel_size).astype(np.int32)
    grid = np.zeros(tuple(dims.tolist()), dtype=bool)
    grid[idx[:, 0], idx[:, 1], idx[:, 2]] = True
    return grid, origin


def solid_from_occupancy(occupancy: np.ndarray) -> np.ndarray:
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
    return solid


def estimate_convex_hull(points: np.ndarray, cfg: dict) -> tuple[float | None, dict, o3d.geometry.TriangleMesh | None]:
    cloud = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(points))
    mesh, _ = cloud.compute_convex_hull()
    mesh.compute_vertex_normals()
    volume = float(mesh.get_volume()) if mesh.is_watertight() else float(ConvexHull(points).volume)
    return volume, {"implementation": "Open3D convex hull"}, mesh


def estimate_alpha_shape(points: np.ndarray, cfg: dict) -> tuple[float | None, dict, o3d.geometry.TriangleMesh | None]:
    alpha = max(median_nn(points) * 3.0, 0.05)
    cloud = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(points))
    mesh = o3d.geometry.TriangleMesh.create_from_point_cloud_alpha_shape(cloud, alpha)
    mesh.remove_duplicated_vertices()
    mesh.remove_degenerate_triangles()
    mesh.remove_unreferenced_vertices()
    mesh.orient_triangles()
    volume = float(mesh.get_volume()) if len(mesh.triangles) and mesh.is_watertight() else None
    return volume, {"alpha_m": round(float(alpha), 6), "alpha_source": "3 * median nearest-neighbor distance; no GT tuning"}, mesh


def estimate_voxel(points: np.ndarray, cfg: dict) -> tuple[float | None, dict, None]:
    occupancy, _ = occupancy_grid(points, VOXEL_SIZE_M)
    solid = solid_from_occupancy(occupancy)
    return float(np.count_nonzero(solid) * (VOXEL_SIZE_M ** 3)), {"voxel_size_m": VOXEL_SIZE_M, "solid_voxels": int(np.count_nonzero(solid))}, None


def estimate_octree(points: np.ndarray, cfg: dict) -> tuple[float | None, dict, None]:
    coarse_size = VOXEL_SIZE_M * 2.0
    coarse, coarse_origin = occupancy_grid(points, coarse_size)
    coarse_solid = solid_from_occupancy(coarse)
    volume = 0.0
    refined = 0
    for parent in np.argwhere(coarse_solid):
        pmin = coarse_origin + parent.astype(float) * coarse_size
        pmax = pmin + coarse_size
        local = points[np.all((points >= pmin) & (points < pmax), axis=1)]
        if len(local) >= 4:
            fine, _ = occupancy_grid(local, VOXEL_SIZE_M)
            volume += np.count_nonzero(solid_from_occupancy(fine)) * (VOXEL_SIZE_M ** 3)
            refined += 1
        else:
            volume += coarse_size ** 3
    return volume, {"coarse_voxel_size_m": coarse_size, "fine_voxel_size_m": VOXEL_SIZE_M, "refined_parent_voxels": refined}, None


def estimate_poisson(points: np.ndarray, cfg: dict) -> tuple[float | None, dict, o3d.geometry.TriangleMesh | None]:
    if not cfg.get("poisson"):
        return None, {"source": None, "reason": "No canonical production mesh artifact exists for this point cloud."}, None
    mesh = o3d.io.read_triangle_mesh(str(cfg["poisson"]))
    volume = float(mesh.get_volume()) if mesh.is_watertight() else None
    return volume, {"source": str(cfg["poisson"]), "volume_requires_watertight_mesh": True}, mesh


def estimate_tsdf(points: np.ndarray, cfg: dict) -> tuple[float | None, dict, None]:
    if not cfg.get("tsdf_grid"):
        return None, {"source": None, "reason": "No canonical production TSDF grid exists for this point cloud."}, None
    data = np.load(cfg["tsdf_grid"])
    grid = data["sdf"] if "sdf" in data.files else data["tsdf"]
    step = float(data["grid_step_m"]) if "grid_step_m" in data.files else VOXEL_SIZE_M
    inside = np.asarray(grid) < 0.0
    labels, count = ndimage.label(inside, structure=ndimage.generate_binary_structure(3, 2))
    if count > 1:
        sizes = np.bincount(labels.ravel())
        sizes[0] = 0
        inside = labels == int(np.argmax(sizes))
    return float(np.count_nonzero(inside) * (step ** 3)), {"grid_step_m": step, "inside_voxels": int(np.count_nonzero(inside))}, None


def estimate_density(points: np.ndarray, cfg: dict) -> tuple[float | None, dict, None]:
    hull_volume = float(ConvexHull(points).volume)
    hull_density = len(points) / hull_volume if hull_volume > 0 else 0.0
    occupancy, origin = occupancy_grid(points, VOXEL_SIZE_M)
    counts = np.zeros_like(occupancy, dtype=np.int32)
    idx = np.floor((points - origin) / VOXEL_SIZE_M).astype(np.int32)
    np.add.at(counts, (idx[:, 0], idx[:, 1], idx[:, 2]), 1)
    threshold = max(1, int(np.ceil(hull_density * (VOXEL_SIZE_M ** 3) * 0.35)))
    dense = counts >= threshold
    solid = solid_from_occupancy(dense)
    return float(np.count_nonzero(solid) * (VOXEL_SIZE_M ** 3)), {"density_threshold_points_per_voxel": threshold, "hull_density_points_per_m3": round(float(hull_density), 6)}, None


METHODS = {
    "Convex Hull": estimate_convex_hull,
    "Alpha Shape": estimate_alpha_shape,
    "Voxel Occupancy": estimate_voxel,
    "Octree Occupancy": estimate_octree,
    "Surface Mesh (Poisson)": estimate_poisson,
    "TSDF Occupancy": estimate_tsdf,
    "Point Density Integration": estimate_density,
}


def run_method(method: str, points: np.ndarray, cfg: dict) -> dict:
    start = time.perf_counter()
    try:
        volume, params, mesh = METHODS[method](points, cfg)
        status = "ok" if volume is not None else "volume_unavailable"
        failure = None
    except Exception as exc:  # noqa: BLE001
        volume, params, mesh = None, {}, None
        status = "failed"
        failure = f"{type(exc).__name__}: {exc}"
    elapsed = time.perf_counter() - start
    abs_error, pct_error = error_metrics(volume)
    return {
        "method": method,
        "status": status,
        "volume_m3": None if volume is None else round(float(volume), 6),
        "absolute_error_m3": abs_error,
        "percent_error": pct_error,
        "execution_time_seconds": round(float(elapsed), 6),
        "approx_memory_mb": None,
        "memory_note": "Peak memory not measured; no profiler added.",
        "parameters": params,
        "failure": failure,
        **topology(mesh),
    }


def noise_sensitivity(method: str, points: np.ndarray, cfg: dict, sigma: float) -> dict:
    volumes = []
    for trial in range(NOISE_TRIALS):
        rng = np.random.default_rng(1000 + trial)
        result = run_method(method, points + rng.normal(0.0, sigma, points.shape), cfg)
        if result["volume_m3"] is not None:
            volumes.append(float(result["volume_m3"]))
    if not volumes:
        return {"noise_sigma_m": round(float(sigma), 6), "trials": NOISE_TRIALS, "valid_trials": 0, "volume_std_m3": None, "volume_range_m3": None}
    arr = np.asarray(volumes, dtype=float)
    return {
        "noise_sigma_m": round(float(sigma), 6),
        "trials": NOISE_TRIALS,
        "valid_trials": int(len(arr)),
        "volume_mean_m3": round(float(arr.mean()), 6),
        "volume_std_m3": round(float(arr.std(ddof=1)), 6) if len(arr) > 1 else 0.0,
        "volume_range_m3": round(float(arr.max() - arr.min()), 6),
    }


def write_csv(path: Path, rows: list[dict]) -> None:
    fields = ["dataset", "method", "status", "volume_m3", "absolute_error_m3", "percent_error", "execution_time_seconds", "approx_memory_mb", "noise_volume_std_m3", "noise_volume_range_m3", "cross_set_volume_delta_m3", "cross_set_volume_delta_pct", "components", "boundary_edges", "non_manifold_edges", "non_manifold_vertices", "watertight", "orientable"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field) for field in fields})


def write_markdown(path: Path, report: dict) -> None:
    lines = [
        "# Volume Estimator Benchmark\n\n",
        f"Ground Truth: `{GT_VOLUME_M3} m3`\n\n",
        "| Dataset | Method | Volume | Abs Error | % Error | Time s | Noise Std | Cross-set Delta | Components | Boundary | Watertight |\n",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|\n",
    ]
    for row in report["rows"]:
        lines.append("| {dataset} | {method} | {volume_m3} | {absolute_error_m3} | {percent_error} | {execution_time_seconds} | {noise_volume_std_m3} | {cross_set_volume_delta_m3} | {components} | {boundary_edges} | {watertight} |\n".format(**row))
    lines.extend([
        "\n## Recommendation\n\n",
        f"- Best by mean percent error: `{report['recommendation']['best_by_mean_percent_error']}`.\n",
        f"- Mean percent error: `{report['recommendation']['mean_percent_error']}`.\n",
        f"- Mean execution time: `{report['recommendation']['mean_execution_time_seconds']} s`.\n",
        f"- Rationale: {report['recommendation']['rationale']}\n\n",
        "## Notes\n\n",
        "- Ground Truth was used only for final error calculation.\n",
        "- No main pipeline code was modified.\n",
        "- Memory is recorded as null because no profiler was added.\n",
    ])
    path.write_text("".join(lines), encoding="utf-8")


def write_plots(out: Path, rows: list[dict]) -> list[str]:
    try:
        import matplotlib.pyplot as plt
    except Exception:
        return []
    paths = []
    methods = list(METHODS)
    for dataset in DATASETS:
        values = []
        for method in methods:
            match = next((row for row in rows if row["dataset"] == dataset and row["method"] == method), None)
            values.append(np.nan if match is None or match["percent_error"] is None else match["percent_error"])
        fig, ax = plt.subplots(figsize=(12, 5))
        ax.bar(methods, values)
        ax.set_ylabel("Percent error vs Ground Truth")
        ax.set_title(f"Volume estimator percent error - {dataset}")
        ax.tick_params(axis="x", rotation=35)
        fig.tight_layout()
        path = out / f"{dataset}_volume_error.png"
        fig.savefig(path)
        plt.close(fig)
        paths.append(str(path))
    return paths


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    datasets = {}
    for dataset, cfg in DATASETS.items():
        points = read_cloud(cfg["cloud"])
        sigma = max(median_nn(points) * 0.5, 0.005)
        datasets[dataset] = {"input_cloud": str(cfg["cloud"]), "point_count": int(len(points)), "noise_sigma_m": round(float(sigma), 6), "methods": []}
        for method in METHODS:
            result = run_method(method, points, cfg)
            sensitivity = noise_sensitivity(method, points, cfg, sigma)
            result.update({
                "dataset": dataset,
                "ground_truth_m3": GT_VOLUME_M3,
                "noise_sensitivity": sensitivity,
                "noise_volume_std_m3": sensitivity.get("volume_std_m3"),
                "noise_volume_range_m3": sensitivity.get("volume_range_m3"),
            })
            datasets[dataset]["methods"].append(result)
            rows.append(result)
    by_method = defaultdict(dict)
    for row in rows:
        by_method[row["method"]][row["dataset"]] = row
    stability = {}
    for method, items in by_method.items():
        vols = [items.get(ds, {}).get("volume_m3") for ds in ("set1", "set2")]
        if all(vol is not None for vol in vols):
            delta = abs(float(vols[0]) - float(vols[1]))
            stability[method] = {"cross_set_volume_delta_m3": round(delta, 6), "cross_set_volume_delta_pct": round((delta / GT_VOLUME_M3) * 100.0, 6)}
        else:
            stability[method] = {"cross_set_volume_delta_m3": None, "cross_set_volume_delta_pct": None}
    for row in rows:
        row.update(stability[row["method"]])
    valid = []
    for method, items in by_method.items():
        errors = [items.get(ds, {}).get("percent_error") for ds in ("set1", "set2")]
        times = [items.get(ds, {}).get("execution_time_seconds") for ds in ("set1", "set2")]
        if all(error is not None for error in errors):
            valid.append((method, float(np.mean(errors)), float(np.mean(times))))
    valid.sort(key=lambda item: (item[1], item[2]))
    best_method, best_error, best_time = valid[0] if valid else (None, None, None)
    report = {
        "run_id": "VOLUME-ESTIMATORS-BENCHMARK-01",
        "ground_truth_m3": GT_VOLUME_M3,
        "constraints": {"main_pipeline_modified": False, "ground_truth_used_for_parameter_tuning": False, "same_input_per_dataset": True},
        "parameters": {"voxel_size_m": VOXEL_SIZE_M, "noise_trials": NOISE_TRIALS},
        "datasets": datasets,
        "rows": rows,
        "stability_between_sets": stability,
        "recommendation": {
            "best_by_mean_percent_error": best_method,
            "mean_percent_error": None if best_error is None else round(best_error, 6),
            "mean_execution_time_seconds": None if best_time is None else round(best_time, 6),
            "rationale": "Selected strictly by lowest mean percent error across Set 1 and Set 2; runtime is secondary context.",
        },
    }
    write_csv(OUT / "benchmark_volume_estimators.csv", rows)
    write_markdown(OUT / "benchmark_volume_estimators.md", report)
    report["plots"] = write_plots(OUT, rows)
    (OUT / "benchmark_volume_estimators.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"out": str(OUT), "best_method": best_method, "mean_percent_error": report["recommendation"]["mean_percent_error"]}, indent=2))


if __name__ == "__main__":
    main()
