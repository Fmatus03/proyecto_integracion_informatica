"""Validation and CLI adaptation for structured orchestrator responses."""
import json
import re
from pathlib import Path


SAFE_REF_RE = re.compile(r"^[A-Za-z0-9_./+=-]+$")
RUN_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")
TERMINAL_ACTIONS = {"fail", "not-answerable", "complete"}

BASE_FIELDS = {"action", "run_id", "decision_basis", "blocking_condition"}
ACTION_ALLOWED_FIELDS = {
    "advance": BASE_FIELDS | {"stage", "artifacts", "evidence"},
    "gate": BASE_FIELDS | {"gate_name", "value", "justification", "evidence"},
    "claim": BASE_FIELDS | {"claim_name", "evidence"},
    "block": BASE_FIELDS | {"reason", "evidence"},
    "input": BASE_FIELDS | {"reason", "evidence"},
    "fail": BASE_FIELDS | {"reason", "evidence", "confirmation", "confirmed_by"},
    "not-answerable": BASE_FIELDS | {"reason", "evidence", "confirmation", "confirmed_by"},
    "complete": BASE_FIELDS | {"artifacts", "evidence", "confirmation", "confirmed_by"},
}


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _json_type_matches(value, expected_type: str) -> bool:
    if expected_type == "object":
        return isinstance(value, dict)
    if expected_type == "array":
        return isinstance(value, list)
    if expected_type == "string":
        return isinstance(value, str)
    if expected_type == "boolean":
        return isinstance(value, bool)
    if expected_type == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected_type == "null":
        return value is None
    return True


def _validate_schema_node(value, schema: dict, label: str) -> None:
    expected_type = schema.get("type")
    if expected_type and not _json_type_matches(value, expected_type):
        raise ValueError(f"schema_invalid_type:{label}:{expected_type}")

    if "enum" in schema and value not in schema["enum"]:
        raise ValueError(f"schema_invalid_enum:{label}:{value}")

    if "pattern" in schema and isinstance(value, str):
        if not re.match(schema["pattern"], value):
            raise ValueError(f"schema_invalid_pattern:{label}")

    if isinstance(value, dict):
        required = schema.get("required", [])
        for field in required:
            if field not in value:
                raise ValueError(f"schema_missing_field:{label}:{field}")
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            extra = set(value) - set(properties)
            if extra:
                raise ValueError(f"schema_extra_field:{label}:{sorted(extra)[0]}")
        for key, child in value.items():
            if key in properties:
                _validate_schema_node(child, properties[key], f"{label}.{key}")

    if isinstance(value, list) and "items" in schema:
        for idx, item in enumerate(value):
            _validate_schema_node(item, schema["items"], f"{label}[{idx}]")


def load_orchestrator_schema(root_dir=None) -> dict:
    root = Path(root_dir or ".").resolve()
    return _read_json(root / "projects" / "ForestVol" / "harness" / "orchestrator_response.schema.json")


def _load_runtime_contract(root_dir=None) -> dict:
    root = Path(root_dir or ".").resolve()
    return _read_json(root / ".harness" / "runtime_contract.json")


def _load_claim_policy(root_dir=None) -> dict:
    root = Path(root_dir or ".").resolve()
    runtime_contract = _load_runtime_contract(root)
    claim_path = runtime_contract["project_profile"]["claim_policy"]
    return _read_json(root / claim_path)


def _load_prompt_contract(root_dir=None) -> dict:
    root = Path(root_dir or ".").resolve()
    runtime_contract = _load_runtime_contract(root)
    prompt_path = runtime_contract["project_profile"]["prompt_contract"]
    return _read_json(root / prompt_path)


def _assert_non_empty_string(value: str, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"orchestrator_response_invalid:{label}")


def _assert_safe_ref(value: str, label: str) -> None:
    if not isinstance(value, str) or not value:
        raise ValueError(f"guardrail_input_invalid:{label}:empty")
    if "\\" in value or not SAFE_REF_RE.match(value):
        raise ValueError(f"guardrail_input_invalid:{label}:unsafe_chars")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"guardrail_input_invalid:{label}:unsafe_path")


def _assert_ref_list(values: list, label: str) -> None:
    if not isinstance(values, list) or not values:
        raise ValueError(f"orchestrator_response_invalid:{label}")
    for idx, value in enumerate(values):
        _assert_safe_ref(value, f"{label}[{idx}]")


def _assert_terminal_confirmation(payload: dict, root_dir=None) -> None:
    prompt_contract = _load_prompt_contract(root_dir)
    policy = prompt_contract["terminal_confirmation"]
    confirmation = payload.get("confirmation", "")
    confirmed_by = payload.get("confirmed_by", "")
    if not confirmation and not confirmed_by:
        raise ValueError("terminal_confirmation_required")
    if confirmation and not re.match(policy["token_pattern"], confirmation):
        raise ValueError("terminal_confirmation_invalid")
    if confirmed_by and confirmed_by not in policy["allowed_confirmed_by"]:
        raise ValueError("terminal_confirmed_by_invalid")


def _validate_advance(payload: dict, root_dir=None) -> None:
    runtime_contract = _load_runtime_contract(root_dir)
    _assert_non_empty_string(payload.get("stage", ""), "stage")
    terminal_stages = set(runtime_contract["terminal_stages"])
    if payload["stage"] in terminal_stages:
        raise ValueError(f"orchestrator_response_invalid:stage:{payload['stage']}")
    if payload["stage"] not in set(runtime_contract["stages"]):
        raise ValueError(f"orchestrator_response_invalid:stage:{payload['stage']}")
    if "artifacts" in payload:
        _assert_ref_list(payload["artifacts"], "artifacts")
    if "evidence" in payload:
        _assert_ref_list(payload["evidence"], "evidence")


