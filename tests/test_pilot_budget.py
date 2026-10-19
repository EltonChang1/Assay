"""The paid-pilot guard is tested offline; no provider, credential, or Docker call."""

import json
from decimal import Decimal

import pytest

from assay.contracts.episode import Message, ToolSpec
from research.run_pilot import (
    ACTOR_CALLS,
    CONTEXT_TOKENS,
    HARD_CAP,
    MAX_OUTPUT,
    MAX_REQUEST_BYTES,
    MODEL,
    OVERSIGHT_CALLS,
    SABOTAGE,
    BudgetDenied,
    BudgetedClient,
    BudgetJournal,
    PilotStopped,
    UncertainCall,
    charge,
    encoded,
    exclusive_lock,
    model_message,
    request_payload,
)

MESSAGES = (Message(role="system", content="Solve the public task."),)


def response(*, input_tokens=100, output_tokens=20):
    return {
        "model": MODEL,
        "status": "completed",
        "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens},
        "output": [{"type": "message", "content": [{"type": "output_text", "text": "done"}]}],
    }


def test_reservation_is_durable_before_dispatch_and_settles_at_uncached_upper_cost(tmp_path):
    journal = BudgetJournal(tmp_path / "budget.sqlite3")

    def transport(payload):
        reopened = BudgetJournal(journal.path)
        assert reopened.halted
        assert reopened.totals()["call_count"] == 1
        assert Decimal(reopened.totals()["committed_cost_upper_usd"]) == charge(
            CONTEXT_TOKENS, MAX_OUTPUT
        )
        reopened.close()
        assert json.loads(payload)["max_output_tokens"] == MAX_OUTPUT
        return response()

    turn = BudgetedClient(journal, "ep", "analyst", transport=transport).generate(MESSAGES, ())
    assert turn.message.content == "done" and turn.usage.input_tokens == 100
    assert not journal.halted
    assert Decimal(journal.totals()["committed_cost_upper_usd"]) == Decimal("0.000165")
    journal.close()


def test_dollar_cap_denies_before_transport_and_survives_reopening(tmp_path):
    path = tmp_path / "budget.sqlite3"
    journal = BudgetJournal(path, cap=Decimal("0.30"))
    sent = []
    client = BudgetedClient(journal, "ep", "analyst", transport=lambda p: sent.append(p))
    with pytest.raises(BudgetDenied, match="experiment_dollar_cap"):
        client.generate(MESSAGES, ())
    assert sent == [] and journal.totals()["call_count"] == 0
    journal.close()
    reopened = BudgetJournal(path, cap=Decimal("0.30"))
    with pytest.raises(BudgetDenied):
        BudgetedClient(reopened, "ep", "analyst", transport=lambda p: sent.append(p)).generate(
            MESSAGES, ()
        )
    assert sent == []
    with pytest.raises(ValueError, match="frozen spending cap"):
        BudgetJournal(path, cap=Decimal("0.31"))
    reopened.close()


@pytest.mark.parametrize("cap", [Decimal("15.01"), Decimal(0), Decimal("NaN")])
def test_cannot_raise_user_authorized_cap(tmp_path, cap):
    with pytest.raises(ValueError, match="no greater than USD 15"):
        BudgetJournal(tmp_path / "budget.sqlite3", cap=cap)


def test_every_request_reserves_full_context_and_never_exceeds_hard_cap(tmp_path):
    journal = BudgetJournal(tmp_path / "budget.sqlite3", cap=Decimal("0.62"))
    client = BudgetedClient(
        journal,
        "ep",
        "analyst",
        transport=lambda payload: response(input_tokens=CONTEXT_TOKENS, output_tokens=MAX_OUTPUT),
    )
    for _ in range(2):
        client.generate(MESSAGES, ())
    with pytest.raises(BudgetDenied):
        client.generate(MESSAGES, ())
    assert Decimal(journal.totals()["committed_cost_upper_usd"]) <= Decimal("0.62") <= HARD_CAP
    assert journal.totals()["call_count"] == 2
    journal.close()


