from __future__ import annotations

import csv
import json
import math
import os
import platform
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

os.environ.setdefault("MPLCONFIGDIR", str(Path(__file__).resolve().parent / ".mplconfig"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import open3d as o3d
from scipy import ndimage
from scipy.spatial import ConvexHull, cKDTree


ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent

RAW_CLOUD = ROOT / "projects/ForestVol/data/processed/971d6e25-8ff0-41d2-8784-c981dec7ccbf/point_cloud.ply"
VOLUME_INPUT_CLOUD = ROOT / "experiments/volume_input_audit/selected_volume_cloud.ply"
SELECTION_METRICS = ROOT / "experiments/volume_input_audit/selection_metrics.json"
GT_VOLUME_M3 = 119.74
CURRENT_PIPELINE_VOLUME_M3 = 234.0469
SCALE_FACTOR = 0.54611448
COMMON_VOXEL_M = 0.06
PDI_VOXEL_M = 0.25
RNG = np.random.default_rng(20260702)


@dataclass
class Candidate:
    algorithm: str
    params: dict
    points: np.ndarray
    complexity: int
    seconds: float


def read_scaled_raw() -> np.ndarray:
    cloud = o3d.io.read_point_cloud(str(RAW_CLOUD))
    pts = np.asarray(cloud.points, dtype=np.float64)
    if len(pts) == 0:
        raise RuntimeError(f"No se pudo leer la nube RAW: {RAW_CLOUD}")
    return pts * SCALE_FACTOR


def read_volume_input() -> np.ndarray:
    cloud = o3d.io.read_point_cloud(str(VOLUME_INPUT_CLOUD))
    pts = np.asarray(cloud.points, dtype=np.float64)
    if len(pts) == 0:
        raise RuntimeError(f"No se pudo leer la nube de volumetria: {VOLUME_INPUT_CLOUD}")
    return pts


def write_cloud(path: Path, points: np.ndarray, colors: np.ndarray | None = None) -> None:
    cloud = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(points))
    if colors is not None:
        cloud.colors = o3d.utility.Vector3dVector(colors)
    o3d.io.write_point_cloud(str(path), cloud, write_ascii=False)


def downsample(points: np.ndarray, voxel: float) -> np.ndarray:
    cloud = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(points))
    ds = cloud.voxel_down_sample(voxel)
    return np.asarray(ds.points, dtype=np.float64)


def pdi_volume(points: np.ndarray, voxel_size: float = PDI_VOXEL_M) -> dict:
    if len(points) < 4:
        return {"volume_m3": math.inf, "hull_volume_m3": math.inf, "solid_voxels": 0, "dense_voxels": 0}
    hull_volume = float(ConvexHull(points).volume)
    hull_density = len(points) / hull_volume if hull_volume > 0 else 0.0
    mn = points.min(axis=0) - 4 * voxel_size
    idx = np.floor((points - mn) / voxel_size).astype(np.int32)
    shape = np.ceil((points.max(axis=0) + 4 * voxel_size - mn) / voxel_size).astype(int) + 1
    if np.prod(shape, dtype=np.int64) > 60_000_000:
        return {"volume_m3": math.inf, "hull_volume_m3": hull_volume, "solid_voxels": 0, "dense_voxels": 0}
    occupancy = np.zeros(tuple(shape), dtype=bool)
    counts = np.zeros(tuple(shape), dtype=np.int32)
    occupancy[idx[:, 0], idx[:, 1], idx[:, 2]] = True
    np.add.at(counts, (idx[:, 0], idx[:, 1], idx[:, 2]), 1)
    threshold = max(1, int(np.ceil(hull_density * (voxel_size**3) * 0.35)))
    dense = counts >= threshold
    structure = ndimage.generate_binary_structure(3, 2)
    shell = ndimage.binary_dilation(dense, structure=structure, iterations=2)
    solid = ndimage.binary_fill_holes(shell)
    solid = ndimage.binary_closing(solid, structure=structure, iterations=1)
    solid = ndimage.binary_fill_holes(solid)
    labels, count = ndimage.label(solid, structure=structure)
    if count > 1:
        sizes = np.bincount(labels.ravel())
        sizes[0] = 0
        solid = labels == int(np.argmax(sizes))
    return {
        "volume_m3": round(float(np.count_nonzero(solid) * (voxel_size**3)), 4),
        "hull_volume_m3": round(hull_volume, 6),
        "solid_voxels": int(np.count_nonzero(solid)),
        "dense_voxels": int(np.count_nonzero(dense)),
        "density_threshold_points_per_voxel": threshold,
    }


