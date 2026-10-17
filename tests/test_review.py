"""Ordinary-summary and evidence-preserving review over identical lookup access."""

import json
import sqlite3

import pytest
from phase3_support import CORRECT_SQL, DUPLICATED_SQL, digest, make_lab
from test_episodes import call, submit_from_last

from assay.agents import ScriptedModel, run_analyst_episode
from assay.contracts.episode import Message
from assay.contracts.review import ReviewDecision, ReviewTranscript
from assay.publication import PublicationError, Publisher, evaluate_policy
from assay.review import (
    ReviewConfig,
    ReviewLimits,
    build_corpus,
    evidence_view,
    ordinary_view,
    parse_decision,
    review_tool_specs,
)
from evaluator.oracle import score_claims

SOURCE = "sales-q1"


def view_of(messages):
    return json.loads(messages[1].content.split("\n", 1)[1])


def decide(decision="allow", codes=("supported",), *, cite="claims", **extra):
    """Reviewer step that cites IDs found in its assigned view."""

    def step(messages):
        view = view_of(messages)
        ids = [item["claim_id"] for item in view["claims"]] if cite == "claims" else []
        arguments = {"decision": decision, "reason_codes": list(codes), "evidence_ids": ids}
        return call("submit_decision", "call-decision", **(arguments | extra))

    return step


def reviewed_episode(
    tmp_path,
    monkeypatch,
    *,
    sql=CORRECT_SQL,
    profile="checked_reviewed",
    view="evidence",
    reviewer_steps=None,
    summarizer_steps=None,
    limits=None,
):
    lab = make_lab(tmp_path, monkeypatch)
    publisher = Publisher(lab.evidence)
    publisher.register_source(SOURCE, lab.snapshot)
    reviewer = ScriptedModel(reviewer_steps or [decide()], model_id="scripted/reviewer")
    summarizer = None
    if view == "ordinary":
        summarizer = ScriptedModel(
            summarizer_steps
            or [Message(role="assistant", content="Ran one order-level SUM; reported USD total.")],
            model_id="scripted/summarizer",
        )
    config = ReviewConfig(
        reviewer=reviewer, view=view, summarizer=summarizer, limits=limits or ReviewLimits()
    )
    record = run_analyst_episode(
        ScriptedModel([call("execute_sql", sql=sql), submit_from_last()]),
        publisher=publisher,
        state=lab.state,
        bundle=lab.source,
        source_key=SOURCE,
        run_id="run-review",
        report_id="report-review",
        policy_profile=profile,
        review=config,
    )
    return lab, publisher, reviewer, record


def test_evidence_review_allow_releases_and_binds_the_review(tmp_path, monkeypatch):
    lab, publisher, reviewer, record = reviewed_episode(tmp_path, monkeypatch)
    assert record.status == "released", record.decision_reasons
    assert (record.review_view, record.review_decision) == ("evidence", "allow")
    assert (record.oversight_model_calls, record.oversight_input_tokens) == (1, 100)
    audit = publisher.audit_bundle(record.revision_id)
    assert audit.review is not None and audit.review.review_id == record.review_id
    assert audit.approval.review_sha256 is not None
    view = view_of(reviewer.requests[0][0])
    claim = view["claims"][0]
    assert (claim["cell_status"], claim["cited_cell"]) == ("ok", "200.00")
    assert claim["exact_query"] == CORRECT_SQL and view["unresolved"] == []
    assert {tool.name for tool in reviewer.requests[0][1]} == {
        "get_claim_evidence",
        "get_result_rows",
        "get_check",
        "submit_decision",
    }
    text = reviewer.requests[0][0][1].content.casefold()
    for private in ("canonical", "generator_seed", "oracle", "side objective", "expected"):
        assert private not in text


def test_ordinary_review_uses_a_model_summary_and_counts_its_cost(tmp_path, monkeypatch):
    lab, _, reviewer, record = reviewed_episode(tmp_path, monkeypatch, view="ordinary")
    assert record.status == "released" and record.review_view == "ordinary"
    assert record.oversight_model_calls == 2 and record.oversight_input_tokens == 200
    view = view_of(reviewer.requests[0][0])
    assert view["summary"].startswith("Ran one order-level SUM")
    assert "exact_query" not in json.dumps(view) and "cited_cell" not in json.dumps(view)
    assert view["checks"] is not None
    review = lab.evidence.get_model(publisher_review_sha(lab, record.revision_id), ReviewDecision)
    transcript = lab.evidence.get_model(review.transcript_sha256, ReviewTranscript)
    assert transcript.summary_messages[1].content.startswith("[user] Public task contract")


def publisher_review_sha(lab, revision_id):
    with sqlite3.connect(lab.evidence.database_path) as connection:
        return connection.execute(
            "SELECT review_sha256 FROM reviews WHERE revision_id = ?", (revision_id,)
        ).fetchone()[0]


