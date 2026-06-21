"""Prompt contract file validation and token budget enforcement."""
import re
import unicodedata
from pathlib import Path

from tokenization import count_prompt_files


PROMPT_PLACEHOLDER_PATTERNS = ("placeholder", "todo", "tbd", "lorem ipsum")


def _ascii_fold(content: str) -> str:
    decomposed = unicodedata.normalize("NFKD", unicodedata.normalize("NFKC", content))
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch)).lower()


def _assert_no_reserved_markers(content: str, label: str, reserved_markers: list) -> None:
    for marker in reserved_markers:
        if marker in content:
            raise ValueError(f"prompt_invalid:reserved_marker:{label}:{marker}")


def _validate_context_file(path: Path, label: str) -> None:
    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"prompt_invalid:encoding:{label}") from exc
    if not content.strip():
        raise ValueError(f"prompt_invalid:empty:{label}")


def _assert_prompt_not_duplicate_canonical(
    content: str,
    canonical_content: str,
    label: str,
) -> None:
    canonical_lines = {
        line.strip() for line in canonical_content.splitlines()
        if len(line.strip()) >= 32
    }
    duplicated = 0
    for line in content.splitlines():
        stripped = line.strip()
        if stripped in canonical_lines:
            duplicated += 1
    if duplicated >= 8:
        raise ValueError(f"prompt_invalid:duplicated_authority:{label}")


def _validate_prompt_file(
    path: Path,
    label: str,
    canonical_content: str,
    required_sections: list = None,
    required_markers: list = None,
) -> None:
    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"prompt_invalid:encoding:{label}") from exc
    if not content.strip():
        raise ValueError(f"prompt_invalid:empty:{label}")
    folded = _ascii_fold(content)
    for pattern in PROMPT_PLACEHOLDER_PATTERNS:
        if pattern in folded:
            raise ValueError(f"prompt_invalid:placeholder:{label}:{pattern}")
    if (
        "FV_05_Enmienda_Harness_2026_06_12.md" not in content
        and label not in ("bootstrap_prompt", "project_context")
    ):
        raise ValueError(f"prompt_invalid:missing_authority_reference:{label}")
    for marker in required_markers or []:
        if marker not in content:
            raise ValueError(f"prompt_invalid:missing_marker:{label}:{marker}")
    for heading in required_sections or []:
        if heading.lower() not in content.lower():
            raise ValueError(f"prompt_invalid:missing_section:{label}:{heading}")
    _assert_prompt_not_duplicate_canonical(content, canonical_content, label)


def _prompt_token_paths(root_dir: Path, prompt_contract: dict) -> dict:
    paths = {
        "bootstrap_prompt": root_dir / prompt_contract["bootstrap_prompt"],
        "eval_prompt": root_dir / prompt_contract["eval_prompt"],
    }
    for role, rel_path in prompt_contract["role_prompts"].items():
        paths[f"role_prompt:{role}"] = root_dir / rel_path
    return paths


def _enforce_token_budget(root_dir: Path, prompt_contract: dict) -> dict:
    budget = prompt_contract["token_budget"]
    model = budget["model"]
    counts = count_prompt_files(_prompt_token_paths(root_dir, prompt_contract), model)
    max_single = budget["max_single_prompt_tokens"]
    max_static = budget["max_static_prompt_tokens"]
    for label, count in counts.items():
        if count > max_single:
            raise ValueError(f"prompt_token_budget_exceeded:{label}:{count}>{max_single}")
    total = sum(counts.values())
    if total > max_static:
        raise ValueError(f"prompt_token_budget_exceeded:static_prompt_tokens:{total}>{max_static}")
    return {"model": model, "total": total, "files": counts}


def validate_prompt_contract_files(
    root_dir: Path,
    runtime_contract: dict,
    prompt_contract: dict,
    canonical_content: str,
) -> dict:
    bootstrap_prompt = root_dir / runtime_contract["bootstrap_prompt"]
    project_context = root_dir / prompt_contract["project_context"]
    eval_prompt = root_dir / prompt_contract["eval_prompt"]

    _validate_prompt_file(
        bootstrap_prompt,
        "bootstrap_prompt",
        canonical_content,
        required_sections=[
            "## Identity",
            "## Authority",
            "## Trusted Sources",
            "## Untrusted Context",
            "## Runtime-Only Decisions",
            "## Output Contract",
            "## Failure Modes",
        ],
        required_markers=prompt_contract["required_markers"],
    )
    _validate_prompt_file(
        eval_prompt,
        "eval_prompt",
        canonical_content,
        required_markers=prompt_contract["required_markers"],
    )
    _validate_context_file(project_context, "project_context")
    _assert_no_reserved_markers(
        project_context.read_text(encoding="utf-8"),
        "project_context",
        prompt_contract["required_markers"],
    )

    for role, rel_path in prompt_contract["role_prompts"].items():
        role_prompt = root_dir / rel_path
        if not role_prompt.exists():
            raise FileNotFoundError(f"authority_gate_failed:role_prompt_missing:{role}")
        _validate_prompt_file(
            role_prompt,
            f"role_prompt:{role}",
            canonical_content,
            required_sections=[
                f"## {section}"
                for section in prompt_contract["output_contracts"][role]["required_sections"]
            ],
        )
        _assert_no_reserved_markers(
            role_prompt.read_text(encoding="utf-8"),
            f"role_prompt:{role}",
            prompt_contract["required_markers"],
        )

    return _enforce_token_budget(root_dir, prompt_contract)
