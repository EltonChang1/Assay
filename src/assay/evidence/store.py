"""Transactional, content-addressed local execution evidence.

This store is a trusted-host API. A database and its artifacts must be outside
actor mounts. Hash verification detects changes; it does not replace that access
boundary or implement publication authority.
"""

from __future__ import annotations

import hashlib
import re
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError

from assay.contracts import DatasetSnapshot, TaskSpec, VersionedModel, canonical_json_bytes
from assay.contracts.execution import ExecutionReceipt, WorkerSuccess

SCHEMA_VERSION = 3

# Version 2 adds publisher-owned indexes; version 3 adds bound reviews. Immutable
# record bytes stay in artifacts; rows hold only identities, state, and validity.
_PUBLICATION_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS source_registry ("
    "source_key TEXT PRIMARY KEY, active_snapshot_id TEXT NOT NULL, "
    "active_manifest_sha256 TEXT NOT NULL, epoch INTEGER NOT NULL CHECK(epoch > 0), "
    "FOREIGN KEY (active_manifest_sha256) REFERENCES artifacts(sha256))",
    "CREATE TABLE IF NOT EXISTS source_snapshots ("
    "source_key TEXT NOT NULL, epoch INTEGER NOT NULL, snapshot_id TEXT NOT NULL, "
    "manifest_sha256 TEXT NOT NULL, PRIMARY KEY(source_key, epoch), "
    "FOREIGN KEY (manifest_sha256) REFERENCES artifacts(sha256))",
    "CREATE TABLE IF NOT EXISTS run_leases ("
    "run_id TEXT PRIMARY KEY, active_attempt_id TEXT, "
    "fencing_token INTEGER NOT NULL CHECK(fencing_token > 0))",
    "CREATE TABLE IF NOT EXISTS attempts ("
    "attempt_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, fencing_token INTEGER NOT NULL, "
    "state TEXT NOT NULL CHECK(state IN ('running', 'canceled', 'revoked')), "
    "UNIQUE(run_id, fencing_token), FOREIGN KEY (run_id) REFERENCES run_leases(run_id))",
    "CREATE TABLE IF NOT EXISTS report_revisions ("
    "revision_id TEXT PRIMARY KEY, report_id TEXT NOT NULL, "
    "revision INTEGER NOT NULL CHECK(revision > 0), run_id TEXT NOT NULL, "
    "attempt_id TEXT NOT NULL, source_key TEXT NOT NULL, snapshot_id TEXT NOT NULL, "
    "report_semantics TEXT NOT NULL CHECK(report_semantics IN ('current', 'historical')), "
    "report_sha256 TEXT NOT NULL UNIQUE, rendered_sha256 TEXT NOT NULL, "
    "check_bundle_sha256 TEXT, status TEXT NOT NULL CHECK(status IN ("
    "'submitted', 'checked', 'approved', 'rejected', 'needs_review', 'published', 'stale')), "
    "UNIQUE(report_id, revision), "
    "FOREIGN KEY (attempt_id) REFERENCES attempts(attempt_id), "
    "FOREIGN KEY (report_sha256) REFERENCES artifacts(sha256), "
    "FOREIGN KEY (rendered_sha256) REFERENCES artifacts(sha256), "
    "FOREIGN KEY (check_bundle_sha256) REFERENCES artifacts(sha256))",
    "CREATE TABLE IF NOT EXISTS claims ("
    "claim_id TEXT PRIMARY KEY, revision_id TEXT NOT NULL, record_sha256 TEXT NOT NULL, "
    "execution_id TEXT NOT NULL, "
    "FOREIGN KEY (revision_id) REFERENCES report_revisions(revision_id), "
    "FOREIGN KEY (record_sha256) REFERENCES artifacts(sha256))",
    "CREATE TABLE IF NOT EXISTS approvals ("
    "approval_id TEXT PRIMARY KEY, revision_id TEXT NOT NULL UNIQUE, "
    "approval_sha256 TEXT NOT NULL, "
    "FOREIGN KEY (revision_id) REFERENCES report_revisions(revision_id), "
    "FOREIGN KEY (approval_sha256) REFERENCES artifacts(sha256))",
    "CREATE TABLE IF NOT EXISTS releases ("
    "release_id TEXT PRIMARY KEY, report_id TEXT NOT NULL, "
    "revision_id TEXT NOT NULL UNIQUE, approval_id TEXT NOT NULL UNIQUE, "
    "release_sha256 TEXT NOT NULL, rendered_sha256 TEXT NOT NULL, "
    "source_key TEXT NOT NULL, source_epoch INTEGER NOT NULL, "
    "validity TEXT NOT NULL CHECK(validity IN ('current', 'stale', 'historical')), "
    "FOREIGN KEY (revision_id) REFERENCES report_revisions(revision_id), "
    "FOREIGN KEY (approval_id) REFERENCES approvals(approval_id), "
    "FOREIGN KEY (release_sha256) REFERENCES artifacts(sha256), "
    "FOREIGN KEY (rendered_sha256) REFERENCES artifacts(sha256))",
    "CREATE TABLE IF NOT EXISTS latest_releases ("
    "report_id TEXT PRIMARY KEY, release_id TEXT NOT NULL UNIQUE, "
    "FOREIGN KEY (release_id) REFERENCES releases(release_id))",
    "CREATE TABLE IF NOT EXISTS reviews ("
    "revision_id TEXT PRIMARY KEY, review_sha256 TEXT NOT NULL, "
    "FOREIGN KEY (revision_id) REFERENCES report_revisions(revision_id), "
    "FOREIGN KEY (review_sha256) REFERENCES artifacts(sha256))",
)


