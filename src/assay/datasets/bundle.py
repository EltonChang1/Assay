"""Allowlisted public exports and a deliberately separate private event file.

The manifest and checksum detect changes; filesystem/process isolation is a later
runtime responsibility. Export creation never overwrites an existing directory.
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
from datetime import datetime
from pathlib import Path

from pydantic import ValidationError

from assay.contracts import DatasetSnapshot, TaskSpec, VersionedModel, canonical_json_bytes

from .sales import (
    TABLE_COLUMNS,
    CanonicalOrderEvent,
    CustomerRow,
    OrderItemRow,
    OrderRow,
    SalesFixture,
    fixture_tables,
    snapshot_identity,
    table_csv_bytes,
)


class BundleValidationError(ValueError):
    """The public bundle does not satisfy its immutable content contract."""


class PrivateFixtureRecord(VersionedModel):
    """Canonical source events for a private, independently implemented oracle."""

    task_id: str
    snapshot_id: str
    generator_seed: int
    canonical_orders: tuple[CanonicalOrderEvent, ...]


def write_public_bundle(fixture: SalesFixture, output_dir: str | Path) -> DatasetSnapshot:
    """Write only the public contract, CSV tables, and content manifest/checksum."""

    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=False)
    (target / "tables").mkdir()
    (target / "task.json").write_bytes(canonical_json_bytes(fixture.public_task))
    for name, content in fixture_tables(fixture).items():
        (target / "tables" / f"{name}.csv").write_bytes(content)
    manifest = canonical_json_bytes(fixture.snapshot)
    (target / "manifest.json").write_bytes(manifest)
    (target / "manifest.sha256").write_text(
        hashlib.sha256(manifest).hexdigest() + "\n", encoding="ascii", newline="\n"
    )
    return validate_public_bundle(target)


def write_private_fixture(fixture: SalesFixture, output_path: str | Path) -> Path:
    """Write evaluator-only inputs outside any existing public bundle tree."""

    target = Path(output_path).resolve()
    for parent in (target.parent, *target.parents):
        if (parent / "manifest.json").exists() and (parent / "task.json").exists():
            raise ValueError("private canonical events cannot be written inside a public bundle")
    record = PrivateFixtureRecord(
        task_id=fixture.public_task.task_id,
        snapshot_id=fixture.snapshot.snapshot_id,
        generator_seed=fixture.generator_seed,
        canonical_orders=fixture.canonical_orders,
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as stream:
        stream.write(canonical_json_bytes(record))
    return target


def _read_table(content: bytes, table_id: str) -> tuple[VersionedModel, ...]:
    columns = TABLE_COLUMNS[table_id]
    reader = csv.DictReader(io.StringIO(content.decode("utf-8"), newline=""))
    if reader.fieldnames != [column.name for column in columns]:
        raise BundleValidationError("CSV column order disagrees with the declared schema")
    models: dict[str, type[VersionedModel]] = {
        "customers": CustomerRow,
        "orders": OrderRow,
        "order_items": OrderItemRow,
    }
    model = models[table_id]
    records: list[VersionedModel] = []
    for row in reader:
        if None in row or any(value is None for value in row.values()):
            raise BundleValidationError("CSV row width disagrees with the declared schema")
        values: dict[str, object] = {}
        for column in columns:
            value = row[column.name]
            if value == "" and column.nullable:
                values[column.name] = None
            elif value == "":
                raise BundleValidationError("non-nullable CSV value is empty")
            elif column.data_type == "integer":
                if re.fullmatch(r"0|-?[1-9][0-9]*", value) is None:
                    raise BundleValidationError("integer CSV value is not canonical")
                values[column.name] = int(value)
            elif column.data_type == "boolean":
                if value not in ("true", "false"):
                    raise BundleValidationError("boolean CSV value must be true or false")
                values[column.name] = value == "true"
            elif column.data_type == "timestamp_utc":
                if not value.endswith("Z"):
                    raise BundleValidationError("CSV timestamps must use explicit UTC Z suffix")
                values[column.name] = datetime.fromisoformat(value)
            else:
                values[column.name] = value
        records.append(model.model_validate(values))
    return tuple(records)


def _validate_relations(rows: dict[str, tuple[VersionedModel, ...]]) -> None:
    for table, key in (
        ("customers", "customer_id"),
        ("orders", "order_id"),
        ("order_items", "item_id"),
    ):
        ids = [getattr(row, key) for row in rows[table]]
        if len(set(ids)) != len(ids):
            raise BundleValidationError("primary key values must be unique")
    customers = tuple(row for row in rows["customers"] if isinstance(row, CustomerRow))
    orders = tuple(row for row in rows["orders"] if isinstance(row, OrderRow))
    order_items = tuple(row for row in rows["order_items"] if isinstance(row, OrderItemRow))
    if (
        len(customers) != len(rows["customers"])
        or len(orders) != len(rows["orders"])
        or len(order_items) != len(rows["order_items"])
    ):
        raise BundleValidationError("relational row types disagree with their tables")
    customer_ids = {row.customer_id for row in customers}
    order_ids = {row.order_id for row in orders}
    if any(row.customer_id not in customer_ids for row in orders):
        raise BundleValidationError("order references an unknown customer")
    if any(row.order_id not in order_ids for row in order_items):
        raise BundleValidationError("item references an unknown order")
    if {row.order_id for row in order_items} != order_ids:
        raise BundleValidationError("every generated order requires at least one item")
    for order in orders:
        items = [row for row in order_items if row.order_id == order.order_id]
        amounts = [item.amount_minor for item in items]
        order_amount = order.amount_minor
        if order_amount is None:
            if any(amount is not None for amount in amounts):
                raise BundleValidationError("unknown order amount must remain unknown in its items")
        elif (
            any(amount is None for amount in amounts)
            or sum(amount for amount in amounts if amount is not None) != order_amount
        ):
            raise BundleValidationError("line item amounts must sum to their order amount")


def validate_public_bundle(output_dir: str | Path) -> DatasetSnapshot:
    """Verify exact hashes, allowlisted files, schema, scope, and relational keys."""

    target = Path(output_dir)
    try:
        if target.is_symlink() or target.is_junction():
            raise BundleValidationError(
                "public bundle directory cannot be a symbolic link or junction"
            )
        paths = tuple(target.rglob("*"))
        if any(path.is_symlink() or path.is_junction() for path in paths):
            raise BundleValidationError("public bundle cannot contain symbolic links or junctions")
        manifest_bytes = (target / "manifest.json").read_bytes()
        checksum = (target / "manifest.sha256").read_bytes()
        if checksum != (hashlib.sha256(manifest_bytes).hexdigest() + "\n").encode("ascii"):
            raise BundleValidationError("manifest checksum mismatch")
        snapshot = DatasetSnapshot.model_validate_json(manifest_bytes)
        if canonical_json_bytes(snapshot) != manifest_bytes:
            raise BundleValidationError("manifest serialization is not canonical")
        expected = {"task.json", "manifest.json", "manifest.sha256"}
        expected.update(table.path for table in snapshot.tables)
        actual = {path.relative_to(target).as_posix() for path in paths if path.is_file()}
        if actual != expected:
            raise BundleValidationError("public bundle contains missing or non-allowlisted files")
        task_bytes = (target / "task.json").read_bytes()
        if hashlib.sha256(task_bytes).hexdigest() != snapshot.task_sha256:
            raise BundleValidationError("public task checksum mismatch")
        task = TaskSpec.model_validate_json(task_bytes)
        if canonical_json_bytes(task) != task_bytes:
            raise BundleValidationError("public task serialization is not canonical")
        if task.task_id != snapshot.task_id or task.permitted_snapshot_ids != (
            snapshot.snapshot_id,
        ):
            raise BundleValidationError("task and snapshot identities disagree")
        if {table.table_id for table in snapshot.tables} != set(TABLE_COLUMNS):
            raise BundleValidationError("snapshot must contain exactly the supported sales tables")
        if set(task.allowed_tables) != set(TABLE_COLUMNS):
            raise BundleValidationError("task table permissions disagree with its snapshot")
        if snapshot_identity(snapshot.tables) != snapshot.snapshot_id:
            raise BundleValidationError("snapshot content identity mismatch")
        rows: dict[str, tuple[VersionedModel, ...]] = {}
        for table in snapshot.tables:
            if table.columns != TABLE_COLUMNS[table.table_id]:
                raise BundleValidationError("table schema differs from the supported data contract")
            content = (target / table.path).read_bytes()
            if hashlib.sha256(content).hexdigest() != table.sha256:
                raise BundleValidationError("public table checksum mismatch")
            parsed = _read_table(content, table.table_id)
            if table_csv_bytes(parsed, table.columns) != content:
                raise BundleValidationError("public table CSV serialization is not canonical")
            if len(parsed) != table.row_count:
                raise BundleValidationError("public table row count mismatch")
            rows[table.table_id] = parsed
        _validate_relations(rows)
        return snapshot
    except BundleValidationError:
        raise
    except (OSError, UnicodeError, ValueError, ValidationError, csv.Error) as exc:
        raise BundleValidationError("invalid or unreadable public fixture bundle") from exc
