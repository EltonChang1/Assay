"""Phase 3 persistence, migration, dependency integrity and shared atomic writes."""

import hashlib
import json
import sqlite3
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from test_evidence import captured_execution, table_counts

from assay.contracts import DatasetSnapshot, TaskSpec, canonical_json_bytes
from assay.evidence import EvidenceIntegrityError, EvidenceStore
from assay.evidence.store import SCHEMA_VERSION


def test_typed_records_and_exact_blobs_round_trip_with_stable_content_identity(tmp_path):
    fixture, _, _ = captured_execution()
    store = EvidenceStore(tmp_path)
    digest = store.put_model(fixture.public_task)
    assert digest == hashlib.sha256(canonical_json_bytes(fixture.public_task)).hexdigest()
    assert store.put_model(fixture.public_task) == digest
    assert store.get_model(digest, TaskSpec) == fixture.public_task
    assert store.get_blob(digest) == canonical_json_bytes(fixture.public_task)
    changed = fixture.public_task.model_copy(update={"task_id": "revised-public-task"})
    revision_digest = store.put_model(changed)
    assert digest != revision_digest
    assert store.get_model(digest, TaskSpec) == fixture.public_task
    assert store.get_model(revision_digest, TaskSpec) == changed
    raw = b"\x00released exact bytes\xff\r\n"
    raw_digest = store.put_blob(raw)
    assert EvidenceStore(tmp_path).get_blob(raw_digest) == raw
    with pytest.raises(TypeError, match="must be bytes"):
        store.put_blob(bytearray(raw))


def test_model_storage_revalidates_copies_and_reads_reject_noncanonical_or_wrong_schema(tmp_path):
    fixture, _, _ = captured_execution()
    store = EvidenceStore(tmp_path)
    invalid = fixture.public_task.model_copy(update={"task_id": "invalid task id"})
    with pytest.raises(ValidationError):
        store.put_model(invalid)
    assert table_counts(store) == (0, 0, 0)
    digest = store.put_model(fixture.public_task)
    with pytest.raises(EvidenceIntegrityError, match="record schema"):
        store.get_model(digest, DatasetSnapshot)
    noncanonical = json.dumps(fixture.public_task.model_dump(mode="json")).encode()
    noncanonical_digest = store.put_blob(noncanonical)
    with pytest.raises(EvidenceIntegrityError, match="not canonical"):
        store.get_model(noncanonical_digest, TaskSpec)


def test_execution_context_and_provenance_are_verified_and_retry_events_are_unique(tmp_path):
    fixture, result, receipt = captured_execution()
    store = EvidenceStore(tmp_path)
    started = datetime.now(UTC)
    store.record_execution(receipt, result, fixture.snapshot, fixture.public_task)
    store.record_execution(receipt, result, fixture.snapshot, fixture.public_task)
    assert store.get_execution_context(receipt.execution_id) == (
        receipt,
        result,
        fixture.snapshot,
        fixture.public_task,
    )
    receipt_hash = hashlib.sha256(canonical_json_bytes(receipt)).hexdigest()
    assert store.get_dependencies(receipt_hash) == tuple(
        sorted(
            (
                receipt.snapshot_manifest_sha256,
                fixture.snapshot.task_sha256,
                receipt.output_sha256,
            )
        )
    )
    events = store.get_events()
    assert len(events) == 1
    assert events[0].event_type == "execution.recorded"
    assert events[0].artifact_sha256 == receipt_hash
    assert started <= events[0].occurred_at <= datetime.now(UTC)
    assert events[0].event_id.startswith("event-")
    assert EvidenceStore(tmp_path).get_events() == events


def test_dependency_graph_handles_diamonds_and_rejects_cycles_and_missing_inputs(tmp_path):
    store = EvidenceStore(tmp_path)
    source, left, right, report, unrelated = (store.put_blob(bytes([n])) for n in range(5))
    for parent, child in ((source, left), (source, right), (left, report), (right, report)):
        store.add_dependency(parent, child)
    store.add_dependency(left, report)
    assert store.get_dependencies(report) == tuple(sorted((left, right)))
    assert store.get_dependents(source) == tuple(sorted((left, right, report)))
    assert store.get_dependents(source, transitive=False) == tuple(sorted((left, right)))
    assert store.get_dependents(unrelated) == ()
    for parent, child in ((report, source), (source, source), (report, left)):
        with pytest.raises(EvidenceIntegrityError, match="cycle"):
            store.add_dependency(parent, child)
    with pytest.raises(EvidenceIntegrityError, match="missing"):
        store.add_dependency(source, "0" * 64)
    assert store.get_dependents(source) == tuple(sorted((left, right, report)))


def test_shared_host_transaction_rolls_back_models_edges_events_and_other_records(tmp_path):
    fixture, _, _ = captured_execution()
    store = EvidenceStore(tmp_path)
    with store.transaction() as connection:
        connection.execute("CREATE TABLE host_test_records (artifact_sha256 TEXT)")
    with pytest.raises(RuntimeError, match="interrupted"), store.transaction() as connection:
        task_hash = store._put_model(connection, fixture.public_task)
        payload_hash = store._put_artifact(connection, b"uncommitted payload")
        store._add_dependency(connection, task_hash, payload_hash)
        store._record_event(connection, "host.recorded", payload_hash, fixture.public_task)
        connection.execute("INSERT INTO host_test_records VALUES (?)", (payload_hash,))
        raise RuntimeError("interrupted")
    assert table_counts(store) == (0, 0, 0)
    assert store.get_events() == ()
    with sqlite3.connect(store.database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM host_test_records").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM dependency_edges").fetchone()[0] == 0


