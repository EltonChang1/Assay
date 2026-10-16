"""Episodes driven through Inspect's model API with its offline mock provider."""

import importlib.util
import json
import os

import pytest
from phase3_support import CORRECT_SQL, make_lab

from safety_lab.agents import TOOL_SPECS, run_analyst_episode
from safety_lab.contracts.episode import EpisodeTranscript, Message, ToolCall
from safety_lab.publication import Publisher

REQUIRED = os.environ.get("SAFETY_LAB_INSPECT_TESTS") == "1"
if importlib.util.find_spec("inspect_ai") is None:
    if REQUIRED:
        raise RuntimeError("SAFETY_LAB_INSPECT_TESTS=1 requires the inspect extra")
    pytest.skip("Install the inspect extra to run Inspect adapter tests", allow_module_level=True)

from inspect_ai.model import ChatMessageTool, ModelOutput  # noqa: E402

from safety_lab.agents.inspect_client import InspectModelClient, to_inspect_messages  # noqa: E402

MOCK = "mockllm/model"


def scripted_outputs(seen_tools):
    """A mock provider policy: query, then cite the host execution it returned."""

    def respond(messages, tools, tool_choice, config):
        seen_tools.append([tool.name for tool in tools])
        results = [message for message in messages if isinstance(message, ChatMessageTool)]
        if not results:
            return ModelOutput.for_tool_call(
                MOCK, "execute_sql", {"sql": CORRECT_SQL}, tool_call_id="call:query/1"
            )
        if len(results) == 1:
            result = json.loads(results[-1].text)
            claim = {
                "slot_id": "settled_revenue_usd",
                "value": result["rows"][0][0],
                "execution_id": result["execution_id"],
                "row_index": 0,
                "column": "revenue_usd",
            }
            return ModelOutput.for_tool_call(
                MOCK, "submit_claims", {"claims": [claim]}, tool_call_id="call-submit"
            )
        return ModelOutput.from_content(MOCK, "unexpected extra turn")

    return respond


def run(tmp_path, monkeypatch, client):
    lab = make_lab(tmp_path, monkeypatch)
    publisher = Publisher(lab.evidence)
    publisher.register_source("sales-q1", lab.snapshot)
    record = run_analyst_episode(
        client,
        publisher=publisher,
        state=lab.state,
        bundle=lab.source,
        source_key="sales-q1",
        run_id="run-inspect",
        report_id="report-inspect",
        policy_profile="checked",
    )
    return lab, publisher, record


def test_inspect_provider_drives_a_complete_released_episode(tmp_path, monkeypatch):
    seen_tools: list[list[str]] = []
    client = InspectModelClient(MOCK, custom_outputs=scripted_outputs(seen_tools))
    lab, publisher, record = run(tmp_path, monkeypatch, client)
    assert record.status == "released", record
    assert record.model_id == client.model_id and "mockllm" in record.model_id
    assert seen_tools[0] == [spec.name for spec in TOOL_SPECS]
    assert b"USD 200.00" in publisher.read_current("report-inspect").content
    messages = lab.evidence.get_model(record.transcript_sha256, EpisodeTranscript).messages
    query_call = messages[2].tool_calls[0]
    assert query_call.call_id.startswith("call-") and ":" not in query_call.call_id
    assert messages[3].tool_call_id == query_call.call_id


def test_inspect_error_outputs_and_exceptions_are_model_errors(tmp_path, monkeypatch):
    errored = InspectModelClient(
        MOCK, custom_outputs=[ModelOutput.from_content(MOCK, "", error="rate limited")]
    )
    _, _, record = run(tmp_path, monkeypatch, errored)
    assert (record.status, record.error_category) == ("model_error", "InspectGenerationError")

    def explode(*args):
        raise ConnectionError("provider unreachable")

    raising = InspectModelClient(MOCK, custom_outputs=explode)
    _, _, record = run(tmp_path / "raise", monkeypatch, raising)
    assert record.status == "model_error"


def test_message_conversion_preserves_roles_ids_and_tool_functions():
    messages = (
        Message(role="system", content="s"),
        Message(role="user", content="u"),
        Message(
            role="assistant",
            content="thinking",
            tool_calls=(ToolCall(call_id="call-1", name="execute_sql", arguments={"sql": "x"}),),
        ),
        Message(role="tool", content='{"status":"ok"}', tool_call_id="call-1"),
    )
    converted = to_inspect_messages(messages)
    assert [message.role for message in converted] == ["system", "user", "assistant", "tool"]
    assert converted[2].tool_calls[0].id == "call-1"
    assert converted[2].tool_calls[0].arguments == {"sql": "x"}
    assert converted[3].tool_call_id == "call-1" and converted[3].function == "execute_sql"
