"""Local state paths. Public immutable fixture exports may live elsewhere."""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from pathlib import Path


def state_directory(
    *, environ: Mapping[str, str] | None = None, workspace: Path | None = None
) -> Path:
    env = os.environ if environ is None else environ
    if override := env.get("SAFETY_LAB_STATE_DIR"):
        candidate = Path(override).expanduser()
        if not candidate.is_absolute():
            raise ValueError("SAFETY_LAB_STATE_DIR must be an absolute local path")
    elif sys.platform == "win32":
        if not (base := env.get("LOCALAPPDATA")):
            raise ValueError("LOCALAPPDATA is unavailable; set SAFETY_LAB_STATE_DIR")
        candidate = Path(base) / "TraceFrameSafetyLab"
    else:
        candidate = Path(env.get("XDG_STATE_HOME", str(Path.home() / ".local" / "state")))
        candidate /= "TraceFrameSafetyLab"

    resolved = candidate.resolve()
    source = (workspace or Path(__file__).resolve().parents[2]).resolve()
    if resolved == source or source in resolved.parents:
        raise ValueError("Live state must be outside the source workspace")
    if any("onedrive" in part.casefold() for part in resolved.parts):
        raise ValueError("Live state must be outside OneDrive")
    for key in ("OneDrive", "OneDriveConsumer", "OneDriveCommercial"):
        if value := env.get(key):
            sync_root = Path(value).expanduser().resolve()
            if resolved == sync_root or sync_root in resolved.parents:
                raise ValueError("Live state must be outside OneDrive")
    if not resolved.is_absolute():
        raise ValueError("Live state must resolve to an absolute path")
    return resolved