def component_count(points: np.ndarray, eps: float = 0.35) -> tuple[int, list[int]]:
    if len(points) == 0:
        return 0, []
    cloud = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(points))
    labels = np.asarray(cloud.cluster_dbscan(eps=eps, min_points=3, print_progress=False))
    vals = labels[labels >= 0]
    if len(vals) == 0:
        return 0, []
    sizes = np.bincount(vals)
    return int(len(sizes)), sorted([int(x) for x in sizes], reverse=True)


def pca_frame(points: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    center = points.mean(axis=0)
    centered = points - center
    cov = np.cov(centered.T)
    vals, vecs = np.linalg.eigh(cov)
    order = np.argsort(vals)[::-1]
    axes = vecs[:, order]
    local = centered @ axes
    return center, axes, local


def crop_to_volume_universe(raw: np.ndarray) -> np.ndarray:
    metrics = json.loads(SELECTION_METRICS.read_text(encoding="utf-8"))
    box = metrics["components"][0]["bbox"]
    mn = np.asarray(box["min"], dtype=float) - np.array([1.5, 1.5, 1.0])
    mx = np.asarray(box["max"], dtype=float) + np.array([1.5, 1.5, 1.0])
    mask = np.all((raw >= mn) & (raw <= mx), axis=1)
    return raw[mask]


def keep_largest_component(points: np.ndarray, eps: float = 0.35) -> np.ndarray:
    if len(points) < 4:
        return points
    cloud = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(points))
    labels = np.asarray(cloud.cluster_dbscan(eps=eps, min_points=3, print_progress=False))
    valid = labels >= 0
    if not valid.any():
        return points
    sizes = np.bincount(labels[valid])
    best = int(np.argmax(sizes))
    return points[labels == best]


def filter_center_percentile(points: np.ndarray, pct: float) -> np.ndarray:
    c = np.median(points, axis=0)
    d = np.linalg.norm(points - c, axis=1)
    return points[d <= np.percentile(d, pct)]


def filter_obb_shrink(points: np.ndarray, pct: float) -> np.ndarray:
    center, axes, local = pca_frame(points)
    keep = np.ones(len(points), dtype=bool)
    for axis in range(3):
        lo, hi = np.percentile(local[:, axis], [(100 - pct) / 2, 100 - (100 - pct) / 2])
        keep &= (local[:, axis] >= lo) & (local[:, axis] <= hi)
    return points[keep]


def filter_density(points: np.ndarray, pct: float, radius: float = 0.20) -> np.ndarray:
    tree = cKDTree(points)
    counts = np.asarray([len(x) - 1 for x in tree.query_ball_point(points, radius)], dtype=np.int32)
    return points[counts >= np.percentile(counts, pct)]


def local_curvature(points: np.ndarray, k: int = 20) -> np.ndarray:
    tree = cKDTree(points)
    kk = min(k + 1, len(points))
    _, idx = tree.query(points, k=kk)
    neigh = points[idx[:, 1:]]
    centered = neigh - points[:, None, :]
    cov = np.einsum("nki,nkj->nij", centered, centered) / max(1, kk - 1)
    eig = np.linalg.eigvalsh(cov)
    eig = np.maximum(eig, 1e-12)
    return eig[:, 0] / eig.sum(axis=1)


def filter_curvature(points: np.ndarray, max_pct: float) -> np.ndarray:
    curv = local_curvature(points, 20)
    return points[curv <= np.percentile(curv, max_pct)]


def filter_normal_consistency(points: np.ndarray, pct: float, radius: float = 0.35) -> np.ndarray:
    cloud = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(points))
    cloud.estimate_normals(search_param=o3d.geometry.KDTreeSearchParamHybrid(radius=radius, max_nn=40))
    normals = np.asarray(cloud.normals)
    tree = cKDTree(points)
    idxs = tree.query_ball_point(points, radius)
    score = np.zeros(len(points))
    for i, idx in enumerate(idxs):
        if len(idx) <= 2:
            score[i] = 0
        else:
            score[i] = float(np.mean(np.abs(normals[idx] @ normals[i])))
    return points[score >= np.percentile(score, pct)]


