"""Minimal container entrypoint; never a host fallback for analyst SQL.

The build context contains this file, the public SQL policy, and pinned runtime
dependencies only. Private evaluation code and the host application are absent.
Pure request/CSV/serialization functions can be tested without executing SQL.
"""

from __future__ import annotations

import csv
import io
import json
import math
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import BinaryIO, Literal

MAX_REQUEST_BYTES = 32_768
MAX_ROWS = 1000
MAX_OUTPUT_BYTES = 1_048_576
MAX_TABLE_BYTES = 8_388_608
MAX_TABLE_ROWS = 50_000
MAX_CELL_CHARS = 100_000
DATA_ROOT = Path("/data")

ErrorCode = Literal[
    "invalid_request",
    "invalid_bundle",
    "policy_denied",
    "query_error",
    "output_limit",
    "unsupported_result",
    "internal_error",
]


class WorkerError(ValueError):
    """A fixed public failure code; never include query/data exception text."""

    def __init__(self, error_code: ErrorCode):
        super().__init__(error_code)
        self.error_code = error_code


@dataclass(frozen=True)
class Request:
    query: str
    allowed_tables: tuple[str, ...]
    max_rows: int
    max_output_bytes: int


_HEADERS = {
    "customers": ("customer_id", "eligible"),
    "orders": ("order_id", "customer_id", "amount_minor", "currency", "status", "occurred_at"),
    "order_items": ("item_id", "order_id", "quantity", "amount_minor"),
}
_CREATE_TABLE = {
    "customers": "CREATE TABLE customers (customer_id VARCHAR PRIMARY KEY, eligible BOOLEAN)",
    "orders": (
        "CREATE TABLE orders (order_id VARCHAR PRIMARY KEY, customer_id VARCHAR, "
        "amount_minor BIGINT, currency VARCHAR, status VARCHAR, occurred_at TIMESTAMPTZ)"
    ),
    "order_items": (
        "CREATE TABLE order_items (item_id VARCHAR PRIMARY KEY, order_id VARCHAR, "
        "quantity BIGINT, amount_minor BIGINT)"
    ),
}
_INSERT_TABLE = {
    "customers": "INSERT INTO customers VALUES (?, ?)",
    "orders": "INSERT INTO orders VALUES (?, ?, ?, ?, ?, ?)",
    "order_items": "INSERT INTO order_items VALUES (?, ?, ?, ?)",
}
_IDENTIFIER = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,159}\Z")
_INTEGER = re.compile(r"(?:0|[1-9][0-9]{0,18})\Z")
_UTC_TIMESTAMP = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{6})?Z\Z"
)
_INTEGER_TYPES = frozenset(
    {
        "TINYINT",
        "SMALLINT",
        "INTEGER",
        "BIGINT",
        "HUGEINT",
        "UTINYINT",
        "USMALLINT",
        "UINTEGER",
        "UBIGINT",
        "UHUGEINT",
    }
)


def _json_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise WorkerError("invalid_request")
        result[key] = value
    return result


def _invalid_constant(value: str) -> object:
    raise WorkerError("invalid_request")


def parse_request(raw: bytes) -> Request:
    """Strict wire validation before importing the database or reading data."""
    if not raw or len(raw) > MAX_REQUEST_BYTES:
        raise WorkerError("invalid_request")
    try:
        value = json.loads(
            raw.decode("utf-8"), object_pairs_hook=_json_pairs, parse_constant=_invalid_constant
        )
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise WorkerError("invalid_request") from exc
    keys = {"schema_version", "query", "allowed_tables", "max_rows", "max_output_bytes"}
    if not isinstance(value, dict) or set(value) != keys or value["schema_version"] != "1.0":
        raise WorkerError("invalid_request")
    query = value["query"]
    tables = value["allowed_tables"]
    max_rows = value["max_rows"]
    max_bytes = value["max_output_bytes"]
    if not isinstance(query, str) or not query.strip():
        raise WorkerError("invalid_request")
    try:
        query.encode("utf-8")
    except UnicodeError as exc:
        raise WorkerError("invalid_request") from exc
    if (
        not isinstance(tables, list)
        or not tables
        or len(tables) > len(_HEADERS)
        or any(type(table) is not str or table not in _HEADERS for table in tables)
        or len(set(tables)) != len(tables)
        or type(max_rows) is not int
        or not 1 <= max_rows <= MAX_ROWS
        or type(max_bytes) is not int
        or not 1 <= max_bytes <= MAX_OUTPUT_BYTES
    ):
        raise WorkerError("invalid_request")
    return Request(query, tuple(tables), max_rows, max_bytes)


def read_request(stream: BinaryIO) -> Request:
    return parse_request(stream.read(MAX_REQUEST_BYTES + 1))


def _identifier(value: str) -> str:
    if _IDENTIFIER.fullmatch(value) is None:
        raise WorkerError("invalid_bundle")
    return value


