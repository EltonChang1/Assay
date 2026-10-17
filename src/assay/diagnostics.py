"""Charge-free setup checks. Docker availability is not worker isolation proof."""

from __future__ import annotations

import platform
import subprocess
from importlib.metadata import version
from pathlib import Path
from typing import Any

from safety_lab.config import state_directory
from safety_lab.execution.docker import WorkerUnavailableError, _docker_path, load_worker


def doctor(*, workspace: Path | None = None) -> dict[str, Any]:
    checks: list[dict[str, str]] = []
    python_ok = platform.python_version_tuple()[:2] == ("3", "12")
    checks.append(
        {
            "name": "python",
            "status": "ok" if python_ok else "error",
            "detail": platform.python_version(),
        }
    )
    checks.append({"name": "pydantic", "status": "ok", "detail": version("pydantic")})
    state: Path | None = None
    try:
        state = state_directory(workspace=workspace)
        checks.append({"name": "state_directory", "status": "ok", "detail": str(state)})
    except ValueError as exc:
        checks.append({"name": "state_directory", "status": "error", "detail": str(exc)})

    docker_path: str | None = None
    try:
        docker_path = _docker_path()
        docker_ready = True
        detail = "Local Linux engine available"
    except WorkerUnavailableError as exc:
        docker_ready = False
        detail = str(exc)
    checks.append(
        {"name": "docker", "status": "ok" if docker_ready else "pending", "detail": detail}
    )
    worker_ready = False
    worker_detail = "Worker availability requires valid local state and Docker"
    if state is not None and docker_path is not None:
        try:
            image = load_worker(state)
            process = subprocess.run(
                [docker_path, "image", "inspect", "--format", "{{.Id}}", image.image_id],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            worker_ready = process.returncode == 0 and process.stdout.strip() == image.image_id
            worker_detail = (
                "Pinned worker image available" if worker_ready else "Worker image unavailable"
            )
        except WorkerUnavailableError as exc:
            worker_detail = str(exc)
        except (subprocess.TimeoutExpired, OSError):
            worker_detail = "Worker image inspection failed or timed out"
    checks.append(
        {
            "name": "worker_image",
            "status": "ok" if worker_ready else "pending",
            "detail": worker_detail,
        }
    )
    return {
        "schema_version": "1.0",
        "offline_ready": all(check["status"] != "error" for check in checks),
        "docker_ready": docker_ready,
        "sql_worker_ready": worker_ready,
        "isolation_validation": "not_assessed_by_doctor",
        "model_calls_enabled": False,
        "checks": checks,
        "next_gate": "See implementation status for phase gates; doctor checks availability only",
    }
