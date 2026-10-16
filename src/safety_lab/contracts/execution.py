"""Versioned worker output and host-owned execution receipts."""

from __future__ import annotations

import math
from decimal import Decimal, InvalidOperation
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from .base import VersionedModel
from .snapshot import Sha256
from .task import Identifier, UtcTimestamp


class ResultColumn(VersionedModel):
    name: str = Field(min_length=1, max_length=256)
    data_type: str = Field(min_length=1, max_length=256)


class ResultCell(VersionedModel):
    type: Literal["null", "boolean", "integer", "decimal", "float", "string", "date", "timestamp"]
    value: Annotated[str, Field(max_length=100_000)] | bool | int | None

    @model_validator(mode="after")
    def check_type(self) -> Self:
        expected: type[object]
        if self.type == "null":
            if self.value is not None:
                raise ValueError("null cell requires null value")
            return self
        if self.type == "boolean":
            expected = bool
        elif self.type == "integer":
            expected = int
        else:
            expected = str
        if type(self.value) is not expected:
            raise ValueError("result cell type disagrees with its value")
        if self.type in {"decimal", "float"}:
            try:
                if not Decimal(str(self.value)).is_finite():
                    raise ValueError("nonfinite numerical result")
                if self.type == "float" and not math.isfinite(float(str(self.value))):
                    raise ValueError("nonfinite float result")
            except InvalidOperation as exc:
                raise ValueError("invalid numerical result") from exc
        return self


class WorkerSuccess(VersionedModel):
    status: Literal["success"]
    columns: tuple[ResultColumn, ...] = Field(min_length=1, max_length=128)
    rows: tuple[tuple[ResultCell, ...], ...] = Field(max_length=1000)
    row_count: int = Field(strict=True, ge=0, le=1000)

    @model_validator(mode="after")
    def check_shape(self) -> Self:
        if self.row_count != len(self.rows):
            raise ValueError("result row count disagrees with captured rows")
        if any(len(row) != len(self.columns) for row in self.rows):
            raise ValueError("result row width disagrees with columns")
        if len({column.name for column in self.columns}) != len(self.columns):
            raise ValueError("ambiguous duplicate result columns are unsupported")
        return self


class WorkerFailure(VersionedModel):
    status: Literal["error"]
    error_code: Literal[
        "invalid_request",
        "invalid_bundle",
        "policy_denied",
        "query_error",
        "output_limit",
        "unsupported_result",
        "internal_error",
    ]


class ExecutionReceipt(VersionedModel):
    execution_id: Identifier
    run_id: Identifier
    snapshot_id: Identifier
    snapshot_manifest_sha256: Sha256
    task_id: Identifier
    exact_query: str = Field(max_length=16_384)
    query_sha256: Sha256
    normalized_query: str = Field(max_length=32_768)
    source_ids: tuple[Identifier, ...]
    policy_version: str
    worker_image_id: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    started_at: UtcTimestamp
    finished_at: UtcTimestamp
    elapsed_ms: int = Field(strict=True, ge=0)
    status: Literal["success", "error", "timeout", "cancelled", "output_limit", "protocol_error"]
    error_code: str | None = Field(default=None, max_length=128)
    result_id: Identifier | None = None
    output_sha256: Sha256 | None = None
    row_count: int | None = Field(default=None, strict=True, ge=0)
    preview_row_count: int | None = Field(default=None, strict=True, ge=0)
    preview_truncated: bool = False

    @model_validator(mode="after")
    def coherent_outcome(self) -> Self:
        if self.finished_at < self.started_at:
            raise ValueError("execution cannot finish before it starts")
        captured = (self.result_id, self.output_sha256, self.row_count, self.preview_row_count)
        if self.status == "success":
            if any(value is None for value in captured) or self.error_code is not None:
                raise ValueError("successful receipt requires its complete result metadata")
            assert self.row_count is not None and self.preview_row_count is not None
            if self.preview_row_count > self.row_count:
                raise ValueError("preview cannot exceed the full result")
            if self.preview_truncated != (self.preview_row_count < self.row_count):
                raise ValueError("preview truncation metadata disagrees")
        elif any(value is not None for value in captured) or self.preview_truncated:
            raise ValueError("failed executions cannot assert successful result metadata")
        return self
