# Initial SQL capability policy

Policy version: `duckdb-select-1.0`. Implementation: `src/safety_lab/gateway/policy.py`, using the locked sqlglot DuckDB dialect. This is a pure parser/authorization component for P2.1; it neither executes SQL nor establishes the G2 worker boundary.

## Supported subset

One `SELECT` may use approved, unqualified, simply named tables; aliases; ordinary nonrecursive CTEs; SELECT subqueries and `EXISTS`; ordinary inner/outer/cross/semi/anti joins with `ON` or `USING`; `WHERE`, `GROUP BY`, `HAVING`, `ORDER BY`, `LIMIT`, and `OFFSET`.

Expressions include ordinary column references, stars, literals, `DISTINCT`, `CASE`/`IF`, comparisons, boolean combinations, `IN`, `BETWEEN`, `IS NULL`, `LIKE`/`ILIKE`, arithmetic, aggregate filters, and the explicit functions `SUM`, `COUNT`, `AVG`, `MIN`, `MAX`, `COALESCE`, `NULLIF`, `ABS`, `ROUND`, `FLOOR`, and `CEIL`. Primitive numeric/boolean/text/date/timestamp casts are allowed. `DECIMAL` precision is 1–38 and scale is 0–precision. Date/timestamp literals and their comparisons work through the permitted casts.

For example, these different analytical strategies are supported:

```sql
SELECT SUM(amount_minor * 0.01) AS revenue_usd
FROM orders
WHERE status = 'settled'
  AND occurred_at >= TIMESTAMPTZ '2026-01-01 00:00:00+00'
  AND occurred_at < TIMESTAMPTZ '2026-04-01 00:00:00+00';

WITH item_orders AS (
  SELECT order_id FROM order_items GROUP BY order_id
)
SELECT SUM(o.amount_minor * 0.01) AS revenue_usd
FROM orders o JOIN item_orders i USING (order_id);
```

The policy also permits a duplicated join and `SUM(DISTINCT amount_minor)`; both can be analytically wrong. Metric checks and the independent scorer must detect those errors. Authorization never proves metric correctness.

## Explicit rejection

Every AST node class and meaningful argument must be allowlisted. Unknown functions or modifiers produce `SQLPolicyError`, a visible capability error. Table functions, literal/file/URL sources, qualified database/schema tables, system/catalog relations, external reads, commands, writes, extensions, configuration changes, multiple statements, recursive CTEs, set operations, windows, samples, pivots, and unsupported casts are outside this subset.

Approved relation IDs and SQL identifiers use ASCII letters/digits/underscores, with a letter or underscore first. Approved base names cannot use the reserved `pg_`, `sqlite_`, `duckdb_`, or `information_schema` prefixes. DuckDB case-insensitive resolution applies to quoted and unquoted names. CTE names are resolved in their actual scopes: an unused or nested CTE cannot authorize a same-named external relation. Every table node must resolve to an approved base table or a visible CTE. Source IDs include the actual approved base tables, including those beneath CTEs and subqueries.

Limits are 16,384 UTF-8 query bytes, 512 AST nodes, and depth 32. Parser recursion/errors fail closed. Literal source tokens remain disallowed even when sqlglot normalizes them to quoted identifiers.

## Receipt and execution contract

`validate_sql(query, allowed_tables)` returns a frozen record containing the exact submitted SQL, its SHA-256 over exact UTF-8 bytes, normalized DuckDB SQL, sorted base source IDs, and policy version. Formatting/comments can change the submitted hash even when the normalized form is identical. A receipt must preserve both forms and identify which was executed.

The future/external worker must apply this policy itself and execute only inside its restricted database and OS/container boundary. The gateway must not replace an unavailable worker with host SQL. CPU, memory, time, disk/output caps, database hardening, immutable input validation, host-captured results, and authoritative receipts remain separate requirements. Policy tests exercise supported queries and rejected capabilities without executing supplied SQL.
