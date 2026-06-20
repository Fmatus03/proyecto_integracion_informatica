from __future__ import annotations

import pytest
from fastapi import HTTPException

from backend.app.config import get_settings
from backend.app.main import health
from backend.app.services.nodeodm_client import NodeODMClient


def test_health_returns_503_when_nodeodm_unreachable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(NodeODMClient, "is_reachable", lambda self: False)
    with pytest.raises(HTTPException) as exc_info:
        health(get_settings())
    assert exc_info.value.status_code == 503
    assert exc_info.value.detail["error_code"] == "DEPENDENCY_UNAVAILABLE"
