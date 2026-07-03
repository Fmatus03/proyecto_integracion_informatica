from __future__ import annotations

import json
import time
from pathlib import Path

import requests


BASE_URL = "http://localhost:8000"
DATASET = Path("projects/ForestVol/set_imagenes+guia/set_fotos_castillo_de_madera_2")
OUT = Path(".harness/runs/RUN-POISSON-RECOVERY-01/e2e-poisson-recovery-result.json")


def main() -> None:
    image_paths = sorted(DATASET.glob("*.png"))
    with requests.Session() as session:
        files = [("files", (path.name, path.read_bytes(), "image/png")) for path in image_paths]
        upload = session.post(f"{BASE_URL}/api/upload", files=files, timeout=120)
        upload.raise_for_status()
        upload_payload = upload.json()
        session_id = upload_payload["session_id"]

        calibrate = session.post(f"{BASE_URL}/api/calibrate/{session_id}", json={}, timeout=120)
        calibrate.raise_for_status()

        reconstruct = session.post(f"{BASE_URL}/api/reconstruct/{session_id}", timeout=120)
        reconstruct.raise_for_status()

        result_payload = None
        started = time.time()
        for _ in range(240):
            result = session.get(f"{BASE_URL}/api/results/{session_id}", timeout=60)
            result.raise_for_status()
            result_payload = result.json()
            if result_payload["pipeline_state"] in {"COMPLETED", "FAILED"}:
                break
            time.sleep(10)

    payload = {
        "session_id": session_id,
        "elapsed_seconds": round(time.time() - started, 2),
        "upload": upload_payload,
        "calibration": calibrate.json(),
        "reconstruct": reconstruct.json(),
        "result": result_payload,
    }
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
