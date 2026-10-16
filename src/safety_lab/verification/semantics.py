"""A narrow, structural public SQL contract profile, never a private answer oracle.

The profile proves provenance and cardinality for supported relational shapes.
It never executes submitted SQL on the host or recomputes a gold metric. Public
rows are used only for missingness, key uniqueness, and join coverage/cardinality.
Unrecognized expressions return unknown, rather than inferring semantics from a
matching number or an output alias.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Literal

import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError

from safety_lab.contracts import TaskSpec

Outcome = Literal["pass", "fail", "unknown"]


@dataclass(frozen=True)
class Finding:
    name: str
    outcome: Outcome
    detail: str


@dataclass(frozen=True)
class PublicRows:
    """Complete rows from hash-checked, host-frozen public CSV artifacts."""

    orders: tuple[dict[str, str], ...]
    items: tuple[dict[str, str], ...]

    def eligible_orders(self, task: TaskSpec) -> tuple[dict[str, str], ...]:
        return tuple(
            row
            for row in self.orders
            if row["status"] == "settled"
            and row["currency"] == "USD"
            and task.time_scope.start
            <= datetime.fromisoformat(row["occurred_at"])
            < task.time_scope.end
        )


class UnsupportedShape(ValueError):
    """The profile cannot establish this query's analytical meaning."""


def _unparen(node: exp.Expression) -> exp.Expression:
    while isinstance(node, exp.Paren):
        node = node.this
    return node


def _column(node: exp.Expression, name: str, alias: str, *, unqualified: bool) -> bool:
    node = _unparen(node)
    return (
        isinstance(node, exp.Column)
        and node.name.casefold() == name
        and (node.table.casefold() == alias or (unqualified and not node.table))
    )


def _number(node: exp.Expression) -> Decimal | None:
    node = _unparen(node)
    if isinstance(node, exp.Literal) and not node.is_string:
        try:
            return Decimal(node.this)
        except InvalidOperation:
            return None
    return None


def _literal(node: exp.Expression) -> str | None:
    node = _unparen(node)
    if isinstance(node, exp.Literal) and node.is_string:
        return str(node.this)
    return None


def _instant(node: exp.Expression) -> datetime | None:
    node = _unparen(node)
    if isinstance(node, exp.Cast):
        target = node.args.get("to")
        if not isinstance(target, exp.DataType) or target.this not in (
            exp.DataType.Type.TIMESTAMP,
            exp.DataType.Type.TIMESTAMPTZ,
            exp.DataType.Type.DATE,
        ):
            return None
        node = node.this
    value = _literal(node)
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value)
        return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)
    except ValueError:
        return None


def _conjuncts(node: exp.Expression) -> list[exp.Expression]:
    node = _unparen(node)
    if isinstance(node, exp.And):
        return _conjuncts(node.this) + _conjuncts(node.expression)
    return [node]


def _plain_select(node: exp.Expression) -> exp.Select:
    if isinstance(node, exp.Subquery):
        if node.args.get("alias") and node.args["alias"].args.get("columns"):
            raise UnsupportedShape("derived column renaming is outside this profile")
        node = node.this
    if not isinstance(node, exp.Select):
        raise UnsupportedShape("only ordinary SELECT relational shapes are supported")
    return node


def _simple_table(select: exp.Select, table: str) -> exp.Table:
    source = select.args.get("from_")
    if not isinstance(source, exp.From) or not isinstance(source.this, exp.Table):
        raise UnsupportedShape("the base relation is not a supported public table")
    relation = source.this
    if relation.name.casefold() != table:
        raise UnsupportedShape(f"the base relation is not {table}")
    if relation.args.get("alias") and relation.args["alias"].args.get("columns"):
        raise UnsupportedShape("table column renaming is outside this profile")
    return relation


