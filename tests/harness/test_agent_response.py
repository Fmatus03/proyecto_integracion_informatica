"""Tests for structured orchestrator response validation and CLI adaptation."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / ".harness"))
from agent_response import (  # noqa: E402
    orchestrator_response_to_cli_args,
    validate_orchestrator_response,
)
from validation import assert_safe_ref, validate_schema_node  # noqa: E402


def test_validate_orchestrator_response_accepts_advance_payload(temp_repo):
    payload = {
        "action": "advance",
        "run_id": "RUN-001",
        "stage": "PLAN_VALIDATION",
        "artifacts": ["spec.md"],
        "decision_basis": "spec.md is present and validated.",
    }

    validated = validate_orchestrator_response(payload, temp_repo)

    assert validated == payload


def test_validate_orchestrator_response_rejects_gate_pass_without_justification(temp_repo):
    payload = {
        "action": "gate",
        "run_id": "RUN-001",
        "gate_name": "analysis_gate",
        "value": "passed",
        "decision_basis": "analysis gate should pass",
        "evidence": ["evidence/analyze_report.json"],
    }

    with pytest.raises(ValueError, match="orchestrator_response_invalid:justification"):
        validate_orchestrator_response(payload, temp_repo)


def test_validate_orchestrator_response_rejects_complete_without_artifacts(temp_repo):
    payload = {
        "action": "complete",
        "run_id": "RUN-001",
        "decision_basis": "qa is ready",
        "confirmation": "USER-OK-2026",
    }

    with pytest.raises(ValueError, match="orchestrator_response_invalid:artifacts"):
        validate_orchestrator_response(payload, temp_repo)


def test_validate_orchestrator_response_rejects_invalid_confirmed_by(temp_repo):
    payload = {
        "action": "fail",
        "run_id": "RUN-001",
        "reason": "runtime_crash",
        "decision_basis": "runtime crashed during validation",
        "confirmed_by": "validator",
    }

    with pytest.raises(ValueError, match="terminal_confirmed_by_invalid"):
        validate_orchestrator_response(payload, temp_repo)


def test_validate_orchestrator_response_rejects_unexpected_field(temp_repo):
    payload = {
        "action": "claim",
        "run_id": "RUN-001",
        "claim_name": "dataset_contract",
        "decision_basis": "dataset evidence exists",
        "message": "extra chatter",
    }

    with pytest.raises(ValueError, match="schema_extra_field:orchestrator_response:message"):
        validate_orchestrator_response(payload, temp_repo)


def test_orchestrator_response_to_cli_args_matches_advance_shape(temp_repo):
    payload = {
        "action": "advance",
        "run_id": "RUN-001",
        "stage": "PLAN_VALIDATION",
        "artifacts": ["spec.md"],
        "evidence": ["evidence/spec_validation.json"],
        "decision_basis": "spec.md is present and is the only required exit artifact.",
    }

    args = orchestrator_response_to_cli_args(payload)

    assert args == [
        "advance",
        "RUN-001",
        "PLAN_VALIDATION",
        "--artifacts=spec.md",
        "--evidence=evidence/spec_validation.json",
        "--actor=orchestrator",
    ]


def test_orchestrator_response_to_cli_args_matches_complete_shape(temp_repo):
    payload = {
        "action": "complete",
        "run_id": "RUN-001",
        "artifacts": ["test-report.md", "final-report.md"],
        "confirmation": "USER-OK-2026",
        "confirmed_by": "user",
        "decision_basis": "QA artifacts are ready for runtime close validation.",
    }

    args = orchestrator_response_to_cli_args(payload)

    assert args == [
        "complete",
        "RUN-001",
        "--artifacts=test-report.md,final-report.md",
        "--confirmation=USER-OK-2026",
        "--confirmed-by=user",
        "--actor=orchestrator",
    ]


def test_shared_validation_helpers_keep_schema_and_path_guards_consistent():
    schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["artifact"],
        "properties": {"artifact": {"type": "string", "pattern": "^[A-Za-z0-9_.-]+$"}},
    }

    validate_schema_node({"artifact": "spec.md"}, schema, "sample")

    with pytest.raises(ValueError, match="schema_extra_field:sample:extra"):
        validate_schema_node({"artifact": "spec.md", "extra": True}, schema, "sample")

    with pytest.raises(ValueError, match="guardrail_input_invalid:artifact:unsafe_path"):
        assert_safe_ref("../secret.md", "artifact")
