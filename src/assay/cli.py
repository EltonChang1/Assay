"""Only implemented development commands are exposed; no model dispatch exists."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from assay import __version__
from assay.config import state_directory
from assay.contracts.experiment import ExperimentConfig
from assay.diagnostics import doctor
from assay.execution.docker import WorkerUnavailableError


def _print(value: Any) -> None:
    print(json.dumps(value, indent=2, sort_keys=True, default=str))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Assay development foundation")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)
    diagnostic = commands.add_parser("doctor", help="Check offline setup; never calls models")
    diagnostic.add_argument("--require-docker", action="store_true")
    commands.add_parser(
        "milestone", help="Run private development regressions from a source checkout"
    )
    dataset = commands.add_parser("dataset", help="Generate or validate public synthetic fixtures")
    datasets = dataset.add_subparsers(dest="dataset_command", required=True)
    build = datasets.add_parser("build")
    build.add_argument("--output", type=Path)
    build.add_argument("--seed", type=int, default=0)
    build.add_argument(
        "--variant", choices=("base", "equal_amount", "insufficient", "historical"), default="base"
    )
    validate = datasets.add_parser("validate")
    validate.add_argument("--manifest", type=Path, required=True)
    spec = commands.add_parser(
        "spec", help="Validate development configuration; does not run models"
    )
    specs = spec.add_subparsers(dest="spec_command", required=True)
    spec_validate = specs.add_parser("validate")
    spec_validate.add_argument("--manifest", type=Path, required=True)
    worker = commands.add_parser("worker", help="Build or smoke-test the pinned Docker worker")
    workers = worker.add_subparsers(dest="worker_command", required=True)
    workers.add_parser("build")
    workers.add_parser("smoke")
    query = commands.add_parser(
        "query", help="Development SQL through Docker with captured evidence"
    )
    query.add_argument("--manifest", type=Path, required=True)
    query.add_argument("--sql", required=True)
    receipt = commands.add_parser("receipt", help="Read a host execution receipt by ID")
    receipt.add_argument("--id", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "doctor":
            result = doctor()
            _print(result)
            return int(
                not result["offline_ready"] or (args.require_docker and not result["docker_ready"])
            )
        if args.command == "milestone":
            # Never import private scoring code into the installed runtime package.
            root = Path(__file__).resolve().parents[2]
            if not (root / "evaluator" / "__main__.py").is_file():
                raise ValueError(
                    "Milestone requires a source checkout and uv sync with dev dependencies"
                )
            completed = subprocess.run([sys.executable, "-m", "evaluator"], cwd=root, check=False)
            return completed.returncode
        if args.command == "spec":
            config = ExperimentConfig.model_validate_json(args.manifest.read_text(encoding="utf-8"))
            _print({"valid": True, "config": config.model_dump(mode="json"), "dispatched": False})
            return 0
        if args.command == "worker":
            if args.worker_command == "build":
                from assay.execution.docker import build_worker

                source = Path(__file__).resolve().parents[2]
                if not (source / "sandbox" / "Dockerfile").is_file():
                    raise ValueError("Worker build requires a source checkout with sandbox sources")
                image = build_worker(source)
                _print({"image": image.model_dump(mode="json"), "isolation_validation": "pending"})
                return 0
            from assay.datasets import (
                generate_sales_fixture,
                validate_public_bundle,
                write_public_bundle,
            )
            from assay.gateway.service import execute_query

            fixture = generate_sales_fixture()
            bundle = state_directory() / "worker-smoke" / fixture.public_task.task_id
            if bundle.exists():
                if validate_public_bundle(bundle) != fixture.snapshot:
                    raise ValueError("Existing smoke input differs from current fixture")
            else:
                write_public_bundle(fixture, bundle)
            outcome = execute_query(
                "SELECT SUM(amount_minor * 0.01) AS revenue_usd "
                "FROM orders WHERE status = 'settled'",
                bundle,
            )
            success = (
                outcome.result is not None
                and outcome.result.row_count == 1
                and outcome.result.rows[0][0].type == "decimal"
                and outcome.result.rows[0][0].value == "200.00"
            )
            _print(
                {
                    "provisioning_smoke_passed": success,
                    "receipt": outcome.receipt.model_dump(mode="json"),
                }
            )
            return int(not success)
        if args.command == "query":
            from assay.gateway.service import execute_query

            path = args.manifest
            bundle = path.parent if path.name == "manifest.json" else path
            outcome = execute_query(args.sql, bundle)
            _print(
                {
                    "receipt": outcome.receipt.model_dump(mode="json"),
                    "columns": [column.model_dump(mode="json") for column in outcome.result.columns]
                    if outcome.result is not None
                    else None,
                    "preview_rows": [
                        [cell.model_dump(mode="json") for cell in row]
                        for row in outcome.result.rows[:20]
                    ]
                    if outcome.result is not None
                    else None,
                }
            )
            return int(outcome.receipt.status != "success")
        if args.command == "receipt":
            from assay.evidence.store import EvidenceStore

            receipt = EvidenceStore(state_directory() / "evidence").get_execution(args.id)
            _print(receipt.model_dump(mode="json"))
            return 0
        if args.command == "dataset":
            from assay.datasets import (
                generate_sales_fixture,
                validate_public_bundle,
                write_public_bundle,
            )

            if args.dataset_command == "build":
                fixture = generate_sales_fixture(seed=args.seed, variant=args.variant)
                output = args.output or state_directory() / "datasets" / fixture.public_task.task_id
                snapshot = write_public_bundle(fixture, output)
                _print(
                    {
                        "public_bundle": str(output.resolve()),
                        "snapshot": snapshot.model_dump(mode="json"),
                    }
                )
            else:
                path = args.manifest
                bundle = path.parent if path.name == "manifest.json" else path
                snapshot = validate_public_bundle(bundle)
                _print({"valid": True, "snapshot": snapshot.model_dump(mode="json")})
            return 0
    except (ValueError, ValidationError, OSError, WorkerUnavailableError, KeyError) as exc:
        # Do not dump environment values or credentials when a public input is invalid.
        _print({"error": str(exc)})
        return 1
    return 2