def test_shared_transactions_enable_foreign_keys_and_commit_related_writes(tmp_path):
    store = EvidenceStore(tmp_path)
    with store.transaction() as connection:
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        parent = store._put_artifact(connection, b"source")
        child = store._put_artifact(connection, b"report")
        store._add_dependency(connection, parent, child)
        event = store._record_event(connection, "report.recorded", child)
    assert store.get_dependents(parent) == (child,)
    assert store.get_events() == (event,)
    with pytest.raises(sqlite3.IntegrityError), store.transaction() as connection:
        connection.execute("DELETE FROM artifacts WHERE sha256 = ?", (parent,))
    assert store.get_blob(parent) == b"source"


def test_host_event_identifiers_are_unique_immutable_and_bind_verified_context(tmp_path):
    fixture, _, _ = captured_execution()
    store = EvidenceStore(tmp_path)
    artifact = store.put_blob(b"rendered report")
    first = store.record_event("report.created", artifact, fixture.public_task)
    second = store.record_event("report.created", artifact, fixture.public_task)
    assert first.event_id != second.event_id
    assert first.details_sha256 == second.details_sha256
    assert store.get_model(first.details_sha256, TaskSpec) == fixture.public_task
    assert store.get_events() == (first, second)
    with pytest.raises(FrozenInstanceError):
        first.event_id = "actor-selected-id"
    with pytest.raises(EvidenceIntegrityError, match="missing"):
        store.record_event("report.created", "0" * 64)
    with pytest.raises(ValueError, match="bounded lowercase"):
        store.record_event("not a valid event")
    assert store.get_events() == (first, second)


def test_failed_execution_event_insert_rolls_back_every_dependency_and_artifact(tmp_path):
    fixture, result, receipt = captured_execution()
    store = EvidenceStore(tmp_path)
    with sqlite3.connect(store.database_path) as connection:
        connection.execute(
            "CREATE TRIGGER reject_event BEFORE INSERT ON evidence_events "
            "BEGIN SELECT RAISE(ABORT, 'simulated event failure'); END"
        )
    with pytest.raises(sqlite3.IntegrityError, match="simulated event failure"):
        store.record_execution(receipt, result, fixture.snapshot, fixture.public_task)
    assert table_counts(store) == (0, 0, 0)
    assert store.get_events() == ()
    with sqlite3.connect(store.database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM dependency_edges").fetchone()[0] == 0


PUBLICATION_TABLES = (
    "source_registry",
    "source_snapshots",
    "run_leases",
    "attempts",
    "report_revisions",
    "claims",
    "approvals",
    "releases",
    "latest_releases",
    "reviews",
)


def make_legacy_database(tmp_path):
    """Remove only Phase 3 additions to reproduce a real schema-1 evidence DB."""

    fixture, result, receipt = captured_execution()
    store = EvidenceStore(tmp_path)
    store.record_execution(receipt, result, fixture.snapshot, fixture.public_task)
    with sqlite3.connect(store.database_path) as connection:
        original_records = {
            table: connection.execute(f"SELECT * FROM {table}").fetchall()
            for table in ("artifacts", "results", "executions")
        }
        for table in (*reversed(PUBLICATION_TABLES), "dependency_edges", "evidence_events"):
            connection.execute(f"DROP TABLE {table}")
        connection.execute("PRAGMA user_version=1")
    return fixture, result, receipt, original_records


def test_schema_one_recovery_preserves_original_bytes_and_backfills_only_real_provenance(tmp_path):
    fixture, result, receipt, original_records = make_legacy_database(tmp_path)
    store = EvidenceStore(tmp_path)
    assert store.get_execution_context(receipt.execution_id) == (
        receipt,
        result,
        fixture.snapshot,
        fixture.public_task,
    )
    receipt_hash = hashlib.sha256(canonical_json_bytes(receipt)).hexdigest()
    assert receipt_hash in store.get_dependents(receipt.snapshot_manifest_sha256)
    assert store.get_events() == ()
    with sqlite3.connect(store.database_path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        for table, records in original_records.items():
            assert connection.execute(f"SELECT * FROM {table}").fetchall() == records
        for table in PUBLICATION_TABLES:
            assert connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
    assert EvidenceStore(tmp_path).get_execution(receipt.execution_id) == receipt
    with sqlite3.connect(store.database_path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION


def test_corrupt_legacy_evidence_does_not_partially_migrate_or_invent_dependencies(tmp_path):
    _, _, receipt, _ = make_legacy_database(tmp_path)
    database_path = tmp_path / "evidence.sqlite3"
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "UPDATE artifacts SET content = ? WHERE sha256 = ?",
            (b"corrupted manifest", receipt.snapshot_manifest_sha256),
        )
    with pytest.raises(EvidenceIntegrityError, match="content hash changed"):
        EvidenceStore(tmp_path)
    with sqlite3.connect(database_path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM executions").fetchone()[0] == 1
        added = ("dependency_edges", "evidence_events", *PUBLICATION_TABLES)
        assert (
            connection.execute(
                f"SELECT name FROM sqlite_master WHERE name IN ({', '.join('?' for _ in added)})",
                added,
            ).fetchall()
            == []
        )


def test_dependency_and_event_reads_detect_corrupted_bound_artifacts(tmp_path):
    store = EvidenceStore(tmp_path)
    parent = store.put_blob(b"source")
    child = store.put_blob(b"report")
    store.add_dependency(parent, child)
    store.record_event("report.created", child)
    with sqlite3.connect(store.database_path) as connection:
        connection.execute("UPDATE artifacts SET content = ? WHERE sha256 = ?", (b"bad", child))
    for read in (lambda: store.get_dependents(parent), lambda: store.get_events()):
        with pytest.raises(EvidenceIntegrityError, match="content hash changed"):
            read()
