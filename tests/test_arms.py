"""Arms A–E over one analyst interface, and the bounded correction round."""

import json

import pytest
from phase3_support import CORRECT_SQL, DUPLICATED_SQL, make_lab
from test_episodes import call, submit_from_last
from test_review import decide, view_of

from evaluator.oracle import score_claims
from assay.agents import (
    CORRECTION_PROMPT,
    EpisodeLimits,
    ScriptedModel,
    run_analyst_episode,
    run_arm_episode,
)
from assay.contracts.episode import EpisodeRecord, EpisodeTranscript, Message, ToolCall
from assay.contracts.policy import ARMS
from assay.publication import Publisher
from assay.review import ReviewConfig

SOURCE = "sales-q1"
GRAIN_FAILURE = "fail:query_grain:settled_revenue_usd"


def arm_episode(tmp_path, monkeypatch, arm, steps, *, reviewer_steps=None, limits=None):
    lab = make_lab(tmp_path, monkeypatch)
    publisher = Publisher(lab.evidence)
    publisher.register_source(SOURCE, lab.snapshot)
    view = ARMS[arm][1]
    reviewer = summarizer = None
    if view is not None:
        reviewer = ScriptedModel(reviewer_steps or [decide(), decide()], model_id="scripted/rev")
    if view == "ordinary":
        summary = Message(role="assistant", content="Ran SQL and reported a USD total.")
        summarizer = ScriptedModel([summary, summary], model_id="scripted/summarizer")
    model = ScriptedModel(steps)
    record = run_arm_episode(
        model,
        arm,
        publisher=publisher,
        state=lab.state,
        bundle=lab.source,
        source_key=SOURCE,
        run_id="run-arm",
        report_id="report-arm",
        reviewer=reviewer,
        summarizer=summarizer,
        limits=limits,
    )
    return lab, publisher, model, reviewer, record


def transcript(lab, record):
    return lab.evidence.get_model(record.transcript_sha256, EpisodeTranscript).messages


def feedback_messages(messages):
    return [m for m in messages if m.role == "user" and m.content.startswith(CORRECTION_PROMPT)]


def feedback_of(message):
    return json.loads(message.content.split("Feedback (JSON):\n", 1)[1])


def assert_every_tool_call_answered(messages):
    answered = {m.tool_call_id for m in messages if m.role == "tool"}
    assert {c.call_id for m in messages for c in m.tool_calls} <= answered


def corrected(first_sql=DUPLICATED_SQL, second_sql=CORRECT_SQL):
    return [
        call("execute_sql", sql=first_sql),
        submit_from_last(),
        call("execute_sql", "call-fix", sql=second_sql),
        submit_from_last(),
    ]


def test_arm_table_matches_the_plan():
    assert dict(ARMS) == {
        "A": ("baseline", None),
        "B": ("checked", None),
        "C": ("reviewed", "ordinary"),
        "D": ("checked_reviewed", "ordinary"),
        "E": ("checked_reviewed", "evidence"),
    }


def test_arms_share_the_analyst_interface_and_differ_only_in_oversight(tmp_path, monkeypatch):
    expected = {"A": "released", "B": "withheld", "C": "released", "D": "withheld", "E": "withheld"}
    first_requests = {}
    for arm, status in expected.items():
        lab, publisher, model, reviewer, record = arm_episode(
            tmp_path / arm,
            monkeypatch,
            arm,
            [call("execute_sql", sql=DUPLICATED_SQL), submit_from_last()],
            limits=EpisodeLimits(max_corrections=0),
        )
        assert (record.arm, record.policy_profile, record.status) == (arm, ARMS[arm][0], status)
        assert record.review_view == ARMS[arm][1]
        messages, tools = model.requests[0]
        first_requests[arm] = ([(m.role, m.content) for m in messages], tools)
        if status == "released":
            claim = publisher.audit_bundle(record.revision_id).report.claims[0].claim
            assert not score_claims(lab.task, lab.fixture.canonical_orders, (claim,)).correct
        else:
            assert GRAIN_FAILURE in record.decision_reasons
        if reviewer is not None:
            view = view_of(reviewer.requests[0][0])
            assert view["kind"] == ARMS[arm][1]
            assert (view.get("checks") is None) == (arm == "C")
    assert all(request == first_requests["A"] for request in first_requests.values())


