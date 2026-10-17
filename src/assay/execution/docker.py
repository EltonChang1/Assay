"""A minimal Docker process boundary with bounded capture and explicit cleanup."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Literal
from uuid import uuid4

from pydantic import Field

from safety_lab.config import state_directory
from safety_lab.contracts.base import VersionedModel, canonical_json_bytes
from safety_lab.contracts.execution import WorkerFailure, WorkerSuccess
from safety_lab.contracts.experiment import ResourceLimits
from safety_lab.contracts.snapshot import Sha256

BASE_IMAGE = (
    "python:3.12-slim@sha256:2b4f19dae3a777dfc3b76730bda1e82e1f66ab2a2686fa93ca78edbfb4f04ffe"
)
CLIENT_VERSION: Literal["docker-process-1.0"] = "docker-process-1.0"
PROXY_VARIABLES = tuple(
    variant
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "FTP_PROXY", "NO_PROXY", "ALL_PROXY")
    for variant in (name, name.lower())
)


class WorkerUnavailableError(RuntimeError):
    """No usable pinned container; no host fallback is permitted."""


class WorkerImage(VersionedModel):
    image_id: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    base_image: str
    platform: Literal["linux/amd64"] = "linux/amd64"
    policy_sha256: Sha256
    worker_sha256: Sha256
    requirements_sha256: Sha256
    client_version: Literal["docker-process-1.0"] = CLIENT_VERSION


@dataclass(frozen=True)
class ContainerOutcome:
    status: Literal["success", "error", "timeout", "cancelled", "output_limit", "protocol_error"]
    result: WorkerSuccess | None = None
    error_code: str | None = None


def _docker_path() -> str:
    docker = shutil.which("docker")
    if docker is None:
        raise WorkerUnavailableError("Docker is unavailable; isolated execution is required")
    endpoint_override = os.environ.get("DOCKER_HOST", "")
    if endpoint_override and not endpoint_override.startswith(("unix://", "npipe://")):
        raise WorkerUnavailableError("Only a local Docker engine is supported")
    try:
        context = subprocess.run(
            [docker, "context", "inspect", "--format", "{{.Endpoints.docker.Host}}"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if context.returncode != 0 or not context.stdout.strip().startswith(
            ("unix://", "npipe://")
        ):
            raise WorkerUnavailableError("Only a local Docker engine is supported")
        check = subprocess.run(
            [docker, "info", "--format", "{{.OSType}}"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise WorkerUnavailableError("Docker readiness check failed") from exc
    if check.returncode != 0 or check.stdout.strip() != "linux":
        raise WorkerUnavailableError("A running Linux Docker engine is required; no host fallback")
    return docker


def _policy_source() -> Path:
    from safety_lab.gateway import policy

    assert policy.__file__ is not None
    return Path(policy.__file__)


def build_worker(source_root: Path, state: Path | None = None) -> WorkerImage:
    """Build an allowlisted context; save an immutable local image ID, never a tag."""
    docker = _docker_path()
    root = state or state_directory()
    root.mkdir(parents=True, exist_ok=True)
    policy_path = _policy_source()
    with tempfile.TemporaryDirectory(prefix="worker-build-", dir=root) as temporary:
        context = Path(temporary).resolve()
        if not context.is_relative_to(root.resolve()):
            raise ValueError("Build scratch path escaped configured state directory")
        for name in ("Dockerfile", "worker.py", "requirements.txt"):
            shutil.copyfile(source_root / "sandbox" / name, context / name)
        shutil.copyfile(policy_path, context / "policy.py")
        if BASE_IMAGE not in (context / "Dockerfile").read_text(encoding="utf-8"):
            raise ValueError("Worker base image does not match the pinned platform digest")
        image_file = root / f"image-{uuid4().hex}.txt"
        try:
            subprocess.run(
                [
                    docker,
                    "build",
                    "--platform",
                    "linux/amd64",
                    "--iidfile",
                    str(image_file),
                    *[
                        argument
                        for name in PROXY_VARIABLES
                        for argument in ("--build-arg", name + "=")
                    ],
                    str(context),
                ],
                check=True,
                timeout=600,
            )
            image = WorkerImage(
                image_id=image_file.read_text(encoding="ascii").strip(),
                base_image=BASE_IMAGE,
                policy_sha256=hashlib.sha256((context / "policy.py").read_bytes()).hexdigest(),
                worker_sha256=hashlib.sha256((context / "worker.py").read_bytes()).hexdigest(),
                requirements_sha256=hashlib.sha256(
                    (context / "requirements.txt").read_bytes()
                ).hexdigest(),
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise WorkerUnavailableError(
                "Pinned worker build failed; no execution enabled"
            ) from exc
        finally:
            image_file.unlink(missing_ok=True)
    temporary_manifest = root / f"worker-{uuid4().hex}.json"
    temporary_manifest.write_bytes(canonical_json_bytes(image))
    temporary_manifest.replace(root / "worker.json")
    return image


def load_worker(state: Path | None = None) -> WorkerImage:
    root = state or state_directory()
    try:
        image = WorkerImage.model_validate_json((root / "worker.json").read_bytes())
    except (ValueError, OSError) as exc:
        raise WorkerUnavailableError(
            "Build the pinned worker with safety-lab worker build first"
        ) from exc
    if image.base_image != BASE_IMAGE:
        raise WorkerUnavailableError("Worker base image differs from current pin; rebuild required")
    if image.policy_sha256 != hashlib.sha256(_policy_source().read_bytes()).hexdigest():
        raise WorkerUnavailableError(
            "Worker policy differs from installed policy; rebuild required"
        )
    checkout_sandbox = Path(__file__).resolve().parents[3] / "sandbox"
    for filename, expected in (
        ("worker.py", image.worker_sha256),
        ("requirements.txt", image.requirements_sha256),
    ):
        source = checkout_sandbox / filename
        if source.exists() and hashlib.sha256(source.read_bytes()).hexdigest() != expected:
            raise WorkerUnavailableError("Worker sources changed; rebuild required")
    return image


def container_arguments(
    docker: str, image: WorkerImage, bundle: Path, name: str, limits: ResourceLimits
) -> list[str]:
    """No shell, host credentials, writable host mount, Docker socket, or host network."""
    if not re.fullmatch(r"safety-lab-[0-9a-f]{32}", name):
        raise ValueError("Container name must be host-generated")
    source = str(bundle.resolve())
    if "," in source:
        raise ValueError("Docker bind source paths containing commas are unsupported")
    return [
        docker,
        "run",
        "--name",
        name,
        "--rm",
        "--pull=never",
        "--platform=linux/amd64",
        "--network=none",
        "--read-only",
        "--user=10001:10001",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--pids-limit=64",
        "--cpus=1",
        f"--memory={limits.memory_mb}m",
        f"--memory-swap={limits.memory_mb}m",
        "--ulimit=nofile=64:64",
        "--log-driver=none",
        "--tmpfs=/tmp:rw,noexec,nosuid,size=64m,mode=1777",
        "--mount",
        f"type=bind,source={source},target=/data,readonly",
        *[argument for name in PROXY_VARIABLES for argument in ("--env", name + "=")],
        "--interactive",
        image.image_id,
    ]


def execute_container(
    image: WorkerImage,
    bundle: Path,
    query: str,
    allowed_tables: tuple[str, ...],
    limits: ResourceLimits,
    cancel: threading.Event | None = None,
) -> ContainerOutcome:
    docker = _docker_path()
    if cancel is not None and cancel.is_set():
        return ContainerOutcome("cancelled", error_code="cancelled_before_dispatch")
    name = "safety-lab-" + uuid4().hex
    request = json.dumps(
        {
            "schema_version": "1.0",
            "query": query,
            "allowed_tables": list(allowed_tables),
            "max_rows": min(limits.max_rows, 1000),
            "max_output_bytes": min(limits.max_output_bytes, 1_048_576),
        }
    ).encode("utf-8")
    if len(request) > 32_768:
        return ContainerOutcome("error", error_code="request_limit")
    try:
        process = subprocess.Popen(
            container_arguments(docker, image, bundle, name, limits),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError as exc:
        raise WorkerUnavailableError("Could not launch isolated worker") from exc
    output = bytearray()
    overflow = threading.Event()
    budget_lock = threading.Lock()
    captured_bytes = 0

    def capture(stream: BinaryIO, keep: bool) -> None:
        nonlocal captured_bytes
        try:
            while chunk := stream.read(4096):
                with budget_lock:
                    captured_bytes += len(chunk)
                    if captured_bytes > limits.max_output_bytes + 16_384:
                        overflow.set()
                        break
                    if keep:
                        output.extend(chunk)
        finally:
            stream.close()

    assert process.stdin is not None and process.stdout is not None and process.stderr is not None

    def send_packet() -> None:
        assert process.stdin is not None
        try:
            with suppress(BrokenPipeError, OSError):
                process.stdin.write(request)
        finally:
            with suppress(BrokenPipeError, OSError):
                process.stdin.close()

    deadline = time.monotonic() + limits.wall_time_seconds
    writer = threading.Thread(target=send_packet, daemon=True)
    readers = [
        threading.Thread(target=capture, args=(process.stdout, True), daemon=True),
        threading.Thread(target=capture, args=(process.stderr, False), daemon=True),
    ]
    for reader in readers:
        reader.start()
    writer.start()
    stopped: Literal["timeout", "cancelled", "output_limit"] | None = None
    try:
        while process.poll() is None:
            if overflow.is_set():
                stopped = "output_limit"
                break
            if cancel is not None and cancel.is_set():
                stopped = "cancelled"
                break
            if time.monotonic() >= deadline:
                stopped = "timeout"
                break
            time.sleep(0.02)
    finally:
        if stopped is not None:
            # Killing the CLI alone does not reliably kill the container.
            _remove_container(docker, name)
            process.kill()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        for reader in readers:
            reader.join(timeout=5)
        writer.join(timeout=5)
        cleanup_confirmed = _remove_container(docker, name)
    if cleanup_confirmed is False:
        return ContainerOutcome(
            stopped or "protocol_error", error_code="container_cleanup_unconfirmed"
        )
    if stopped is not None:
        return ContainerOutcome(stopped, error_code=stopped)
    if overflow.is_set() or len(output) > limits.max_output_bytes:
        return ContainerOutcome("output_limit", error_code="captured_output_limit")
    if writer.is_alive() or any(reader.is_alive() for reader in readers):
        return ContainerOutcome("protocol_error", error_code="capture_incomplete")
    try:
        payload = json.loads(bytes(output))
        if not isinstance(payload, dict):
            raise ValueError("Worker output must be an object")
        parsed: WorkerSuccess | WorkerFailure
        if payload.get("status") == "success":
            parsed = WorkerSuccess.model_validate(payload)
        else:
            parsed = WorkerFailure.model_validate(payload)
    except (ValueError, UnicodeError):
        return ContainerOutcome("protocol_error", error_code="invalid_worker_output")
    if isinstance(parsed, WorkerFailure):
        return ContainerOutcome("error", error_code=parsed.error_code)
    if process.returncode != 0 or parsed.row_count > limits.max_rows:
        return ContainerOutcome("protocol_error", error_code="invalid_worker_completion")
    return ContainerOutcome("success", result=parsed)


def _remove_container(docker: str, name: str) -> bool:
    try:
        removed = subprocess.run(
            [docker, "rm", "--force", name],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        return removed.returncode == 0 or "no such container" in removed.stderr.casefold()
    except (OSError, subprocess.TimeoutExpired):
        return False