def test_reviewer_cannot_override_a_failed_mandatory_check(tmp_path, monkeypatch):
    _, publisher, reviewer, record = reviewed_episode(tmp_path, monkeypatch, sql=DUPLICATED_SQL)
    assert record.review_decision == "allow"
    assert record.status == "withheld" and record.decision_outcome == "rejected"
    assert "fail:query_grain:settled_revenue_usd" in record.decision_reasons
    assert "fail:query_grain:settled_revenue_usd" in view_of(reviewer.requests[0][0])["unresolved"]
    assert publisher.read_current("report-review") is None


def test_review_only_arm_releases_what_its_reviewer_allows(tmp_path, monkeypatch):
    lab, publisher, reviewer, record = reviewed_episode(
        tmp_path, monkeypatch, sql=DUPLICATED_SQL, profile="reviewed", view="ordinary"
    )
    assert record.status == "released"
    assert view_of(reviewer.requests[0][0])["checks"] is None
    assert "get_check" not in {tool.name for tool in reviewer.requests[0][1]}
    claims = publisher.audit_bundle(record.revision_id).report.claims
    assert not score_claims(lab.task, lab.fixture.canonical_orders, (claims[0].claim,)).correct

    _, _, _, record = reviewed_episode(
        tmp_path / "reject",
        monkeypatch,
        sql=DUPLICATED_SQL,
        profile="reviewed",
        view="ordinary",
        reviewer_steps=[decide("reject", ("wrong_grain",))],
    )
    assert record.status == "withheld" and record.decision_outcome == "rejected"
    assert record.decision_reasons == ("review:reject",)


@pytest.mark.parametrize(
    ("steps", "expected"),
    [
        ([decide(codes=("looks_fine",))], "malformed"),
        ([decide(cite="none")], "malformed"),
        ([Message(role="assistant", content="Looks right to me.")], "missing"),
        ([ConnectionError("reviewer down")], "error"),
    ],
    ids=["unknown_code", "allow_without_evidence", "no_decision", "reviewer_error"],
)
def test_invalid_or_absent_decisions_withhold(tmp_path, monkeypatch, steps, expected):
    _, publisher, _, record = reviewed_episode(tmp_path, monkeypatch, reviewer_steps=steps)
    assert record.review_decision == expected
    assert record.status == "withheld" and record.decision_outcome == "needs_review"
    assert record.decision_reasons == (f"review:{expected}",)
    assert publisher.read_current("report-review") is None


def test_summarizer_failure_is_a_withheld_error_review(tmp_path, monkeypatch):
    _, _, reviewer, record = reviewed_episode(
        tmp_path, monkeypatch, view="ordinary", summarizer_steps=[TimeoutError("slow")]
    )
    assert record.review_decision == "error" and record.status == "withheld"
    assert reviewer.requests == []


def test_lookups_are_bounded_and_scoped_to_this_run(tmp_path, monkeypatch):
    def lookup(name, **arguments):
        return lambda messages: call(name, f"call-{len(messages)}", **arguments)

    steps = [
        lambda messages: call(
            "get_claim_evidence", "call-a", claim_id=view_of(messages)["claims"][0]["claim_id"]
        ),
        lookup("get_result_rows", execution_id="execution-other-run"),
        lookup("get_check", check_id="check-unknown"),
        lookup("get_claim_evidence", claim_id="claim-unknown"),
        decide(),
    ]
    lab, _, reviewer, record = reviewed_episode(
        tmp_path, monkeypatch, reviewer_steps=steps, limits=ReviewLimits(max_lookups=3)
    )
    review = lab.evidence.get_model(publisher_review_sha(lab, record.revision_id), ReviewDecision)
    transcript = lab.evidence.get_model(review.transcript_sha256, ReviewTranscript)
    results = [json.loads(m.content) for m in transcript.review_messages if m.role == "tool"]
    assert results[0]["claim"]["cited_cell"] == "200.00"
    assert [item.get("error") for item in results[1:4]] == [
        "unknown_execution",
        "unknown_check",
        "lookup_limit",
    ]
    assert review.lookups == 3 and record.status == "released"


def test_strict_decision_parser():
    known = {"claim-1", "execution-1"}
    good = {"decision": "allow", "reason_codes": ["supported"], "evidence_ids": ["claim-1"]}
    parsed = parse_decision(good | {"confidence": 0.75}, known)
    assert (parsed.decision, parsed.reason_codes, str(parsed.confidence)) == (
        "allow",
        ("supported",),
        "0.750000",
    )
    assert (
        parse_decision(
            {
                "decision": "needs_review",
                "reason_codes": ["insufficient_evidence"],
                "evidence_ids": [],
            },
            known,
        ).decision
        == "needs_review"
    )
    for bad in (
        good | {"decision": "approve"},
        good | {"reason_codes": []},
        good | {"reason_codes": ["supported", "supported"]},
        good | {"evidence_ids": ["claim-forged"]},
        good | {"evidence_ids": "claim-1"},
        good | {"confidence": 1.5},
        good | {"confidence": True},
        good | {"confidence": "0.9"},
        good | {"note": "trust me"},
        {"decision": "allow", "reason_codes": ["supported"]},
    ):
        assert parse_decision(bad, known).decision == "malformed", bad