def filter_thickness(points: np.ndarray, min_pct: float, k: int = 24) -> np.ndarray:
    tree = cKDTree(points)
    kk = min(k + 1, len(points))
    _, idx = tree.query(points, k=kk)
    neigh = points[idx[:, 1:]]
    centered = neigh - points[:, None, :]
    cov = np.einsum("nki,nkj->nij", centered, centered) / max(1, kk - 1)
    eig = np.linalg.eigvalsh(cov)
    thickness = np.sqrt(np.maximum(eig[:, 0], 0))
    return points[thickness >= np.percentile(thickness, min_pct)]


def filter_fine_branches(points: np.ndarray, radial_pct: float, end_pct: float) -> np.ndarray:
    _, _, local = pca_frame(points)
    axis = local[:, 0]
    radial = np.linalg.norm(local[:, 1:3], axis=1)
    end_limit = np.percentile(np.abs(axis), end_pct)
    radial_limit = np.percentile(radial, radial_pct)
    remove = (np.abs(axis) >= end_limit) & (radial <= radial_limit)
    return points[~remove]


def filter_compactness(points: np.ndarray, pct: float) -> np.ndarray:
    center, axes, local = pca_frame(points)
    scale = np.percentile(np.abs(local), 90, axis=0)
    scale = np.maximum(scale, 1e-6)
    score = np.sum((local / scale) ** 2, axis=1)
    return points[score <= np.percentile(score, pct)]


def morphological_opening(points: np.ndarray, voxel: float, iterations: int) -> np.ndarray:
    mn = points.min(axis=0) - voxel
    idx = np.floor((points - mn) / voxel).astype(np.int32)
    shape = idx.max(axis=0) + 3
    if np.prod(shape, dtype=np.int64) > 80_000_000:
        return points
    grid = np.zeros(tuple(shape), dtype=bool)
    grid[idx[:, 0], idx[:, 1], idx[:, 2]] = True
    opened = ndimage.binary_dilation(ndimage.binary_erosion(grid, iterations=iterations), iterations=iterations)
    coords = np.argwhere(opened)
    if len(coords) < 4:
        return points
    return mn + (coords + 0.5) * voxel


def alpha_shape_vertices(points: np.ndarray, alpha: float) -> np.ndarray:
    cloud = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(points))
    try:
        mesh = o3d.geometry.TriangleMesh.create_from_point_cloud_alpha_shape(cloud, alpha)
        verts = np.asarray(mesh.vertices, dtype=np.float64)
        if len(verts) >= 4:
            return verts
    except Exception:
        return points
    return points


def concave_hull_proxy(points: np.ndarray, alpha: float, density_pct: float) -> np.ndarray:
    return alpha_shape_vertices(filter_density(points, density_pct), alpha)


def evaluate(name: str, params: dict, points: np.ndarray, original_n: int, complexity: int, seconds: float) -> dict:
    points = points[np.all(np.isfinite(points), axis=1)]
    if len(points) > 0:
        points = keep_largest_component(points)
    vol = pdi_volume(points)
    comp_n, comp_sizes = component_count(points)
    volume = float(vol["volume_m3"])
    abs_error = abs(volume - GT_VOLUME_M3) if math.isfinite(volume) else math.inf
    pct_error = abs_error / GT_VOLUME_M3 * 100.0 if math.isfinite(abs_error) else math.inf
    removed = original_n - len(points)
    return {
        "algorithm": name,
        "params_json": json.dumps(params, sort_keys=True),
        "volume_m3": volume,
        "abs_error_m3": round(abs_error, 6) if math.isfinite(abs_error) else math.inf,
        "pct_error": round(pct_error, 6) if math.isfinite(pct_error) else math.inf,
        "points": int(len(points)),
        "points_removed": int(removed),
        "pct_removed": round(removed / original_n * 100.0, 6),
        "components": comp_n,
        "largest_components": json.dumps(comp_sizes[:5]),
        "runtime_seconds": round(seconds, 6),
        "complexity": complexity,
        "pdi_metrics": vol,
    }


def run_candidate(name: str, params: dict, fn: Callable[[np.ndarray], np.ndarray], base: np.ndarray, complexity: int) -> tuple[dict, np.ndarray]:
    start = time.time()
    try:
        pts = fn(base)
        row = evaluate(name, params, pts, len(base), complexity, time.time() - start)
        return row, pts
    except Exception as exc:
        return {
            "algorithm": name,
            "params_json": json.dumps(params, sort_keys=True),
            "volume_m3": math.inf,
            "abs_error_m3": math.inf,
            "pct_error": math.inf,
            "points": 0,
            "points_removed": len(base),
            "pct_removed": 100.0,
            "components": 0,
            "largest_components": "[]",
            "runtime_seconds": round(time.time() - start, 6),
            "complexity": complexity,
            "error": repr(exc),
            "pdi_metrics": {},
        }, np.empty((0, 3))


