"""Offline analyst episodes with a scripted model through real host tools."""

import json

import pytest
from phase3_support import CORRECT_SQL, DUPLICATED_SQL, make_lab

from evaluator.oracle import score_claims
from safety_lab.agents import (
    PROMPT_SHA256,
    TOOL_SPECS,
    EpisodeLimits,
    ScriptedModel,
    run_analyst_episode,
)
from safety_lab.contracts.episode import EpisodeRecord, EpisodeTranscript, Message, ToolCall
from safety_lab.execution.docker import WorkerUnavailableError
from safety_lab.gateway import service
from safety_lab.publication import Publisher

SOURCE = "sales-q1"


def call(name, call_id="call-1", content="", **arguments):
    return Message(
        role="assistant",
        content=content,
        tool_calls=(ToolCall(call_id=call_id, name=name, arguments=arguments),),
    )


def last_tool(messages):
    return json.loads(messages[-1].content)


def submit_from_last(*, value=None, abstain=None, slot="settled_revenue_usd", **extra):
    def step(messages):
        result = last_tool(messages)
        claim = {"slot_id": slot, "execution_id": result["execution_id"]}
        if abstain:
            claim["abstention_reason"] = abstain
        else:
            claim |= {
                "value": value if value is not None else str(result["rows"][0][0]),
                "row_index": 0,
                "column": result["columns"][0]["name"],
            }
        return call("submit_claims", "call-submit", claims=[claim | extra], **{})

    return step


def episode(tmp_path, monkeypatch, steps, *, variant="base", profile="checked", **kwargs):
    lab = make_lab(tmp_path, monkeypatch, variant=variant)
    publisher = Publisher(lab.evidence)
    publisher.register_source(SOURCE, lab.snapshot)
    model = ScriptedModel(steps)
    record = run_analyst_episode(
        model,
        publisher=publisher,
        state=lab.state,
        bundle=lab.source,
        source_key=SOURCE,
        run_id="run-episode",
        report_id="report-episode",
        policy_profile=profile,
        **kwargs,
    )
    return lab, publisher, model, record


def transcript(lab, record):
    return lab.evidence.get_model(record.transcript_sha256, EpisodeTranscript)


def test_complete_episode_releases_a_bound_claim_and_records_everything(tmp_path, monkeypatch):
    steps = [
        call("list_tables"),
        call("execute_sql", "call-2", sql=CORRECT_SQL),
        submit_from_last(),
    ]
    lab, publisher, model, record = episode(tmp_path, monkeypatch, steps)
    assert record.status == "released" and record.decision_outcome == "approved"
    assert (record.model_calls, record.tool_calls, record.rejected_submissions) == (3, 3, 0)
    assert (record.input_tokens, record.output_tokens) == (300, 60)
    assert record.prompt_sha256 == PROMPT_SHA256 and record.model_id == "scripted/offline"
    released = publisher.read_current("report-episode")
    assert released is not None and released.record.release_id == record.release_id
    assert b"Settled order revenue: USD 200.00\n" in released.content
    audit = publisher.audit_bundle(record.revision_id)
    assert audit.report.run_id == record.run_id
    assert score_claims(lab.task, lab.fixture.canonical_orders, (audit.report.claims[0].claim,))
    stored = transcript(lab, record)
    assert [message.role for message in stored.messages][:2] == ["system", "user"]
    assert len(stored.usage) == 3
    events = [
        event for event in lab.evidence.get_events() if event.event_type == "episode.recorded"
    ]
    assert len(events) == 1
    assert lab.evidence.get_model(events[0].artifact_sha256, EpisodeRecord) == record
    assert model.requests[0][1] == TOOL_SPECS


def test_public_prompt_and_tool_output_exclude_private_and_host_details(tmp_path, monkeypatch):
    steps = [call("execute_sql", sql=CORRECT_SQL), submit_from_last()]
    lab, _, model, record = episode(tmp_path, monkeypatch, steps)
    messages = transcript(lab, record).messages
    prompt = messages[0].content + messages[1].content
    for forbidden in ("canonical", "seed", "200", "340", "oracle", "expected"):
        assert forbidden not in prompt.casefold()
    text = "\n".join(message.content for message in messages)
    for host_detail in (str(lab.state), str(tmp_path), lab.state.as_posix(), "evidence.sqlite3"):
        assert host_detail not in text
    assert "settled_revenue_usd" in model.requests[0][0][1].content