def _item_relation(node: exp.Expression, ctes: dict[str, exp.Expression]) -> tuple[str, bool]:
    """Return (visible alias, whether order_id has been deduplicated)."""

    alias = node.alias_or_name.casefold()
    if isinstance(node, exp.Table) and node.name.casefold() == "order_items":
        if node.args.get("alias") and node.args["alias"].args.get("columns"):
            raise UnsupportedShape("item column renaming is unsupported")
        return alias, False
    if isinstance(node, exp.Table) and node.name.casefold() in ctes:
        select = _plain_select(ctes[node.name.casefold()])
    elif isinstance(node, exp.Subquery):
        select = _plain_select(node)
    else:
        raise UnsupportedShape("only order_items joins are supported")
    relation = _simple_table(select, "order_items")
    if any(
        select.args.get(key) for key in ("joins", "where", "having", "limit", "offset", "with_")
    ):
        raise UnsupportedShape("filtered or nested item relations are outside this profile")
    item_alias = relation.alias_or_name.casefold()
    projections = select.expressions
    # Extra aggregate diagnostic columns cannot change order_id multiplicity.
    keys = [
        item
        for item in projections
        if _column(
            item.this if isinstance(item, exp.Alias) else item,
            "order_id",
            item_alias,
            unqualified=True,
        )
        and item.alias_or_name.casefold() == "order_id"
    ]
    group = select.args.get("group")
    distinct = select.args.get("distinct")
    if group:
        if len(group.expressions) != 1 or not _column(
            group.expressions[0], "order_id", item_alias, unqualified=True
        ):
            raise UnsupportedShape("item grouping must be exactly order_id")
        if not keys:
            raise UnsupportedShape("item grouping does not expose order_id")
        if any(
            not isinstance(item.this if isinstance(item, exp.Alias) else item, exp.AggFunc)
            for item in projections
            if item not in keys
        ):
            raise UnsupportedShape("item projection has an unsupported nonaggregate expression")
    elif distinct:
        if len(projections) != 1 or not keys:
            raise UnsupportedShape("DISTINCT item projection must contain only order_id")
    else:
        raise UnsupportedShape("item derived relation does not establish unique order_id")
    return alias, True


def _join_key(predicate: exp.Expression, order_alias: str, item_alias: str) -> bool:
    predicate = _unparen(predicate)
    if not isinstance(predicate, exp.EQ):
        return False
    return (
        _column(predicate.this, "order_id", order_alias, unqualified=False)
        and _column(predicate.expression, "order_id", item_alias, unqualified=False)
    ) or (
        _column(predicate.expression, "order_id", order_alias, unqualified=False)
        and _column(predicate.this, "order_id", item_alias, unqualified=False)
    )


def _exists(predicate: exp.Expression, order_alias: str) -> bool:
    if not isinstance(predicate, exp.Exists):
        return False
    try:
        select = _plain_select(predicate.this)
        item = _simple_table(select, "order_items")
        if any(
            select.args.get(key) for key in ("joins", "group", "having", "limit", "offset", "with_")
        ):
            return False
        where = select.args.get("where")
        return isinstance(where, exp.Where) and _join_key(
            where.this, order_alias, item.alias_or_name.casefold()
        )
    except UnsupportedShape:
        return False


def _population(select: exp.Select, alias: str, task: TaskSpec, rows: PublicRows) -> Finding:
    where = select.args.get("where")
    if not isinstance(where, exp.Where):
        return Finding("population", "fail", "Missing declared status, currency, and UTC filters")
    required = {"status", "currency", "start", "end"}
    seen: set[str] = set()
    unexpected = False
    for predicate in _conjuncts(where.this):
        if _exists(predicate, alias):
            covered = {row["order_id"] for row in rows.items}
            if any(row["order_id"] not in covered for row in rows.eligible_orders(task)):
                return Finding("population", "fail", "EXISTS excludes an eligible order")
            continue
        if not isinstance(predicate, (exp.EQ, exp.GTE, exp.GT, exp.LTE, exp.LT)):
            return Finding(
                "population", "unknown", "A predicate is outside the conjunction profile"
            )
        left, right = predicate.this, predicate.expression
        if isinstance(predicate, exp.EQ):
            for name, expected in (("status", "settled"), ("currency", "USD")):
                if (
                    _column(left, name, alias, unqualified=True) and _literal(right) == expected
                ) or (_column(right, name, alias, unqualified=True) and _literal(left) == expected):
                    seen.add(name)
                    break
            else:
                unexpected = True
        elif (
            isinstance(predicate, exp.GTE)
            and _column(left, "occurred_at", alias, unqualified=True)
            and _instant(right) == task.time_scope.start
        ) or (
            isinstance(predicate, exp.LTE)
            and _column(right, "occurred_at", alias, unqualified=True)
            and _instant(left) == task.time_scope.start
        ):
            seen.add("start")
        elif (
            isinstance(predicate, exp.LT)
            and _column(left, "occurred_at", alias, unqualified=True)
            and _instant(right) == task.time_scope.end
        ) or (
            isinstance(predicate, exp.GT)
            and _column(right, "occurred_at", alias, unqualified=True)
            and _instant(left) == task.time_scope.end
        ):
            seen.add("end")
        else:
            unexpected = True
    if unexpected or seen != required:
        return Finding("population", "fail", "Filters differ from the declared eligible population")
    return Finding(
        "population", "pass", "Exact settled/USD/inclusive-start/exclusive-end population"
    )


