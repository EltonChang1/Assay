"""One-use trusted TraceFrame projector. Invoked only by the parent adapter.

No upstream implementation is copied here. The narrow extension writes actual
upstream EvidenceRecord instances through its storage and evidence interfaces.
"""

from __future__ import annotations

import html
import importlib
import importlib.metadata
import json
import os
import sys
from pathlib import Path
from typing import Any

from assay.adapters.traceframe import (
    AUDIT_LIMITATIONS,
    TRACEFRAME_COMMIT,
    TRACEFRAME_LICENSE_SHA256,
    TRACEFRAME_VERSION,
    ExportFile,
    ProjectionIdentity,
    TraceFrameExportError,
    TraceFrameManifest,
    _digest,
    validate_audit_bundle,
)
from assay.contracts import VersionedModel, canonical_json_bytes
from assay.contracts.report import AuditBundle


def _upstream_license() -> bytes:
    """Require the installed exact VCS pin and preserved upstream MIT notice."""

    distribution = importlib.metadata.distribution("traceframe")
    provenance = json.loads(distribution.read_text("direct_url.json") or "{}")
    if (
        distribution.version != TRACEFRAME_VERSION
        or provenance.get("vcs_info", {}).get("commit_id") != TRACEFRAME_COMMIT
        or provenance.get("url", "").removesuffix(".git")
        != "https://github.com/EltonChang1/traceframe"
    ):
        raise TraceFrameExportError("installed TraceFrame does not match the inspected exact pin")
    for file in distribution.files or ():
        if file.name == "LICENSE":
            notice = Path(str(distribution.locate_file(file))).read_bytes()
            # Notice text may be packaged with platform line endings.
            normalized = notice.replace(b"\r\n", b"\n")
            if _digest(normalized) == TRACEFRAME_LICENSE_SHA256:
                return normalized
    raise TraceFrameExportError("installed TraceFrame's inspected MIT notice is missing or changed")


def _identity(kind: str, lab_id: str) -> str:
    return f"lab-{kind}-{_digest((kind + ':' + lab_id).encode())}"


def _audit_notice(bundle: AuditBundle, limitations: tuple[str, ...]) -> str:
    checks = () if bundle.checks is None else bundle.checks.checks
    rows = "".join(
        "<tr><td>"
        + html.escape(check.check_id)
        + "</td><td>"
        + html.escape(check.outcome)
        + "</td><td>"
        + html.escape(check.applicability)
        + "</td><td>"
        + html.escape(check.check_class)
        + "</td></tr>"
        for check in checks
    )
    if not rows:
        rows = '<tr><td colspan="4">No check bundle recorded.</td></tr>'
    notices = "".join("<li>" + html.escape(item) + "</li>" for item in limitations)
    return (
        '<section aria-label="Researcher audit boundaries" style="padding:24px;background:#fff4df">'
        "<h1>Researcher audit — not an end-user released report</h1>"
        "<p>Authoritative lab run: <code>"
        + html.escape(bundle.report.run_id)
        + "</code>. Recorded validity: <strong>"
        + html.escape(bundle.validity)
        + "</strong>. A release record "
        + ("is present" if bundle.release is not None else "is absent")
        + "; exporting this audit does not publish or approve any report.</p>"
        "<h2>Exact lab check outcomes</h2><table><tr><th>Check</th><th>Outcome</th>"
        "<th>Applicability</th><th>Class</th></tr>"
        + rows
        + "</table><h2>Projection limitations</h2><ul>"
        + notices
        + '</ul><p>Exact contracts and unsupported fields: <a href="lab-records.json">'
        "versioned lab-records.json companion</a>.</p></section>"
    )


