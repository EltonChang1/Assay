"""Pure worker-wire tests: these never execute analyst SQL on the host."""

import io
import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from assay.contracts.execution import WorkerFailure, WorkerSuccess
from sandbox.worker import (
    MAX_REQUEST_BYTES,
    Request,
    WorkerError,
    error_result,
    parse_request,
    read_request,
    read_table_rows,
    serialize_cell,
    serialize_result,
)


def request_bytes(**updates):
    value = {
        "schema_version": "1.0",
        "query": "SELECT order_id FROM orders",
        "allowed_tables": ["orders"],
        "max_rows": 1000,
        "max_output_bytes": 1_048_576,
    }
    value.update(updates)
    return json.dumps(value).encode("utf-8")


def test_request_is_strict_and_reads_only_its_bounded_frame():
    request = parse_request(request_bytes())
    assert request == Request("SELECT order_id FROM orders", ("orders",), 1000, 1_048_576)
    assert read_request(io.BytesIO(request_bytes())) == request
    with pytest.raises(WorkerError, match="invalid_request"):
        read_request(io.BytesIO(b" " * (MAX_REQUEST_BYTES + 1)))


@pytest.mark.parametrize(
    "updates",
    [
        {"schema_version": "2.0"},
        {"query": ""},
        {"query": 5},
        {"query": "\ud800"},
        {"allowed_tables": []},
        {"allowed_tables": ["orders", "orders"]},
        {"allowed_tables": ["private"]},
        {"allowed_tables": ["/data/orders.csv"]},
        {"allowed_tables": "orders"},
        {"allowed_tables": [True]},
        {"max_rows": True},
        {"max_rows": 0},
        {"max_rows": 1001},
        {"max_output_bytes": False},
        {"max_output_bytes": 0},
        {"max_output_bytes": 1_048_577},
        {"unrecognized": "ignored?"},
    ],
)
def test_invalid_request_fields_are_rejected(updates):
    with pytest.raises(WorkerError, match="invalid_request"):
        parse_request(request_bytes(**updates))


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"not json",
        b"[]",
        b"{}",
        b"\xff",
        b'{"query":"one","query":"two"}',
        b'{"query":NaN}',
        b'{"query":Infinity}',
        b"{} {}",
    ],
)
def test_invalid_json_does_not_expose_parser_details(raw):
    with pytest.raises(WorkerError) as error:
        parse_request(raw)
    assert str(error.value) == "invalid_request"


def test_exact_scalar_serialization_matches_host_contract():
    values = (
        None,
        True,
        2**63,
        Decimal("200.010000"),
        0.1,
        "first, second\nthird <script> & café",
        date(2026, 1, 2),
        datetime(2026, 1, 2, 3, 4, 5, 123456, tzinfo=UTC),
    )
    description = [
        (f"column_{index}", data_type)
        for index, data_type in enumerate(
            [
                "VARCHAR",
                "BOOLEAN",
                "HUGEINT",
                "DECIMAL(18,6)",
                "DOUBLE",
                "VARCHAR",
                "DATE",
                "TIMESTAMP WITH TIME ZONE",
            ]
        )
    ]
    encoded = serialize_result(description, [values], 1000, 1_048_576)
    parsed = WorkerSuccess.model_validate_json(encoded)
    assert parsed.row_count == 1
    assert [cell.type for cell in parsed.rows[0]] == [
        "null",
        "boolean",
        "integer",
        "decimal",
        "float",
        "string",
        "date",
        "timestamp",
    ]
    assert parsed.rows[0][3].value == "200.010000"
    assert parsed.rows[0][4].value == "0.1"
    assert parsed.rows[0][7].value == "2026-01-02T03:04:05.123456+00:00"
    assert serialize_cell(-0.0) == {"type": "float", "value": "-0.0"}


@pytest.mark.parametrize(
    "value",
    [
        float("inf"),
        float("-inf"),
        float("nan"),
        Decimal("Infinity"),
        Decimal("NaN"),
        b"binary",
        [1, 2],
        {"nested": 1},
        timedelta(seconds=1),
        date.max,
        date.min,
        datetime.max,
        datetime.min,
    ],
)
def test_unsupported_or_nonfinite_cells_are_rejected(value):
    with pytest.raises(WorkerError, match="unsupported_result"):
        serialize_cell(value)


@pytest.mark.parametrize(
    "description",
    [
        [],
        [("duplicate", "BIGINT"), ("duplicate", "BIGINT")],
        [("", "VARCHAR")],
        [("a" * 257, "VARCHAR")],
        [("x", "INTEGER[]")],
        [("x", "STRUCT(a INTEGER)")],
        [("x", "BLOB")],
        [("x", "TIMESTAMP_NS")],
        [("x", "TIME")],
        [("x", "INTERVAL")],
    ],
)
def test_ambiguous_or_unsupported_columns_are_rejected(description):
    with pytest.raises(WorkerError, match="unsupported_result"):
        serialize_result(description, [], 1000, 1_048_576)


