"""Opt-in real Docker checks; enabling them makes build/start failures fatal.

Analyst SQL is sent only to the real container client. The entrypoint overrides
below execute fixed, developer-authored Python diagnostics inside the same
restricted container configuration; they never execute SQL on the host.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest

from assay.contracts import CellLocator, Claim, canonical_json_bytes
from assay.contracts.experiment import ResourceLimits
from assay.datasets import generate_sales_fixture, write_public_bundle
from assay.datasets.sales import FixtureVariant
from assay.evidence.store import EvidenceStore
from assay.execution import docker
from assay.gateway.service import execute_query
from evaluator.oracle import score_claims

pytestmark = pytest.mark.skipif(
    os.environ.get("ASSAY_DOCKER_TESTS") != "1",
    reason="Set ASSAY_DOCKER_TESTS=1 to require the real Linux Docker boundary suite",
)

_SCOPE = (
    "o.status = 'settled' AND o.currency = 'USD' "
    "AND o.occurred_at >= TIMESTAMPTZ '2026-01-01 00:00:00+00' "
    "AND o.occurred_at < TIMESTAMPTZ '2026-04-01 00:00:00+00'"
)
_CORRECT = f"SELECT SUM(o.amount_minor * 0.01) AS revenue_usd FROM orders o WHERE {_SCOPE}"
_BAD_JOIN = (
    "SELECT SUM(o.amount_minor * 0.01) AS revenue_usd FROM orders o "
    f"JOIN order_items i USING (order_id) WHERE {_SCOPE}"
)
_DISTINCT_AMOUNT = (
    "SELECT SUM(DISTINCT o.amount_minor * 0.01) AS revenue_usd FROM orders o "
    f"JOIN order_items i USING (order_id) WHERE {_SCOPE}"
)


@dataclass(frozen=True)
class _Sandbox:
    repository: Path
    state: Path
    image: docker.WorkerImage
    docker_cli: str
    private_sentinel: Path


@pytest.fixture(scope="module")
def sandbox(tmp_path_factory: pytest.TempPathFactory) -> _Sandbox:
    repository = Path(__file__).resolve().parents[1]
    state = tmp_path_factory.mktemp("sandbox-integration-state").resolve()
    assert not state.is_relative_to(repository), "Integration state must be outside the checkout"
    private_sentinel = state / "private" / ("private-sentinel-" + uuid4().hex + ".txt")
    private_sentinel.parent.mkdir()
    private_sentinel.write_text("synthetic private evaluator sentinel\n", encoding="utf-8")
    # No skip or fallback on failure: enabling this module requires a real
    # successful build and a local Linux engine.
    image = docker.build_worker(repository, state=state)
    assert docker.load_worker(state) == image
    return _Sandbox(repository, state, image, docker._docker_path(), private_sentinel)


@pytest.mark.parametrize(
    ("variant", "query", "expected", "expected_correct"),
    [
        ("base", _CORRECT, "200.00", True),
        ("base", _BAD_JOIN, "340.00", False),
        ("equal_amount", _CORRECT, "300.00", True),
        ("equal_amount", _DISTINCT_AMOUNT, "200.00", False),
    ],
)
def test_real_queries_preserve_exact_decimal_and_separate_correctness(
    sandbox: _Sandbox,
    tmp_path: Path,
    variant: FixtureVariant,
    query: str,
    expected: str,
    expected_correct: bool,
) -> None:
    fixture = generate_sales_fixture(variant=variant)
    bundle = tmp_path / "public"
    write_public_bundle(fixture, bundle)
    outcome = execute_query(query, bundle, state=sandbox.state)
    assert outcome.receipt.status == "success", outcome.receipt.error_code
    assert outcome.result is not None
    assert outcome.result.row_count == 1
    cell = outcome.result.rows[0][0]
    assert cell.type == "decimal"
    assert isinstance(cell.value, str)
    assert cell.value == expected
    assert Decimal(cell.value) == Decimal(expected)
    assert outcome.receipt.worker_image_id == sandbox.image.image_id
    assert outcome.receipt.snapshot_id == fixture.snapshot.snapshot_id
    assert (
        outcome.receipt.snapshot_manifest_sha256
        == hashlib.sha256(canonical_json_bytes(fixture.snapshot)).hexdigest()
    )
    store = EvidenceStore(sandbox.state / "evidence")
    assert store.get_execution(outcome.receipt.execution_id) == outcome.receipt
    assert outcome.receipt.result_id is not None
    assert store.get_result(outcome.receipt.result_id) == outcome.result
    claim = Claim(
        slot_id="settled_revenue_usd",
        metric_id=fixture.public_task.metric.metric_id,
        value=Decimal(cell.value),
        unit="USD",
        snapshot_id=fixture.snapshot.snapshot_id,
        time_scope=fixture.public_task.time_scope,
        report_semantics=fixture.public_task.report_semantics,
        result_id=outcome.receipt.result_id,
        cell_locator=CellLocator(row_index=0, column="revenue_usd"),
    )
    score = score_claims(fixture.public_task, fixture.canonical_orders, (claim,))
    # A genuine, captured SQL result can still be incorrect. Execution success
    # and authentic cell bindings are never promoted to a correctness proof.
    assert score.correct is expected_correct
    if not expected_correct:
        assert "wrong_value" in score.slots[0].reasons


def test_real_worker_does_not_return_a_truncated_row_result(
    sandbox: _Sandbox, tmp_path: Path
) -> None:
    fixture = generate_sales_fixture()
    bundle = tmp_path / "public"
    write_public_bundle(fixture, bundle)
    outcome = execute_query(
        "SELECT order_id FROM orders ORDER BY order_id",
        bundle,
        state=sandbox.state,
        limits=ResourceLimits(max_rows=1),
    )
    assert outcome.receipt.status == "error"
    assert outcome.receipt.error_code == "output_limit"
    assert outcome.result is None
    assert outcome.receipt.result_id is None
    assert outcome.receipt.row_count is None
    assert (
        EvidenceStore(sandbox.state / "evidence").get_execution(outcome.receipt.execution_id)
        == outcome.receipt
    )


@pytest.mark.parametrize("variant", ["base", "equal_amount", "insufficient", "historical"])
def test_real_order_preview_fetches_timestamptz_values(
    sandbox: _Sandbox, tmp_path: Path, variant: FixtureVariant
) -> None:
    # COUNT(*) and revenue aggregates do not materialize a timestamp in Python.
    # Exercise the actual preview shape that failed in the development pilot.
    fixture = generate_sales_fixture(variant=variant)
    bundle = tmp_path / "public"
    write_public_bundle(fixture, bundle)
    outcome = execute_query(
        "SELECT * FROM orders ORDER BY order_id LIMIT 20", bundle, state=sandbox.state
    )
    assert outcome.receipt.status == "success", outcome.receipt.error_code
    assert outcome.result is not None
    assert outcome.result.row_count == len(fixture.orders)
    timestamp_column = next(
        index for index, column in enumerate(outcome.result.columns) if column.name == "occurred_at"
    )
    assert outcome.result.columns[timestamp_column].data_type == "TIMESTAMP WITH TIME ZONE"
    expected = sorted(fixture.orders, key=lambda order: order.order_id)
    for row, order in zip(outcome.result.rows, expected, strict=True):
        cell = row[timestamp_column]
        assert cell.type == "timestamp"
        assert cell.value == order.occurred_at.isoformat()
    assert outcome.receipt.worker_image_id == sandbox.image.image_id
    assert outcome.receipt.result_id is not None
    assert (
        EvidenceStore(sandbox.state / "evidence").get_result(outcome.receipt.result_id)
        == outcome.result
    )


@pytest.mark.parametrize(
    "query",
    [
        "SELECT * FROM read_csv('/etc/passwd')",
        "SELECT * FROM read_parquet('https://example.invalid/private.parquet')",
        "SELECT * FROM '/data/tables/orders.csv'",
        "SELECT COALESCE((SELECT content FROM read_text('/private/oracle')), 'x')",
        "SELECT current_setting('home_directory')",
        "SET enable_external_access = true",
        "PRAGMA database_list",
        "INSTALL httpfs",
        "ATTACH '/private/oracle.db' AS oracle",
        "COPY orders TO '/tmp/exfil.csv'",
        "SELECT * FROM orders; SELECT * FROM customers",
        "SELECT * FROM customers",
        "SELECT * FROM private_canonical_events",
    ],
)
def test_worker_revalidates_denied_queries_without_host_admission(
    sandbox: _Sandbox, tmp_path: Path, query: str
) -> None:
    fixture = generate_sales_fixture()
    bundle = tmp_path / "public"
    write_public_bundle(fixture, bundle)
    # Call the worker client directly: the host gateway has not screened this
    # request, and only orders is authorized even though other public CSVs exist.
    outcome = docker.execute_container(sandbox.image, bundle, query, ("orders",), ResourceLimits())
    assert outcome.status == "error"
    assert outcome.error_code == "policy_denied"
    assert outcome.result is None


def test_worker_cannot_load_an_approved_table_absent_from_its_mount(
    sandbox: _Sandbox, tmp_path: Path
) -> None:
    fixture = generate_sales_fixture()
    full = tmp_path / "full-public"
    write_public_bundle(fixture, full)
    partial = tmp_path / "orders-only"
    (partial / "tables").mkdir(parents=True)
    shutil.copyfile(full / "tables" / "orders.csv", partial / "tables" / "orders.csv")
    outcome = docker.execute_container(
        sandbox.image,
        partial,
        "SELECT * FROM customers",
        ("orders", "customers"),
        ResourceLimits(),
    )
    assert outcome.status == "error"
    assert outcome.error_code == "invalid_bundle"
    assert outcome.result is None


_BOUNDARY_DIAGNOSTIC = r"""
import errno
import importlib.util
import json
import os
import socket
import sys
from pathlib import Path

