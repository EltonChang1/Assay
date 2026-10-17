"""Offline Phase 3 harness: genuine DuckDB results through the real gateway path.

Only the container boundary is replaced. The stand-in reuses the worker's fixed
CSV loaders and result serializer, so receipts, frozen inputs, and captured
cells are the same records the Docker worker produces. Isolation evidence comes
from the separate Docker suite, not from this harness.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import duckdb

from assay.contracts import CellLocator, Claim, canonical_json_bytes
from assay.contracts.execution import WorkerSuccess
from assay.contracts.report import ClaimInput, ClaimRecord, ReportRevision
from assay.datasets import SalesFixture, generate_sales_fixture, write_public_bundle
from assay.evidence import EvidenceStore
from assay.execution.docker import ContainerOutcome, WorkerImage
from assay.gateway import service
from assay.gateway.service import QueryOutcome
from assay.publication.rendering import render_report
from sandbox.worker import _CREATE_TABLE, _INSERT_TABLE, read_table_rows, serialize_result

SCOPE = (
    "o.status = 'settled' AND o.currency = 'USD' "
    "AND o.occurred_at >= TIMESTAMPTZ '2026-01-01 00:00:00+00' "
    "AND o.occurred_at < TIMESTAMPTZ '2026-04-01 00:00:00+00'"
)
CORRECT_SQL = f"SELECT SUM(o.amount_minor * 0.01) AS revenue_usd FROM orders o WHERE {SCOPE}"
DUPLICATED_SQL = (
    "SELECT SUM(o.amount_minor * 0.01) AS revenue_usd "
    f"FROM orders o JOIN order_items i USING (order_id) WHERE {SCOPE}"
)
DISTINCT_AMOUNT_SQL = (
    "SELECT SUM(DISTINCT o.amount_minor * 0.01) AS revenue_usd "
    f"FROM orders o JOIN order_items i USING (order_id) WHERE {SCOPE}"
)
COUNT_SQL = f"SELECT COUNT(DISTINCT o.order_id) AS order_count FROM orders o WHERE {SCOPE}"
IMAGE = WorkerImage(
    image_id="sha256:" + "a" * 64,
    base_image="offline-test-stand-in",
    policy_sha256="b" * 64,
    worker_sha256="c" * 64,
    requirements_sha256="d" * 64,
)


def in_process_worker(image, bundle, query, allowed_tables, limits, cancel=None):
    """Container stand-in over the frozen copy; never used outside tests."""

    with duckdb.connect(":memory:", config={"enable_external_access": False}) as connection:
        for table in allowed_tables:
            connection.execute(_CREATE_TABLE[table])
            rows = read_table_rows(table, Path(bundle))
            if rows:
                connection.executemany(_INSERT_TABLE[table], rows)
        cursor = connection.execute(query)
        raw = serialize_result(cursor.description, cursor.fetchall(), 1000, 1 << 20)
    return ContainerOutcome("success", WorkerSuccess.model_validate_json(raw))


@dataclass
class Lab:
    state: Path
    source: Path
    fixture: SalesFixture
    run_id: str = "run-lab"

    @property
    def evidence(self) -> EvidenceStore:
        return EvidenceStore(self.state / "evidence")

    @property
    def task(self):
        return self.fixture.public_task

    @property
    def snapshot(self):
        return self.fixture.snapshot

    def query(self, sql: str, *, run_id: str | None = None) -> QueryOutcome:
        return service.execute_query(
            sql, self.source, state=self.state, run_id=run_id or self.run_id
        )

    def claim_input(
        self,
        outcome: QueryOutcome,
        value: str | Decimal | None = None,
        *,
        slot: str = "settled_revenue_usd",
        column: str = "revenue_usd",
        row: int = 0,
        **updates: object,
    ) -> ClaimInput:
        count = slot == "settled_order_count"
        if value is None and "abstention_reason" not in updates:
            assert outcome.result is not None
            names = [item.name for item in outcome.result.columns]
            value = str(outcome.result.rows[row][names.index(column)].value)
        abstaining = updates.get("abstention_reason") is not None
        fields: dict[str, object] = {
            "slot_id": slot,
            "metric_id": slot,
            "metric_type": "count" if count else "total",
            "value": None if abstaining else Decimal(str(value)),
            "unit": "orders" if count else "USD",
            "snapshot_id": self.snapshot.snapshot_id,
            "time_scope": self.task.time_scope,
            "report_semantics": self.task.report_semantics,
        }
        if not abstaining:
            fields["result_id"] = outcome.receipt.result_id
            fields["cell_locator"] = CellLocator(row_index=row, column=column)
        fields.update(updates)
        return ClaimInput(claim=Claim(**fields), execution_id=outcome.receipt.execution_id)


def make_lab(tmp_path: Path, monkeypatch, *, variant="base", seed=0, name="source") -> Lab:
    fixture = generate_sales_fixture(seed=seed, variant=variant)
    source = tmp_path / name
    write_public_bundle(fixture, source)
    monkeypatch.setattr(service, "load_worker", lambda *args: IMAGE)
    monkeypatch.setattr(service, "execute_container", in_process_worker)
    return Lab(state=tmp_path / "state", source=source, fixture=fixture)


def make_report(
    lab: Lab,
    claims: tuple[ClaimInput, ...],
    *,
    run_id: str | None = None,
    **updates: object,
) -> ReportRevision:
    """A host-shaped revision for verifier tests, independent of the publisher."""

    records = tuple(
        ClaimRecord(claim=item.claim, execution_id=item.execution_id, claim_id=f"claim-{index}")
        for index, item in enumerate(claims)
    )
    if "rendered_sha256" not in updates:
        updates["rendered_sha256"] = hashlib.sha256(render_report(lab.task, records)).hexdigest()
    fields: dict[str, object] = {
        "revision_id": "revision-test",
        "report_id": "report-test",
        "revision": 1,
        "run_id": run_id or lab.run_id,
        "attempt_id": "attempt-test",
        "fencing_token": 1,
        "source_key": "sales-q1",
        "source_epoch": 1,
        "task": lab.task,
        "snapshot": lab.snapshot,
        "claims": records,
        "created_at": datetime(2026, 10, 16, tzinfo=UTC),
    }
    fields.update(updates)
    return ReportRevision(**fields)


def digest(model) -> str:
    return hashlib.sha256(canonical_json_bytes(model)).hexdigest()
