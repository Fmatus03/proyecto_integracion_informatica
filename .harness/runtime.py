"""Reusable project harness runtime for Python 3.11."""
import json
import re
import hashlib
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from validation import (
    assert_safe_ref,
    assert_terminal_confirmation,
    validate_schema_node,
)
from prompt_validation import validate_prompt_contract_files

MODULE_DIR = Path(__file__).parent
DEFAULT_ROOT = MODULE_DIR.parent

TERMINAL_STATUS_BY_STAGE = {
    "CLOSE": "complete",
    "BLOCKED": "blocked",
    "ERROR": "error",
    "NEEDS_USER_INPUT": "needs_user_input",
    "NOT_ANSWERABLE": "not_answerable",
}

ALLOWED_GATE_VALUES = {"pending", "passed", "failed"}
LESSON_SEVERITIES = {"low", "medium", "high", "critical"}
REQUIRED_LESSON_FIELDS = {
    "lesson_id",
    "run_id",
    "stage",
    "context",
    "attempted_action",
    "outcome",
    "failure_reason",
    "do_not_repeat",
    "recommended_action",
    "applies_when",
    "severity",
    "source",
    "timestamp",
}

GATE_EVIDENCE_CLAIMS = {
    "dataset_gate": {"dataset_manifest", "dataset_images", "marker_image_file"},
    "authority_gate": {"runtime_contract", "harness_contract", "eval_contract"},
    "analysis_gate": {"analyze_report", "analysis_report"},
    "claim_gate": {
        "dataset_manifest",
        "dataset_images",
        "marker_image_file",
        "valid_mesh",
        "ground_truth_certified",
        "error_percentage",
        "rf09_compliance",
    },
    "test_gate": {"test_report", "test_runner"},
    "traceability_gate": {"traceability", "audit_chain"},
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _unique(items: list) -> list:
    seen: set = set()
    result = []
    for item in items or []:
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _read_json(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: Path, payload) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
        f.write("\n")


def _ensure_file(path: Path) -> None:
    path = Path(path)
    if not path.exists():
        path.touch()


def _append_jsonl(path: Path, payload: dict) -> None:
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(payload) + "\n")


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _canonical_json(payload) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")




LEETSPEAK_TRANSLATION = str.maketrans({
    "0": "o",
    "1": "i",
    "3": "e",
    "4": "a",
    "5": "s",
    "7": "t",
    "@": "a",
    "$": "s",
})


def _ascii_fold(content: str) -> str:
    normalized = unicodedata.normalize("NFKC", content).translate(LEETSPEAK_TRANSLATION)
    decomposed = unicodedata.normalize("NFKD", normalized)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch)).lower()


def _normalized_text(content: str) -> str:
    return re.sub(r"\s+", " ", _ascii_fold(content)).strip()