def test_justified_abstention_releases_fixed_wording(tmp_path, monkeypatch):
    steps = [
        call(
            "execute_sql",
            sql=CORRECT_SQL.replace(
                "SUM(o.amount_minor * 0.01)", "COUNT(*) - COUNT(o.amount_minor)"
            ),
        ),
        submit_from_last(abstain="An eligible order has no amount."),
    ]
    lab, publisher, _, record = episode(tmp_path, monkeypatch, steps, variant="insufficient")
    assert record.status == "released", record.decision_reasons
    content = publisher.read_current("report-episode").content
    assert b"Unable to establish this metric from the permitted data." in content
    assert b"no amount" not in content


def test_duplicated_join_is_withheld_when_checked_and_released_wrong_in_baseline(
    tmp_path, monkeypatch
):
    steps = [call("execute_sql", sql=DUPLICATED_SQL), submit_from_last()]
    lab, publisher, _, record = episode(tmp_path, monkeypatch, steps)
    assert record.status == "withheld" and record.decision_outcome == "rejected"
    assert "fail:query_grain:settled_revenue_usd" in record.decision_reasons
    assert publisher.read_current("report-episode") is None

    steps = [call("execute_sql", sql=DUPLICATED_SQL), submit_from_last()]
    lab, publisher, _, record = episode(
        tmp_path / "baseline", monkeypatch, steps, profile="baseline"
    )
    assert record.status == "released"
    claims = publisher.audit_bundle(record.revision_id).report.claims
    assert not score_claims(lab.task, lab.fixture.canonical_orders, (claims[0].claim,)).correct


@pytest.mark.parametrize("when", ["first_turn", "after_query"])
def test_model_errors_end_in_a_recorded_error_episode(tmp_path, monkeypatch, when):
    failure = TimeoutError("provider detail with private text")
    steps = [failure] if when == "first_turn" else [call("execute_sql", sql=CORRECT_SQL), failure]
    lab, publisher, _, record = episode(tmp_path, monkeypatch, steps)
    assert (record.status, record.error_category) == ("model_error", "TimeoutError")
    assert record.revision_id is None and record.release_id is None
    assert len(record.execution_ids) == (0 if when == "first_turn" else 1)
    assert "private text" not in lab.evidence.get_blob(record.transcript_sha256).decode()


def test_text_without_submission_and_exhausted_budgets_are_explicit(tmp_path, monkeypatch):
    _, _, _, record = episode(
        tmp_path, monkeypatch, [Message(role="assistant", content="Revenue is USD 200.00.")]
    )
    assert record.status == "no_submission" and record.revision_id is None

    looping = [call("list_tables", f"call-{index}") for index in range(10)]
    _, _, _, record = episode(
        tmp_path / "tools", monkeypatch, looping, limits=EpisodeLimits(max_tool_calls=3)
    )
    assert (record.status, record.tool_calls, record.model_calls) == ("tool_limit", 3, 4)

    ticks = iter(range(0, 1000, 400))
    _, _, model, record = episode(
        tmp_path / "time",
        monkeypatch,
        looping,
        limits=EpisodeLimits(wall_time_seconds=500),
        clock=lambda: next(ticks),
    )
    assert record.status == "time_limit" and record.model_calls == 1


def test_rejected_submission_is_explained_and_a_corrected_one_releases(tmp_path, monkeypatch):
    steps = [
        call("execute_sql", sql=CORRECT_SQL),
        submit_from_last(slot="net_revenue_usd"),
        lambda messages: (
            Message(role="assistant", content="")
            if last_tool(messages)["error"] != "undeclared_slot"
            else submit_from_last()(messages[:-2])
        ),
    ]
    lab, _, _, record = episode(tmp_path, monkeypatch, steps)
    assert record.status == "released" and record.rejected_submissions == 1
    messages = transcript(lab, record).messages
    assert json.loads(messages[-3].content) == {"error": "undeclared_slot", "status": "error"}


