from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import requests


API = "http://localhost:8000"
ALLOWED = {".png", ".jpg", ".jpeg"}


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")


def append_log(path: Path, message: str) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}\n")


def post_upload(images: list[Path]) -> dict:
    handles = []
    try:
        files = []
        for path in images:
            handle = path.open("rb")
            handles.append(handle)
            mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
            files.append(("files", (path.name, handle, mime)))
        response = requests.post(f"{API}/api/upload", files=files, timeout=120)
        response.raise_for_status()
        return response.json()
    finally:
        for handle in handles:
            handle.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--poll-seconds", type=int, default=20)
    args = parser.parse_args()

    dataset = Path(args.dataset)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    log = out / "api_runner.log"

    images = sorted(path for path in dataset.iterdir() if path.is_file() and path.suffix.lower() in ALLOWED)
    append_log(log, f"Dataset: {dataset}")
    append_log(log, f"Images: {len(images)}")
    write_json(out / "status.json", {"status": "starting", "dataset": str(dataset), "image_count": len(images)})

    upload = post_upload(images)
    write_json(out / "upload_response.json", upload)
    session_id = upload["session_id"]
    append_log(log, f"Uploaded session {session_id}")

    write_json(out / "status.json", {"status": "calibrating", "session_id": session_id, "image_count": len(images)})
    calibration_response = requests.post(f"{API}/api/calibrate/{session_id}", timeout=300)
    write_json(
        out / "calibration_response.json",
        {
            "status_code": calibration_response.status_code,
            "body": calibration_response.json() if calibration_response.content else None,
        },
    )
    calibration_response.raise_for_status()
    append_log(log, "Calibration completed")

    write_json(out / "status.json", {"status": "reconstructing", "session_id": session_id, "image_count": len(images)})
    reconstruction_response = requests.post(f"{API}/api/reconstruct/{session_id}", timeout=120)
    write_json(
        out / "reconstruct_response.json",
        {
            "status_code": reconstruction_response.status_code,
            "body": reconstruction_response.json() if reconstruction_response.content else None,
        },
    )
    reconstruction_response.raise_for_status()
    append_log(log, "Reconstruction submitted")

    while True:
        results_response = requests.get(f"{API}/api/results/{session_id}", timeout=60)
        results_response.raise_for_status()
        results = results_response.json()
        write_json(out / "latest_results.json", results)
        write_json(
            out / "status.json",
            {
                "status": results.get("pipeline_state"),
                "session_id": session_id,
                "image_count": len(images),
                "message": results.get("message"),
                "error_code": results.get("error_code"),
                "volume_m3": results.get("volume_m3"),
                "error_percentage": results.get("error_percentage"),
            },
        )
        append_log(
            log,
            "Poll "
            f"state={results.get('pipeline_state')} progress={results.get('progress_percentage')} "
            f"message={results.get('message')}",
        )
        if results.get("pipeline_state") in {"COMPLETED", "FAILED"}:
            write_json(out / "final_results.json", results)
            return 0 if results.get("pipeline_state") == "COMPLETED" else 2
        time.sleep(args.poll_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