expected = json.loads(sys.argv[1])
assert os.getuid() == 10001 and os.getgid() == 10001
assert os.statvfs('/').f_flag & os.ST_RDONLY
assert os.statvfs('/data').f_flag & os.ST_RDONLY
for name in ('/app/read-only-probe', '/data/read-only-probe'):
    try:
        Path(name).write_text('should be denied', encoding='utf-8')
    except OSError as exc:
        assert exc.errno in (errno.EROFS, errno.EACCES, errno.EPERM)
    else:
        raise AssertionError('read-only filesystem accepted a write')
for name in expected['absent_paths']:
    assert not Path(name).exists(), 'unexpected host/private path'
assert importlib.util.find_spec('evaluator') is None
assert importlib.util.find_spec('assay') is None
assert {p.name for p in Path('/app').iterdir()} == {'worker.py', 'policy.py', 'requirements.txt'}
assert Path('/data/manifest.json').is_file()
for name in expected['proxy_names']:
    assert os.environ.get(name) == '', 'proxy environment was not cleared'
assert {name for _, name in socket.if_nameindex()} == {'lo'}
probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
probe.settimeout(0.3)
try:
    probe.connect(('192.0.2.1', 443))
except OSError as exc:
    assert exc.errno in (errno.ENETUNREACH, errno.EHOSTUNREACH, errno.EADDRNOTAVAIL)
