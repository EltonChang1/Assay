"""Isolated TraceFrame projections preserve lab identities and never publish."""

import importlib.util
import json
import os

import pytest
from phase3_support import CORRECT_SQL
from test_publication import setup, through_decision
from test_publication_recovery import race

from safety_lab.adapters import TraceFrameExportError, export_traceframe, read_traceframe_export
from safety_lab.contracts import canonical_json_bytes

REQUIRED = os.environ.get("SAFETY_LAB_TRACEFRAME_TESTS") == "1"
if importlib.util.find_spec("traceframe") is None:
    if REQUIRED:
        raise RuntimeError("SAFETY_LAB_TRACEFRAME_TESTS=1 requires the pinned traceframe extra")
    pytest.skip(
        "Install the pinned extra (uv sync --extra traceframe) to run adapter tests",
        allow_module_level=True,
    )

CASE_SQL = (
    "SELECT SUM(CASE WHEN o.status = 'settled' THEN o.amount_minor * 0.01 ELSE 0 END) "
    "AS revenue_usd FROM orders o WHERE o.currency = 'USD' "
    "AND o.occurred_at >= TIMESTAMPTZ '2026-01-01 00:00:00+00' "
    "AND o.occurred_at < TIMESTAMPTZ '2026-04-01 00:00:00+00'"
)


def published_audit(tmp_path, monkeypatch):
    lab, publisher, lease = setup(tmp_path, monkeypatch)
    report, _ = through_decision(lab, publisher, lease)
    publisher.publish(lease, report.revision_id)
    return lab, publisher, lease, report, publisher.audit_bundle(report.revision_id)


def test_published_audit_round_trips_identities_hashes_and_check_outcomes(tmp_path, monkeypatch):
    lab, publisher, _, report, audit = published_audit(tmp_path, monkeypatch)
    export = export_traceframe(audit, tmp_path / "exports" / "q1")
    loaded, companion = read_traceframe_export(export.root)
    assert canonical_json_bytes(companion) == canonical_json_bytes(audit)
    assert loaded.manifest == export.manifest
    kinds = sorted(item.lab_kind for item in export.manifest.identities)
    assert kinds.count("source") == 3 and kinds.count("snapshot") == 1
    assert kinds.count("execution") == 1 and kinds.count("result") == 1
    assert kinds.count("claim") == len(report.claims)
    assert kinds.count("check") == len(audit.checks.checks)
    claim = next(item for item in export.manifest.identities if item.lab_kind == "claim")
    assert claim.lab_id == report.claims[0].claim_id
    html = export.report_path.read_text(encoding="utf-8")
    assert "Researcher audit — not an end-user released report" in html
    assert "Recorded validity: <strong>current</strong>" in html
    assert publisher.read_current("report-q1").record == audit.release


def test_unknown_checks_stay_unknown_and_draft_status_is_explicit(tmp_path, monkeypatch):
    lab, publisher, lease = setup(tmp_path, monkeypatch)
    report, decision = through_decision(lab, publisher, lease, CASE_SQL)
    assert decision.outcome == "needs_review"
    audit = publisher.audit_bundle(report.revision_id)
    export = export_traceframe(audit, tmp_path / "draft")
    _, companion = read_traceframe_export(export.root)
    unknown = {check.check_id for check in companion.checks.checks if check.outcome == "unknown"}
    assert unknown
    native = json.loads((export.root / ".traceframe" / "checks.json").read_text(encoding="utf-8"))[
        "checks"
    ]
    native_ids = {item["details"]["check_id"] for item in native}
    assert native_ids.isdisjoint(unknown)
    assert companion.validity == "draft" and companion.release is None
    assert "Recorded validity: <strong>draft</strong>" in export.report_path.read_text("utf-8")