class EvidenceIntegrityError(ValueError):
    """Persisted evidence is missing, changed, or internally inconsistent."""


class EvidenceConflictError(ValueError):
    """An existing host-generated execution ID cannot acquire different bytes."""


@dataclass(frozen=True)
class EvidenceEvent:
    """An append-only host event with optional content-addressed context."""

    event_id: str
    event_type: str
    occurred_at: datetime
    artifact_sha256: str | None
    details_sha256: str | None


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _validated[ModelT: VersionedModel](model: ModelT) -> ModelT:
    # Revalidate dictionaries because model_copy(update=...) bypasses validation.
    return type(model).model_validate(model.model_dump())


def _validate_execution(
    receipt: ExecutionReceipt,
    result: WorkerSuccess | None,
    snapshot: DatasetSnapshot,
    task: TaskSpec,
) -> None:
    if _sha256(receipt.exact_query.encode("utf-8")) != receipt.query_sha256:
        raise EvidenceIntegrityError("exact query hash disagrees with the execution receipt")
    if _sha256(canonical_json_bytes(snapshot)) != receipt.snapshot_manifest_sha256:
        raise EvidenceIntegrityError("snapshot manifest hash disagrees with the execution receipt")
    if receipt.snapshot_id != snapshot.snapshot_id:
        raise EvidenceIntegrityError("execution and snapshot identities disagree")
    if receipt.task_id != task.task_id or snapshot.task_id != task.task_id:
        raise EvidenceIntegrityError("execution, task, and snapshot identities disagree")
    if snapshot.snapshot_id not in task.permitted_snapshot_ids:
        raise EvidenceIntegrityError("snapshot is not permitted by the public task")
    if _sha256(canonical_json_bytes(task)) != snapshot.task_sha256:
        raise EvidenceIntegrityError("public task hash disagrees with the snapshot manifest")
    table_ids = {table.table_id for table in snapshot.tables}
    if not set(task.allowed_tables).issubset(table_ids):
        raise EvidenceIntegrityError("task permits a table absent from its snapshot")
    if len(set(receipt.source_ids)) != len(receipt.source_ids) or not set(
        receipt.source_ids
    ).issubset(task.allowed_tables):
        raise EvidenceIntegrityError("execution references duplicate or unpermitted source tables")
    if receipt.status == "success":
        if result is None:
            raise EvidenceIntegrityError("successful execution requires a captured result")
        output_hash = _sha256(canonical_json_bytes(result))
        if receipt.output_sha256 != output_hash or receipt.result_id != f"result-{output_hash}":
            raise EvidenceIntegrityError("captured result identity disagrees with its exact bytes")
        if receipt.row_count != result.row_count:
            raise EvidenceIntegrityError("captured result row count disagrees with its receipt")
    elif result is not None:
        raise EvidenceIntegrityError("failed executions cannot persist a successful result")


