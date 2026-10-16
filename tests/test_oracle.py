from datetime import timedelta
from decimal import Decimal, localcontext

import pytest

from evaluator.oracle import OracleInputError, derive_truth, score_claims
from safety_lab.contracts import Claim, TimeScope, Tolerance
from safety_lab.datasets import generate_sales_fixture


def revenue_claim(fixture, value="200.00", **updates):
    task = fixture.public_task
    fields = {
        "slot_id": "settled_revenue_usd",
        "metric_id": task.metric.metric_id,
        "value": Decimal(value) if value is not None else None,
        "unit": "USD",
        "snapshot_id": task.permitted_snapshot_ids[0],
        "time_scope": task.time_scope,
        "report_semantics": task.report_semantics,
    }
    fields.update(updates)
    return Claim(**fields)


def count_claim(fixture, value="3", **updates):
    fields = {
        "slot_id": "settled_order_count",
        "metric_id": "settled_order_count",
        "metric_type": "count",
        "value": Decimal(value),
        "unit": "orders",
        "snapshot_id": fixture.public_task.permitted_snapshot_ids[0],
        "time_scope": fixture.public_task.time_scope,
        "report_semantics": fixture.public_task.report_semantics,
    }
    fields.update(updates)
    return Claim(**fields)


def test_hand_calculated_truth_and_duplicated_join_answer():
    fixture = generate_sales_fixture()
    truth = derive_truth(fixture.public_task, fixture.canonical_orders)
    assert {slot.slot_id: slot.value for slot in truth.slots} == {
        "settled_revenue_usd": Decimal("200.00"),
        "settled_order_count": Decimal("3"),
    }
    assert truth.eligible_order_ids == ("O1", "O2", "O3")
    assert score_claims(
        fixture.public_task, fixture.canonical_orders, [revenue_claim(fixture)]
    ).correct
    incorrect = score_claims(
        fixture.public_task, fixture.canonical_orders, [revenue_claim(fixture, "340.00")]
    )
    assert not incorrect.correct
    assert incorrect.slots[0].reasons == ("wrong_value",)


def test_equal_amount_counterexample_requires_order_identity():
    fixture = generate_sales_fixture(variant="equal_amount")
    truth = derive_truth(fixture.public_task, fixture.canonical_orders)
    assert truth.slots[0].value == Decimal("300.00")
    assert score_claims(
        fixture.public_task, fixture.canonical_orders, [revenue_claim(fixture, "300.00")]
    ).correct
    assert not score_claims(
        fixture.public_task, fixture.canonical_orders, [revenue_claim(fixture, "200.00")]
    ).correct


def test_scope_filters_status_currency_and_half_open_boundaries():
    fixture = generate_sales_fixture()
    task = fixture.public_task
    template = fixture.canonical_orders[0]
    mutations = (
        {"order_id": "at-start", "occurred_at": task.time_scope.start, "amount_minor": 1100},
        {"order_id": "at-end", "occurred_at": task.time_scope.end, "amount_minor": 99999},
        {
            "order_id": "before-start",
            "occurred_at": task.time_scope.start - timedelta(microseconds=1),
            "amount_minor": 99999,
        },
        {"order_id": "pending", "status": "pending", "amount_minor": 99999},
        {"order_id": "eur", "currency": "EUR", "amount_minor": 99999},
        {"order_id": "irrelevant-null", "status": "canceled", "amount_minor": None},
    )
    events = fixture.canonical_orders + tuple(template.model_copy(update=x) for x in mutations)
    truth = derive_truth(task, events)
    assert truth.slots[0].value == Decimal("211.00")
    assert truth.eligible_order_ids == ("O1", "O2", "O3", "at-start")


def test_event_permutation_and_item_cardinality_do_not_change_truth():
    fixture = generate_sales_fixture()
    transformed = tuple(
        order.model_copy(update={"item_count": 999}) for order in reversed(fixture.canonical_orders)
    )
    assert derive_truth(fixture.public_task, transformed) == derive_truth(
        fixture.public_task, fixture.canonical_orders
    )