def test_identical_retry_reuses_export_and_conflicting_bundle_is_refused(tmp_path, monkeypatch):
    lab, publisher, lease, report, audit = published_audit(tmp_path, monkeypatch)
    destination = tmp_path / "exports" / "q1"
    first = export_traceframe(audit, destination)
    second = export_traceframe(audit, destination)
    assert second.manifest == first.manifest
    other, _ = through_decision(lab, publisher, lease)
    with pytest.raises(TraceFrameExportError, match="another audit bundle"):
        export_traceframe(publisher.audit_bundle(other.revision_id), destination)


@pytest.mark.parametrize("tamper", ["html", "companion", "extra_file", "evidence_record"])
def test_changed_or_unmanifested_export_files_are_detected(tmp_path, monkeypatch, tamper):
    *_, audit = published_audit(tmp_path, monkeypatch)
    export = export_traceframe(audit, tmp_path / "exports" / "q1")
    root = export.root
    if tamper == "html":
        export.report_path.write_text("<p>USD 999.00</p>", encoding="utf-8")
    elif tamper == "companion":
        path = root / "lab-records.json"
        path.write_bytes(path.read_bytes().replace(b"200.00", b"999.00"))
    elif tamper == "extra_file":
        (root / "released-report.txt").write_text("unapproved", encoding="utf-8")
    else:
        record = next((root / ".traceframe" / "audit_logs").glob("lab-claim-*.json"))
        record.write_bytes(record.read_bytes().replace(b"200.00", b"999.00"))
    with pytest.raises(TraceFrameExportError):
        read_traceframe_export(root)


def test_failed_or_invalid_export_leaves_publication_state_unchanged(tmp_path, monkeypatch):
    lab, publisher, _, report, audit = published_audit(tmp_path, monkeypatch)
    events_before = lab.evidence.get_events()
    with pytest.raises(TraceFrameExportError, match="timed out"):
        export_traceframe(audit, tmp_path / "slow", timeout_seconds=0.001)
    assert not (tmp_path / "slow").exists()
    forged = audit.model_copy(
        update={"report": audit.report.model_copy(update={"rendered_sha256": "0" * 64})}
    )
    with pytest.raises(TraceFrameExportError):
        export_traceframe(forged, tmp_path / "forged")
    assert not (tmp_path / "forged").exists()
    assert lab.evidence.get_events() == events_before
    assert publisher.read_current("report-q1").record == audit.release


def test_parallel_exports_use_separate_processes_and_traceframe_runs(tmp_path, monkeypatch):
    lab, publisher, lease, _, audit = published_audit(tmp_path, monkeypatch)
    draft = publisher.submit_report(
        lease,
        report_id="report-draft",
        source_key="sales-q1",
        task=lab.task,
        snapshot=lab.snapshot,
        claims=(lab.claim_input(lab.query(CORRECT_SQL)),),
    )
    second = publisher.audit_bundle(draft.revision_id)
    first_export, second_export = race(
        lambda: export_traceframe(audit, tmp_path / "parallel" / "a"),
        lambda: export_traceframe(second, tmp_path / "parallel" / "b"),
    )
    assert not isinstance(first_export, Exception), first_export
    assert not isinstance(second_export, Exception), second_export
    assert first_export.manifest.exporter_pid != second_export.manifest.exporter_pid
    assert first_export.manifest.traceframe_run_id != second_export.manifest.traceframe_run_id
    assert os.getpid() not in {
        first_export.manifest.exporter_pid,
        second_export.manifest.exporter_pid,
    }


def test_model_text_is_escaped_in_the_researcher_html(tmp_path, monkeypatch):
    lab, publisher, lease = setup(tmp_path, monkeypatch, variant="insufficient")
    outcome = lab.query(CORRECT_SQL)
    injected = "<script>alert('x')</script><img src=x onerror=alert(1)>"
    report = publisher.submit_report(
        lease,
        report_id="report-injected",
        source_key="sales-q1",
        task=lab.task,
        snapshot=lab.snapshot,
        claims=(lab.claim_input(outcome, abstention_reason=injected),),
    )
    export = export_traceframe(publisher.audit_bundle(report.revision_id), tmp_path / "x")
    html = export.report_path.read_text(encoding="utf-8")
    assert "<script>alert" not in html and "<img src=x" not in html
