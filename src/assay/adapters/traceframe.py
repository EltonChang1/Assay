"""Isolated, integrity-checked TraceFrame researcher-audit projections.

The lab bundle remains authoritative. This module has no publication API and
never executes SQL. TraceFrame imports occur only in the one-export subprocess.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Annotated, Final, Literal

from pydantic import Field, ValidationError

from assay.contracts import VersionedModel, canonical_json_bytes
from assay.contracts.report import AuditBundle
from assay.contracts.snapshot import Sha256
from assay.evidence.store import EvidenceIntegrityError, _validate_execution

TRACEFRAME_COMMIT: Final = "422befdcbadb95024b75b2e4ac381cb6716b97c3"
TRACEFRAME_VERSION: Final = "0.1.0"
TRACEFRAME_LICENSE_SHA256 = "e45758a61ce1a6293d3c315edbfb3e76d48a1c35b84a32b03153ebfe96625098"
ADAPTER_VERSION: Final = "traceframe-projection-1.0"
AUDIT_LIMITATIONS = (
    "Researcher audit only; this HTML is not an end-user released report or publication authority.",
    "Lineage records explicit table/execution/result/claim relationships; "
    "row lineage is incomplete.",
    "Source tables are hash-and-schema metadata only; no source-row samples are exported.",
    "Captured result cells are preserved without re-executing SQL or recomputing claims.",
    "Unknown checks remain unknown in evidence and the companion; TraceFrame's boolean-only "
    "native check table includes only pass and fail outcomes.",
    "The companion preserves exact lab contracts, locators, receipt failures, revision, approval, "
    "release and validity fields unsupported by TraceFrame's native model.",
    "Export hashes detect accidental changes; mutable local audit files are not tamper protection.",
)


class TraceFrameExportError(ValueError):
    """A projection failed; the authoritative publication state is unchanged."""


class ProjectionIdentity(VersionedModel):
    lab_kind: Literal["snapshot", "source", "execution", "result", "claim", "check"]
    lab_id: str = Field(min_length=1)
    traceframe_id: str = Field(pattern=r"^lab-[a-z]+-[0-9a-f]{64}$")
    content_sha256: Sha256


class ExportFile(VersionedModel):
    path: str = Field(min_length=1)
    sha256: Sha256


class TraceFrameManifest(VersionedModel):
    audience: Literal["research_audit"] = "research_audit"
    adapter_version: Literal["traceframe-projection-1.0"] = ADAPTER_VERSION
    traceframe_commit: Literal["422befdcbadb95024b75b2e4ac381cb6716b97c3"] = TRACEFRAME_COMMIT
    traceframe_version: Literal["0.1.0"] = TRACEFRAME_VERSION
    upstream_license_sha256: Sha256 = TRACEFRAME_LICENSE_SHA256
    run_id: str = Field(min_length=1)
    traceframe_run_id: str = Field(min_length=1)
    exporter_pid: Annotated[int, Field(strict=True, gt=0)]
    bundle_sha256: Sha256
    identities: tuple[ProjectionIdentity, ...]
    limitations: tuple[str, ...]
    files: tuple[ExportFile, ...]


@dataclass(frozen=True)
class TraceFrameExport:
    root: Path
    manifest: TraceFrameManifest

    @property
    def report_path(self) -> Path:
        return self.root / "researcher-audit.html"

    @property
    def manifest_path(self) -> Path:
        return self.root / "traceframe-export.json"


def _digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def validate_audit_bundle(bundle: AuditBundle) -> AuditBundle:
    """Revalidate caller copies and captured hashes, without rechecking analytical truth."""

    try:
        checked = AuditBundle.model_validate(bundle.model_dump())
        if checked.report.task != checked.task or checked.report.snapshot != checked.snapshot:
            raise TraceFrameExportError("audit report and public input records disagree")
        executions = {item.receipt.execution_id: item for item in checked.executions}
        if len(executions) != len(checked.executions):
            raise TraceFrameExportError("audit contains duplicate execution identities")
        for item in checked.executions:
            _validate_execution(item.receipt, item.result, checked.snapshot, checked.task)
            if item.receipt.run_id != checked.report.run_id:
                raise TraceFrameExportError("audit execution belongs to another run")
        if not set(checked.report.execution_ids).issubset(executions):
            raise TraceFrameExportError("audit is missing a referenced execution")
        from assay.publication.rendering import render_report

        if (
            _digest(render_report(checked.task, checked.report.claims))
            != checked.report.rendered_sha256
        ):
            raise TraceFrameExportError("audit rendered-report hash disagrees")
        report_hash = _digest(canonical_json_bytes(checked.report))
        if checked.checks is not None:
            if (
                checked.checks.report_revision_id != checked.report.revision_id
                or checked.checks.report_sha256 != report_hash
            ):
                raise TraceFrameExportError("audit checks refer to different report bytes")
            check_ids = [check.check_id for check in checked.checks.checks]
            if len(set(check_ids)) != len(check_ids):
                raise TraceFrameExportError("audit contains duplicate check identities")
        if checked.approval is not None and (
            checked.approval.report_revision_id != checked.report.revision_id
            or checked.approval.report_sha256 != report_hash
            or checked.approval.rendered_sha256 != checked.report.rendered_sha256
            or checked.checks is None
            or checked.approval.check_bundle_sha256 != _digest(canonical_json_bytes(checked.checks))
        ):
            raise TraceFrameExportError("audit approval dependencies disagree")
        if checked.release is not None and (
            checked.approval is None
            or checked.release.approval_id != checked.approval.approval_id
            or checked.release.report_revision_id != checked.report.revision_id
            or checked.release.rendered_sha256 != checked.report.rendered_sha256
        ):
            raise TraceFrameExportError("audit release dependencies disagree")
        return checked
    except (ValidationError, EvidenceIntegrityError) as exc:
        raise TraceFrameExportError(
            "audit input failed schema or content integrity checks"
        ) from exc


def _canonical_read(path: Path, model: type[VersionedModel]) -> VersionedModel:
    try:
        content = path.read_bytes()
        parsed = model.model_validate_json(content)
        if canonical_json_bytes(parsed) != content:
            raise TraceFrameExportError("audit file serialization is not canonical")
        return parsed
    except (OSError, ValidationError) as exc:
        raise TraceFrameExportError("audit file is missing, malformed or unsupported") from exc


def _projection_records(bundle: AuditBundle) -> dict[tuple[str, str], VersionedModel]:
    records: dict[tuple[str, str], VersionedModel] = {
        ("snapshot", bundle.snapshot.snapshot_id): bundle.snapshot
    }
    for table in bundle.snapshot.tables:
        records["source", bundle.snapshot.snapshot_id + ":" + table.table_id] = table
    for item in bundle.executions:
        records["execution", item.receipt.execution_id] = item.receipt
        if item.result is not None and item.receipt.result_id is not None:
            records["result", item.receipt.result_id] = item.result
    for claim_record in bundle.report.claims:
        records["claim", claim_record.claim_id] = claim_record
    for check in () if bundle.checks is None else bundle.checks.checks:
        records["check", check.check_id] = check
    return records


def _verify_projection(root: Path, manifest: TraceFrameManifest, bundle: AuditBundle) -> None:
    records = _projection_records(bundle)
    keys: set[tuple[str, str]] = set()
    for item in manifest.identities:
        key = item.lab_kind, item.lab_id
        if key in keys or key not in records:
            raise TraceFrameExportError("audit projection contains duplicate or foreign identities")
        keys.add(key)
        expected_id = f"lab-{item.lab_kind}-" + _digest(
            (item.lab_kind + ":" + item.lab_id).encode()
        )
        if item.traceframe_id != expected_id or item.content_sha256 != _digest(
            canonical_json_bytes(records[key])
        ):
            raise TraceFrameExportError("audit projection identity or record hash disagrees")
        try:
            record = json.loads(
                (root / ".traceframe" / "audit_logs" / f"{item.traceframe_id}.json").read_bytes()
            )
            metadata = record["metadata"]
            if (
                record["id"] != item.traceframe_id
                or record["run_id"] != manifest.traceframe_run_id
                or metadata["lab_kind"] != item.lab_kind
                or metadata["lab_id"] != item.lab_id
                or metadata["lab_run_id"] != bundle.report.run_id
                or metadata["lab_content_sha256"] != item.content_sha256
                or metadata["lab_record"] != records[key].model_dump(mode="json")
            ):
                raise TraceFrameExportError(
                    "TraceFrame evidence differs from authoritative records"
                )
        except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
            raise TraceFrameExportError("TraceFrame evidence is malformed or missing") from exc
    if keys != records.keys():
        raise TraceFrameExportError("TraceFrame projection omitted authoritative record identities")


def read_traceframe_export(destination: str | Path) -> tuple[TraceFrameExport, AuditBundle]:
    """Read and verify all exported bytes and return the lossless public companion."""

    root = Path(destination).resolve()
    parsed = _canonical_read(root / "traceframe-export.json", TraceFrameManifest)
    assert isinstance(parsed, TraceFrameManifest)
    seen: set[str] = set()
    for item in parsed.files:
        relative = PurePosixPath(item.path)
        if relative.is_absolute() or ".." in relative.parts or "\\" in item.path:
            raise TraceFrameExportError("audit manifest contains an unsafe artifact path")
        if item.path in seen:
            raise TraceFrameExportError("audit manifest contains duplicate artifact paths")
        seen.add(item.path)
        path = (root / Path(*relative.parts)).resolve()
        if not path.is_relative_to(root):
            raise TraceFrameExportError("audit artifact escapes its export directory")
        try:
            if _digest(path.read_bytes()) != item.sha256:
                raise TraceFrameExportError("audit artifact content hash changed")
        except OSError as exc:
            raise TraceFrameExportError("audit artifact is missing") from exc
    required = {"lab-records.json", "researcher-audit.html", "TRACEFRAME-LICENSE.txt"}
    if not required.issubset(seen):
        raise TraceFrameExportError("audit manifest lacks required artifacts")
    companion = _canonical_read(root / "lab-records.json", AuditBundle)
    assert isinstance(companion, AuditBundle)
    companion = validate_audit_bundle(companion)
    if (
        _digest(canonical_json_bytes(companion)) != parsed.bundle_sha256
        or companion.report.run_id != parsed.run_id
        or parsed.upstream_license_sha256 != TRACEFRAME_LICENSE_SHA256
        or _digest((root / "TRACEFRAME-LICENSE.txt").read_bytes()) != TRACEFRAME_LICENSE_SHA256
        or not set(AUDIT_LIMITATIONS).issubset(parsed.limitations)
    ):
        raise TraceFrameExportError("audit manifest and companion identities disagree")
    actual = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and path.name != "traceframe-export.json"
    }
    if actual != seen:
        raise TraceFrameExportError("audit contains unmanifested or missing files")
    _verify_projection(root, parsed, companion)
    return TraceFrameExport(root, parsed), companion


def export_traceframe(
    bundle: AuditBundle,
    destination: str | Path,
    *,
    timeout_seconds: float = 60,
) -> TraceFrameExport:
    """Export in a fresh process; identical retries reuse a verified complete export.

    Install the optional pinned ``traceframe`` extra before calling. Failure never
    writes to the evidence store, approval records, or release state.
    """

    checked = validate_audit_bundle(bundle)
    bundle_bytes = canonical_json_bytes(checked)
    target = Path(destination).resolve()
    if target.exists():
        existing, old_bundle = read_traceframe_export(target)
        if canonical_json_bytes(old_bundle) != bundle_bytes:
            raise TraceFrameExportError("export destination already contains another audit bundle")
        return existing
    target.parent.mkdir(parents=True, exist_ok=True)
    # Only the public bundle crosses this process boundary. Do not inherit model
    # credentials or caller-controlled PYTHONPATH into the exporter environment.
    keep_environment = {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "LANG", "LC_ALL"}
    environment = {
        key: value for key, value in os.environ.items() if key.upper() in keep_environment
    }
    environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[2])
    environment["PYTHONIOENCODING"] = "utf-8"
    with tempfile.TemporaryDirectory(prefix=".traceframe-audit-", dir=target.parent) as scratch:
        scratch_root = Path(scratch)
        input_path = scratch_root / "input.json"
        output_path = scratch_root / "export"
        input_path.write_bytes(bundle_bytes)
        # Upstream plotting imports resolve a home/cache path at import time.
        # Give them a disposable directory instead of the host user's home.
        home = scratch_root / "home"
        home.mkdir()
        for name in ("HOME", "USERPROFILE", "XDG_CACHE_HOME"):
            environment[name] = str(home)
        try:
            outcome = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "assay.adapters._traceframe_worker",
                    str(input_path),
                    str(output_path),
                ],
                cwd=scratch_root,
                env=environment,
                capture_output=True,
                timeout=timeout_seconds,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise TraceFrameExportError("TraceFrame exporter unavailable or timed out") from exc
        if outcome.returncode != 0:
            # Child diagnostics can contain analyst data; return a bounded code,
            # not subprocess stderr, through the ordinary host error channel.
            raise TraceFrameExportError(
                "TraceFrame exporter failed; publication state is unchanged"
            )
        exported, restored = read_traceframe_export(output_path)
        if canonical_json_bytes(restored) != bundle_bytes:
            raise TraceFrameExportError("TraceFrame companion differs from authoritative input")
        try:
            output_path.rename(target)
        except OSError as exc:
            if not target.exists():
                raise TraceFrameExportError("TraceFrame audit could not be committed") from exc
            concurrent, concurrent_bundle = read_traceframe_export(target)
            if canonical_json_bytes(concurrent_bundle) != bundle_bytes:
                raise TraceFrameExportError("concurrent export destination conflict") from exc
            return concurrent
        return TraceFrameExport(target, exported.manifest)
