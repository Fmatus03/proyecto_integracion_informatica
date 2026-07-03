from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from backend.app.services import mesh_service


SESSION_ID = "b6b04af0-122f-4fcc-af8a-cc553ca5e28d"
SESSION_PATH = Path("/app/data/uploads") / SESSION_ID / "session.json"
POINT_CLOUD_PATH = Path("/app/data/processed") / SESSION_ID / "point_cloud.ply"
EXISTING_MESH_PATH = Path("/app/data/processed") / SESSION_ID / "preliminary_mesh.ply"
BASE_OUTPUT_DIR = Path("/app/data/processed") / SESSION_ID / "stage_diagnostics"
OUTPUT_DIR = BASE_OUTPUT_DIR


def _extent_volume(extent: np.ndarray) -> float:
    return float(np.prod(extent)) if extent.size == 3 and np.all(extent > 0) else 0.0


def _cloud_metrics(cloud, previous_count: int | None = None) -> dict:
    bbox = cloud.get_axis_aligned_bounding_box()
    extent = np.asarray(bbox.get_extent(), dtype=float)
    min_bound = np.asarray(bbox.get_min_bound(), dtype=float)
    max_bound = np.asarray(bbox.get_max_bound(), dtype=float)
    count = int(len(cloud.points))
    bbox_volume = _extent_volume(extent)
    retained = None if previous_count in (None, 0) else round(count / previous_count * 100.0, 4)
    return {
        "point_count": count,
        "bbox_min": [round(float(v), 4) for v in min_bound.tolist()],
        "bbox_max": [round(float(v), 4) for v in max_bound.tolist()],
        "bbox_extent_m": [round(float(v), 4) for v in extent.tolist()],
        "bbox_volume_m3": round(bbox_volume, 4),
        "density_points_per_m3": round(count / bbox_volume, 4) if bbox_volume > 0 else 0.0,
        "retained_vs_previous_pct": retained,
    }


def _mesh_metrics(mesh, previous_count: int | None = None) -> dict:
    bbox = mesh.get_axis_aligned_bounding_box()
    extent = np.asarray(bbox.get_extent(), dtype=float)
    count = int(len(mesh.vertices))
    bbox_volume = _extent_volume(extent)
    retained = None if previous_count in (None, 0) else round(count / previous_count * 100.0, 4)
    return {
        "vertex_count": count,
        "triangle_count": int(len(mesh.triangles)),
        "bbox_extent_m": [round(float(v), 4) for v in extent.tolist()],
        "bbox_volume_m3": round(bbox_volume, 4),
        "mesh_volume_m3": round(float(mesh.get_volume()), 4) if mesh.is_watertight() else None,
        "watertight": bool(mesh.is_watertight()),
        "retained_vertices_vs_mesh_input_points_pct": retained,
    }


def _write_cloud(o3d, name: str, cloud) -> str:
    path = OUTPUT_DIR / name
    o3d.io.write_point_cloud(str(path), cloud, write_ascii=False, compressed=False)
    return str(path)


def _write_mesh(o3d, name: str, mesh) -> str:
    path = OUTPUT_DIR / name
    o3d.io.write_triangle_mesh(str(path), mesh, write_ascii=False, compressed=False)
    return str(path)


