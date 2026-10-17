from types import SimpleNamespace

from assay import diagnostics
from assay.execution.docker import WorkerUnavailableError


def test_doctor_distinguishes_unavailable_engine_without_starting_work(monkeypatch, tmp_path):
    state = tmp_path / "state"
    monkeypatch.setattr(diagnostics, "state_directory", lambda **kwargs: state)

    def unavailable():
        raise WorkerUnavailableError("test engine unavailable")

    monkeypatch.setattr(diagnostics, "_docker_path", unavailable)
    result = diagnostics.doctor()
    assert result["offline_ready"]
    assert not result["docker_ready"] and not result["sql_worker_ready"]
    assert not state.exists()


def test_doctor_requires_the_pinned_image_to_exist(monkeypatch, tmp_path):
    state = tmp_path / "state"
    image_id = "sha256:" + "a" * 64
    monkeypatch.setattr(diagnostics, "state_directory", lambda **kwargs: state)
    monkeypatch.setattr(diagnostics, "_docker_path", lambda: "docker")
    monkeypatch.setattr(diagnostics, "load_worker", lambda root: SimpleNamespace(image_id=image_id))
    monkeypatch.setattr(
        diagnostics.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout=image_id + "\n"),
    )
    result = diagnostics.doctor()
    assert result["docker_ready"] and result["sql_worker_ready"]
    assert result["isolation_validation"] == "not_assessed_by_doctor"
    assert not state.exists()
    monkeypatch.setattr(
        diagnostics.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1, stdout=""),
    )
    assert not diagnostics.doctor()["sql_worker_ready"]