def _compact_text(content: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", _ascii_fold(content)).strip()


def _joined_text(content: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", _ascii_fold(content))


def _policy_term_matches(term: str, normalized: str, joined: str) -> bool:
    compact_term = _compact_text(term)
    joined_term = _joined_text(term)
    if compact_term and re.search(rf"(^| ){re.escape(compact_term)}( |$)", normalized):
        return True
    return len(joined_term) >= 5 and joined_term in joined


SEMANTIC_CONCEPT_GROUPS = {
    "rgb": ["rgb", "imagenes rgb", "entradas rgb"],
    "aruco": ["aruco", "marcador", "referencia"],
    "metadata_free": ["sin metadata", "sin metadatos", "exif", "gps"],
    "ground_truth": ["ground truth", "rf-09", "error"],
    "dataset_manifest": ["dataset manifest", "dataset_manifest", "manifest"],
    "evidence": ["evidencia", "checksum", "validator"],
    "runtime": ["runtime", "cli"],
    "mesh_volume": ["malla", "mesh", "volumen"],
    "claims": ["claim", "claims", "claim_gate"],
    "traceability": ["trazabilidad", "audit", "integridad"],
}


# ── Hook System ──────────────────────────────────────────────────────────────
#
# Hooks are opt-in lifecycle callbacks that fire at well-defined points without
# ever blocking harness operations. Errors inside a hook are logged to stderr
# but never propagate — the harness is always the authority.
#
# Available hooks (all optional, registered via HarnessHooks.register):
#
#   on_before_advance(run_id, current_stage, next_stage, artifacts, actor)
#       → Called BEFORE a stage transition is committed. Use for pre-flight
#         checks, notifications, or external guardrails. Raise ValueError to
#         HARD-BLOCK the advance (the only hook that can veto an operation).
#
#   on_run_init(run_id, state)
#       → Fired after a run is fully initialised and state.json written.
#         Use for external registration, alerting, or dashboard push.
#
#   on_stage_advance(run_id, from_stage, to_stage, artifacts, actor, state)
#       → Fired after a successful stage transition. Use for notifications,
#         CI triggers, or external state sync.
#
#   on_gate_set(run_id, gate_name, value, actor, justification, state)
#       → Fired after a gate value is committed. Use for telemetry or
#         external audit systems.
#
#   on_claim_evaluated(run_id, claim_name, outcome, evidence, state)
#       → Fired after a claim is accepted or blocked. Use for dashboards
#         or compliance reporting.
#
#   on_lesson_recorded(run_id, lesson, state)
#       → Fired after a lesson is persisted locally and globally.
#         Use for knowledge-base integrations or alerting on high-severity
#         lessons.
#
#   on_run_terminal(run_id, terminal_stage, reason, state)
#       → Fired when a run reaches any terminal stage (CLOSE, BLOCKED,
#         ERROR, NEEDS_USER_INPUT, NOT_ANSWERABLE). Use for cleanup,
#         final notifications, or external resource release.
#
#   on_test_pass(run_id, result)
#       → Fired when the eval/test suite reports overall_result == "pass".
#         The built-in GitCommitHook implementation uses this to auto-commit
#         a verified snapshot to the git repository.

import subprocess as _subprocess
import sys as _sys


class HarnessHooks:
    """Registry and dispatcher for harness lifecycle hooks.

    Usage::

        hooks = HarnessHooks()
        hooks.register("on_run_init", my_callback)
        rt = create_runtime(hooks=hooks)
    """

    VALID_EVENTS = {
        "on_before_advance",
        "on_run_init",
        "on_stage_advance",
        "on_gate_set",
        "on_claim_evaluated",
        "on_lesson_recorded",
        "on_run_terminal",
        "on_test_pass",
        "on_error",
        "on_state_corrupted",
        "on_user_input_requested",
        "on_artifact_written",
    }

    def __init__(self):
        self._handlers = {event: [] for event in self.VALID_EVENTS}

    def register(self, event, callback):
        # type: (str, object) -> None
        """Register *callback* for *event*.

        ``on_before_advance`` is the only hook that may raise ValueError to
        veto an operation. All other hooks are fire-and-forget; exceptions are
        printed to stderr but never re-raised.
        """
        if event not in self.VALID_EVENTS:
            raise ValueError("unknown_hook_event:" + event)
        self._handlers[event].append(callback)

    def fire(self, event, **kwargs):
        # type: (str, **object) -> None
        """Dispatch *event* to all registered callbacks.

        ``on_before_advance`` re-raises ValueError so callers can hard-block.
        All other events swallow exceptions after printing to stderr.
        """
        for handler in self._handlers.get(event, []):
            try:
                handler(**kwargs)
            except ValueError:
                if event == "on_before_advance":
                    raise
                import traceback
                print(
                    "[harness_hook_error] event={} handler={} error={}".format(
                        event, getattr(handler, "__name__", repr(handler)),
                        traceback.format_exc()
                    ),
                    file=_sys.stderr,
                )
            except Exception:
                import traceback
                print(
                    "[harness_hook_error] event={} handler={} error={}".format(
                        event, getattr(handler, "__name__", repr(handler)),
                        traceback.format_exc()
                    ),
                    file=_sys.stderr,
                )


class GitCommitHook:
    """Built-in hook: commits the current working tree when all tests pass.

    Registers on ``on_test_pass``. Performs::

        git add -A
        git commit -m "harness: tests verified — <run_id> [auto]"

    Only commits if there are staged changes. Skips silently when git is not
    available or the working tree is already clean.

    Usage::

        hooks = HarnessHooks()
        hooks.register("on_test_pass", GitCommitHook(root_dir).on_test_pass)
        rt = create_runtime(hooks=hooks)
    """

    def __init__(self, root_dir=None):
        self.root_dir = str(root_dir or Path(".").resolve())

    def on_test_pass(self, run_id, result):
        # type: (str, dict) -> None
        """Stage all changes and commit with an informative message."""
        try:
            status = _subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=self.root_dir,
                capture_output=True,
                text=True,
            )
            if not status.stdout.strip():
                # Nothing to commit — working tree is clean.
                return

            _subprocess.run(
                ["git", "add", "-A"],
                cwd=self.root_dir,
                check=True,
                capture_output=True,
            )
            passed = result.get("passed", "?")
            total = result.get("total_cases", "?")
            msg = "harness: tests verified ({}/{}) — {} [auto]".format(
                passed, total, run_id
            )
            _subprocess.run(
                ["git", "commit", "-m", msg],
                cwd=self.root_dir,
                check=True,
                capture_output=True,
            )
            print("[harness_hook:git_commit] committed: " + msg, file=_sys.stderr)
        except FileNotFoundError:
            # git not installed — skip silently.
            pass
        except _subprocess.CalledProcessError as exc:
            print(
                "[harness_hook:git_commit_failed] " + str(exc),
                file=_sys.stderr,
            )


_NOOP_HOOKS = HarnessHooks()


class HarnessRuntime:
    def __init__(self, root_dir=None, hooks=None):
        self.root_dir = Path(root_dir) if root_dir else DEFAULT_ROOT
        self.harness_dir = self.root_dir / ".harness"
        self.runs_dir = self.harness_dir / "runs"
        self.hooks = hooks if hooks is not None else _NOOP_HOOKS

    # ── Contracts ────────────────────────────────────────────────────────────

    def _load_contracts(self):
        runtime_contract = _read_json(self.harness_dir / "runtime_contract.json")
        profile = runtime_contract.get("project_profile", {})
        state_machine = _read_json(self.harness_dir / "state_machine.json")
        claim_policy = _read_json(self.root_dir / profile.get("claim_policy", ".harness/claim_policy.json"))
        artifact_policy = _read_json(self.root_dir / profile.get("artifact_policy", ".harness/artifact_policy.json"))
        evidence_policy = _read_json(self.root_dir / profile.get("evidence_policy", ".harness/evidence_policy.json"))
        role_policy = _read_json(self.harness_dir / "role_policy.json")
        injection_policy = _read_json(self.root_dir / profile.get("injection_policy", ".harness/injection_policy.json"))
        eval_contract = _read_json(self.root_dir / profile.get("eval_contract", ".harness/eval_contract.json"))
        prompt_contract = _read_json(self.root_dir / profile.get("prompt_contract", ".harness/prompt_contract.json"))
        manifest = _read_json(
            self.root_dir
            / profile.get(
                "dataset_manifest",
                "projects/ForestVol/set_imagenes+guia/dataset_manifest.json",
            )
        )
        self._validate_contract_integrity(
            runtime_contract, state_machine, claim_policy, artifact_policy,
            evidence_policy, role_policy, injection_policy, eval_contract,
            prompt_contract, manifest
        )
        return (
            runtime_contract, state_machine, claim_policy, artifact_policy,
            evidence_policy, role_policy, injection_policy, eval_contract,
            prompt_contract, manifest
        )

    def _validate_contract_integrity(self, runtime_contract: dict, state_machine: dict,
                                     claim_policy: dict, artifact_policy: dict,
                                     evidence_policy: dict, role_policy: dict,
                                     injection_policy: dict, eval_contract: dict,
                                     prompt_contract: dict, manifest: dict) -> None:
        self._validate_json_schema(
            runtime_contract,
            self.harness_dir / "schemas" / "runtime_contract.schema.json",
            "runtime_contract",
        )
        self._validate_json_schema(
            prompt_contract,
            self.harness_dir / "schemas" / "prompt_contract.schema.json",
            "prompt_contract",
        )
        contract_stages = set(runtime_contract["stages"])
        machine_stages = set(state_machine["stages"])
        if contract_stages != machine_stages:
            raise ValueError("authority_gate_failed:stage_contract_mismatch")
        if set(runtime_contract["terminal_stages"]) != set(state_machine["terminal_stages"]):
            raise ValueError("authority_gate_failed:terminal_stage_mismatch")
        missing_statuses = set(runtime_contract["terminal_stages"]) - set(TERMINAL_STATUS_BY_STAGE)
        if missing_statuses:
            raise ValueError("authority_gate_failed:terminal_status_mapping_missing")
        if not claim_policy.get("claims"):
            raise ValueError("authority_gate_failed:claim_policy_empty")
        if prompt_contract["bootstrap_prompt"] != runtime_contract["bootstrap_prompt"]:
            raise ValueError("authority_gate_failed:bootstrap_prompt_contract_mismatch")
        dataset_required = manifest.get("dataset_gate", {}).get("required", True)
        if dataset_required and ("dataset_root" not in manifest or "reference_marker" not in manifest):
            raise ValueError("authority_gate_failed:dataset_manifest_invalid")
        for role in runtime_contract["roles"]:
            if role not in role_policy["roles"]:
                raise ValueError(f"authority_gate_failed:role_policy_missing:{role}")
            if role not in prompt_contract["role_prompts"]:
                raise ValueError(f"authority_gate_failed:prompt_role_missing:{role}")
            if role not in prompt_contract["output_contracts"]:
                raise ValueError(f"authority_gate_failed:prompt_output_contract_missing:{role}")
        for artifact in artifact_policy["artifacts"]:
            owner = artifact_policy["artifacts"][artifact]["owner_role"]
            if owner not in runtime_contract["roles"]:
                raise ValueError(f"authority_gate_failed:artifact_owner_unknown:{artifact}")
        for field in evidence_policy["required_fields"]:
            if not isinstance(field, str):
                raise ValueError("authority_gate_failed:evidence_policy_invalid")
        for role, output_contract in prompt_contract["output_contracts"].items():
            allowed_artifacts = set(role_policy["roles"].get(role, {}).get("can_write_artifacts", []))
            if not set(output_contract["artifacts"]).issubset(allowed_artifacts):
                raise ValueError(f"authority_gate_failed:prompt_output_artifact_mismatch:{role}")

        canonical_doc = self.root_dir / runtime_contract["canonical_doc"]
        bootstrap_prompt = self.root_dir / runtime_contract["bootstrap_prompt"]
        project_context = self.root_dir / prompt_contract["project_context"]
        eval_prompt = self.root_dir / prompt_contract["eval_prompt"]
        if not canonical_doc.exists():
            raise FileNotFoundError("authority_gate_failed:canonical_doc_missing")
        if not bootstrap_prompt.exists():
            raise FileNotFoundError("authority_gate_failed:bootstrap_prompt_missing")
        if not project_context.exists():
            raise FileNotFoundError("authority_gate_failed:project_context_missing")
        if not eval_prompt.exists():
            raise FileNotFoundError("authority_gate_failed:eval_prompt_missing")

        content = canonical_doc.read_text(encoding="utf-8")
        expected_version = f"**Version:** {runtime_contract['harness_version']}"
        if expected_version not in content or "**Estado:** `active`" not in content:
            raise ValueError("authority_gate_failed:canonical_doc_version_mismatch")
        for rel_path in eval_contract["required_files"]:
            if not (self.root_dir / rel_path).exists():
                raise FileNotFoundError(f"authority_gate_failed:eval_file_missing:{rel_path}")
        for rel_path in prompt_contract["trusted_sources"]:
            if not (self.root_dir / rel_path).exists():
                raise FileNotFoundError(f"authority_gate_failed:trusted_source_missing:{rel_path}")
        confirmation_policy = prompt_contract["terminal_confirmation"]
        if not set(confirmation_policy["required_stages"]).issubset(set(runtime_contract["terminal_stages"])):
            raise ValueError("authority_gate_failed:terminal_confirmation_stage_invalid")

        validate_prompt_contract_files(
            self.root_dir,
            runtime_contract,
            prompt_contract,
            content,
        )

    def _validate_json_schema(self, payload, schema_path: Path, label: str) -> None:
        schema = _read_json(schema_path)
        if schema.get("strict") is not True:
            raise ValueError(f"schema_not_strict:{label}")
        validate_schema_node(payload, schema, label)

    # ── Paths ─────────────────────────────────────────────────────────────────

    def _assert_safe_run_id(self, run_id: str) -> None:
        if not run_id:
            raise ValueError("run_id_required")
        if not re.match(r"^[a-zA-Z0-9_-]+$", run_id):
            raise ValueError("invalid_run_id_format")

    def _assert_safe_ref(self, value: str, label: str) -> None:
        assert_safe_ref(value, label)

    def _resolve_under(self, base: Path, rel_path: str, label: str) -> Path:
        self._assert_safe_ref(rel_path, label)
        resolved_base = base.resolve()
        resolved_path = (base / rel_path).resolve()
        if resolved_path != resolved_base and resolved_base not in resolved_path.parents:
            raise ValueError(f"guardrail_input_invalid:{label}:outside_root")
        return resolved_path

    def _run_path(self, run_id: str) -> Path:
        self._assert_safe_run_id(run_id)
        return self.runs_dir / run_id

    def _artifact_path(self, run_id: str, name: str) -> Path:
        return self._resolve_under(self._run_path(run_id), name, "artifact_ref")

    # ── Dataset gate ──────────────────────────────────────────────────────────

    def _dataset_evidence(self, manifest: dict) -> dict:
        if manifest.get("dataset_gate", {}).get("required") is False:
            return {"refs": [], "image_count": 0}

        dataset_root = self.root_dir / manifest["dataset_root"]
        marker_path = self.root_dir / manifest["reference_marker"]["marker_image_path"]

        if not dataset_root.exists():
            raise FileNotFoundError("dataset_gate_failed:dataset_root_missing")
        if not marker_path.exists():
            raise FileNotFoundError("dataset_gate_failed:marker_missing")

        accepted = {ext.lower() for ext in manifest["input_contract"]["accepted_extensions"]}
        image_count = sum(
            1 for p in dataset_root.iterdir()
            if p.is_file() and p.suffix.lower() in accepted
        )
        if image_count < manifest["input_contract"]["min_images"]:
            raise ValueError("dataset_gate_failed:min_images")

        return {
            "refs": ["dataset_manifest", "dataset_images", "marker_image_file"],
            "image_count": image_count,
        }

    def _active_dataset_manifest_path(self) -> str:
        runtime_contract = _read_json(self.harness_dir / "runtime_contract.json")
        return runtime_contract.get("project_profile", {}).get(
            "dataset_manifest",
            "projects/ForestVol/set_imagenes+guia/dataset_manifest.json",
        )

    # ── State I/O ─────────────────────────────────────────────────────────────

    def read_state(self, run_id: str) -> dict:
        return _read_json(self._artifact_path(run_id, "state.json"))

    def write_state(self, run_id: str, state: dict) -> dict:
        previous_hash = (state.get("integrity") or {}).get("current_hash", "GENESIS")
        state["last_updated"] = _now_iso()
        self._assert_traceability_files(run_id)
        state.setdefault("gate_status", {})["traceability_gate"] = "passed"
        integrity = {
            "previous_hash": previous_hash,
            "current_hash": "",
            "algorithm": "sha256",
        }
        state["integrity"] = integrity
        integrity["current_hash"] = self._state_hash(state)
        self._validate_json_schema(
            state,
            self.harness_dir / "schemas" / "state.schema.json",
            "state",
        )
        _write_json(self._artifact_path(run_id, "state.json"), state)
        self._append_audit(run_id, "state_written", previous_hash, integrity["current_hash"])
        self._sync_traceability(run_id, state)
        return state

    def _state_hash(self, state: dict) -> str:
        payload = json.loads(json.dumps(state))
        payload.get("integrity", {})["current_hash"] = ""
        return _sha256_bytes(_canonical_json(payload))

    def _append_audit(self, run_id: str, event_type: str,
                      previous_hash: str, current_hash: str, details: dict = None) -> None:
        audit_path = self._artifact_path(run_id, "audit/audit_log.jsonl")
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "ts": _now_iso(),
            "type": event_type,
            "previous_hash": previous_hash,
            "current_hash": current_hash,
            "details": details or {},
        }
        _append_jsonl(audit_path, payload)
        _append_jsonl(self._global_audit_path(), {"run_id": run_id, **payload})

    def _assert_state_integrity(self, state: dict) -> None:
        integrity = state.get("integrity")
        if not isinstance(integrity, dict) or "current_hash" not in integrity:
            self.hooks.fire("on_state_corrupted", run_id=state.get("run_id"), state=state)
            raise ValueError("state_integrity_missing")
        if integrity["current_hash"] != self._state_hash(state):
            self.hooks.fire("on_state_corrupted", run_id=state.get("run_id"), state=state)
            raise ValueError("state_integrity_failed")

    def _assert_traceability_files(self, run_id: str) -> None:
        for name in ("traceability.json", "events/cycle_log.jsonl", "decisions/decision_log.jsonl", "audit/audit_log.jsonl", "lessons/lessons_log.jsonl"):
            if not self._artifact_path(run_id, name).exists():
                raise FileNotFoundError(f"traceability_gate_failed:{name}")

    def _sync_traceability(self, run_id: str, state: dict,
                           event: dict = None, decision: dict = None,
                           lesson: dict = None) -> None:
        trace_path = self._artifact_path(run_id, "traceability.json")
        trace = _read_json(trace_path)
        trace["status"] = state["status"]
        trace["current_stage"] = state["current_stage"]
        trace.setdefault("events", [])
        trace.setdefault("decisions", [])
        trace.setdefault("lessons", [])
        if event:
            trace["events"].append(event)
        if decision:
            trace["decisions"].append(decision)
        if lesson:
            trace["lessons"].append({
                "lesson_id": lesson["lesson_id"],
                "stage": lesson["stage"],
                "outcome": lesson["outcome"],
                "do_not_repeat": lesson["do_not_repeat"],
                "recommended_action": lesson["recommended_action"],
                "applies_when": lesson["applies_when"],
                "severity": lesson["severity"],
                "source": lesson["source"],
                "timestamp": lesson["timestamp"],
            })
        _write_json(trace_path, trace)

    # ── Logging ───────────────────────────────────────────────────────────────

    def log_cycle(self, run_id: str, type_: str,
                  details: dict = None, state: dict = None) -> None:
        """Append to cycle_log.jsonl. Pass state to avoid redundant disk read."""
        payload = {**(details or {}), "ts": _now_iso(), "type": type_}
        cycle_path = self._artifact_path(run_id, "events/cycle_log.jsonl")
        cycle_path.parent.mkdir(parents=True, exist_ok=True)
        _append_jsonl(cycle_path, payload)
        s = state if state is not None else self.read_state(run_id)
        self._sync_traceability(run_id, s, event=payload)

    def log_decision(self, run_id: str, type_: str,
                     details: dict = None, state: dict = None) -> None:
        """Append to decision_log.jsonl. Pass state to avoid redundant disk read."""
        payload = {**(details or {}), "ts": _now_iso(), "type": type_}
        decision_path = self._artifact_path(run_id, "decisions/decision_log.jsonl")
        decision_path.parent.mkdir(parents=True, exist_ok=True)
        _append_jsonl(decision_path, payload)
        s = state if state is not None else self.read_state(run_id)
        self._sync_traceability(run_id, s, decision=payload)

    # -- Lessons ----------------------------------------------------------------

    def _global_lessons_path(self) -> Path:
        path = self.root_dir / "trazabilidad" / "lessons" / "LESSONS_LEARNED.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        _ensure_file(path)
        return path

    def _global_audit_path(self) -> Path:
        path = self.root_dir / "trazabilidad" / "audit" / "global_audit_trail.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        _ensure_file(path)
        return path

    def _global_milestones_path(self) -> Path:
        path = self.root_dir / "trazabilidad" / "milestones" / "global_milestones.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        _ensure_file(path)
        return path

    def _read_jsonl_file(self, path: Path) -> list:
        if not path.exists():
            return []
        rows = []
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid_jsonl:{path}:{line_no}") from exc
        return rows

    def _validate_lesson(self, lesson: dict) -> None:
        missing = REQUIRED_LESSON_FIELDS - set(lesson)
        if missing:
            raise ValueError(f"lesson_missing_field:{','.join(sorted(missing))}")
        for field in (
            "lesson_id",
            "run_id",
            "stage",
            "context",
            "attempted_action",
            "outcome",
            "failure_reason",
            "do_not_repeat",
            "recommended_action",
            "severity",
            "source",
            "timestamp",
        ):
            if not isinstance(lesson[field], str):
                raise ValueError(f"lesson_invalid_type:{field}")
        if not re.match(r"^[A-Za-z0-9_.-]+$", lesson["lesson_id"]):
            raise ValueError("lesson_invalid_id")
        if lesson["severity"] not in LESSON_SEVERITIES:
            raise ValueError(f"lesson_invalid_severity:{lesson['severity']}")
        if not isinstance(lesson["applies_when"], list):
            raise ValueError("lesson_invalid_type:applies_when")
        if any(not isinstance(item, str) or not item.strip() for item in lesson["applies_when"]):
            raise ValueError("lesson_invalid_applies_when")

    def list_lessons(self, run_id: str = None, include_global: bool = False) -> dict:
        lessons = []
        if run_id:
            self._assert_safe_run_id(run_id)
            lessons.extend(self._read_jsonl_file(self._artifact_path(run_id, "lessons/lessons_log.jsonl")))
        if include_global or not run_id:
            lessons.extend(self._read_jsonl_file(self._global_lessons_path()))
        return {"count": len(lessons), "lessons": lessons}

    def record_lesson(self, run_id: str, context: str, attempted_action: str,
                      outcome: str, failure_reason: str, do_not_repeat: str,
                      recommended_action: str, applies_when: list,
                      severity: str = "medium", source: str = "manual",
                      stage: str = None, lesson_id: str = None) -> dict:
        self._assert_safe_run_id(run_id)
        state = self.read_state(run_id)
        lesson = {
            "lesson_id": lesson_id or f"LESSON-{run_id}-{len(self.list_lessons(run_id)['lessons']) + 1:03d}",
            "run_id": run_id,
            "stage": stage or state["current_stage"],
            "context": context,
            "attempted_action": attempted_action,
            "outcome": outcome,
            "failure_reason": failure_reason,
            "do_not_repeat": do_not_repeat,
            "recommended_action": recommended_action,
            "applies_when": applies_when,
            "severity": severity,
            "source": source,
            "timestamp": _now_iso(),
        }
        self._validate_lesson(lesson)
        lesson_path = self._artifact_path(run_id, "lessons/lessons_log.jsonl")
        lesson_path.parent.mkdir(parents=True, exist_ok=True)
        _append_jsonl(lesson_path, lesson)
        _append_jsonl(self._global_lessons_path(), lesson)
        self._sync_traceability(run_id, state, lesson=lesson)
        self.log_decision(run_id, "lesson_recorded", {
            "lesson_id": lesson["lesson_id"],
            "source": source,
            "severity": severity,
            "applies_when": applies_when,
        }, state)
        self.hooks.fire("on_lesson_recorded", run_id=run_id, lesson=lesson, state=state)
        return lesson

    def _assert_no_known_lesson_repeat(self, run_id: str, content: str, label: str) -> None:
        if not content:
            return
        content_compact = _compact_text(content)
        for lesson in self.list_lessons(run_id, include_global=True)["lessons"]:
            do_not_repeat = lesson.get("do_not_repeat") or ""
            if not do_not_repeat.strip():
                continue
            lesson_compact = _compact_text(do_not_repeat)
            if lesson_compact and lesson_compact in content_compact:
                raise ValueError(
                    f"lesson_repeat_blocked:{label}:{lesson.get('lesson_id', 'unknown')}"
                )

    # ── Validation ────────────────────────────────────────────────────────────

    def validate_state_object(self, state: dict) -> bool:
        runtime_contract, state_machine, *_ = self._load_contracts()
        self._validate_json_schema(
            state,
            self.harness_dir / "schemas" / "state.schema.json",
            "state",
        )
        required = set(runtime_contract["required_state_fields"])
        allowed_statuses = set(runtime_contract["terminal_statuses"]) | {"running"}

        for field in required:
            if field not in state:
                raise ValueError(f"missing_state_field:{field}")
        if state["status"] not in allowed_statuses:
            raise ValueError(f"invalid_status:{state['status']}")
        if state["current_stage"] not in state_machine["stages"]:
            raise ValueError(f"invalid_stage:{state['current_stage']}")
        self._assert_state_integrity(state)
        if set(state["gate_status"]) != set(runtime_contract["gates"]):
            raise ValueError("invalid_gate_status_keys")
        invalid_gate_values = [
            value for value in state["gate_status"].values()
            if value not in ALLOWED_GATE_VALUES
        ]
        if invalid_gate_values:
            raise ValueError("invalid_gate_status_value")
        for field in ("completed_stages", "active_claims", "blocked_claims",
                      "evidence_refs", "artifacts"):
            if not isinstance(state.get(field), list):
                raise ValueError(f"invalid_state_field_type:{field}")
        return True

    def validate_run(self, run_id: str) -> dict:
        state = self.read_state(run_id)
        self.validate_state_object(state)
        return state

    # ── Stage side effects ────────────────────────────────────────────────────

    def _apply_stage_side_effects(self, state: dict, stage: str, artifacts: list) -> dict:
        if stage == "ANALYZE" and "analyze-report.md" in artifacts:
            state["gate_status"]["analysis_gate"] = "passed"
        if stage == "QA" and "test-report.md" in artifacts:
            state["gate_status"]["test_gate"] = "passed"
        return state

    def _assert_required_artifacts(self, stage_config: dict,
                                   artifacts: list, current_stage: str) -> None:
        required = set(stage_config.get("exit_artifacts") or [])
        missing = required - set(artifacts)
        if missing:
            raise ValueError(
                f"missing_exit_artifacts:{current_stage}:{','.join(sorted(missing))}"
            )
        extra = set(artifacts) - required
        if extra:
            raise ValueError(
                f"guardrail_tool_call_artifact_scope:{current_stage}:{','.join(sorted(extra))}"
            )

    def _assert_artifacts_exist(self, run_id: str, artifacts: list) -> None:
        for artifact in artifacts:
            if not self._artifact_path(run_id, artifact).exists():
                raise FileNotFoundError(f"artifact_not_found:{artifact}")

    def _assert_actor(self, actor: str, permission: str) -> None:
        _, _, _, _, _, role_policy, *_ = self._load_contracts()
        role = role_policy["roles"].get(actor)
        if not role:
            raise ValueError(f"unknown_actor_role:{actor}")
        if not role.get(permission, False):
            raise PermissionError(f"role_not_authorized:{actor}:{permission}")

    def _assert_artifact_role(self, artifact: str, actor: str) -> None:
        _, _, _, artifact_policy, _, role_policy, *_ = self._load_contracts()
        policy = artifact_policy["artifacts"].get(artifact)
        if not policy:
            return
        owner = policy["owner_role"]
        if actor != "orchestrator" and actor != owner:
            raise PermissionError(f"artifact_role_violation:{artifact}:{actor}:{owner}")
        allowed = role_policy["roles"][owner]["can_write_artifacts"]
        if artifact not in allowed:
            raise PermissionError(f"artifact_owner_policy_violation:{artifact}:{owner}")

    def _assert_clean_text(self, content: str, artifact: str) -> None:
        _, _, _, artifact_policy, _, _, injection_policy, *_ = self._load_contracts()
        normalized = content.lower()
        if len(content.strip()) < artifact_policy["min_chars"]:
            raise ValueError(f"artifact_invalid:too_short:{artifact}")
        for pattern in artifact_policy["forbidden_patterns"]:
            if pattern.lower() in normalized:
                raise ValueError(f"artifact_invalid:forbidden_pattern:{artifact}:{pattern}")
        self._assert_no_prompt_injection(content, artifact, injection_policy)
        lines = [line.strip() for line in content.splitlines() if line.strip()]
        if lines:
            most_common = max(lines.count(line) for line in set(lines))
            if most_common / len(lines) > artifact_policy["max_repeated_line_ratio"]:
                raise ValueError(f"artifact_invalid:repeated_content:{artifact}")

    def _assert_no_prompt_injection(self, content: str, artifact: str,
                                    injection_policy: dict) -> None:
        normalized = _compact_text(content)
        joined = _joined_text(content)
        raw_lower = _ascii_fold(content)
        for pattern in injection_policy["forbidden_instruction_patterns"]:
            compact_pattern = _compact_text(pattern)
            joined_pattern = _joined_text(pattern)
            if compact_pattern in normalized or joined_pattern in joined:
                raise ValueError(f"artifact_invalid:prompt_injection:{artifact}")

        for marker in injection_policy.get("protected_markers", []):
            if _ascii_fold(marker) in raw_lower or _joined_text(marker) in joined:
                raise ValueError(f"artifact_invalid:prompt_injection:{artifact}:protected_marker")

        intent_hits = [
            term for term in injection_policy.get("suspicious_intent_terms", [])
            if _policy_term_matches(term, normalized, joined)
        ]
        target_hits = [
            term for term in injection_policy.get("protected_target_terms", [])
            if _policy_term_matches(term, normalized, joined)
        ]
        if intent_hits and target_hits:
            raise ValueError(f"artifact_invalid:prompt_injection:{artifact}:intent_target")

    def _assert_tool_text_safe(self, content: str, label: str) -> None:
        if not content:
            return
        _, _, _, _, _, _, injection_policy, *_ = self._load_contracts()
        try:
            self._assert_no_prompt_injection(content, label, injection_policy)
        except ValueError as exc:
            raise ValueError(f"guardrail_input_prompt_injection:{label}") from exc

    def _assert_ref_list_safe(self, refs: list, label: str) -> None:
        for ref in refs or []:
            self._assert_safe_ref(ref, label)

    def _assert_artifact_structure(self, run_id: str, artifact: str, actor: str = "orchestrator") -> None:
        _, _, _, artifact_policy, *_ = self._load_contracts()
        policy = artifact_policy["artifacts"].get(artifact)
        if not policy:
            return
        self._assert_artifact_role(artifact, actor)
        path = self._artifact_path(run_id, artifact)
        content = path.read_text(encoding="utf-8")
        self._assert_clean_text(content, artifact)
        for heading in policy["required_headings"]:
            if not re.search(rf"^#+\s+{re.escape(heading)}\b", content, re.MULTILINE | re.IGNORECASE):
                raise ValueError(f"artifact_invalid:missing_heading:{artifact}:{heading}")
        if policy.get("requires_task_ids"):
            task_ids = re.findall(r"\bT-\d{3,}\b", content)
            if not task_ids:
                raise ValueError(f"artifact_invalid:missing_task_ids:{artifact}")
            if len(task_ids) != len(set(task_ids)):
                raise ValueError(f"artifact_invalid:duplicate_task_ids:{artifact}")
        self._assert_artifact_semantics(run_id, artifact, content)

    def _assert_artifact_semantics(self, run_id: str, artifact: str, content: str) -> None:
        _, _, _, artifact_policy, *_ = self._load_contracts()
        policy = artifact_policy["artifacts"].get(artifact) or {}
        semantic_rules = policy.get("semantic_rules") or {}
        normalized = _normalized_text(content)

        for idx, group in enumerate(semantic_rules.get("must_include_any") or [], start=1):
            if not any(term.lower() in normalized for term in group):
                raise ValueError(
                    f"artifact_invalid:semantic_missing:{artifact}:group_{idx}"
                )

        for phrase in semantic_rules.get("must_not_include") or []:
            if phrase.lower() in normalized:
                raise ValueError(f"artifact_invalid:semantic_contradiction:{artifact}:{phrase}")

        self._assert_cross_artifact_consistency(run_id, artifact, normalized)

    def _assert_cross_artifact_consistency(self, run_id: str, artifact: str, normalized: str) -> None:
        if artifact == "plan.md":
            self._assert_concept_inheritance(
                run_id,
                source_artifact="spec.md",
                target_artifact=artifact,
                target_normalized=normalized,
                concepts=["rgb", "aruco", "metadata_free", "ground_truth"],
            )
            return

        if artifact == "tasks.md":
            self._assert_concept_inheritance(
                run_id,
                source_artifact="spec.md",
                target_artifact=artifact,
                target_normalized=normalized,
                concepts=["rgb", "aruco", "metadata_free"],
            )
            self._assert_concept_inheritance(
                run_id,
                source_artifact="plan.md",
                target_artifact=artifact,
                target_normalized=normalized,
                concepts=["dataset_manifest", "evidence", "runtime", "mesh_volume"],
            )
            return

        if artifact == "analyze-report.md":
            self._assert_concept_inheritance(
                run_id,
                source_artifact="tasks.md",
                target_artifact=artifact,
                target_normalized=normalized,
                concepts=["dataset_manifest", "evidence", "mesh_volume", "claims"],
            )
            self._assert_concept_inheritance(
                run_id,
                source_artifact="spec.md",
                target_artifact=artifact,
                target_normalized=normalized,
                concepts=["ground_truth", "metadata_free"],
            )
            return

        if artifact == "validation-report.md":
            self._assert_state_report_consistency(run_id, artifact, normalized)
            return

        if artifact == "final-report.md":
            self._assert_state_report_consistency(run_id, artifact, normalized)

    def _assert_concept_inheritance(self, run_id: str, source_artifact: str,
                                    target_artifact: str, target_normalized: str,
                                    concepts: list) -> None:
        source_path = self._artifact_path(run_id, source_artifact)
        if not source_path.exists():
            return
        source_normalized = _normalized_text(source_path.read_text(encoding="utf-8"))
        for concept in concepts:
            aliases = SEMANTIC_CONCEPT_GROUPS[concept]
            if any(alias in source_normalized for alias in aliases):
                if not any(alias in target_normalized for alias in aliases):
                    raise ValueError(
                        f"artifact_invalid:semantic_incomplete:{target_artifact}:missing_{concept}"
                    )

    def _assert_state_report_consistency(self, run_id: str, artifact: str,
                                         normalized: str) -> None:
        state = self.read_state(run_id)

        contradiction_groups = []
        if artifact == "validation-report.md":
            if state["gate_status"].get("claim_gate") == "failed":
                contradiction_groups.extend([
                    "claim_gate passed",
                    "todos los claims aceptados",
                    "sin claims bloqueados",
                ])
            if state["gate_status"].get("claim_gate") == "passed":
                contradiction_groups.append("claim_gate failed")
            if state["gate_status"].get("analysis_gate") == "passed":
                required = ["analisis", "analyze-report", "analysis_gate"]
                if not any(term in normalized for term in required):
                    raise ValueError(
                        "artifact_invalid:semantic_state_mismatch:validation-report.md:missing_analysis_reference"
                    )

        if artifact == "final-report.md":
            if state.get("blocked_claims"):
                contradiction_groups.extend([
                    "close permitido",
                    "cierre permitido",
                    "sin claims bloqueados",
                ])
            else:
                contradiction_groups.append("claim_gate failed")
            if state["gate_status"].get("claim_gate") == "failed":
                contradiction_groups.append("claim_gate passed")
            if state["gate_status"].get("test_gate") == "failed":
                contradiction_groups.extend(["test_gate pasa", "test_gate passed"])

        for phrase in contradiction_groups:
            if phrase in normalized:
                raise ValueError(
                    f"artifact_invalid:semantic_state_mismatch:{artifact}:{phrase}"
                )

    def _assert_artifacts_valid(self, run_id: str, artifacts: list, actor: str) -> None:
        self._assert_artifacts_exist(run_id, artifacts)
        for artifact in artifacts:
            self._assert_artifact_structure(run_id, artifact, actor)

    def _load_evidence_record(self, run_id: str, evidence_ref: str) -> dict:
        self._assert_safe_ref(evidence_ref, "evidence_ref")
        if not evidence_ref.endswith(".json"):
            raise ValueError(f"evidence_invalid:nominal_evidence:{evidence_ref}")
        path = self._artifact_path(run_id, evidence_ref)
        if not path.exists():
            raise FileNotFoundError(f"evidence_not_found:{evidence_ref}")
        return _read_json(path)

    def _resolve_evidence_artifact(self, run_id: str, artifact_ref: str) -> Path:
        self._assert_safe_ref(artifact_ref, "evidence_artifact_path")
        root_candidate = self._resolve_under(self.root_dir, artifact_ref, "evidence_artifact_path")
        if root_candidate.exists():
            return root_candidate
        run_candidate = self._resolve_under(
            self._run_path(run_id),
            artifact_ref,
            "evidence_artifact_path",
        )
        if run_candidate.exists():
            return run_candidate
        raise FileNotFoundError(f"evidence_invalid:artifact_missing:{artifact_ref}")

    def _validate_evidence_record(self, run_id: str, evidence_ref: str,
                                  required_ref: str = None) -> dict:
        _, _, _, _, evidence_policy, *_ = self._load_contracts()
        record = self._load_evidence_record(run_id, evidence_ref)
        self._validate_json_schema(
            record,
            self.harness_dir / "schemas" / "evidence.schema.json",
            "evidence",
        )
        for field in evidence_policy["required_fields"]:
            if field not in record:
                raise ValueError(f"evidence_invalid:missing_field:{field}")
        if record["result"] not in evidence_policy["allowed_results"]:
            raise ValueError(f"evidence_invalid:result:{record['result']}")
        if record["result"] != "pass":
            raise ValueError(f"evidence_invalid:not_passing:{evidence_ref}")
        if record["validator"] not in evidence_policy["allowed_validators"]:
            raise ValueError(f"evidence_invalid:validator:{record['validator']}")
        if required_ref and record["claim"] != required_ref:
            raise ValueError(f"evidence_invalid:claim_mismatch:{required_ref}:{record['claim']}")
        artifact_path = self._resolve_evidence_artifact(run_id, record["artifact_path"])
        if _sha256_file(artifact_path) != record["checksum"]:
            raise ValueError(f"evidence_invalid:checksum:{evidence_ref}")
        return record

    def _assert_gate_evidence_matches(self, run_id: str, gate_name: str,
                                      evidence: list) -> list:
        _, _, _, _, evidence_policy, *_ = self._load_contracts()
        project_gate_claims = evidence_policy.get("gate_evidence_claims", {})
        allowed_claims = set(project_gate_claims.get(gate_name, GATE_EVIDENCE_CLAIMS.get(gate_name, [])))
        if not allowed_claims:
            raise ValueError(f"guardrail_tool_call_unknown_gate:{gate_name}")
        records = []
        for ref in evidence:
            record = self._validate_evidence_record(run_id, ref)
            if record["claim"] not in allowed_claims:
                raise ValueError(
                    f"guardrail_tool_call_evidence_mismatch:{gate_name}:{record['claim']}"
                )
            records.append(record)
        return records

    def _resolve_record_artifact(self, run_id: str, record: dict) -> Path:
        return self._resolve_evidence_artifact(run_id, record["artifact_path"])

    def _assert_claim_semantics(self, run_id: str, claim_name: str,
                                records_by_claim: dict) -> None:
        _, _, claim_policy, _, _, _, _, _, _, manifest = self._load_contracts()
        rule = claim_policy["claims"][claim_name]
        validator_name = rule.get("semantic_validator")
        if not validator_name:
            return

        if validator_name == "dataset_contract":
            manifest_record = records_by_claim["dataset_manifest"]
            images_record = records_by_claim["dataset_images"]
            if manifest_record["validator"] != "dataset_gate":
                raise ValueError("claim_invalid:dataset_contract:manifest_validator")
            if images_record["validator"] != "dataset_gate":
                raise ValueError("claim_invalid:dataset_contract:images_validator")
            dataset_manifest_path = self._active_dataset_manifest_path()
            if manifest_record["artifact_path"] != dataset_manifest_path:
                raise ValueError("claim_invalid:dataset_contract:manifest_artifact_path")
            if manifest["input_contract"]["requires_exif"] is not False:
                raise ValueError("claim_invalid:dataset_contract:requires_exif")
            if manifest["input_contract"]["requires_drone_metadata"] is not False:
                raise ValueError("claim_invalid:dataset_contract:requires_drone_metadata")
            if set(ext.lower() for ext in manifest["input_contract"]["accepted_extensions"]) != {
                ".jpg", ".jpeg", ".png"
            }:
                raise ValueError("claim_invalid:dataset_contract:accepted_extensions")

        elif validator_name == "reference_marker":
            marker_record = records_by_claim["marker_image_file"]
            manifest_record = records_by_claim["dataset_manifest"]
            if marker_record["validator"] != "dataset_gate":
                raise ValueError("claim_invalid:reference_marker:marker_validator")
            dataset_manifest_path = self._active_dataset_manifest_path()
            if manifest_record["artifact_path"] != dataset_manifest_path:
                raise ValueError("claim_invalid:reference_marker:manifest_artifact_path")
            ref = manifest["reference_marker"]
            if ref["dictionary"] != "DICT_4X4_50" or ref["id"] != 0 or ref["physical_size_cm"] != 50.0:
                raise ValueError("claim_invalid:reference_marker:manifest_content")
            if marker_record["artifact_path"] != ref["marker_image_path"]:
                raise ValueError("claim_invalid:reference_marker:marker_artifact_path")

        elif validator_name == "volume_estimate":
            mesh_record = records_by_claim["valid_mesh"]
            if mesh_record["validator"] != "mesh_validator":
                raise ValueError("claim_invalid:volume_estimate:validator")
            mesh_path = self._resolve_record_artifact(run_id, mesh_record)
            if mesh_path.suffix.lower() not in {".obj", ".ply", ".glb", ".gltf", ".stl", ".json"}:
                raise ValueError("claim_invalid:volume_estimate:artifact_type")

        elif validator_name == "error_percentage":
            gt_record = records_by_claim["ground_truth_certified"]
            if gt_record["validator"] != "ground_truth_validator":
                raise ValueError("claim_invalid:error_percentage:validator")
            gt_path = self._resolve_record_artifact(run_id, gt_record)
            payload = _read_json(gt_path)
            if payload.get("ground_truth", {}).get("volume_m3") is None:
                raise ValueError("claim_invalid:error_percentage:ground_truth_missing")
            if payload.get("error_percentage") is None:
                raise ValueError("claim_invalid:error_percentage:error_missing")

        elif validator_name == "rf09_compliance":
            gt_record = records_by_claim["ground_truth_certified"]
            error_record = records_by_claim["error_percentage"]
            if gt_record["validator"] != "ground_truth_validator":
                raise ValueError("claim_invalid:rf09_compliance:ground_truth_validator")
            if error_record["validator"] != "ground_truth_validator":
                raise ValueError("claim_invalid:rf09_compliance:error_validator")
            gt_path = self._resolve_record_artifact(run_id, gt_record)
            payload = _read_json(gt_path)
            error_value = payload.get("error_percentage")
            threshold = manifest["validation_contract"]["error_threshold_pct_when_gt_available"]
            if error_value is None:
                raise ValueError("claim_invalid:rf09_compliance:error_missing")
            if error_value > threshold:
                raise ValueError("claim_invalid:rf09_compliance:threshold_exceeded")

    # ── Core operations ───────────────────────────────────────────────────────

    def init_run(self, run_id: str) -> dict:
        if not run_id:
            raise ValueError("run_id_required")
        if not re.match(r"^[a-zA-Z0-9_-]+$", run_id):
            raise ValueError("invalid_run_id_format")

        runtime_contract, state_machine, *rest = self._load_contracts()
        manifest = rest[-1]

        self._run_path(run_id).mkdir(parents=True, exist_ok=True)
        dataset = self._dataset_evidence(manifest)

        gate_status = {gate: "pending" for gate in runtime_contract["gates"]}
        gate_status.update({
            "dataset_gate": "passed",
            "authority_gate": "passed",
            "traceability_gate": "passed",
        })

        state = {
            "run_id": run_id,
            "status": "running",
            "current_stage": state_machine["initial_stage"],
            "completed_stages": [],
            "active_claims": [],
            "blocked_claims": [],
            "evidence_refs": _unique(
                [self._active_dataset_manifest_path()] + dataset["refs"]
            ),
            "gate_status": gate_status,
            "artifacts": [],
            "claim_status": {},
            "integrity": {
                "previous_hash": "GENESIS",
                "current_hash": "",
                "algorithm": "sha256",
            },
            "last_updated": _now_iso(),
        }
        traceability = {
            "run_id": run_id,
            "status": "running",
            "current_stage": state["current_stage"],
            "events": [],
            "decisions": [],
            "lessons": [],
        }

        _write_json(self._artifact_path(run_id, "traceability.json"), traceability)
        for subdir in ["events", "decisions", "audit", "lessons"]:
            (self._run_path(run_id) / subdir).mkdir(parents=True, exist_ok=True)
        _ensure_file(self._artifact_path(run_id, "events/cycle_log.jsonl"))
        _ensure_file(self._artifact_path(run_id, "decisions/decision_log.jsonl"))
        _ensure_file(self._artifact_path(run_id, "audit/audit_log.jsonl"))
        _ensure_file(self._artifact_path(run_id, "lessons/lessons_log.jsonl"))
        self.write_state(run_id, state)
        state = self.read_state(run_id)
        self.log_cycle(run_id, "run_initialized",
                       {"stage": state["current_stage"], "image_count": dataset["image_count"]},
                       state)
        self.hooks.fire("on_run_init", run_id=run_id, state=state)
        return state

    def advance_run(self, run_id: str, next_stage: str,
                    artifacts: list = None, evidence: list = None,
                    actor: str = "orchestrator") -> dict:
        self._assert_actor(actor, "can_advance")
        _, state_machine, *_ = self._load_contracts()
        state = self.read_state(run_id)
        self.validate_state_object(state)

        if state["status"] != "running":
            raise ValueError("terminal_run_cannot_advance")

        current_stage = state["current_stage"]
        # Explicit terminal-stage guard for clear error messages
        if current_stage in state_machine["terminal_stages"]:
            raise ValueError(f"terminal_stage_cannot_advance:{current_stage}")

        current_config = state_machine["stages"][current_stage]
        if next_stage not in current_config["allowed_next"]:
            raise ValueError(f"invalid_transition:{current_stage}->{next_stage}")

        artifacts = _unique(artifacts or [])
        evidence = _unique(evidence or [])
        self._assert_ref_list_safe(artifacts, "artifact_ref")
        self._assert_ref_list_safe(evidence, "evidence_ref")

        self.hooks.fire("on_before_advance", run_id=run_id, current_stage=current_stage, next_stage=next_stage, artifacts=artifacts, actor=actor)

        if next_stage == "CLOSE":
            self._assert_required_artifacts(current_config, artifacts, current_stage)
            self._assert_artifacts_valid(run_id, artifacts, actor)
            self._apply_stage_side_effects(state, current_stage, artifacts)
        elif next_stage not in state_machine["terminal_stages"]:
            self._assert_required_artifacts(current_config, artifacts, current_stage)
            self._assert_artifacts_valid(run_id, artifacts, actor)
            self._apply_stage_side_effects(state, current_stage, artifacts)

        state["completed_stages"] = _unique(state["completed_stages"] + [current_stage])
        state["current_stage"] = next_stage
        state["artifacts"] = _unique(state["artifacts"] + artifacts)
        state["evidence_refs"] = _unique(state["evidence_refs"] + evidence)

        if next_stage in state_machine["terminal_stages"]:
            state["status"] = TERMINAL_STATUS_BY_STAGE[next_stage]

        self.write_state(run_id, state)
        self.log_cycle(run_id, "stage_advanced", {
            "from": current_stage,
            "to": next_stage,
            "artifacts": artifacts,
            "evidence": evidence or [],
            "actor": actor,
        }, state)

        for art in artifacts:
            self.hooks.fire("on_artifact_written", run_id=run_id, artifact=art, actor=actor, state=state)

        if next_stage == "CLOSE":
            _append_jsonl(self._global_milestones_path(), {
                "ts": _now_iso(),
                "run_id": run_id,
                "event": "project_closed_successfully"
            })

        self.hooks.fire("on_stage_advance", run_id=run_id, from_stage=current_stage, to_stage=next_stage, artifacts=artifacts, actor=actor, state=state)
        return state

    def set_gate(self, run_id: str, gate_name: str, value: str,
                 actor: str = "orchestrator", justification: str = "",
                 evidence: list = None) -> dict:
        self._assert_actor(actor, "can_set_gate")
        self._assert_tool_text_safe(justification, "gate_justification")
        self._assert_no_known_lesson_repeat(run_id, justification, "gate_justification")
        runtime_contract, *_ = self._load_contracts()
        if gate_name not in runtime_contract["gates"]:
            raise ValueError(f"unknown_gate:{gate_name}")
        allowed_values = set(runtime_contract.get("allowed_gate_values", ALLOWED_GATE_VALUES))
        if value not in allowed_values:
            raise ValueError(f"invalid_gate_value:{value}")
        if value == "passed":
            if not justification.strip():
                raise ValueError("gate_requires_justification")
            if not evidence:
                raise ValueError("gate_requires_evidence")
            self._assert_gate_evidence_matches(run_id, gate_name, evidence)
        state = self.read_state(run_id)
        state["gate_status"][gate_name] = value
        self.write_state(run_id, state)
        self.log_decision(run_id, "gate_updated", {
            "gate": gate_name,
            "value": value,
            "actor": actor,
            "justification": justification,
            "evidence": evidence or [],
        }, state)
        self.hooks.fire("on_gate_set", run_id=run_id, gate_name=gate_name, value=value, actor=actor, justification=justification, state=state)
        return state

    def evaluate_claim(self, run_id: str, claim_name: str, evidence: list = None,
                       actor: str = "orchestrator") -> dict:
        self._assert_actor(actor, "can_evaluate_claim")
        _, _, claim_policy, _, evidence_policy, *_ = self._load_contracts()
        state = self.read_state(run_id)
        rule = claim_policy["claims"].get(claim_name)
        if not rule:
            raise ValueError(f"unknown_claim:{claim_name}")

        evidence = evidence or []
        self._assert_ref_list_safe(evidence, "evidence_ref")
        records_by_claim = {}
        for ref in evidence:
            record = self._validate_evidence_record(run_id, ref)
            if record["claim"] not in rule["required_evidence"]:
                raise ValueError(
                    f"claim_invalid:evidence_claim_mismatch:{claim_name}:{record['claim']}"
                )
            records_by_claim[record["claim"]] = record
        missing = [e for e in rule["required_evidence"] if e not in records_by_claim]
        state.setdefault("claim_status", {})
        state["evidence_refs"] = _unique(state["evidence_refs"] + evidence)

        if missing:
            state["blocked_claims"] = _unique(state["blocked_claims"] + [claim_name])
            state["active_claims"] = [c for c in state["active_claims"] if c != claim_name]
            state["claim_status"][claim_name] = {
                "status": "blocked",
                "missing_evidence": missing,
                "policy": rule["on_missing"],
            }
            # Derived from aggregated blocked_claims, not from last-evaluated claim
            state["gate_status"]["claim_gate"] = (
                "passed" if not state["blocked_claims"] else "failed"
            )
            self.write_state(run_id, state)
            self.log_decision(run_id, "claim_blocked", {
                "claim": claim_name,
                "missing_evidence": missing,
                "policy": rule["on_missing"],
                "actor": actor,
            }, state)
            self.hooks.fire("on_claim_evaluated", run_id=run_id, claim_name=claim_name, outcome="blocked", evidence=evidence, state=state)
            self.record_lesson(
                run_id,
                context=f"Claim {claim_name} was evaluated without required evidence.",
                attempted_action=f"evaluate_claim:{claim_name}",
                outcome="blocked",
                failure_reason=f"Missing evidence: {','.join(missing)}",
                do_not_repeat=f"evaluate {claim_name} without {','.join(missing)}",
                recommended_action=(
                    f"Provide verifiable evidence records for {','.join(missing)} "
                    f"before evaluating {claim_name}."
                ),
                applies_when=[claim_name] + missing,
                severity="high",
                source="auto:claim_blocked",
                stage=state["current_stage"],
            )
            return {"outcome": "blocked", "missing": missing}

        self._assert_claim_semantics(run_id, claim_name, records_by_claim)
        state["active_claims"] = _unique(state["active_claims"] + [claim_name])
        state["blocked_claims"] = [c for c in state["blocked_claims"] if c != claim_name]
        state["claim_status"][claim_name] = {"status": "accepted", "evidence": evidence}
        # Derived from aggregated blocked_claims, not from last-evaluated claim
        state["gate_status"]["claim_gate"] = (
            "passed" if not state["blocked_claims"] else "failed"
        )
        self.write_state(run_id, state)
        self.log_decision(run_id, "claim_accepted",
                          {"claim": claim_name, "evidence": evidence, "actor": actor}, state)
        self.hooks.fire("on_claim_evaluated", run_id=run_id, claim_name=claim_name, outcome="accepted", evidence=evidence, state=state)
        return {"outcome": "accepted", "evidence": evidence}

    def _assert_terminal_confirmation(self, terminal_stage: str,
                                      confirmation: str = "",
                                      confirmed_by: str = "") -> None:
        runtime_contract, _, _, _, _, _, _, _, prompt_contract, _ = self._load_contracts()
        policy = prompt_contract["terminal_confirmation"]
        assert_terminal_confirmation(
            policy,
            confirmation=confirmation,
            confirmed_by=confirmed_by,
            terminal_stage=terminal_stage,
            terminal_stages=set(runtime_contract["terminal_stages"]),
        )

    def _terminate_run(self, run_id: str, terminal_stage: str,
                       reason: str, evidence: list = None,
                       actor: str = "orchestrator",
                       confirmation: str = "",
                       confirmed_by: str = "") -> dict:
        self._assert_actor(actor, "can_terminate")
        self._assert_tool_text_safe(reason, "terminal_reason")
        self._assert_no_known_lesson_repeat(run_id, reason, "terminal_reason")
        self._assert_ref_list_safe(evidence or [], "evidence_ref")
        self._assert_terminal_confirmation(terminal_stage, confirmation, confirmed_by)
        state = self.read_state(run_id)
        if state["status"] != "running":
            raise ValueError("run_already_terminal")
        self.advance_run(run_id, terminal_stage, evidence=evidence or [], actor=actor)
        state = self.read_state(run_id)
        self.log_decision(run_id, "run_terminated", {
            "stage": terminal_stage,
            "reason": reason,
            "evidence": evidence or [],
            "actor": actor,
            "confirmation": confirmation,
            "confirmed_by": confirmed_by,
        }, state)
        self.hooks.fire("on_run_terminal", run_id=run_id, terminal_stage=terminal_stage, reason=reason, state=state)
        if terminal_stage == "NEEDS_USER_INPUT":
            self.hooks.fire("on_user_input_requested", run_id=run_id, reason=reason, state=state)
        return self.read_state(run_id)

    def block_run(self, run_id: str, reason: str, evidence: list = None,
                  actor: str = "orchestrator") -> dict:
        return self._terminate_run(run_id, "BLOCKED", reason, evidence, actor)

    def request_input(self, run_id: str, reason: str, evidence: list = None,
                      actor: str = "orchestrator") -> dict:
        return self._terminate_run(run_id, "NEEDS_USER_INPUT", reason, evidence, actor)

    def fail_run(self, run_id: str, reason: str, evidence: list = None,
                 actor: str = "orchestrator", confirmation: str = "",
                 confirmed_by: str = "") -> dict:
        return self._terminate_run(
            run_id, "ERROR", reason, evidence, actor, confirmation, confirmed_by
        )

    def not_answerable_run(self, run_id: str, reason: str, evidence: list = None,
                           actor: str = "orchestrator", confirmation: str = "",
                           confirmed_by: str = "") -> dict:
        return self._terminate_run(
            run_id, "NOT_ANSWERABLE", reason, evidence, actor, confirmation, confirmed_by
        )

    def complete_run(self, run_id: str,
                     evidence: list = None, artifacts: list = None,
                     actor: str = "orchestrator", confirmation: str = "",
                     confirmed_by: str = "") -> dict:
        self._assert_actor(actor, "can_complete")
        self._assert_terminal_confirmation("CLOSE", confirmation, confirmed_by)
        if artifacts is None:
            artifacts = ["test-report.md", "final-report.md"]
        self._assert_ref_list_safe(artifacts, "artifact_ref")
        self._assert_ref_list_safe(evidence or [], "evidence_ref")
        state = self.read_state(run_id)
        if state["status"] != "running":
            raise ValueError("run_already_terminal")
        if state["current_stage"] != "QA":
            raise ValueError("complete_requires_qa_stage")
        if state["blocked_claims"]:
            raise ValueError("blocked_claims_prevent_close")
        self._assert_artifacts_valid(run_id, artifacts, actor)
        self.advance_run(run_id, "CLOSE", artifacts=artifacts, evidence=evidence or [], actor=actor)
        state = self.read_state(run_id)
        self.log_decision(run_id, "run_closed", {
            "actor": actor,
            "artifacts": artifacts,
            "evidence": evidence or [],
            "confirmation": confirmation,
            "confirmed_by": confirmed_by,
        }, state)
        return self.read_state(run_id)

    def list_runs(self) -> list:
        try:
            return sorted(d.name for d in self.runs_dir.iterdir() if d.is_dir())
        except FileNotFoundError:
            return []

    def show_run(self, run_id: str) -> dict:
        return self.read_state(run_id)


def create_runtime(root_dir=None, hooks=None) -> HarnessRuntime:
    runtime = HarnessRuntime(root_dir, hooks=hooks)
    runtime.runs_dir.mkdir(parents=True, exist_ok=True)
    return runtime
