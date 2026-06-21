"""Shared validation helpers for harness runtime and agent response parsing."""
import re
from pathlib import Path


SAFE_REF_RE = re.compile(r"^[A-Za-z0-9_./+=-]+$")


def json_type_matches(value, expected_type: str) -> bool:
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


def validate_schema_node(value, schema: dict, label: str) -> None:
    expected_type = schema.get("type")
    if expected_type and not json_type_matches(value, expected_type):
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
                validate_schema_node(child, properties[key], f"{label}.{key}")

    if isinstance(value, list) and "items" in schema:
        for idx, item in enumerate(value):
            validate_schema_node(item, schema["items"], f"{label}[{idx}]")


def assert_safe_ref(value: str, label: str) -> None:
    if not isinstance(value, str) or not value:
        raise ValueError(f"guardrail_input_invalid:{label}:empty")
    if "\\" in value or not SAFE_REF_RE.match(value):
        raise ValueError(f"guardrail_input_invalid:{label}:unsafe_chars")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"guardrail_input_invalid:{label}:unsafe_path")


def assert_ref_list_safe(values: list, label: str) -> None:
    if not isinstance(values, list) or not values:
        raise ValueError(f"orchestrator_response_invalid:{label}")
    for idx, value in enumerate(values):
        assert_safe_ref(value, f"{label}[{idx}]")


def assert_terminal_confirmation(
    policy: dict,
    confirmation: str = "",
    confirmed_by: str = "",
    terminal_stage: str = "",
    terminal_stages: set = None,
) -> None:
    stage_suffix = f":{terminal_stage}" if terminal_stage else ""
    if terminal_stage and terminal_stage not in policy["required_stages"]:
        return
    if terminal_stage and terminal_stages is not None and terminal_stage not in terminal_stages:
        raise ValueError(f"terminal_confirmation_invalid_stage:{terminal_stage}")
    if not confirmation and not confirmed_by:
        raise ValueError(f"terminal_confirmation_required{stage_suffix}")
    if confirmation and not re.match(policy["token_pattern"], confirmation):
        raise ValueError(f"terminal_confirmation_invalid{stage_suffix}")
    if confirmed_by and confirmed_by not in policy["allowed_confirmed_by"]:
        raise ValueError(f"terminal_confirmed_by_invalid:{confirmed_by}")
