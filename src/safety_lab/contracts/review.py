"""Reviewer views and structured decisions; a decision never publishes by itself."""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from .base import VersionedModel
from .episode import Count, Message, ModelUsage
from .snapshot import Sha256
from .task import Identifier, NonEmpty, UtcTimestamp

ViewKind = Literal["ordinary", "evidence"]
ReviewOutcome = Literal["allow", "reject", "needs_review", "malformed", "missing", "error"]
REASON_CODES = (
    "supported",
    "binding_mismatch",
    "wrong_metric",
    "wrong_grain",
    "wrong_population",
    "wrong_units",
    "stale_evidence",
    "missing_required",
    "unsupported_abstention",
    "suspicious_instruction",
    "insufficient_evidence",
    "other",
)
ReasonCode = Literal[
    "supported",
    "binding_mismatch",
    "wrong_metric",
    "wrong_grain",
    "wrong_population",
    "wrong_units",
    "stale_evidence",
    "missing_required",
    "unsupported_abstention",
    "suspicious_instruction",
    "insufficient_evidence",
    "other",
]
Bounded = Annotated[str, Field(max_length=4000)]


class CheckSummary(VersionedModel):
    check_id: Identifier
    name: Identifier
    check_class: Literal["host_integrity", "research_mandatory", "advisory"]
    outcome: Literal["pass", "fail", "unknown"]
    claim_slot_id: Identifier | None
    scope: Bounded
    limitations: tuple[Bounded, ...] = ()


class ClaimEvidence(VersionedModel):
    """Host-resolved links from one claim to its cited execution and cell."""

    claim_id: Identifier
    slot_id: Identifier
    value: str | None
    unit: NonEmpty
    abstention: bool
    execution_id: Identifier
    execution_found: bool
    execution_status: str | None = None
    exact_query: Annotated[str, Field(max_length=16_384)] | None = None
    snapshot_id: Identifier | None = None
    source_ids: tuple[Identifier, ...] = ()
    result_id: Identifier | None = None
    row_index: int | None = None
    column: Annotated[str, Field(max_length=256)] | None = None
    cell_status: Literal["ok", "abstention", "not_cited", "missing"]
    cited_cell: str | int | bool | None = None


class ClaimLine(VersionedModel):
    claim_id: Identifier
    slot_id: Identifier
    value: str | None
    unit: NonEmpty


class OrdinaryView(VersionedModel):
    """Arms C/D: a model-written transcript summary plus the candidate report."""

    kind: Literal["ordinary"] = "ordinary"
    question: NonEmpty
    report_text: Bounded
    claims: tuple[ClaimLine, ...]
    execution_ids: tuple[Identifier, ...]
    summary: Bounded
    checks: tuple[CheckSummary, ...] | None = None


class EvidenceView(VersionedModel):
    """Arm E: host-built claim/execution/cell/source/check links, no extra corpus."""

    kind: Literal["evidence"] = "evidence"
    question: NonEmpty
    metric_definition: NonEmpty
    rules: tuple[NonEmpty, ...]
    report_semantics: Literal["current", "historical"]
    report_text: Bounded
    snapshot_id: Identifier
    source_key: Identifier
    source_epoch: Annotated[int, Field(strict=True, ge=0)]
    claims: tuple[ClaimEvidence, ...]
    execution_ids: tuple[Identifier, ...]
    checks: tuple[CheckSummary, ...]
    unresolved: tuple[Bounded, ...]


class ReviewTranscript(VersionedModel):
    revision_id: Identifier
    summary_messages: tuple[Message, ...] = ()
    review_messages: tuple[Message, ...]
    usage: tuple[ModelUsage, ...]


class ReviewDecision(VersionedModel):
    review_id: Identifier
    report_revision_id: Identifier
    report_sha256: Sha256
    view_kind: ViewKind
    view_sha256: Sha256
    checks_visible: bool
    reviewer_model_id: NonEmpty
    summarizer_model_id: NonEmpty | None = None
    reviewer_prompt_sha256: Sha256
    decision: ReviewOutcome
    reason_codes: tuple[ReasonCode, ...] = Field(default=(), max_length=12)
    evidence_ids: tuple[Identifier, ...] = Field(default=(), max_length=64)
    confidence: Annotated[Decimal, Field(ge=0, le=1, max_digits=7, decimal_places=6)] | None = None
    error_category: Annotated[str, Field(min_length=1, max_length=128)] | None = None
    lookups: Count = 0
    model_calls: Count = 0
    input_tokens: Count = 0
    output_tokens: Count = 0
    transcript_sha256: Sha256
    created_at: UtcTimestamp

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if (self.decision == "error") != (self.error_category is not None):
            raise ValueError("error reviews, and only error reviews, carry a category")
        if self.decision in ("allow", "reject", "needs_review") and not self.reason_codes:
            raise ValueError("a well-formed decision needs at least one reason code")
        return self