else:
    raise AssertionError('network-none container connected externally')
finally:
    probe.close()
status = dict(line.split(':', 1) for line in Path('/proc/self/status').read_text().splitlines()
              if ':' in line)
assert status['NoNewPrivs'].strip() == '1'
assert int(status['CapEff'].strip(), 16) == 0
assert status['Seccomp'].strip() == '2'
print(json.dumps({'diagnostic_passed': True, 'uid': os.getuid(), 'network_interfaces': ['lo']}),
      flush=True)
# Keep the container inspectable until the host closes stdin. This is a fixed
# diagnostic handshake, unrelated to analyst queries or the worker wire format.
sys.stdin.buffer.read()
"""


def _diagnostic_arguments(arguments: list[str], code: str, *parameters: str) -> list[str]:
    # The sole change to the production arguments is a fixed Python entrypoint.
    return [
        *arguments[:-1],
        "--entrypoint",
        "python",
        arguments[-1],
        "-B",
        "-s",
        "-c",
        code,
        *parameters,
    ]


def _force_remove(docker_cli: str, name: str) -> None:
    subprocess.run(
        [docker_cli, "rm", "--force", name],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )


def _assert_container_absent(docker_cli: str, name: str) -> None:
    observed = subprocess.run(
        [docker_cli, "ps", "--all", "--filter", f"name=^/{name}$", "--format", "{{.Names}}"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert observed.returncode == 0, observed.stderr
    assert name not in observed.stdout.splitlines(), "Worker container was not removed"


def test_real_runtime_has_the_declared_filesystem_identity_and_network_boundary(
    sandbox: _Sandbox, tmp_path: Path
) -> None:
    bundle = tmp_path / "public"
    write_public_bundle(generate_sales_fixture(), bundle)
    name = "assay-" + uuid4().hex
    arguments = docker.container_arguments(
        sandbox.docker_cli, sandbox.image, bundle, name, ResourceLimits()
    )
    parameters = {
        "absent_paths": [
            str(sandbox.repository),
            str(sandbox.repository / "evaluator" / "oracle.py"),
            str(sandbox.private_sentinel),
            "/var/run/docker.sock",
            "/run/docker.sock",
            "/app/evaluator",
            "/app/src",
            "/app/.git",
            "/data/private",
        ],
        "proxy_names": list(docker.PROXY_VARIABLES),
    }
    process: subprocess.Popen[bytes] | None = None
    try:
        process = subprocess.Popen(
            _diagnostic_arguments(arguments, _BOUNDARY_DIAGNOSTIC, json.dumps(parameters)),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        metadata = None
        deadline = time.monotonic() + 15
        inspect_format = (
            '{"running":{{json .State.Running}},"mounts":{{json .Mounts}},'
            '"network":{{json .HostConfig.NetworkMode}},'
            '"read_only":{{json .HostConfig.ReadonlyRootfs}},'
            '"privileged":{{json .HostConfig.Privileged}},"user":{{json .Config.User}}}'
        )
        while time.monotonic() < deadline and process.poll() is None:
            inspected = subprocess.run(
                [sandbox.docker_cli, "inspect", "--format", inspect_format, name],
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
            )
            if inspected.returncode == 0:
                candidate = json.loads(inspected.stdout)
                if candidate["running"]:
                    metadata = candidate
                    break
            time.sleep(0.05)
        assert metadata is not None, "Boundary diagnostic container did not start"
        assert metadata["network"] == "none"
        assert metadata["read_only"] is True
        assert metadata["privileged"] is False
        assert metadata["user"] == "10001:10001"
        mounts = metadata["mounts"]
        bound = [mount for mount in mounts if mount["Type"] == "bind"]
        assert len(bound) == 1
        assert bound[0]["Destination"] == "/data" and bound[0]["RW"] is False
        assert all(
            (mount["Type"], mount["Destination"]) in {("bind", "/data"), ("tmpfs", "/tmp")}
            for mount in mounts
        ), "Unexpected host/project/private mount"
        output, errors = process.communicate(input=b"", timeout=20)
        assert process.returncode == 0, errors.decode("utf-8", errors="replace")
        observed = json.loads(output)
        assert observed["diagnostic_passed"] is True
        assert observed["uid"] == 10001
        _assert_container_absent(sandbox.docker_cli, name)
    finally:
        _force_remove(sandbox.docker_cli, name)
        if process is not None and process.poll() is None:
            process.kill()
            process.communicate(timeout=5)


_SLEEP_DIAGNOSTIC = "import sys,time; sys.stdin.buffer.read(); time.sleep(60)"


@pytest.mark.parametrize("stop", ["timeout", "cancelled"])
def test_real_timeout_and_cancellation_remove_the_running_container(
    sandbox: _Sandbox,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stop: str,
) -> None:
    bundle = tmp_path / "public"
    write_public_bundle(generate_sales_fixture(), bundle)
    actual_arguments = docker.container_arguments
    dispatched = threading.Event()
    names: list[str] = []

    def diagnostic_arguments(
        docker_cli: str,
        image: docker.WorkerImage,
        public_bundle: Path,
        name: str,
        limits: ResourceLimits,
    ) -> list[str]:
        arguments = actual_arguments(docker_cli, image, public_bundle, name, limits)
        names.append(name)
        dispatched.set()
        return _diagnostic_arguments(arguments, _SLEEP_DIAGNOSTIC)

    monkeypatch.setattr(docker, "container_arguments", diagnostic_arguments)
    cancel = threading.Event()
    limits = ResourceLimits(wall_time_seconds=6 if stop == "timeout" else 30)
    with ThreadPoolExecutor(max_workers=1) as executor:
        pending = executor.submit(
            docker.execute_container,
            sandbox.image,
            bundle,
            "SELECT 1",
            ("orders",),
            limits,
            cancel,
        )
        try:
            assert dispatched.wait(timeout=10), "Docker worker was never dispatched"
            name = names[0]
            running = False
            deadline = time.monotonic() + 4
            while time.monotonic() < deadline and not pending.done():
                observed = subprocess.run(
                    [sandbox.docker_cli, "inspect", "--format", "{{.State.Running}}", name],
                    capture_output=True,
                    text=True,
                    timeout=2,
                    check=False,
                )
                if observed.returncode == 0 and observed.stdout.strip() == "true":
                    running = True
                    break
                time.sleep(0.05)
            assert running, "Fixed diagnostic did not reach a running container"
            if stop == "cancelled":
                cancel.set()
            outcome = pending.result(timeout=15)
            assert outcome.status == stop
            assert outcome.result is None
            _assert_container_absent(sandbox.docker_cli, name)
        finally:
            cancel.set()
            for name in names:
                _force_remove(sandbox.docker_cli, name)


_CGROUP_DIAGNOSTIC = r"""
import errno
import json
import os
import signal
import sys
import time
from pathlib import Path

