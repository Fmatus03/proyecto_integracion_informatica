from __future__ import annotations

from io import BytesIO

import pytest
from fastapi import UploadFile
from PIL import Image

from backend.app.config import get_settings
from backend.app.services.image_validator import validate_uploads


def _png_bytes() -> bytes:
    buffer = BytesIO()
    image = Image.new("RGB", (8, 8), color=(0, 255, 0))
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _upload_file(index: int, content_type: str = "image/png", payload: bytes | None = None) -> UploadFile:
    return UploadFile(
        filename=f"image_{index}.png",
        file=BytesIO(payload or _png_bytes()),
        headers={"content-type": content_type},
    )


@pytest.mark.asyncio
async def test_validate_uploads_accepts_png_batch() -> None:
    files = [_upload_file(i) for i in range(10)]
    validated = await validate_uploads(files, get_settings())
    assert len(validated) == 10


@pytest.mark.asyncio
async def test_validate_uploads_rejects_invalid_mime() -> None:
    files = [_upload_file(i) for i in range(9)] + [_upload_file(10, content_type="application/octet-stream")]
    with pytest.raises(Exception) as exc_info:
        await validate_uploads(files, get_settings())
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["error_code"] == "INVALID_IMAGE_FORMAT"
