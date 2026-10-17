"""Immutable content identities for the public fixture export."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, model_validator

from .base import VersionedModel
from .task import Identifier, NonEmpty, UtcTimestamp

Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class ColumnSpec(VersionedModel):
    name: Identifier
    data_type: Literal["string", "integer", "boolean", "timestamp_utc"]
    nullable: bool = False


class TableFile(VersionedModel):
    table_id: Identifier
    path: NonEmpty
    sha256: Sha256
    row_count: Annotated[int, Field(strict=True, ge=0)]
    columns: tuple[ColumnSpec, ...]

    @model_validator(mode="after")
    def validate_schema(self) -> TableFile:
        if self.path != f"tables/{self.table_id}.csv":
            raise ValueError("table paths must be the declared relative CSV path")
        names = [column.name for column in self.columns]
        if not names or len(set(names)) != len(names):
            raise ValueError("column names must be nonempty and unique")
        return self


class DatasetSnapshot(VersionedModel):
    snapshot_id: Identifier
    task_id: Identifier
    task_sha256: Sha256
    tables: tuple[TableFile, ...]
    source: NonEmpty = "TraceFrame Safety Lab synthetic development fixture"
    license: NonEmpty = "undecided; local synthetic development fixture"
    created_at: UtcTimestamp
    data_contract_version: Literal["sales-orders-1.0"] = "sales-orders-1.0"
    canonicalization_version: Literal["utf8-csv-lf-json-sorted-1.0"] = "utf8-csv-lf-json-sorted-1.0"

    @model_validator(mode="after")
    def validate_tables(self) -> DatasetSnapshot:
        ids = [table.table_id for table in self.tables]
        if not ids or len(set(ids)) != len(ids):
            raise ValueError("snapshot table IDs must be nonempty and unique")
        return self
