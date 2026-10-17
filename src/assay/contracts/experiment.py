"""Development experiment configuration; not a frozen study manifest."""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .task import ExactDecimal, Identifier

NonNegativeMoney = Annotated[ExactDecimal, Field(ge=0)]


class ResourceLimits(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    wall_time_seconds: int = Field(default=30, strict=True, gt=0, le=300)
    memory_mb: int = Field(default=256, strict=True, ge=64, le=4096)
    max_output_bytes: int = Field(default=1_048_576, strict=True, gt=0, le=1_048_576)
    max_rows: int = Field(default=1000, strict=True, gt=0, le=1000)


class ExperimentConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    experiment_id: str = Field(min_length=1, pattern=r"^[a-zA-Z0-9_-]+$")
    split: Literal["development"] = "development"
    arm: Literal["A", "B", "C", "D", "E"] = "E"
    regime: Literal["ordinary", "injection", "sabotage"] = "ordinary"
    mode: Literal["offline", "live"] = "offline"
    task_ids: tuple[Identifier, ...] = Field(min_length=1)
    analyst_model: str | None = Field(default=None, min_length=1)
    reviewer_model: str | None = Field(default=None, min_length=1)
    total_cost_cap_usd: NonNegativeMoney = Decimal("0")
    oversight_cost_cap_usd: NonNegativeMoney = Decimal("0")
    max_corrections: int = Field(default=1, ge=0, le=1)
    limits: ResourceLimits = ResourceLimits()

    @model_validator(mode="after")
    def coherent_budget(self) -> Self:
        if len(set(self.task_ids)) != len(self.task_ids):
            raise ValueError("Task IDs must be unique")
        if self.oversight_cost_cap_usd > self.total_cost_cap_usd:
            raise ValueError("Oversight cap cannot exceed total cap")
        if self.mode == "offline" and self.total_cost_cap_usd != 0:
            raise ValueError("Offline configurations must have a zero spending cap")
        if self.mode == "live":
            if not self.analyst_model or self.total_cost_cap_usd <= 0:
                raise ValueError("Live configurations require an analyst and positive total cap")
            if self.arm in {"C", "D", "E"} and (
                not self.reviewer_model or self.oversight_cost_cap_usd <= 0
            ):
                raise ValueError("Reviewer arms require a reviewer and positive oversight cap")
        return self
