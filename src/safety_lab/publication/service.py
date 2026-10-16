"""The single trusted release path: revision-bound, attempt-fenced, epoch-checked.

Every state change happens inside one SQLite writer transaction that re-reads
the active attempt, revision state, and source registry before committing.
Rendered bytes are stored when a revision is submitted, but nothing is served
until a committed release row references them, so an interrupted publication
leaves no visible output. Researcher audit exports are separate projections.
"""

from __future__ import annotations

import hashlib
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import uuid4

from pydantic import Field

from safety_lab.contracts import DatasetSnapshot, TaskSpec, VersionedModel, canonical_json_bytes
from safety_lab.contracts.report import (
    ApprovalRecord,
    AuditBundle,
    CheckBundle,
    ClaimInput,
    ClaimRecord,
    ExecutionEvidence,
    PublicationDecision,
    ReleaseRecord,
    ReportRevision,
)
from safety_lab.contracts.task import Identifier, NonEmpty
from safety_lab.evidence.store import EvidenceIntegrityError, EvidenceStore
from safety_lab.verification import CHECKER_VERSION, required_check_keys, verify_report

from .rendering import render_report

POLICY_VERSION = "publication-policy-1.0"
PolicyProfile = Literal["checked", "baseline"]
PolicyOutcome = Literal["approved", "rejected", "needs_review"]
Validity = Literal["current", "stale", "historical"]
_PENDING = ("submitted", "checked", "approved")


class PublicationError(RuntimeError):
    """The trusted publisher refused a state change; nothing was released."""


class FencingError(PublicationError):
    """The caller's attempt is no longer the run's active, unrevoked attempt."""


class StaleSourceError(PublicationError):
    """The registered source changed after this revision was created or approved."""


class InvalidTransitionError(PublicationError):
    """The revision is not in the state this operation requires."""


class StaleReportError(PublicationError):
    """Ordinary access to a superseded current-data release; use archival access."""


class AttemptEvent(VersionedModel):
    run_id: Identifier
    attempt_id: Identifier
    fencing_token: Annotated[int, Field(strict=True, gt=0)]
    state: Literal["running", "canceled", "revoked"]


class SourceEvent(VersionedModel):
    source_key: Identifier
    snapshot_id: Identifier
    epoch: Annotated[int, Field(strict=True, gt=0)]


class StaleEvent(VersionedModel):
    source_key: Identifier
    epoch: Annotated[int, Field(strict=True, gt=0)]
    reason: NonEmpty


@dataclass(frozen=True)
class AttemptLease:
    run_id: str
    attempt_id: str
    fencing_token: int


@dataclass(frozen=True)
class Release:
    record: ReleaseRecord
    validity: Validity
    content: bytes


@dataclass(frozen=True)
class _Revision:
    revision_id: str
    report_id: str
    revision: int
    run_id: str
    attempt_id: str
    report_sha256: str
    rendered_sha256: str
    check_bundle_sha256: str | None
    status: str


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _digest(model: VersionedModel) -> str:
    return _sha256(canonical_json_bytes(model))


def _now() -> datetime:
    return datetime.now(UTC)


def evaluate_policy(
    report: ReportRevision, checks: CheckBundle, profile: PolicyProfile
) -> tuple[PolicyOutcome, tuple[str, ...]]:
    """Apply the frozen release rule; absent or duplicated checks never pass.

    Host integrity is mandatory in every profile and cannot be overridden. The
    ``checked`` profile also requires every research check to pass; ``baseline``
    (arm A) records them without using them. Advisory checks never authorize.
    """

    if checks.report_sha256 != _digest(report) or checks.report_revision_id != report.revision_id:
        return "needs_review", ("check_bundle_binding",)
    required = {
        key
        for key in required_check_keys(report)
        if profile == "checked" or key[0] == "host_integrity"
    }
    found: dict[tuple[str, str, str | None], list[str]] = {}
    reasons: list[str] = []
    unknown = failed = False
    for check in checks.checks:
        if check.checker_version != CHECKER_VERSION:
            reasons.append(f"checker_version:{check.name}")
            unknown = True
        found.setdefault((check.check_class, check.name, check.claim_slot_id), []).append(
            check.outcome
        )
    for key in sorted(required, key=lambda item: (item[0], item[1], item[2] or "")):
        label = f"{key[1]}:{key[2] or 'report'}"
        outcomes = found.get(key, [])
        if len(outcomes) != 1:
            reasons.append(f"coverage:{label}")
            unknown = True
        elif outcomes[0] == "fail":
            reasons.append(f"fail:{label}")
            failed = True
        elif outcomes[0] == "unknown":
            reasons.append(f"unknown:{label}")
            unknown = True
    outcome: PolicyOutcome = "rejected" if failed else "needs_review" if unknown else "approved"
    return outcome, tuple(reasons)


