import hashlib
import os
import stat

import pytest

from assay.contracts import canonical_json_bytes
from assay.contracts.execution import WorkerSuccess
from assay.datasets import generate_sales_fixture, validate_public_bundle, write_public_bundle
from assay.evidence.store import EvidenceStore
from assay.execution.docker import ContainerOutcome, WorkerImage, WorkerUnavailableError
from assay.gateway import service
from assay.gateway.policy import SQLPolicyError


def setup_gateway(tmp_path, monkeypatch, result=None, outcome=None):
    source = tmp_path / "source"
    fixture = generate_sales_fixture()
    write_public_bundle(fixture, source)
    image = WorkerImage(
        image_id="sha256:" + "a" * 64,
        base_image="test-only",
        policy_sha256="b" * 64,
        worker_sha256="c" * 64,
        requirements_sha256="d" * 64,
    )
    if result is None and outcome is None:
        result = WorkerSuccess.model_validate(
            {
                "status": "success",
                "columns": [{"name": "revenue_usd", "data_type": "DECIMAL(38,2)"}],
                "rows": [[{"type": "decimal", "value": "200.00"}]],
                "row_count": 1,
            }
        )
    monkeypatch.setattr(service, "load_worker", lambda *args: image)
    monkeypatch.setattr(
        service, "execute_container", lambda *args: outcome or ContainerOutcome("success", result)
    )
    return source, fixture, result


def test_gateway_captures_host_receipt_and_full_durable_evidence(tmp_path, monkeypatch):
    source, fixture, result = setup_gateway(tmp_path, monkeypatch)
    query = "SELECT SUM(amount_minor * 0.01) AS revenue_usd FROM orders"
    state = tmp_path / "state"
    outcome = service.execute_query(query, source, state=state)
    receipt = outcome.receipt
    assert receipt.exact_query == query
    assert receipt.query_sha256 == hashlib.sha256(query.encode()).hexdigest()
    assert receipt.execution_id.startswith("execution-")
    store = EvidenceStore(state / "evidence")
    assert store.get_execution(receipt.execution_id) == receipt
    assert store.get_result(receipt.result_id) == result
    frozen = state / "evidence" / "inputs" / receipt.snapshot_manifest_sha256
    (source / "tables" / "orders.csv").write_text("changed original input", encoding="utf-8")
    assert validate_public_bundle(frozen) == fixture.snapshot
    assert hashlib.sha256(canonical_json_bytes(result)).hexdigest() == receipt.output_sha256
    repeated = service.execute_query(query, frozen, state=state)
    assert repeated.receipt.execution_id != receipt.execution_id
    assert repeated.receipt.run_id != receipt.run_id


@pytest.mark.skipif(os.name != "posix", reason="POSIX modes reach the worker via its bind mount")
def test_frozen_snapshot_is_readable_by_the_worker_uid_under_a_private_umask(tmp_path):
    source = tmp_path / "source"
    write_public_bundle(generate_sales_fixture(), source)
    previous = os.umask(0o077)
    try:
        frozen, _, _ = service.freeze_input_bundle(source, tmp_path / "evidence")
    finally:
        os.umask(previous)
    for path in (frozen, *frozen.rglob("*")):
        assert stat.S_IMODE(path.stat().st_mode) == (0o755 if path.is_dir() else 0o644), path


def test_runner_supplied_run_id_groups_queries_and_is_validated_before_dispatch(
    tmp_path, monkeypatch
):
    source, _, _ = setup_gateway(tmp_path, monkeypatch)
    state = tmp_path / "state"
    first = service.execute_query("SELECT * FROM orders", source, state=state, run_id="run-a")
    second = service.execute_query("SELECT * FROM orders", source, state=state, run_id="run-a")
    assert first.receipt.run_id == second.receipt.run_id == "run-a"
    assert first.receipt.execution_id != second.receipt.execution_id

    def unexpected_dispatch(*args):
        raise AssertionError("Invalid run identity reached worker dispatch")

    monkeypatch.setattr(service, "execute_container", unexpected_dispatch)
    for run_id in ("../run", "", "run id", "r" * 161):
        with pytest.raises(ValueError, match="run_id"):
            service.execute_query("SELECT * FROM orders", source, state=state, run_id=run_id)


def test_unsafe_sql_never_reaches_dispatch(tmp_path, monkeypatch):
    source, _, _ = setup_gateway(tmp_path, monkeypatch)

    def unexpected_dispatch(*args):
        raise AssertionError("Unsafe query reached worker dispatch")

    monkeypatch.setattr(service, "execute_container", unexpected_dispatch)
    with pytest.raises(SQLPolicyError):
        service.execute_query(
            "SELECT * FROM read_csv('/private/oracle.csv')", source, state=tmp_path / "state"
        )


def test_unavailable_worker_has_no_execution_fallback(tmp_path, monkeypatch):
    source, _, _ = setup_gateway(tmp_path, monkeypatch)

    def unavailable(*args):
        raise WorkerUnavailableError("test engine absent")

    monkeypatch.setattr(service, "load_worker", unavailable)
    with pytest.raises(WorkerUnavailableError):
        service.execute_query("SELECT * FROM orders", source, state=tmp_path / "state")
    assert not (tmp_path / "state" / "evidence" / "evidence.sqlite3").exists()


@pytest.mark.parametrize("status", ["timeout", "cancelled", "error", "output_limit"])
def test_failed_execution_retains_no_success_result(tmp_path, monkeypatch, status):
    source, _, _ = setup_gateway(
        tmp_path, monkeypatch, outcome=ContainerOutcome(status, error_code=status)
    )
    outcome = service.execute_query("SELECT * FROM orders", source, state=tmp_path / "state")
    assert outcome.receipt.status == status
    assert outcome.receipt.result_id is None
    assert outcome.result is None
    assert (
        EvidenceStore(tmp_path / "state" / "evidence").get_execution(outcome.receipt.execution_id)
        == outcome.receipt
    )


def test_capped_preview_preserves_full_result(tmp_path, monkeypatch):
    result = WorkerSuccess.model_validate(
        {
            "status": "success",
            "columns": [{"name": "order_id", "data_type": "VARCHAR"}],
            "rows": [[{"type": "string", "value": f"O{index}"}] for index in range(30)],
            "row_count": 30,
        }
    )
    source, _, _ = setup_gateway(tmp_path, monkeypatch, result=result)
    outcome = service.execute_query("SELECT order_id FROM orders", source, state=tmp_path / "state")
    assert outcome.receipt.preview_row_count == 20
    assert outcome.receipt.preview_truncated
    stored = EvidenceStore(tmp_path / "state" / "evidence").get_result(outcome.receipt.result_id)
    assert len(stored.rows) == 30
