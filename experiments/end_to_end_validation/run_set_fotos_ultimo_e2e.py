from __future__ import annotations

import csv
import json
import os
import shutil
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
FORESTVOL = ROOT / "projects" / "ForestVol"
BACKEND = FORESTVOL / "backend"
sys.path.insert(0, str(BACKEND.parent))

from backend.app.config import Settings, get_settings  # noqa: E402
from backend.app.services.calibration_service import calibrate_session, calibration_result_to_session_payload  # noqa: E402
from backend.app.services.gcp_service import generate_aruco_gcp_file  # noqa: E402
from backend.app.services.mesh_service import _clean_point_cloud, _estimate_pdi_volume, _load_point_cloud, _segment_woodpile_components  # noqa: E402
from backend.app.services.nodeodm_client import ATTEMPTS, STATUS_COMPLETED, NodeODMClient  # noqa: E402
from backend.app.services.reconstructed_scale_service import estimate_reconstructed_aruco_scale  # noqa: E402
from backend.app.services.scale_service import inspect_scale_inputs  # noqa: E402
from backend.app.services.session_store import SessionStore  # noqa: E402


OUT = ROOT / "experiments" / "end_to_end_validation"
RUN_DIR = OUT / "set_fotos_ultimo"
DATASET = FORESTVOL / "set_imagenes+guia" / "set_fotos_ultimo"
GROUND_TRUTH_M3 = 119.74
PIPELINE_ORIGINAL_M3 = 234.0469
BENCHMARK_VOLUME_M3 = 121.2031
OBB_PERCENTILE = 80
CURVATURE_PERCENTILE = 80


def settings_for_host() -> Settings:
    s = get_settings()
    return Settings(
        version=s.version,
        backend_port=s.backend_port,
        nodeodm_url=os.environ.get("NODEODM_URL", "http://localhost:3001").rstrip("/"),
        nodeodm_timeout_seconds=int(os.environ.get("NODEODM_TIMEOUT_SECONDS", "7200")),
        nodeodm_data_path=Path(os.environ.get("NODEODM_DATA_PATH", str(FORESTVOL / "data" / "nodeodm"))),
        min_images=s.min_images,
        max_images=50,
        max_image_size_mb=s.max_image_size_mb,
        max_session_size_gb=max(s.max_session_size_gb, 4),
        upload_path=FORESTVOL / "data" / "uploads",
        processed_path=FORESTVOL / "data" / "processed",
        export_path=FORESTVOL / "data" / "exports",
        calibration_confidence_threshold=s.calibration_confidence_threshold,
        calibration_marker_size_cm=100.0,
    )


def image_paths() -> list[Path]:
    paths = sorted(p for p in DATASET.iterdir() if p.suffix.lower() in {".png", ".jpg", ".jpeg"})
    if len(paths) != 50:
        raise RuntimeError(f"Expected exactly 50 images in {DATASET}, found {len(paths)}")
    return paths


def points(cloud: o3d.geometry.PointCloud) -> np.ndarray:
    return np.asarray(cloud.points, dtype=np.float64)


def make_cloud(pts: np.ndarray) -> o3d.geometry.PointCloud:
    cloud = o3d.geometry.PointCloud()
    cloud.points = o3d.utility.Vector3dVector(np.asarray(pts, dtype=np.float64))
    return cloud


def write_cloud(path: Path, pts: np.ndarray, colors: np.ndarray | None = None) -> None:
    cloud = make_cloud(pts)
    if colors is not None:
        cloud.colors = o3d.utility.Vector3dVector(colors)
    o3d.io.write_point_cloud(str(path), cloud, write_ascii=False)


