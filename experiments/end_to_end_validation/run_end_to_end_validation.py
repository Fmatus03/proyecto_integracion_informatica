from __future__ import annotations

import csv
import json
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", str(Path(__file__).resolve().parent / ".mplconfig"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import open3d as o3d
from scipy.spatial import ConvexHull, cKDTree


ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
PROJECT = ROOT / "projects/ForestVol"
BACKEND = PROJECT / "backend"
sys.path.insert(0, str(BACKEND))

from app.services import mesh_service  # noqa: E402


RAW_CLOUD = PROJECT / "data/processed/971d6e25-8ff0-41d2-8784-c981dec7ccbf/point_cloud.ply"
SCALE_FACTOR = 0.54611448
GROUND_TRUTH_M3 = 119.74
PIPELINE_ORIGINAL_M3 = 234.0469
BENCHMARK_VOLUME_M3 = 121.2031
OBB_PERCENTILE = 80
CURVATURE_PERCENTILE = 80


def cloud_from_points(points: np.ndarray) -> o3d.geometry.PointCloud:
    cloud = o3d.geometry.PointCloud()
    cloud.points = o3d.utility.Vector3dVector(points)
    return cloud


def points_from_cloud(cloud: o3d.geometry.PointCloud) -> np.ndarray:
    return np.asarray(cloud.points, dtype=np.float64)


def write_cloud(path: Path, points: np.ndarray, colors: np.ndarray | None = None) -> None:
    cloud = cloud_from_points(points)
    if colors is not None:
        cloud.colors = o3d.utility.Vector3dVector(colors)
    o3d.io.write_point_cloud(str(path), cloud, write_ascii=False)


