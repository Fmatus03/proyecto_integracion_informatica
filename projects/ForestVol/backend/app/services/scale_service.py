"""Photogrammetric scale evidence for ForestVol reconstruction."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image


@dataclass(frozen=True)
class ScaleEvidence:
    image_count: int
    images_with_exif: int
    images_with_gps: int
    gcp_path: str | None
    scale_certified: bool
    reason: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "image_count": self.image_count,
            "images_with_exif": self.images_with_exif,
            "images_with_gps": self.images_with_gps,
            "gcp_path": self.gcp_path,
            "scale_certified": self.scale_certified,
            "reason": self.reason,
        }


def _gps_ifd_has_coordinates(gps_ifd: Any) -> bool:
    if not gps_ifd:
        return False
    keys = set(gps_ifd.keys()) if hasattr(gps_ifd, "keys") else set()
    return {1, 2, 3, 4}.issubset(keys) or {"GPSLatitudeRef", "GPSLatitude", "GPSLongitudeRef", "GPSLongitude"}.issubset(keys)


def _image_exif_status(path: Path) -> tuple[bool, bool]:
    try:
        with Image.open(path) as image:
            exif = image.getexif()
            if not exif:
                return False, False
            gps_ifd = exif.get_ifd(34853) if hasattr(exif, "get_ifd") else exif.get(34853)
            return True, _gps_ifd_has_coordinates(gps_ifd)
    except Exception:
        return False, False


def find_gcp_file(dataset_root: Path) -> Path | None:
    candidates = [
        dataset_root / "gcp_list.txt",
        dataset_root / "gcp.txt",
        dataset_root.parent / "gcp_list.txt",
        dataset_root.parent / "gcp.txt",
    ]
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


def inspect_scale_inputs(image_paths: list[Path], dataset_root: Path) -> ScaleEvidence:
    images_with_exif = 0
    images_with_gps = 0
    for image_path in image_paths:
        has_exif, has_gps = _image_exif_status(image_path)
        images_with_exif += int(has_exif)
        images_with_gps += int(has_gps)

    gcp_file = find_gcp_file(dataset_root)
    if gcp_file is not None:
        return ScaleEvidence(
            image_count=len(image_paths),
            images_with_exif=images_with_exif,
            images_with_gps=images_with_gps,
            gcp_path=str(gcp_file),
            scale_certified=True,
            reason="gcp_file_available",
        )
    if images_with_gps == len(image_paths) and image_paths:
        return ScaleEvidence(
            image_count=len(image_paths),
            images_with_exif=images_with_exif,
            images_with_gps=images_with_gps,
            gcp_path=None,
            scale_certified=True,
            reason="all_images_have_gps_exif",
        )
    return ScaleEvidence(
        image_count=len(image_paths),
        images_with_exif=images_with_exif,
        images_with_gps=images_with_gps,
        gcp_path=None,
        scale_certified=False,
        reason="missing_gcp_and_gps_exif",
    )
