"""Revision-bound public checks with separate authenticity and analytical claims."""

from __future__ import annotations

import csv
import hashlib
import io
import sqlite3
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import ValidationError

from safety_lab.contracts import DatasetSnapshot, TaskSpec, canonical_json_bytes
from safety_lab.contracts.execution import ExecutionReceipt, WorkerSuccess
from safety_lab.contracts.report import CheckBundle, CheckResult, ClaimRecord, ReportRevision
from safety_lab.evidence import EvidenceIntegrityError, EvidenceStore
from safety_lab.gateway.policy import SQLPolicyError, validate_sql

from .semantics import Finding, Outcome, PublicRows, inspect_query

CHECKER_VERSION = "sales-public-1.0"
CheckClass = Literal["host_integrity", "research_mandatory", "advisory"]
CheckKey = tuple[str, str, str | None]
GLOBAL_HOST_CHECKS = ("report_contract", "declared_slots")
CLAIM_HOST_CHECKS = ("evidence_identity", "execution_success")
CLAIM_RESEARCH_CHECKS = (
    "cell_binding",
    "slot_contract",
    "query_metric",
    "query_units",
    "query_grain",
    "query_population",
    "public_missingness",
)
SEMANTIC_LIMITATION = (
    "Proves only the declared sales-public-1.0 SQL shapes; no private correctness score."
)
DIAGNOSTIC_LIMITATION = (
    "Diagnostics describe public rows; they do not supply an independent gold answer."
)
SEMANTIC_CHECKS = {
    "metric": "query_metric",
    "units": "query_units",
    "grain": "query_grain",
    "population": "query_population",
}


def required_check_keys(report: ReportRevision) -> frozenset[CheckKey]:
    """Frozen coverage expected by publication; absent checks never imply success."""

    return frozenset(
        [("host_integrity", name, None) for name in GLOBAL_HOST_CHECKS]
        + [
            (check_class, name, record.claim.slot_id)
            for record in report.claims
            for check_class, names in (
                ("host_integrity", CLAIM_HOST_CHECKS),
                ("research_mandatory", CLAIM_RESEARCH_CHECKS),
            )
            for name in names
        ]
    )


def _digest(model: object) -> str:
    # All callers are versioned contracts. Keeping the public helper typed at
    # those call sites avoids accepting arbitrary JSON as trusted evidence.
    if not isinstance(model, (ReportRevision, ClaimRecord, TaskSpec, DatasetSnapshot)):
        raise TypeError("Only public versioned verification inputs can be hashed")
    return hashlib.sha256(canonical_json_bytes(model)).hexdigest()


def _safe_input(path: Path) -> bytes:
    if path.is_symlink() or path.is_junction():
        raise EvidenceIntegrityError("Frozen public inputs cannot use links")
    return path.read_bytes()


def _public_rows(
    evidence: EvidenceStore, receipt: ExecutionReceipt, snapshot: DatasetSnapshot, task: TaskSpec
) -> PublicRows:
    """Inspect complete public exports, without importing generators or evaluators."""

    inputs = evidence.root / "inputs"
    bundle = inputs / receipt.snapshot_manifest_sha256
    if inputs.is_symlink() or inputs.is_junction() or bundle.is_symlink() or bundle.is_junction():
        raise EvidenceIntegrityError("Frozen public bundle cannot use links")
    if (bundle / "tables").is_symlink() or (bundle / "tables").is_junction():
        raise EvidenceIntegrityError("Frozen public tables cannot use links")
    if _safe_input(bundle / "manifest.json") != canonical_json_bytes(snapshot):
        raise EvidenceIntegrityError("Frozen manifest differs from captured public evidence")
    if _safe_input(bundle / "task.json") != canonical_json_bytes(task):
        raise EvidenceIntegrityError("Frozen task differs from captured public evidence")
    tables: dict[str, tuple[dict[str, str], ...]] = {}
    for table in snapshot.tables:
        content = _safe_input(bundle / table.path)
        if hashlib.sha256(content).hexdigest() != table.sha256:
            raise EvidenceIntegrityError("Frozen public table content hash changed")
        reader = csv.DictReader(io.StringIO(content.decode("utf-8"), newline=""))
        if reader.fieldnames != [column.name for column in table.columns]:
            raise EvidenceIntegrityError("Public CSV columns differ from captured manifest")
        parsed: list[dict[str, str]] = []
        for row in reader:
            if None in row or any(value is None for value in row.values()):
                raise EvidenceIntegrityError("Public CSV row shape differs from captured schema")
            if any(row[column.name] == "" and not column.nullable for column in table.columns):
                raise EvidenceIntegrityError("Public CSV violates nonnullable column contract")
            parsed.append(row)
        if len(parsed) != table.row_count:
            raise EvidenceIntegrityError("Public CSV row count differs from captured manifest")
        tables[table.table_id] = tuple(parsed)
    if "orders" not in tables or "order_items" not in tables:
        raise EvidenceIntegrityError("Supported public sales tables are unavailable")
    return PublicRows(orders=tables["orders"], items=tables["order_items"])


