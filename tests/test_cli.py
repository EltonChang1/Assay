import json
from pathlib import Path

from assay.cli import main


def test_doctor_is_charge_free() -> None:
    # No credentials or provider SDK is needed for the implemented diagnostic path.
    import subprocess

    completed = subprocess.run(["assay", "doctor"], check=False, capture_output=True, text=True)
    assert completed.returncode == 0
    value = json.loads(completed.stdout)
    assert value["offline_ready"]
    assert value["model_calls_enabled"] is False
    assert isinstance(value["sql_worker_ready"], bool)
    assert value["isolation_validation"] == "not_assessed_by_doctor"


def test_cli_spec_validation() -> None:
    assert main(["spec", "validate", "--manifest", "experiment_specs/development.json"]) == 0


def test_invalid_spec_and_missing_file_are_errors(tmp_path: Path) -> None:
    bad = tmp_path / "invalid.json"
    bad.write_text('{"schema_version":"future"}', encoding="utf-8")
    assert main(["spec", "validate", "--manifest", str(bad)]) == 1
    assert main(["spec", "validate", "--manifest", str(tmp_path / "missing.json")]) == 1


def test_cli_build_validate_and_refuse_overwrite(tmp_path: Path) -> None:
    output = tmp_path / "public"
    assert main(["dataset", "build", "--output", str(output)]) == 0
    assert main(["dataset", "validate", "--manifest", str(output / "manifest.json")]) == 0
    assert main(["dataset", "build", "--output", str(output)]) == 1


def test_missing_receipt_is_a_cli_error(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ASSAY_STATE_DIR", str(tmp_path / "state"))
    assert main(["receipt", "--id", "execution-does-not-exist"]) == 1
