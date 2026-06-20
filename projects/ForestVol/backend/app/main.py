"""ForestVol FastAPI application."""
from __future__ import annotations

from fastapi import Depends, FastAPI, HTTPException

from backend.app.api.routes.calibration import router as calibration_router
from backend.app.api.routes.reconstruction import router as reconstruction_router
from backend.app.api.routes.upload import router as upload_router
from backend.app.config import Settings, get_settings
from backend.app.models.schemas import HealthResponse
from backend.app.services.nodeodm_client import NodeODMClient

app = FastAPI(title="ForestVol Backend", version="5.1")
app.include_router(upload_router)
app.include_router(calibration_router)
app.include_router(reconstruction_router)


@app.get("/health", response_model=HealthResponse)
def health(settings: Settings = Depends(get_settings)) -> HealthResponse:
    client = NodeODMClient(settings)
    reachable = client.is_reachable()
    if not reachable:
        raise HTTPException(
            status_code=503,
            detail={
                "error_code": "DEPENDENCY_UNAVAILABLE",
                "message": "NodeODM service is not reachable at configured host",
            },
        )
    return HealthResponse(status="ok", version=settings.version, nodeodm_reachable=True)
