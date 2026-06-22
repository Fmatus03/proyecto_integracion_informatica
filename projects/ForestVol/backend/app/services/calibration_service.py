"""Spatial calibration service for ForestVol Hito 1."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from backend.app.config import Settings

ARUCO_MARKER_ID = 0
ARUCO_DICTIONARY = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)


class CalibrationFailedError(Exception):
    """Raised when automatic calibration cannot proceed and no manual scale exists."""

    def __init__(self, message: str, detection_confidence: float = 0.0) -> None:
        super().__init__(message)
        self.detection_confidence = detection_confidence


@dataclass(frozen=True)
class MarkerDetection:
    """Detected ArUco marker metrics for a single image."""

    image_path: str
    marker_id: int
    side_px: float
    scale_px_per_cm: float
    homography_px_to_cm: list[list[float]]
    corners_px: list[list[float]]


@dataclass(frozen=True)
class CalibrationResult:
    """Result returned by spatial calibration."""

    calibration_mode: str
    guide_detected_in_n_images: int
    guide_visible_in_n_images: int
    detection_confidence: float
    scale_px_per_cm: float
    scale_error_percentage: float | None
    marker_detections: list[MarkerDetection]
    warning: str | None = None


@dataclass(frozen=True)
class DetectionVariant:
    """Image variant used to recover valid ArUco detections under mild blur/aliasing."""

    gray: np.ndarray
    scale_factor: float
    corner_offset: np.ndarray


def _image_paths_for_session(upload_dir: Path) -> list[Path]:
    allowed = {".jpg", ".jpeg", ".png"}
    return sorted(path for path in upload_dir.iterdir() if path.is_file() and path.suffix.lower() in allowed)


def _side_length_px(corners: np.ndarray) -> float:
    points = corners.reshape(4, 2).astype(np.float32)
    sides = [
        np.linalg.norm(points[1] - points[0]),
        np.linalg.norm(points[2] - points[1]),
        np.linalg.norm(points[3] - points[2]),
        np.linalg.norm(points[0] - points[3]),
    ]
    return float(np.mean(sides))


def _homography_px_to_cm(corners: np.ndarray, marker_size_cm: float) -> list[list[float]]:
    source = corners.reshape(4, 2).astype(np.float32)
    destination = np.array(
        [
            [0.0, 0.0],
            [marker_size_cm, 0.0],
            [marker_size_cm, marker_size_cm],
            [0.0, marker_size_cm],
        ],
        dtype=np.float32,
    )
    homography = cv2.getPerspectiveTransform(source, destination)
    return homography.astype(float).tolist()


def _read_grayscale(image_path: Path) -> np.ndarray | None:
    image = cv2.imread(str(image_path), cv2.IMREAD_UNCHANGED)
    if image is None:
        return None
    if len(image.shape) == 3 and image.shape[2] == 4:
        alpha = image[:, :, 3].astype(np.float32) / 255.0
        color = image[:, :, :3].astype(np.float32)
        white = np.full_like(color, 255.0)
        image = (color * alpha[..., None] + white * (1.0 - alpha[..., None])).astype(np.uint8)
    if len(image.shape) == 2:
        return image
    return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)


def _detect_corners(gray: np.ndarray) -> tuple[list[np.ndarray], np.ndarray | None]:
    corners, ids, _rejected = cv2.aruco.detectMarkers(gray, ARUCO_DICTIONARY)
    return corners, ids


def _build_detection_variants(gray: np.ndarray) -> list[DetectionVariant]:
    base_variants = [
        gray,
        cv2.GaussianBlur(gray, (5, 5), 0),
        cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1],
    ]
    upscaled = cv2.resize(gray, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
    variants: list[DetectionVariant] = []
    for variant in base_variants:
        variants.append(
            DetectionVariant(
                gray=variant,
                scale_factor=1.0,
                corner_offset=np.array([0.0, 0.0], dtype=np.float32),
            )
        )
        pad = max(10, int(min(variant.shape[:2]) * 0.05))
        variants.append(
            DetectionVariant(
                gray=cv2.copyMakeBorder(variant, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=255),
                scale_factor=1.0,
                corner_offset=np.array([float(pad), float(pad)], dtype=np.float32),
            )
        )
    variants.append(
        DetectionVariant(
            gray=upscaled,
            scale_factor=2.0,
            corner_offset=np.array([0.0, 0.0], dtype=np.float32),
        )
    )
    return variants


def _detect_marker(image_path: Path, marker_size_cm: float) -> MarkerDetection | None:
    gray = _read_grayscale(image_path)
    if gray is None:
        return None

    for variant in _build_detection_variants(gray):
        corners, ids = _detect_corners(variant.gray)
        if ids is None:
            continue

        for index, marker_id in enumerate(ids.flatten()):
            if int(marker_id) != ARUCO_MARKER_ID:
                continue

            marker_corners = corners[index].astype(np.float32)
            marker_corners -= variant.corner_offset
            marker_corners /= variant.scale_factor
            cv2.cornerSubPix(
                gray,
                marker_corners,
                winSize=(5, 5),
                zeroZone=(-1, -1),
                criteria=(cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001),
            )
            side_px = _side_length_px(marker_corners)
            return MarkerDetection(
                image_path=str(image_path),
                marker_id=ARUCO_MARKER_ID,
                side_px=side_px,
                scale_px_per_cm=side_px / marker_size_cm,
                homography_px_to_cm=_homography_px_to_cm(marker_corners, marker_size_cm),
                corners_px=marker_corners.reshape(4, 2).astype(float).tolist(),
            )

    return None


def _scale_error_percentage(
    measured_scale_px_per_cm: float,
    expected_scale_px_per_cm: float | None,
) -> float | None:
    if expected_scale_px_per_cm is None:
        return None
    return abs(measured_scale_px_per_cm - expected_scale_px_per_cm) / expected_scale_px_per_cm * 100.0


def _resolve_visible_image_paths(
    image_paths: list[Path],
    visible_image_names: list[str] | None,
) -> list[Path]:
    if not visible_image_names:
        return image_paths
    image_index = {path.name: path for path in image_paths}
    visible_paths: list[Path] = []
    for image_name in visible_image_names:
        image_path = image_index.get(image_name)
        if image_path is not None and image_path not in visible_paths:
            visible_paths.append(image_path)
    return visible_paths or image_paths


def calibrate_session(
    session_id: str,
    settings: Settings,
    manual_scale_px_per_cm: float | None = None,
    visible_image_names: list[str] | None = None,
) -> CalibrationResult:
    """Calibrate a session using ArUco DICT_4X4_50 ID 0 or manual scale fallback."""

    image_paths = _image_paths_for_session(settings.upload_path / session_id)
    visible_image_paths = _resolve_visible_image_paths(image_paths, visible_image_names)
    return calibrate_image_paths(
        image_paths,
        settings,
        manual_scale_px_per_cm=manual_scale_px_per_cm,
        visible_image_paths=visible_image_paths,
    )


def calibrate_image_paths(
    image_paths: list[Path],
    settings: Settings,
    manual_scale_px_per_cm: float | None = None,
    expected_scale_px_per_cm: float | None = None,
    visible_image_paths: list[Path] | None = None,
) -> CalibrationResult:
    """Calibrate a list of image paths using the Hito 1 calibration contract."""

    if not image_paths:
        raise CalibrationFailedError("No usable JPG/PNG images found for calibration")

    detections = [
        detection
        for path in image_paths
        if (detection := _detect_marker(path, settings.calibration_marker_size_cm)) is not None
    ]
    visible_paths = visible_image_paths or image_paths
    visible_names = {path.name for path in visible_paths}
    confidence_detections = [
        detection for detection in detections if Path(detection.image_path).name in visible_names
    ]
    detection_confidence = len(confidence_detections) / len(visible_paths)

    if confidence_detections and detection_confidence >= settings.calibration_confidence_threshold:
        scale_values = [detection.scale_px_per_cm for detection in confidence_detections]
        measured_scale_px_per_cm = float(np.mean(scale_values))
        return CalibrationResult(
            calibration_mode="automatic",
            guide_detected_in_n_images=len(confidence_detections),
            guide_visible_in_n_images=len(visible_paths),
            detection_confidence=round(detection_confidence, 4),
            scale_px_per_cm=round(measured_scale_px_per_cm, 4),
            scale_error_percentage=(
                None
                if expected_scale_px_per_cm is None
                else round(_scale_error_percentage(measured_scale_px_per_cm, expected_scale_px_per_cm), 4)
            ),
            marker_detections=confidence_detections,
        )

    if manual_scale_px_per_cm is not None:
        scale_error_percentage = _scale_error_percentage(manual_scale_px_per_cm, expected_scale_px_per_cm)
        return CalibrationResult(
            calibration_mode="manual",
            guide_detected_in_n_images=len(confidence_detections),
            guide_visible_in_n_images=len(visible_paths),
            detection_confidence=round(detection_confidence, 4),
            scale_px_per_cm=round(float(manual_scale_px_per_cm), 4),
            scale_error_percentage=None if scale_error_percentage is None else round(scale_error_percentage, 4),
            marker_detections=confidence_detections,
            warning=(
                "Automatic detection confidence below threshold "
                f"({settings.calibration_confidence_threshold:.2f}). Manual scale applied."
            ),
        )

    raise CalibrationFailedError(
        "Automatic calibration did not meet confidence threshold and manual scale was not provided",
        detection_confidence=round(detection_confidence, 4),
    )


def calibration_result_to_session_payload(result: CalibrationResult) -> dict[str, Any]:
    """Serialize calibration details for session persistence."""

    return {
        "calibration_mode": result.calibration_mode,
        "guide_detected_in_n_images": result.guide_detected_in_n_images,
        "guide_visible_in_n_images": result.guide_visible_in_n_images,
        "detection_confidence": result.detection_confidence,
        "scale_px_per_cm": result.scale_px_per_cm,
        "scale_error_percentage": result.scale_error_percentage,
        "warning": result.warning,
        "marker_detections": [
            {
                "image_path": detection.image_path,
                "marker_id": detection.marker_id,
                "side_px": round(detection.side_px, 4),
                "scale_px_per_cm": round(detection.scale_px_per_cm, 4),
                "homography_px_to_cm": detection.homography_px_to_cm,
                "corners_px": detection.corners_px,
            }
            for detection in result.marker_detections
        ],
    }
