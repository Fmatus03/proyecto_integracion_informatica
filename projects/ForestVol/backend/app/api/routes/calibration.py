"""Calibration routes for ForestVol Hito 1."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from backend.app.config import Settings, get_settings
from backend.app.models.schemas import CalibrationRequest, CalibrationResponse
from backend.app.services.calibration_service import (
    CalibrationFailedError,
    calibrate_session,
    calibration_result_to_session_payload,
)
from backend.app.services.session_store import SessionStore

router = APIRouter(prefix="/api", tags=["calibration"])


def _raise(status_code: int, code: str, message: str) -> None:
    raise HTTPException(status_code=status_code, detail={"error_code": code, "message": message})


@router.post("/calibrate/{session_id}", response_model=CalibrationResponse)
def calibrate(
    session_id: str,
    request: CalibrationRequest | None = None,
    settings: Settings = Depends(get_settings),
) -> CalibrationResponse:
    store = SessionStore(settings)
    session = store.load_session(session_id)
    if session is None:
        _raise(404, "SESSION_NOT_FOUND", "Session not found")

    session["pipeline_state"] = "CALIBRATION_PENDING"
    session["error_code"] = None
    session["message"] = "Spatial calibration started"
    store.save_session(session_id, session)

    manual_scale = request.manual_scale_px_per_cm if request is not None else None
    visible_image_names = request.visible_image_names if request is not None else None
    try:
        result = calibrate_session(
            session_id,
            settings,
            manual_scale_px_per_cm=manual_scale,
            visible_image_names=visible_image_names,
        )
    except CalibrationFailedError as exc:
        session["pipeline_state"] = "FAILED"
        session["error_code"] = "CALIBRATION_FAILED"
        session["message"] = str(exc)
        session["detection_confidence"] = exc.detection_confidence
        store.save_session(session_id, session)
        _raise(422, "CALIBRATION_FAILED", str(exc))

    session["pipeline_state"] = "CALIBRATED"
    session["calibration"] = calibration_result_to_session_payload(result)
    session["message"] = "Spatial calibration completed"
    store.save_session(session_id, session)

    return CalibrationResponse(
        session_id=session_id,
        calibration_mode=result.calibration_mode,
        guide_detected_in_n_images=result.guide_detected_in_n_images,
        detection_confidence=result.detection_confidence,
        scale_px_per_cm=result.scale_px_per_cm,
        scale_error_percentage=result.scale_error_percentage,
        warning=result.warning,
        pipeline_state="CALIBRATED",
    )