class Publisher:
    """Trusted-host publication authority over one evidence store."""

    def __init__(self, evidence: EvidenceStore):
        self.evidence = evidence

    # Attempt leases -----------------------------------------------------

    def start_attempt(self, run_id: str) -> AttemptLease:
        """Issue a new fencing token, revoking any previously active attempt."""

        AttemptEvent(run_id=run_id, attempt_id="attempt-pending", fencing_token=1, state="running")
        with self.evidence.transaction() as connection:
            row = connection.execute(
                "SELECT active_attempt_id, fencing_token FROM run_leases WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            token = 1 if row is None else row[1] + 1
            if row is not None and row[0] is not None:
                connection.execute(
                    "UPDATE attempts SET state = 'revoked' WHERE attempt_id = ?", (row[0],)
                )
                self._attempt_event(connection, run_id, row[0], row[1], "revoked")
            connection.execute(
                "INSERT INTO run_leases(run_id, active_attempt_id, fencing_token) "
                "VALUES (?, NULL, ?) ON CONFLICT(run_id) DO UPDATE SET "
                "active_attempt_id = NULL, fencing_token = excluded.fencing_token",
                (run_id, token),
            )
            lease = AttemptLease(run_id, "attempt-" + uuid4().hex, token)
            connection.execute(
                "INSERT INTO attempts(attempt_id, run_id, fencing_token, state) "
                "VALUES (?, ?, ?, 'running')",
                (lease.attempt_id, run_id, token),
            )
            connection.execute(
                "UPDATE run_leases SET active_attempt_id = ? WHERE run_id = ?",
                (lease.attempt_id, run_id),
            )
            self._attempt_event(connection, run_id, lease.attempt_id, token, "running")
        return lease

    def cancel_attempt(self, lease: AttemptLease) -> None:
        with self.evidence.transaction() as connection:
            self._require_lease(connection, lease)
            connection.execute(
                "UPDATE attempts SET state = 'canceled' WHERE attempt_id = ?", (lease.attempt_id,)
            )
            connection.execute(
                "UPDATE run_leases SET active_attempt_id = NULL WHERE run_id = ?", (lease.run_id,)
            )
            self._attempt_event(
                connection, lease.run_id, lease.attempt_id, lease.fencing_token, "canceled"
            )

    def _attempt_event(
        self,
        connection: sqlite3.Connection,
        run_id: str,
        attempt_id: str,
        token: int,
        state: Literal["running", "canceled", "revoked"],
    ) -> None:
        details = AttemptEvent(
            run_id=run_id, attempt_id=attempt_id, fencing_token=token, state=state
        )
        self.evidence._record_event(connection, f"attempt.{state}", details=details)

    @staticmethod
    def _require_lease(connection: sqlite3.Connection, lease: AttemptLease) -> None:
        row = connection.execute(
            "SELECT leases.active_attempt_id, leases.fencing_token, attempts.state "
            "FROM run_leases AS leases JOIN attempts "
            "ON attempts.attempt_id = leases.active_attempt_id WHERE leases.run_id = ?",
            (lease.run_id,),
        ).fetchone()
        if row is None or (row[0], row[1], row[2]) != (
            lease.attempt_id,
            lease.fencing_token,
            "running",
        ):
            raise FencingError("attempt lease is revoked, canceled, or not the active attempt")

    # Source registry ----------------------------------------------------

    def register_source(self, source_key: str, snapshot: DatasetSnapshot) -> int:
        """Make ``snapshot`` active; a change advances the epoch and invalidates.

        Current-data releases on the old epoch become stale (history is kept)
        and unreleased current-data revisions can no longer be approved or
        published. Re-registering the active snapshot is an idempotent no-op.
        """

        snapshot = DatasetSnapshot.model_validate(snapshot.model_dump())
        with self.evidence.transaction() as connection:
            row = connection.execute(
                "SELECT active_snapshot_id, epoch FROM source_registry WHERE source_key = ?",
                (source_key,),
            ).fetchone()
            if row is not None and row[0] == snapshot.snapshot_id:
                return int(row[1])
            epoch = 1 if row is None else int(row[1]) + 1
            details = SourceEvent(
                source_key=source_key, snapshot_id=snapshot.snapshot_id, epoch=epoch
            )
            manifest = self.evidence._put_model(connection, snapshot)
            connection.execute(
                "INSERT INTO source_registry(source_key, active_snapshot_id, "
                "active_manifest_sha256, epoch) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(source_key) DO UPDATE SET active_snapshot_id = excluded."
                "active_snapshot_id, active_manifest_sha256 = excluded.active_manifest_sha256, "
                "epoch = excluded.epoch",
                (source_key, snapshot.snapshot_id, manifest, epoch),
            )
            connection.execute(
                "INSERT INTO source_snapshots(source_key, epoch, snapshot_id, manifest_sha256) "
                "VALUES (?, ?, ?, ?)",
                (source_key, epoch, snapshot.snapshot_id, manifest),
            )
            self.evidence._record_event(connection, "source.registered", manifest, details)
            if row is not None:
                self._invalidate(connection, source_key, epoch)
        return epoch

    def _invalidate(self, connection: sqlite3.Connection, source_key: str, epoch: int) -> None:
        details = StaleEvent(
            source_key=source_key, epoch=epoch, reason="registered active snapshot changed"
        )
        releases = connection.execute(
            "SELECT release_id, release_sha256 FROM releases "
            "WHERE source_key = ? AND validity = 'current' ORDER BY release_id",
            (source_key,),
        ).fetchall()
        for release_id, release_sha256 in releases:
            connection.execute(
                "UPDATE releases SET validity = 'stale' WHERE release_id = ?", (release_id,)
            )
            connection.execute("DELETE FROM latest_releases WHERE release_id = ?", (release_id,))
            self.evidence._record_event(connection, "release.stale", release_sha256, details)
        pending = connection.execute(
            "SELECT revision_id, report_sha256 FROM report_revisions WHERE source_key = ? "
            "AND report_semantics = 'current' AND status IN (?, ?, ?) ORDER BY revision_id",
            (source_key, *_PENDING),
        ).fetchall()
        for revision_id, report_sha256 in pending:
            connection.execute(
                "UPDATE report_revisions SET status = 'stale' WHERE revision_id = ?",
                (revision_id,),
            )
            self.evidence._record_event(connection, "report.stale", report_sha256, details)

    @staticmethod
    def _source_problem(connection: sqlite3.Connection, report: ReportRevision) -> str | None:
        row = connection.execute(
            "SELECT active_snapshot_id, epoch FROM source_registry WHERE source_key = ?",
            (report.source_key,),
        ).fetchone()
        if row is None:
            return "source_unregistered"
        if report.task.report_semantics == "current":
            if (row[0], row[1]) != (report.snapshot_id, report.source_epoch):
                return "source_epoch_changed"
            return None
        known = connection.execute(
            "SELECT 1 FROM source_snapshots WHERE source_key = ? AND snapshot_id = ? "
            "AND epoch <= ?",
            (report.source_key, report.snapshot_id, report.source_epoch),
        ).fetchone()
        return None if known is not None else "historical_snapshot_unregistered"

    # Revision lifecycle -------------------------------------------------

    def submit_report(
        self,
        lease: AttemptLease,
        *,
        report_id: str,
        source_key: str,
        task: TaskSpec,
        snapshot: DatasetSnapshot,
        claims: Sequence[ClaimInput],
    ) -> ReportRevision:
        """Record a new immutable revision from the episode's assigned inputs.

        ``task`` and ``snapshot`` come from the trusted runner, never from the
        analyst. Claims citing other evidence are recorded and fail checks.
        Output-schema violations (unlisted or contradictory slots) raise.
        """

        task = TaskSpec.model_validate(task.model_dump())
        snapshot = DatasetSnapshot.model_validate(snapshot.model_dump())
        records = tuple(
            ClaimRecord(
                claim=item.claim, execution_id=item.execution_id, claim_id="claim-" + uuid4().hex
            )
            for item in (ClaimInput.model_validate(claim.model_dump()) for claim in claims)
        )
        rendered = render_report(task, records)
        with self.evidence.transaction() as connection:
            self._require_lease(connection, lease)
            registry = connection.execute(
                "SELECT epoch FROM source_registry WHERE source_key = ?", (source_key,)
            ).fetchone()
            if registry is None:
                raise PublicationError("report source key is not registered")
            revision = connection.execute(
                "SELECT COALESCE(MAX(revision), 0) + 1 FROM report_revisions WHERE report_id = ?",
                (report_id,),
            ).fetchone()[0]
            report = ReportRevision(
                revision_id="revision-" + uuid4().hex,
                report_id=report_id,
                revision=revision,
                run_id=lease.run_id,
                attempt_id=lease.attempt_id,
                fencing_token=lease.fencing_token,
                source_key=source_key,
                source_epoch=registry[0],
                task=task,
                snapshot=snapshot,
                claims=records,
                rendered_sha256=_sha256(rendered),
                created_at=_now(),
            )
            problem = self._source_problem(connection, report)
            if problem is not None:
                raise StaleSourceError(f"report inputs are not registered as valid: {problem}")
            report_sha256 = self.evidence._put_model(connection, report)
            rendered_sha256 = self.evidence._put_artifact(connection, rendered)
            connection.execute(
                "INSERT INTO report_revisions(revision_id, report_id, revision, run_id, "
                "attempt_id, source_key, snapshot_id, report_semantics, report_sha256, "
                "rendered_sha256, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'submitted')",
                (
                    report.revision_id,
                    report_id,
                    revision,
                    lease.run_id,
                    lease.attempt_id,
                    source_key,
                    snapshot.snapshot_id,
                    task.report_semantics,
                    report_sha256,
                    rendered_sha256,
                ),
            )
            for record in records:
                record_sha256 = self.evidence._put_model(connection, record)
                connection.execute(
                    "INSERT INTO claims(claim_id, revision_id, record_sha256, execution_id) "
                    "VALUES (?, ?, ?, ?)",
                    (record.claim_id, report.revision_id, record_sha256, record.execution_id),
                )
                self.evidence._add_dependency(connection, record_sha256, report_sha256)
                receipt = connection.execute(
                    "SELECT receipt_sha256 FROM executions WHERE execution_id = ?",
                    (record.execution_id,),
                ).fetchone()
                if receipt is not None:
                    self.evidence._add_dependency(connection, receipt[0], record_sha256)
            self.evidence._add_dependency(connection, report_sha256, rendered_sha256)
            self.evidence._record_event(connection, "report.submitted", report_sha256)
        return report

    def check_report(self, lease: AttemptLease, revision_id: str) -> CheckBundle:
        """Run the public checker on stored bytes and bind its bundle to them."""

        with self.evidence._connection() as connection:
            connection.execute("BEGIN")
            row = self._owned_revision(connection, lease, revision_id, "submitted")
            report = self.evidence._read_model(connection, row.report_sha256, ReportRevision)
        bundle = verify_report(report, self.evidence)
        with self.evidence.transaction() as connection:
            row = self._owned_revision(connection, lease, revision_id, "submitted")
            bundle_sha256 = self.evidence._put_model(connection, bundle)
            self.evidence._add_dependency(connection, row.report_sha256, bundle_sha256)
            connection.execute(
                "UPDATE report_revisions SET check_bundle_sha256 = ?, status = 'checked' "
                "WHERE revision_id = ?",
                (bundle_sha256, revision_id),
            )
            self.evidence._record_event(connection, "report.checked", bundle_sha256)
        return bundle

    def decide(
        self, lease: AttemptLease, revision_id: str, policy_profile: PolicyProfile
    ) -> PublicationDecision:
        """Apply the frozen policy; only an approval can later be published."""

        with self.evidence.transaction() as connection:
            row = self._owned_revision(connection, lease, revision_id, "checked")
            assert row.check_bundle_sha256 is not None
            report = self.evidence._read_model(connection, row.report_sha256, ReportRevision)
            bundle = self.evidence._read_model(connection, row.check_bundle_sha256, CheckBundle)
            problem = self._source_problem(connection, report)
            outcome: Literal["approved", "rejected", "needs_review", "stale"]
            reasons: tuple[str, ...]
            if problem is not None:
                outcome, reasons = "stale", (problem,)
            else:
                outcome, reasons = evaluate_policy(report, bundle, policy_profile)
            decision = PublicationDecision(
                decision_id="decision-" + uuid4().hex,
                report_revision_id=revision_id,
                report_sha256=row.report_sha256,
                check_bundle_sha256=row.check_bundle_sha256,
                policy_profile=policy_profile,
                policy_version=POLICY_VERSION,
                outcome=outcome,
                reasons=reasons,
                source_epoch=report.source_epoch,
                attempt_id=lease.attempt_id,
                fencing_token=lease.fencing_token,
                created_at=_now(),
            )
            decision_sha256 = self.evidence._put_model(connection, decision)
            self.evidence._add_dependency(connection, row.check_bundle_sha256, decision_sha256)
            connection.execute(
                "UPDATE report_revisions SET status = ? WHERE revision_id = ?",
                (outcome, revision_id),
            )
            if outcome == "approved":
                approval = ApprovalRecord(
                    approval_id="approval-" + uuid4().hex,
                    report_revision_id=revision_id,
                    report_sha256=row.report_sha256,
                    rendered_sha256=row.rendered_sha256,
                    check_bundle_sha256=row.check_bundle_sha256,
                    policy_profile=policy_profile,
                    policy_version=POLICY_VERSION,
                    source_epoch=report.source_epoch,
                    attempt_id=lease.attempt_id,
                    fencing_token=lease.fencing_token,
                    created_at=decision.created_at,
                )
                approval_sha256 = self.evidence._put_model(connection, approval)
                connection.execute(
                    "INSERT INTO approvals(approval_id, revision_id, approval_sha256) "
                    "VALUES (?, ?, ?)",
                    (approval.approval_id, revision_id, approval_sha256),
                )
                self.evidence._add_dependency(connection, decision_sha256, approval_sha256)
            self.evidence._record_event(connection, "report.decided", decision_sha256)
        return decision

    def publish(self, lease: AttemptLease, revision_id: str) -> ReleaseRecord:
        """Atomically release exact approved bytes; an identical retry is idempotent."""

        stale = False
        with self.evidence.transaction() as connection:
            row = self._owned_revision(connection, lease, revision_id, "approved", "published")
            if row.status == "published":
                existing = connection.execute(
                    "SELECT release_sha256 FROM releases WHERE revision_id = ?", (revision_id,)
                ).fetchone()
                if existing is None:
                    raise EvidenceIntegrityError("published revision has no release record")
                return self.evidence._read_model(connection, existing[0], ReleaseRecord)
            approval_row = connection.execute(
                "SELECT approval_sha256 FROM approvals WHERE revision_id = ?", (revision_id,)
            ).fetchone()
            if approval_row is None:
                raise EvidenceIntegrityError("approved revision has no approval record")
            approval = self.evidence._read_model(connection, approval_row[0], ApprovalRecord)
            report = self.evidence._read_model(connection, row.report_sha256, ReportRevision)
            if (
                approval.report_sha256,
                approval.rendered_sha256,
                approval.check_bundle_sha256,
                approval.policy_version,
            ) != (
                row.report_sha256,
                report.rendered_sha256,
                row.check_bundle_sha256,
                POLICY_VERSION,
            ) or row.rendered_sha256 != report.rendered_sha256:
                raise EvidenceIntegrityError("approval no longer binds this exact revision")
            if (approval.attempt_id, approval.fencing_token) != (
                lease.attempt_id,
                lease.fencing_token,
            ):
                raise FencingError("approval belongs to a different attempt token")
            assert row.check_bundle_sha256 is not None
            self.evidence._read_model(connection, row.check_bundle_sha256, CheckBundle)
            self.evidence._read_artifact(connection, row.rendered_sha256)
            if _sha256(render_report(report.task, report.claims)) != row.rendered_sha256:
                raise EvidenceIntegrityError("approved claims no longer render the approved bytes")
            problem = self._source_problem(connection, report)
            if problem is not None:
                connection.execute(
                    "UPDATE report_revisions SET status = 'stale' WHERE revision_id = ?",
                    (revision_id,),
                )
                details = StaleEvent(
                    source_key=report.source_key, epoch=max(1, report.source_epoch), reason=problem
                )
                self.evidence._record_event(connection, "report.stale", row.report_sha256, details)
                stale = True
            else:
                release = ReleaseRecord(
                    release_id="release-" + uuid4().hex,
                    report_revision_id=revision_id,
                    approval_id=approval.approval_id,
                    rendered_sha256=row.rendered_sha256,
                    published_at=_now(),
                )
                release_sha256 = self.evidence._put_model(connection, release)
                connection.execute(
                    "INSERT INTO releases(release_id, report_id, revision_id, approval_id, "
                    "release_sha256, rendered_sha256, source_key, source_epoch, validity) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        release.release_id,
                        row.report_id,
                        revision_id,
                        approval.approval_id,
                        release_sha256,
                        row.rendered_sha256,
                        report.source_key,
                        report.source_epoch,
                        "current" if report.task.report_semantics == "current" else "historical",
                    ),
                )
                latest = connection.execute(
                    "SELECT revisions.revision FROM latest_releases AS latest "
                    "JOIN releases ON releases.release_id = latest.release_id "
                    "JOIN report_revisions AS revisions "
                    "ON revisions.revision_id = releases.revision_id "
                    "WHERE latest.report_id = ?",
                    (row.report_id,),
                ).fetchone()
                if latest is None or latest[0] < row.revision:
                    connection.execute(
                        "INSERT INTO latest_releases(report_id, release_id) VALUES (?, ?) "
                        "ON CONFLICT(report_id) DO UPDATE SET release_id = excluded.release_id",
                        (row.report_id, release.release_id),
                    )
                connection.execute(
                    "UPDATE report_revisions SET status = 'published' WHERE revision_id = ?",
                    (revision_id,),
                )
                self.evidence._add_dependency(connection, approval_row[0], release_sha256)
                self.evidence._add_dependency(connection, row.rendered_sha256, release_sha256)
                self.evidence._record_event(connection, "report.published", release_sha256)
        if stale:
            raise StaleSourceError("registered source changed after approval; nothing released")
        return release

    def _owned_revision(
        self,
        connection: sqlite3.Connection,
        lease: AttemptLease,
        revision_id: str,
        *statuses: str,
    ) -> _Revision:
        self._require_lease(connection, lease)
        row = self._revision(connection, revision_id)
        if (row.run_id, row.attempt_id) != (lease.run_id, lease.attempt_id):
            raise FencingError("revision belongs to a different run attempt")
        if row.status not in statuses:
            raise InvalidTransitionError(
                f"revision is {row.status}; operation requires {' or '.join(statuses)}"
            )
        return row

    @staticmethod
    def _revision(connection: sqlite3.Connection, revision_id: str) -> _Revision:
        row = connection.execute(
            "SELECT revision_id, report_id, revision, run_id, attempt_id, report_sha256, "
            "rendered_sha256, check_bundle_sha256, status FROM report_revisions "
            "WHERE revision_id = ?",
            (revision_id,),
        ).fetchone()
        if row is None:
            raise KeyError("unknown report revision")
        return _Revision(*row)

    # Read paths ---------------------------------------------------------

    def revision_status(self, revision_id: str) -> str:
        with self.evidence._connection() as connection:
            return self._revision(connection, revision_id).status

    def read_current(self, report_id: str) -> Release | None:
        """Ordinary access: the newest non-stale release, or nothing."""

        with self.evidence._connection() as connection:
            connection.execute("BEGIN")
            row = connection.execute(
                "SELECT release_id FROM latest_releases WHERE report_id = ?", (report_id,)
            ).fetchone()
            return None if row is None else self._load_release(connection, row[0], False)

    def read_release(self, release_id: str, *, archival: bool = False) -> Release:
        """Stale releases need explicit archival access; original bytes are retained."""

        with self.evidence._connection() as connection:
            connection.execute("BEGIN")
            return self._load_release(connection, release_id, archival)

    def _load_release(
        self, connection: sqlite3.Connection, release_id: str, archival: bool
    ) -> Release:
        row = connection.execute(
            "SELECT release_sha256, rendered_sha256, validity FROM releases WHERE release_id = ?",
            (release_id,),
        ).fetchone()
        if row is None:
            raise KeyError("unknown release")
        if row[2] == "stale" and not archival:
            raise StaleReportError("release is stale; request archival access explicitly")
        record = self.evidence._read_model(connection, row[0], ReleaseRecord)
        if (record.release_id, record.rendered_sha256) != (release_id, row[1]):
            raise EvidenceIntegrityError("release index disagrees with its record")
        return Release(record, row[2], self.evidence._read_artifact(connection, row[1]))

    def audit_bundle(self, revision_id: str, limitations: tuple[str, ...] = ()) -> AuditBundle:
        """Research-only projection of one revision and its verified evidence."""

        with self.evidence._connection() as connection:
            connection.execute("BEGIN")
            row = self._revision(connection, revision_id)
            report = self.evidence._read_model(connection, row.report_sha256, ReportRevision)
            executions = []
            for execution_id in report.execution_ids:
                try:
                    receipt, result, _, _ = self.evidence._load_execution_context(
                        connection, execution_id
                    )
                except KeyError:
                    continue
                executions.append(ExecutionEvidence(receipt=receipt, result=result))
            artifacts = [row.report_sha256]
            checks = None
            if row.check_bundle_sha256 is not None:
                checks = self.evidence._read_model(connection, row.check_bundle_sha256, CheckBundle)
                artifacts.append(row.check_bundle_sha256)
            approval = None
            approval_row = connection.execute(
                "SELECT approval_sha256 FROM approvals WHERE revision_id = ?", (revision_id,)
            ).fetchone()
            if approval_row is not None:
                approval = self.evidence._read_model(connection, approval_row[0], ApprovalRecord)
                artifacts.append(approval_row[0])
            release = None
            validity: Literal["draft", "current", "stale", "historical"] = "draft"
            release_row = connection.execute(
                "SELECT release_sha256, validity FROM releases WHERE revision_id = ?",
                (revision_id,),
            ).fetchone()
            if release_row is not None:
                release = self.evidence._read_model(connection, release_row[0], ReleaseRecord)
                artifacts.append(release_row[0])
                validity = release_row[1]
            artifacts.extend(
                record[0]
                for record in connection.execute(
                    "SELECT record_sha256 FROM claims WHERE revision_id = ? ORDER BY claim_id",
                    (revision_id,),
                )
            )
            placeholders = ", ".join("?" for _ in artifacts)
            edges = tuple(
                (parent, child)
                for parent, child in connection.execute(
                    "SELECT parent_sha256, child_sha256 FROM dependency_edges "
                    f"WHERE child_sha256 IN ({placeholders}) ORDER BY parent_sha256, child_sha256",
                    artifacts,
                )
            )
            for parent, child in edges:
                self.evidence._read_artifact(connection, parent)
                self.evidence._read_artifact(connection, child)
        return AuditBundle(
            task=report.task,
            snapshot=report.snapshot,
            executions=tuple(executions),
            report=report,
            checks=checks,
            approval=approval,
            release=release,
            validity=validity,
            dependency_edges=edges,
            limitations=limitations,
        )