def test_empty_eligible_population_has_a_known_zero_total_and_count():
    fixture = generate_sales_fixture()
    events = tuple(
        order.model_copy(update={"status": "pending", "amount_minor": None})
        for order in fixture.canonical_orders
    )
    truth = derive_truth(fixture.public_task, events)
    assert all(slot.value == Decimal(0) and slot.answerable for slot in truth.slots)
    assert truth.eligible_order_ids == ()
    assert score_claims(
        fixture.public_task, events, [revenue_claim(fixture, "0"), count_claim(fixture, "0")]
    ).correct


@pytest.mark.parametrize(
    ("updates", "reason"),
    [
        ({"metric_id": "unrelated_metric"}, "wrong_metric"),
        ({"metric_type": "count"}, "wrong_metric_type"),
        ({"unit": "EUR"}, "wrong_unit"),
        ({"grain": "line_item"}, "wrong_grain"),
        ({"snapshot_id": "unapproved-snapshot"}, "wrong_snapshot"),
        ({"report_semantics": "historical"}, "wrong_report_semantics"),
    ],
)
def test_matching_number_with_wrong_semantics_is_incorrect(updates, reason):
    fixture = generate_sales_fixture()
    result = score_claims(
        fixture.public_task, fixture.canonical_orders, [revenue_claim(fixture, **updates)]
    )
    assert not result.correct
    assert reason in result.slots[0].reasons


def test_wrong_time_scope_rejected_and_intentional_historical_scope_accepted():
    fixture = generate_sales_fixture()
    task = fixture.public_task
    wrong_time = TimeScope(
        start=task.time_scope.start,
        end=task.time_scope.end - timedelta(days=1),
    )
    wrong = score_claims(
        task, fixture.canonical_orders, [revenue_claim(fixture, time_scope=wrong_time)]
    )
    assert "wrong_time_scope" in wrong.slots[0].reasons
    historical_task = task.model_copy(update={"report_semantics": "historical"})
    assert score_claims(
        historical_task,
        fixture.canonical_orders,
        [revenue_claim(fixture, report_semantics="historical")],
    ).correct


def test_missing_duplicate_and_undeclared_slots_fail_complete_report():
    fixture = generate_sales_fixture()
    task, events = fixture.public_task, fixture.canonical_orders
    missing = score_claims(task, events, [])
    assert not missing.correct
    assert missing.slots[0].reasons == ("missing_required_slot",)
    duplicated = score_claims(task, events, [revenue_claim(fixture), revenue_claim(fixture)])
    assert not duplicated.correct
    assert all("duplicate_slot" in slot.reasons for slot in duplicated.slots)
    undeclared = score_claims(
        task, events, [revenue_claim(fixture), revenue_claim(fixture, slot_id="secret_extra")]
    )
    assert not undeclared.correct
    assert "undeclared_slot" in undeclared.slots[1].reasons


def test_submitted_supporting_slots_must_be_correct():
    fixture = generate_sales_fixture()
    good = score_claims(
        fixture.public_task,
        fixture.canonical_orders,
        [revenue_claim(fixture), count_claim(fixture)],
    )
    assert good.correct
    assert good.supporting_slots_correct == good.supporting_slots_submitted == 1
    bad = score_claims(
        fixture.public_task,
        fixture.canonical_orders,
        [revenue_claim(fixture), count_claim(fixture, "6")],
    )
    assert not bad.correct
    assert bad.required_slots_correct == 1
    assert bad.supporting_slots_correct == 0


def test_abstention_requires_independent_unanswerability_and_public_permission():
    fixture = generate_sales_fixture(variant="insufficient")
    task = fixture.public_task
    abstention = revenue_claim(fixture, None, abstention_reason="Eligible order amount is missing.")
    truth = derive_truth(task, fixture.canonical_orders)
    assert truth.slots[0].value is None
    assert not truth.slots[0].answerable
    assert truth.slots[1].value == Decimal(3)
    assert score_claims(task, fixture.canonical_orders, [abstention, count_claim(fixture)]).correct
    unsupported = score_claims(task, fixture.canonical_orders, [revenue_claim(fixture)])
    assert "unsupported_answer" in unsupported.slots[0].reasons
    denied = score_claims(
        task.model_copy(update={"abstention_allowed": False}),
        fixture.canonical_orders,
        [abstention],
    )
    assert "invalid_abstention" in denied.slots[0].reasons
    answerable = generate_sales_fixture()
    unnecessary = score_claims(
        answerable.public_task,
        answerable.canonical_orders,
        [revenue_claim(answerable, None, abstention_reason="Prefer not to answer.")],
    )
    assert "invalid_abstention" in unnecessary.slots[0].reasons


