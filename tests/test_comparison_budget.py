"""Offline cumulative admission checks; no credential, provider, or Docker call."""

import hashlib
import json
from dataclasses import replace
from decimal import Decimal

import pytest

from research.comparison_budget import CumulativeJournal, FrozenConfig
from research.run_pilot import BudgetDenied, BudgetJournal, PilotStopped, UncertainCall

CONFIG = FrozenConfig()
MANIFEST = "a" * 64


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def payload(config=CONFIG):
    return encoded({"model": config.model, "max_output_tokens": config.max_output, "input": []})


def response(inputs=100, outputs=20):
    return {
        "model": CONFIG.model,
        "usage": {"input_tokens": inputs, "output_tokens": outputs},
        "output": [],
    }


def make_parent(tmp_path, *, calls=1, inputs=214_404):
    directory = tmp_path / "research" / "parent"
    directory.mkdir(parents=True)
    manifest = {
        "model": CONFIG.model,
        "cost_cap_usd": "15.00",
        "input_price_per_million_usd": "0.75",
        "output_price_per_million_usd": "4.50",
        "reservation_input_tokens": 400_000,
        "max_output_tokens": 2048,
    }
    raw = encoded(manifest)
    manifest_sha = hashlib.sha256(raw).hexdigest()
    (directory / "manifest.json").write_bytes(raw)
    (directory / "manifest.sha256").write_text(manifest_sha + "\n", encoding="ascii")
    parent = BudgetJournal(directory / "budget.sqlite3")
    for index in range(calls):
        call = parent.reserve(f"parent-{index}", "analyst", payload())
        parent.settle(call, response(inputs, 0))
    summary = parent.totals()
    parent.close()
    (directory / "results.json").write_bytes(
        encoded(
            {
                "complete": True,
                "manifest_sha256": manifest_sha,
                "budget": summary,
            }
        )
    )
    return directory, directory.parent / "child" / "budget.sqlite3"


def test_imports_parent_spending_and_persists_exact_request_response_before_reopen(tmp_path):
    parent, path = make_parent(tmp_path)
    before = {p.name: p.read_bytes() for p in parent.iterdir()}
    with CumulativeJournal(path, parent, MANIFEST, CONFIG) as journal:
        assert Decimal(journal.totals()["remaining_usd"]) == Decimal("14.839197")
        call = journal.reserve("ep", "oversight", payload())
        assert journal.halted
        assert Decimal(journal.totals()["committed_cost_upper_usd"]) == Decimal("0.470019")
        usage = journal.settle(call, response())
        assert usage.input_tokens == 100 and not journal.halted
        saved = journal.db.execute("SELECT request_json,response_json FROM calls").fetchone()
        assert saved == (payload(), encoded(response()))
    with CumulativeJournal(path, parent, MANIFEST, CONFIG) as reopened:
        assert reopened.totals()["call_count"] == 1
        assert reopened.totals()["cumulative_call_count"] == 2
        assert Decimal(reopened.totals()["committed_cost_upper_usd"]) == Decimal("0.160968")
    assert before == {p.name: p.read_bytes() for p in parent.iterdir()}


def test_cumulative_cap_denies_before_reservation_or_dispatch(tmp_path):
    parent, path = make_parent(tmp_path, calls=49, inputs=400_000)
    with CumulativeJournal(path, parent, MANIFEST, CONFIG) as journal:
        assert Decimal(journal.totals()["parent_cost_upper_usd"]) == Decimal("14.7")
        with pytest.raises(BudgetDenied, match="cumulative_experiment_dollar_cap"):
            journal.reserve("ep", "analyst", payload())
        assert journal.totals()["call_count"] == 0


def test_summary_and_reviewer_corrections_share_six_call_allowance(tmp_path):
    parent, path = make_parent(tmp_path)
    with CumulativeJournal(path, parent, MANIFEST, CONFIG) as journal:
        for _ in range(CONFIG.oversight_calls):
            journal.settle(journal.reserve("ep", "oversight", payload()), response())
        with pytest.raises(BudgetDenied, match="shared_role_call_limit"):
            journal.reserve("ep", "oversight", payload())
        # A new analyst call does not reset the review allowance or the cumulative dollars.
        journal.settle(journal.reserve("ep", "analyst", payload()), response())
        assert journal.totals()["call_count"] == 7


def test_actor_limit_is_frozen_independently_of_old_six_call_default(tmp_path):
    parent, path = make_parent(tmp_path)
    with CumulativeJournal(path, parent, MANIFEST, CONFIG) as journal:
        for _ in range(24):
            journal.settle(journal.reserve("ep", "analyst", payload()), response())
        with pytest.raises(BudgetDenied, match="shared_role_call_limit"):
            journal.reserve("ep", "analyst", payload())


def test_lineage_refuses_concurrency_and_a_different_child_manifest_or_configuration(tmp_path):
    parent, path = make_parent(tmp_path)
    with CumulativeJournal(path, parent, MANIFEST, CONFIG), pytest.raises(FileExistsError):
        CumulativeJournal(path, parent, MANIFEST, CONFIG)
    for alternate_path, manifest, config in (
        (path.parent.parent / "other" / "budget.sqlite3", MANIFEST, CONFIG),
        (path, "b" * 64, CONFIG),
        (path, MANIFEST, replace(CONFIG, oversight_calls=7)),
    ):
        with pytest.raises(PilotStopped, match="already claimed"):
            CumulativeJournal(alternate_path, parent, manifest, config)
    with CumulativeJournal(path, parent, MANIFEST, CONFIG):
        pass