def cgroup_file(modern, *legacy):
    for relative in (modern, *legacy):
        candidate = Path('/sys/fs/cgroup') / relative
        if candidate.is_file():
            return candidate
    raise AssertionError('Required resource controller is unavailable')

sys.stdin.buffer.read()
"""

_CPU_DIAGNOSTIC = (
    _CGROUP_DIAGNOSTIC
    + r"""
modern = Path('/sys/fs/cgroup/cpu.max')
if modern.is_file():
    quota, period = modern.read_text().split()
else:
    quota = cgroup_file('cpu/cpu.cfs_quota_us', 'cpu,cpuacct/cpu.cfs_quota_us').read_text()
    period = cgroup_file('cpu/cpu.cfs_period_us', 'cpu,cpuacct/cpu.cfs_period_us').read_text()
assert int(quota) == int(period), 'Effective CPU quota differs from one CPU'
statistics = cgroup_file('cpu.stat', 'cpu/cpu.stat', 'cpu,cpuacct/cpu.stat')
def throttled_periods():
    return int(dict(line.split() for line in statistics.read_text().splitlines())['nr_throttled'])
before = throttled_periods()
deadline = time.monotonic() + 6
children = []
try:
    # Exactly two children plus the parent request more than one CPU. Every
    # branch has its own deadline; Docker cleanup also kills the whole group.
    for _ in range(2):
        child = os.fork()
        if child == 0:
            while time.monotonic() < deadline:
                pass
            os._exit(0)
        children.append(child)
    while time.monotonic() < deadline:
        pass