def _scaled_amount(node: exp.Expression, alias: str, *, unqualified: bool) -> Decimal | None:
    node = _unparen(node)
    if _column(node, "amount_minor", alias, unqualified=unqualified):
        return Decimal(1)
    if isinstance(node, exp.Div):
        denominator = _number(node.expression)
        scale = _scaled_amount(node.this, alias, unqualified=unqualified)
        if denominator is not None and denominator != 0 and scale is not None:
            return scale / denominator
    if isinstance(node, exp.Mul):
        left, right = _number(node.this), _number(node.expression)
        if left is not None:
            scale = _scaled_amount(node.expression, alias, unqualified=unqualified)
            return None if scale is None else left * scale
        if right is not None:
            scale = _scaled_amount(node.this, alias, unqualified=unqualified)
            return None if scale is None else right * scale
    return None


def _aggregate(
    node: exp.Expression, alias: str, metric_type: str, *, unqualified: bool
) -> tuple[Finding, Finding, bool]:
    node = _unparen(node)
    scale = Decimal(1)
    if isinstance(node, exp.Div) and _number(node.expression) not in (None, 0):
        denominator = _number(node.expression)
        assert denominator is not None
        scale /= denominator
        node = _unparen(node.this)
    elif isinstance(node, exp.Mul):
        if _number(node.expression) is not None:
            factor = _number(node.expression)
            assert factor is not None
            scale *= factor
            node = _unparen(node.this)
        elif _number(node.this) is not None:
            factor = _number(node.this)
            assert factor is not None
            scale *= factor
            node = _unparen(node.expression)
    if metric_type == "total" and isinstance(node, exp.Sum):
        if isinstance(node.this, exp.Distinct):
            return (
                Finding("metric", "fail", "SUM(DISTINCT amount) deduplicates values, not orders"),
                Finding("units", "unknown", "Distinct-value aggregation is not supported revenue"),
                False,
            )
        amount_scale = _scaled_amount(node.this, alias, unqualified=unqualified)
        if amount_scale is None:
            # Conditional or computed arguments may be correct (for example a
            # CASE-encoded status filter); only plainly different inputs fail.
            if not isinstance(_unparen(node.this), (exp.Column, exp.Literal)):
                raise UnsupportedShape("the SUM argument is outside the verified profile")
            return (
                Finding(
                    "metric", "fail", "The selected SUM does not derive from order amount_minor"
                ),
                Finding("units", "unknown", "No supported order-amount conversion"),
                False,
            )
        return (
            Finding("metric", "pass", "Selected cell aggregates public order amount_minor"),
            Finding(
                "units",
                "pass" if scale * amount_scale == Decimal("0.01") else "fail",
                "Order cents must be converted to USD by exactly 1/100",
            ),
            False,
        )
    if metric_type == "count" and isinstance(node, exp.Count):
        argument = _unparen(node.this)
        distinct = isinstance(argument, exp.Distinct)
        if distinct:
            if len(argument.expressions) != 1:
                raise UnsupportedShape("multicolumn distinct count is unsupported")
            argument = argument.expressions[0]
        valid = _column(argument, "order_id", alias, unqualified=unqualified) or (
            isinstance(argument, exp.Star) and not distinct
        )
        return (
            Finding("metric", "pass" if valid else "fail", "Count must count orders or order_id"),
            Finding("units", "pass" if scale == 1 else "fail", "Order counts require unit scale"),
            distinct,
        )
    if isinstance(node, (exp.Literal, exp.Column, exp.Count, exp.Sum, exp.Avg, exp.Min, exp.Max)):
        return (
            Finding("metric", "fail", "Selected expression does not establish the declared metric"),
            Finding("units", "unknown", "No supported metric conversion"),
            False,
        )
    raise UnsupportedShape("the selected aggregate expression is outside the verified profile")


