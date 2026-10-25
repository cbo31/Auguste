"""Tool-calling loop with turn/token limits, policy gate and stop control."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from auguste.agent.mcp_clients import ToolHost
from auguste.agent.policy import Policy, Tier
from auguste.agent.providers.base import AIProvider, ToolCall

SYSTEM_PROMPT = (
    "You are Auguste, an assistant inside SideFX Houdini. Use the tools to inspect and edit the "
    "live scene. Prefer nodes over code. Some tools need the user's approval; if a call is "
    "declined, do not retry it, explain what you would have done instead."
)
DECLINED = "The user declined this tool call. It was not run."
STOPPED = "The run was stopped by the user. This tool call was not run."

# Asked before a gated tool runs; returns True to approve.
Confirm = Callable[[ToolCall, Tier], Awaitable[bool]]


@dataclass
class Event:
    type: str  # text | tool_call | confirm | tool_result | tool_skipped | error | done
    data: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"type": self.type, **self.data}


class Agent:
    def __init__(
        self,
        provider: AIProvider,
        tools: ToolHost,
        confirm: Confirm,
        policy: Policy | None = None,
        max_turns: int = 20,
        max_tokens: int = 400_000,
        system_prompt: str = SYSTEM_PROMPT,
    ):
        self.provider = provider
        self.tools = tools
        self.confirm = confirm
        self.policy = policy or Policy()
        self.max_turns = max_turns
        self.max_tokens = max_tokens
        self.messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
        self._stopped = False

    def stop(self) -> None:
        self._stopped = True

    async def run(self, user_text: str) -> AsyncIterator[Event]:
        """Run one user request to completion. The history carries over between runs."""
        self._stopped = False
        self.messages.append({"role": "user", "content": user_text})
        tokens = 0
        for _ in range(self.max_turns):
            if self._stopped:
                yield Event("done", {"reason": "stopped"})
                return
            try:
                completion = await self.provider.complete(self.messages, self.tools.tool_specs())
            except Exception as exc:
                yield Event("error", {"message": f"{type(exc).__name__}: {exc}"})
                yield Event("done", {"reason": "error"})
                return
            tokens += completion.tokens
            self.messages.append(completion.as_message())
            if completion.text:
                yield Event("text", {"text": completion.text})
            if not completion.tool_calls:
                yield Event("done", {"reason": "finished", "tokens": tokens})
                return
            for call in completion.tool_calls:
                async for event in self._run_tool(call):
                    yield event
            if tokens >= self.max_tokens:
                yield Event("done", {"reason": "max_tokens", "tokens": tokens})
                return
        yield Event("done", {"reason": "max_turns", "tokens": tokens})

    async def _run_tool(self, call: ToolCall) -> AsyncIterator[Event]:
        # Every tool call in the assistant message needs a tool reply, even when skipped.
        tier = self.policy.tier(call.name, call.arguments)
        info = {"id": call.id, "name": call.name, "arguments": call.arguments, "tier": tier.value}
        if self._stopped:
            result = STOPPED
            yield Event("tool_skipped", {**info, "reason": "stopped"})
        else:
            yield Event("tool_call", info)
            approved = True
            if self.policy.needs_confirmation(call.name, call.arguments):
                yield Event("confirm", info)
                approved = await self.confirm(call, tier) and not self._stopped
            if not approved:
                result = STOPPED if self._stopped else DECLINED
                yield Event("tool_skipped", {**info, "reason": "stopped" if self._stopped else "declined"})
            else:
                try:
                    result = await self.tools.call(call.name, call.arguments)
                except Exception as exc:
                    result = f"Error: {type(exc).__name__}: {exc}"
                yield Event("tool_result", {"id": call.id, "name": call.name, "result": result})
        self.messages.append({"role": "tool", "tool_call_id": call.id, "content": result})
