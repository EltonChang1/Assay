"""Content integrity, immutable identities, and atomic receipt persistence."""

import hashlib
import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from safety_lab.contracts import canonical_json_bytes
from safety_lab.contracts.execution import (
    ExecutionReceipt,
    ResultCell,
    ResultColumn,
    WorkerSuccess,
)
from safety_lab.datasets import generate_sales_fixture
from safety_lab.evidence import EvidenceConflictError, EvidenceIntegrityError, EvidenceStore


def captured_execution(execution_id="execution-one"):
    fixture = generate_sales_fixture()
    result = WorkerSuccess(
        status="success",
        columns=(ResultColumn(name="revenue_usd", data_type="DECIMAL(30, 2)"),),
        rows=((ResultCell(type="decimal", value="200.00"),),),
        row_count=1,
    )
    output_hash = hashlib.sha256(canonical_json_bytes(result)).hexdigest()
    query = "SELECT SUM(amount_minor) / 100 AS revenue_usd FROM orders"
    started = datetime(2026, 10, 16, tzinfo=UTC)
    receipt = ExecutionReceipt(
        execution_id=execution_id,
        run_id="run-one",
        snapshot_id=fixture.snapshot.snapshot_id,
        snapshot_manifest_sha256=hashlib.sha256(canonical_json_bytes(fixture.snapshot)).hexdigest(),
        task_id=fixture.public_task.task_id,
        exact_query=query,
        query_sha256=hashlib.sha256(query.encode()).hexdigest(),
        normalized_query=query,
        source_ids=("orders",),
        policy_version="sql-select-1.0",
        worker_image_id="sha256:" + "0" * 64,
        started_at=started,
        finished_at=started + timedelta(milliseconds=5),
        elapsed_ms=5,
        status="success",
        result_id="result-" + output_hash,
        output_sha256=output_hash,
        row_count=1,
        preview_row_count=1,
    )
    return fixture, result, receipt


def table_counts(store):
    with sqlite3.connect(store.database_path) as connection:
        return tuple(
            connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("artifacts", "results", "executions")
        )


def test_receipt_and_complete_output_survive_reopening_with_input_artifacts(tmp_path):
    fixture, result, receipt = captured_execution()
    store = EvidenceStore(tmp_path / "state")
    store.record_execution(receipt, result, fixture.snapshot, fixture.public_task)
    reopened = EvidenceStore(tmp_path / "state")
    assert reopened.get_execution(receipt.execution_id) == receipt
    assert reopened.get_result(receipt.result_id) == result
    assert table_counts(reopened) == (4, 1, 1)
    with sqlite3.connect(store.database_path) as connection:
        contents = [row[0] for row in connection.execute("SELECT content FROM artifacts")]
    assert canonical_json_bytes(fixture.snapshot) in contents
    assert canonical_json_bytes(fixture.public_task) in contents
    assert all(b"canonical_orders" not in content for content in contents)


def test_exact_retry_is_idempotent_and_equal_outputs_share_content_identity(tmp_path):
    fixture, result, receipt = captured_execution()
    store = EvidenceStore(tmp_path)
    store.record_execution(receipt, result, fixture.snapshot, fixture.public_task)
    store.record_execution(receipt, result, fixture.snapshot, fixture.public_task)
    assert table_counts(store) == (4, 1, 1)
    second = receipt.model_copy(update={"execution_id": "execution-two"})
    store.record_execution(second, result, fixture.snapshot, fixture.public_task)
    assert table_counts(store) == (5, 1, 2)
    assert store.get_execution(second.execution_id).result_id == receipt.result_id


def test_conflicting_execution_id_cannot_replace_existing_bytes(tmp_path):
    fixture, result, receipt = captured_execution()
    store = EvidenceStore(tmp_path)
    store.record_execution(receipt, result, fixture.snapshot, fixture.public_task)
    query = "SELECT 200.00 AS revenue_usd FROM orders LIMIT 1"
    conflict = receipt.model_copy(
        update={
            "exact_query": query,
            "normalized_query": query,
            "query_sha256": hashlib.sha256(query.encode()).hexdigest(),
        }
    )
    with pytest.raises(EvidenceConflictError):
        store.record_execution(conflict, result, fixture.snapshot, fixture.public_task)
    assert table_counts(store) == (4, 1, 1)
    assert store.get_execution(receipt.execution_id) == receipt