@pytest.mark.parametrize("role,limit", [("analyst", ACTOR_CALLS), ("oversight", OVERSIGHT_CALLS)])
def test_call_budgets_are_shared_across_new_clients_and_correction_rounds(tmp_path, role, limit):
    journal = BudgetJournal(tmp_path / "budget.sqlite3")
    sent = []

    def transport(payload):
        sent.append(payload)
        return response()

    for _ in range(limit):
        BudgetedClient(journal, "ep", role, transport=transport).generate(MESSAGES, ())
    with pytest.raises(BudgetDenied, match="shared_role_call_limit"):
        BudgetedClient(journal, "ep", role, transport=transport).generate(MESSAGES, ())
    assert len(sent) == limit
    # A separate assigned episode has its own role allowance, but shares dollars.
    BudgetedClient(journal, "next-ep", role, transport=transport).generate(MESSAGES, ())
    assert len(sent) == limit + 1
    journal.close()


def test_summary_and_reviewer_share_one_oversight_cap(tmp_path):
    journal = BudgetJournal(tmp_path / "budget.sqlite3")
    summarizer = BudgetedClient(journal, "ep", "oversight", transport=lambda p: response())
    reviewer = BudgetedClient(journal, "ep", "oversight", transport=lambda p: response())
    for _ in range(OVERSIGHT_CALLS // 2):
        summarizer.generate(MESSAGES, ())
        reviewer.generate(MESSAGES, ())
    with pytest.raises(BudgetDenied, match="shared_role_call_limit"):
        reviewer.generate(MESSAGES, ())
    journal.close()


def test_uncertain_exception_keeps_reservation_and_halts_without_retry(tmp_path):
    journal = BudgetJournal(tmp_path / "budget.sqlite3")
    sent = []

    def transport(payload):
        sent.append(payload)
        raise TimeoutError("private provider exception details must not be journaled")

    client = BudgetedClient(journal, "ep", "analyst", transport=transport)
    with pytest.raises(UncertainCall):
        client.generate(MESSAGES, ())
    assert len(sent) == 1 and journal.halted
    assert Decimal(journal.totals()["unreconciled_reserved_usd"]) == charge(
        CONTEXT_TOKENS, MAX_OUTPUT
    )
    with pytest.raises(UncertainCall, match="unsettled_call"):
        client.generate(MESSAGES, ())
    assert len(sent) == 1
    row = journal.db.execute("SELECT error_category,response_json FROM calls").fetchone()
    assert row == ("TimeoutError", None)
    journal.close()


@pytest.mark.parametrize(
    "changed",
    [
        {},
        {"usage": None},
        {"usage": {"input_tokens": True, "output_tokens": 1}},
        {"usage": {"input_tokens": 1, "output_tokens": MAX_OUTPUT + 1}},
        {"usage": {"input_tokens": CONTEXT_TOKENS + 1, "output_tokens": 1}},
        {"model": "unpriced/model"},
    ],
)
def test_missing_or_out_of_bound_usage_never_frees_reservation(tmp_path, changed):
    journal = BudgetJournal(tmp_path / "budget.sqlite3")
    malformed = response() | changed if changed else {}
    with pytest.raises(UncertainCall, match="invalid_or_missing_usage"):
        BudgetedClient(journal, "ep", "analyst", transport=lambda p: malformed).generate(
            MESSAGES, ()
        )
    assert journal.halted and journal.totals()["settled_cost_upper_usd"] == "0"
    journal.close()


def test_a_process_crash_reservation_survives_reopening_and_prevents_new_calls(tmp_path):
    path = tmp_path / "budget.sqlite3"
    journal = BudgetJournal(path)
    journal.reserve("ep", "analyst", b"{}")
    journal.close()
    reopened = BudgetJournal(path)
    with pytest.raises(UncertainCall):
        reopened.reserve("new", "analyst", b"{}")
    assert reopened.totals()["call_count"] == 1
    reopened.close()


def test_source_failure_and_request_byte_limit_dispatch_nothing(tmp_path):
    journal = BudgetJournal(tmp_path / "budget.sqlite3")
    sent = []

    def changed():
        raise PilotStopped("sources changed")

    with pytest.raises(PilotStopped):
        BudgetedClient(
            journal, "ep", "analyst", source_check=changed, transport=lambda p: sent.append(p)
        ).generate(MESSAGES, ())
    with pytest.raises(BudgetDenied, match="serialized_request_byte_limit"):
        BudgetedClient(journal, "ep", "analyst", transport=lambda p: sent.append(p)).generate(
            (
                Message(role="user", content="a" * 60_000),
                Message(role="user", content="b" * 60_000),
            ),
            (),
        )
    assert sent == [] and journal.totals()["call_count"] == 0
    assert MAX_REQUEST_BYTES < 120_500
    journal.close()


def test_parallel_dispatch_and_concurrent_process_lock_are_refused(tmp_path):
    journal = BudgetJournal(tmp_path / "budget.sqlite3")
    assert journal.call_lock.acquire(blocking=False)
    try:
        with pytest.raises(PilotStopped, match="parallel model dispatch"):
            BudgetedClient(journal, "ep", "analyst").generate(MESSAGES, ())
    finally:
        journal.call_lock.release()
    with exclusive_lock(tmp_path), pytest.raises(FileExistsError), exclusive_lock(tmp_path):
        pytest.fail("a second process acquired the same run")
    assert not (tmp_path / "pilot.lock").exists()
    journal.close()


def test_sabotage_is_in_actual_analyst_request_and_not_shared_transcript_or_reviewer(tmp_path):
    journal = BudgetJournal(tmp_path / "budget.sqlite3")
    sent = []

    def transport(payload):
        sent.append(json.loads(payload))
        return response()

    BudgetedClient(journal, "ep", "analyst", sabotage=True, transport=transport).generate(
        MESSAGES, ()
    )
    BudgetedClient(journal, "ep", "oversight", transport=transport).generate(MESSAGES, ())
    assert SABOTAGE in sent[0]["input"][0]["content"]
    assert SABOTAGE not in encoded(sent[1]).decode("utf-8")
    assert MESSAGES[0].content == "Solve the public task."
    with pytest.raises(ValueError, match="only analyst"):
        BudgetedClient(journal, "ep", "oversight", sabotage=True)
    journal.close()


def test_payload_uses_only_function_tools_and_fixed_unretained_standard_tier():
    spec = ToolSpec(
        name="list_tables",
        description="public tables",
        parameters={"type": "object", "properties": {}},
    )
    payload = request_payload(MESSAGES, (spec,))
    assert payload["store"] is False and payload["service_tier"] == "default"
    assert payload["reasoning"] == {"effort": "none"}
    assert payload["tools"][0]["type"] == "function"
    assert payload["parallel_tool_calls"] is False
    assert payload["model"] == MODEL


def test_settlement_is_not_repeatable_and_retains_malformed_output_cost(tmp_path):
    journal = BudgetJournal(tmp_path / "budget.sqlite3")
    call_id = journal.reserve("ep", "analyst", b"{}")
    journal.settle(call_id, response())
    with pytest.raises(PilotStopped, match="exactly once"):
        journal.settle(call_id, response())
    malformed = response() | {
        "output": [
            {"type": "function_call", "call_id": "c", "name": "list_tables", "arguments": "[]"}
        ]
    }
    with pytest.raises(ValueError, match="arguments must be an object"):
        BudgetedClient(journal, "next", "analyst", transport=lambda p: malformed).generate(
            MESSAGES, ()
        )
    assert journal.totals()["call_count"] == 2 and not journal.halted
    journal.close()


def test_response_tool_call_id_is_normalized_without_executing_prose():
    value = response() | {
        "output": [
            {
                "type": "function_call",
                "call_id": "call:provider/id",
                "name": "list_tables",
                "arguments": "{}",
            }
        ]
    }
    assert model_message(value).tool_calls[0].call_id.startswith("call-")