def pca_frame(points: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    center = points.mean(axis=0)
    centered = points - center
    cov = np.cov(centered.T)
    vals, vecs = np.linalg.eigh(cov)
    order = np.argsort(vals)[::-1]
    axes = vecs[:, order]
    local = centered @ axes
    return center, axes, local


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


def apply_winning_filter(points: np.ndarray) -> tuple[np.ndarray, dict]:
    _, _, local = pca_frame(points)
    keep_obb = np.ones(len(points), dtype=bool)
    margin = (100 - OBB_PERCENTILE) / 2
    obb_bounds = []
    for axis in range(3):
        lo, hi = np.percentile(local[:, axis], [margin, 100 - margin])
        keep_obb &= (local[:, axis] >= lo) & (local[:, axis] <= hi)
        obb_bounds.append([float(lo), float(hi)])
    obb_points = points[keep_obb]
    curvature = local_curvature(obb_points, 20)
    curv_threshold = float(np.percentile(curvature, CURVATURE_PERCENTILE))
    keep_curv = curvature <= curv_threshold
    filtered = obb_points[keep_curv]
    return filtered, {
        "algorithm": "obb_plus_curvature",
        "obb_percentile": OBB_PERCENTILE,
        "curvature_percentile": CURVATURE_PERCENTILE,
        "obb_local_bounds": obb_bounds,
        "curvature_threshold": curv_threshold,
        "input_points": int(len(points)),
        "after_obb_points": int(len(obb_points)),
        "after_curvature_points": int(len(filtered)),
        "removed_points": int(len(points) - len(filtered)),
        "removed_percent": float((len(points) - len(filtered)) / len(points) * 100.0),
    }


def component_stats(points: np.ndarray, eps: float = 0.35) -> dict:
    if len(points) < 4:
        return {"component_count": 0, "component_sizes": []}
    cloud = cloud_from_points(points)
    labels = np.asarray(cloud.cluster_dbscan(eps=eps, min_points=3, print_progress=False))
    valid = labels >= 0
    if not valid.any():
        return {"component_count": 0, "component_sizes": []}
    sizes = np.bincount(labels[valid])
    return {"component_count": int(len(sizes)), "component_sizes": sorted([int(x) for x in sizes], reverse=True)}


def bbox(points: np.ndarray) -> dict:
    mn = points.min(axis=0)
    mx = points.max(axis=0)
    ext = mx - mn
    return {"min": mn.tolist(), "max": mx.tolist(), "extent_m": ext.tolist(), "volume_m3": float(np.prod(ext))}


def overlay(before: np.ndarray, after: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    tree = cKDTree(after)
    d, _ = tree.query(before, k=1)
    kept = d <= 0.09
    colors = np.tile(np.array([[0.9, 0.1, 0.05]]), (len(before), 1))
    colors[kept] = np.array([0.1, 0.75, 0.2])
    return before, colors


def view(points: np.ndarray, colors: np.ndarray, path: Path, mode: str) -> None:
    fig = plt.figure(figsize=(10, 8), dpi=150)
    sample = points
    c = colors
    if len(points) > 80000:
        idx = np.linspace(0, len(points) - 1, 80000).astype(int)
        sample = points[idx]
        c = colors[idx]
    if mode == "iso":
        ax = fig.add_subplot(111, projection="3d")
        ax.scatter(sample[:, 0], sample[:, 1], sample[:, 2], c=c, s=0.3, linewidths=0)
        ax.view_init(elev=25, azim=-45)
        ax.set_xlabel("X m")
        ax.set_ylabel("Y m")
        ax.set_zlabel("Z m")
    else:
        axes = {"front": (0, 2), "side": (1, 2), "top": (0, 1)}
        a, b = axes[mode]
        ax = fig.add_subplot(111)
        ax.scatter(sample[:, a], sample[:, b], c=c, s=0.4, linewidths=0)
        ax.set_aspect("equal", adjustable="box")
        ax.set_xlabel(["X", "Y", "Z"][a] + " m")
        ax.set_ylabel(["X", "Y", "Z"][b] + " m")
    ax.set_title("E2E winner filter overlay: green kept, red removed")
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def main() -> int:
    started = time.time()
    OUT.mkdir(exist_ok=True)
    for d in ["views", "captures"]:
        (OUT / d).mkdir(exist_ok=True)

    raw_cloud = mesh_service._load_point_cloud(o3d, RAW_CLOUD)
    raw_cloud.scale(SCALE_FACTOR, center=(0, 0, 0))
    raw_scaled_points = points_from_cloud(raw_cloud)

    cleaned = mesh_service._clean_point_cloud(
        raw_cloud,
        voxel_size_m=None,
        outlier_neighbors=24,
        outlier_std_ratio=2.0,
        min_retained_ratio=0.70,
    )
    cleaned_points = points_from_cloud(cleaned)

    segmented, segmentation_quality = mesh_service._segment_woodpile_components(
        cleaned,
        segmentation_voxel_size_m=0.06,
        cluster_eps_m=0.35,
        cluster_min_points=20,
        max_components=2,
        min_component_ratio=0.10,
        max_component_height_m=8.0,
        max_component_bbox_volume_m3=500.0,
        max_component_axis_ratio=8.0,
    )
    pipeline_points = points_from_cloud(segmented)
    original_pdi = mesh_service._estimate_pdi_volume(segmented, mesh_service.PDI_VOXEL_SIZE_M)

    filtered_points, filter_metrics = apply_winning_filter(pipeline_points)
    filtered_cloud = cloud_from_points(filtered_points)
    filtered_pdi = mesh_service._estimate_pdi_volume(filtered_cloud, mesh_service.PDI_VOXEL_SIZE_M)

    write_cloud(OUT / "pipeline_output.ply", pipeline_points)
    write_cloud(OUT / "filtered_cloud.ply", filtered_points)
    ov_pts, ov_colors = overlay(pipeline_points, filtered_points)
    write_cloud(OUT / "overlay_before_after.ply", ov_pts, ov_colors)

    for mode in ["front", "side", "top", "iso"]:
        view(ov_pts, ov_colors, OUT / f"{mode}.png", mode)
        view(ov_pts, ov_colors, OUT / "views" / f"{mode}.png", mode)

    e2e_volume = float(filtered_pdi["volume_m3"])
    comparison = [
        {
            "metric": "pipeline_original",
            "volume_m3": PIPELINE_ORIGINAL_M3,
            "difference_vs_real_m3": round(abs(PIPELINE_ORIGINAL_M3 - GROUND_TRUTH_M3), 6),
            "error_percent": round(abs(PIPELINE_ORIGINAL_M3 - GROUND_TRUTH_M3) / GROUND_TRUTH_M3 * 100, 6),
            "difference_vs_benchmark_m3": "",
        },
        {
            "metric": "benchmark_winner",
            "volume_m3": BENCHMARK_VOLUME_M3,
            "difference_vs_real_m3": round(abs(BENCHMARK_VOLUME_M3 - GROUND_TRUTH_M3), 6),
            "error_percent": round(abs(BENCHMARK_VOLUME_M3 - GROUND_TRUTH_M3) / GROUND_TRUTH_M3 * 100, 6),
            "difference_vs_benchmark_m3": 0.0,
        },
        {
            "metric": "pipeline_e2e_with_winner_filter",
            "volume_m3": e2e_volume,
            "difference_vs_real_m3": round(abs(e2e_volume - GROUND_TRUTH_M3), 6),
            "error_percent": round(abs(e2e_volume - GROUND_TRUTH_M3) / GROUND_TRUTH_M3 * 100, 6),
            "difference_vs_benchmark_m3": round(e2e_volume - BENCHMARK_VOLUME_M3, 6),
        },
    ]

    with (OUT / "comparison.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(comparison[0].keys()))
        writer.writeheader()
        writer.writerows(comparison)
    (OUT / "comparison.json").write_text(json.dumps(comparison, indent=2), encoding="utf-8")

    filtered_components = component_stats(filtered_points)
    metrics = {
        "configuration": {
            "algorithm": "obb_plus_curvature",
            "obb_percentile": OBB_PERCENTILE,
            "curvature_percentile": CURVATURE_PERCENTILE,
            "insertion_point": "immediately before mesh_service._estimate_pdi_volume",
        },
        "sources": {
            "raw_cloud": str(RAW_CLOUD),
            "scale_factor_m_per_unit": SCALE_FACTOR,
        },
        "stage_points": {
            "raw_scaled": int(len(raw_scaled_points)),
            "after_clean": int(len(cleaned_points)),
            "pipeline_volume_input_before_filter": int(len(pipeline_points)),
            "after_winner_filter": int(len(filtered_points)),
        },
        "segmentation_quality": segmentation_quality,
        "filter_metrics": filter_metrics,
        "original_pdi_recomputed": original_pdi,
        "filtered_pdi": filtered_pdi,
        "geometry": {
            "before_filter_aabb": bbox(pipeline_points),
            "after_filter_aabb": bbox(filtered_points),
            "after_filter_hull_volume_m3": float(ConvexHull(filtered_points).volume),
            "after_filter_components_eps035": filtered_components,
        },
        "comparison": comparison,
        "validations": {
            "pipeline_completed": True,
            "filtered_cloud_valid": bool(len(filtered_points) >= 4 and np.all(np.isfinite(filtered_points))),
            "volume_completed": "volume_m3" in filtered_pdi,
            "unexpected_components": filtered_components["component_count"] != 1,
            "benchmark_difference_m3": round(e2e_volume - BENCHMARK_VOLUME_M3, 6),
            "benchmark_difference_abs_m3": round(abs(e2e_volume - BENCHMARK_VOLUME_M3), 6),
        },
        "runtime_seconds": round(time.time() - started, 3),
    }
    (OUT / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")

    # Lightweight text capture requested as volume capture.
    (OUT / "captures" / "volume_obtained.txt").write_text(
        f"pipeline_e2e_with_winner_filter_volume_m3={e2e_volume}\n"
        f"benchmark_reference_m3={BENCHMARK_VOLUME_M3}\n"
        f"ground_truth_m3={GROUND_TRUTH_M3}\n",
        encoding="utf-8",
    )

    report = [
        "# End-to-End Validation: Benchmark Winner Filter\n\n",
        "## Alcance\n",
        "Validacion experimental E2E sobre la reconstruccion existente. No se modifico codigo productivo, NodeODM, OpenSfM ni parametros. Se replico el flujo productivo hasta el input de PDI y se inserto en memoria el filtro ganador inmediatamente antes de `_estimate_pdi_volume`.\n\n",
        "## Configuracion fija\n",
        "- Algoritmo: `obb_plus_curvature`\n",
        f"- `obb_percentile`: `{OBB_PERCENTILE}`\n",
        f"- `curvature_percentile`: `{CURVATURE_PERCENTILE}`\n\n",
        "## Etapas ejecutadas\n",
        "1. `_load_point_cloud()` sobre `point_cloud.ply` existente.\n",
        f"2. Escalado con factor `{SCALE_FACTOR}`.\n",
        "3. `_clean_point_cloud(voxel_size_m=None, outlier_neighbors=24, outlier_std_ratio=2.0)`.\n",
        "4. `_segment_woodpile_components(segmentation_voxel_size_m=0.06, cluster_eps_m=0.35, cluster_min_points=20, max_components=2)`.\n",
        "5. Filtro ganador `obb_plus_curvature`.\n",
        "6. `_estimate_pdi_volume(..., 0.25)`.\n\n",
        "## Comparacion obligatoria\n",
        "| Caso | Volumen m3 | Dif. vs real m3 | Error % | Dif. vs benchmark m3 |\n",
        "|---|---:|---:|---:|---:|\n",
    ]
    for row in comparison:
        report.append(
            f"| {row['metric']} | {row['volume_m3']} | {row['difference_vs_real_m3']} | {row['error_percent']} | {row['difference_vs_benchmark_m3']} |\n"
        )
    report.extend(
        [
            "\n## Validaciones adicionales\n",
            f"- Pipeline completo experimental termino sin errores: `{metrics['validations']['pipeline_completed']}`.\n",
            f"- Nube filtrada valida: `{metrics['validations']['filtered_cloud_valid']}`.\n",
            f"- Volumetria termino correctamente: `{metrics['validations']['volume_completed']}`.\n",
            f"- Componentes despues del filtro eps=0.35: `{filtered_components['component_count']}`; tamanos principales `{filtered_components['component_sizes'][:5]}`.\n",
            f"- Diferencia absoluta benchmark vs E2E: `{metrics['validations']['benchmark_difference_abs_m3']}` m3.\n\n",
            "## Entregables\n",
            "- `pipeline_output.ply`\n",
            "- `filtered_cloud.ply`\n",
            "- `overlay_before_after.ply` verde=conservado, rojo=eliminado\n",
            "- `front.png`, `side.png`, `top.png`, `iso.png`\n",
            "- `comparison.csv`, `comparison.json`, `metrics.json`\n",
            "- `captures/volume_obtained.txt`\n\n",
            "## Conclusion\n",
        ]
    )
    close = abs(e2e_volume - BENCHMARK_VOLUME_M3)
    if close <= 5.0:
        report.append(
            f"La configuracion ganadora mantiene el comportamiento esperado integrada al flujo E2E experimental: volumen `{e2e_volume}` m3, a `{close}` m3 del benchmark `{BENCHMARK_VOLUME_M3}` m3.\n"
        )
    else:
        report.append(
            f"La configuracion no reproduce suficientemente el benchmark: volumen `{e2e_volume}` m3, diferencia `{close}` m3 respecto de `{BENCHMARK_VOLUME_M3}` m3.\n"
        )
    (OUT / "report.md").write_text("".join(report), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
