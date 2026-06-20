from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

import cv2
import numpy as np
import pytest
from fastapi import HTTPException

from backend.app.api.routes.calibration import calibrate
from backend.app.config import get_settings
from backend.app.models.schemas import CalibrationRequest
from backend.app.services.calibration_service import (
    CalibrationFailedError,
    calibrate_image_paths,
    calibrate_session,
)
from backend.app.services.session_store import SessionStore


def _settings(tmp_path: Path):
    return replace(
        get_settings(),
        upload_path=tmp_path / "uploads",
        processed_path=tmp_path / "processed",
        export_path=tmp_path / "exports",
        calibration_confidence_threshold=0.90,
        calibration_marker_size_cm=100.0,
    )


def _marker_image(side_px: int = 500, canvas_px: int = 700) -> np.ndarray:
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    marker = cv2.aruco.generateImageMarker(dictionary, 0, side_px)
    canvas = np.full((canvas_px, canvas_px), 255, dtype=np.uint8)
    offset = (canvas_px - side_px) // 2
    canvas[offset : offset + side_px, offset : offset + side_px] = marker
    return canvas


def _blank_image(canvas_px: int = 700) -> np.ndarray:
    return np.full((canvas_px, canvas_px), 255, dtype=np.uint8)


def _write_images(upload_dir: Path, images: list[np.ndarray]) -> list[str]:
    upload_dir.mkdir(parents=True, exist_ok=True)
    filenames: list[str] = []
    for index, image in enumerate(images):
        filename = f"image_{index:02d}.png"
        cv2.imwrite(str(upload_dir / filename), image)
        filenames.append(filename)
    return filenames


def _project_dataset() -> tuple[Path, dict]:
    project_root = Path(__file__).resolve().parents[3]
    manifest_path = project_root / "set_imagenes+guia" / "dataset_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return project_root, manifest


def test_calibrate_session_detects_aruco_id_0_and_computes_scale(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    session_id = "session-auto"
    _write_images(settings.upload_path / session_id, [_marker_image() for _ in range(10)])

    result = calibrate_session(session_id, settings)

    assert result.calibration_mode == "automatic"
    assert result.guide_detected_in_n_images == 10
    assert result.detection_confidence == 1.0
    assert result.scale_px_per_cm == pytest.approx(5.0, abs=0.05)
    assert result.scale_error_percentage is None
    assert result.marker_detections[0].marker_id == 0
    assert len(result.marker_detections[0].homography_px_to_cm) == 3


def test_calibrate_session_uses_configured_marker_size_cm(tmp_path: Path) -> None:
    settings = replace(_settings(tmp_path), calibration_marker_size_cm=50.0)
    session_id = "session-auto-50cm"
    _write_images(settings.upload_path / session_id, [_marker_image() for _ in range(10)])

    result = calibrate_session(session_id, settings)

    assert result.calibration_mode == "automatic"
    assert result.scale_px_per_cm == pytest.approx(10.0, abs=0.05)


def test_calibrate_session_sets_scale_error_when_expected_scale_is_known(tmp_path: Path) -> None:
    settings = replace(_settings(tmp_path), calibration_marker_size_cm=100.0)
    image_path = tmp_path / "known-marker.png"
    cv2.imwrite(str(image_path), _marker_image())

    result = calibrate_image_paths([image_path], settings, expected_scale_px_per_cm=5.0)

    assert result.calibration_mode == "automatic"
    assert result.scale_error_percentage == pytest.approx(0.0, abs=1.0)


def test_calibrate_session_uses_manual_fallback_when_confidence_is_low(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    session_id = "session-manual"
    images = [_marker_image() for _ in range(4)] + [_blank_image() for _ in range(6)]
    _write_images(settings.upload_path / session_id, images)

    result = calibrate_session(session_id, settings, manual_scale_px_per_cm=11.8)

    assert result.calibration_mode == "manual"
    assert result.guide_detected_in_n_images == 4
    assert result.detection_confidence == 0.4
    assert result.scale_px_per_cm == 11.8
    assert result.scale_error_percentage is None
    assert result.warning is not None


def test_calibrate_session_uses_visible_image_names_for_confidence(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    session_id = "session-visible"
    filenames = _write_images(settings.upload_path / session_id, [_marker_image() for _ in range(4)] + [_blank_image() for _ in range(6)])

    result = calibrate_session(
        session_id,
        settings,
        visible_image_names=filenames[:4],
    )

    assert result.calibration_mode == "automatic"
    assert result.guide_detected_in_n_images == 4
    assert result.detection_confidence == 1.0


def test_calibrate_image_paths_recovers_real_dataset_marker_with_preprocessing(tmp_path: Path) -> None:
    project_root, manifest = _project_dataset()
    settings = replace(
        _settings(tmp_path),
        calibration_marker_size_cm=float(manifest["reference_marker"]["physical_size_cm"]),
    )
    image_path = project_root / "set_imagenes+guia" / "set_fotos_castillo_de_madera" / "Captura de pantalla 2026-06-16 200918.png"

    calibrated = calibrate_image_paths([image_path], settings)

    assert calibrated.calibration_mode == "automatic"
    assert calibrated.guide_detected_in_n_images == 1
    assert calibrated.detection_confidence == 1.0


def test_calibrate_session_fails_without_marker_or_manual_fallback(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    session_id = "session-fail"
    _write_images(settings.upload_path / session_id, [_blank_image() for _ in range(10)])

    with pytest.raises(CalibrationFailedError) as exc_info:
        calibrate_session(session_id, settings)

    assert exc_info.value.detection_confidence == 0.0


def test_calibrate_route_persists_result_and_calibrated_state(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    store = SessionStore(settings)
    session = store.create_session([f"image_{index:02d}.png" for index in range(10)])
    _write_images(settings.upload_path / session["session_id"], [_marker_image() for _ in range(10)])

    response = calibrate(session["session_id"], CalibrationRequest(), settings)
    saved = store.load_session(session["session_id"])

    assert response.pipeline_state == "CALIBRATED"
    assert response.calibration_mode == "automatic"
    assert saved is not None
    assert saved["pipeline_state"] == "CALIBRATED"
    assert saved["calibration"]["scale_error_percentage"] is None


def test_calibrate_route_returns_422_calibration_failed(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    store = SessionStore(settings)
    session = store.create_session([f"image_{index:02d}.png" for index in range(10)])
    _write_images(settings.upload_path / session["session_id"], [_blank_image() for _ in range(10)])

    with pytest.raises(HTTPException) as exc_info:
        calibrate(session["session_id"], CalibrationRequest(), settings)

    saved = store.load_session(session["session_id"])
    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["error_code"] == "CALIBRATION_FAILED"
    assert saved is not None
    assert saved["pipeline_state"] == "FAILED"