def _binding(record: ClaimRecord, result: WorkerSuccess | None, task: TaskSpec) -> Finding:
    claim = record.claim
    if claim.value is None:
        return Finding("cell_binding", "pass", "Explicit abstention asserts no numerical cell")
    if result is None or claim.result_id is None or claim.cell_locator is None:
        return Finding(
            "cell_binding", "fail", "Numerical claim requires a successful exact cell reference"
        )
    locator = claim.cell_locator
    names = [column.name for column in result.columns]
    if locator.column not in names or locator.row_index >= result.row_count:
        return Finding("cell_binding", "fail", "Designated row or exact column does not exist")
    cell = result.rows[locator.row_index][names.index(locator.column)]
    if cell.type not in ("integer", "decimal", "float"):
        return Finding("cell_binding", "fail", "Designated cell is not a finite numerical value")
    try:
        value = Decimal(str(cell.value))
    except InvalidOperation:
        return Finding("cell_binding", "fail", "Designated cell is not a numerical value")
    slots = {slot.slot_id: slot for slot in task.required_slots + task.supporting_slots}
    slot = slots.get(claim.slot_id)
    tolerance = (
        Decimal(0)
        if slot is None
        else max(slot.tolerance.absolute, abs(value) * slot.tolerance.relative)
    )
    matches = value.is_finite() and abs(claim.value - value) <= tolerance
    return Finding(
        "cell_binding",
        "pass" if matches else "fail",
        "Exact designated cell agrees within declared tolerance"
        if matches
        else "Claim value differs from the exact designated cell",
    )


def _slot_contract(record: ClaimRecord, report: ReportRevision) -> Finding:
    claim = record.claim
    slots = {
        slot.slot_id: slot for slot in report.task.required_slots + report.task.supporting_slots
    }
    slot = slots.get(claim.slot_id)
    if slot is None:
        return Finding("slot_contract", "fail", "Claim is outside declared answer slots")
    same = (
        claim.metric_id == slot.metric_id
        and claim.metric_type == slot.metric_type
        and claim.unit == slot.unit
        and claim.grain == slot.grain
        and claim.time_scope == report.task.time_scope
        and claim.report_semantics == report.task.report_semantics
        and claim.snapshot_id == report.snapshot_id
        and claim.snapshot_id in report.task.permitted_snapshot_ids
    )
    return Finding(
        "slot_contract",
        "pass" if same else "fail",
        "Metric, units, grain, UTC scope, snapshot and report semantics agree"
        if same
        else "Claim metadata differs from its public answer-slot contract",
    )


