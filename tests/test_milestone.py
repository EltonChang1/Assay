import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from evaluator import run_milestone


@pytest.fixture(scope="module")
def milestone():
    return run_milestone()


def test_trusted_sql_mutations_and_valid_alternatives(milestone):
    assert milestone["passed"]
    assert milestone["checks_passed"] == milestone["checks_run"] == 10
    cases = {case["case_id"]: case for case in milestone["cases"]}
    assert query_value(cases["base.order_aggregation"]) == "200.00"
    assert query_value(cases["base.duplicated_join"]) == "340.00"
    assert cases["base.order_aggregation"]["score"]["correct"]
    assert not cases["base.duplicated_join"]["score"]["correct"]
    assert cases["base.distinct_amount"]["score"]["correct"]
    assert query_value(cases["equal_amount.order_aggregation"]) == "300.00"
    assert query_value(cases["equal_amount.distinct_amount"]) == "200.00"
    assert not cases["equal_amount.distinct_amount"]["score"]["correct"]
    for variant in ("base", "equal_amount"):
        for strategy in ("exists_filter", "grouped_item_join"):
            assert cases[f"{variant}.{strategy}"]["score"]["correct"]
    assert all(case["regression_passed"] for case in cases.values())


def query_value(case):
    # SQL multiplies integer cents by a DECIMAL literal; compare exact strings.
    return case["query_value"]


def test_milestone_labels_its_actual_validation_scope(milestone):
    assert milestone["model_calls"] == 0
    assert milestone["untrusted_execution_boundary_tested"] is False
    assert milestone["publication_boundary_tested"] is False
    assert "developer-authored SQL only" in milestone["validation_scope"]
    json.dumps(milestone)


def test_private_cli_runs_from_checkout_and_accepts_no_sql_input():
    root = Path(__file__).resolve().parents[1]
    env = {**os.environ, "PYTHONPATH": str(root / "src") + os.pathsep + str(root)}
    result = subprocess.run(
        [sys.executable, "-m", "evaluator"],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["passed"]
    rejected = subprocess.run(
        [sys.executable, "-m", "evaluator", "--sql", "SELECT 1"],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert rejected.returncode == 2
    assert "unrecognized arguments" in rejected.stderr