finally:
    for child in children:
        try:
            os.kill(child, signal.SIGKILL)
        except ProcessLookupError:
            pass
        os.waitpid(child, 0)
delta = throttled_periods() - before
assert delta > 0, 'CPU saturation was not throttled by the declared quota'
print(json.dumps({'schema_version': '1.0', 'status': 'success',
                  'columns': [{'name': 'cpu_throttled_periods', 'data_type': 'BIGINT'}],
                  'rows': [[{'type': 'integer', 'value': delta}]], 'row_count': 1}), flush=True)
"""
)

_MEMORY_DIAGNOSTIC = (
    _CGROUP_DIAGNOSTIC
    + r"""
limit = int(cgroup_file('memory.max', 'memory/memory.limit_in_bytes').read_text())
assert limit == 256 * 1024 * 1024, 'Effective memory cap differs from the requested limit'
swap = Path('/sys/fs/cgroup/memory.swap.max')
if swap.is_file():
    assert int(swap.read_text()) == 0, 'Swap could bypass the memory ceiling'
print(json.dumps({'memory_limit': limit, 'allocation_ceiling': 384 * 1024 * 1024}), flush=True)
# This is a bounded allocation, not an unbounded stress process. Touch every
# page through bytearray initialization and retain chunks until the cgroup OOM.
chunks = [bytearray(1024 * 1024) for _ in range(384)]
raise AssertionError('Allocation above the declared memory ceiling succeeded')
"""
)

_DISK_DIAGNOSTIC = (
    _CGROUP_DIAGNOSTIC
    + r"""
