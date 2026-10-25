"""Provider-neutral completion interface. Messages and tool specs use the
OpenAI chat format, which LiteLLM translates for every provider."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class Completion:
    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    tokens: int = 0

    def as_message(self) -> dict[str, Any]:
        """The assistant message to append to the conversation history."""
        message: dict[str, Any] = {"role": "assistant", "content": self.text or None}
        if self.tool_calls:
            message["tool_calls"] = [
                {"id": c.id, "type": "function", "function": {"name": c.name, "arguments": json.dumps(c.arguments)}}
                for c in self.tool_calls
            ]
        return message


class AIProvider(Protocol):
    model: str

    async def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> Completion: ...