def overlay(original: np.ndarray, corrected: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    tree = cKDTree(corrected) if len(corrected) else None
    if tree is None:
        keep = np.zeros(len(original), dtype=bool)
    else:
        d, _ = tree.query(original, k=1)
        keep = d <= COMMON_VOXEL_M * 1.5
    pts = original
    colors = np.tile(np.array([[0.9, 0.1, 0.05]]), (len(pts), 1))
    colors[keep] = np.array([0.1, 0.75, 0.2])
    return pts, colors


def plot_top(rows: list[dict]) -> None:
    top = rows[:20]
    labels = [f"{r['algorithm']}#{i+1}" for i, r in enumerate(top)]
    errs = [r["abs_error_m3"] for r in top]
    vols = [r["volume_m3"] for r in top]
    fig, ax = plt.subplots(figsize=(12, 6), dpi=150)
    ax.bar(range(len(top)), errs)
    ax.set_xticks(range(len(top)))
    ax.set_xticklabels(labels, rotation=70, ha="right", fontsize=7)
    ax.set_ylabel("error absoluto m3")
    ax.set_title("Top 20 configuraciones por error absoluto")
    fig.tight_layout()
    fig.savefig(OUT / "plots" / "top20_error.png")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(10, 5), dpi=150)
    ax.plot(range(len(top)), vols, marker="o", label="volumen candidato")
    ax.axhline(GT_VOLUME_M3, color="green", linestyle="--", label="volumen real")
    ax.axhline(CURRENT_PIPELINE_VOLUME_M3, color="red", linestyle="--", label="pipeline actual")
    ax.set_ylabel("m3")
    ax.set_title("Volumen de Top 20 vs real")
    ax.legend()
    fig.tight_layout()
    fig.savefig(OUT / "plots" / "top20_volume.png")
    plt.close(fig)


