"""Provider-agnostic model messages, analyst submissions, and episode records."""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import Field, JsonValue, model_validator

from .base import VersionedModel
from .policy import PolicyProfile
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


EpisodeStatus = Literal[
    "released",
    "withheld",
    "no_submission",
    "tool_limit",
    "time_limit",
    "model_error",
    "infrastructure_error",
]


class EpisodeRecord(VersionedModel):
    episode_id: Identifier
    run_id: Identifier
    attempt_id: Identifier
    fencing_token: Annotated[int, Field(strict=True, gt=0)]
    task_id: Identifier
    snapshot_id: Identifier
    source_key: Identifier
    policy_profile: PolicyProfile
    model_id: NonEmpty
    prompt_version: NonEmpty
    prompt_sha256: Sha256
    status: EpisodeStatus
    error_category: Annotated[str, Field(min_length=1, max_length=128)] | None = None
    revision_id: Identifier | None = None
    decision_outcome: Literal["approved", "rejected", "needs_review", "stale"] | None = None
    decision_reasons: tuple[Annotated[str, Field(max_length=400)], ...] = ()
    release_id: Identifier | None = None
    review_id: Identifier | None = None
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
        if (self.status in ("model_error", "infrastructure_error")) != (
            self.error_category is not None
        ):
            raise ValueError("error episodes, and only error episodes, carry a category")
        return self