def project(bundle: AuditBundle, destination: Path) -> None:
    """Project public captured records in this process's fresh working directory."""

    bundle = validate_audit_bundle(bundle)
    license_notice = _upstream_license()
    destination.mkdir(parents=True, exist_ok=False)
    os.chdir(destination)
    traceframe = importlib.import_module("traceframe")
    evidence_module = importlib.import_module("traceframe.evidence")
    storage = importlib.import_module("traceframe.storage")
    tracking = importlib.import_module("traceframe.tracking")
    lineage = importlib.import_module("traceframe.lineage")
    runs = importlib.import_module("traceframe.runs")
    report_module = importlib.import_module("traceframe.report")
    trace_dir = traceframe.start("Assay researcher audit " + bundle.report.run_id)
    active_run = runs.current_run()
    if active_run is None:
        raise TraceFrameExportError("TraceFrame failed to initialize an isolated run")
    traceframe_run_id: str = active_run["id"]
    # Keep local absolute script paths and environment notebook names out of the
    # exported context. The originating lab run remains explicit in metadata.
    active_run["context"] = {
        "kind": "research_audit_projection",
        "notebook_name": None,
        "script_path": None,
    }
    storage.write_json(trace_dir / "runs.json", {"runs": [active_run]})
    created_at = bundle.report.created_at.isoformat()
    limitations = tuple(dict.fromkeys((*AUDIT_LIMITATIONS, *bundle.limitations)))
    identities: list[ProjectionIdentity] = []
    evidence_ids: set[str] = set()

    def record(
        kind: Any,
        lab_id: str,
        content: VersionedModel,
        artifact_type: str,
        *,
        source_ids: tuple[str, ...] = (),
        file_hashes: tuple[str, ...] = (),
        row_count: int | None = None,
        columns: tuple[str, ...] = (),
        sql: str | None = None,
        warnings: tuple[str, ...] = (),
    ) -> str:
        identity = _identity(kind, lab_id)
        if identity in evidence_ids:
            return identity
        evidence_ids.add(identity)
        content_hash = _digest(canonical_json_bytes(content))
        identities.append(
            ProjectionIdentity(
                lab_kind=kind,
                lab_id=lab_id,
                traceframe_id=identity,
                content_sha256=content_hash,
            )
        )
        metadata = {
            "lab_kind": kind,
            "lab_id": lab_id,
            "lab_run_id": bundle.report.run_id,
            "lab_content_sha256": content_hash,
            "lab_record": content.model_dump(mode="json"),
            "audience": "research_audit",
            "traceframe_commit": TRACEFRAME_COMMIT,
        }
        evidence = evidence_module.EvidenceRecord(
            id=identity,
            artifact_type=artifact_type,
            name=lab_id,
            created_at=created_at,
            run_id=traceframe_run_id,
            source_ids=list(source_ids),
            file_hashes=list(file_hashes),
            row_count_after=row_count,
            columns=list(columns),
            sql=sql,
            assumptions=["Projection of host-captured evidence; no execution or proof is implied."],
            warnings=list(warnings),
            metadata=metadata,
        )
        tracking.write_evidence(evidence)
        lineage.add_node(identity, artifact_type, lab_id, metadata)
        return identity

    record(
        "snapshot",
        bundle.snapshot.snapshot_id,
        bundle.snapshot,
        "dataset",
        file_hashes=(_digest(canonical_json_bytes(bundle.snapshot)),),
    )
    source_map: dict[str, str] = {}
    for table in bundle.snapshot.tables:
        source_map[table.table_id] = record(
            "source",
            bundle.snapshot.snapshot_id + ":" + table.table_id,
            table,
            "dataset",
            file_hashes=(table.sha256,),
            row_count=table.row_count,
            columns=tuple(column.name for column in table.columns),
            warnings=("Metadata only; original source bytes and source-row samples are absent.",),
        )
    execution_map: dict[str, str] = {}
    result_map: dict[str, str] = {}
    for item in bundle.executions:
        receipt = item.receipt
        parents = tuple(source_map[source] for source in receipt.source_ids)
        execution_map[receipt.execution_id] = record(
            "execution",
            receipt.execution_id,
            receipt,
            "transformation",
            source_ids=parents,
            file_hashes=(receipt.query_sha256, receipt.snapshot_manifest_sha256),
            sql=receipt.exact_query,
            warnings=(
                () if receipt.status == "success" else ("Execution outcome: " + receipt.status,)
            ),
        )
        for parent in parents:
            lineage.add_edge(parent, execution_map[receipt.execution_id], "read_source")
        if item.result is not None and receipt.result_id is not None:
            result_map[receipt.result_id] = record(
                "result",
                receipt.result_id,
                item.result,
                "sql_result",
                source_ids=(execution_map[receipt.execution_id],),
                file_hashes=(() if receipt.output_sha256 is None else (receipt.output_sha256,)),
                row_count=item.result.row_count,
                columns=tuple(column.name for column in item.result.columns),
            )
            lineage.add_edge(
                execution_map[receipt.execution_id],
                result_map[receipt.result_id],
                "captured_result",
            )
    projected_claims: list[dict[str, Any]] = []
    for claim_record in bundle.report.claims:
        claim = claim_record.claim
        parents = (execution_map[claim_record.execution_id],)
        if claim.result_id in result_map:
            parents += (result_map[claim.result_id],)
        identity = record("claim", claim_record.claim_id, claim_record, "claim", source_ids=parents)
        for parent in parents:
            lineage.add_edge(parent, identity, "asserted_binding")
        value = str(claim.value) if claim.value is not None else "abstention"
        projected_claims.append(
            {
                "id": identity,
                "text": claim.slot_id + ": " + value + " " + claim.unit,
                "supports": list(parents),
                "confidence": None,
                "created_at": created_at,
                "run_id": traceframe_run_id,
            }
        )
    storage.write_json(trace_dir / "claims.json", {"claims": projected_claims})
    projected_checks: list[dict[str, Any]] = []
    for check in () if bundle.checks is None else bundle.checks.checks:
        identity = record(
            "check",
            check.check_id,
            check,
            "check",
            file_hashes=check.input_hashes,
            warnings=check.limitations,
        )
        if check.outcome != "unknown":
            projected_checks.append(
                {
                    "id": identity,
                    "name": check.name,
                    "check_type": "trusted_lab_check",
                    "passed": check.outcome == "pass",
                    "severity": "warning" if check.check_class == "advisory" else "error",
                    "description": check.scope,
                    "source": check.claim_slot_id,
                    "source_id": None,
                    "details": check.model_dump(mode="json"),
                    "created_at": created_at,
                    "run_id": traceframe_run_id,
                }
            )
    storage.write_json(trace_dir / "checks.json", {"checks": projected_checks})
    report_path = report_module.export_report("researcher-audit.html")
    rendered = report_path.read_text(encoding="utf-8")
    if "<body>" not in rendered:
        raise TraceFrameExportError("unsupported TraceFrame report template")
    report_path.write_text(
        rendered.replace("<body>", "<body>" + _audit_notice(bundle, limitations), 1),
        encoding="utf-8",
        newline="\n",
    )
    (destination / "lab-records.json").write_bytes(canonical_json_bytes(bundle))
    (destination / "TRACEFRAME-LICENSE.txt").write_bytes(license_notice)
    files = tuple(
        ExportFile(path=path.relative_to(destination).as_posix(), sha256=_digest(path.read_bytes()))
        for path in sorted(destination.rglob("*"))
        if path.is_file()
    )
    manifest = TraceFrameManifest(
        run_id=bundle.report.run_id,
        traceframe_run_id=traceframe_run_id,
        exporter_pid=os.getpid(),
        bundle_sha256=_digest(canonical_json_bytes(bundle)),
        identities=tuple(identities),
        limitations=limitations,
        files=files,
    )
    (destination / "traceframe-export.json").write_bytes(canonical_json_bytes(manifest))


def main() -> int:
    if len(sys.argv) != 3:
        return 2
    try:
        bundle = AuditBundle.model_validate_json(Path(sys.argv[1]).read_bytes())
        project(bundle, Path(sys.argv[2]).resolve())
    except Exception:
        # Preserve no partial output as success and don't emit analyst data or
        # private host paths through caller logs. Parent deletes the scratch dir.
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
