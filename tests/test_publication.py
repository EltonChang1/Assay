"""One trusted release path: policy, fencing, epochs, invalidation, and history."""

import hashlib
import sqlite3

import pytest
from phase3_support import CORRECT_SQL, COUNT_SQL, DUPLICATED_SQL, SCOPE, digest, make_lab

from assay.contracts.report import CheckBundle
from assay.publication import (
    FencingError,
    InvalidTransitionError,
    PublicationError,
    Publisher,
    StaleReportError,
    StaleSourceError,
    evaluate_policy,
)
from evaluator.oracle import score_claims

SOURCE = "sales-q1"


def setup(tmp_path, monkeypatch, **kwargs):
    lab = make_lab(tmp_path, monkeypatch, **kwargs)
    publisher = Publisher(lab.evidence)
    publisher.register_source(SOURCE, lab.snapshot)
    lease = publisher.start_attempt(lab.run_id)
    return lab, publisher, lease


def submit(lab, publisher, lease, *claims, report_id="report-q1"):
    return publisher.submit_report(
        lease,
        report_id=report_id,
        source_key=SOURCE,
        task=lab.task,
        snapshot=lab.snapshot,
        claims=claims,
    )


def through_decision(lab, publisher, lease, sql=CORRECT_SQL, profile="checked", **claim_kw):
    report = submit(lab, publisher, lease, lab.claim_input(lab.query(sql), **claim_kw))
    publisher.check_report(lease, report.revision_id)
    return report, publisher.decide(lease, report.revision_id, profile)


def released_score(lab, publisher, release):
    audit = publisher.audit_bundle(release.record.report_revision_id)
    return score_claims(
        lab.task, lab.fixture.canonical_orders, tuple(item.claim for item in audit.report.claims)
    )


def test_correct_report_releases_exact_rendered_bytes_and_scores_correct(tmp_path, monkeypatch):
    lab, publisher, lease = setup(tmp_path, monkeypatch)
    revenue = lab.claim_input(lab.query(CORRECT_SQL))
    count = lab.claim_input(lab.query(COUNT_SQL), slot="settled_order_count", column="order_count")
    report = submit(lab, publisher, lease, revenue, count)
    assert publisher.read_current("report-q1") is None
    publisher.check_report(lease, report.revision_id)
    decision = publisher.decide(lease, report.revision_id, "checked")
    assert (decision.outcome, decision.reasons) == ("approved", ())
    record = publisher.publish(lease, report.revision_id)
    current = publisher.read_current("report-q1")
    assert current is not None and current.record == record and current.validity == "current"
    assert hashlib.sha256(current.content).hexdigest() == report.rendered_sha256
    assert b"Settled order revenue: USD 200.00\n" in current.content
    assert b"Settled order count: 3 orders\n" in current.content
    assert released_score(lab, publisher, current).correct
    assert publisher.publish(lease, report.revision_id) == record
    events = [event.event_type for event in lab.evidence.get_events()]
    assert events.count("report.published") == 1
    assert events.index("report.submitted") < events.index("report.checked")
    assert events.index("report.decided") < events.index("report.published")


def test_duplicated_join_is_rejected_by_checks_but_baseline_release_scores_incorrect(
    tmp_path, monkeypatch
):
    lab, publisher, lease = setup(tmp_path, monkeypatch)
    report, decision = through_decision(lab, publisher, lease, DUPLICATED_SQL)
    assert decision.outcome == "rejected"
    assert "fail:query_grain:settled_revenue_usd" in decision.reasons
    with pytest.raises(InvalidTransitionError):
        publisher.publish(lease, report.revision_id)
    assert publisher.read_current("report-q1") is None

    _, baseline = through_decision(lab, publisher, lease, DUPLICATED_SQL, "baseline")
    assert baseline.outcome == "approved"
    release = publisher.publish(lease, baseline.report_revision_id)
    released = publisher.read_release(release.release_id)
    assert b"USD 340.00" in released.content
    assert not released_score(lab, publisher, released).correct


