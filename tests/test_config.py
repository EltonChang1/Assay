from pathlib import Path

import pytest
from pydantic import ValidationError

from safety_lab.config import state_directory
from safety_lab.contracts.experiment import ExperimentConfig


def test_state_override_is_absolute_and_outside_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "source"
    state = tmp_path / "state"
    assert (
        state_directory(environ={"SAFETY_LAB_STATE_DIR": str(state)}, workspace=workspace)
        == state.resolve()
    )
    for value in ("relative-state", str(workspace / "runs"), str(tmp_path / "OneDrive" / "x")):
        with pytest.raises(ValueError):
            state_directory(environ={"SAFETY_LAB_STATE_DIR": value}, workspace=workspace)


def test_state_rejects_named_sync_root(tmp_path: Path) -> None:
    sync = tmp_path / "company-sync"
    with pytest.raises(ValueError, match="OneDrive"):
        state_directory(
            environ={"SAFETY_LAB_STATE_DIR": str(sync / "runs"), "OneDriveCommercial": str(sync)},
            workspace=tmp_path / "source",
        )


def test_development_spec_and_budget_constraints() -> None:
    config = ExperimentConfig.model_validate_json(
        Path("experiment_specs/development.json").read_text(encoding="utf-8")
    )
    assert config.total_cost_cap_usd == 0
    for change in (
        {"total_cost_cap_usd": "1"},
        {"oversight_cost_cap_usd": "1"},
        {"mode": "live", "total_cost_cap_usd": "1"},
        {"task_ids": ["duplicate", "duplicate"]},
        {"total_cost_cap_usd": "NaN"},
        {"unexpected": True},
    ):
        with pytest.raises(ValidationError):
            ExperimentConfig.model_validate(config.model_dump() | change)


def test_reviewer_arm_requires_combined_oversight_budget() -> None:
    live = dict(
        experiment_id="dev",
        task_ids=("sales",),
        mode="live",
        analyst_model="provider/analyst-version",
        reviewer_model="provider/reviewer-version",
        total_cost_cap_usd="2.00",
        oversight_cost_cap_usd="0.50",
    )
    assert ExperimentConfig.model_validate(live).mode == "live"
    with pytest.raises(ValidationError):
        ExperimentConfig.model_validate(live | {"oversight_cost_cap_usd": "2.01"})
