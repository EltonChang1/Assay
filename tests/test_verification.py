"""Claim-to-cell binding and public-contract checks on genuine captured results."""

import shutil
from decimal import Decimal

import pytest
from phase3_support import (
    CORRECT_SQL,
    COUNT_SQL,
    DISTINCT_AMOUNT_SQL,
    DUPLICATED_SQL,
    SCOPE,
    digest,
    make_lab,
    make_report,
)

from assay.verification import required_check_keys, verify_report


def outcomes(bundle, slot="settled_revenue_usd"):
    return {
        check.name: check.outcome
        for check in bundle.checks
        if check.claim_slot_id in (slot, None) and check.check_class != "advisory"
    }


def host_passes(bundle):
    return all(
        check.outcome == "pass" for check in bundle.checks if check.check_class == "host_integrity"
    )


def checked(lab, *claims, **updates):
    report = make_report(lab, claims, **updates)
    return report, verify_report(report, lab.evidence)


def test_correct_order_aggregation_passes_every_mandatory_check(tmp_path, monkeypatch):
    lab = make_lab(tmp_path, monkeypatch)
    revenue = lab.query(CORRECT_SQL)
    count = lab.query(COUNT_SQL)
    assert revenue.result.rows[0][0].value == "200.00"
    report, bundle = checked(
        lab,
        lab.claim_input(revenue),
        lab.claim_input(count, slot="settled_order_count", column="order_count"),
    )
    assert bundle.report_sha256 == digest(report)
    assert bundle.report_revision_id == report.revision_id
    mandatory = [check for check in bundle.checks if check.check_class != "advisory"]
    assert {check.outcome for check in mandatory} == {"pass"}
    assert {
        (check.check_class, check.name, check.claim_slot_id) for check in mandatory
    } == required_check_keys(report)
    assert all(check.input_hashes[0] == bundle.report_sha256 for check in bundle.checks)
    advisory = [check for check in bundle.checks if check.check_class == "advisory"]
    assert advisory and all(check.limitations for check in advisory)


@pytest.mark.parametrize(
    "sql",
    [
        f"SELECT SUM(o.amount_minor) / 100 AS revenue_usd FROM orders AS o WHERE {SCOPE}",
        "SELECT SUM(o.amount_minor * 0.01) AS revenue_usd FROM orders o "
        f"WHERE {SCOPE} AND EXISTS "
        "(SELECT 1 FROM order_items i WHERE i.order_id = o.order_id)",
        "WITH item_orders AS (SELECT order_id FROM order_items GROUP BY order_id) "
        "SELECT SUM(o.amount_minor * 0.01) AS revenue_usd FROM orders o "
        f"JOIN item_orders i USING (order_id) WHERE {SCOPE}",
        "SELECT SUM(o.amount_minor * 0.01) AS revenue_usd FROM orders o LEFT JOIN "
        "(SELECT DISTINCT order_id FROM order_items) i ON o.order_id = i.order_id "
        f"WHERE {SCOPE}",
    ],
    ids=["outer_division", "exists", "grouped_cte_join", "distinct_left_join"],
)
def test_alternative_correct_queries_are_accepted(tmp_path, monkeypatch, sql):
    lab = make_lab(tmp_path, monkeypatch)
    outcome = lab.query(sql)
    assert Decimal(str(outcome.result.rows[0][0].value)) == Decimal("200")
    _, bundle = checked(lab, lab.claim_input(outcome))
    assert set(outcomes(bundle).values()) == {"pass"}, outcomes(bundle)


def test_authentic_duplicated_join_passes_integrity_and_binding_but_fails_grain(
    tmp_path, monkeypatch
):
    lab = make_lab(tmp_path, monkeypatch)
    outcome = lab.query(DUPLICATED_SQL)
    assert outcome.result.rows[0][0].value == "340.00"
    _, bundle = checked(lab, lab.claim_input(outcome))
    assert host_passes(bundle)
    result = outcomes(bundle)
    assert result["cell_binding"] == "pass"
    assert result["query_grain"] == "fail"
    assert result["query_metric"] == "pass"


def test_claim_value_must_come_from_its_designated_cell(tmp_path, monkeypatch):
    lab = make_lab(tmp_path, monkeypatch)
    genuine = lab.query(CORRECT_SQL)
    _, bundle = checked(lab, lab.claim_input(genuine, "340.00"))
    assert host_passes(bundle)
    assert outcomes(bundle)["cell_binding"] == "fail"

    both = lab.query(
        f"SELECT SUM(o.amount_minor * 0.01) AS revenue_usd, COUNT(*) AS order_count "
        f"FROM orders o WHERE {SCOPE}"
    )
    _, bundle = checked(lab, lab.claim_input(both, "200.00", column="order_count"))
    assert outcomes(bundle)["cell_binding"] == "fail"
    for row, column in ((1, "revenue_usd"), (0, "missing_column")):
        _, bundle = checked(lab, lab.claim_input(both, "200.00", column=column, row=row))
        assert outcomes(bundle)["cell_binding"] == "fail"