def pca_frame(pts: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    center = pts.mean(axis=0)
    centered = pts - center
    vals, vecs = np.linalg.eigh(np.cov(centered.T))
    axes = vecs[:, np.argsort(vals)[::-1]]
    local = centered @ axes
    return center, axes, local


def local_curvature(pts: np.ndarray, k: int = 20) -> np.ndarray:
    tree = cKDTree(pts)
    kk = min(k + 1, len(pts))
    _, idx = tree.query(pts, k=kk)
    neigh = pts[idx[:, 1:]]
    centered = neigh - pts[:, None, :]
    cov = np.einsum("nki,nkj->nij", centered, centered) / max(1, kk - 1)
    eig = np.maximum(np.linalg.eigvalsh(cov), 1e-12)
    return eig[:, 0] / eig.sum(axis=1)


def apply_winner_filter(pts: np.ndarray) -> tuple[np.ndarray, dict]:
    _, _, local = pca_frame(pts)
    margin = (100 - OBB_PERCENTILE) / 2
    keep = np.ones(len(pts), dtype=bool)
    bounds = []
    for axis in range(3):
        lo, hi = np.percentile(local[:, axis], [margin, 100 - margin])
        keep &= (local[:, axis] >= lo) & (local[:, axis] <= hi)
        bounds.append([float(lo), float(hi)])
    obb_pts = pts[keep]
    curv = local_curvature(obb_pts, 20)
    threshold = float(np.percentile(curv, CURVATURE_PERCENTILE))
    filtered = obb_pts[curv <= threshold]
    return filtered, {
        "algorithm": "obb_plus_curvature",
        "obb_percentile": OBB_PERCENTILE,
        "curvature_percentile": CURVATURE_PERCENTILE,
        "obb_local_bounds": bounds,
        "curvature_threshold": threshold,
        "input_points": int(len(pts)),
        "after_obb_points": int(len(obb_pts)),
        "after_curvature_points": int(len(filtered)),
        "removed_points": int(len(pts) - len(filtered)),
        "removed_percent": float((len(pts) - len(filtered)) / len(pts) * 100.0),
    }


def bbox(pts: np.ndarray) -> dict:
    mn = pts.min(axis=0)
    mx = pts.max(axis=0)
    ext = mx - mn
    return {"min": mn.tolist(), "max": mx.tolist(), "extent_m": ext.tolist(), "volume_m3": float(np.prod(ext))}


def components(pts: np.ndarray) -> dict:
    labels = np.asarray(make_cloud(pts).cluster_dbscan(eps=0.35, min_points=3, print_progress=False))
    valid = labels[labels >= 0]
    if len(valid) == 0:
        return {"component_count": 0, "component_sizes": []}
    sizes = np.bincount(valid)
    return {"component_count": int(len(sizes)), "component_sizes": sorted([int(x) for x in sizes], reverse=True)}


def overlay(before: np.ndarray, after: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    d, _ = cKDTree(after).query(before, k=1)
    kept = d <= 0.09
    colors = np.tile(np.array([[0.9, 0.1, 0.05]]), (len(before), 1))
    colors[kept] = np.array([0.1, 0.75, 0.2])
    return before, colors


def render_view(pts: np.ndarray, colors: np.ndarray, path: Path, mode: str) -> None:
    fig = plt.figure(figsize=(10, 8), dpi=150)
    sample = pts
    c = colors
    if len(pts) > 90000:
        idx = np.linspace(0, len(pts) - 1, 90000).astype(int)
        sample = pts[idx]
        c = colors[idx]
    if mode == "iso":
        ax = fig.add_subplot(111, projection="3d")
        ax.scatter(sample[:, 0], sample[:, 1], sample[:, 2], c=c, s=0.25, linewidths=0)
        ax.view_init(elev=25, azim=-45)
        ax.set_xlabel("X m")
        ax.set_ylabel("Y m")
        ax.set_zlabel("Z m")
    else:
        axis_map = {"front": (0, 2), "side": (1, 2), "top": (0, 1)}
        a, b = axis_map[mode]
        ax = fig.add_subplot(111)
        ax.scatter(sample[:, a], sample[:, b], c=c, s=0.35, linewidths=0)
        ax.set_aspect("equal", adjustable="box")
        ax.set_xlabel(["X", "Y", "Z"][a] + " m")
        ax.set_ylabel(["X", "Y", "Z"][b] + " m")
    ax.set_title("set_fotos_ultimo E2E: green kept, red removed")
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def create_session(store: SessionStore, imgs: list[Path]) -> tuple[str, list[Path]]:
    session = store.create_session([p.name for p in imgs])
    upload_paths = store.store_images(session["session_id"], [(p.name, p.read_bytes()) for p in imgs])
    calibration = calibrate_session(session["session_id"], store.settings)
    session = store.load_session(session["session_id"]) or session
    session["pipeline_state"] = "CALIBRATED"
    session["calibration"] = calibration_result_to_session_payload(calibration)
    session["message"] = "Spatial calibration completed"
    store.save_session(session["session_id"], session)
    return session["session_id"], upload_paths


def run_nodeodm(session_id: str, upload_paths: list[Path], settings: Settings, store: SessionStore) -> tuple[Path, dict]:
    client = NodeODMClient(settings)
    if not client.is_reachable():
        raise RuntimeError(f"NodeODM is not reachable at {settings.nodeodm_url}")
    processed_dir = store.processed_dir(session_id)
    scale_evidence = inspect_scale_inputs(upload_paths, DATASET)
    gcp_result = generate_aruco_gcp_file(upload_paths, processed_dir, marker_size_cm=settings.calibration_marker_size_cm)
    scale_evidence = type(scale_evidence)(
        image_count=scale_evidence.image_count,
        images_with_exif=scale_evidence.images_with_exif,
        images_with_gps=scale_evidence.images_with_gps,
        gcp_path=gcp_result.gcp_path,
        scale_certified=False,
        reason="aruco_gcp_generated_pending_3d_validation",
    )
    attempts = []
    session = store.load_session(session_id) or {}
    session["scale_evidence"] = {**scale_evidence.to_payload(), "aruco_gcp": gcp_result.to_payload()}
    session["pipeline_state"] = "RECONSTRUCTING"
    store.save_session(session_id, session)
    for attempt in ATTEMPTS:
        record = {"attempt": attempt.name, "options": attempt.options, "task_uuid": None, "status": "started"}
        attempts.append(record)
        try:
            task_uuid = client.submit_task(session_id, upload_paths, attempt, scale_evidence=scale_evidence)
            record["task_uuid"] = task_uuid
            info = client.poll_task(task_uuid)
            record["nodeodm_info"] = info
            if int(info["status"]["code"]) == STATUS_COMPLETED:
                point_cloud = client.download_first_ply(task_uuid, processed_dir)
                reconstructed_scale = estimate_reconstructed_aruco_scale(
                    point_cloud,
                    marker_size_m=settings.calibration_marker_size_cm / 100.0,
                )
                scale_payload = {
                    **scale_evidence.to_payload(),
                    "scale_certified": True,
                    "reason": "reconstructed_aruco_3d",
                    "aruco_gcp": gcp_result.to_payload(),
                    "reconstructed_aruco_scale": reconstructed_scale.to_payload(),
                }
                session = store.load_session(session_id) or {}
                session["nodeodm_task_uuid"] = task_uuid
                session["point_cloud_path"] = str(point_cloud)
                session["scale_evidence"] = scale_payload
                session["pipeline_state"] = "POINT_CLOUD_READY"
                store.save_session(session_id, session)
                record["status"] = "completed"
                return point_cloud, {"attempts": attempts, "task_uuid": task_uuid, "scale_payload": scale_payload}
            record["status"] = "failed"
        except Exception as exc:
            record["status"] = "failed"
            record["error"] = f"{type(exc).__name__}: {exc}"
    raise RuntimeError(f"NodeODM failed after attempts: {attempts}")


def run_volume(point_cloud_path: Path, scale_factor: float) -> dict:
    raw = _load_point_cloud(o3d, point_cloud_path)
    raw.scale(scale_factor, center=(0.0, 0.0, 0.0))
    raw_pts = points(raw)
    cleaned = _clean_point_cloud(raw, voxel_size_m=None, outlier_neighbors=24, outlier_std_ratio=2.0, min_retained_ratio=0.70)
    cleaned_pts = points(cleaned)
    segmented, segmentation_quality = _segment_woodpile_components(
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
    pipeline_pts = points(segmented)
    original_pdi = _estimate_pdi_volume(segmented, 0.25)
    filtered_pts, filter_metrics = apply_winner_filter(pipeline_pts)
    filtered_cloud = make_cloud(filtered_pts)
    filtered_pdi = _estimate_pdi_volume(filtered_cloud, 0.25)
    return {
        "raw_scaled_points": raw_pts,
        "cleaned_points": cleaned_pts,
        "pipeline_points": pipeline_pts,
        "filtered_points": filtered_pts,
        "segmentation_quality": segmentation_quality,
        "original_pdi": original_pdi,
        "filtered_pdi": filtered_pdi,
        "filter_metrics": filter_metrics,
    }


def main() -> int:
    started = time.time()
    if RUN_DIR.exists():
        shutil.rmtree(RUN_DIR)
    for sub in ["views", "captures"]:
        (RUN_DIR / sub).mkdir(parents=True, exist_ok=True)
    settings = settings_for_host()
    imgs = image_paths()
    store = SessionStore(settings)
    resume_session_id = os.environ.get("FORESTVOL_RESUME_SESSION_ID")
    if resume_session_id:
        session_id = resume_session_id
        point_cloud_path = store.processed_dir(session_id) / "point_cloud.ply"
        if not point_cloud_path.exists():
            raise RuntimeError(f"Resume point cloud does not exist: {point_cloud_path}")
        reconstructed_scale = estimate_reconstructed_aruco_scale(
            point_cloud_path,
            marker_size_m=settings.calibration_marker_size_cm / 100.0,
        )
        scale_payload = {
            "scale_certified": True,
            "reason": "reconstructed_aruco_3d_resume_from_existing_nodeodm_cloud",
            "reconstructed_aruco_scale": reconstructed_scale.to_payload(),
        }
        nodeodm = {
            "attempts": "resumed_from_existing_nodeodm_point_cloud",
            "task_uuid": os.environ.get("FORESTVOL_RESUME_NODEODM_TASK_UUID"),
            "scale_payload": scale_payload,
        }
    else:
        session_id, uploads = create_session(store, imgs)
        point_cloud_path, nodeodm = run_nodeodm(session_id, uploads, settings, store)
    scale_factor = float(nodeodm["scale_payload"]["reconstructed_aruco_scale"]["scale_factor_m_per_unit"])
    vol = run_volume(point_cloud_path, scale_factor)

    pipeline_pts = vol["pipeline_points"]
    filtered_pts = vol["filtered_points"]
    write_cloud(RUN_DIR / "pipeline_output.ply", pipeline_pts)
    write_cloud(RUN_DIR / "filtered_cloud.ply", filtered_pts)
    ov_pts, ov_colors = overlay(pipeline_pts, filtered_pts)
    write_cloud(RUN_DIR / "overlay_before_after.ply", ov_pts, ov_colors)
    for mode in ["front", "side", "top", "iso"]:
        render_view(ov_pts, ov_colors, RUN_DIR / f"{mode}.png", mode)
        render_view(ov_pts, ov_colors, RUN_DIR / "views" / f"{mode}.png", mode)

    e2e_volume = float(vol["filtered_pdi"]["volume_m3"])
    comparison = [
        {
            "metric": "pipeline_original_reference",
            "volume_m3": PIPELINE_ORIGINAL_M3,
            "difference_vs_real_m3": round(abs(PIPELINE_ORIGINAL_M3 - GROUND_TRUTH_M3), 6),
            "error_percent": round(abs(PIPELINE_ORIGINAL_M3 - GROUND_TRUTH_M3) / GROUND_TRUTH_M3 * 100, 6),
            "difference_vs_benchmark_m3": "",
        },
        {
            "metric": "benchmark_winner_reference",
            "volume_m3": BENCHMARK_VOLUME_M3,
            "difference_vs_real_m3": round(abs(BENCHMARK_VOLUME_M3 - GROUND_TRUTH_M3), 6),
            "error_percent": round(abs(BENCHMARK_VOLUME_M3 - GROUND_TRUTH_M3) / GROUND_TRUTH_M3 * 100, 6),
            "difference_vs_benchmark_m3": 0.0,
        },
        {
            "metric": "set_fotos_ultimo_e2e_with_winner_filter",
            "volume_m3": e2e_volume,
            "difference_vs_real_m3": round(abs(e2e_volume - GROUND_TRUTH_M3), 6),
            "error_percent": round(abs(e2e_volume - GROUND_TRUTH_M3) / GROUND_TRUTH_M3 * 100, 6),
            "difference_vs_benchmark_m3": round(e2e_volume - BENCHMARK_VOLUME_M3, 6),
        },
    ]
    with (RUN_DIR / "comparison.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(comparison[0].keys()))
        writer.writeheader()
        writer.writerows(comparison)
    (RUN_DIR / "comparison.json").write_text(json.dumps(comparison, indent=2), encoding="utf-8")

    filtered_components = components(filtered_pts)
    metrics = {
        "dataset": str(DATASET),
        "image_count": len(imgs),
        "session_id": session_id,
        "point_cloud_path": str(point_cloud_path),
        "nodeodm": nodeodm,
        "configuration": {"algorithm": "obb_plus_curvature", "obb_percentile": 80, "curvature_percentile": 80},
        "scale_factor_m_per_unit": scale_factor,
        "stage_points": {
            "raw_scaled": int(len(vol["raw_scaled_points"])),
            "after_clean": int(len(vol["cleaned_points"])),
            "pipeline_volume_input_before_filter": int(len(pipeline_pts)),
            "after_winner_filter": int(len(filtered_pts)),
        },
        "filter_metrics": vol["filter_metrics"],
        "segmentation_quality": vol["segmentation_quality"],
        "original_pdi_recomputed_for_this_run": vol["original_pdi"],
        "filtered_pdi": vol["filtered_pdi"],
        "geometry": {
            "before_filter_aabb": bbox(pipeline_pts),
            "after_filter_aabb": bbox(filtered_pts),
            "after_filter_hull_volume_m3": float(ConvexHull(filtered_pts).volume),
            "after_filter_components_eps035": filtered_components,
        },
        "comparison": comparison,
        "validations": {
            "pipeline_completed": True,
            "filtered_cloud_valid": bool(len(filtered_pts) >= 4 and np.all(np.isfinite(filtered_pts))),
            "volume_completed": "volume_m3" in vol["filtered_pdi"],
            "unexpected_components": filtered_components["component_count"] != 1,
            "benchmark_difference_abs_m3": round(abs(e2e_volume - BENCHMARK_VOLUME_M3), 6),
        },
        "runtime_seconds": round(time.time() - started, 3),
    }
    (RUN_DIR / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    (RUN_DIR / "captures" / "volume_obtained.txt").write_text(
        f"volume_m3={e2e_volume}\nbenchmark_reference_m3={BENCHMARK_VOLUME_M3}\nground_truth_m3={GROUND_TRUTH_M3}\n",
        encoding="utf-8",
    )

    report = [
        "# E2E Validation with set_fotos_ultimo\n\n",
        "## Alcance\n",
        "Pipeline completo desde imagenes con NodeODM sobre `set_fotos_ultimo`. La unica insercion experimental fue `obb_plus_curvature` inmediatamente antes del PDI. No hubo busqueda ni ajuste de parametros.\n\n",
        "## Configuracion\n",
        "- Algoritmo: `obb_plus_curvature`\n",
        "- `obb_percentile`: `80`\n",
        "- `curvature_percentile`: `80`\n\n",
        "## Comparacion\n",
        "| Caso | Volumen m3 | Dif. vs real m3 | Error % | Dif. vs benchmark m3 |\n",
        "|---|---:|---:|---:|---:|\n",
    ]
    for row in comparison:
        report.append(f"| {row['metric']} | {row['volume_m3']} | {row['difference_vs_real_m3']} | {row['error_percent']} | {row['difference_vs_benchmark_m3']} |\n")
    report.extend(
        [
            "\n## Validaciones\n",
            f"- Session ID: `{session_id}`\n",
            f"- NodeODM task: `{nodeodm['task_uuid']}`\n",
            f"- Scale factor reconstructed ArUco: `{scale_factor}`\n",
            f"- Puntos antes del filtro: `{len(pipeline_pts)}`\n",
            f"- Puntos despues del filtro: `{len(filtered_pts)}`\n",
            f"- Componentes despues del filtro eps=0.35: `{filtered_components['component_count']}`\n",
            f"- Volumetria completada: `{metrics['validations']['volume_completed']}`\n",
            f"- Diferencia absoluta vs benchmark: `{metrics['validations']['benchmark_difference_abs_m3']}` m3\n\n",
            "## Entregables\n",
            "- `pipeline_output.ply`\n",
            "- `filtered_cloud.ply`\n",
            "- `overlay_before_after.ply`\n",
            "- `front.png`, `side.png`, `top.png`, `iso.png`\n",
            "- `metrics.json`, `comparison.csv`, `comparison.json`\n\n",
        ]
    )
    (RUN_DIR / "report.md").write_text("".join(report), encoding="utf-8")

    # Copy required deliverables to the root end_to_end_validation folder as the latest run.
    for name in [
        "report.md",
        "metrics.json",
        "comparison.csv",
        "comparison.json",
        "pipeline_output.ply",
        "filtered_cloud.ply",
        "overlay_before_after.ply",
        "front.png",
        "side.png",
        "top.png",
        "iso.png",
    ]:
        shutil.copy2(RUN_DIR / name, OUT / name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