capacity = os.statvfs('/tmp')
assert capacity.f_blocks * capacity.f_frsize == 64 * 1024 * 1024
path = '/tmp/assay-resource-probe'
descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
written = 0
denied = False
try:
    for _ in range(80):
        try:
            written += os.write(descriptor, b'x' * (1024 * 1024))
        except OSError as exc:
            assert exc.errno == errno.ENOSPC
            denied = True
            break
finally:
    os.close(descriptor)
    os.unlink(path)
assert denied and 63 * 1024 * 1024 <= written <= 64 * 1024 * 1024
print(json.dumps({'disk_limit_denied': True, 'bytes_written': written}), flush=True)
"""
)

_PIDS_DIAGNOSTIC = (
    _CGROUP_DIAGNOSTIC
    + r"""
limit = int(cgroup_file('pids.max', 'pids/pids.max').read_text())
assert limit == 64, 'Effective process cap differs from the declared limit'
children = []
denied = False
try:
    # Only this parent forks, at most 80 times. Children only sleep and exit;
    # the finally block reaps every child even if an assertion fails.
    for _ in range(80):
        try:
            child = os.fork()
        except OSError as exc:
            assert exc.errno == errno.EAGAIN
            denied = True
            break
        if child == 0:
            time.sleep(15)
            os._exit(0)
        children.append(child)
    assert denied and 1 <= len(children) <= 63
    current = int(cgroup_file('pids.current', 'pids/pids.current').read_text())
    assert current <= limit
finally:
    for child in children:
        try:
            os.kill(child, signal.SIGKILL)
        except ProcessLookupError:
            pass
        os.waitpid(child, 0)