@pytest.mark.parametrize(
    "change",
    [
        {"query_sha256": "0" * 64},
        {"snapshot_manifest_sha256": "0" * 64},
        {"snapshot_id": "snapshot-unrelated"},
        {"task_id": "task-unrelated"},
        {"result_id": "result-unrelated"},
        {"output_sha256": "0" * 64},
        {"source_ids": ("orders", "private_events")},
        {"source_ids": ("orders", "orders")},
        {"row_count": 2, "preview_truncated": True},
    ],
)
def test_inconsistent_captured_metadata_is_rejected_without_persistence(tmp_path, change):
    fixture, result, receipt = captured_execution()
    store = EvidenceStore(tmp_path)
    receipt = receipt.model_copy(update=change)
    with pytest.raises(EvidenceIntegrityError):
        store.record_execution(receipt, result, fixture.snapshot, fixture.public_task)
    assert table_counts(store) == (0, 0, 0)


def test_database_failure_rolls_back_artifacts_result_and_receipt_together(tmp_path):
    fixture, result, receipt = captured_execution()
    store = EvidenceStore(tmp_path)
    with sqlite3.connect(store.database_path) as connection:
        connection.execute(
            "CREATE TRIGGER reject_execution BEFORE INSERT ON executions "
            "BEGIN SELECT RAISE(ABORT, 'simulated receipt write failure'); END"
        )
    with pytest.raises(sqlite3.IntegrityError, match="simulated receipt write failure"):
        store.record_execution(receipt, result, fixture.snapshot, fixture.public_task)
    assert table_counts(store) == (0, 0, 0)


def test_failed_execution_persists_receipt_without_successful_result(tmp_path):
    fixture, result, receipt = captured_execution()
    failed = receipt.model_copy(
        update={
            "status": "timeout",
            "error_code": "wall_clock_limit",
            "result_id": None,
            "output_sha256": None,
            "row_count": None,
            "preview_row_count": None,
        }
    )
    store = EvidenceStore(tmp_path)
    store.record_execution(failed, None, fixture.snapshot, fixture.public_task)
    assert store.get_execution(failed.execution_id) == failed
    assert table_counts(store) == (3, 0, 1)
    with pytest.raises(EvidenceIntegrityError, match="failed executions"):
        store.record_execution(failed, result, fixture.snapshot, fixture.public_task)
    with pytest.raises(EvidenceIntegrityError, match="requires a captured result"):
        store.record_execution(receipt, None, fixture.snapshot, fixture.public_task)


@pytest.mark.parametrize("artifact", ["output", "receipt", "snapshot", "task"])
def test_artifact_corruption_is_detected_on_read(tmp_path, artifact):
    fixture, result, receipt = captured_execution()
    store = EvidenceStore(tmp_path)
    store.record_execution(receipt, result, fixture.snapshot, fixture.public_task)
    digests = {
        "output": receipt.output_sha256,
        "receipt": hashlib.sha256(canonical_json_bytes(receipt)).hexdigest(),
        "snapshot": receipt.snapshot_manifest_sha256,
        "task": fixture.snapshot.task_sha256,
    }
    with sqlite3.connect(store.database_path) as connection:
        connection.execute(
            "UPDATE artifacts SET content = ? WHERE sha256 = ?",
            (b'{"changed":true}\n', digests[artifact]),
        )
    with pytest.raises(EvidenceIntegrityError, match="content hash changed"):
        store.get_execution(receipt.execution_id)
    if artifact == "output":
        with pytest.raises(EvidenceIntegrityError, match="content hash changed"):
            store.get_result(receipt.result_id)


def test_index_corruption_is_detected_and_lookup_ids_do_not_become_paths(tmp_path):
    fixture, result, receipt = captured_execution()
    store = EvidenceStore(tmp_path)
    store.record_execution(receipt, result, fixture.snapshot, fixture.public_task)
    with pytest.raises(KeyError, match="unknown execution"):
        store.get_execution("../../private/events.json")
    with sqlite3.connect(store.database_path) as connection:
        connection.execute("UPDATE executions SET result_id = NULL")
    with pytest.raises(EvidenceIntegrityError, match="index disagrees"):
        store.get_execution(receipt.execution_id)


def test_unsupported_database_version_does_not_migrate_silently(tmp_path):
    database = tmp_path / "evidence.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA user_version=9")
    with pytest.raises(EvidenceIntegrityError, match="unsupported evidence database schema"):
        EvidenceStore(tmp_path)
