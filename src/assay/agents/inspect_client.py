"""``ModelClient`` backed by any Inspect model provider (optional ``inspect`` extra).

Only public task text, tool specifications, and tool results are converted.
Provider credentials stay in Inspect's host-side configuration. Inspect is
imported lazily so the runtime package does not require it.
"""

from __future__ import annotations

import asyncio
import hashlib
import re
from typing import TYPE_CHECKING, Any

from assay.contracts.episode import Message, ModelTurn, ModelUsage, ToolCall, ToolSpec

if TYPE_CHECKING:
    from inspect_ai.model import ChatMessage, GenerateConfig, Model

_CALL_ID = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,159}")


class InspectGenerationError(RuntimeError):
    """The provider returned an error output instead of an assistant turn."""


def _call_id(provider_id: str) -> str:
    if _CALL_ID.fullmatch(provider_id):
        return provider_id
    return "call-" + hashlib.sha256(provider_id.encode("utf-8")).hexdigest()[:32]


def to_inspect_messages(messages: tuple[Message, ...]) -> list[ChatMessage]:
    from inspect_ai.model import (
        ChatMessageAssistant,
        ChatMessageSystem,
        ChatMessageTool,
        ChatMessageUser,
    )
    from inspect_ai.tool import ToolCall as InspectToolCall

    functions: dict[str, str] = {}
    converted: list[ChatMessage] = []
    for message in messages:
        if message.role == "system":
            converted.append(ChatMessageSystem(content=message.content))
        elif message.role == "user":
            converted.append(ChatMessageUser(content=message.content))
        elif message.role == "assistant":
            calls = []
            for call in message.tool_calls:
                functions[call.call_id] = call.name
                calls.append(
                    InspectToolCall(
                        id=call.call_id, function=call.name, arguments=dict(call.arguments)
                    )
                )
            converted.append(
                ChatMessageAssistant(content=message.content, tool_calls=calls or None)
            )
        else:
            assert message.tool_call_id is not None
            converted.append(
                ChatMessageTool(
                    content=message.content,
                    tool_call_id=message.tool_call_id,
                    function=functions.get(message.tool_call_id),
                )
            )
    return converted


class InspectModelClient:
    """Synchronous adapter for the trusted episode runner.

    Provider retries default to two (transient failures only, per the plan);
    the runner never retries semantic outcomes. Usage is taken from Inspect's
    reported token counts.
    """

    def __init__(
        self,
        model: str | Model,
        *,
        config: GenerateConfig | None = None,
        **model_args: Any,
    ):
        from inspect_ai.model import GenerateConfig, get_model

        self._config = config or GenerateConfig(max_retries=2)
        self._model = get_model(model, config=self._config, memoize=False, **model_args)

    @property
    def model_id(self) -> str:
        return str(self._model)

    def generate(self, messages: tuple[Message, ...], tools: tuple[ToolSpec, ...]) -> ModelTurn:
        from inspect_ai.tool import ToolInfo, ToolParams

        infos = [
            ToolInfo(
                name=spec.name,
                description=spec.description,
                parameters=ToolParams.model_validate(spec.parameters),
            )
            for spec in tools
        ]
        output = asyncio.run(
            self._model.generate(to_inspect_messages(messages), tools=infos, config=self._config)
        )
        if output.error:
            raise InspectGenerationError("provider returned an error output")
        assistant = output.message
        calls = tuple(
            ToolCall(
                call_id=_call_id(call.id),
                name=call.function[:128] or "unnamed",
                arguments=call.arguments if isinstance(call.arguments, dict) else {},
            )
            for call in (assistant.tool_calls or [])
        )
        usage = output.usage
        return ModelTurn(
            model_id=self.model_id,
            message=Message(role="assistant", content=assistant.text[:65_536], tool_calls=calls),
            usage=ModelUsage(
                input_tokens=0 if usage is None else usage.input_tokens,
                output_tokens=0 if usage is None else usage.output_tokens,
            ),
        )