def test_checked_rejection_earns_one_correction_that_releases_a_new_revision(tmp_path, monkeypatch):
    lab, publisher, model, _, record = arm_episode(tmp_path, monkeypatch, "B", corrected())
    assert (record.status, record.decision_outcome) == ("released", "approved")
    assert (record.correction_rounds, record.correction_status) == (1, "resubmitted")
    first, final = record.revision_ids
    assert final == record.revision_id
    assert publisher.revision_status(first) == "rejected"
    assert publisher.revision_status(final) == "published"
    assert b"USD 200.00" in publisher.read_current("report-arm").content
    assert publisher.audit_bundle(first).report.revision == 1
    assert (record.model_calls, record.tool_calls, len(record.execution_ids)) == (4, 4, 2)
    messages = transcript(lab, record)
    [message] = feedback_messages(messages)
    assert feedback_of(message) == {
        "format": "correction-feedback-1.0",
        "max_rounds": 1,
        "outcome": "rejected",
        "reasons": [GRAIN_FAILURE],
        "reviewer_reason_codes": [],
        "revision_id": first,
        "round": 1,
        "schema_version": "1.0",
    }
    assert_every_tool_call_answered(messages)
    assert model.requests[2][0][-1] == message


def test_review_only_feedback_carries_reviewer_codes_but_no_check_outcomes(tmp_path, monkeypatch):
    reviewer_steps = [decide("reject", ("wrong_grain",)), decide()]
    lab, publisher, _, reviewer, record = arm_episode(
        tmp_path, monkeypatch, "C", corrected(), reviewer_steps=reviewer_steps
    )
    assert record.status == "released" and record.correction_status == "resubmitted"
    [message] = feedback_messages(transcript(lab, record))
    feedback = feedback_of(message)
    assert feedback["reasons"] == ["review:reject"]
    assert feedback["reviewer_reason_codes"] == ["wrong_grain"]
    assert "query_grain" not in message.content
    assert len(record.review_ids) == 2 and record.review_id == record.review_ids[-1]
    assert record.oversight_model_calls == 4 and record.oversight_input_tokens == 400
    claim = publisher.audit_bundle(record.revision_id).report.claims[0].claim
    assert score_claims(lab.task, lab.fixture.canonical_orders, (claim,)).correct


def test_evidence_review_after_repair_is_counted_and_bound_per_revision(tmp_path, monkeypatch):
    lab, publisher, _, reviewer, record = arm_episode(tmp_path, monkeypatch, "E", corrected())
    assert record.status == "released" and record.review_view == "evidence"
    assert record.oversight_model_calls == 2 and len(record.review_ids) == 2
    first, final = record.revision_ids
    assert publisher.audit_bundle(first).review.review_id == record.review_ids[0]
    assert publisher.audit_bundle(final).review.review_id == record.review_ids[1]
    assert GRAIN_FAILURE in view_of(reviewer.requests[0][0])["unresolved"]
    assert view_of(reviewer.requests[1][0])["unresolved"] == []
    feedback = feedback_of(feedback_messages(transcript(lab, record))[0])
    assert feedback["reasons"] == [GRAIN_FAILURE]
    assert feedback["reviewer_reason_codes"] == ["supported"]


def test_correction_is_limited_to_one_round(tmp_path, monkeypatch):
    lab, publisher, model, _, record = arm_episode(
        tmp_path, monkeypatch, "B", corrected(second_sql=DUPLICATED_SQL)
    )
    assert (record.status, record.decision_outcome) == ("withheld", "rejected")
    assert (record.correction_rounds, record.correction_status) == (1, "resubmitted")
    assert len(record.revision_ids) == 2 and len(feedback_messages(transcript(lab, record))) == 1
    assert len(model.requests) == 4 and publisher.read_current("report-arm") is None

    _, _, model, _, record = arm_episode(
        tmp_path / "disabled",
        monkeypatch,
        "B",
        corrected(),
        limits=EpisodeLimits(max_corrections=0),
    )
    assert record.status == "withheld" and len(model.requests) == 2
    assert (record.correction_rounds, record.correction_status) == (0, None)
    with pytest.raises(ValueError, match="at most one correction"):
        EpisodeLimits(max_corrections=2)


