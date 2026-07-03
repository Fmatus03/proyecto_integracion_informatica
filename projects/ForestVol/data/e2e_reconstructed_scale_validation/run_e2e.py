from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
import traceback
from pathlib import Path

from backend.app.api.routes.reconstruction import _run_reconstruction
from backend.app.config import get_settings
from backend.app.services.calibration_service import (
    CalibrationFailedError,
    calibrate_session,
    calibration_result_to_session_payload,
)
from backend.app.services.session_store import SessionStore


DATASET = Path("/app/projects/ForestVol/set_imagenes+guia/set_fotos_castillo_de_madera_defnitivo")
OUT_ROOT = Path("/app/data/e2e_reconstructed_scale_validation")
EXPECTED_VOLUME_M3 = 119.74
PHYSICAL_ARUCO_SIDE_M = 1.0


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")


def append_log(path: Path, message: str) -> None:
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"[{timestamp}] {message}\n")


def extract_run_metrics(session: dict) -> dict:
    scale = (session.get("scale_evidence") or {}).get("reconstructed_aruco_scale") or {}
    volume = session.get("volume") or {}
    pdi = volume.get("pdi_metrics") or {}
    diagnostic = volume.get("diagnostic") or {}
    segmentation = diagnostic.get("segmentation") or {}
    return {
        "session_id": session.get("session_id"),
        "pipeline_state": session.get("pipeline_state"),
        "message": session.get("message"),
        "error_code": session.get("error_code"),
        "point_cloud_path": session.get("point_cloud_path"),
        "scale_evidence": session.get("scale_evidence"),
        "aruco_detection": {
            "selected_candidate": scale.get("selected_candidate"),
            "reconstructed_side_units": scale.get("reconstructed_side_units"),
            "physical_side_m": PHYSICAL_ARUCO_SIDE_M,
            "scale_factor_m_per_unit": scale.get("scale_factor_m_per_unit"),
            "confidence": scale.get("confidence"),
            "point_count": scale.get("point_count"),
        },
        "scaling": {
            "factor_applied": scale.get("scale_factor_m_per_unit"),
            "source": "reconstructed_aruco_3d" if scale else None,
        },
        "segmentation": segmentation,
        "pdi": {
            "hull_volume_m3": pdi.get("hull_volume_m3"),
            "volume_m3": pdi.get("volume_m3"),
            "voxel_size_m": pdi.get("voxel_size_m"),
            "occupied_voxels": pdi.get("occupied_voxels"),
            "filled_voxels": pdi.get("filled_voxels"),
        },
        "volume": {
            "volume_m3": volume.get("volume_m3"),
            "volume_method": volume.get("volume_method"),
            "expected_volume_m3": EXPECTED_VOLUME_M3,
            "error_percentage": volume.get("error_percentage"),
        },
        "reconstruction_attempts": session.get("reconstruction_attempts", []),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True, choices=["run_1", "run_2"])
    args = parser.parse_args()

    run_dir = OUT_ROOT / args.run
    run_dir.mkdir(parents=True, exist_ok=True)
    log_path = run_dir / "runner.log"
    write_json(
        run_dir / "status.json",
        {
            "run": args.run,
            "status": "starting",
            "dataset": str(DATASET),
            "physical_aruco_side_m": PHYSICAL_ARUCO_SIDE_M,
            "expected_volume_m3": EXPECTED_VOLUME_M3,
            "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        },
    )
    append_log(log_path, "Starting E2E run")

    try:
        settings = get_settings()
        store = SessionStore(settings)
        images = sorted(
            path
            for path in DATASET.iterdir()
            if path.is_file() and path.suffix.lower() in {".png", ".jpg", ".jpeg"}
        )
        append_log(log_path, f"Dataset images found: {len(images)}")
        if not images:
            raise RuntimeError(f"No images found in {DATASET}")

        session = store.create_session([path.name for path in images])
        session_id = session["session_id"]
        append_log(log_path, f"Created session: {session_id}")
        write_json(
            run_dir / "status.json",
            {
                "run": args.run,
                "status": "copying_images",
                "session_id": session_id,
                "image_count": len(images),
                "dataset": str(DATASET),
            },
        )

        store.store_images(session_id, [(path.name, path.read_bytes()) for path in images])
        append_log(log_path, "Images copied into session upload folder")

        session = store.load_session(session_id)
        session["pipeline_state"] = "CALIBRATION_PENDING"
        session["error_code"] = None
        session["message"] = "Spatial calibration started"
        store.save_session(session_id, session)
        write_json(
            run_dir / "status.json",
            {
                "run": args.run,
                "status": "calibrating",
                "session_id": session_id,
                "image_count": len(images),
            },
        )

        calibration = calibrate_session(session_id, settings)
        session = store.load_session(session_id)
        session["pipeline_state"] = "CALIBRATED"
        session["calibration"] = calibration_result_to_session_payload(calibration)
        session["message"] = "Spatial calibration completed"
        store.save_session(session_id, session)
        append_log(
            log_path,
            "Calibration completed: "
            f"mode={calibration.calibration_mode}, detections={calibration.guide_detected_in_n_images}, "
            f"confidence={calibration.detection_confidence}",
        )

        write_json(
            run_dir / "status.json",
            {
                "run": args.run,
                "status": "reconstructing",
                "session_id": session_id,
                "image_count": len(images),
                "calibration": calibration_result_to_session_payload(calibration),
            },
        )

        _run_reconstruction(session_id, settings)
        session = store.load_session(session_id)
        metrics = extract_run_metrics(session)
        write_json(run_dir / "session.json", session)
        write_json(run_dir / "metrics.json", metrics)
        write_json(
            run_dir / "status.json",
            {
                "run": args.run,
                "status": "completed" if session.get("pipeline_state") == "COMPLETED" else "failed",
                "session_id": session_id,
                "pipeline_state": session.get("pipeline_state"),
                "message": session.get("message"),
                "error_code": session.get("error_code"),
                "volume_m3": metrics["volume"]["volume_m3"],
                "error_percentage": metrics["volume"]["error_percentage"],
                "scale_factor_m_per_unit": metrics["aruco_detection"]["scale_factor_m_per_unit"],
            },
        )
        append_log(log_path, f"Run finished with state={session.get('pipeline_state')}")

        point_cloud = session.get("point_cloud_path")
        if point_cloud and Path(point_cloud).exists():
            shutil.copy2(point_cloud, run_dir / "point_cloud.ply")
            append_log(log_path, "Copied point_cloud.ply")

        return 0 if session.get("pipeline_state") == "COMPLETED" else 2

    except CalibrationFailedError as exc:
        append_log(log_path, f"Calibration failed: {exc}")
        write_json(run_dir / "status.json", {"run": args.run, "status": "failed", "error": str(exc)})
        return 3
    except Exception as exc:
        append_log(log_path, f"Unhandled error: {exc}")
        append_log(log_path, traceback.format_exc())
        write_json(run_dir / "status.json", {"run": args.run, "status": "failed", "error": str(exc)})
        return 1


if __name__ == "__main__":
    sys.exit(main())
