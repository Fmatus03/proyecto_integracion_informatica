"""NodeODM integration used by the Hito 0 technical validation."""
from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import json
from pathlib import Path
import time
from zipfile import ZipFile

import requests

from backend.app.config import Settings


STATUS_QUEUED = 10
STATUS_RUNNING = 20
STATUS_FAILED = 30
STATUS_COMPLETED = 40


@dataclass(frozen=True)
class AttemptConfig:
    name: str
    options: list[dict[str, str]]


ATTEMPTS = [
    AttemptConfig(
        name="attempt_1",
        options=[
            {"name": "feature-quality", "value": "high"},
            {"name": "pc-quality", "value": "medium"},
            {"name": "min-num-features", "value": "8000"},
            # Hito 0 closes when the first dense point cloud exists in data/processed.
            {"name": "end-with", "value": "odm_filterpoints"},
        ],
    ),
    AttemptConfig(
        name="attempt_2",
        options=[
            {"name": "feature-quality", "value": "medium"},
            {"name": "pc-quality", "value": "low"},
            {"name": "min-num-features", "value": "4000"},
            {"name": "end-with", "value": "odm_filterpoints"},
        ],
    ),
    AttemptConfig(
        name="attempt_3",
        options=[
            {"name": "feature-quality", "value": "low"},
            {"name": "pc-quality", "value": "low"},
            {"name": "min-num-features", "value": "2000"},
            {"name": "end-with", "value": "odm_filterpoints"},
        ],
    ),
]


class NodeODMClient:
    """Thin REST client backed by the official NodeODM endpoints."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.timeout = 30

    def is_reachable(self) -> bool:
        try:
            response = requests.get(f"{self.settings.nodeodm_url}/info", timeout=self.timeout)
            response.raise_for_status()
            return True
        except requests.RequestException:
            return False

    def submit_task(self, session_id: str, images: list[Path], attempt: AttemptConfig) -> str:
        files = [
            ("images", (path.name, path.read_bytes(), self._guess_mime(path)))
            for path in images
        ]
        data = {
            "name": f"forestvol-{session_id}-{attempt.name}",
            "options": json.dumps(attempt.options),
        }
        response = requests.post(
            f"{self.settings.nodeodm_url}/task/new",
            data=data,
            files=files,
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        return payload["uuid"]

    def poll_task(self, task_uuid: str) -> dict[str, object]:
        started = time.time()
        while True:
            response = requests.get(
                f"{self.settings.nodeodm_url}/task/{task_uuid}/info",
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.json()
            status_code = int(payload["status"]["code"])
            if status_code in {STATUS_COMPLETED, STATUS_FAILED}:
                return payload
            if time.time() - started > self.settings.nodeodm_timeout_seconds:
                raise TimeoutError(f"NodeODM task {task_uuid} timed out")
            time.sleep(10)

    def download_first_ply(self, task_uuid: str, destination_dir: Path) -> Path:
        response = requests.get(
            f"{self.settings.nodeodm_url}/task/{task_uuid}/download/all.zip",
            timeout=self.timeout,
        )
        response.raise_for_status()
        with ZipFile(BytesIO(response.content)) as archive:
            for member in archive.namelist():
                if member.lower().endswith(".ply"):
                    target_path = destination_dir / Path(member).name
                    target_path.write_bytes(archive.read(member))
                    return target_path
        shared_point_cloud = (
            self.settings.nodeodm_data_path / task_uuid / "odm_filterpoints" / "point_cloud.ply"
        )
        if shared_point_cloud.exists():
            target_path = destination_dir / shared_point_cloud.name
            target_path.write_bytes(shared_point_cloud.read_bytes())
            return target_path
        raise FileNotFoundError("NodeODM completed without producing a .ply artifact")

    @staticmethod
    def _guess_mime(path: Path) -> str:
        suffix = path.suffix.lower()
        return "image/png" if suffix == ".png" else "image/jpeg"
