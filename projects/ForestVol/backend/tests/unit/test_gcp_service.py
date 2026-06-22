from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from backend.app.services.gcp_service import generate_aruco_gcp_file


def _marker_image(side_px: int = 500, canvas_px: int = 700) -> np.ndarray:
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    marker = cv2.aruco.generateImageMarker(dictionary, 0, side_px)
    canvas = np.full((canvas_px, canvas_px), 255, dtype=np.uint8)
    offset = (canvas_px - side_px) // 2
    canvas[offset : offset + side_px, offset : offset + side_px] = marker
    return canvas


def test_generate_aruco_gcp_file_reuses_detector_outputs_nodeodm_format(tmp_path: Path) -> None:
    image_paths = []
    for index in range(4):
        path = tmp_path / f"image_{index:02d}.png"
        cv2.imwrite(str(path), _marker_image())
        image_paths.append(path)

    result = generate_aruco_gcp_file(image_paths, tmp_path / "processed", marker_size_cm=100.0)
    lines = Path(result.gcp_path).read_text(encoding="utf-8").splitlines()

    assert lines[0] == "EPSG:3857"
    assert result.marker_size_m == 1.0
    assert result.gcp_count == 16
    assert len(result.detections) == 4
    assert "aruco_0_c0" in lines[1]


def test_generate_aruco_gcp_file_sanitizes_nodeodm_image_names(tmp_path: Path) -> None:
    image_path = tmp_path / "Captura de pantalla 2026-06-16 200740.png"
    cv2.imwrite(str(image_path), _marker_image())

    result = generate_aruco_gcp_file([image_path], tmp_path / "processed", marker_size_cm=100.0, min_detections=1)
    contents = Path(result.gcp_path).read_text(encoding="utf-8")

    assert "Capturadepantalla2026-06-16200740.png" in contents
    assert "Captura de pantalla" not in contents