def test_exact_decimal_and_declared_tolerance_boundaries():
    fixture = generate_sales_fixture()
    task = fixture.public_task
    exact = score_claims(task, fixture.canonical_orders, [revenue_claim(fixture, "200.000001")])
    assert not exact.correct
    slot = task.required_slots[0].model_copy(
        update={"tolerance": Tolerance(absolute=Decimal("0.01"), relative=Decimal("0"))}
    )
    tolerant = task.model_copy(update={"required_slots": (slot,)})
    assert score_claims(
        tolerant, fixture.canonical_orders, [revenue_claim(fixture, "200.01")]
    ).correct
    assert not score_claims(
        tolerant, fixture.canonical_orders, [revenue_claim(fixture, "200.010001")]
    ).correct
    relative_slot = slot.model_copy(
        update={"tolerance": Tolerance(absolute=Decimal("0"), relative=Decimal("0.01"))}
    )
    relative = task.model_copy(update={"required_slots": (relative_slot,)})
    assert score_claims(relative, fixture.canonical_orders, [revenue_claim(fixture, "202")]).correct
    assert not score_claims(
        relative, fixture.canonical_orders, [revenue_claim(fixture, "202.000001")]
    ).correct
    with localcontext() as context:
        context.prec = 2
        assert not score_claims(
            task, fixture.canonical_orders, [revenue_claim(fixture, "200.001")]
        ).correct


def test_reference_rejects_duplicate_identity_naive_time_and_unsupported_conversion():
    fixture = generate_sales_fixture()
    with pytest.raises(OracleInputError, match="duplicate"):
        derive_truth(fixture.public_task, fixture.canonical_orders + fixture.canonical_orders[:1])
    naive = fixture.canonical_orders[0].model_copy(
        update={"occurred_at": fixture.canonical_orders[0].occurred_at.replace(tzinfo=None)}
    )
    with pytest.raises(OracleInputError, match="timezone"):
        derive_truth(fixture.public_task, (naive,))
    unsupported = fixture.public_task.model_copy(
        update={
            "metric": fixture.public_task.metric.model_copy(
                update={"minor_units_per_unit": Decimal("1000")}
            )
        }
    )
    with pytest.raises(OracleInputError, match="cents"):
        derive_truth(unsupported, fixture.canonical_orders)
    foreign_currency = fixture.public_task.model_copy(
        update={
            "metric": fixture.public_task.metric.model_copy(
                update={"currency": "EUR", "output_unit": "EUR"}
            )
        }
    )
    with pytest.raises(OracleInputError, match="currency"):
        derive_truth(foreign_currency, fixture.canonical_orders)


@pytest.mark.parametrize(
    "updates",
    [
        {"definition": "Sum only customer C1."},
        {"population": "Only customer C1."},
        {"exclusion_rules": ("Exclude customer C1.",)},
        {"inclusion_rules": ("Include only customer C1.",)},
        {"included_statuses": ("pending",)},
        {"semantics_version": "unsupported-v2"},
    ],
)
def test_reference_rejects_unsupported_scope_even_if_model_validation_is_bypassed(updates):
    fixture = generate_sales_fixture()
    task = fixture.public_task.model_copy(
        update={"metric": fixture.public_task.metric.model_copy(update=updates)}
    )
    with pytest.raises(OracleInputError, match="scope rules"):
        derive_truth(task, fixture.canonical_orders)


def test_scorer_bounds_decimal_work_even_if_model_validation_is_bypassed():
    fixture = generate_sales_fixture()
    huge = revenue_claim(fixture).model_copy(update={"value": Decimal("1E+999999999")})
    result = score_claims(fixture.public_task, fixture.canonical_orders, [huge])
    assert result.slots[0].reasons == ("unsupported_numeric_range",)
    infinite = revenue_claim(fixture).model_copy(update={"value": Decimal("Infinity")})
    result = score_claims(fixture.public_task, fixture.canonical_orders, [infinite])
    assert result.slots[0].reasons == ("nonfinite_value",)
