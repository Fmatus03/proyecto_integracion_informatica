from __future__ import annotations

from pathlib import Path

from PIL import Image

from backend.app.services.scale_service import inspect_scale_inputs


def test_inspect_scale_inputs_reports_uncertified_without_gps_or_gcp(tmp_path: Path) -> None:
    image_path = tmp_path / "image.png"
    Image.new("RGB", (10, 10)).save(image_path)

    result = inspect_scale_inputs([image_path], tmp_path)

    assert result.image_count == 1
    assert result.images_with_exif == 0
    assert result.images_with_gps == 0
    assert result.gcp_path is None
    assert result.scale_certified is False
    assert result.reason == "missing_gcp_and_gps_exif"


def test_inspect_scale_inputs_accepts_gcp_file(tmp_path: Path) -> None:
    image_path = tmp_path / "image.png"
    Image.new("RGB", (10, 10)).save(image_path)
    gcp_path = tmp_path / "gcp_list.txt"
    gcp_path.write_text("EPSG:4326\n", encoding="utf-8")

    result = inspect_scale_inputs([image_path], tmp_path)

    assert result.gcp_path == str(gcp_path)
    assert result.scale_certified is True
    assert result.reason == "gcp_file_available"
