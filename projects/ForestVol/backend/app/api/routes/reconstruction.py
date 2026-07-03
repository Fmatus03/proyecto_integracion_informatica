"""NodeODM reconstruction routes for Hito 0."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from backend.app.config import Settings, get_settings
from backend.app.models.schemas import ReconstructionResponse, ResultResponse
from backend.app.services.cloud_provider import load_pipeline_point_cloud
from backend.app.services.mesh_service import (
    MeshProcessingError,
    generate_preliminary_volumetry,
    mesh_artifacts_to_session_payload,
)
from backend.app.services.gcp_service import generate_aruco_gcp_file
from backend.app.services.nodeodm_client import ATTEMPTS, STATUS_COMPLETED, NodeODMClient
from backend.app.services.reconstructed_scale_service import (
    ReconstructedScaleError,
    estimate_reconstructed_aruco_scale,
)
from backend.app.services.scale_service import inspect_scale_inputs
from backend.app.services.session_store import SessionStore

router = APIRouter(prefix="/api", tags=["reconstruction"])
executor = ThreadPoolExecutor(max_workers=1)


def _raise(status_code: int, code: str, message: str) -> None:
    raise HTTPException(status_code=status_code, detail={"error_code": code, "message": message})


def _ground_truth_volume_m3() -> float | None:
    manifest_path = Path("projects/ForestVol/set_imagenes+guia/dataset_manifest.json")
    if not manifest_path.exists():
        return None
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return manifest.get("validation_contract", {}).get("ground_truth_volume_m3")


def _metric_point_cloud_scale_from_session(session: dict) -> tuple[float | None, str | None]:
    scale_evidence = session.get("scale_evidence") or {}
    reconstructed_scale = scale_evidence.get("reconstructed_aruco_scale") or {}
    scale_factor = reconstructed_scale.get("scale_factor_m_per_unit")
    if scale_evidence.get("scale_certified") and scale_factor:
        return float(scale_factor), "reconstructed_aruco_3d"
    return None, None


def _run_preliminary_volumetry(session_id: str, settings: Settings, store: SessionStore, session: dict) -> None:
    scale_px_per_cm = session.get("calibration", {}).get("scale_px_per_cm")
    point_cloud_scale_m_per_unit, scale_source = _metric_point_cloud_scale_from_session(session)
    if not session.get("point_cloud_path"):
        raise MeshProcessingError("Point cloud is required before preliminary volumetry")
    cloud_source = load_pipeline_point_cloud(session_id, settings)

    session["pipeline_state"] = "MESH_PENDING"
    session["message"] = "Preliminary mesh generation started"
    session["cloud_source"] = cloud_source.fingerprint()
    store.save_session(session_id, session)

    artifacts = generate_preliminary_volumetry(
        cloud_source.path,
        store.processed_dir(session_id),
        scale_px_per_cm=scale_px_per_cm,
        ground_truth_volume_m3=_ground_truth_volume_m3(),
        point_cloud_scale_m_per_unit=point_cloud_scale_m_per_unit,
        scale_source=scale_source,
    )
    payload = mesh_artifacts_to_session_payload(artifacts)
    session["mesh"] = {
        key: payload[key]
        for key in (
            "mesh_ply_path",
            "mesh_glb_path",
            "mesh_watertight",
            "mesh_repair_applied",
            "repair_cycles",
            "vertex_count",
            "triangle_count",
            "point_cloud_quality",
            "warning",
            "legacy_mesh_enabled",
        )
    }
    session["volume"] = {
        key: payload[key]
        for key in (
            "volume_m3",
            "volume_method",
            "confidence_score",
            "confidence_level",
            "quality_gates",
            "diagnostic",
            "pdi_metrics",
            "bounding_box_m",
            "ground_truth_volume_m3",
            "error_percentage",
        )
    }
    session["pipeline_state"] = "COMPLETED"
    session["message"] = "Preliminary volumetry completed"
    store.save_session(session_id, session)


def _run_reconstruction(session_id: str, settings: Settings) -> None:
    store = SessionStore(settings)
    session = store.load_session(session_id)
    if session is None:
        return

    client = NodeODMClient(settings)
    image_paths = sorted((settings.upload_path / session_id).glob("*"))
    image_paths = [path for path in image_paths if path.is_file() and path.suffix.lower() in {".png", ".jpg", ".jpeg"}]
    processed_dir = store.processed_dir(session_id)
    dataset_root = Path("projects/ForestVol/set_imagenes+guia/set_fotos_castillo_de_madera")
    scale_evidence = inspect_scale_inputs(image_paths, dataset_root)
    try:
        gcp_result = generate_aruco_gcp_file(
            image_paths,
            processed_dir,
            marker_size_cm=settings.calibration_marker_size_cm,
        )
        scale_payload = scale_evidence.to_payload()
        scale_payload.update(
            {
                "gcp_path": gcp_result.gcp_path,
                "scale_certified": False,
                "reason": "aruco_gcp_generated_pending_3d_validation",
                "aruco_gcp": gcp_result.to_payload(),
            }
        )
        scale_evidence = type(scale_evidence)(
            image_count=scale_evidence.image_count,
            images_with_exif=scale_evidence.images_with_exif,
            images_with_gps=scale_evidence.images_with_gps,
            gcp_path=gcp_result.gcp_path,
            scale_certified=False,
            reason="aruco_gcp_generated_pending_3d_validation",
        )
    except ValueError as exc:
        scale_payload = scale_evidence.to_payload()
        scale_payload["aruco_gcp_error"] = str(exc)

    session["pipeline_state"] = "RECONSTRUCTING"
    session["message"] = "NodeODM task started"
    session["scale_evidence"] = scale_payload
    store.save_session(session_id, session)

    for attempt in ATTEMPTS:
        attempt_record = {
            "attempt": attempt.name,
            "options": attempt.options,
            "task_uuid": None,
            "status": "started",
            "message": None,
        }
        session["reconstruction_attempts"].append(attempt_record)
        store.save_session(session_id, session)
        try:
            task_uuid = client.submit_task(session_id, image_paths, attempt, scale_evidence=scale_evidence)
            attempt_record["task_uuid"] = task_uuid
            session["nodeodm_task_uuid"] = task_uuid
            store.save_session(session_id, session)

            task_info = client.poll_task(task_uuid)
            session["progress_percentage"] = int(task_info.get("progress", 100))
            if int(task_info["status"]["code"]) == STATUS_COMPLETED:
                point_cloud = client.download_first_ply(task_uuid, processed_dir)
                scale_payload = session.get("scale_evidence") or scale_payload
                try:
                    reconstructed_scale = estimate_reconstructed_aruco_scale(
                        point_cloud,
                        marker_size_m=settings.calibration_marker_size_cm / 100.0,
                    )
                    scale_payload.update(
                        {
                            "scale_certified": True,
                            "reason": "reconstructed_aruco_3d",
                            "reconstructed_aruco_scale": reconstructed_scale.to_payload(),
                        }
                    )
                except ReconstructedScaleError as exc:
                    scale_payload.update(
                        {
                            "scale_certified": False,
                            "reason": "reconstructed_aruco_3d_failed",
                            "reconstructed_aruco_scale_error": {
                                "message": str(exc),
                                "details": exc.details,
                            },
                        }
                    )
                session["pipeline_state"] = "POINT_CLOUD_READY"
                session["point_cloud_path"] = str(point_cloud)
                session["scale_evidence"] = scale_payload
                session["message"] = "Point cloud generated successfully"
                attempt_record["status"] = "completed"
                store.save_session(session_id, session)
                try:
                    _run_preliminary_volumetry(session_id, settings, store, session)
                except MeshProcessingError as exc:
                    session["pipeline_state"] = "FAILED"
                    session["error_code"] = "MESH_PROCESSING_FAILED"
                    session["message"] = str(exc)
                    session["mesh"] = {
                        "mesh_watertight": False,
                        "error_details": exc.details,
                    }
                    store.save_session(session_id, session)
                return

            attempt_record["status"] = "failed"
            attempt_record["message"] = "NodeODM returned FAILED"
            store.save_session(session_id, session)
        except TimeoutError as exc:
            attempt_record["status"] = "failed"
            attempt_record["message"] = str(exc)
            session["error_code"] = "NODEODM_TIMEOUT"
            store.save_session(session_id, session)
        except Exception as exc:  # pragma: no cover - exercised via docker validation
            attempt_record["status"] = "failed"
            attempt_record["message"] = str(exc)
            session["error_code"] = "NODEODM_PROCESSING_FAILED"
            store.save_session(session_id, session)

    session["pipeline_state"] = "FAILED"
    session["message"] = "NodeODM failed after 3 fallback attempts"
    if session["error_code"] is None:
        session["error_code"] = "NODEODM_PROCESSING_FAILED"
    store.save_session(session_id, session)


@router.post("/reconstruct/{session_id}", response_model=ReconstructionResponse, status_code=202)
def reconstruct(
    session_id: str,
    settings: Settings = Depends(get_settings),
) -> ReconstructionResponse:
    store = SessionStore(settings)
    session = store.load_session(session_id)
    if session is None:
        _raise(404, "SESSION_NOT_FOUND", "Session not found")
    if session["pipeline_state"] in {"RECONSTRUCTION_PENDING", "RECONSTRUCTING"}:
        _raise(409, "RECONSTRUCTION_IN_PROGRESS", "Reconstruction is already in progress")
    if session["pipeline_state"] != "CALIBRATED":
        if session["pipeline_state"] in {"VALIDATED", "CALIBRATION_PENDING", "FAILED"}:
            _raise(424, "CALIBRATION_REQUIRED", "Spatial calibration is required before reconstruction")
        _raise(409, "INVALID_PIPELINE_STATE", f"Cannot reconstruct from {session['pipeline_state']}")

    session["pipeline_state"] = "RECONSTRUCTION_PENDING"
    session["progress_percentage"] = 0
    session["message"] = "Reconstruction task submitted to NodeODM"
    session["error_code"] = None
    session["reconstruction_attempts"] = []
    store.save_session(session_id, session)

    executor.submit(_run_reconstruction, session_id, settings)
    return ReconstructionResponse(
        session_id=session_id,
        pipeline_state="RECONSTRUCTION_PENDING",
        message="Reconstruction task submitted to NodeODM. Poll /api/results/{session_id} for status.",
    )


@router.get("/results/{session_id}", response_model=ResultResponse)
def results(
    session_id: str,
    settings: Settings = Depends(get_settings),
) -> ResultResponse:
    store = SessionStore(settings)
    session = store.load_session(session_id)
    if session is None:
        _raise(404, "SESSION_NOT_FOUND", "Session not found")

    mesh = session.get("mesh") or {}
    volume = session.get("volume") or {}
    return ResultResponse(
        session_id=session_id,
        pipeline_state=session["pipeline_state"],
        progress_percentage=session.get("progress_percentage"),
        point_cloud_path=session.get("point_cloud_path"),
        mesh_ply_path=mesh.get("mesh_ply_path"),
        mesh_glb_path=mesh.get("mesh_glb_path"),
        mesh_watertight=mesh.get("mesh_watertight"),
        mesh_repair_applied=mesh.get("mesh_repair_applied"),
        volume_m3=volume.get("volume_m3"),
        volume_method=volume.get("volume_method"),
        confidence_score=volume.get("confidence_score"),
        confidence_level=volume.get("confidence_level"),
        quality_gates=volume.get("quality_gates"),
        diagnostic=volume.get("diagnostic"),
        pdi_metrics=volume.get("pdi_metrics"),
        bounding_box_m=volume.get("bounding_box_m"),
        ground_truth_volume_m3=volume.get("ground_truth_volume_m3"),
        error_percentage=volume.get("error_percentage"),
        reconstruction_attempts=session.get("reconstruction_attempts", []),
        scale_evidence=session.get("scale_evidence"),
        error_code=session.get("error_code"),
        message=session.get("message"),
    )