def _integer(value: str, *, nullable: bool = False, positive: bool = False) -> int | None:
    if value == "" and nullable:
        return None
    if _INTEGER.fullmatch(value) is None:
        raise WorkerError("invalid_bundle")
    result = int(value)
    if result > 2**63 - 1 or (positive and result == 0):
        raise WorkerError("invalid_bundle")
    return result


def _timestamp(value: str) -> datetime:
    # The public builder emits seconds or exactly six fractional digits. Reject
    # greater precision instead of silently losing nanoseconds in datetime.
    if _UTC_TIMESTAMP.fullmatch(value) is None:
        raise WorkerError("invalid_bundle")
    try:
        result = datetime.fromisoformat(value)
    except ValueError as exc:
        raise WorkerError("invalid_bundle") from exc
    if result.tzinfo is None or result.utcoffset() != UTC.utcoffset(result):
        raise WorkerError("invalid_bundle")
    return result


def _convert_row(table_id: str, row: list[str]) -> tuple[object, ...]:
    if table_id == "customers":
        if row[1] not in ("true", "false"):
            raise WorkerError("invalid_bundle")
        return (_identifier(row[0]), row[1] == "true")
    if table_id == "orders":
        if row[3] != "USD" or row[4] not in ("settled", "pending", "refunded"):
            raise WorkerError("invalid_bundle")
        return (
            _identifier(row[0]),
            _identifier(row[1]),
            _integer(row[2], nullable=True),
            row[3],
            row[4],
            _timestamp(row[5]),
        )
    return (
        _identifier(row[0]),
        _identifier(row[1]),
        _integer(row[2], positive=True),
        _integer(row[3], nullable=True),
    )


def read_table_rows(table_id: str, data_root: Path = DATA_ROOT) -> list[tuple[object, ...]]:
    """Read an exact known CSV schema; file paths never enter DuckDB SQL."""
    if table_id not in _HEADERS:
        raise WorkerError("invalid_bundle")
    table_dir = data_root / "tables"
    path = table_dir / f"{table_id}.csv"
    try:
        if table_dir.is_symlink() or path.is_symlink() or not path.is_file():
            raise WorkerError("invalid_bundle")
        with path.open("rb") as stream:
            content = stream.read(MAX_TABLE_BYTES + 1)
        if len(content) > MAX_TABLE_BYTES:
            raise WorkerError("invalid_bundle")
        reader = csv.reader(io.StringIO(content.decode("utf-8"), newline=""), strict=True)
        if next(reader, None) != list(_HEADERS[table_id]):
            raise WorkerError("invalid_bundle")
        rows: list[tuple[object, ...]] = []
        seen_ids: set[object] = set()
        for row in reader:
            if len(row) != len(_HEADERS[table_id]) or len(rows) >= MAX_TABLE_ROWS:
                raise WorkerError("invalid_bundle")
            converted = _convert_row(table_id, row)
            if converted[0] in seen_ids:
                raise WorkerError("invalid_bundle")
            seen_ids.add(converted[0])
            rows.append(converted)
        return rows
    except (OSError, UnicodeError, csv.Error, ValueError) as exc:
        raise WorkerError("invalid_bundle") from exc


def _column_kind(data_type: str) -> str:
    if data_type == "BOOLEAN":
        return "boolean"
    if data_type in _INTEGER_TYPES:
        return "integer"
    if re.fullmatch(r"DECIMAL\([0-9]{1,2}, ?[0-9]{1,2}\)", data_type):
        return "decimal"
    if data_type in {"FLOAT", "DOUBLE"}:
        return "float"
    if data_type == "VARCHAR":
        return "string"
    if data_type == "DATE":
        return "date"
    if data_type in {"TIMESTAMP", "TIMESTAMP_S", "TIMESTAMP_MS", "TIMESTAMP WITH TIME ZONE"}:
        return "timestamp"
    # Python datetime cannot preserve nanoseconds. Nested, binary, time, UUID,
    # interval, and other unsupported representations also fail explicitly.
    raise WorkerError("unsupported_result")


def serialize_cell(value: object, expected_kind: str | None = None) -> dict[str, object]:
    """Preserve exact scalar values, including a float's round-trip string."""
    if value is None:
        return {"type": "null", "value": None}
    kind: str
    encoded: object
    if type(value) is bool:
        kind, encoded = "boolean", value
    elif type(value) is int:
        kind, encoded = "integer", value
    elif isinstance(value, Decimal):
        if not value.is_finite():
            raise WorkerError("unsupported_result")
        kind, encoded = "decimal", str(value)
    elif type(value) is float:
        if not math.isfinite(value):
            raise WorkerError("unsupported_result")
        kind, encoded = "float", repr(value)
    elif type(value) is str:
        kind, encoded = "string", value
    elif type(value) is datetime:
        if value.replace(tzinfo=None) in (datetime.min, datetime.max):
            raise WorkerError("unsupported_result")
        kind, encoded = "timestamp", value.isoformat()
    elif type(value) is date:
        if value in (date.min, date.max):
            raise WorkerError("unsupported_result")
        kind, encoded = "date", value.isoformat()
    else:
        raise WorkerError("unsupported_result")
    if expected_kind is not None and kind != expected_kind:
        raise WorkerError("unsupported_result")
    if isinstance(encoded, str) and len(encoded) > MAX_CELL_CHARS:
        raise WorkerError("output_limit")
    return {"type": kind, "value": encoded}


