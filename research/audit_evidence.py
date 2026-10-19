"""Reconcile paper evidence without model calls or changes to runtime state.

Run with the locked project interpreter. The optional local pilot is read-only;
its requests, responses, paths, and credentials are never copied to the report.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def audit(pilot_dir: Path | None, junit: Path) -> dict:
    saved = read_json(ROOT / "research/validation/current-validation.json")
    mismatches = [
        name
        for name, expected in saved["source_sha256"].items()
        if not (ROOT / name).is_file() or digest(ROOT / name) != expected
    ]
    # The trusted milestone uses only fixed developer-authored SQL, never actor SQL.
    process = subprocess.run(
        [sys.executable, "-m", "evaluator"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    observed = json.loads(process.stdout)
    original = read_json(ROOT / "research/validation/milestone.json")
    if observed != original:
        raise ValueError("fresh numerical milestone differs from saved evidence")
    suites = ET.parse(junit).getroot().findall("testsuite")
    counts = {
        key: sum(int(suite.attrib[key]) for suite in suites)
        for key in ("tests", "failures", "errors", "skipped")
    }
    counts["passed"] = counts["tests"] - sum(
        counts[key] for key in ("failures", "errors", "skipped")
    )
    if counts["failures"] or counts["errors"]:
        raise ValueError("fresh test evidence contains failures or errors")
    pilot: dict = {"local_ledger_checked": False}
    if pilot_dir is not None:
        summary = read_json(ROOT / "research/validation/development-pilot.json")
        manifest = read_json(pilot_dir / "manifest.json")
        results = read_json(pilot_dir / "results.json")
        for name in ("manifest", "results"):
            if digest(pilot_dir / (name + ".json")) != summary[name + "_sha256"]:
                raise ValueError(f"pilot {name} hash mismatch")
        episodes = results["episodes"]
        assigned = {a["episode_id"] for a in manifest["assignments"]}
        # EpisodeRecord assigns its own episode_id; the frozen assignment is run_id.
        if len(episodes) != len(assigned) or {e["run_id"] for e in episodes} != assigned:
            raise ValueError("assignment accounting is incomplete or duplicated")
        by_run = {e["run_id"]: e for e in episodes}
        for assignment in manifest["assignments"]:
            if any(
                by_run[assignment["episode_id"]][key] != assignment[key]
                for key in ("arm", "regime", "variant", "snapshot_id")
            ):
                raise ValueError("assignment treatment or input identity mismatch")
        connection = sqlite3.connect(
            (pilot_dir / "budget.sqlite3").resolve().as_uri() + "?mode=ro", uri=True
        )
        try:
            rows = connection.execute(
                "SELECT role,status,input_tokens,output_tokens,actual_usd,response_json FROM calls"
            ).fetchall()
        finally:
            connection.close()
        inputs = sum(row[2] or 0 for row in rows)
        outputs = sum(row[3] or 0 for row in rows)
        settled = sum((Decimal(row[4] or "0") for row in rows), Decimal(0))
        cached = sum(
            json.loads(row[5])["usage"]["input_tokens_details"]["cached_tokens"]
            for row in rows
            if row[5] is not None
        )
        pilot = {
            "local_ledger_checked": True,
            "manifest_sha256": digest(pilot_dir / "manifest.json"),
            "results_sha256": digest(pilot_dir / "results.json"),
            "assigned_episodes": len(assigned),
            "completed_assignments": len(episodes),
            "status_counts": dict(Counter(e["status"] for e in episodes)),
            "release_known": sum(e["release_known"] for e in episodes),
            "releases": sum(e["released"] for e in episodes),
            "analyst_calls": sum(row[0] == "analyst" for row in rows),
            "oversight_calls": sum(row[0] == "oversight" for row in rows),
            "uncertain_calls": sum(row[1] != "settled" for row in rows),
            "input_tokens": inputs,
            "output_tokens": outputs,
            "cached_input_tokens": cached,
            "journal_uncached_settlement_usd": str(settled),
        }
        for name, value in pilot.items():
            if name in summary and (
                Decimal(value) != Decimal(summary[name])
                if name.endswith("_usd")
                else value != summary[name]
            ):
                raise ValueError(f"pilot aggregate mismatch: {name}")
        if (
            settled
            != (Decimal(inputs) * Decimal("0.75") + Decimal(outputs) * Decimal("4.50")) / 1_000_000
        ):
            raise ValueError("journal token-cost arithmetic mismatch")
    inventory = {
        path.relative_to(ROOT).as_posix(): digest(path)
        for folder in (
            "src",
            "sandbox",
            "evaluator",
            "tests",
            "research",
            "docs",
            "benchmark",
            "experiment_specs",
            ".github",
        )
        for path in sorted((ROOT / folder).rglob("*"))
        if path.is_file()
        and "__pycache__" not in path.parts
        and path.suffix in {".py", ".md", ".toml", ".yml", ".json"}
        and "validation" not in path.parts
    }
    inventory.update(
        {
            path.name: digest(path)
            for path in sorted(ROOT.iterdir())
            if path.is_file()
            and (
                path.suffix in {".md", ".toml", ".lock"}
                or path.name in {".python-version", ".gitignore", ".gitattributes"}
            )
        }
    )
    return {
        "schema_version": "assay-paper-evidence-audit-1.0",
        "audited_at_utc": datetime.now(UTC).isoformat(),
        "historical_validation_source_files": len(saved["source_sha256"]),
        "historical_validation_source_mismatches": mismatches,
        "numerical_milestone_exact_match": True,
        "fresh_pytest": counts,
        "fresh_junit_sha256": digest(junit),
        "docker_retested": False,
        "docker_note": "Engine unavailable; historical enabled results retained separately.",
        "new_paid_calls": 0,
        "pilot": pilot,
        "reviewed_tree_sha256": inventory,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pilot-dir", type=Path)
    parser.add_argument(
        "--junit", type=Path, default=ROOT / "research/validation/repository-review-junit.xml"
    )
    args = parser.parse_args()
    result = audit(args.pilot_dir, args.junit)
    target = ROOT / "research/validation/repository-review.json"
    target.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {key: value for key, value in result.items() if key != "reviewed_tree_sha256"}, indent=2
        )
    )


if __name__ == "__main__":
    main()