def test_unknown_semantics_withhold_and_host_failures_reject_even_in_baseline(
    tmp_path, monkeypatch
):
    lab, publisher, lease = setup(tmp_path, monkeypatch)
    case_sql = (
        "SELECT SUM(CASE WHEN o.status = 'settled' THEN o.amount_minor * 0.01 ELSE 0 END) "
        "AS revenue_usd FROM orders o WHERE o.currency = 'USD' "
        "AND o.occurred_at >= TIMESTAMPTZ '2026-01-01 00:00:00+00' "
        "AND o.occurred_at < TIMESTAMPTZ '2026-04-01 00:00:00+00'"
    )
    report, decision = through_decision(lab, publisher, lease, case_sql)
    assert decision.outcome == "needs_review"
    assert all(reason.startswith("unknown:") for reason in decision.reasons)
    assert publisher.revision_status(report.revision_id) == "needs_review"
    with pytest.raises(InvalidTransitionError):
        publisher.publish(lease, report.revision_id)

    other = lab.query(CORRECT_SQL, run_id="run-other")
    report = submit(lab, publisher, lease, lab.claim_input(other))
    publisher.check_report(lease, report.revision_id)
    decision = publisher.decide(lease, report.revision_id, "baseline")
    assert decision.outcome == "rejected"
    assert "fail:evidence_identity:settled_revenue_usd" in decision.reasons


def test_policy_never_treats_missing_duplicated_or_rebound_checks_as_passing(tmp_path, monkeypatch):
    lab, publisher, lease = setup(tmp_path, monkeypatch)
    report = submit(lab, publisher, lease, lab.claim_input(lab.query(CORRECT_SQL)))
    bundle = publisher.check_report(lease, report.revision_id)
    assert evaluate_policy(report, bundle, "checked") == ("approved", ())
    grain = next(check for check in bundle.checks if check.name == "query_grain")
    missing = bundle.model_copy(
        update={"checks": tuple(check for check in bundle.checks if check is not grain)}
    )
    assert evaluate_policy(report, missing, "checked") == (
        "needs_review",
        ("coverage:query_grain:settled_revenue_usd",),
    )
    assert evaluate_policy(report, missing, "baseline") == ("approved", ())
    duplicated = bundle.model_copy(update={"checks": (*bundle.checks, grain)})
    assert evaluate_policy(report, duplicated, "checked")[0] == "needs_review"
    rebound = CheckBundle.model_validate(bundle.model_dump() | {"report_sha256": "0" * 64})
    assert evaluate_policy(report, rebound, "checked") == (
        "needs_review",
        ("check_bundle_binding",),
    )
    old_checker = bundle.model_copy(
        update={
            "checks": tuple(c.model_copy(update={"checker_version": "0"}) for c in bundle.checks)
        }
    )
    assert evaluate_policy(report, old_checker, "checked")[0] == "needs_review"


def test_delayed_approval_from_canceled_or_superseded_attempt_cannot_publish(tmp_path, monkeypatch):
    lab, publisher, first = setup(tmp_path, monkeypatch)
    report, decision = through_decision(lab, publisher, first)
    assert decision.outcome == "approved"
    publisher.cancel_attempt(first)
    with pytest.raises(FencingError):
        publisher.publish(first, report.revision_id)
    second = publisher.start_attempt(lab.run_id)
    assert second.fencing_token == first.fencing_token + 1
    with pytest.raises(FencingError):
        publisher.publish(second, report.revision_id)
    with pytest.raises(FencingError):
        publisher.publish(first, report.revision_id)
    assert publisher.read_current("report-q1") is None

    report, decision = through_decision(lab, publisher, second)
    third = publisher.start_attempt(lab.run_id)
    for lease in (second, third):
        with pytest.raises(FencingError):
            publisher.publish(lease, report.revision_id)
    with pytest.raises(FencingError):
        publisher.submit_report(
            second,
            report_id="report-q1",
            source_key=SOURCE,
            task=lab.task,
            snapshot=lab.snapshot,
            claims=(lab.claim_input(lab.query(CORRECT_SQL)),),
        )
    attempts = [e.event_type for e in lab.evidence.get_events() if e.event_type.startswith("att")]
    assert attempts == [
        "attempt.running",
        "attempt.canceled",
        "attempt.running",
        "attempt.revoked",
        "attempt.running",
    ]