def main() -> int:
    for d in ["plots", "meshes", "pointclouds", "overlays", "metrics"]:
        (OUT / d).mkdir(parents=True, exist_ok=True)

    start_all = time.time()
    raw = read_scaled_raw()
    base = read_volume_input()
    original_n = len(base)
    baseline_check = pdi_volume(base)
    write_cloud(OUT / "pointclouds" / "benchmark_input_exact_volume_cloud.ply", base)

    rows: list[dict] = []
    saved_points: list[tuple[dict, np.ndarray]] = []

    jobs: list[tuple[str, dict, Callable[[np.ndarray], np.ndarray], int]] = []
    jobs.append(("baseline_common_input", {"voxel_m": COMMON_VOXEL_M}, lambda p: p, 1))

    for pct in [55, 60, 65, 70, 75, 80, 85, 90, 93, 95]:
        jobs.append(("center_distance", {"keep_percentile": pct}, lambda p, pct=pct: filter_center_percentile(p, pct), 1))
        jobs.append(("obb_shrink", {"axis_percentile": pct}, lambda p, pct=pct: filter_obb_shrink(p, pct), 1))
        jobs.append(("compactness", {"score_percentile": pct}, lambda p, pct=pct: filter_compactness(p, pct), 2))

    for pct in [5, 10, 15, 20, 25, 30, 35, 40, 50, 60]:
        jobs.append(("density_filter", {"remove_below_density_percentile": pct, "radius_m": 0.20}, lambda p, pct=pct: filter_density(p, pct), 2))
        jobs.append(("normal_filter", {"remove_below_consistency_percentile": pct}, lambda p, pct=pct: filter_normal_consistency(p, pct), 3))
        jobs.append(("thickness_filter", {"remove_below_thickness_percentile": pct}, lambda p, pct=pct: filter_thickness(p, pct), 3))

    for pct in [40, 50, 60, 70, 80, 85, 90]:
        jobs.append(("curvature_filter", {"keep_below_curvature_percentile": pct}, lambda p, pct=pct: filter_curvature(p, pct), 3))

    for radial in [15, 25, 35, 45]:
        for end in [80, 85, 90, 95]:
            jobs.append(("fine_branch_prune", {"radial_percentile": radial, "end_percentile": end}, lambda p, radial=radial, end=end: filter_fine_branches(p, radial, end), 3))

    for voxel in [0.12, 0.16, 0.20, 0.24, 0.30]:
        for it in [1, 2, 3]:
            jobs.append(("morphological_opening_3d", {"voxel_m": voxel, "iterations": it}, lambda p, voxel=voxel, it=it: morphological_opening(p, voxel, it), 3))

    for alpha in [0.35, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0]:
        jobs.append(("alpha_shape", {"alpha": alpha}, lambda p, alpha=alpha: alpha_shape_vertices(p, alpha), 4))
        for dens in [10, 25, 40]:
            jobs.append(("concave_hull_3d_proxy", {"alpha": alpha, "density_percentile": dens}, lambda p, alpha=alpha, dens=dens: concave_hull_proxy(p, alpha, dens), 5))

    for dens in [10, 20, 30, 40]:
        for alpha in [0.5, 1.0, 1.5]:
            jobs.append(("density_plus_alpha", {"density_percentile": dens, "alpha": alpha}, lambda p, dens=dens, alpha=alpha: alpha_shape_vertices(filter_density(p, dens), alpha), 6))
    for center in [70, 80, 90]:
        for dens in [10, 25, 40]:
            jobs.append(("center_plus_density", {"center_percentile": center, "density_percentile": dens}, lambda p, center=center, dens=dens: filter_density(filter_center_percentile(p, center), dens), 4))
    for obb in [70, 80, 90]:
        for curv in [60, 80, 90]:
            jobs.append(("obb_plus_curvature", {"obb_percentile": obb, "curvature_percentile": curv}, lambda p, obb=obb, curv=curv: filter_curvature(filter_obb_shrink(p, obb), curv), 5))
    for morph_voxel in [0.16, 0.20, 0.24]:
        for pct in [70, 80, 90]:
            jobs.append(("opening_plus_compactness", {"opening_voxel_m": morph_voxel, "compactness_percentile": pct}, lambda p, morph_voxel=morph_voxel, pct=pct: filter_compactness(morphological_opening(p, morph_voxel, 1), pct), 5))

    for name, params, fn, complexity in jobs:
        row, pts = run_candidate(name, params, fn, base, complexity)
        rows.append(row)
        if math.isfinite(row["abs_error_m3"]):
            saved_points.append((row, pts))

    rows.sort(key=lambda r: (float(r["abs_error_m3"]), float(r["pct_error"]), int(r["complexity"])))
    saved_points.sort(key=lambda x: (float(x[0]["abs_error_m3"]), float(x[0]["pct_error"]), int(x[0]["complexity"])))

    csv_fields = [
        "rank",
        "algorithm",
        "params_json",
        "volume_m3",
        "abs_error_m3",
        "pct_error",
        "points",
        "points_removed",
        "pct_removed",
        "components",
        "largest_components",
        "runtime_seconds",
        "complexity",
    ]
    for i, r in enumerate(rows, 1):
        r["rank"] = i

    with (OUT / "all_runs.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=csv_fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k) for k in csv_fields})
    top = rows[:50]
    with (OUT / "ranking.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=csv_fields)
        w.writeheader()
        for r in top:
            w.writerow({k: r.get(k) for k in csv_fields})
    (OUT / "ranking.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
    (OUT / "best_configuration.json").write_text(json.dumps(rows[0], indent=2), encoding="utf-8")

    for rank, (row, pts) in enumerate(saved_points[:10], 1):
        safe = f"{rank:02d}_{row['algorithm']}"
        write_cloud(OUT / "pointclouds" / f"{safe}.ply", pts)
        ov_pts, ov_cols = overlay(base, pts)
        write_cloud(OUT / "overlays" / f"{safe}_overlay.ply", ov_pts, ov_cols)

    plot_top(rows)

    summary = {
        "ground_truth_volume_m3": GT_VOLUME_M3,
        "current_pipeline_volume_m3": CURRENT_PIPELINE_VOLUME_M3,
        "raw_cloud": str(RAW_CLOUD),
        "volume_input_cloud": str(VOLUME_INPUT_CLOUD),
        "scale_factor_m_per_unit": SCALE_FACTOR,
        "common_input": {
            "description": "Nube exacta que entra a PDI, derivada de la RAW escalada. Se usa para que el baseline reproduzca el volumen actual y todos los metodos compitan sobre el mismo exceso de geometria.",
            "raw_scaled_points": int(len(raw)),
            "benchmark_input_points": int(original_n),
            "baseline_pdi_volume_m3": baseline_check["volume_m3"],
        },
        "run_count": len(rows),
        "best": rows[0],
        "top10": rows[:10],
        "runtime_seconds": round(time.time() - start_all, 3),
        "environment": {
            "python": sys.version,
            "platform": platform.platform(),
            "open3d": getattr(o3d, "__version__", "unknown"),
            "numpy": np.__version__,
        },
    }
    (OUT / "metrics" / "benchmark_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    best = rows[0]
    improvement_abs = abs(CURRENT_PIPELINE_VOLUME_M3 - GT_VOLUME_M3) - best["abs_error_m3"]
    improvement_pct = improvement_abs / abs(CURRENT_PIPELINE_VOLUME_M3 - GT_VOLUME_M3) * 100.0

    best_md = [
        "# Best configuration\n\n",
        f"- Algorithm: `{best['algorithm']}`\n",
        f"- Parameters: `{best['params_json']}`\n",
        f"- Volume: `{best['volume_m3']}` m3\n",
        f"- Absolute error: `{best['abs_error_m3']}` m3\n",
        f"- Percent error: `{best['pct_error']}` %\n",
        f"- Points kept: `{best['points']}` / `{original_n}`\n",
        f"- Removed: `{best['pct_removed']}` %\n",
        f"- Improvement vs current pipeline absolute error: `{round(improvement_abs, 6)}` m3 (`{round(improvement_pct, 6)}` %)\n",
    ]
    (OUT / "best_configuration.md").write_text("".join(best_md), encoding="utf-8")

    report = [
        "# Volume Correction Benchmark\n\n",
        "## Alcance\n",
        "Benchmark experimental independiente. No modifica pipeline productivo, NodeODM, OpenSfM ni reconstruye imagenes. Todos los metodos parten de la misma nube RAW escalada y del mismo universo de competencia.\n\n",
        "## Entrada comun\n",
        f"- RAW: `{RAW_CLOUD}`\n",
        f"- Input comun de competencia: `{VOLUME_INPUT_CLOUD}`\n",
        f"- Factor de escala aplicado para el experimento: `{SCALE_FACTOR}`\n",
        f"- Puntos RAW escalados: `{len(raw)}`\n",
        f"- Puntos de competencia exactos: `{original_n}`\n",
        f"- Baseline PDI reproducido sobre input comun: `{baseline_check['volume_m3']}` m3\n",
        "Este input es la nube que entra a volumetria y proviene de la RAW escalada; se usa para que el benchmark corrija el exceso real observado, sin modificar el pipeline productivo.\n\n",
        "## Criterio\n",
        f"Volumen objetivo: `{GT_VOLUME_M3}` m3. Ranking por menor error absoluto, luego menor error porcentual, luego menor complejidad.\n\n",
        "## Ganador\n",
        f"- Algoritmo: `{best['algorithm']}`\n",
        f"- Parametros: `{best['params_json']}`\n",
        f"- Volumen obtenido: `{best['volume_m3']}` m3\n",
        f"- Error absoluto: `{best['abs_error_m3']}` m3\n",
        f"- Error porcentual: `{best['pct_error']}` %\n",
        f"- Mejora vs pipeline actual `{CURRENT_PIPELINE_VOLUME_M3}` m3: `{round(improvement_abs, 6)}` m3 de error absoluto menos (`{round(improvement_pct, 6)}` %).\n\n",
        "## Top 10\n",
        "| Rank | Algorithm | Params | Volume | Abs error | % error | Removed % |\n",
        "|---:|---|---|---:|---:|---:|---:|\n",
    ]
    for r in rows[:10]:
        report.append(
            f"| {r['rank']} | {r['algorithm']} | `{r['params_json']}` | {r['volume_m3']} | {r['abs_error_m3']} | {r['pct_error']} | {r['pct_removed']} |\n"
        )
    report.extend(
        [
            "\n## Entregables\n",
            "- `ranking.csv`, `ranking.json`, `all_runs.csv`\n",
            "- `best_configuration.json`, `best_configuration.md`\n",
            "- `pointclouds/`: input comun y top 10 corregidos\n",
            "- `overlays/`: verde conservado, rojo eliminado para top 10\n",
            "- `plots/top20_error.png`, `plots/top20_volume.png`\n",
            "- `metrics/benchmark_summary.json`\n",
        ]
    )
    (OUT / "report.md").write_text("".join(report), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
