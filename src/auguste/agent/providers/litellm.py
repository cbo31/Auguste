"""Optional AIProvider backed by LiteLLM, meant for local models such as
"ollama/qwen3". Any credentials come from LiteLLM's own env vars."""

from __future__ import annotations

import json
from typing import Any

from auguste.agent.providers.base import Completion, ToolCall


class LiteLLMProvider:
    def __init__(self, model: str, api_key: str | None = None, **options: Any):
        self.model = model
        self.api_key = api_key
        self.options = options

    async def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> Completion:
        import litellm

        kwargs: dict[str, Any] = dict(self.options)
        if tools:
            kwargs["tools"] = tools
        if self.api_key:
            kwargs["api_key"] = self.api_key
        response = await litellm.acompletion(model=self.model, messages=messages, **kwargs)
        return parse_response(response)


def parse_response(response: Any) -> Completion:
    message = response.choices[0].message
    calls = []
    for call in getattr(message, "tool_calls", None) or []:
        raw = call.function.arguments or "{}"
        try:
            arguments = json.loads(raw) if isinstance(raw, str) else dict(raw)
        except json.JSONDecodeError:
            arguments = {"_unparsed": raw}
        calls.append(ToolCall(id=call.id, name=call.function.name, arguments=arguments))
    usage = getattr(response, "usage", None)
    return Completion(text=message.content or "", tool_calls=calls, tokens=getattr(usage, "total_tokens", 0) or 0)