def test_source_update_stales_current_release_but_keeps_its_history(tmp_path, monkeypatch):
    lab, publisher, lease = setup(tmp_path, monkeypatch)
    report, _ = through_decision(lab, publisher, lease)
    release = publisher.publish(lease, report.revision_id)
    original = publisher.read_release(release.release_id)
    updated = make_lab(tmp_path / "update", monkeypatch, variant="equal_amount")
    assert publisher.register_source(SOURCE, updated.snapshot) == 2
    assert publisher.register_source(SOURCE, updated.snapshot) == 2
    assert publisher.read_current("report-q1") is None
    with pytest.raises(StaleReportError):
        publisher.read_release(release.release_id)
    archived = publisher.read_release(release.release_id, archival=True)
    assert archived.validity == "stale"
    assert (archived.record, archived.content) == (original.record, original.content)
    assert publisher.audit_bundle(report.revision_id).validity == "stale"
    stale = [event for event in lab.evidence.get_events() if event.event_type == "release.stale"]
    assert len(stale) == 1
    assert released_score(lab, publisher, archived).correct


def test_historical_release_survives_source_update(tmp_path, monkeypatch):
    lab = make_lab(tmp_path, monkeypatch, variant="historical")
    publisher = Publisher(lab.evidence)
    publisher.register_source(SOURCE, lab.snapshot)
    lease = publisher.start_attempt(lab.run_id)
    current = make_lab(tmp_path / "current", monkeypatch)
    publisher.register_source(SOURCE, current.snapshot)
    report, decision = through_decision(lab, publisher, lease)
    assert decision.outcome == "approved"
    release = publisher.publish(lease, report.revision_id)
    publisher.register_source(SOURCE, make_lab(tmp_path / "later", monkeypatch, seed=7).snapshot)
    loaded = publisher.read_current("report-q1")
    assert loaded is not None and loaded.record == release and loaded.validity == "historical"
    assert b"Data basis: historical snapshot\n" in loaded.content
    assert b"USD 190.00" in loaded.content


def test_source_change_before_approval_or_publication_releases_nothing(tmp_path, monkeypatch):
    lab, publisher, lease = setup(tmp_path, monkeypatch)
    approved, decision = through_decision(lab, publisher, lease)
    checked_only = submit(lab, publisher, lease, lab.claim_input(lab.query(CORRECT_SQL)))
    publisher.check_report(lease, checked_only.revision_id)
    publisher.register_source(SOURCE, make_lab(tmp_path / "u", monkeypatch, seed=3).snapshot)
    assert publisher.revision_status(approved.revision_id) == "stale"
    assert publisher.revision_status(checked_only.revision_id) == "stale"
    with pytest.raises(InvalidTransitionError):
        publisher.publish(lease, approved.revision_id)
    with pytest.raises(InvalidTransitionError):
        publisher.decide(lease, checked_only.revision_id, "checked")
    with pytest.raises(StaleSourceError):
        submit(lab, publisher, lease, lab.claim_input(lab.query(CORRECT_SQL)))
    with pytest.raises(PublicationError, match="not registered"):
        publisher.submit_report(
            lease,
            report_id="r",
            source_key="unregistered",
            task=lab.task,
            snapshot=lab.snapshot,
            claims=(lab.claim_input(lab.query(CORRECT_SQL)),),
        )
    assert publisher.read_current("report-q1") is None


