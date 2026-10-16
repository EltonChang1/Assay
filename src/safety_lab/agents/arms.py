"""Experimental arms A–E over one analyst interface and one release path.

Every arm uses the same analyst prompt, tools, claim schema, budgets, host
integrity checks, and publisher. Arms vary only the research interventions:
whether research checks gate release, whether a reviewer runs, and which view
the reviewer receives (see ``safety_lab.contracts.policy.ARMS``).
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from safety_lab.contracts.episode import EpisodeRecord
from safety_lab.contracts.experiment import ResourceLimits
from safety_lab.contracts.policy import ARMS, Arm
from safety_lab.publication import Publisher

from .episode import EpisodeLimits, run_analyst_episode
from .model import ModelClient

if TYPE_CHECKING:
    from safety_lab.review import ReviewConfig, ReviewLimits


def arm_review_config(
    arm: Arm,
    *,
    reviewer: ModelClient | None = None,
    summarizer: ModelClient | None = None,
    limits: ReviewLimits | None = None,
) -> ReviewConfig | None:
    """The arm's review configuration; models an arm does not use are refused."""

    from safety_lab.review import ReviewConfig, ReviewLimits

    view = ARMS[arm][1]
    if view is None:
        if reviewer is not None or summarizer is not None or limits is not None:
            raise ValueError(f"arm {arm} has no reviewer")
        return None
    if reviewer is None:
        raise ValueError(f"arm {arm} requires a reviewer model")
    if view == "evidence" and summarizer is not None:
        raise ValueError(f"arm {arm} reviews a host-built evidence view without a summarizer")
    if view == "ordinary" and summarizer is None:
        raise ValueError(f"arm {arm} requires a summarizer for its ordinary view")
    return ReviewConfig(
        reviewer=reviewer, view=view, summarizer=summarizer, limits=limits or ReviewLimits()
    )


def run_arm_episode(
    model: ModelClient,
    arm: Arm,
    *,
    publisher: Publisher,
    state: Path,
    bundle: Path,
    source_key: str,
    run_id: str,
    report_id: str,
    reviewer: ModelClient | None = None,
    summarizer: ModelClient | None = None,
    review_limits: ReviewLimits | None = None,
    limits: EpisodeLimits | None = None,
    query_limits: ResourceLimits | None = None,
    cancel: threading.Event | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> EpisodeRecord:
    """Run one episode under ``arm``; configuration errors raise before any model call."""

    review = arm_review_config(arm, reviewer=reviewer, summarizer=summarizer, limits=review_limits)
    return run_analyst_episode(
        model,
        publisher=publisher,
        state=state,
        bundle=bundle,
        source_key=source_key,
        run_id=run_id,
        report_id=report_id,
        policy_profile=ARMS[arm][0],
        review=review,
        arm=arm,
        limits=limits,
        query_limits=query_limits,
        cancel=cancel,
        clock=clock,
    )