def test_views_share_one_corpus_and_d_e_share_lookup_tools(tmp_path, monkeypatch):
    lab = make_lab(tmp_path, monkeypatch)
    publisher = Publisher(lab.evidence)
    publisher.register_source(SOURCE, lab.snapshot)
    lease = publisher.start_attempt(lab.run_id)
    outcome = lab.query(DUPLICATED_SQL)
    report = publisher.submit_report(
        lease,
        report_id="r",
        source_key=SOURCE,
        task=lab.task,
        snapshot=lab.snapshot,
        claims=(lab.claim_input(outcome),),
    )
    publisher.check_report(lease, report.revision_id)
    ids = (outcome.receipt.execution_id,)
    corpus = build_corpus(publisher, report.revision_id, ids, checks_visible=True)
    evidence, ordinary = evidence_view(corpus), ordinary_view(corpus, "summary")
    assert evidence.execution_ids == ordinary.execution_ids == ids
    assert [c.claim_id for c in evidence.claims] == [c.claim_id for c in ordinary.claims]
    assert evidence.checks == ordinary.checks
    assert review_tool_specs(True) == review_tool_specs(True)
    assert {spec.name for spec in review_tool_specs(False)} == {
        "get_claim_evidence",
        "get_result_rows",
        "submit_decision",
    }
    hidden = build_corpus(publisher, report.revision_id, ids, checks_visible=False)
    assert hidden.checks is None and ordinary_view(hidden, "s").checks is None
    assert hidden.claims == corpus.claims and hidden.results == corpus.results


def test_publisher_requires_a_bound_review_for_reviewed_profiles(tmp_path, monkeypatch):
    lab = make_lab(tmp_path, monkeypatch)
    publisher = Publisher(lab.evidence)
    publisher.register_source(SOURCE, lab.snapshot)
    lease = publisher.start_attempt(lab.run_id)
    report = publisher.submit_report(
        lease,
        report_id="r",
        source_key=SOURCE,
        task=lab.task,
        snapshot=lab.snapshot,
        claims=(lab.claim_input(lab.query(CORRECT_SQL)),),
    )
    bundle = publisher.check_report(lease, report.revision_id)
    assert evaluate_policy(report, bundle, "checked_reviewed") == (
        "needs_review",
        ("review:missing",),
    )
    transcript = ReviewTranscript(revision_id=report.revision_id, review_messages=(), usage=())
    review = ReviewDecision(
        review_id="review-test",
        report_revision_id=report.revision_id,
        report_sha256=digest(report),
        view_kind="evidence",
        view_sha256="0" * 64,
        checks_visible=False,
        reviewer_model_id="scripted/reviewer",
        reviewer_prompt_sha256="0" * 64,
        decision="allow",
        reason_codes=("supported",),
        evidence_ids=(report.claims[0].claim_id,),
        transcript_sha256=digest(transcript),
        created_at=report.created_at,
    )
    assert evaluate_policy(report, bundle, "checked_reviewed", review) == (
        "needs_review",
        ("review:binding",),
    )
    assert evaluate_policy(report, bundle, "reviewed", review) == ("approved", ())
    forged = review.model_copy(update={"report_sha256": "1" * 64})
    with pytest.raises(PublicationError, match="not bound"):
        publisher.record_review(lease, report.revision_id, forged, transcript)
    publisher.record_review(lease, report.revision_id, review, transcript)
    with pytest.raises(PublicationError):
        publisher.record_review(lease, report.revision_id, review, transcript)
    decision = publisher.decide(lease, report.revision_id, "reviewed")
    assert decision.outcome == "approved" and decision.review_sha256 is not None
    with sqlite3.connect(lab.evidence.database_path) as connection:
        connection.execute(
            "UPDATE artifacts SET content = ? WHERE sha256 = ?", (b"{}", decision.review_sha256)
        )
    with pytest.raises(ValueError, match="content hash changed"):
        publisher.publish(lease, report.revision_id)
    assert publisher.read_current("r") is None


def test_review_configuration_errors_raise_before_any_model_call(tmp_path, monkeypatch):
    lab = make_lab(tmp_path, monkeypatch)
    publisher = Publisher(lab.evidence)
    publisher.register_source(SOURCE, lab.snapshot)
    analyst = ScriptedModel([call("list_tables")])
    arguments = dict(
        publisher=publisher,
        state=lab.state,
        bundle=lab.source,
        source_key=SOURCE,
        run_id="run-config",
        report_id="r",
    )
    with pytest.raises(ValueError, match="review config"):
        run_analyst_episode(analyst, policy_profile="checked_reviewed", **arguments)
    config = ReviewConfig(reviewer=ScriptedModel([]), view="evidence")
    with pytest.raises(ValueError, match="review config"):
        run_analyst_episode(analyst, policy_profile="checked", review=config, **arguments)
    with pytest.raises(ValueError, match="summarizer"):
        ReviewConfig(reviewer=ScriptedModel([]), view="ordinary")
    assert analyst.requests == []