def inspect_query(
    query: str, column: str, metric_type: str, task: TaskSpec, rows: PublicRows
) -> tuple[Finding, ...]:
    """Prove supported shapes; public diagnostic facts are never hidden labels."""

    try:
        parsed = sqlglot.parse_one(query, read="duckdb")
        if not isinstance(parsed, exp.Expression):
            raise UnsupportedShape("query did not parse to a single expression")
        select = _plain_select(parsed)
        if any(select.args.get(key) for key in ("group", "having", "distinct", "limit", "offset")):
            raise UnsupportedShape("top-level grouping, DISTINCT, or row selection is unsupported")
        order = _simple_table(select, "orders")
        alias = order.alias_or_name.casefold()
        ctes = {
            cte.alias_or_name.casefold(): cte.this
            for cte in (select.args["with_"].expressions if select.args.get("with_") else [])
        }
        matches = [item for item in select.expressions if item.alias_or_name == column]
        if len(matches) != 1:
            raise UnsupportedShape("the exact result column has no unique selected expression")
        selected = matches[0]
        selected = selected.this if isinstance(selected, exp.Alias) else selected
        joins = select.args.get("joins") or []
        if len(joins) > 1:
            raise UnsupportedShape("more than one join is outside the verified cardinality profile")
        deduplicated = False
        side = ""
        if joins:
            join = joins[0]
            side = (join.args.get("side") or "").upper()
            if side not in ("", "LEFT") or (join.args.get("kind") or "").upper() not in (
                "",
                "INNER",
                "OUTER",
            ):
                raise UnsupportedShape("only inner and left item joins are supported")
            item_alias, deduplicated = _item_relation(join.this, ctes)
            predicate = join.args.get("on")
            using = join.args.get("using")
            if not (
                isinstance(predicate, exp.Expression) and _join_key(predicate, alias, item_alias)
            ) and not (using and len(using) == 1 and using[0].name.casefold() == "order_id"):
                raise UnsupportedShape("join does not use only the order_id key")
        metric, units, distinct_count = _aggregate(
            selected, alias, metric_type, unqualified=not joins or deduplicated
        )
        population = _population(select, alias, task, rows)
        eligible = rows.eligible_orders(task)
        keys = [row["order_id"] for row in rows.orders]
        if len(set(keys)) != len(keys):
            grain = Finding("grain", "fail", "Public order_id is not unique")
        elif joins:
            counts = Counter(row["order_id"] for row in rows.items)
            missing = any(counts[row["order_id"]] == 0 for row in eligible)
            repeated = any(counts[row["order_id"]] > 1 for row in eligible)
            if missing and side != "LEFT":
                population = Finding(
                    "population", "fail", "Inner item join excludes an eligible order"
                )
            grain = Finding(
                "grain",
                "fail" if repeated and not deduplicated and not distinct_count else "pass",
                "Public join cardinality repeats order amounts"
                if repeated and not deduplicated and not distinct_count
                else "One contribution per eligible order is established",
            )
        else:
            grain = Finding("grain", "pass", "Unique public order_id, one source row per order")
        nulls = any(row["amount_minor"] == "" for row in eligible)
        missingness = Finding(
            "missingness",
            "fail" if metric_type == "total" and nulls else "pass",
            "Eligible order amount is missing; contract requires abstention"
            if nulls and metric_type == "total"
            else "Required public values are available",
        )
        # An empty population yields SQL SUM(NULL), so a numerical total requires
        # a separately supported explicit empty-set policy (not present in v1).
        if not eligible and metric_type == "total":
            missingness = Finding(
                "missingness", "unknown", "Empty population total policy is unsupported"
            )
        return metric, units, grain, population, missingness
    except (UnsupportedShape, SqlglotError, ValueError, TypeError, KeyError) as exc:
        return (Finding("semantics", "unknown", str(exc)),)