def _json_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value, ensure_ascii=False, allow_nan=False, separators=(",", ":"), sort_keys=True
        ).encode("utf-8")
    except (ValueError, UnicodeError) as exc:
        raise WorkerError("unsupported_result") from exc


def serialize_result(
    description: Sequence[Sequence[object]],
    rows: Sequence[Sequence[object]],
    max_rows: int,
    max_output_bytes: int,
) -> bytes:
    """Emit complete results only; enforce the byte budget while encoding rows."""
    if not description or len(description) > 128:
        raise WorkerError("unsupported_result")
    if len(rows) > max_rows:
        raise WorkerError("output_limit")
    columns: list[dict[str, str]] = []
    kinds: list[str] = []
    seen_names: set[str] = set()
    for column in description:
        if len(column) < 2 or not isinstance(column[0], str):
            raise WorkerError("unsupported_result")
        name, data_type = column[0], str(column[1])
        if not name or len(name) > 256 or len(data_type) > 256 or name in seen_names:
            raise WorkerError("unsupported_result")
        seen_names.add(name)
        kinds.append(_column_kind(data_type))
        columns.append({"name": name, "data_type": data_type})
    prefix = b'{"schema_version":"1.0","status":"success","columns":' + _json_bytes(columns)
    output = bytearray(prefix + b',"rows":[')
    suffix = b'],"row_count":' + str(len(rows)).encode("ascii") + b"}\n"
    if len(output) + len(suffix) > max_output_bytes:
        raise WorkerError("output_limit")
    for index, row in enumerate(rows):
        if len(row) != len(columns):
            raise WorkerError("unsupported_result")
        cell_row = [serialize_cell(value, kind) for value, kind in zip(row, kinds, strict=True)]
        encoded_row = (b"," if index else b"") + _json_bytes(cell_row)
        if len(output) + len(encoded_row) + len(suffix) > max_output_bytes:
            raise WorkerError("output_limit")
        output.extend(encoded_row)
    output.extend(suffix)
    return bytes(output)


def _execute_in_container(request: Request, normalized_sql: str) -> bytes:
    # Deliberately lazy: importing pure wire helpers on the host does not load
    # DuckDB or supply an analyst-query execution fallback.
    import duckdb

    try:
        connection = duckdb.connect(
            ":memory:",
            config={
                "enable_external_access": False,
                "autoinstall_known_extensions": False,
                "autoload_known_extensions": False,
                "threads": 1,
                "memory_limit": "128MB",
                "temp_directory": "/tmp/duckdb",
                "max_temp_directory_size": "32MB",
            },
        )
    except duckdb.Error as exc:
        raise WorkerError("internal_error") from exc
    try:
        # This is a session option; DuckDB rejects it in connect()'s global config.
        connection.execute("SET enable_progress_bar = false")
        for table in request.allowed_tables:
            rows = read_table_rows(table)
            try:
                connection.execute(_CREATE_TABLE[table])
                if rows:
                    connection.executemany(_INSERT_TABLE[table], rows)
            except duckdb.Error as exc:
                raise WorkerError("invalid_bundle") from exc
        try:
            connection.execute("SET lock_configuration = true")
        except duckdb.Error as exc:
            raise WorkerError("internal_error") from exc
        try:
            result = connection.execute(normalized_sql)
            description = result.description
            rows = result.fetchmany(request.max_rows + 1)
        except duckdb.Error as exc:
            raise WorkerError("query_error") from exc
        if description is None:
            raise WorkerError("unsupported_result")
        return serialize_result(description, rows, request.max_rows, request.max_output_bytes)
    finally:
        connection.close()


def error_result(error_code: ErrorCode) -> bytes:
    return (
        _json_bytes({"schema_version": "1.0", "status": "error", "error_code": error_code}) + b"\n"
    )


def main() -> int:
    try:
        request = read_request(sys.stdin.buffer)
        # This standalone policy is copied from the same reviewed public source
        # as the host policy. Its import has no private evaluator dependency.
        from policy import SQLPolicyError, validate_sql  # type: ignore[import-not-found]

        try:
            checked = validate_sql(request.query, request.allowed_tables)
        except SQLPolicyError as exc:
            raise WorkerError("policy_denied") from exc
        output = _execute_in_container(request, checked.normalized_sql)
        status = 0
    except WorkerError as exc:
        output, status = error_result(exc.error_code), 1
    except Exception:
        output, status = error_result("internal_error"), 1
    try:
        sys.stdout.buffer.write(output)
        sys.stdout.buffer.flush()
    except (BrokenPipeError, OSError):
        return 1
    return status


if __name__ == "__main__":
    raise SystemExit(main())
