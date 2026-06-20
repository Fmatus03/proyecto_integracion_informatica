"""Filesystem session store for Hito 0."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from backend.app.config import Settings


class SessionStore:
    """Persist sessions in the project data directory."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._ensure_roots()

    def _ensure_roots(self) -> None:
        for root in (self.settings.upload_path, self.settings.processed_path, self.settings.export_path):
            root.mkdir(parents=True, exist_ok=True)

    def _session_file(self, session_id: str) -> Path:
        return self.settings.upload_path / session_id / "session.json"

    def create_session(self, filenames: list[str]) -> dict[str, Any]:
        session_id = str(uuid4())
        upload_dir = self.settings.upload_path / session_id
        processed_dir = self.settings.processed_path / session_id
        upload_dir.mkdir(parents=True, exist_ok=True)
        processed_dir.mkdir(parents=True, exist_ok=True)

        payload = {
            "session_id": session_id,
            "pipeline_state": "VALIDATED",
            "image_count": len(filenames),
            "filenames": filenames,
            "nodeodm_task_uuid": None,
            "progress_percentage": 0,
            "point_cloud_path": None,
            "mesh": None,
            "volume": None,
            "reconstruction_attempts": [],
            "error_code": None,
            "message": None,
        }
        self.save_session(session_id, payload)
        return payload

    def save_session(self, session_id: str, payload: dict[str, Any]) -> None:
        session_file = self._session_file(session_id)
        session_file.parent.mkdir(parents=True, exist_ok=True)
        tmp_file = session_file.with_name(f"{session_file.name}.tmp")
        tmp_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp_file.replace(session_file)

    def load_session(self, session_id: str) -> dict[str, Any] | None:
        session_file = self._session_file(session_id)
        if not session_file.exists():
            return None
        return json.loads(session_file.read_text(encoding="utf-8"))

    def store_images(self, session_id: str, images: list[tuple[str, bytes]]) -> list[Path]:
        upload_dir = self.settings.upload_path / session_id
        upload_dir.mkdir(parents=True, exist_ok=True)
        written_files: list[Path] = []
        for filename, data in images:
            destination = upload_dir / filename
            destination.write_bytes(data)
            written_files.append(destination)
        return written_files

    def processed_dir(self, session_id: str) -> Path:
        path = self.settings.processed_path / session_id
        path.mkdir(parents=True, exist_ok=True)
        return path
