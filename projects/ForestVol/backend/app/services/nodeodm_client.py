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
from backend.app.services.gcp_service import nodeodm_safe_filename
from backend.app.services.scale_service import ScaleEvidence


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
            {"name": "feature-quality", "value": "ultra"},
            {"name": "pc-quality", "value": "high"},
            {"name": "min-num-features", "value": "16000"},
            {"name": "matcher-neighbors", "value": "12"},
            {"name": "depthmap-resolution", "value": "high"},
            {"name": "pc-filter", "value": "1"},
            # Hito 0.5 needs a dense cloud with enough texture detail before meshing.
            {"name": "end-with", "value": "odm_filterpoints"},
        ],
    ),
    AttemptConfig(
        name="attempt_2",
        options=[
            {"name": "feature-quality", "value": "high"},
            {"name": "pc-quality", "value": "high"},
            {"name": "min-num-features", "value": "12000"},
            {"name": "matcher-neighbors", "value": "10"},
            {"name": "depthmap-resolution", "value": "medium"},
            {"name": "pc-filter", "value": "1"},
            {"name": "end-with", "value": "odm_filterpoints"},
        ],
    ),
    AttemptConfig(
        name="attempt_3",
        options=[
            {"name": "feature-quality", "value": "medium"},
            {"name": "pc-quality", "value": "medium"},
            {"name": "min-num-features", "value": "9000"},
            {"name": "matcher-neighbors", "value": "8"},
            {"name": "depthmap-resolution", "value": "medium"},
            {"name": "pc-filter", "value": "2"},
            {"name": "end-with", "value": "odm_filterpoints"},
        ],
    ),
]


def options_for_attempt(attempt: AttemptConfig, scale_evidence: ScaleEvidence | None = None) -> list[dict[str, str]]:
    options = list(attempt.options)
    if scale_evidence is None:
        return options
    if scale_evidence.gcp_path:
        if scale_evidence.images_with_gps:
            options.append({"name": "force-gps", "value": "true"})
            options.append({"name": "use-exif", "value": "true"})
    elif scale_evidence.scale_certified and scale_evidence.images_with_gps == scale_evidence.image_count:
        options.append({"name": "force-gps", "value": "true"})
    return options


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

    def submit_task(
        self,
        session_id: str,
        images: list[Path],
        attempt: AttemptConfig,
        scale_evidence: ScaleEvidence | None = None,
    ) -> str:
        files = [
            ("images", (nodeodm_safe_filename(path.name), path.read_bytes(), self._guess_mime(path)))
            for path in images
        ]
        if scale_evidence is not None and scale_evidence.gcp_path:
            gcp_path = Path(scale_evidence.gcp_path)
            files.append(("images", (gcp_path.name, gcp_path.read_bytes(), "text/plain")))
        data = {
            "name": f"forestvol-{session_id}-{attempt.name}",
            "options": json.dumps(options_for_attempt(attempt, scale_evidence)),
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
