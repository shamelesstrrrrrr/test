from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pydantic import ValidationError

from gamma_dinsar.config import load_task_config
from gamma_dinsar.executor import MockGammaExecutor
from gamma_dinsar.state import StateStore
from gamma_dinsar.workflow import run_workflow


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="gamma-dinsar")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate", help="validate a YAML task configuration")
    validate.add_argument("config", type=Path)

    run = subparsers.add_parser("run", help="run a task from the first stage")
    run.add_argument("config", type=Path)
    run.add_argument("--executor", choices=["mock"], default="mock")

    status = subparsers.add_parser("status", help="print the task state file")
    status.add_argument("config", type=Path)

    resume = subparsers.add_parser("resume", help="resume a task from a selected stage")
    resume.add_argument("config", type=Path)
    resume.add_argument("--from-stage", required=True)
    resume.add_argument("--executor", choices=["mock"], default="mock")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        config = load_task_config(args.config)
    except (OSError, ValidationError) as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return 2

    if args.command == "validate":
        print(f"valid configuration: {config.task_id}")
        return 0

    if args.command == "status":
        store = StateStore(config.output_dir, config.task_id)
        if not store.state_path.exists():
            print(f"state file not found: {store.state_path}", file=sys.stderr)
            return 1
        print(json.dumps(store.load_or_create().model_dump(mode="json"), indent=2))
        return 0

    executor = MockGammaExecutor(config.mock)

    if args.command == "run":
        state = run_workflow(config, executor)
    elif args.command == "resume":
        config.resume = True
        state = run_workflow(config, executor, from_stage=args.from_stage)
    else:
        parser.error(f"unsupported command: {args.command}")
        return 2

    failed = [name for name, record in state.stages.items() if record.status == "failed"]
    print(json.dumps(state.model_dump(mode="json"), indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
