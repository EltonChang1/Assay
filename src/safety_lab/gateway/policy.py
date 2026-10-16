"""Fail-closed capability policy for the first DuckDB SELECT subset.

This module performs no database execution and imports only stdlib/sqlglot so
the same policy can run inside the worker. Policy approval is not proof of query
correctness or a substitute for worker isolation and resource limits.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

import sqlglot
from sqlglot import exp
from sqlglot.errors import ErrorLevel, SqlglotError
from sqlglot.optimizer.normalize_identifiers import normalize_identifiers
from sqlglot.optimizer.scope import Scope, traverse_scope

POLICY_VERSION = "duckdb-select-1.0"
MAX_QUERY_BYTES = 16_384
MAX_AST_NODES = 512
MAX_AST_DEPTH = 32
_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
_SYSTEM_PREFIXES = ("pg_", "sqlite_", "duckdb_", "information_schema")


class SQLPolicyError(ValueError):
    """The supplied query exceeds the explicit supported capability."""


@dataclass(frozen=True)
class ValidatedQuery:
    exact_sql: str
    query_sha256: str
    normalized_sql: str
    source_ids: tuple[str, ...]
    policy_version: str


# Exact node classes and meaningful argument names are both allowlisted. This
# avoids inheriting new syntax through subclasses or ignored optional modifiers.
_ALLOWED_ARGS: dict[type[exp.Expression], frozenset[str]] = {
    exp.Select: frozenset(
        {
            "expressions",
            "from_",
            "joins",
            "where",
            "group",
            "having",
            "order",
            "limit",
            "offset",
            "with_",
            "distinct",
        }
    ),
    exp.From: frozenset({"this"}),
    exp.Table: frozenset({"this", "alias"}),
    exp.TableAlias: frozenset({"this", "columns"}),
    exp.Identifier: frozenset({"this", "quoted"}),
    exp.Column: frozenset({"this", "table"}),
    exp.Alias: frozenset({"this", "alias"}),
    exp.Star: frozenset(),
    exp.Literal: frozenset({"this", "is_string"}),
    exp.Boolean: frozenset({"this"}),
    exp.Null: frozenset(),
    exp.Where: frozenset({"this"}),
    exp.Group: frozenset({"expressions"}),
    exp.Having: frozenset({"this"}),
    exp.Order: frozenset({"expressions"}),
    exp.Ordered: frozenset({"this", "desc", "nulls_first"}),
    exp.Limit: frozenset({"expression"}),
    exp.Offset: frozenset({"expression"}),
    exp.Join: frozenset({"this", "on", "using", "side", "kind"}),
    exp.With: frozenset({"expressions"}),
    exp.CTE: frozenset({"this", "alias"}),
    exp.Subquery: frozenset({"this", "alias"}),
    exp.Exists: frozenset({"this"}),
    exp.Distinct: frozenset({"expressions"}),
    exp.Case: frozenset({"this", "ifs", "default"}),
    exp.If: frozenset({"this", "true", "false"}),
    exp.Filter: frozenset({"this", "expression"}),
    exp.Between: frozenset({"this", "low", "high"}),
    exp.In: frozenset({"this", "expressions", "query"}),
    exp.Tuple: frozenset({"expressions"}),
    exp.Cast: frozenset({"this", "to"}),
    exp.DataType: frozenset({"this", "expressions"}),
    exp.DataTypeParam: frozenset({"this"}),
    exp.Count: frozenset({"this", "big_int"}),
    exp.Coalesce: frozenset({"this", "expressions"}),
    exp.Nullif: frozenset({"this", "expression"}),
    exp.Round: frozenset({"this", "decimals"}),
}
for _unary in (
    exp.Paren,
    exp.Not,
    exp.Neg,
    exp.Sum,
    exp.Avg,
    exp.Min,
    exp.Max,
    exp.Abs,
    exp.Floor,
    exp.Ceil,
):
    _ALLOWED_ARGS[_unary] = frozenset({"this"})
for _binary in (
    exp.And,
    exp.Or,
    exp.EQ,
    exp.NEQ,
    exp.GT,
    exp.GTE,
    exp.LT,
    exp.LTE,
    exp.Is,
    exp.Like,
    exp.ILike,
    exp.Add,
    exp.Sub,
    exp.Mul,
    exp.Div,
    exp.IntDiv,
    exp.Mod,
):
    _ALLOWED_ARGS[_binary] = frozenset({"this", "expression"})

_CAST_TYPES = frozenset(
    {
        exp.DataType.Type.BOOLEAN,
        exp.DataType.Type.TINYINT,
        exp.DataType.Type.SMALLINT,
        exp.DataType.Type.INT,
        exp.DataType.Type.BIGINT,
        exp.DataType.Type.INT128,
        exp.DataType.Type.FLOAT,
        exp.DataType.Type.DOUBLE,
        exp.DataType.Type.DECIMAL,
        exp.DataType.Type.VARCHAR,
        exp.DataType.Type.DATE,
        exp.DataType.Type.TIMESTAMP,
        exp.DataType.Type.TIMESTAMPTZ,
    }
)


def _meaningful(value: object) -> bool:
    return (
        value is not None
        and value is not False
        and not (isinstance(value, (list, tuple)) and not value)
    )


def _check_type(node: exp.DataType) -> None:
    if node.this not in _CAST_TYPES:
        raise SQLPolicyError("Unsupported SQL capability: cast data type")
    parameters = node.expressions
    if not parameters:
        return
    if node.this != exp.DataType.Type.DECIMAL or len(parameters) not in (1, 2):
        raise SQLPolicyError("Unsupported SQL capability: cast parameters")
    values: list[int] = []
    for parameter in parameters:
        literal = parameter.this
        if (
            not isinstance(parameter, exp.DataTypeParam)
            or not isinstance(literal, exp.Literal)
            or literal.is_string
            or not re.fullmatch(r"[0-9]{1,2}", literal.this)
        ):
            raise SQLPolicyError("Unsupported SQL capability: decimal precision or scale")
        values.append(int(literal.this))
    if not 1 <= values[0] <= 38 or (len(values) == 2 and not 0 <= values[1] <= values[0]):
        raise SQLPolicyError("Unsupported SQL capability: decimal precision or scale")


def _check_nodes(tree: exp.Expression, literal_starts: set[int]) -> None:
    stack = [(tree, 1)]
    count = 0
    while stack:
        node, depth = stack.pop()
        count += 1
        if count > MAX_AST_NODES or depth > MAX_AST_DEPTH:
            raise SQLPolicyError("Unsupported SQL capability: AST size or depth limit")
        allowed = _ALLOWED_ARGS.get(type(node))
        if allowed is None:
            raise SQLPolicyError(f"Unsupported SQL capability: {type(node).__name__}")
        for key, value in node.args.items():
            if key not in allowed and _meaningful(value):
                raise SQLPolicyError(f"Unsupported SQL capability: {type(node).__name__}.{key}")
        if isinstance(node, exp.Identifier) and not _NAME.fullmatch(node.name):
            raise SQLPolicyError("Unsupported SQL capability: identifier spelling")
        if isinstance(node, exp.Identifier) and node.meta.get("start") in literal_starts:
            # sqlglot rewrites FROM 'orders' into a quoted Identifier. Preserve
            # the source token distinction so a literal never becomes authority.
            raise SQLPolicyError("Unsupported SQL capability: literal used as an identifier")
        if isinstance(node, exp.Table) and type(node.this) is not exp.Identifier:
            raise SQLPolicyError("Unsupported SQL capability: table function or file source")
        if isinstance(node, exp.Join):
            if node.args.get("side") not in (None, "", "LEFT", "RIGHT", "FULL"):
                raise SQLPolicyError("Unsupported SQL capability: join side")
            if node.args.get("kind") not in (None, "", "INNER", "OUTER", "CROSS", "SEMI", "ANTI"):
                raise SQLPolicyError("Unsupported SQL capability: join kind")
        if isinstance(node, exp.CTE) and type(node.this) is not exp.Select:
            raise SQLPolicyError("Unsupported SQL capability: non-SELECT CTE")
        if isinstance(node, exp.DataType):
            _check_type(node)
        stack.extend((child, depth + 1) for child in node.iter_expressions())


def _source_ids(tree: exp.Expression, approved: dict[str, str]) -> tuple[str, ...]:
    """Resolve each table within its actual CTE/subquery scope, never globally."""

    seen: set[int] = set()
    sources: set[str] = set()
    for scope in traverse_scope(tree):
        for node, source in scope.selected_sources.values():
            if isinstance(node, exp.Table):
                seen.add(id(node))
            if isinstance(source, exp.Table):
                source_id = approved.get(source.name.casefold())
                if source_id is None:
                    raise SQLPolicyError("Unsupported SQL capability: relation is not approved")
                sources.add(source_id)
            elif not isinstance(source, Scope):
                raise SQLPolicyError("Unsupported SQL capability: unresolved relation")
    if any(id(table) not in seen for table in tree.find_all(exp.Table)):
        raise SQLPolicyError("Unsupported SQL capability: unresolved table scope")
    return tuple(sorted(sources))


def validate_sql(query: str, allowed_tables: tuple[str, ...]) -> ValidatedQuery:
    """Authorize one bounded SELECT and preserve its exact submitted-byte hash.

    Approved relation IDs must be simple identifiers. The supported subset has
    ordinary CTEs/subqueries, joins, aggregate/null/arithmetic expressions, CASE,
    filters, ordering, limits, and primitive casts/date-literal comparisons.
    Unsupported syntax and functions always raise a visible capability error.
    """

    if not isinstance(query, str):
        raise SQLPolicyError("SQL query must be text")
    if len(query) > MAX_QUERY_BYTES:
        raise SQLPolicyError("Unsupported SQL capability: query byte limit")
    try:
        encoded = query.encode("utf-8")
    except UnicodeError as exc:
        raise SQLPolicyError("SQL query must be valid UTF-8 text") from exc
    if not encoded or len(encoded) > MAX_QUERY_BYTES:
        raise SQLPolicyError("Unsupported SQL capability: query byte limit")
    approved: dict[str, str] = {}
    for table in allowed_tables:
        if not isinstance(table, str) or not _NAME.fullmatch(table):
            raise SQLPolicyError("Approved relation IDs must be simple identifiers")
        key = table.casefold()
        if key.startswith(_SYSTEM_PREFIXES):
            raise SQLPolicyError("Approved relation IDs cannot name system or catalog relations")
        if key in approved:
            raise SQLPolicyError("Approved relation IDs must be unique ignoring case")
        approved[key] = table
    try:
        statements = sqlglot.parse(query, read="duckdb", error_level=ErrorLevel.RAISE)
        if len(statements) != 1 or type(statements[0]) is not exp.Select:
            raise SQLPolicyError("Unsupported SQL capability: exactly one SELECT is required")
        tree = statements[0]
        assert tree is not None
        literal_starts = {
            token.start
            for token in sqlglot.tokenize(query, read="duckdb")
            if "STRING" in token.token_type.name
        }
        _check_nodes(tree, literal_starts)
        # DuckDB resolves quoted and unquoted identifiers without case sensitivity.
        tree = normalize_identifiers(tree, dialect="duckdb")
        sources = _source_ids(tree, approved)
        normalized = tree.sql(dialect="duckdb", comments=False, unsupported_level=ErrorLevel.RAISE)
    except SQLPolicyError:
        raise
    except (SqlglotError, RecursionError, ValueError) as exc:
        raise SQLPolicyError(
            "Unsupported SQL capability: query parse or scope resolution failed"
        ) from exc
    return ValidatedQuery(
        exact_sql=query,
        query_sha256=hashlib.sha256(encoded).hexdigest(),
        normalized_sql=normalized,
        source_ids=sources,
        policy_version=POLICY_VERSION,
    )
