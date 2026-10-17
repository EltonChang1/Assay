"""Host-side analyst tools over public metadata, the gateway, and own-run results.

Tool arguments are untrusted model output. SQL reaches data only through the
gateway's policy and container worker. Errors returned to the model are fixed
strings that never echo host paths, exception text, or submitted values.
"""

from __future__ import annotations

import json
import re
import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path

from pydantic import JsonValue, ValidationError

from assay.contracts import DatasetSnapshot, TaskSpec
from assay.contracts.episode import ClaimSubmission, ToolCall, ToolSpec
from assay.contracts.execution import ExecutionReceipt
from assay.contracts.experiment import ResourceLimits
from assay.evidence import EvidenceIntegrityError, EvidenceStore
from assay.execution.docker import WorkerUnavailableError
from assay.gateway import service
from assay.gateway.policy import SQLPolicyError

PREVIEW_ROWS = 20
MAX_SLICE_ROWS = 100
_TABLE = re.compile(r"[a-z][a-z0-9_]{0,63}")

TOOL_SPECS = (
    ToolSpec(
        name="list_tables",
        description="List permitted tables with row counts and column schemas.",
        parameters={"type": "object", "properties": {}, "additionalProperties": False},
    ),
    ToolSpec(
        name="preview_rows",
        description=f"Return up to {PREVIEW_ROWS} rows from one permitted table.",
        parameters={
            "type": "object",
            "properties": {
                "table": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": PREVIEW_ROWS},
            },
            "required": ["table"],
            "additionalProperties": False,
        },
    ),
    ToolSpec(
        name="execute_sql",
        description=(
            "Run one read-only DuckDB SELECT over permitted tables in an isolated worker. "
            f"Returns a host execution_id, result_id, and the first {PREVIEW_ROWS} rows."
        ),
        parameters={
            "type": "object",
            "properties": {"sql": {"type": "string"}},
            "required": ["sql"],
            "additionalProperties": False,
        },
    ),
    ToolSpec(
        name="get_result_rows",
        description=f"Read up to {MAX_SLICE_ROWS} rows of a result from this episode.",
        parameters={
            "type": "object",
            "properties": {
                "execution_id": {"type": "string"},
                "offset": {"type": "integer", "minimum": 0},
                "limit": {"type": "integer", "minimum": 1, "maximum": MAX_SLICE_ROWS},
            },
            "required": ["execution_id"],
            "additionalProperties": False,
        },
    ),
    ToolSpec(
        name="submit_claims",
        description=(
            "Submit the final answer. Each claim names a declared slot_id and either a decimal "
            "value with the execution_id, row_index, and column of the exact result cell, or a "
            "null value with an abstention_reason and the execution_id that supports it."
        ),
        parameters={
            "type": "object",
            "properties": {
                "claims": {
                    "type": "array",
                    "minItems": 1,
                    "items": {
                        "type": "object",
                        "properties": {
                            "slot_id": {"type": "string"},
                            "value": {"type": ["string", "null"]},
                            "abstention_reason": {"type": ["string", "null"]},
                            "execution_id": {"type": "string"},
                            "row_index": {"type": ["integer", "null"], "minimum": 0},
                            "column": {"type": ["string", "null"]},
                        },
                        "required": ["slot_id", "execution_id"],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["claims"],
            "additionalProperties": False,
        },
    ),
)


class EpisodeAbort(Exception):
    """Infrastructure failure; the episode ends without blaming the model."""

    def __init__(self, category: str):
        super().__init__(category)
        self.category = category


@dataclass(frozen=True)
class ToolOutcome:
    content: str
    submission: ClaimSubmission | None = None


def _json(value: JsonValue) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _error(code: str) -> ToolOutcome:
    return ToolOutcome(_json({"status": "error", "error": code}))


class AnalystTools:
    def __init__(
        self,
        *,
        state: Path,
        bundle: Path,
        task: TaskSpec,
        snapshot: DatasetSnapshot,
        run_id: str,
        query_limits: ResourceLimits,
        cancel: threading.Event | None = None,
    ):
        self.state = state
        self.bundle = bundle
        self.task = task
        self.snapshot = snapshot
        self.run_id = run_id
        self.query_limits = query_limits
        self.cancel = cancel
        self.evidence = EvidenceStore(state / "evidence")
        self.execution_ids: list[str] = []

    def call(self, call: ToolCall) -> ToolOutcome:
        handlers = {
            "list_tables": self._list_tables,
            "preview_rows": self._preview_rows,
            "execute_sql": self._execute_sql,
            "get_result_rows": self._get_result_rows,
            "submit_claims": self._submit_claims,
        }
        handler = handlers.get(call.name)
        if handler is None:
            return _error("unknown_tool")
        return handler(call.arguments)

    def _list_tables(self, arguments: dict[str, JsonValue]) -> ToolOutcome:
        if arguments:
            return _error("unexpected_arguments")
        tables: list[JsonValue] = [
            {
                "table": table.table_id,
                "row_count": table.row_count,
                "columns": [
                    {"name": column.name, "type": column.data_type, "nullable": column.nullable}
                    for column in table.columns
                ],
            }
            for table in self.snapshot.tables
            if table.table_id in self.task.allowed_tables
        ]
        return ToolOutcome(_json({"status": "ok", "tables": tables}))

    def _preview_rows(self, arguments: dict[str, JsonValue]) -> ToolOutcome:
        table, limit = arguments.get("table"), arguments.get("limit", 5)
        if set(arguments) - {"table", "limit"}:
            return _error("unexpected_arguments")
        if (
            not isinstance(table, str)
            or _TABLE.fullmatch(table) is None
            or table not in self.task.allowed_tables
        ):
            return _error("unknown_table")
        if type(limit) is not int or not 1 <= limit <= PREVIEW_ROWS:
            return _error("invalid_limit")
        return self._query(f"SELECT * FROM {table} LIMIT {limit}")

    def _execute_sql(self, arguments: dict[str, JsonValue]) -> ToolOutcome:
        sql = arguments.get("sql")
        if set(arguments) != {"sql"} or not isinstance(sql, str):
            return _error("invalid_arguments")
        return self._query(sql)

    def _query(self, sql: str) -> ToolOutcome:
        try:
            outcome = service.execute_query(
                sql,
                self.bundle,
                state=self.state,
                limits=self.query_limits,
                cancel=self.cancel,
                run_id=self.run_id,
            )
        except SQLPolicyError as exc:
            # Policy errors are fixed capability descriptions without input text.
            return ToolOutcome(_json({"status": "denied", "error": str(exc)[:300]}))
        except WorkerUnavailableError as exc:
            raise EpisodeAbort("worker_unavailable") from exc
        except (OSError, sqlite3.Error, EvidenceIntegrityError, ValueError) as exc:
            raise EpisodeAbort("gateway_" + type(exc).__name__) from exc
        receipt = outcome.receipt
        self.execution_ids.append(receipt.execution_id)
        payload: dict[str, JsonValue] = {
            "status": receipt.status,
            "execution_id": receipt.execution_id,
            "error_code": receipt.error_code,
        }
        if outcome.result is not None:
            payload |= self._rows(receipt, 0, PREVIEW_ROWS)
        return ToolOutcome(_json(payload))

    def _rows(self, receipt: ExecutionReceipt, offset: int, limit: int) -> dict[str, JsonValue]:
        result = self.evidence.get_result(str(receipt.result_id))
        rows: list[JsonValue] = [
            [cell.value for cell in row] for row in result.rows[offset : offset + limit]
        ]
        return {
            "result_id": receipt.result_id,
            "columns": [
                {"name": column.name, "data_type": column.data_type} for column in result.columns
            ],
            "offset": offset,
            "rows": rows,
            "row_count": result.row_count,
            "rows_truncated": offset + len(rows) < result.row_count,
        }

    def _get_result_rows(self, arguments: dict[str, JsonValue]) -> ToolOutcome:
        execution_id = arguments.get("execution_id")
        offset, limit = arguments.get("offset", 0), arguments.get("limit", MAX_SLICE_ROWS)
        if set(arguments) - {"execution_id", "offset", "limit"}:
            return _error("unexpected_arguments")
        if type(offset) is not int or offset < 0:
            return _error("invalid_offset")
        if type(limit) is not int or not 1 <= limit <= MAX_SLICE_ROWS:
            return _error("invalid_limit")
        if not isinstance(execution_id, str) or execution_id not in self.execution_ids:
            return _error("unknown_execution")
        try:
            receipt = self.evidence.get_execution(execution_id)
            if receipt.status != "success":
                return _error("execution_has_no_result")
            payload: dict[str, JsonValue] = {"status": "ok"}
            payload |= self._rows(receipt, offset, limit)
            return ToolOutcome(_json(payload))
        except (OSError, sqlite3.Error, EvidenceIntegrityError) as exc:
            raise EpisodeAbort("evidence_" + type(exc).__name__) from exc

    def _submit_claims(self, arguments: dict[str, JsonValue]) -> ToolOutcome:
        try:
            submission = ClaimSubmission.model_validate(arguments)
        except ValidationError:
            return _error("invalid_submission_schema")
        return ToolOutcome(_json({"status": "received"}), submission)
