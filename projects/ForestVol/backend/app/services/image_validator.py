"""Upload validation for ForestVol Hito 0."""
from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from fastapi import HTTPException, UploadFile
from PIL import Image, UnidentifiedImageError

from backend.app.config import Settings

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png"}
ALLOWED_MIME_TYPES = {"image/jpeg", "image/png"}


@dataclass(frozen=True)
class ValidatedImage:
    filename: str
    content_type: str
    size_bytes: int
    data: bytes


def _raise(status_code: int, code: str, message: str) -> None:
    raise HTTPException(status_code=status_code, detail={"error_code": code, "message": message})


def _detect_mime(data: bytes) -> str:
    try:
        with Image.open(BytesIO(data)) as image:
            image.verify()
            format_name = (image.format or "").upper()
    except (UnidentifiedImageError, OSError) as exc:
        _raise(400, "INVALID_IMAGE_FORMAT", f"Invalid image payload: {exc}")

    if format_name == "JPEG":
        return "image/jpeg"
    if format_name == "PNG":
        return "image/png"
    _raise(400, "INVALID_IMAGE_FORMAT", f"Unsupported image format detected: {format_name}")


async def validate_uploads(files: list[UploadFile], settings: Settings) -> list[ValidatedImage]:
    image_count = len(files)
    if image_count < settings.min_images:
        _raise(400, "INSUFFICIENT_IMAGES", f"At least {settings.min_images} images are required")
    if image_count > settings.max_images:
        _raise(400, "TOO_MANY_IMAGES", f"At most {settings.max_images} images are allowed")

    validated: list[ValidatedImage] = []
    total_size = 0

    for file in files:
        extension = Path(file.filename or "").suffix.lower()
        if extension not in ALLOWED_EXTENSIONS:
            _raise(400, "INVALID_IMAGE_FORMAT", f"Unsupported extension for {file.filename}")
        if file.content_type not in ALLOWED_MIME_TYPES:
            _raise(400, "INVALID_IMAGE_FORMAT", f"Unsupported MIME type for {file.filename}")

        data = await file.read()
        size_bytes = len(data)
        if size_bytes > settings.max_image_size_bytes:
            _raise(413, "IMAGE_SIZE_EXCEEDED", f"{file.filename} exceeds {settings.max_image_size_mb} MB")

        detected_mime = _detect_mime(data)
        if detected_mime != file.content_type:
            _raise(400, "INVALID_IMAGE_FORMAT", f"MIME mismatch for {file.filename}")

        total_size += size_bytes
        if total_size > settings.max_session_size_bytes:
            _raise(413, "SESSION_SIZE_EXCEEDED", "Total session size exceeds configured limit")

        validated.append(
            ValidatedImage(
                filename=file.filename or "unnamed-image",
                content_type=file.content_type or detected_mime,
                size_bytes=size_bytes,
                data=data,
            )
        )

    return validated