class EvidenceStore:
    """One SQLite writer transaction commits each receipt and all dependencies."""

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.database_path = self.root / "evidence.sqlite3"
        with self._connection() as connection:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version not in range(SCHEMA_VERSION + 1):
                raise EvidenceIntegrityError("unsupported evidence database schema version")
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("BEGIN IMMEDIATE")
            # Another host writer may have completed a migration while this
            # connection waited for the SQLite lock. Never downgrade its version.
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version not in range(SCHEMA_VERSION + 1):
                raise EvidenceIntegrityError("unsupported evidence database schema version")
            has_dependency_graph = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'dependency_edges'"
            ).fetchone()
            connection.execute(
                "CREATE TABLE IF NOT EXISTS artifacts ("
                "sha256 TEXT PRIMARY KEY, content BLOB NOT NULL)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS results ("
                "result_id TEXT PRIMARY KEY, artifact_sha256 TEXT NOT NULL UNIQUE, "
                "FOREIGN KEY (artifact_sha256) REFERENCES artifacts(sha256))"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS executions ("
                "execution_id TEXT PRIMARY KEY, receipt_sha256 TEXT NOT NULL, "
                "snapshot_sha256 TEXT NOT NULL, task_sha256 TEXT NOT NULL, result_id TEXT, "
                "FOREIGN KEY (receipt_sha256) REFERENCES artifacts(sha256), "
                "FOREIGN KEY (snapshot_sha256) REFERENCES artifacts(sha256), "
                "FOREIGN KEY (task_sha256) REFERENCES artifacts(sha256), "
                "FOREIGN KEY (result_id) REFERENCES results(result_id))"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS dependency_edges ("
                "parent_sha256 TEXT NOT NULL, child_sha256 TEXT NOT NULL, "
                "PRIMARY KEY(parent_sha256, child_sha256), "
                "CHECK(parent_sha256 != child_sha256), "
                "FOREIGN KEY (parent_sha256) REFERENCES artifacts(sha256), "
                "FOREIGN KEY (child_sha256) REFERENCES artifacts(sha256))"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS dependency_edges_child "
                "ON dependency_edges(child_sha256)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS evidence_events ("
                "sequence INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT NOT NULL UNIQUE, "
                "event_type TEXT NOT NULL, occurred_at TEXT NOT NULL, "
                "artifact_sha256 TEXT, details_sha256 TEXT, "
                "FOREIGN KEY (artifact_sha256) REFERENCES artifacts(sha256), "
                "FOREIGN KEY (details_sha256) REFERENCES artifacts(sha256))"
            )
            if has_dependency_graph is None:
                for (execution_id,) in connection.execute("SELECT execution_id FROM executions"):
                    receipt, result, snapshot, task = self._load_execution_context(
                        connection, execution_id
                    )
                    receipt_hash = _sha256(canonical_json_bytes(receipt))
                    dependencies = [
                        _sha256(canonical_json_bytes(snapshot)),
                        _sha256(canonical_json_bytes(task)),
                    ]
                    if result is not None:
                        dependencies.append(_sha256(canonical_json_bytes(result)))
                    for parent in dependencies:
                        self._add_dependency(connection, parent, receipt_hash)
            for statement in _PUBLICATION_SCHEMA:
                connection.execute(statement)
            if version < SCHEMA_VERSION:
                connection.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
            connection.commit()

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path, timeout=30, isolation_level=None)
        try:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA synchronous=FULL")
            yield connection
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Commit one trusted-host write atomically, including publisher records.

        Call the connection-taking helpers inside this scope instead of opening
        another store write transaction. Errors roll back every related write.
        """

        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()

    @staticmethod
    def _read_artifact(connection: sqlite3.Connection, digest: str) -> bytes:
        row = connection.execute(
            "SELECT content FROM artifacts WHERE sha256 = ?", (digest,)
        ).fetchone()
        if row is None or not isinstance(row[0], bytes) or _sha256(row[0]) != digest:
            raise EvidenceIntegrityError("evidence artifact is missing or its content hash changed")
        return row[0]

    @staticmethod
    def _read_model[ModelT: VersionedModel](
        connection: sqlite3.Connection, digest: str, model: type[ModelT]
    ) -> ModelT:
        content = EvidenceStore._read_artifact(connection, digest)
        try:
            parsed = model.model_validate_json(content)
        except ValidationError as exc:
            raise EvidenceIntegrityError(
                "evidence artifact does not match its record schema"
            ) from exc
        if canonical_json_bytes(parsed) != content:
            raise EvidenceIntegrityError("evidence artifact serialization is not canonical")
        return parsed

    @staticmethod
    def _put_artifact(connection: sqlite3.Connection, content: bytes) -> str:
        digest = _sha256(content)
        connection.execute(
            "INSERT OR IGNORE INTO artifacts(sha256, content) VALUES (?, ?)", (digest, content)
        )
        if EvidenceStore._read_artifact(connection, digest) != content:
            raise EvidenceIntegrityError("content identity conflicts with an existing artifact")
        return digest

    @staticmethod
    def _put_model[ModelT: VersionedModel](connection: sqlite3.Connection, model: ModelT) -> str:
        return EvidenceStore._put_artifact(connection, canonical_json_bytes(_validated(model)))

    def put_blob(self, content: bytes) -> str:
        """Persist exact bytes under their SHA-256; identical retries share identity."""

        if not isinstance(content, bytes):
            raise TypeError("evidence blobs must be bytes")
        with self.transaction() as connection:
            return self._put_artifact(connection, content)

    def get_blob(self, digest: str) -> bytes:
        with self._connection() as connection:
            return self._read_artifact(connection, digest)

    def put_model[ModelT: VersionedModel](self, model: ModelT) -> str:
        """Persist a revalidated immutable record using canonical serialization."""

        with self.transaction() as connection:
            return self._put_model(connection, model)

    def get_model[ModelT: VersionedModel](self, digest: str, model: type[ModelT]) -> ModelT:
        with self._connection() as connection:
            return self._read_model(connection, digest, model)

    @staticmethod
    def _get_dependents(
        connection: sqlite3.Connection, parent_sha256: str, *, transitive: bool = True
    ) -> tuple[str, ...]:
        EvidenceStore._read_artifact(connection, parent_sha256)
        if transitive:
            rows = connection.execute(
                "WITH RECURSIVE dependents(sha256) AS ("
                "SELECT child_sha256 FROM dependency_edges WHERE parent_sha256 = ? "
                "UNION SELECT edges.child_sha256 FROM dependency_edges AS edges "
                "JOIN dependents ON edges.parent_sha256 = dependents.sha256) "
                "SELECT sha256 FROM dependents ORDER BY sha256",
                (parent_sha256,),
            ).fetchall()
        else:
            rows = connection.execute(
                "SELECT child_sha256 FROM dependency_edges "
                "WHERE parent_sha256 = ? ORDER BY child_sha256",
                (parent_sha256,),
            ).fetchall()
        dependents = tuple(row[0] for row in rows)
        if parent_sha256 in dependents:
            raise EvidenceIntegrityError("dependency graph contains a cycle")
        for digest in dependents:
            EvidenceStore._read_artifact(connection, digest)
        return dependents

    @staticmethod
    def _add_dependency(
        connection: sqlite3.Connection, parent_sha256: str, child_sha256: str
    ) -> None:
        EvidenceStore._read_artifact(connection, parent_sha256)
        EvidenceStore._read_artifact(connection, child_sha256)
        if parent_sha256 == child_sha256 or parent_sha256 in EvidenceStore._get_dependents(
            connection, child_sha256
        ):
            raise EvidenceIntegrityError("dependency would create a cycle")
        connection.execute(
            "INSERT OR IGNORE INTO dependency_edges(parent_sha256, child_sha256) VALUES (?, ?)",
            (parent_sha256, child_sha256),
        )

    def add_dependency(self, parent_sha256: str, child_sha256: str) -> None:
        """Record that the child depends on the parent; cycles fail atomically."""

        with self.transaction() as connection:
            self._add_dependency(connection, parent_sha256, child_sha256)

    def get_dependencies(self, child_sha256: str) -> tuple[str, ...]:
        """Return verified direct inputs in deterministic hash order."""

        with self._connection() as connection:
            connection.execute("BEGIN")
            self._read_artifact(connection, child_sha256)
            rows = connection.execute(
                "SELECT parent_sha256 FROM dependency_edges "
                "WHERE child_sha256 = ? ORDER BY parent_sha256",
                (child_sha256,),
            ).fetchall()
            for row in rows:
                self._read_artifact(connection, row[0])
            return tuple(row[0] for row in rows)

    def get_dependents(self, parent_sha256: str, *, transitive: bool = True) -> tuple[str, ...]:
        """Return verified descendants for host-owned invalidation decisions."""

        with self._connection() as connection:
            connection.execute("BEGIN")
            return self._get_dependents(connection, parent_sha256, transitive=transitive)

    @staticmethod
    def _record_event(
        connection: sqlite3.Connection,
        event_type: str,
        artifact_sha256: str | None = None,
        details: VersionedModel | None = None,
    ) -> EvidenceEvent:
        if re.fullmatch(r"[a-z][a-z0-9_.-]{0,127}", event_type) is None:
            raise ValueError("event type must be a bounded lowercase identifier")
        if artifact_sha256 is not None:
            EvidenceStore._read_artifact(connection, artifact_sha256)
        details_sha256 = None if details is None else EvidenceStore._put_model(connection, details)
        event = EvidenceEvent(
            event_id=f"event-{uuid4().hex}",
            event_type=event_type,
            occurred_at=datetime.now(UTC),
            artifact_sha256=artifact_sha256,
            details_sha256=details_sha256,
        )
        connection.execute(
            "INSERT INTO evidence_events("
            "event_id, event_type, occurred_at, artifact_sha256, details_sha256"
            ") VALUES (?, ?, ?, ?, ?)",
            (
                event.event_id,
                event.event_type,
                event.occurred_at.isoformat(),
                event.artifact_sha256,
                event.details_sha256,
            ),
        )
        return event

    def record_event(
        self,
        event_type: str,
        artifact_sha256: str | None = None,
        details: VersionedModel | None = None,
    ) -> EvidenceEvent:
        """Append a host-ID event; this operation grants no publication authority."""

        with self.transaction() as connection:
            return self._record_event(connection, event_type, artifact_sha256, details)

    def get_events(self) -> tuple[EvidenceEvent, ...]:
        with self._connection() as connection:
            connection.execute("BEGIN")
            rows = connection.execute(
                "SELECT event_id, event_type, occurred_at, artifact_sha256, details_sha256 "
                "FROM evidence_events ORDER BY sequence"
            ).fetchall()
            events = []
            for event_id, event_type, occurred_at, artifact_sha256, details_sha256 in rows:
                for digest in (artifact_sha256, details_sha256):
                    if digest is not None:
                        self._read_artifact(connection, digest)
                try:
                    timestamp = datetime.fromisoformat(occurred_at)
                    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
                        raise ValueError("event timestamp must include an offset")
                except (TypeError, ValueError) as exc:
                    raise EvidenceIntegrityError("event timestamp is invalid") from exc
                events.append(
                    EvidenceEvent(event_id, event_type, timestamp, artifact_sha256, details_sha256)
                )
            return tuple(events)

    def record_execution(
        self,
        receipt: ExecutionReceipt,
        result: WorkerSuccess | None,
        snapshot: DatasetSnapshot,
        task: TaskSpec,
    ) -> None:
        """Commit exact host-captured bytes; identical retry is idempotent."""

        receipt = _validated(receipt)
        result = None if result is None else _validated(result)
        snapshot = _validated(snapshot)
        task = _validated(task)
        _validate_execution(receipt, result, snapshot, task)
        receipt_bytes = canonical_json_bytes(receipt)
        with self.transaction() as connection:
            existing = connection.execute(
                "SELECT receipt_sha256 FROM executions WHERE execution_id = ?",
                (receipt.execution_id,),
            ).fetchone()
            if existing is not None:
                if self._read_artifact(connection, existing[0]) != receipt_bytes:
                    raise EvidenceConflictError(
                        "execution ID already refers to a different receipt"
                    )
                self._load_execution(connection, receipt.execution_id)
                return
            receipt_hash = self._put_artifact(connection, receipt_bytes)
            snapshot_hash = self._put_artifact(connection, canonical_json_bytes(snapshot))
            task_hash = self._put_artifact(connection, canonical_json_bytes(task))
            if result is not None:
                result_hash = self._put_artifact(connection, canonical_json_bytes(result))
                connection.execute(
                    "INSERT OR IGNORE INTO results(result_id, artifact_sha256) VALUES (?, ?)",
                    (receipt.result_id, result_hash),
                )
                loaded_result = self._load_result(connection, receipt.result_id)
                if loaded_result != result:
                    raise EvidenceIntegrityError(
                        "result identity conflicts with the captured output"
                    )
            connection.execute(
                "INSERT INTO executions("
                "execution_id, receipt_sha256, snapshot_sha256, task_sha256, result_id"
                ") VALUES (?, ?, ?, ?, ?)",
                (receipt.execution_id, receipt_hash, snapshot_hash, task_hash, receipt.result_id),
            )
            for parent in (snapshot_hash, task_hash):
                self._add_dependency(connection, parent, receipt_hash)
            if result is not None:
                self._add_dependency(connection, result_hash, receipt_hash)
            self._record_event(connection, "execution.recorded", receipt_hash)

    def _load_result(self, connection: sqlite3.Connection, result_id: str | None) -> WorkerSuccess:
        row = connection.execute(
            "SELECT artifact_sha256 FROM results WHERE result_id = ?", (result_id,)
        ).fetchone()
        if row is None:
            raise KeyError("unknown result ID")
        if result_id != f"result-{row[0]}":
            raise EvidenceIntegrityError("result index disagrees with its content identity")
        return self._read_model(connection, row[0], WorkerSuccess)

    def _load_execution(
        self, connection: sqlite3.Connection, execution_id: str
    ) -> ExecutionReceipt:
        return self._load_execution_context(connection, execution_id)[0]

    def _load_execution_context(
        self, connection: sqlite3.Connection, execution_id: str
    ) -> tuple[ExecutionReceipt, WorkerSuccess | None, DatasetSnapshot, TaskSpec]:
        row = connection.execute(
            "SELECT receipt_sha256, snapshot_sha256, task_sha256, result_id "
            "FROM executions WHERE execution_id = ?",
            (execution_id,),
        ).fetchone()
        if row is None:
            raise KeyError("unknown execution ID")
        receipt = self._read_model(connection, row[0], ExecutionReceipt)
        snapshot = self._read_model(connection, row[1], DatasetSnapshot)
        task = self._read_model(connection, row[2], TaskSpec)
        try:
            result = None if row[3] is None else self._load_result(connection, row[3])
        except KeyError as exc:
            raise EvidenceIntegrityError("execution references a missing captured result") from exc
        if receipt.execution_id != execution_id or receipt.result_id != row[3]:
            raise EvidenceIntegrityError("execution index disagrees with its receipt")
        _validate_execution(receipt, result, snapshot, task)
        return receipt, result, snapshot, task

    def get_execution(self, execution_id: str) -> ExecutionReceipt:
        with self._connection() as connection:
            connection.execute("BEGIN")
            return self._load_execution(connection, execution_id)

    def get_execution_context(
        self, execution_id: str
    ) -> tuple[ExecutionReceipt, WorkerSuccess | None, DatasetSnapshot, TaskSpec]:
        """Read and verify all public evidence for one authoritative execution."""

        with self._connection() as connection:
            connection.execute("BEGIN")
            return self._load_execution_context(connection, execution_id)

    def get_result(self, result_id: str) -> WorkerSuccess:
        with self._connection() as connection:
            connection.execute("BEGIN")
            return self._load_result(connection, result_id)