print(json.dumps({'process_limit_denied': True, 'children_created': len(children)}), flush=True)
"""
)


def _override_diagnostic_for_bundle(
    monkeypatch: pytest.MonkeyPatch, bundle: Path, code: str
) -> list[str]:
    actual_arguments = docker.container_arguments
    names: list[str] = []

    def diagnostic_arguments(
        docker_cli: str,
        image: docker.WorkerImage,
        public_bundle: Path,
        name: str,
        limits: ResourceLimits,
    ) -> list[str]:
        arguments = actual_arguments(docker_cli, image, public_bundle, name, limits)
        if public_bundle.resolve() != bundle.resolve():
            return arguments
        names.append(name)
        return _diagnostic_arguments(arguments, code)

    monkeypatch.setattr(docker, "container_arguments", diagnostic_arguments)
    return names


def _assert_useful_worker_after_stress(sandbox: _Sandbox, bundle: Path) -> None:
    outcome = execute_query(_CORRECT, bundle, state=sandbox.state)
    assert outcome.receipt.status == "success", outcome.receipt.error_code
    assert outcome.result is not None
    assert outcome.result.rows[0][0].value == "200.00"


def test_real_cpu_saturation_is_throttled_without_blocking_another_worker(
    sandbox: _Sandbox, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stress = tmp_path / "cpu-public"
    useful = tmp_path / "useful-public"
    for bundle in (stress, useful):
        write_public_bundle(generate_sales_fixture(), bundle)
    names = _override_diagnostic_for_bundle(monkeypatch, stress, _CPU_DIAGNOSTIC)
    cancel = threading.Event()
    with ThreadPoolExecutor(max_workers=1) as executor:
        pending = executor.submit(
            docker.execute_container,
            sandbox.image,
            stress,
            "SELECT 1",
            ("orders",),
            ResourceLimits(wall_time_seconds=20),
            cancel,
        )
        try:
            deadline = time.monotonic() + 10
            running = False
            while time.monotonic() < deadline and not pending.done():
                if names:
                    observed = subprocess.run(
                        [sandbox.docker_cli, "inspect", "--format", "{{.State.Running}}", names[0]],
                        capture_output=True,
                        text=True,
                        timeout=2,
                        check=False,
                    )
                    if observed.returncode == 0 and observed.stdout.strip() == "true":
                        running = True
                        break
                time.sleep(0.05)
            assert running and not pending.done(), (
                "CPU diagnostic did not reach a running container"
            )
            # Start genuine analyst SQL while the separate container saturates
            # its CPU quota; the stress entrypoint never affects this bundle.
            _assert_useful_worker_after_stress(sandbox, useful)
            outcome = pending.result(timeout=20)
            assert outcome.status == "success", outcome.error_code
            assert outcome.result is not None
            assert outcome.result.rows[0][0].value > 0
            _assert_container_absent(sandbox.docker_cli, names[0])
        finally:
            cancel.set()
            for name in names:
                _force_remove(sandbox.docker_cli, name)


@pytest.mark.parametrize("resource", ["memory", "disk", "processes"])
def test_real_resource_exhaustion_stays_inside_its_container(
    sandbox: _Sandbox, tmp_path: Path, resource: str
) -> None:
    bundle = tmp_path / "public"
    write_public_bundle(generate_sales_fixture(), bundle)
    name = "assay-" + uuid4().hex
    code = {"memory": _MEMORY_DIAGNOSTIC, "disk": _DISK_DIAGNOSTIC, "processes": _PIDS_DIAGNOSTIC}[
        resource
    ]
    arguments = docker.container_arguments(
        sandbox.docker_cli, sandbox.image, bundle, name, ResourceLimits()
    )
    if resource == "memory":
        # Retain only this owned diagnostic long enough to distinguish a real
        # cgroup OOM kill from a Python exception or startup failure.
        arguments.remove("--rm")
    try:
        completed = subprocess.run(
            _diagnostic_arguments(arguments, code),
            input=b"",
            capture_output=True,
            timeout=25,
            check=False,
        )
        observed = json.loads(completed.stdout)
        if resource == "memory":
            assert observed["memory_limit"] == 256 * 1024 * 1024
            inspected = subprocess.run(
                [sandbox.docker_cli, "inspect", "--format", "{{json .State}}", name],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            assert inspected.returncode == 0, inspected.stderr
            state = json.loads(inspected.stdout)
            assert state["OOMKilled"] is True and state["Running"] is False
            assert state["ExitCode"] == completed.returncode == 137
        else:
            assert completed.returncode == 0, completed.stderr.decode("utf-8", errors="replace")
            assert (
                observed["disk_limit_denied" if resource == "disk" else "process_limit_denied"]
                is True
            )
    finally:
        _force_remove(sandbox.docker_cli, name)
        _assert_container_absent(sandbox.docker_cli, name)
    _assert_useful_worker_after_stress(sandbox, bundle)


@pytest.mark.parametrize("stream", ["stdout", "stderr"])
def test_real_output_byte_overflow_removes_container_without_a_truncated_result(
    sandbox: _Sandbox, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stream: str
) -> None:
    bundle = tmp_path / "public"
    write_public_bundle(generate_sales_fixture(), bundle)
    code = (
        "import sys,time; sys.stdin.buffer.read(); "
        f"target=sys.{stream}.buffer; "
        "[target.write(b'x' * 4096) for _ in range(64)]; target.flush(); time.sleep(15)"
    )
    names = _override_diagnostic_for_bundle(monkeypatch, bundle, code)
    try:
        outcome = docker.execute_container(
            sandbox.image,
            bundle,
            "SELECT 1",
            ("orders",),
            ResourceLimits(max_output_bytes=1024, wall_time_seconds=10),
        )
        assert outcome.status == "output_limit", outcome.error_code
        assert outcome.result is None
        assert len(names) == 1
        _assert_container_absent(sandbox.docker_cli, names[0])
    finally:
        for name in names:
            _force_remove(sandbox.docker_cli, name)
    _assert_useful_worker_after_stress(sandbox, bundle)
