"""Upload route for the Hito 0 scaffold."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, UploadFile

from backend.app.config import Settings, get_settings
from backend.app.models.schemas import UploadResponse
from backend.app.services.image_validator import validate_uploads
from backend.app.services.session_store import SessionStore

router = APIRouter(prefix="/api", tags=["upload"])


@router.post("/upload", response_model=UploadResponse)
async def upload_images(
    files: list[UploadFile] = File(...),
    settings: Settings = Depends(get_settings),
) -> UploadResponse:
    validated = await validate_uploads(files, settings)
    store = SessionStore(settings)
    session = store.create_session([item.filename for item in validated])
    store.store_images(session["session_id"], [(item.filename, item.data) for item in validated])
    return UploadResponse(
        session_id=session["session_id"],
        image_count=session["image_count"],
        valid=True,
        errors=[],
        pipeline_state=session["pipeline_state"],
    )