def test_changed_report_or_rendered_bytes_after_review_cannot_publish(tmp_path, monkeypatch):
    lab, publisher, lease = setup(tmp_path, monkeypatch)
    report, _ = through_decision(lab, publisher, lease)
    with sqlite3.connect(lab.evidence.database_path) as connection:
        rendered = connection.execute(
            "SELECT rendered_sha256 FROM report_revisions WHERE revision_id = ?",
            (report.revision_id,),
        ).fetchone()[0]
        connection.execute(
            "UPDATE artifacts SET content = ? WHERE sha256 = ?", (b"USD 999.00\n", rendered)
        )
    with pytest.raises(ValueError, match="content hash changed"):
        publisher.publish(lease, report.revision_id)
    assert publisher.revision_status(report.revision_id) == "approved"
    assert publisher.read_current("report-q1") is None


def test_unlisted_or_contradictory_claims_are_refused_at_submission(tmp_path, monkeypatch):
    lab, publisher, lease = setup(tmp_path, monkeypatch)
    outcome = lab.query(CORRECT_SQL)
    for claims in (
        (lab.claim_input(outcome), lab.claim_input(outcome, "340.00")),
        (lab.claim_input(outcome, grain="line_item"),),
        (lab.claim_input(lab.query(COUNT_SQL), slot="settled_order_count", column="order_count"),),
    ):
        with pytest.raises(ValueError):
            submit(lab, publisher, lease, *claims)
    with sqlite3.connect(lab.evidence.database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM report_revisions").fetchone()[0] == 0


def test_lifecycle_steps_cannot_be_skipped_or_repeated(tmp_path, monkeypatch):
    lab, publisher, lease = setup(tmp_path, monkeypatch)
    report = submit(lab, publisher, lease, lab.claim_input(lab.query(CORRECT_SQL)))
    for step in (
        lambda: publisher.decide(lease, report.revision_id, "checked"),
        lambda: publisher.publish(lease, report.revision_id),
    ):
        with pytest.raises(InvalidTransitionError):
            step()
    publisher.check_report(lease, report.revision_id)
    with pytest.raises(InvalidTransitionError):
        publisher.check_report(lease, report.revision_id)
    with pytest.raises(KeyError):
        publisher.publish(lease, "revision-unknown")
    second = submit(lab, publisher, lease, lab.claim_input(lab.query(CORRECT_SQL)))
    assert (report.revision, second.revision) == (1, 2)
    with pytest.raises(KeyError):
        publisher.read_release("../releases/anything")


def test_newer_revision_supersedes_latest_index_but_older_retry_does_not(tmp_path, monkeypatch):
    lab, publisher, lease = setup(tmp_path, monkeypatch)
    first, _ = through_decision(lab, publisher, lease)
    second, _ = through_decision(lab, publisher, lease)
    newer = publisher.publish(lease, second.revision_id)
    older = publisher.publish(lease, first.revision_id)
    current = publisher.read_current("report-q1")
    assert current is not None and current.record == newer
    assert publisher.read_release(older.release_id).validity == "current"


def test_audit_bundle_binds_checks_approval_release_and_edges(tmp_path, monkeypatch):
    lab, publisher, lease = setup(tmp_path, monkeypatch)
    report, _ = through_decision(lab, publisher, lease)
    publisher.publish(lease, report.revision_id)
    audit = publisher.audit_bundle(report.revision_id, ("Development fixture only.",))
    assert audit.report == report and audit.validity == "current"
    assert audit.checks is not None and audit.approval is not None and audit.release is not None
    assert audit.approval.check_bundle_sha256 == digest(audit.checks)
    assert [item.receipt.execution_id for item in audit.executions] == list(report.execution_ids)
    children = {child for _, child in audit.dependency_edges}
    assert len(children) >= 4
    assert SCOPE in audit.executions[0].receipt.exact_query