def verify_report(report: ReportRevision, evidence: EvidenceStore) -> CheckBundle:
    """Check exact stored evidence and a supported public analytical contract.

    Authenticity is deliberately independent of arithmetic and SQL semantics:
    authentic duplicated-join outputs can pass every host check and fail grain.
    Checks are returned even when prerequisites fail, with explicit unknowns.
    """

    report_hash = _digest(report)
    checks: list[CheckResult] = []

    def add(
        name: str,
        check_class: CheckClass,
        outcome: Outcome,
        detail: str,
        *,
        slot: str | None = None,
        hashes: tuple[str, ...] = (),
        applicable: bool = True,
        limitations: tuple[str, ...] = (),
    ) -> None:
        checks.append(
            CheckResult(
                check_id="check-" + uuid4().hex,
                name=name,
                checker_version=CHECKER_VERSION,
                check_class=check_class,
                outcome=outcome,
                applicability="applicable" if applicable else "not_applicable",
                claim_slot_id=slot,
                input_hashes=tuple(dict.fromkeys((report_hash, *hashes))),
                scope=detail[:2000],
                facts=(detail[:2000],),
                limitations=limitations,
            )
        )

    try:
        ReportRevision.model_validate(report.model_dump())
        valid = report.snapshot.task_sha256 == _digest(report.task) and set(
            report.task.allowed_tables
        ).issubset({table.table_id for table in report.snapshot.tables})
        add(
            "report_contract",
            "host_integrity",
            "pass" if valid else "fail",
            "Versioned report and public input hashes agree"
            if valid
            else "Report task hash or permitted table references disagree",
        )
    except (ValidationError, ValueError, TypeError):
        add(
            "report_contract",
            "host_integrity",
            "fail",
            "Report revision violates its versioned schema",
        )
    declared = {slot.slot_id for slot in report.task.required_slots + report.task.supporting_slots}
    required = {slot.slot_id for slot in report.task.required_slots}
    actual = [record.claim.slot_id for record in report.claims]
    complete = (
        len(set(actual)) == len(actual)
        and required.issubset(actual)
        and set(actual).issubset(declared)
    )
    add(
        "declared_slots",
        "host_integrity",
        "pass" if complete else "fail",
        "Required slots complete; no undeclared or repeated slots"
        if complete
        else "Missing required slots, undeclared slots, or repeated answer slots",
    )

    for record in report.claims:
        claim = record.claim
        slot_id = claim.slot_id
        inputs: tuple[str, ...] = (_digest(record),)
        result: WorkerSuccess | None = None
        receipt: ExecutionReceipt | None = None
        rows: PublicRows | None = None
        evidence_outcome: Outcome = "fail"
        evidence_detail = "Execution evidence is unavailable"
        try:
            receipt, result, snapshot, task = evidence.get_execution_context(record.execution_id)
            inputs += (receipt.query_sha256, receipt.snapshot_manifest_sha256, snapshot.task_sha256)
            if receipt.output_sha256:
                inputs += (receipt.output_sha256,)
            dependencies = {record.execution_id, receipt.snapshot_id, *receipt.source_ids}
            if receipt.result_id:
                dependencies.add(receipt.result_id)
            allowed = (
                receipt.run_id == report.run_id
                and receipt.task_id == report.task_id
                and task == report.task
                and receipt.snapshot_id == report.snapshot_id == claim.snapshot_id
                and receipt.snapshot_manifest_sha256 == _digest(report.snapshot)
                and snapshot == report.snapshot
                and (claim.value is None or claim.result_id == receipt.result_id)
                and set(claim.dependency_ids).issubset(dependencies)
            )
            admitted = validate_sql(receipt.exact_query, task.allowed_tables)
            allowed = (
                allowed
                and admitted.normalized_sql == receipt.normalized_query
                and (admitted.source_ids == receipt.source_ids)
            )
            if not allowed:
                raise EvidenceIntegrityError(
                    "Claim evidence has a different run, task, snapshot, result or dependency"
                )
            rows = _public_rows(evidence, receipt, snapshot, task)
            evidence_outcome = "pass"
            evidence_detail = (
                "Hash-checked execution, result and public inputs match exact authorized identities"
            )
        except (KeyError, EvidenceIntegrityError, SQLPolicyError, UnicodeError, csv.Error) as exc:
            evidence_detail = f"Evidence identity/integrity check failed: {type(exc).__name__}"
        except (OSError, sqlite3.Error):
            evidence_outcome = "unknown"
            evidence_detail = (
                "Required trusted evidence storage or frozen public inputs are unavailable"
            )
        add(
            "evidence_identity",
            "host_integrity",
            evidence_outcome,
            evidence_detail,
            slot=slot_id,
            hashes=inputs,
        )
        success = receipt is not None and receipt.status == "success" and result is not None
        add(
            "execution_success",
            "host_integrity",
            "pass" if success else "fail",
            "Designated query completed with its full captured result"
            if success
            else "Designated execution has no successful complete result",
            slot=slot_id,
            hashes=inputs,
        )
        binding = _binding(record, result if evidence_outcome == "pass" else None, report.task)
        add(
            binding.name,
            "research_mandatory",
            binding.outcome,
            binding.detail,
            slot=slot_id,
            hashes=inputs,
            applicable=claim.value is not None,
        )
        contract = _slot_contract(record, report)
        add(
            contract.name,
            "research_mandatory",
            contract.outcome,
            contract.detail,
            slot=slot_id,
            hashes=inputs,
        )
        findings: dict[str, Finding] = {}
        if (
            claim.value is not None
            and claim.cell_locator is not None
            and rows is not None
            and receipt is not None
        ):
            findings = {
                finding.name: finding
                for finding in inspect_query(
                    receipt.normalized_query,
                    claim.cell_locator.column,
                    claim.metric_type,
                    report.task,
                    rows,
                )
            }
        for semantic_name, check_name in SEMANTIC_CHECKS.items():
            if claim.value is None:
                add(
                    check_name,
                    "research_mandatory",
                    "pass",
                    "Explicit abstention makes no SQL metric assertion",
                    slot=slot_id,
                    hashes=inputs,
                    applicable=False,
                )
            else:
                finding = findings.get(
                    semantic_name,
                    findings.get(
                        "semantics",
                        Finding(
                            semantic_name,
                            "unknown",
                            "Supported semantic profile prerequisites are unavailable",
                        ),
                    ),
                )
                add(
                    check_name,
                    "research_mandatory",
                    finding.outcome,
                    finding.detail,
                    slot=slot_id,
                    hashes=inputs,
                    limitations=(SEMANTIC_LIMITATION,),
                )
        if rows is None:
            missingness = Finding(
                "public_missingness",
                "unknown",
                "Complete authenticated public rows are unavailable",
            )
        else:
            try:
                eligible = rows.eligible_orders(report.task)
                has_null = any(row["amount_minor"] == "" for row in eligible)
                if claim.value is None:
                    justified = (
                        report.task.abstention_allowed and claim.metric_type == "total" and has_null
                    )
                    missingness = Finding(
                        "public_missingness",
                        "pass" if justified else "fail",
                        "Eligible public order amount is missing; abstention is justified"
                        if justified
                        else "Public missingness does not justify this abstention",
                    )
                else:
                    missingness = Finding(
                        "public_missingness",
                        "fail" if claim.metric_type == "total" and has_null else "pass",
                        "Eligible public amount is missing; total requires abstention"
                        if claim.metric_type == "total" and has_null
                        else "Required public amounts are available (or this is an order count)",
                    )
                    if not eligible and claim.metric_type == "total":
                        missingness = Finding(
                            "public_missingness",
                            "unknown",
                            "Empty-population total policy is unsupported",
                        )
                add(
                    "data_diagnostics",
                    "advisory",
                    "pass",
                    f"Inspected {len(rows.orders)} public orders, {len(rows.items)} items; "
                    f"eligible rows={len(eligible)}; missing eligible amount={has_null}",
                    slot=slot_id,
                    hashes=inputs,
                    limitations=(DIAGNOSTIC_LIMITATION,),
                )
            except (KeyError, ValueError):
                missingness = Finding(
                    "public_missingness",
                    "unknown",
                    "Public rows are outside supported diagnostic semantics",
                )
        add(
            missingness.name,
            "research_mandatory",
            missingness.outcome,
            missingness.detail,
            slot=slot_id,
            hashes=inputs,
        )

    return CheckBundle(
        check_bundle_id="checks-" + uuid4().hex,
        report_revision_id=report.revision_id,
        report_sha256=report_hash,
        checks=tuple(checks),
        input_hashes=(report_hash,),
        created_at=datetime.now(UTC),
    )
