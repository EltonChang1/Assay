"""Generation, canonical projection, and public/private export boundaries."""

import hashlib
import json
from collections import Counter
from decimal import Decimal

import pytest

from safety_lab.contracts import DatasetSnapshot, TaskSpec, canonical_json_bytes
from safety_lab.datasets import (
    BundleValidationError,
    PrivateFixtureRecord,
    generate_sales_fixture,
    validate_public_bundle,
    write_private_fixture,
    write_public_bundle,
)
from safety_lab.datasets.sales import snapshot_identity


@pytest.mark.parametrize("variant", ["base", "equal_amount", "insufficient", "historical"])
def test_seeded_generation_and_export_are_byte_reproducible(tmp_path, variant):
    first = generate_sales_fixture(seed=0, variant=variant)
    second = generate_sales_fixture(seed=0, variant=variant)
    assert first == second
    for name in ("one", "two"):
        exported = write_public_bundle(first, tmp_path / name)
        assert exported == first.snapshot
        assert validate_public_bundle(tmp_path / name) == exported
    for path in (tmp_path / "one").rglob("*"):
        if path.is_file():
            assert (
                path.read_bytes()
                == (tmp_path / "two" / path.relative_to(tmp_path / "one")).read_bytes()
            )


def test_nonzero_seed_controls_events_without_entering_public_contract():
    fixture = generate_sales_fixture(seed=772)
    assert fixture == generate_sales_fixture(seed=772)
    assert fixture.snapshot.snapshot_id != generate_sales_fixture(seed=773).snapshot.snapshot_id
    assert fixture.canonical_orders != generate_sales_fixture().canonical_orders
    assert b"seed" not in canonical_json_bytes(fixture.public_task)


def test_hand_fixture_has_correct_projection_and_demonstrates_duplication():
    fixture = generate_sales_fixture()
    assert [event.amount_minor for event in fixture.canonical_orders] == [10000, 8000, 2000]
    multiplicities = Counter(item.order_id for item in fixture.order_items)
    assert multiplicities == {"O1": 2, "O2": 1, "O3": 3}
    assert Decimal(sum(event.amount_minor for event in fixture.canonical_orders)) / 100 == Decimal(
        "200"
    )
    joined = sum(order.amount_minor * multiplicities[order.order_id] for order in fixture.orders)
    assert Decimal(joined) / 100 == Decimal("340")
    for event, order in zip(fixture.canonical_orders, fixture.orders, strict=True):
        assert event.order_id == order.order_id
        assert event.amount_minor == order.amount_minor
        assert event.occurred_at == order.occurred_at
        assert (
            sum(
                item.amount_minor for item in fixture.order_items if item.order_id == order.order_id
            )
            == order.amount_minor
        )


def test_equal_amount_orders_defeat_distinct_amount_shortcut():
    fixture = generate_sales_fixture(variant="equal_amount")
    assert sum(order.amount_minor for order in fixture.orders) == 30000
    assert sum({order.amount_minor for order in fixture.orders}) == 20000
    assert len({order.order_id for order in fixture.orders}) == 4


def test_insufficient_data_keeps_unknown_amounts_and_historical_scope_is_explicit():
    fixture = generate_sales_fixture(variant="insufficient")
    assert fixture.canonical_orders[2].amount_minor is None
    assert fixture.orders[2].amount_minor is None
    assert all(item.amount_minor is None for item in fixture.order_items if item.order_id == "O3")
    historical = generate_sales_fixture(variant="historical")
    assert historical.public_task.report_semantics == "historical"
    assert "historical snapshot" in historical.public_task.question
    current = generate_sales_fixture()
    assert historical.snapshot.snapshot_id != current.snapshot.snapshot_id
    assert historical.public_task.task_id != current.public_task.task_id
    assert historical.public_task.as_of < current.public_task.as_of
    assert historical.snapshot.created_at < current.snapshot.created_at
    assert sum(order.amount_minor for order in historical.orders) == 19000