def _orthographic_png(name: str, points: np.ndarray, title: str) -> None:
    if points.size == 0:
        return
    pairs = {"xy": (0, 1), "xz": (0, 2), "yz": (1, 2)}
    width = 900
    panel = 300
    img = Image.new("RGB", (width, panel), "white")
    draw = ImageDraw.Draw(img)
    for panel_index, (label, (a, b)) in enumerate(pairs.items()):
        x0 = panel_index * panel
        sub = points[:, [a, b]]
        mins = sub.min(axis=0)
        span = np.maximum(sub.max(axis=0) - mins, 1e-9)
        norm = (sub - mins) / span
        px = (norm[:, 0] * (panel - 24) + x0 + 12).astype(int)
        py = ((1.0 - norm[:, 1]) * (panel - 36) + 24).astype(int)
        step = max(1, len(px) // 60000)
        for x, y in zip(px[::step], py[::step]):
            draw.point((int(x), int(y)), fill=(20, 80, 140))
        draw.rectangle([x0 + 8, 20, x0 + panel - 8, panel - 8], outline=(30, 30, 30))
        draw.text((x0 + 12, 6), f"{title} {label.upper()}", fill=(0, 0, 0))
    img.save(OUTPUT_DIR / name)


def _write_cloud_views(name_prefix: str, cloud, title: str) -> None:
    _orthographic_png(f"{name_prefix}.png", np.asarray(cloud.points), title)


def _select_by_labels(cloud, labels: np.ndarray, keep_labels: list[int], invert: bool = False):
    mask = np.isin(labels, keep_labels)
    if invert:
        mask = ~mask
    return cloud.select_by_index(np.where(mask)[0].tolist())


def main() -> None:
    global OUTPUT_DIR
    if OUTPUT_DIR.exists():
        index = 2
        while True:
            candidate = BASE_OUTPUT_DIR.with_name(f"{BASE_OUTPUT_DIR.name}_{index}")
            if not candidate.exists():
                OUTPUT_DIR = candidate
                break
            index += 1
    OUTPUT_DIR.mkdir(parents=True, exist_ok=False)
    session = json.loads(SESSION_PATH.read_text(encoding="utf-8"))
    mesh_cfg = session["mesh"]["point_cloud_quality"]["segmentation"]
    scale_cfg = session["mesh"]["point_cloud_quality"]["scale"]
    o3d = mesh_service._require_open3d()

    stage_metrics: dict[str, dict] = {}
    exported: dict[str, str] = {}

    raw_cloud = mesh_service._load_point_cloud(o3d, POINT_CLOUD_PATH)
    exported["01_raw_cloud"] = _write_cloud(o3d, "01_raw_cloud.ply", raw_cloud)
    _write_cloud_views("01_raw_cloud", raw_cloud, "01 raw")
    stage_metrics["01_raw_cloud"] = _cloud_metrics(raw_cloud)

    scaled_cloud = mesh_service._load_point_cloud(o3d, POINT_CLOUD_PATH)
    scaled_cloud.scale(float(scale_cfg["point_cloud_scale_m_per_unit"]), center=(0.0, 0.0, 0.0))
    exported["02_scaled_cloud"] = _write_cloud(o3d, "02_scaled_cloud.ply", scaled_cloud)
    _write_cloud_views("02_scaled_cloud", scaled_cloud, "02 scaled")
    stage_metrics["02_scaled_cloud"] = _cloud_metrics(scaled_cloud, stage_metrics["01_raw_cloud"]["point_count"])

    clean_cloud = mesh_service._clean_point_cloud(
        scaled_cloud,
        voxel_size_m=None,
        outlier_neighbors=24,
        outlier_std_ratio=2.0,
        min_retained_ratio=0.70,
    )
    exported["03_clean_cloud"] = _write_cloud(o3d, "03_clean_cloud.ply", clean_cloud)
    _write_cloud_views("03_clean_cloud", clean_cloud, "03 clean")
    stage_metrics["03_clean_cloud"] = _cloud_metrics(clean_cloud, stage_metrics["02_scaled_cloud"]["point_count"])

    clustering_cloud = clean_cloud.voxel_down_sample(float(mesh_cfg["voxel_size_m"]))
    exported["04_filtered_voxel_cloud"] = _write_cloud(o3d, "04_filtered_voxel_cloud.ply", clustering_cloud)
    _write_cloud_views("04_filtered_voxel_cloud", clustering_cloud, "04 voxel")
    stage_metrics["04_filtered_voxel_cloud"] = _cloud_metrics(clustering_cloud, stage_metrics["03_clean_cloud"]["point_count"])

    labels = np.asarray(
        clustering_cloud.cluster_dbscan(
            eps=float(mesh_cfg["cluster_eps_m"]),
            min_points=int(mesh_cfg["cluster_min_points"]),
            print_progress=False,
        )
    )
    selected_labels = [int(v) for v in mesh_cfg["selected_labels"]]
    segmented_cloud = _select_by_labels(clustering_cloud, labels, selected_labels)
    discarded_cloud = _select_by_labels(clustering_cloud, labels, selected_labels, invert=True)
    noise_cloud = clustering_cloud.select_by_index(np.where(labels < 0)[0].tolist())

    exported["05_segmented_cloud"] = _write_cloud(o3d, "05_segmented_cloud.ply", segmented_cloud)
    exported["05_discarded_by_segmentation"] = _write_cloud(o3d, "05_discarded_by_segmentation.ply", discarded_cloud)
    exported["05_dbscan_noise"] = _write_cloud(o3d, "05_dbscan_noise.ply", noise_cloud)
    _write_cloud_views("05_segmented_cloud", segmented_cloud, "05 segmented")
    _write_cloud_views("05_discarded_by_segmentation", discarded_cloud, "05 discarded")
    stage_metrics["05_segmented_cloud"] = _cloud_metrics(segmented_cloud, stage_metrics["04_filtered_voxel_cloud"]["point_count"])
    stage_metrics["05_discarded_by_segmentation"] = _cloud_metrics(discarded_cloud, stage_metrics["04_filtered_voxel_cloud"]["point_count"])
    stage_metrics["05_dbscan_noise"] = _cloud_metrics(noise_cloud, stage_metrics["04_filtered_voxel_cloud"]["point_count"])

    mesh_input_cloud = segmented_cloud
    mesh_service._prepare_normals(
        o3d,
        mesh_input_cloud,
        normal_radius_m=0.05,
        normal_max_nn=48,
        recompute_normals=True,
    )
    exported["06_mesh_input_cloud"] = _write_cloud(o3d, "06_mesh_input_cloud.ply", mesh_input_cloud)
    _write_cloud_views("06_mesh_input_cloud", mesh_input_cloud, "06 mesh input")
    stage_metrics["06_mesh_input_cloud"] = _cloud_metrics(mesh_input_cloud, stage_metrics["05_segmented_cloud"]["point_count"])

    poisson_mesh = mesh_service._poisson_mesh(o3d, mesh_input_cloud, depth=8, density_quantile=0.01)
    exported["06a_poisson_mesh_before_repair"] = _write_mesh(o3d, "06a_poisson_mesh_before_repair.ply", poisson_mesh)
    stage_metrics["06a_poisson_mesh_before_repair"] = _mesh_metrics(poisson_mesh, stage_metrics["06_mesh_input_cloud"]["point_count"])

    final_mesh, repair_cycles, fallback_applied = mesh_service._watertight_mesh(
        o3d,
        mesh_input_cloud,
        poisson_mesh,
        alpha_shape_fallback=True,
        alpha_min_m=1.5,
        alpha_max_m=3.0,
        alpha_extent_ratio=0.52,
    )
    final_mesh.compute_vertex_normals()
    exported["07_final_mesh"] = _write_mesh(o3d, "07_final_mesh.ply", final_mesh)
    stage_metrics["07_final_mesh"] = _mesh_metrics(final_mesh, stage_metrics["06_mesh_input_cloud"]["point_count"])

    if EXISTING_MESH_PATH.exists():
        shutil.copy2(EXISTING_MESH_PATH, OUTPUT_DIR / "07_existing_final_mesh_copy.ply")

    cluster_summary = []
    for label in sorted(int(v) for v in np.unique(labels)):
        label_cloud = clustering_cloud.select_by_index(np.where(labels == label)[0].tolist())
        metrics = _cloud_metrics(label_cloud)
        metrics["label"] = label
        metrics["selected"] = label in selected_labels
        cluster_summary.append(metrics)

    report = {
        "session_id": SESSION_ID,
        "source_point_cloud": str(POINT_CLOUD_PATH),
        "output_dir": str(OUTPUT_DIR),
        "pipeline_parameters_observed": {
            "scale": scale_cfg,
            "segmentation": mesh_cfg,
            "poisson_depth": 8,
            "density_quantile": 0.01,
            "alpha_shape_fallback": True,
            "alpha_min_m": 1.5,
            "alpha_max_m": 3.0,
            "alpha_extent_ratio": 0.52,
        },
        "exported_artifacts": exported,
        "stage_metrics": stage_metrics,
        "dbscan_cluster_summary": cluster_summary,
        "repair_cycles_recomputed": repair_cycles,
        "fallback_applied_recomputed": fallback_applied,
        "session_final_volume_m3": session["volume"]["volume_m3"],
        "recomputed_final_volume_m3": stage_metrics["07_final_mesh"]["mesh_volume_m3"],
    }
    (OUTPUT_DIR / "stage_metrics.json").write_text(json.dumps(report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
