"""Provider-agnostic model messages, analyst submissions, and episode records."""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import Field, JsonValue, model_validator

from .base import VersionedModel
from .policy import ARMS, Arm, PolicyProfile
from .snapshot import Sha256
from .task import Identifier, NonEmpty, UtcTimestamp

ToolName = Literal[
    "list_tables",
    "preview_rows",
    "execute_sql",
    "get_result_rows",
    "submit_claims",
    "get_claim_evidence",
    "get_check",
    "submit_decision",
]
Count = Annotated[int, Field(strict=True, ge=0)]


class ToolCall(VersionedModel):
    call_id: Identifier
    name: Annotated[str, Field(min_length=1, max_length=128)]
    arguments: dict[str, JsonValue] = Field(default_factory=dict)


class Message(VersionedModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: Annotated[str, Field(max_length=65_536)] = ""
    tool_calls: tuple[ToolCall, ...] = Field(default=(), max_length=16)
    tool_call_id: Identifier | None = None

    @model_validator(mode="after")
    def coherent_role(self) -> Self:
        if self.tool_calls and self.role != "assistant":
            raise ValueError("only assistant messages can request tools")
        if (self.role == "tool") != (self.tool_call_id is not None):
            raise ValueError("tool messages, and only tool messages, answer a tool call")
        return self


class ModelUsage(VersionedModel):
    input_tokens: Count = 0
    output_tokens: Count = 0


class ModelTurn(VersionedModel):
    """One provider response; usage is recorded even when the turn is unusable."""

    model_id: NonEmpty
    message: Message
    usage: ModelUsage = Field(default_factory=ModelUsage)

    @model_validator(mode="after")
    def assistant_only(self) -> Self:
        if self.message.role != "assistant":
            raise ValueError("model turns must be assistant messages")
        return self


class ToolSpec(VersionedModel):
    name: ToolName
    description: NonEmpty
    parameters: dict[str, JsonValue]


class SubmittedClaim(VersionedModel):
    """The analyst's structured answer; slot metadata comes from the public task."""

    slot_id: Identifier
    value: Annotated[str, Field(min_length=1, max_length=64)] | None = None
    abstention_reason: Annotated[str, Field(min_length=1, max_length=2000)] | None = None
    execution_id: Identifier | None = None
    row_index: Annotated[int, Field(strict=True, ge=0)] | None = None
    column: Annotated[str, Field(min_length=1, max_length=256)] | None = None


class ClaimSubmission(VersionedModel):
    claims: tuple[SubmittedClaim, ...] = Field(min_length=1, max_length=16)


class EpisodeTranscript(VersionedModel):
    """Audit-only transcript; free text here never reaches released bytes."""

    run_id: Identifier
    attempt_id: Identifier
    messages: tuple[Message, ...]
    usage: tuple[ModelUsage, ...]


class CorrectionFeedback(VersionedModel):
    """The only oversight output an analyst sees: its arm's decision reasons.

    Reasons come from the arm's own policy decision, so arms without research
    checks never receive check outcomes. Reviewer prose is never included.
    """

    format: Literal["correction-feedback-1.0"] = "correction-feedback-1.0"
    round: Annotated[int, Field(strict=True, gt=0)]
    max_rounds: Annotated[int, Field(strict=True, gt=0)]
    revision_id: Identifier
    outcome: Literal["rejected", "needs_review"]
    reasons: tuple[Annotated[str, Field(max_length=400)], ...] = Field(default=(), max_length=1024)
    reviewer_reason_codes: tuple[Identifier, ...] = Field(default=(), max_length=12)


EpisodeStatus = Literal[
    "released",
    "withheld",
    "no_submission",
    "tool_limit",
    "time_limit",
    "model_error",
    "infrastructure_error",
]
CorrectionStatus = Literal[
    "resubmitted",
    "no_submission",
    "tool_limit",
    "time_limit",
    "model_error",
    "infrastructure_error",
]
_ERRORS = ("model_error", "infrastructure_error")


class EpisodeRecord(VersionedModel):
    episode_id: Identifier
    run_id: Identifier
    attempt_id: Identifier
    fencing_token: Annotated[int, Field(strict=True, gt=0)]
    task_id: Identifier
    snapshot_id: Identifier
    source_key: Identifier
    policy_profile: PolicyProfile
    arm: Arm | None = None
    model_id: NonEmpty
    prompt_version: NonEmpty
    prompt_sha256: Sha256
    status: EpisodeStatus
    error_category: Annotated[str, Field(min_length=1, max_length=128)] | None = None
    revision_id: Identifier | None = None
    revision_ids: tuple[Identifier, ...] = Field(default=(), max_length=8)
    correction_rounds: Count = 0
    correction_status: CorrectionStatus | None = None
    decision_outcome: Literal["approved", "rejected", "needs_review", "stale"] | None = None
    decision_reasons: tuple[Annotated[str, Field(max_length=400)], ...] = ()
    release_id: Identifier | None = None
    review_id: Identifier | None = None
    review_ids: tuple[Identifier, ...] = Field(default=(), max_length=8)
    review_view: Literal["ordinary", "evidence"] | None = None
    review_decision: (
        Literal["allow", "reject", "needs_review", "malformed", "missing", "error"] | None
    ) = None
    oversight_model_calls: Count = 0
    oversight_input_tokens: Count = 0
    oversight_output_tokens: Count = 0
    model_calls: Count
    tool_calls: Count
    rejected_submissions: Count = 0
    input_tokens: Count
    output_tokens: Count
    execution_ids: tuple[Identifier, ...] = ()
    transcript_sha256: Sha256
    started_at: UtcTimestamp
    finished_at: UtcTimestamp

    @model_validator(mode="after")
    def coherent_outcome(self) -> Self:
        if self.finished_at < self.started_at:
            raise ValueError("episode cannot finish before it starts")
        if (self.status == "released") != (self.release_id is not None):
            raise ValueError("only released episodes reference a release")
        if self.status == "released" and self.decision_outcome != "approved":
            raise ValueError("released episodes require an approval")
        if self.status == "withheld" and self.decision_outcome in (None, "approved"):
            raise ValueError("withheld episodes require a non-approving decision")
        if (self.status in _ERRORS or self.correction_status in _ERRORS) != (
            self.error_category is not None
        ):
            raise ValueError("only an episode or correction round ending in error has a category")
        if self.revision_ids and self.revision_ids[-1] != self.revision_id:
            raise ValueError("the final revision must be the last recorded revision")
        if self.review_ids and self.review_ids[-1] != self.review_id:
            raise ValueError("the final review must be the last recorded review")
        if (self.correction_rounds == 0) != (self.correction_status is None):
            raise ValueError("a correction status records exactly the rounds that were offered")
        if (
            self.correction_status == "resubmitted"
            and self.revision_ids
            and (len(self.revision_ids) != self.correction_rounds + 1)
        ):
            raise ValueError("each resubmitted correction round adds one revision")
        if self.arm is not None:
            profile, view = ARMS[self.arm]
            if self.policy_profile != profile:
                raise ValueError("the arm determines the publication policy profile")
            if self.review_view is not None and self.review_view != view:
                raise ValueError("the arm determines the reviewer view")
        return self