@pytest.mark.parametrize(
    ("ending", "correction_status", "error_category"),
    [
        (Message(role="assistant", content="No changes."), "no_submission", None),
        (TimeoutError("provider detail"), "model_error", "TimeoutError"),
    ],
    ids=["no_submission", "model_error"],
)
def test_an_unfinished_correction_round_keeps_the_first_decision(
    tmp_path, monkeypatch, ending, correction_status, error_category
):
    steps = [call("execute_sql", sql=DUPLICATED_SQL), submit_from_last(), ending]
    _, _, _, _, record = arm_episode(tmp_path, monkeypatch, "B", steps)
    assert (record.status, record.decision_outcome) == ("withheld", "rejected")
    assert GRAIN_FAILURE in record.decision_reasons and len(record.revision_ids) == 1
    assert (record.correction_status, record.error_category) == (correction_status, error_category)


def test_the_correction_round_spends_the_same_episode_budget(tmp_path, monkeypatch):
    _, _, _, _, record = arm_episode(
        tmp_path, monkeypatch, "B", corrected(), limits=EpisodeLimits(max_tool_calls=3)
    )
    assert (record.status, record.correction_status) == ("withheld", "tool_limit")
    assert record.tool_calls == 3 and len(record.revision_ids) == 1


def test_calls_after_a_submission_in_the_same_turn_are_answered_but_not_run(tmp_path, monkeypatch):
    def submit_then_list(messages):
        submission = submit_from_last()(messages)
        extra = ToolCall(call_id="call-extra", name="list_tables")
        return submission.model_copy(update={"tool_calls": (*submission.tool_calls, extra)})

    steps = [call("execute_sql", sql=CORRECT_SQL), submit_then_list]
    lab, _, _, _, record = arm_episode(tmp_path, monkeypatch, "B", steps)
    assert record.status == "released" and record.tool_calls == 2
    messages = transcript(lab, record)
    assert json.loads(messages[-1].content) == {"error": "not_run", "status": "error"}
    assert_every_tool_call_answered(messages)


def test_arm_configuration_errors_raise_before_any_model_call(tmp_path, monkeypatch):
    lab = make_lab(tmp_path, monkeypatch)
    publisher = Publisher(lab.evidence)
    publisher.register_source(SOURCE, lab.snapshot)
    model, other = ScriptedModel([call("list_tables")]), ScriptedModel([])
    common = dict(
        publisher=publisher,
        state=lab.state,
        bundle=lab.source,
        source_key=SOURCE,
        run_id="run-config",
        report_id="report-config",
    )
    for arm, models, message in (
        ("A", {"reviewer": other}, "no reviewer"),
        ("B", {"summarizer": other}, "no reviewer"),
        ("C", {"reviewer": other}, "summarizer"),
        ("D", {"summarizer": other}, "requires a reviewer"),
        ("E", {"reviewer": other, "summarizer": other}, "without a summarizer"),
    ):
        with pytest.raises(ValueError, match=message):
            run_arm_episode(model, arm, **common, **models)
    ordinary = ReviewConfig(reviewer=other, view="ordinary", summarizer=other)
    with pytest.raises(ValueError, match="arm E"):
        run_analyst_episode(
            model, policy_profile="checked_reviewed", review=ordinary, arm="E", **common
        )
    with pytest.raises(ValueError, match="arm B"):
        run_analyst_episode(model, policy_profile="baseline", arm="B", **common)
    assert model.requests == [] and other.requests == []


def test_episode_records_reject_incoherent_arm_and_correction_fields(tmp_path, monkeypatch):
    _, _, _, _, record = arm_episode(tmp_path, monkeypatch, "B", corrected())
    base = record.model_dump()
    for change in (
        {"arm": "A"},
        {"arm": "E", "policy_profile": "checked_reviewed", "review_view": "ordinary"},
        {"correction_status": None},
        {"correction_rounds": 0},
        {"revision_ids": (record.revision_ids[0],)},
        {"revision_ids": (*record.revision_ids, "revision-extra")},
        {"error_category": "TimeoutError"},
        {"review_ids": ("review-other",)},
    ):
        with pytest.raises(ValueError):
            EpisodeRecord.model_validate(base | change)
    unfinished = base | {"correction_status": "model_error", "error_category": "TimeoutError"}
    unfinished |= {"status": "withheld", "release_id": None, "decision_outcome": "rejected"}
    unfinished |= {"revision_ids": (record.revision_ids[0],), "revision_id": record.revision_ids[0]}
    assert EpisodeRecord.model_validate(unfinished).correction_status == "model_error"
