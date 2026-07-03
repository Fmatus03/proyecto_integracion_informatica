from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
FORESTVOL_ROOT = ROOT / "projects" / "ForestVol"
BACKEND = FORESTVOL_ROOT / "backend"
if not BACKEND.exists():
    FORESTVOL_ROOT = Path("/app")
    BACKEND = FORESTVOL_ROOT / "backend"
if str(BACKEND.parent) not in sys.path:
    sys.path.insert(0, str(BACKEND.parent))

from backend.app.config import Settings, get_settings  # noqa: E402
from backend.app.services.cloud_provider import load_pipeline_point_cloud  # noqa: E402


PRODUCTION_SESSIONS = {
    "set1": "b3c14c84-b660-407f-817f-1fc185ce3e9c",
    "set2": "723f91e2-b1b5-43f7-b336-6816d8300509",
}


def cloud_provider_settings() -> Settings:
    settings = get_settings()
    if settings.processed_path.exists() and settings.upload_path.exists():
        return settings
    return Settings(
        version=settings.version,
        backend_port=settings.backend_port,
        nodeodm_url=settings.nodeodm_url,
        nodeodm_timeout_seconds=settings.nodeodm_timeout_seconds,
        nodeodm_data_path=settings.nodeodm_data_path,
        min_images=settings.min_images,
        max_images=settings.max_images,
        max_image_size_mb=settings.max_image_size_mb,
        max_session_size_gb=settings.max_session_size_gb,
        upload_path=FORESTVOL_ROOT / "data" / "uploads",
        processed_path=FORESTVOL_ROOT / "data" / "processed",
        export_path=FORESTVOL_ROOT / "data" / "exports",
        calibration_confidence_threshold=settings.calibration_confidence_threshold,
        calibration_marker_size_cm=settings.calibration_marker_size_cm,
    )


def load_dataset_cloud_source(dataset: str) -> Any:
    return load_pipeline_point_cloud(PRODUCTION_SESSIONS[dataset], cloud_provider_settings())
