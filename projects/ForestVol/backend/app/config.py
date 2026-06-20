"""Environment-backed settings for the ForestVol backend."""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


def _int_env(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)))


def _float_env(name: str, default: float) -> float:
    return float(os.getenv(name, str(default)))


@dataclass(frozen=True)
class Settings:
    version: str
    backend_port: int
    nodeodm_url: str
    nodeodm_timeout_seconds: int
    nodeodm_data_path: Path
    min_images: int
    max_images: int
    max_image_size_mb: int
    max_session_size_gb: int
    upload_path: Path
    processed_path: Path
    export_path: Path
    calibration_confidence_threshold: float
    calibration_marker_size_cm: float

    @property
    def max_image_size_bytes(self) -> int:
        return self.max_image_size_mb * 1024 * 1024

    @property
    def max_session_size_bytes(self) -> int:
        return self.max_session_size_gb * 1024 * 1024 * 1024


def get_settings() -> Settings:
    return Settings(
        version=os.getenv("FORESTVOL_VERSION", "5.1"),
        backend_port=_int_env("BACKEND_PORT", 8000),
        nodeodm_url=os.getenv("NODEODM_URL", "http://nodeodm:3000").rstrip("/"),
        nodeodm_timeout_seconds=_int_env("NODEODM_TIMEOUT_SECONDS", 1800),
        nodeodm_data_path=Path(os.getenv("NODEODM_DATA_PATH", "/nodeodm-data")),
        min_images=_int_env("MIN_IMAGES", 10),
        max_images=_int_env("MAX_IMAGES", 50),
        max_image_size_mb=_int_env("MAX_IMAGE_SIZE_MB", 20),
        max_session_size_gb=_int_env("MAX_SESSION_SIZE_GB", 1),
        upload_path=Path(os.getenv("UPLOAD_PATH", "data/uploads")),
        processed_path=Path(os.getenv("PROCESSED_PATH", "data/processed")),
        export_path=Path(os.getenv("EXPORT_PATH", "data/exports")),
        calibration_confidence_threshold=_float_env("CALIBRATION_CONFIDENCE_THRESHOLD", 0.90),
        calibration_marker_size_cm=_float_env("CALIBRATION_MARKER_SIZE_CM", 100.0),
    )
