from __future__ import annotations

from typing import Any

import pytest

from auguste.agent.providers.base import Completion, ToolCall


class FakeProvider:
    """Replays scripted completions and records the messages it was sent."""

    model = "fake/model"

    def __init__(self, *completions: Completion):
        self.completions = list(completions)
        self.calls: list[list[dict[str, Any]]] = []

    async def complete(self, messages, tools):
        self.calls.append([dict(m) for m in messages])
        if not self.completions:
            return Completion(text="done")
        return self.completions.pop(0)


class FakeTools:
    def __init__(self):
        self.called: list[tuple[str, dict]] = []

    def tool_specs(self):
        return [{"type": "function", "function": {"name": "get_scene_info", "parameters": {"type": "object"}}}]

    async def call(self, name, arguments):
        self.called.append((name, arguments))
        return f"ran {name}"


def tool_turn(*calls: tuple[str, dict], tokens: int = 10) -> Completion:
    return Completion(
        text="", tool_calls=[ToolCall(f"c{i}", name, args) for i, (name, args) in enumerate(calls)], tokens=tokens
    )


@pytest.fixture
def tools():
    return FakeTools()