def _validate_gate(payload: dict, root_dir=None) -> None:
    runtime_contract = _load_runtime_contract(root_dir)
    _assert_non_empty_string(payload.get("gate_name", ""), "gate_name")
    if payload["gate_name"] not in set(runtime_contract["gates"]):
        raise ValueError(f"orchestrator_response_invalid:gate_name:{payload['gate_name']}")
    _assert_non_empty_string(payload.get("value", ""), "value")
    if payload["value"] not in set(runtime_contract["allowed_gate_values"]):
        raise ValueError(f"orchestrator_response_invalid:value:{payload['value']}")
    if payload["value"] == "passed":
        _assert_non_empty_string(payload.get("justification", ""), "justification")
        _assert_ref_list(payload.get("evidence", []), "evidence")
    elif "evidence" in payload:
        _assert_ref_list(payload["evidence"], "evidence")


def _validate_claim(payload: dict, root_dir=None) -> None:
    claim_policy = _load_claim_policy(root_dir)
    _assert_non_empty_string(payload.get("claim_name", ""), "claim_name")
    if payload["claim_name"] not in set(claim_policy["claims"]):
        raise ValueError(f"orchestrator_response_invalid:claim_name:{payload['claim_name']}")
    if "evidence" in payload:
        _assert_ref_list(payload["evidence"], "evidence")


def _validate_terminal_reason(payload: dict, root_dir=None) -> None:
    _assert_non_empty_string(payload.get("reason", ""), "reason")
    if "evidence" in payload:
        _assert_ref_list(payload["evidence"], "evidence")
    if payload["action"] in {"fail", "not-answerable"}:
        _assert_terminal_confirmation(payload, root_dir)


def _validate_complete(payload: dict, root_dir=None) -> None:
    _assert_ref_list(payload.get("artifacts", []), "artifacts")
    if "evidence" in payload:
        _assert_ref_list(payload["evidence"], "evidence")
    _assert_terminal_confirmation(payload, root_dir)


def validate_orchestrator_response(payload, root_dir=None) -> dict:
    schema = load_orchestrator_schema(root_dir)
    if schema.get("strict") is not True:
        raise ValueError("schema_not_strict:orchestrator_response")
    _validate_schema_node(payload, schema, "orchestrator_response")

    _assert_non_empty_string(payload.get("run_id", ""), "run_id")
    if not RUN_ID_RE.match(payload["run_id"]):
        raise ValueError("invalid_run_id_format")
    _assert_non_empty_string(payload.get("decision_basis", ""), "decision_basis")
    if "blocking_condition" in payload:
        _assert_non_empty_string(payload["blocking_condition"], "blocking_condition")

    action = payload["action"]
    unexpected = set(payload) - ACTION_ALLOWED_FIELDS[action]
    if unexpected:
        raise ValueError(f"orchestrator_response_unexpected_field:{sorted(unexpected)[0]}")

    if action == "advance":
        _validate_advance(payload, root_dir)
    elif action == "gate":
        _validate_gate(payload, root_dir)
    elif action == "claim":
        _validate_claim(payload, root_dir)
    elif action in {"block", "input", "fail", "not-answerable"}:
        _validate_terminal_reason(payload, root_dir)
    elif action == "complete":
        _validate_complete(payload, root_dir)

    return payload


def _join_csv(values: list) -> str:
    return ",".join(values)


def orchestrator_response_to_cli_args(payload: dict) -> list:
    validated = validate_orchestrator_response(payload)
    action = validated["action"]
    args = [action, validated["run_id"]]

    if action == "advance":
        args.append(validated["stage"])
        if validated.get("artifacts"):
            args.append("--artifacts=" + _join_csv(validated["artifacts"]))
        if validated.get("evidence"):
            args.append("--evidence=" + _join_csv(validated["evidence"]))
    elif action == "gate":
        args.extend([validated["gate_name"], validated["value"]])
        if validated.get("justification"):
            args.append("--justification=" + validated["justification"])
        if validated.get("evidence"):
            args.append("--evidence=" + _join_csv(validated["evidence"]))
    elif action == "claim":
        args.append(validated["claim_name"])
        if validated.get("evidence"):
            args.append("--evidence=" + _join_csv(validated["evidence"]))
    elif action in {"block", "input", "fail", "not-answerable"}:
        args.append(validated["reason"])
        if validated.get("evidence"):
            args.append("--evidence=" + _join_csv(validated["evidence"]))
        if validated.get("confirmation"):
            args.append("--confirmation=" + validated["confirmation"])
        if validated.get("confirmed_by"):
            args.append("--confirmed-by=" + validated["confirmed_by"])
    elif action == "complete":
        args.append("--artifacts=" + _join_csv(validated["artifacts"]))
        if validated.get("evidence"):
            args.append("--evidence=" + _join_csv(validated["evidence"]))
        if validated.get("confirmation"):
            args.append("--confirmation=" + validated["confirmation"])
        if validated.get("confirmed_by"):
            args.append("--confirmed-by=" + validated["confirmed_by"])

    args.append("--actor=orchestrator")
    return args
