#!/usr/bin/env python3
"""ForestVol Harness CLI entrypoint. Compatible with Python 3.8+."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from runtime import create_runtime, HarnessHooks, GitCommitHook  # noqa: E402
from eval_runner import run_evals   # noqa: E402


def _parse_list(value):
    # type: (str) -> list
    return [item.strip() for item in value.split(",") if item.strip()] if value else []


def _build_parser():
    # type: () -> argparse.ArgumentParser
    p = argparse.ArgumentParser(prog="harness", description="ForestVol Harness CLI")
    sub = p.add_subparsers(dest="command", required=True)

    # Helpers
    def _with_run(sp):
        sp.add_argument("run_id")

    def _with_run_and_evidence(sp):
        _with_run(sp)
        sp.add_argument("--evidence", default="")
        sp.add_argument("--actor", default="orchestrator")

    # Commands
    s = sub.add_parser("init");      _with_run(s)
    s = sub.add_parser("show");      _with_run(s)
    s = sub.add_parser("validate");  _with_run(s)
    s = sub.add_parser("list")
    s = sub.add_parser("eval")
    s.add_argument("--mode", choices=("offline", "live"), default="offline")
    s.add_argument("--update-fixtures", action="store_true")

    s = sub.add_parser("advance");   _with_run(s)
    s.add_argument("stage")
    s.add_argument("--artifacts", default="")
    s.add_argument("--evidence", default="")
    s.add_argument("--actor", default="orchestrator")

    s = sub.add_parser("gate");      _with_run(s)
    s.add_argument("gate_name")
    s.add_argument("value")
    s.add_argument("--actor", default="orchestrator")
    s.add_argument("--justification", default="")
    s.add_argument("--evidence", default="")

    s = sub.add_parser("claim");     _with_run(s)
    s.add_argument("claim_name")
    s.add_argument("--evidence", default="")
    s.add_argument("--actor", default="orchestrator")

    s = sub.add_parser("lesson-add"); _with_run(s)
    s.add_argument("--context", required=True)
    s.add_argument("--attempted-action", required=True)
    s.add_argument("--outcome", required=True)
    s.add_argument("--failure-reason", required=True)
    s.add_argument("--do-not-repeat", required=True)
    s.add_argument("--recommended-action", required=True)
    s.add_argument("--applies-when", required=True)
    s.add_argument("--severity", default="medium")
    s.add_argument("--source", default="manual")
    s.add_argument("--lesson-id", default="")

    s = sub.add_parser("lesson-list")
    s.add_argument("run_id", nargs="?")
    s.add_argument("--global", dest="include_global", action="store_true")

    for cmd in ("block", "input", "fail", "not-answerable"):
        s = sub.add_parser(cmd);    _with_run_and_evidence(s)
        s.add_argument("reason")
        if cmd in ("fail", "not-answerable"):
            s.add_argument("--confirmation", default="")
            s.add_argument("--confirmed-by", default="")

    s = sub.add_parser("complete");  _with_run(s)
    s.add_argument("--artifacts", default="")
    s.add_argument("--evidence", default="")
    s.add_argument("--actor", default="orchestrator")
    s.add_argument("--confirmation", default="")
    s.add_argument("--confirmed-by", default="")

    return p


def main():
    # type: () -> None
    args = _build_parser().parse_args()
    
    root_dir = Path(".").resolve()
    hooks = HarnessHooks()
    # "uno que tire a git los cambios cuando pasan los test" -> GitCommitHook
    hooks.register("on_test_pass", GitCommitHook(root_dir).on_test_pass)
    rt = create_runtime(root_dir, hooks=hooks)
    
    cmd = args.command

    if cmd == "init":
        result = rt.init_run(args.run_id)

    elif cmd == "advance":
        result = rt.advance_run(
            args.run_id, args.stage,
            artifacts=_parse_list(args.artifacts),
            evidence=_parse_list(args.evidence),
            actor=args.actor,
        )

    elif cmd == "gate":
        result = rt.set_gate(
            args.run_id, args.gate_name, args.value,
            actor=args.actor,
            justification=args.justification,
            evidence=_parse_list(args.evidence),
        )

    elif cmd == "claim":
        result = rt.evaluate_claim(
            args.run_id, args.claim_name,
            evidence=_parse_list(args.evidence),
            actor=args.actor,
        )

    elif cmd == "lesson-add":
        result = rt.record_lesson(
            args.run_id,
            context=args.context,
            attempted_action=args.attempted_action,
            outcome=args.outcome,
            failure_reason=args.failure_reason,
            do_not_repeat=args.do_not_repeat,
            recommended_action=args.recommended_action,
            applies_when=_parse_list(args.applies_when),
            severity=args.severity,
            source=args.source,
            lesson_id=args.lesson_id or None,
        )

    elif cmd == "lesson-list":
        result = rt.list_lessons(args.run_id, include_global=args.include_global)

    elif cmd == "block":
        result = rt.block_run(
            args.run_id, args.reason,
            evidence=_parse_list(args.evidence),
            actor=args.actor,
        )

    elif cmd == "input":
        result = rt.request_input(
            args.run_id, args.reason,
            evidence=_parse_list(args.evidence),
            actor=args.actor,
        )

    elif cmd == "fail":
        result = rt.fail_run(
            args.run_id, args.reason,
            evidence=_parse_list(args.evidence),
            actor=args.actor,
            confirmation=args.confirmation,
            confirmed_by=args.confirmed_by,
        )

    elif cmd == "not-answerable":
        result = rt.not_answerable_run(
            args.run_id, args.reason,
            evidence=_parse_list(args.evidence),
            actor=args.actor,
            confirmation=args.confirmation,
            confirmed_by=args.confirmed_by,
        )

    elif cmd == "complete":
        arts = _parse_list(args.artifacts) or ["test-report.md", "final-report.md"]
        result = rt.complete_run(
            args.run_id,
            evidence=_parse_list(args.evidence),
            artifacts=arts,
            actor=args.actor,
            confirmation=args.confirmation,
            confirmed_by=args.confirmed_by,
        )

    elif cmd == "show":
        result = rt.show_run(args.run_id)

    elif cmd == "validate":
        result = rt.validate_run(args.run_id)

    elif cmd == "list":
        result = rt.list_runs()

    elif cmd == "eval":
        result = run_evals(
            Path(".").resolve(),
            mode=args.mode,
            update_fixtures=args.update_fixtures,
        )
        if result["overall_result"] not in {"pass", "skip"}:
            print(json.dumps(result, indent=2))
            sys.exit(1)
        else:
            # Fire the hook for tests passing
            rt.hooks.fire("on_test_pass", run_id="N/A", result=result)

    else:
        print("unknown_command", file=sys.stderr)
        sys.exit(1)

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
