"""Contract tests target ambiguous answers and silently lost analytical scope."""

from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from assay.contracts import (
    AnswerSlot,
    CellLocator,
    Claim,
    TaskSpec,
    TimeScope,
    Tolerance,
    canonical_json_bytes,
)
from assay.datasets import generate_sales_fixture


def claim_data() -> dict:
    task = generate_sales_fixture().public_task
    return {
        "slot_id": "settled_revenue_usd",
        "metric_id": "settled_revenue_usd",
        "value": Decimal("200.00"),
        "unit": "USD",
        "snapshot_id": task.permitted_snapshot_ids[0],
        "time_scope": task.time_scope,
    }


def test_exact_decimal_and_scope_survive_public_json_round_trip():
    claim = Claim(**claim_data())
    assert Claim.model_validate_json(canonical_json_bytes(claim)) == claim
    assert b'"value":"200.00"' in canonical_json_bytes(claim)
    assert claim.time_scope.start == datetime(2026, 1, 1, tzinfo=UTC)
    task = generate_sales_fixture().public_task
    assert TaskSpec.model_validate_json(canonical_json_bytes(task)) == task


@pytest.mark.parametrize(
    "value",
    [
        200.0,
        True,
        float("nan"),
        "NaN",
        "Infinity",
        Decimal("-Infinity"),
        "1E+999999999",
        "1E-999999999",
        "1.0000001",
        "9" * 200,
        10**100,
        "not-a-number",
        b"200.00",
    ],
)
def test_inexact_or_nonfinite_financial_answers_are_rejected(value):
    with pytest.raises(ValidationError):
        Claim(**(claim_data() | {"value": value}))


@pytest.mark.parametrize(
    "changes",
    [
        {"value": None},
        {"value": None, "abstention_reason": "   "},
        {"abstention_reason": "Missing order amounts"},
        {"result_id": "result-1"},
        {"cell_locator": CellLocator(row_index=0, column="revenue")},
        {"value": None, "abstention_reason": "Unknown", "result_id": "result-1"},
        {"dependency_ids": ("result-1", "result-1")},
    ],
)
def test_ambiguous_answer_or_partial_binding_is_rejected(changes):
    with pytest.raises(ValidationError):
        Claim(**(claim_data() | changes))


def test_abstention_and_complete_numerical_binding_are_separate_valid_forms():
    answer = Claim(
        **(
            claim_data()
            | {"result_id": "result-1", "cell_locator": CellLocator(row_index=0, column="revenue")}
        )
    )
    assert answer.value == Decimal("200.00")
    abstention = Claim(**(claim_data() | {"value": None, "abstention_reason": "Missing O3 amount"}))
    assert abstention.value is None


def test_records_and_nested_collections_are_frozen_and_unknown_fields_fail():
    task = generate_sales_fixture().public_task
    with pytest.raises(ValidationError):
        task.task_id = "changed"
    with pytest.raises(ValidationError):
        task.metric.definition = "changed"
    assert isinstance(task.required_slots, tuple)
    assert isinstance(task.metric.inclusion_rules, tuple)
    with pytest.raises(ValidationError):
        Claim(**(claim_data() | {"expected_answer": "200.00"}))
    with pytest.raises(ValidationError):
        TaskSpec.model_validate(task.model_dump() | {"schema_version": "2.0"})


def test_scope_normalizes_offsets_to_utc_and_preserves_analytical_zone():
    local = timezone(timedelta(hours=-8))
    scope = TimeScope(
        start=datetime(2026, 1, 1, tzinfo=local),
        end=datetime(2026, 4, 1, tzinfo=local),
        analytical_timezone="America/Los_Angeles",
    )
    assert scope.start == datetime(2026, 1, 1, 8, tzinfo=UTC)
    assert scope.start.tzinfo == UTC
    assert scope.analytical_timezone == "America/Los_Angeles"


@pytest.mark.parametrize(
    "changes",
    [
        {"start": datetime(2026, 1, 1)},
        {"end": datetime(2025, 12, 1, tzinfo=UTC)},
        {"analytical_timezone": "Not/A_Zone"},
    ],
)
def test_scope_rejects_naive_reversed_or_undeclared_time(changes):
    original = generate_sales_fixture().public_task.time_scope.model_dump()
    with pytest.raises(ValidationError):
        TimeScope.model_validate(original | changes)


@pytest.mark.parametrize(
    "changes",
    [
        {"required_slots": ()},
        {"allowed_tables": ()},
        {"allowed_tables": ("orders", "orders")},
        {"permitted_snapshot_ids": ()},
        {"as_of": datetime(2026, 1, 10, tzinfo=UTC)},
    ],
)
def test_task_requires_explicit_nonduplicated_permissions_and_closed_period(changes):
    task = generate_sales_fixture().public_task
    with pytest.raises(ValidationError):
        TaskSpec.model_validate(task.model_dump() | changes)


def test_required_and_supporting_slot_collisions_and_unknown_metrics_fail():
    task = generate_sales_fixture().public_task
    with pytest.raises(ValidationError):
        TaskSpec.model_validate(task.model_dump() | {"supporting_slots": task.required_slots})
    unsupported = task.required_slots[0].model_dump() | {"metric_id": "not_declared"}
    with pytest.raises(ValidationError):
        TaskSpec.model_validate(task.model_dump() | {"required_slots": (unsupported,)})
    with pytest.raises(ValidationError):
        AnswerSlot(
            slot_id="count",
            metric_id="settled_order_count",
            metric_type="count",
            description="Count eligible orders",
            unit="USD",
        )
    with pytest.raises(ValidationError):
        Tolerance(absolute="-0.01")
    with pytest.raises(ValidationError):
        CellLocator(row_index=-1, column="revenue")


@pytest.mark.parametrize(
    "field,value",
    [
        ("definition", "Sum all orders, including refunds"),
        ("population", "Settled orders from female customers only"),
        ("included_statuses", ("pending",)),
        ("inclusion_rules", ("Include all orders",)),
        ("exclusion_rules", ("Exclude O3",)),
        ("minor_units_per_unit", "1000"),
    ],
)
def test_unsupported_metric_qualifiers_cannot_be_silently_ignored(field, value):
    task = generate_sales_fixture().public_task
    with pytest.raises(ValidationError):
        TaskSpec.model_validate(
            task.model_dump() | {"metric": task.metric.model_dump() | {field: value}}
        )
