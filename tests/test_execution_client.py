import json
import sys
import threading
import time

import pytest
from pydantic import ValidationError

from assay.contracts.execution import ResultCell, WorkerSuccess
from assay.contracts.experiment import ResourceLimits
from assay.execution import docker


def image():
    return docker.WorkerImage(
        image_id="sha256:" + "a" * 64,
        base_image=docker.BASE_IMAGE,
        policy_sha256="b" * 64,
        worker_sha256="c" * 64,
        requirements_sha256="d" * 64,
    )


def result_dict():
    return {
        "status": "success",
        "columns": [{"name": "revenue_usd", "data_type": "DECIMAL(38,2)"}],
        "rows": [[{"type": "decimal", "value": "200.00"}]],
        "row_count": 1,
    }


def fake_docker(monkeypatch, script):
    monkeypatch.setattr(docker, "_docker_path", lambda: sys.executable)
    monkeypatch.setattr(docker, "container_arguments", lambda *args: [sys.executable, "-c", script])
    monkeypatch.setattr(docker, "_remove_container", lambda *args: None)


def test_no_docker_fails_closed(monkeypatch):
    monkeypatch.setattr(docker.shutil, "which", lambda _: None)
    with pytest.raises(docker.WorkerUnavailableError, match="isolated execution"):
        docker._docker_path()


def test_remote_docker_endpoint_is_rejected_before_contact(monkeypatch):
    monkeypatch.setattr(docker.shutil, "which", lambda _: "docker")
    monkeypatch.setenv("DOCKER_HOST", "tcp://remote.example.invalid:2375")

    def unexpected_contact(*args, **kwargs):
        raise AssertionError("Contacted a remote engine")

    monkeypatch.setattr(docker.subprocess, "run", unexpected_contact)
    with pytest.raises(docker.WorkerUnavailableError, match="local Docker"):
        docker._docker_path()


def test_build_records_copied_policy_and_clears_proxy_args(tmp_path, monkeypatch):
    sandbox = tmp_path / "source" / "sandbox"
    sandbox.mkdir(parents=True)
    (sandbox / "Dockerfile").write_text("FROM " + docker.BASE_IMAGE, encoding="utf-8")
    (sandbox / "worker.py").write_text("# worker", encoding="utf-8")
    (sandbox / "requirements.txt").write_text("# dependencies", encoding="utf-8")
    policy = tmp_path / "policy.py"
    original = b"# policy A\n"
    policy.write_bytes(original)
    monkeypatch.setattr(docker, "_docker_path", lambda: "docker")
    monkeypatch.setattr(docker, "_policy_source", lambda: policy)

    def build(args, **kwargs):
        for name in docker.PROXY_VARIABLES:
            assert name + "=" in args
        image_file = args[args.index("--iidfile") + 1]
        from pathlib import Path

        Path(image_file).write_text("sha256:" + "a" * 64, encoding="ascii")
        policy.write_bytes(b"# policy B changed during build\n")

    monkeypatch.setattr(docker.subprocess, "run", build)
    built = docker.build_worker(tmp_path / "source", tmp_path / "state")
    import hashlib

    assert built.policy_sha256 == hashlib.sha256(original).hexdigest()
    with pytest.raises(docker.WorkerUnavailableError, match="policy differs"):
        docker.load_worker(tmp_path / "state")


def test_container_has_only_readonly_public_mount(tmp_path):
    args = docker.container_arguments(
        "docker", image(), tmp_path, "assay-" + "1" * 32, ResourceLimits()
    )
    for flag in (
        "--network=none",
        "--read-only",
        "--user=10001:10001",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--pids-limit=64",
        "--cpus=1",
        "--pull=never",
    ):
        assert flag in args
    assert args.count("--mount") == 1
    mount = args[args.index("--mount") + 1]
    assert mount == f"type=bind,source={tmp_path.resolve()},target=/data,readonly"
    assert args[-1] == image().image_id
    for name in docker.PROXY_VARIABLES:
        assert name + "=" in args


def test_successful_complete_capture(monkeypatch, tmp_path):
    script = f"import sys; sys.stdin.read(); print({json.dumps(result_dict())!r})"
    fake_docker(monkeypatch, script)
    outcome = docker.execute_container(image(), tmp_path, "SELECT 1", ("orders",), ResourceLimits())
    assert outcome.status == "success"
    assert outcome.result.rows[0][0].value == "200.00"


def test_malformed_worker_response_is_not_success(monkeypatch, tmp_path):
    fake_docker(monkeypatch, "import sys; sys.stdin.read(); print('not json')")
    outcome = docker.execute_container(image(), tmp_path, "SELECT 1", ("orders",), ResourceLimits())
    assert outcome.status == "protocol_error"
    assert outcome.result is None


def test_worker_timeout_terminates_capture(monkeypatch, tmp_path):
    fake_docker(monkeypatch, "import sys,time; sys.stdin.read(); time.sleep(20)")
    outcome = docker.execute_container(
        image(), tmp_path, "SELECT 1", ("orders",), ResourceLimits(wall_time_seconds=1)
    )
    assert outcome.status == "timeout"


def test_timeout_covers_a_worker_that_never_reads_stdin(monkeypatch, tmp_path):
    fake_docker(monkeypatch, "import time; time.sleep(20)")
    start = time.monotonic()
    outcome = docker.execute_container(
        image(), tmp_path, "x" * 20_000, ("orders",), ResourceLimits(wall_time_seconds=1)
    )
    assert outcome.status == "timeout"
    assert time.monotonic() - start < 5


def test_output_limit_cannot_become_truncated_success(monkeypatch, tmp_path):
    fake_docker(monkeypatch, "import sys; sys.stdin.read(); print('x' * 100000)")
    outcome = docker.execute_container(
        image(), tmp_path, "SELECT 1", ("orders",), ResourceLimits(max_output_bytes=1024)
    )
    assert outcome.status == "output_limit"
    assert outcome.result is None


def test_cancel_before_dispatch(monkeypatch, tmp_path):
    monkeypatch.setattr(docker, "_docker_path", lambda: "docker")
    cancelled = threading.Event()
    cancelled.set()
    outcome = docker.execute_container(
        image(), tmp_path, "SELECT 1", ("orders",), ResourceLimits(), cancelled
    )
    assert outcome.status == "cancelled"


@pytest.mark.parametrize(
    "cell",
    [
        {"type": "integer", "value": True},
        {"type": "decimal", "value": "NaN"},
        {"type": "float", "value": "Infinity"},
        {"type": "null", "value": "null"},
    ],
)
def test_wrongly_typed_or_nonfinite_result_is_rejected(cell):
    with pytest.raises(ValidationError):
        ResultCell.model_validate(cell)


def test_duplicate_columns_and_mismatched_counts_fail():
    response = result_dict()
    with pytest.raises(ValidationError):
        WorkerSuccess.model_validate(response | {"row_count": 2})
    with pytest.raises(ValidationError):
        WorkerSuccess.model_validate(response | {"columns": response["columns"] * 2})
