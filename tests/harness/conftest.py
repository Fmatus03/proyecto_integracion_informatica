"""Fixtures compartidos para los tests del harness."""
import json
import shutil
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parents[2]


@pytest.fixture()
def temp_repo(tmp_path):
    """Replica mínima del repo requerida por el runtime del harness."""
    # Archivos del harness
    harness_src = REPO_ROOT / ".harness"
    harness_dst = tmp_path / ".harness"
    harness_dst.mkdir()
    for fname in (
        "runtime_contract.json",
        "state_machine.json",
        "claim_policy.json",
        "artifact_policy.json",
        "evidence_policy.json",
        "role_policy.json",
        "injection_policy.json",
        "eval_contract.json",
        "runtime.py",
        "cli.py",
        "eval_runner.py",
        "agent_response.py",
        "validation.py",
        "tokenization.py",
        "prompt_validation.py",
    ):
        shutil.copy(harness_src / fname, harness_dst / fname)
    shutil.copytree(harness_src / "schemas", harness_dst / "schemas")
    shutil.copytree(REPO_ROOT / ".agents", tmp_path / ".agents")

    shutil.copytree(REPO_ROOT / "evals", tmp_path / "evals")

    # canonical_doc requerido por authority_gate
    shutil.copy(
        REPO_ROOT / "FV_05_Enmienda_Harness_2026_06_12.md",
        tmp_path / "FV_05_Enmienda_Harness_2026_06_12.md",
    )
    shutil.copytree(
        REPO_ROOT / "projects",
        tmp_path / "projects",
        ignore=shutil.ignore_patterns("data", "__pycache__"),
    )

    # Dataset oficial del proyecto activo
    dataset_src_root = REPO_ROOT / "projects" / "ForestVol" / "set_imagenes+guia"
    dataset_dst_root = tmp_path / "projects" / "ForestVol" / "set_imagenes+guia"
    dataset_dst_root.mkdir(parents=True, exist_ok=True)
    manifest_path = dataset_dst_root / "dataset_manifest.json"
    shutil.copy(dataset_src_root / "dataset_manifest.json", manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    fotos_dir = tmp_path / manifest["dataset_root"]
    fotos_dir.mkdir(parents=True, exist_ok=True)
    for i in range(10):
        (fotos_dir / f"img-{i}.png").write_bytes(b"x")

    marker_path = tmp_path / manifest["reference_marker"]["marker_image_path"]
    marker_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(REPO_ROOT / manifest["reference_marker"]["marker_image_path"], marker_path)

    return tmp_path
