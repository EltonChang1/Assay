"""Controlled UTF-8 text templates; model prose never enters released bytes."""

from __future__ import annotations

from decimal import Decimal

from safety_lab.contracts import TaskSpec
from safety_lab.contracts.report import ClaimRecord

RENDERER_VERSION = "structured-text-1.0"


def _amount(value: Decimal, *, money: bool) -> str:
    if value == 0:
        value = Decimal(0)
    plain = format(value, "f")
    whole, _, fraction = plain.partition(".")
    fraction = fraction.rstrip("0")
    if money:
        return whole + "." + fraction.ljust(2, "0")
    return whole + ("." + fraction if fraction else "")


def render_report(task: TaskSpec, claims: tuple[ClaimRecord, ...]) -> bytes:
    """Render only declared answer slots and typed scope, preserving exact values."""
    task = TaskSpec.model_validate(task.model_dump())
    claims = tuple(ClaimRecord.model_validate(record.model_dump()) for record in claims)
    allowed = {slot.slot_id: slot for slot in (*task.required_slots, *task.supporting_slots)}
    supplied = {record.claim.slot_id: record for record in claims}
    if len(supplied) != len(claims) or set(supplied) - allowed.keys():
        raise ValueError("Reports require unique declared answer slots")
    if {slot.slot_id for slot in task.required_slots} - supplied.keys():
        raise ValueError("Report is missing a required answer slot")
    lines = [
        "TraceFrame Safety Lab",
        "Settled order report",
        f"Data basis: {task.report_semantics} snapshot",
        f"Interval (UTC, end exclusive): {task.time_scope.start.isoformat()} / "
        f"{task.time_scope.end.isoformat()}",
        "",
    ]
    for heading, slots in (
        ("Required answers", task.required_slots),
        ("Supporting answers", task.supporting_slots),
    ):
        present = [slot for slot in slots if slot.slot_id in supplied]
        if not present:
            continue
        lines.append(heading)
        for slot in present:
            claim = supplied[slot.slot_id].claim
            if (
                claim.metric_id != slot.metric_id
                or claim.metric_type != slot.metric_type
                or claim.unit != slot.unit
                or claim.grain != slot.grain
                or claim.time_scope != task.time_scope
                or claim.report_semantics != task.report_semantics
                or claim.snapshot_id not in task.permitted_snapshot_ids
            ):
                raise ValueError("Claim declarations disagree with their public answer slot")
            label = (
                "Settled order revenue" if slot.metric_type == "total" else "Settled order count"
            )
            if claim.value is None:
                if not task.abstention_allowed:
                    raise ValueError("This task does not permit abstention")
                answer = "Unable to establish this metric from the permitted data."
            elif slot.metric_type == "total":
                answer = "USD " + _amount(claim.value, money=True)
            else:
                answer = _amount(claim.value, money=False) + " orders"
            lines.append(f"{label}: {answer}")
        lines.append("")
    return ("\n".join(lines).rstrip() + "\n").encode("utf-8")