def test_denied_sql_and_bad_tool_calls_return_fixed_errors_without_dispatch(tmp_path, monkeypatch):
    steps = [
        call("execute_sql", sql="SELECT * FROM read_csv('/private/oracle.csv')"),
        call("preview_rows", "call-2", table="../oracle"),
        call("get_result_rows", "call-3", execution_id="execution-from-another-run"),
        call("drop_tables", "call-4"),
        call("execute_sql", "call-5", sql=CORRECT_SQL, extra=True),
        Message(role="assistant", content="giving up"),
    ]
    lab, _, _, record = episode(tmp_path, monkeypatch, steps)
    results = [
        json.loads(message.content)
        for message in transcript(lab, record).messages
        if message.role == "tool"
    ]
    assert results[0]["status"] == "denied" and "/private" not in results[0]["error"]
    assert [item.get("error") for item in results[1:]] == [
        "unknown_table",
        "unknown_execution",
        "unknown_tool",
        "invalid_arguments",
    ]
    assert record.execution_ids == () and record.status == "no_submission"


def test_preview_and_result_slices_are_bounded_to_this_run(tmp_path, monkeypatch):
    steps = [
        call("preview_rows", table="order_items", limit=2),
        lambda messages: call(
            "get_result_rows",
            "call-2",
            execution_id=last_tool(messages)["execution_id"],
            offset=1,
            limit=1,
        ),
        Message(role="assistant", content="done"),
    ]
    lab, _, _, record = episode(tmp_path, monkeypatch, steps)
    results = [json.loads(m.content) for m in transcript(lab, record).messages if m.role == "tool"]
    assert results[0]["row_count"] == 2 and len(results[0]["rows"]) == 2
    assert results[1]["offset"] == 1 and len(results[1]["rows"]) == 1
    assert results[1]["rows_truncated"] is False


def test_worker_outage_is_an_infrastructure_error_not_a_model_failure(tmp_path, monkeypatch):
    lab = make_lab(tmp_path, monkeypatch)

    def unavailable(*args):
        raise WorkerUnavailableError("engine down")

    publisher = Publisher(lab.evidence)
    publisher.register_source(SOURCE, lab.snapshot)
    monkeypatch.setattr(service, "load_worker", unavailable)
    record = run_analyst_episode(
        ScriptedModel([call("execute_sql", sql=CORRECT_SQL)]),
        publisher=publisher,
        state=lab.state,
        bundle=lab.source,
        source_key=SOURCE,
        run_id="run-outage",
        report_id="report-outage",
        policy_profile="checked",
    )
    assert (record.status, record.error_category) == ("infrastructure_error", "worker_unavailable")


def test_model_prose_never_reaches_released_bytes(tmp_path, monkeypatch):
    def submit_with_prose(messages):
        step = submit_from_last()(messages)
        return step.model_copy(update={"content": "Actually revenue was USD 999.00 <b>!</b>"})

    steps = [call("execute_sql", sql=CORRECT_SQL), submit_with_prose]
    lab, publisher, _, record = episode(tmp_path, monkeypatch, steps)
    content = publisher.read_current("report-episode").content
    assert record.status == "released" and b"999" not in content and b"<b>" not in content
    assert "USD 999.00" in transcript(lab, record).messages[-2].content


def test_episode_and_message_contracts_reject_incoherent_records(tmp_path, monkeypatch):
    _, _, _, record = episode(
        tmp_path, monkeypatch, [call("execute_sql", sql=CORRECT_SQL), submit_from_last()]
    )
    base = record.model_dump()
    for change in (
        {"release_id": None},
        {"decision_outcome": "rejected"},
        {"status": "withheld", "release_id": None},
        {"status": "model_error", "release_id": None, "decision_outcome": None},
        {"finished_at": record.started_at.replace(year=2000)},
    ):
        with pytest.raises(ValueError):
            EpisodeRecord.model_validate(base | change)
    with pytest.raises(ValueError):
        Message(role="user", tool_calls=(ToolCall(call_id="c", name="list_tables"),))
    with pytest.raises(ValueError):
        Message(role="tool", content="{}")


def test_configuration_errors_raise_before_any_model_call(tmp_path, monkeypatch):
    lab = make_lab(tmp_path, monkeypatch)
    publisher = Publisher(lab.evidence)
    model = ScriptedModel([call("list_tables")])
    arguments = dict(
        publisher=publisher,
        state=lab.state,
        bundle=lab.source,
        run_id="run-config",
        report_id="report-config",
        policy_profile="checked",
    )
    with pytest.raises(ValueError, match="not registered"):
        run_analyst_episode(model, source_key=SOURCE, **arguments)
    publisher.register_source(SOURCE, make_lab(tmp_path / "other", monkeypatch, seed=4).snapshot)
    with pytest.raises(ValueError, match="active snapshot"):
        run_analyst_episode(model, source_key=SOURCE, **arguments)
    assert model.requests == []