def test_result_shape_and_column_type_must_agree_with_values():
    with pytest.raises(WorkerError, match="unsupported_result"):
        serialize_result([("id", "BIGINT")], [(1, 2)], 1000, 1_048_576)
    with pytest.raises(WorkerError, match="unsupported_result"):
        serialize_result([("id", "BIGINT")], [(True,)], 1000, 1_048_576)
    with pytest.raises(WorkerError, match="unsupported_result"):
        serialize_result([("time", "TIMESTAMP")], [("unconverted timestamp",)], 1000, 1_048_576)


def test_no_success_is_emitted_for_truncated_or_oversized_results():
    description = [("id", "BIGINT")]
    with pytest.raises(WorkerError, match="output_limit"):
        serialize_result(description, [(1,), (2,)], 1, 1_048_576)
    complete = serialize_result(description, [(1,)], 1, 1_048_576)
    assert serialize_result(description, [(1,)], 1, len(complete)) == complete
    with pytest.raises(WorkerError, match="output_limit"):
        serialize_result(description, [(1,)], 1, len(complete) - 1)
    with pytest.raises(WorkerError, match="output_limit"):
        serialize_result([("text", "VARCHAR")], [("a" * 100_001,)], 1000, 1_048_576)
    empty = WorkerSuccess.model_validate_json(serialize_result(description, [], 1, 1024))
    assert empty.row_count == 0 and empty.rows == ()


def test_error_wire_contains_only_fixed_public_code():
    error = WorkerFailure.model_validate_json(error_result("query_error"))
    assert error.error_code == "query_error"
    assert set(json.loads(error_result("invalid_bundle"))) == {
        "schema_version",
        "status",
        "error_code",
    }


def test_explicit_csv_types_are_loaded_without_duckdb(tmp_path):
    tables = tmp_path / "tables"
    tables.mkdir()
    (tables / "customers.csv").write_text("customer_id,eligible\nC1,true\n", encoding="utf-8")
    (tables / "orders.csv").write_text(
        "order_id,customer_id,amount_minor,currency,status,occurred_at\n"
        "O1,C1,10000,USD,settled,2026-01-02T03:04:05Z\n"
        "O2,C1,,USD,pending,2026-01-02T03:04:05Z\n",
        encoding="utf-8",
    )
    (tables / "order_items.csv").write_text(
        "item_id,order_id,quantity,amount_minor\nI1,O1,1,10000\n", encoding="utf-8"
    )
    assert read_table_rows("customers", tmp_path) == [("C1", True)]
    assert read_table_rows("orders", tmp_path) == [
        ("O1", "C1", 10000, "USD", "settled", datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)),
        ("O2", "C1", None, "USD", "pending", datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)),
    ]
    assert read_table_rows("order_items", tmp_path) == [("I1", "O1", 1, 10000)]


@pytest.mark.parametrize(
    "content",
    [
        "wrong,headers\nC1,true\n",
        "customer_id,eligible\nC1,true,extra\n",
        "customer_id,eligible\nC1\n",
        "customer_id,eligible\nC1,TRUE\n",
        "customer_id,eligible\nC1,true\nC1,true\n",
        "customer_id,eligible\n../../private,true\n",
        'customer_id,eligible\n"unterminated,true\n',
    ],
)
def test_malformed_csv_is_rejected_with_no_source_exception_text(tmp_path, content):
    tables = tmp_path / "tables"
    tables.mkdir()
    (tables / "customers.csv").write_text(content, encoding="utf-8")
    with pytest.raises(WorkerError) as error:
        read_table_rows("customers", tmp_path)
    assert str(error.value) == "invalid_bundle"


def test_csv_path_is_never_supplied_by_the_request(tmp_path):
    with pytest.raises(WorkerError, match="invalid_bundle"):
        read_table_rows("../private", tmp_path)


@pytest.mark.parametrize(
    "timestamp",
    ["2026-01-02T03:04:05.1234567Z", "2026-01-02T03:04:05+00:00", "2026-01-02", "invalidZ"],
)
def test_csv_timestamp_conversion_never_silently_discards_precision(tmp_path, timestamp):
    tables = tmp_path / "tables"
    tables.mkdir()
    (tables / "orders.csv").write_text(
        "order_id,customer_id,amount_minor,currency,status,occurred_at\n"
        f"O1,C1,10000,USD,settled,{timestamp}\n",
        encoding="utf-8",
    )
    with pytest.raises(WorkerError, match="invalid_bundle"):
        read_table_rows("orders", tmp_path)