def test_identical_number_from_an_unrelated_metric_fails_the_metric_contract(tmp_path, monkeypatch):
    lab = make_lab(tmp_path, monkeypatch)
    outcome = lab.query(
        f"SELECT MAX(o.amount_minor) / 50 AS revenue_usd FROM orders o WHERE {SCOPE}"
    )
    assert Decimal(str(outcome.result.rows[0][0].value)) == Decimal("200")
    _, bundle = checked(lab, lab.claim_input(outcome))
    result = outcomes(bundle)
    assert result["cell_binding"] == "pass"
    assert result["query_metric"] == "fail"


def test_equal_value_counterexample_defeats_sum_distinct_amount(tmp_path, monkeypatch):
    lab = make_lab(tmp_path, monkeypatch, variant="equal_amount")
    correct = lab.query(CORRECT_SQL)
    shortcut = lab.query(DISTINCT_AMOUNT_SQL)
    assert correct.result.rows[0][0].value == "300.00"
    assert shortcut.result.rows[0][0].value == "200.00"
    _, bundle = checked(lab, lab.claim_input(correct))
    assert set(outcomes(bundle).values()) == {"pass"}
    _, bundle = checked(lab, lab.claim_input(shortcut))
    assert outcomes(bundle)["cell_binding"] == "pass"
    assert outcomes(bundle)["query_metric"] == "fail"


@pytest.mark.parametrize(
    ("sql", "check"),
    [
        (f"SELECT SUM(o.amount_minor) AS revenue_usd FROM orders o WHERE {SCOPE}", "query_units"),
        (
            "SELECT SUM(o.amount_minor * 0.01) AS revenue_usd FROM orders o "
            "WHERE o.currency = 'USD' AND o.occurred_at >= TIMESTAMPTZ '2026-01-01 00:00:00+00' "
            "AND o.occurred_at < TIMESTAMPTZ '2026-04-01 00:00:00+00'",
            "query_population",
        ),
        (
            "SELECT SUM(o.amount_minor * 0.01) AS revenue_usd FROM orders o "
            "WHERE o.status = 'settled' AND o.currency = 'USD' "
            "AND o.occurred_at >= TIMESTAMPTZ '2026-01-01 00:00:00+00' "
            "AND o.occurred_at <= TIMESTAMPTZ '2026-04-01 00:00:00+00'",
            "query_population",
        ),
        (
            f"SELECT SUM(o.amount_minor * 0.01) AS revenue_usd FROM orders o WHERE {SCOPE} "
            "AND o.amount_minor > 2000",
            "query_population",
        ),
    ],
    ids=["cents_not_dollars", "missing_status", "inclusive_end", "extra_exclusion"],
)
def test_public_contract_deviations_fail_with_a_valid_binding(tmp_path, monkeypatch, sql, check):
    lab = make_lab(tmp_path, monkeypatch)
    outcome = lab.query(sql)
    _, bundle = checked(lab, lab.claim_input(outcome))
    assert outcomes(bundle)["cell_binding"] == "pass"
    assert outcomes(bundle)[check] == "fail"


@pytest.mark.parametrize(
    "sql",
    [
        f"SELECT revenue_usd FROM (SELECT SUM(o.amount_minor * 0.01) AS revenue_usd "
        f"FROM orders o WHERE {SCOPE}) AS t",
        "SELECT SUM(CASE WHEN o.status = 'settled' THEN o.amount_minor * 0.01 ELSE 0 END) "
        "AS revenue_usd FROM orders o WHERE o.currency = 'USD' "
        "AND o.occurred_at >= TIMESTAMPTZ '2026-01-01 00:00:00+00' "
        "AND o.occurred_at < TIMESTAMPTZ '2026-04-01 00:00:00+00'",
        f"SELECT SUM(o.amount_minor * 0.01) AS revenue_usd FROM orders o WHERE {SCOPE} "
        "GROUP BY o.currency",
    ],
    ids=["derived_table", "case_expression", "top_level_group"],
)
def test_unsupported_shapes_are_unknown_never_proof(tmp_path, monkeypatch, sql):
    lab = make_lab(tmp_path, monkeypatch)
    outcome = lab.query(sql)
    _, bundle = checked(lab, lab.claim_input(outcome))
    assert host_passes(bundle)
    result = outcomes(bundle)
    assert result["cell_binding"] == "pass"
    semantic = {result[name] for name in ("query_metric", "query_grain", "query_population")}
    assert "pass" not in semantic and "unknown" in semantic