def test_missing_or_replaced_child_cannot_reset_lineage(tmp_path):
    parent, path = make_parent(tmp_path)
    with CumulativeJournal(path, parent, MANIFEST, CONFIG):
        pass
    path.unlink()
    with pytest.raises(PilotStopped, match="missing"):
        CumulativeJournal(path, parent, MANIFEST, CONFIG)
    path.write_bytes(b"")
    with pytest.raises(PilotStopped, match="no intact identity"):
        CumulativeJournal(path, parent, MANIFEST, CONFIG)


def test_parent_mutation_prevents_next_reservation_and_reopen(tmp_path):
    parent, path = make_parent(tmp_path)
    with CumulativeJournal(path, parent, MANIFEST, CONFIG) as journal:
        results = parent / "results.json"
        original = results.read_bytes()
        results.write_bytes(original + b"\n")
        with pytest.raises(PilotStopped, match="parent evidence changed"):
            journal.reserve("ep", "analyst", payload())
        assert journal.totals()["call_count"] == 0
    with pytest.raises(PilotStopped, match="already claimed"):
        CumulativeJournal(path, parent, MANIFEST, CONFIG)


@pytest.mark.parametrize(
    "changed",
    [
        {},
        {"usage": None},
        {"usage": {"input_tokens": True, "output_tokens": 1}},
        {"usage": {"input_tokens": 400_001, "output_tokens": 1}},
        {"usage": {"input_tokens": 1, "output_tokens": 2049}},
        {"model": "unpriced-model"},
    ],
)
def test_unknown_usage_retains_reservation_across_reopen_and_blocks_dispatch(tmp_path, changed):
    parent, path = make_parent(tmp_path)
    with CumulativeJournal(path, parent, MANIFEST, CONFIG) as journal:
        call = journal.reserve("ep", "analyst", payload())
        malformed = response() | changed if changed else {}
        with pytest.raises(UncertainCall, match="invalid_or_missing_usage"):
            journal.settle(call, malformed)
        assert journal.halted
        assert json.loads(journal.db.execute("SELECT response_json FROM calls").fetchone()[0]) == (
            malformed
        )
    with CumulativeJournal(path, parent, MANIFEST, CONFIG) as journal:
        assert Decimal(journal.totals()["child_unreconciled_reserved_usd"]) == Decimal("0.309216")
        with pytest.raises(UncertainCall, match="unsettled_call"):
            journal.reserve("next", "oversight", payload())


def test_request_bound_and_model_are_checked_before_reservation(tmp_path):
    parent, path = make_parent(tmp_path)
    with CumulativeJournal(path, parent, MANIFEST, CONFIG) as journal:
        for request in (
            {"model": "other", "max_output_tokens": 2048},
            {"model": CONFIG.model, "max_output_tokens": 2049},
        ):
            with pytest.raises(PilotStopped, match="frozen model or output"):
                journal.reserve("ep", "analyst", encoded(request))
        with pytest.raises(BudgetDenied, match="serialized_request_byte_limit"):
            journal.reserve("ep", "analyst", b"x" * 120_001)
        assert journal.totals()["call_count"] == 0


def test_parent_unsettled_call_is_rejected(tmp_path):
    parent, path = make_parent(tmp_path)
    prior = BudgetJournal(parent / "budget.sqlite3")
    prior.reserve("pending", "analyst", payload())
    prior.close()
    with pytest.raises(UncertainCall, match="parent has unresolved"):
        CumulativeJournal(path, parent, MANIFEST, CONFIG)


def test_inconsistent_parent_summary_cannot_lower_imported_commitment(tmp_path):
    parent, path = make_parent(tmp_path)
    results = json.loads((parent / "results.json").read_bytes())
    results["budget"]["committed_cost_upper_usd"] = "0"
    (parent / "results.json").write_bytes(encoded(results))
    with pytest.raises(PilotStopped, match="do not reconcile"):
        CumulativeJournal(path, parent, MANIFEST, CONFIG)


def test_changed_child_settlement_blocks_further_admission(tmp_path):
    parent, path = make_parent(tmp_path)
    with CumulativeJournal(path, parent, MANIFEST, CONFIG) as journal:
        call = journal.reserve("ep", "analyst", payload())
        journal.settle(call, response())
        with journal.db:
            journal.db.execute("UPDATE calls SET actual_usd='0'")
        with pytest.raises(PilotStopped, match="settlement integrity"):
            journal.reserve("next", "analyst", payload())
    with pytest.raises(PilotStopped, match="settlement integrity"):
        CumulativeJournal(path, parent, MANIFEST, CONFIG)


def test_duplicate_settlement_does_not_double_release_commitment(tmp_path):
    parent, path = make_parent(tmp_path)
    with CumulativeJournal(path, parent, MANIFEST, CONFIG) as journal:
        call = journal.reserve("ep", "analyst", payload())
        journal.settle(call, response())
        before = journal.totals()
        with pytest.raises(PilotStopped, match="exactly once"):
            journal.settle(call, response())
        assert journal.totals() == before
