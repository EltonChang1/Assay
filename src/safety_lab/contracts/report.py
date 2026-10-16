"""Host-owned claims, check records, immutable report revisions and releases."""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from .base import VersionedModel
from .claim import Claim
from .execution import ExecutionReceipt, WorkerSuccess
from .snapshot import DatasetSnapshot, Sha256
from .task import Identifier, NonEmpty, TaskSpec, UtcTimestamp


class ClaimInput(VersionedModel):
    claim: Claim
    execution_id: Identifier


class ClaimRecord(ClaimInput):
    claim_id: Identifier


class ReportRevision(VersionedModel):
    revision_id: Identifier
    report_id: Identifier
    revision: Annotated[int, Field(strict=True, gt=0)]
    run_id: Identifier
    attempt_id: Identifier
    fencing_token: Annotated[int, Field(strict=True, gt=0)]
    source_key: Identifier
    source_epoch: Annotated[int, Field(strict=True, ge=0)]
    task: TaskSpec
    snapshot: DatasetSnapshot
    claims: tuple[ClaimRecord, ...] = Field(min_length=1, max_length=64)
    renderer_version: Literal["structured-text-1.0"] = "structured-text-1.0"
    rendered_sha256: Sha256
    created_at: UtcTimestamp

    @property
    def task_id(self) -> str:
        return self.task.task_id

    @property
    def snapshot_id(self) -> str:
        return self.snapshot.snapshot_id

    @property
    def execution_ids(self) -> tuple[str, ...]:
        return tuple(sorted({record.execution_id for record in self.claims}))

    @model_validator(mode="after")
    def consistent_claim_identity(self) -> Self:
        if len({record.claim_id for record in self.claims}) != len(self.claims):
            raise ValueError("Claim record IDs must be unique")
        if self.task.task_id != self.snapshot.task_id:
            raise ValueError("Report task and snapshot identities disagree")
        return self


class CheckResult(VersionedModel):
    check_id: Identifier
    name: Identifier
    checker_version: NonEmpty
    check_class: Literal["host_integrity", "research_mandatory", "advisory"]
    outcome: Literal["pass", "fail", "unknown"]
    applicability: Literal["applicable", "not_applicable"] = "applicable"
    claim_slot_id: Identifier | None = None
    input_hashes: tuple[Sha256, ...]
    scope: Annotated[str, Field(min_length=1, max_length=2000)]
    facts: tuple[Annotated[str, Field(max_length=2000)], ...] = Field(default=(), max_length=128)
    limitations: tuple[Annotated[str, Field(max_length=2000)], ...] = Field(
        default=(), max_length=32
    )
    duration_ms: Annotated[int, Field(strict=True, ge=0)] = 0


class CheckBundle(VersionedModel):
    check_bundle_id: Identifier
    report_revision_id: Identifier
    report_sha256: Sha256
    checker_profile: Literal["sales-public-1.0"] = "sales-public-1.0"
    checks: tuple[CheckResult, ...] = Field(min_length=1, max_length=512)
    input_hashes: tuple[Sha256, ...]
    created_at: UtcTimestamp


class PublicationDecision(VersionedModel):
    """Deterministic policy outcome; only ``approved`` yields an ApprovalRecord."""

    decision_id: Identifier
    report_revision_id: Identifier
    report_sha256: Sha256
    check_bundle_sha256: Sha256
    policy_profile: Literal["checked", "baseline"]
    policy_version: NonEmpty
    outcome: Literal["approved", "rejected", "needs_review", "stale"]
    reasons: tuple[Annotated[str, Field(min_length=1, max_length=400)], ...] = Field(
        default=(), max_length=1024
    )
    source_epoch: Annotated[int, Field(strict=True, ge=0)]
    attempt_id: Identifier
    fencing_token: Annotated[int, Field(strict=True, gt=0)]
    created_at: UtcTimestamp


class ApprovalRecord(VersionedModel):
    approval_id: Identifier
    report_revision_id: Identifier
    report_sha256: Sha256
    rendered_sha256: Sha256
    check_bundle_sha256: Sha256
    policy_profile: Literal["checked", "baseline"]
    policy_version: NonEmpty
    source_epoch: Annotated[int, Field(strict=True, ge=0)]
    attempt_id: Identifier
    fencing_token: Annotated[int, Field(strict=True, gt=0)]
    created_at: UtcTimestamp


class ReleaseRecord(VersionedModel):
    release_id: Identifier
    report_revision_id: Identifier
    approval_id: Identifier
    rendered_sha256: Sha256
    published_at: UtcTimestamp


class ExecutionEvidence(VersionedModel):
    receipt: ExecutionReceipt
    result: WorkerSuccess | None


class AuditBundle(VersionedModel):
    """Research-only projection; no alternate simulated end-user release route."""

    audience: Literal["research_audit"] = "research_audit"
    task: TaskSpec
    snapshot: DatasetSnapshot
    executions: tuple[ExecutionEvidence, ...]
    report: ReportRevision
    checks: CheckBundle | None = None
    approval: ApprovalRecord | None = None
    release: ReleaseRecord | None = None
    validity: Literal["draft", "current", "stale", "historical"]
    dependency_edges: tuple[tuple[Sha256, Sha256], ...] = ()
    limitations: tuple[NonEmpty, ...] = ()
