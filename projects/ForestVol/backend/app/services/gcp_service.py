"""Generate NodeODM GCP files from the existing ArUco detector."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any

import numpy as np

from backend.app.services.calibration_service import MarkerDetection, _detect_marker


@dataclass(frozen=True)
class GcpGenerationResult:
    gcp_path: str
    marker_size_m: float
    detections: list[MarkerDetection]
    rejected_detections: list[dict[str, Any]]
    gcp_count: int

    def to_payload(self) -> dict[str, Any]:
        return {
            "gcp_path": self.gcp_path,
            "marker_size_m": self.marker_size_m,
            "detections_count": len(self.detections),
            "rejected_detections_count": len(self.rejected_detections),
            "gcp_count": self.gcp_count,
            "detections": [
                {
                    "image_path": detection.image_path,
                    "marker_id": detection.marker_id,
                    "side_px": round(detection.side_px, 4),
                    "corners_px": detection.corners_px,
                }
                for detection in self.detections
            ],
            "rejected_detections": self.rejected_detections,
        }


def _marker_world_corners(marker_size_m: float) -> list[tuple[float, float, float, str]]:
    return [
        (0.0, 0.0, 0.0, "aruco_0_c0"),
        (marker_size_m, 0.0, 0.0, "aruco_0_c1"),
        (marker_size_m, marker_size_m, 0.0, "aruco_0_c2"),
        (0.0, marker_size_m, 0.0, "aruco_0_c3"),
    ]


def nodeodm_safe_filename(filename: str) -> str:
    path = Path(filename)
    stem = re.sub(r"[^A-Za-z0-9_.-]+", "", path.stem)
    suffix = re.sub(r"[^A-Za-z0-9.]+", "", path.suffix)
    return f"{stem}{suffix}"


def _detection_quality(
    detection: MarkerDetection,
    min_side_px: float,
    max_side_cv: float,
    min_area_ratio: float,
) -> tuple[bool, dict[str, Any]]:
    corners = np.asarray(detection.corners_px, dtype=float)
    sides = np.array(
        [
            np.linalg.norm(corners[1] - corners[0]),
            np.linalg.norm(corners[2] - corners[1]),
            np.linalg.norm(corners[3] - corners[2]),
            np.linalg.norm(corners[0] - corners[3]),
        ],
        dtype=float,
    )
    mean_side = float(np.mean(sides))
    side_cv = float(np.std(sides) / mean_side) if mean_side > 0 else float("inf")
    area = float(cv2_contour_area(corners))
    max_side = float(np.max(sides)) if sides.size else 0.0
    area_ratio = float(area / (max_side * max_side)) if max_side > 0 else 0.0
    reasons: list[str] = []
    if mean_side < min_side_px:
        reasons.append("marker_too_small")
    if side_cv > max_side_cv:
        reasons.append("unstable_side_lengths")
    if area_ratio < min_area_ratio:
        reasons.append("marker_too_oblique_or_degenerate")
    return not reasons, {
        "image_path": detection.image_path,
        "side_px": round(detection.side_px, 4),
        "mean_side_px": round(mean_side, 4),
        "side_cv": round(side_cv, 4) if np.isfinite(side_cv) else None,
        "area_ratio": round(area_ratio, 4),
        "reasons": reasons,
    }


def cv2_contour_area(corners: np.ndarray) -> float:
    x = corners[:, 0]
    y = corners[:, 1]
    return abs(float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))) / 2.0)


def generate_aruco_gcp_file(
    image_paths: list[Path],
    output_dir: Path,
    marker_size_cm: float,
    min_detections: int = 4,
    min_side_px: float = 60.0,
    max_side_cv: float = 0.45,
    min_area_ratio: float = 0.18,
    filename: str = "gcp_list.txt",
) -> GcpGenerationResult:
    """Generate a NodeODM GCP file from high-quality ArUco corner detections."""

    output_dir.mkdir(parents=True, exist_ok=True)
    marker_size_m = marker_size_cm / 100.0
    raw_detections = [
        detection
        for image_path in image_paths
        if (detection := _detect_marker(image_path, marker_size_cm)) is not None
    ]
    detections: list[MarkerDetection] = []
    rejected_detections: list[dict[str, Any]] = []
    for detection in raw_detections:
        accepted, quality = _detection_quality(
            detection,
            min_side_px=min_side_px,
            max_side_cv=max_side_cv,
            min_area_ratio=min_area_ratio,
        )
        if accepted:
            detections.append(detection)
        else:
            rejected_detections.append(quality)

    if len(detections) < min_detections:
        raise ValueError(
            "insufficient_high_quality_aruco_detections:"
            f"{len(detections)}:{min_detections}:raw={len(raw_detections)}"
        )

    world_corners = _marker_world_corners(marker_size_m)
    lines = ["EPSG:3857"]
    gcp_count = 0
    for detection in detections:
        image_name = nodeodm_safe_filename(Path(detection.image_path).name)
        for (x_m, y_m, z_m, point_name), (px, py) in zip(world_corners, detection.corners_px):
            lines.append(
                f"{x_m:.6f} {y_m:.6f} {z_m:.6f} {float(px):.4f} {float(py):.4f} {image_name} {point_name}"
            )
            gcp_count += 1

    gcp_path = output_dir / filename
    gcp_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return GcpGenerationResult(
        gcp_path=str(gcp_path),
        marker_size_m=marker_size_m,
        detections=detections,
        rejected_detections=rejected_detections,
        gcp_count=gcp_count,
    )
