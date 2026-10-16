"""Provider-agnostic model interface and an offline scripted model.

Provider adapters (for example an Inspect-backed client) implement
``ModelClient``. Credentials stay in that host-side client; the episode runner
passes only public task text, tool specifications, and tool results.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Protocol

from safety_lab.contracts.episode import Message, ModelTurn, ModelUsage, ToolSpec

ScriptStep = Message | Exception | Callable[[tuple[Message, ...]], Message | Exception]


class ModelClient(Protocol):
    @property
    def model_id(self) -> str: ...

    def generate(self, messages: tuple[Message, ...], tools: tuple[ToolSpec, ...]) -> ModelTurn:
        """Return one assistant turn or raise; the runner never retries semantics."""
        ...


class ScriptedModel:
    """Deterministic fake model for offline episodes; never contacts a provider.

    A step is an assistant message, an exception to raise, or a callable that
    reads the conversation so far (for example to cite a host execution ID).
    """

    def __init__(
        self,
        steps: Sequence[ScriptStep],
        *,
        model_id: str = "scripted/offline",
        usage: ModelUsage | None = None,
    ):
        self._steps = list(steps)
        self._model_id = model_id
        self._usage = usage or ModelUsage(input_tokens=100, output_tokens=20)
        self.requests: list[tuple[tuple[Message, ...], tuple[ToolSpec, ...]]] = []

    @property
    def model_id(self) -> str:
        return self._model_id

    def generate(self, messages: tuple[Message, ...], tools: tuple[ToolSpec, ...]) -> ModelTurn:
        self.requests.append((messages, tools))
        if not self._steps:
            raise RuntimeError("scripted model has no remaining steps")
        step = self._steps.pop(0)
        if callable(step) and not isinstance(step, Message):
            step = step(messages)
        if isinstance(step, Exception):
            raise step
        return ModelTurn(model_id=self._model_id, message=step, usage=self._usage)
