"""Trusted SQL mutations for the exposed first development milestone.

Only the fixed statements below run. This is a research regression harness, not
the gateway for untrusted analyst SQL, evidence binding, or report publication.
The independent reference reads canonical events, never these result tables.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

import duckdb

from evaluator.oracle import derive_truth, score_claims
from safety_lab.contracts import Claim
from safety_lab.datasets import SalesFixture, generate_sales_fixture


@dataclass(frozen=True)
class _TrustedStrategy:
    name: str
    sql: str


_SCOPE = """
    o.status = 'settled' AND o.currency = 'USD'
    AND o.occurred_at >= TIMESTAMPTZ '2026-01-01 00:00:00+00'
    AND o.occurred_at < TIMESTAMPTZ '2026-04-01 00:00:00+00'
"""

_STRATEGIES = (
    _TrustedStrategy(
        "order_aggregation",
        f"SELECT SUM(o.amount_minor * 0.01) AS revenue_usd FROM orders o WHERE {_SCOPE}",
    ),
    _TrustedStrategy(
        "duplicated_join",
        "SELECT SUM(o.amount_minor * 0.01) AS revenue_usd "
        f"FROM orders o JOIN order_items i USING (order_id) WHERE {_SCOPE}",
    ),
    _TrustedStrategy(
        "exists_filter",
        "SELECT SUM(o.amount_minor * 0.01) AS revenue_usd FROM orders o "
        f"WHERE {_SCOPE} AND EXISTS "
        "(SELECT 1 FROM order_items i WHERE i.order_id = o.order_id)",
    ),
    _TrustedStrategy(
        "grouped_item_join",
        "WITH item_orders AS (SELECT order_id FROM order_items GROUP BY order_id) "
        "SELECT SUM(o.amount_minor * 0.01) AS revenue_usd FROM orders o "
        f"JOIN item_orders i USING (order_id) WHERE {_SCOPE}",
    ),
    _TrustedStrategy(
        "distinct_amount",
        "SELECT SUM(DISTINCT o.amount_minor * 0.01) AS revenue_usd "
        f"FROM orders o JOIN order_items i USING (order_id) WHERE {_SCOPE}",
    ),
)


def _load_public_tables(connection: duckdb.DuckDBPyConnection, fixture: SalesFixture) -> None:
    """Load relational tables only; canonical events are not SQL inputs."""
    connection.execute(
        "CREATE TABLE orders (order_id VARCHAR, customer_id VARCHAR, "
        "amount_minor BIGINT, currency VARCHAR, status VARCHAR, occurred_at TIMESTAMPTZ)"
    )
    connection.execute(
        "CREATE TABLE order_items (item_id VARCHAR, order_id VARCHAR, "
        "quantity BIGINT, amount_minor BIGINT)"
    )
    connection.executemany(
        "INSERT INTO orders VALUES (?, ?, ?, ?, ?, ?)",
        [
            (
                order.order_id,
                order.customer_id,
                order.amount_minor,
                order.currency,
                order.status,
                order.occurred_at,
            )
            for order in fixture.orders
        ],
    )
    connection.executemany(
        "INSERT INTO order_items VALUES (?, ?, ?, ?)",
        [
            (item.item_id, item.order_id, item.quantity, item.amount_minor)
            for item in fixture.order_items
        ],
    )


def run_milestone() -> dict[str, object]:
    """Validate fixed trusted analyses against independent canonical truth.

    Returns JSON-compatible data and writes no files. No model, network, live
    database, arbitrary query, or publication endpoint is used.
    """
    cases: list[dict[str, object]] = []
    for variant in ("base", "equal_amount"):
        fixture = generate_sales_fixture(variant=variant)
        task = fixture.public_task
        truth = derive_truth(task, fixture.canonical_orders)
        expected_total = next(
            slot.value for slot in truth.slots if slot.slot_id == "settled_revenue_usd"
        )
        with duckdb.connect(
            ":memory:",
            config={
                "enable_external_access": False,
                "autoinstall_known_extensions": False,
                "autoload_known_extensions": False,
            },
        ) as connection:
            _load_public_tables(connection, fixture)
            for strategy in _STRATEGIES:
                row = connection.execute(strategy.sql).fetchone()
                if row is None or not isinstance(row[0], Decimal):
                    raise RuntimeError("trusted fixture query did not return a Decimal cell")
                value = row[0]
                claim = Claim(
                    slot_id="settled_revenue_usd",
                    metric_id=task.metric.metric_id,
                    value=value,
                    unit="USD",
                    snapshot_id=task.permitted_snapshot_ids[0],
                    time_scope=task.time_scope,
                    report_semantics=task.report_semantics,
                )
                score = score_claims(task, fixture.canonical_orders, (claim,))
                expected_correct = strategy.name != "duplicated_join" and not (
                    variant == "equal_amount" and strategy.name == "distinct_amount"
                )
                cases.append(
                    {
                        "case_id": f"{variant}.{strategy.name}",
                        "fixture": variant,
                        "strategy": strategy.name,
                        "query_value": str(value),
                        "canonical_reference_value": str(expected_total),
                        "score": score.as_dict(),
                        "regression_passed": score.correct == expected_correct,
                    }
                )
    passed = sum(case["regression_passed"] is True for case in cases)
    return {
        "schema_version": "1.0",
        "validation_scope": "exposed development fixtures; developer-authored SQL only",
        "model_calls": 0,
        "untrusted_execution_boundary_tested": False,
        "publication_boundary_tested": False,
        "passed": passed == len(cases),
        "checks_passed": passed,
        "checks_run": len(cases),
        "cases": cases,
    }
