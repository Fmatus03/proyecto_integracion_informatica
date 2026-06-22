"""Pydantic request and response schemas for ForestVol."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str
    version: str
    nodeodm_reachable: bool


class UploadResponse(BaseModel):
    session_id: str
    image_count: int
    valid: bool
    errors: list[str]
    pipeline_state: str


class ReconstructionResponse(BaseModel):
    session_id: str
    pipeline_state: str
    message: str


class CalibrationRequest(BaseModel):
    manual_scale_px_per_cm: float | None = Field(default=None, gt=0)
    visible_image_names: list[str] | None = None


class CalibrationResponse(BaseModel):
    session_id: str
    calibration_mode: str
    guide_detected_in_n_images: int
    detection_confidence: float
    scale_px_per_cm: float
    scale_error_percentage: float | None
    pipeline_state: str
    warning: str | None = None


class ResultResponse(BaseModel):
    session_id: str
    pipeline_state: str
    progress_percentage: int | None = None
    point_cloud_path: str | None = None
    mesh_ply_path: str | None = None
    mesh_glb_path: str | None = None
    mesh_watertight: bool | None = None
    mesh_repair_applied: bool | None = None
    volume_m3: float | None = None
    bounding_box_m: dict[str, float] | None = None
    ground_truth_volume_m3: float | None = None
    error_percentage: float | None = None
    reconstruction_attempts: list[dict[str, Any]] = Field(default_factory=list)
    scale_evidence: dict[str, Any] | None = None
    error_code: str | None = None
    message: str | None = None


class ErrorResponse(BaseModel):
    error_code: str
    message: str
