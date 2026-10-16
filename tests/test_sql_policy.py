"""Capability checks only: these tests never execute the submitted SQL."""

from __future__ import annotations

import hashlib
from dataclasses import FrozenInstanceError

import pytest

from safety_lab.gateway import SQLPolicyError, validate_sql
from safety_lab.gateway.policy import MAX_QUERY_BYTES, POLICY_VERSION

TABLES = ("orders", "order_items", "customers")


@pytest.mark.parametrize(
    "query",
    [
        "SELECT SUM(o.amount_minor * 0.01) AS revenue_usd FROM orders o "
        "WHERE o.status = 'settled' AND o.currency = 'USD' "
        "AND o.occurred_at >= TIMESTAMPTZ '2026-01-01 00:00:00+00' "
        "AND o.occurred_at < TIMESTAMPTZ '2026-04-01 00:00:00+00'",
        "SELECT SUM(o.amount_minor * 0.01) FROM orders o JOIN order_items i USING (order_id)",
        "SELECT SUM(o.amount_minor * 0.01) FROM orders o WHERE EXISTS "
        "(SELECT 1 FROM order_items i WHERE i.order_id = o.order_id)",
        "WITH item_orders AS (SELECT order_id FROM order_items GROUP BY order_id) "
        "SELECT SUM(o.amount_minor * 0.01) FROM orders o "
        "JOIN item_orders i USING (order_id)",
        "SELECT SUM(DISTINCT o.amount_minor * 0.01) FROM orders o "
        "JOIN order_items i USING (order_id)",
        "SELECT COUNT(*), COUNT(DISTINCT order_id), AVG(amount_minor), "
        "MIN(amount_minor), MAX(amount_minor) FROM orders",
        "SELECT CASE WHEN amount_minor IS NULL THEN 0 ELSE amount_minor END / 100 "
        "FROM orders WHERE status IN ('settled', 'pending') AND NOT order_id = 'x'",
        "SELECT CAST(amount_minor AS DECIMAL(18, 2)), CAST(occurred_at AS DATE) FROM orders",
        "SELECT COALESCE(amount_minor, 0), NULLIF(amount_minor, 0), "
        "ABS(amount_minor), ROUND(amount_minor / 100, 2), FLOOR(amount_minor), "
        "CEIL(amount_minor) FROM orders",
        "SELECT status, SUM(amount_minor) FILTER (WHERE amount_minor > 0) FROM orders "
        "GROUP BY status HAVING COUNT(*) >= 1 ORDER BY status DESC LIMIT 10 OFFSET 1",
        "SELECT o.* FROM orders AS o LEFT JOIN customers AS c "
        "ON c.customer_id = o.customer_id WHERE c.eligible IS TRUE",
        "SELECT * FROM (SELECT order_id FROM orders) AS selected_orders",
        "SELECT 1 AS answer",
        "SELECT '; COPY orders TO secret.csv' AS harmless_text FROM orders;",
    ],
)
def test_supported_analytical_subset(query: str) -> None:
    result = validate_sql(query, TABLES)
    assert result.exact_sql == query
    assert result.policy_version == POLICY_VERSION
    assert result.query_sha256 == hashlib.sha256(query.encode("utf-8")).hexdigest()


def test_receipt_has_exact_hash_normalized_form_and_resolved_sources() -> None:
    query = " select SUM(o.amount_minor) from Orders o -- harmless comment\n"
    result = validate_sql(query, TABLES)
    same = validate_sql("SELECT SUM(o.amount_minor) FROM orders AS o", TABLES)
    assert result.query_sha256 != same.query_sha256
    assert result.normalized_sql == same.normalized_sql
    assert result.source_ids == ("orders",)
    with pytest.raises(FrozenInstanceError):
        result.exact_sql = "changed"  # type: ignore[misc]


def test_cte_sources_are_actual_base_tables_and_case_insensitive() -> None:
    query = (
        'WITH "ITEM_ORDERS" AS (SELECT order_id FROM order_items GROUP BY order_id) '
        "SELECT * FROM Orders o JOIN item_orders i ON o.order_id = i.order_id"
    )
    assert validate_sql(query, TABLES).source_ids == ("order_items", "orders")
    shadowed = "WITH orders AS (SELECT * FROM orders) SELECT * FROM orders"
    assert validate_sql(shadowed, TABLES).source_ids == ("orders",)


