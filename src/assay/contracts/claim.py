"""Structured answers; evidence binding is a later, separate validation step."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field, model_validator

from .base import VersionedModel
from .task import ExactDecimal, Identifier, MetricType, NonEmpty, ReportSemantics, TimeScope


class CellLocator(VersionedModel):
    """A zero-based row position and an exact result-column name."""

    row_index: Annotated[int, Field(strict=True, ge=0)]
    column: NonEmpty


class Claim(VersionedModel):
    slot_id: Identifier
    metric_id: Identifier
    metric_type: MetricType = "total"
    value: ExactDecimal | None
    unit: NonEmpty
    snapshot_id: Identifier
    grain: NonEmpty = "order"
    time_scope: TimeScope
    report_semantics: ReportSemantics = "current"
    abstention_reason: NonEmpty | None = None
    result_id: Identifier | None = None
    cell_locator: CellLocator | None = None
    dependency_ids: tuple[Identifier, ...] = ()

    @model_validator(mode="after")
    def validate_answer(self) -> Claim:
        if self.value is None:
            if self.abstention_reason is None or not self.abstention_reason.strip():
                raise ValueError("an abstention requires an explicit nonblank reason")
            if self.result_id is not None or self.cell_locator is not None:
                raise ValueError("an abstention cannot assert a numerical cell binding")
        elif self.abstention_reason is not None:
            raise ValueError("a numerical answer cannot also be an abstention")
        if (self.result_id is None) != (self.cell_locator is None):
            raise ValueError("result_id and cell_locator must be provided together")
        if len(set(self.dependency_ids)) != len(self.dependency_ids):
            raise ValueError("dependency IDs must be unique")
        return self