def test_forged_cross_run_and_mismatched_references_fail_identity(tmp_path, monkeypatch):
    lab = make_lab(tmp_path, monkeypatch)
    genuine = lab.query(CORRECT_SQL)
    other_run = lab.query(CORRECT_SQL, run_id="run-other")
    duplicated = lab.query(DUPLICATED_SQL)
    forged = lab.claim_input(genuine).model_copy(update={"execution_id": "execution-forged"})
    cross_run = lab.claim_input(other_run)
    wrong_result = lab.claim_input(genuine, result_id=duplicated.receipt.result_id)
    for claim in (forged, cross_run, wrong_result):
        _, bundle = checked(lab, claim)
        assert outcomes(bundle)["evidence_identity"] == "fail"
        assert outcomes(bundle)["cell_binding"] == "fail"
        assert outcomes(bundle)["query_grain"] == "unknown"
    _, bundle = checked(lab, lab.claim_input(genuine, dependency_ids=("snapshot-unrelated",)))
    assert outcomes(bundle)["evidence_identity"] == "fail"


def test_changed_frozen_inputs_fail_and_missing_inputs_are_unknown(tmp_path, monkeypatch):
    lab = make_lab(tmp_path, monkeypatch)
    outcome = lab.query(CORRECT_SQL)
    frozen = lab.state / "evidence" / "inputs" / outcome.receipt.snapshot_manifest_sha256
    orders = frozen / "tables" / "orders.csv"
    original = orders.read_bytes()
    orders.write_bytes(original.replace(b"10000", b"10001"))
    _, bundle = checked(lab, lab.claim_input(outcome))
    assert outcomes(bundle)["evidence_identity"] == "fail"
    assert outcomes(bundle)["public_missingness"] == "unknown"
    shutil.rmtree(frozen)
    _, bundle = checked(lab, lab.claim_input(outcome))
    assert outcomes(bundle)["evidence_identity"] == "unknown"
    assert "pass" not in {outcomes(bundle)[name] for name in ("cell_binding", "query_grain")}


def test_insufficient_data_accepts_only_justified_abstention(tmp_path, monkeypatch):
    lab = make_lab(tmp_path, monkeypatch, variant="insufficient")
    outcome = lab.query(CORRECT_SQL)
    reason = "An eligible order amount is missing."
    _, bundle = checked(lab, lab.claim_input(outcome, abstention_reason=reason))
    result = outcomes(bundle)
    assert set(result.values()) == {"pass"}
    assert {check.applicability for check in bundle.checks if check.name == "cell_binding"} == {
        "not_applicable"
    }
    _, bundle = checked(lab, lab.claim_input(outcome))
    assert outcomes(bundle)["public_missingness"] == "fail"

    complete = make_lab(tmp_path / "complete", monkeypatch)
    answerable = complete.query(CORRECT_SQL)
    _, bundle = checked(complete, complete.claim_input(answerable, abstention_reason=reason))
    assert outcomes(bundle)["public_missingness"] == "fail"


def test_slot_contract_and_declared_slots_are_host_enforced(tmp_path, monkeypatch):
    lab = make_lab(tmp_path, monkeypatch)
    revenue = lab.query(CORRECT_SQL)
    count = lab.query(COUNT_SQL)
    mismatched = lab.claim_input(revenue, report_semantics="historical")
    with pytest.raises(ValueError, match="disagree"):
        make_report(lab, (mismatched,))
    _, bundle = checked(lab, mismatched, rendered_sha256="0" * 64)
    assert outcomes(bundle)["slot_contract"] == "fail"
    supporting_only = lab.claim_input(count, slot="settled_order_count", column="order_count")
    _, bundle = checked(lab, supporting_only, rendered_sha256="0" * 64)
    assert outcomes(bundle, "settled_order_count")["declared_slots"] == "fail"
    _, bundle = checked(
        lab, lab.claim_input(revenue), lab.claim_input(revenue), rendered_sha256="0" * 64
    )
    assert outcomes(bundle)["declared_slots"] == "fail"


def test_mutated_report_inputs_fail_report_contract(tmp_path, monkeypatch):
    lab = make_lab(tmp_path, monkeypatch)
    outcome = lab.query(CORRECT_SQL)
    other = make_lab(tmp_path / "other", monkeypatch, variant="equal_amount")
    _, bundle = checked(
        lab,
        lab.claim_input(outcome),
        snapshot=other.snapshot.model_copy(update={"task_id": lab.task.task_id}),
    )
    result = outcomes(bundle)
    assert result["report_contract"] == "fail"
    assert result["evidence_identity"] == "fail"