@pytest.mark.parametrize(
    "query",
    [
        "SELECT * FROM read_csv('/etc/passwd')",
        "SELECT * FROM read_csv_auto('/etc/passwd')",
        "SELECT * FROM read_parquet('https://example.invalid/private.parquet')",
        "SELECT * FROM '/etc/passwd'",
        "SELECT * FROM 'orders'",
        'SELECT * FROM "/etc/passwd"',
        "SELECT * FROM main.orders",
        "SELECT * FROM information_schema.tables",
        "SELECT * FROM pg_catalog.pg_tables",
        "SELECT * FROM duckdb_tables()",
        "SELECT * FROM sqlite_scan('/tmp/x.db', 'secrets')",
        "SELECT * FROM query('SELECT * FROM secrets')",
        "SELECT * FROM unapproved",
        "SELECT current_setting('home_directory')",
        "SELECT getenv('AWS_SECRET_ACCESS_KEY')",
        "SELECT read_blob('/etc/passwd')",
        "SELECT COALESCE((SELECT content FROM read_text('/etc/passwd')), 'x')",
        "SELECT * FROM orders; COPY orders TO '/tmp/exfil.csv'",
        "COPY (SELECT * FROM orders) TO '/tmp/exfil.csv'",
        "ATTACH '/tmp/secrets.db' AS secrets",
        "PRAGMA database_list",
        "SET enable_external_access = true",
        "INSTALL httpfs",
        "LOAD httpfs",
        "UPDATE orders SET amount_minor = 0",
        "DELETE FROM orders",
        "INSERT INTO orders VALUES ('x')",
        "CREATE TABLE exfil AS SELECT * FROM orders",
        "SELECT * INTO exfil FROM orders",
        "WITH RECURSIVE recursive_orders AS (SELECT * FROM orders) SELECT * FROM recursive_orders",
        "SELECT * FROM orders UNION ALL SELECT * FROM order_items",
        "SELECT ROW_NUMBER() OVER () FROM orders",
        "SELECT * FROM range(100)",
        "SELECT random() FROM orders",
        "SELECT CAST(amount_minor AS JSON) FROM orders",
        "SELECT TRY_CAST(amount_minor AS INTEGER) FROM orders",
        "SELECT * EXCLUDE (amount_minor) FROM orders",
        "SELECT * FROM orders NATURAL JOIN customers",
        "SELECT * FROM orders USING SAMPLE 10 ROWS",
        "SELECT amount_minor::VARCHAR COLLATE nocase FROM orders",
        "SELECT * FROM orders FOR UPDATE",
        "WITH malicious AS (SELECT * FROM read_csv('/etc/passwd')) SELECT 1",
    ],
)
def test_denied_capabilities(query: str) -> None:
    with pytest.raises(SQLPolicyError, match="Unsupported SQL capability"):
        validate_sql(query, TABLES)


def test_nested_cte_cannot_authorize_an_out_of_scope_system_relation() -> None:
    query = (
        "WITH x AS (SELECT * FROM orders), "
        "y AS (WITH pg_tables AS (SELECT 1) SELECT 1) SELECT * FROM pg_tables"
    )
    with pytest.raises(SQLPolicyError, match="not approved"):
        validate_sql(query, TABLES)


@pytest.mark.parametrize(
    "query", ["", " ", "-- comment only", "SELECT (", "SELECT 1; SELECT 2", "SELECT 1;;"]
)
def test_empty_malformed_or_multiple_statements_fail(query: str) -> None:
    with pytest.raises(SQLPolicyError):
        validate_sql(query, TABLES)


def test_query_utf8_byte_node_and_depth_limits() -> None:
    with pytest.raises(SQLPolicyError, match="byte limit"):
        validate_sql("SELECT '" + "é" * (MAX_QUERY_BYTES // 2) + "'", TABLES)
    with pytest.raises(SQLPolicyError, match="AST size or depth"):
        validate_sql("SELECT " + ", ".join("1" for _ in range(513)), TABLES)
    with pytest.raises(SQLPolicyError, match="AST size or depth"):
        validate_sql("SELECT " + "(" * 40 + "1" + ")" * 40, TABLES)
    with pytest.raises(SQLPolicyError):
        validate_sql("SELECT " + "(" * 1500 + "1" + ")" * 1500, TABLES)
    with pytest.raises(SQLPolicyError, match="UTF-8"):
        validate_sql("SELECT '\ud800'", TABLES)


@pytest.mark.parametrize(
    "tables",
    [("orders", "Orders"), ("orders.csv",), ("main.orders",), ("pg_tables",), ("sqlite_master",)],
)
def test_invalid_approved_relation_configuration(tables: tuple[str, ...]) -> None:
    with pytest.raises(SQLPolicyError):
        validate_sql("SELECT 1", tables)


@pytest.mark.parametrize("data_type", ["DECIMAL(0)", "DECIMAL(39)", "DECIMAL(5,6)", "VARCHAR(20)"])
def test_unsupported_cast_parameters_fail(data_type: str) -> None:
    with pytest.raises(SQLPolicyError):
        validate_sql(f"SELECT CAST(amount_minor AS {data_type}) FROM orders", TABLES)