def test_public_bundle_is_allowlisted_and_private_events_are_exported_separately(tmp_path):
    fixture = generate_sales_fixture()
    public = tmp_path / "public"
    write_public_bundle(fixture, public)
    assert {
        path.relative_to(public).as_posix() for path in public.rglob("*") if path.is_file()
    } == {
        "task.json",
        "manifest.json",
        "manifest.sha256",
        "tables/customers.csv",
        "tables/orders.csv",
        "tables/order_items.csv",
    }
    for path in public.rglob("*.json"):
        content = path.read_text(encoding="utf-8")
        for forbidden in ("canonical_orders", "expected_answer", "generator_seed", '"variant"'):
            assert forbidden not in content
    private = write_private_fixture(fixture, tmp_path / "private" / "events.json")
    record = PrivateFixtureRecord.model_validate_json(private.read_bytes())
    assert record.canonical_orders == fixture.canonical_orders
    assert record.snapshot_id == fixture.snapshot.snapshot_id
    assert validate_public_bundle(public) == fixture.snapshot
    for destination in (public / "events.json", public / "tables" / "nested" / "events.json"):
        with pytest.raises(ValueError, match="inside a public bundle"):
            write_private_fixture(fixture, destination)
    with pytest.raises(FileExistsError):
        write_public_bundle(fixture, public)
    with pytest.raises(FileExistsError):
        write_private_fixture(fixture, private)


@pytest.mark.parametrize(
    "relative", ["task.json", "tables/orders.csv", "manifest.json", "manifest.sha256"]
)
def test_public_bundle_rejects_changed_bytes(tmp_path, relative):
    public = tmp_path / "public"
    write_public_bundle(generate_sales_fixture(), public)
    path = public / relative
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(BundleValidationError, match="checksum"):
        validate_public_bundle(public)


def test_public_bundle_rejects_additional_private_files_and_missing_tables(tmp_path):
    public = tmp_path / "public"
    write_public_bundle(generate_sales_fixture(), public)
    private = public / "labels.json"
    private.write_text('{"expected_answer":"200.00"}', encoding="utf-8")
    with pytest.raises(BundleValidationError, match="non-allowlisted"):
        validate_public_bundle(public)
    private.unlink()
    (public / "tables" / "orders.csv").unlink()
    with pytest.raises(BundleValidationError, match="missing"):
        validate_public_bundle(public)


def test_public_manifest_rejects_schema_and_relative_path_substitution(tmp_path):
    public = tmp_path / "public"
    write_public_bundle(generate_sales_fixture(), public)
    manifest = json.loads((public / "manifest.json").read_bytes())
    manifest["tables"][0]["path"] = "../private/events.json"
    content = (json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n").encode()
    (public / "manifest.json").write_bytes(content)
    (public / "manifest.sha256").write_text(
        hashlib.sha256(content).hexdigest() + "\n", encoding="ascii", newline="\n"
    )
    with pytest.raises(BundleValidationError):
        validate_public_bundle(public)
    with pytest.raises(ValueError):
        DatasetSnapshot.model_validate(manifest)


def test_rehashed_noncanonical_csv_is_rejected(tmp_path):
    public = tmp_path / "public"
    fixture = generate_sales_fixture()
    write_public_bundle(fixture, public)
    path = public / "tables" / "orders.csv"
    content = path.read_bytes().replace(b"\n", b"\r\n")
    path.write_bytes(content)
    tables = tuple(
        table.model_copy(update={"sha256": hashlib.sha256(content).hexdigest()})
        if table.table_id == "orders"
        else table
        for table in fixture.snapshot.tables
    )
    new_id = snapshot_identity(tables)
    task = TaskSpec.model_validate(
        fixture.public_task.model_dump() | {"permitted_snapshot_ids": (new_id,)}
    )
    task_bytes = canonical_json_bytes(task)
    (public / "task.json").write_bytes(task_bytes)
    snapshot = fixture.snapshot.model_copy(
        update={
            "snapshot_id": new_id,
            "tables": tables,
            "task_sha256": hashlib.sha256(task_bytes).hexdigest(),
        }
    )
    manifest = canonical_json_bytes(snapshot)
    (public / "manifest.json").write_bytes(manifest)
    (public / "manifest.sha256").write_text(
        hashlib.sha256(manifest).hexdigest() + "\n", encoding="ascii", newline="\n"
    )
    with pytest.raises(BundleValidationError, match="CSV serialization is not canonical"):
        validate_public_bundle(public)


@pytest.mark.parametrize("seed", [-1, 1.5, True, "0"])
def test_invalid_seed_types_fail_without_silent_coercion(seed):
    with pytest.raises(ValueError, match="nonnegative integer"):
        generate_sales_fixture(seed=seed)


def test_unimplemented_fixture_variant_is_explicit():
    with pytest.raises(ValueError, match="unsupported"):
        generate_sales_fixture(variant="injected")
