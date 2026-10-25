"""MCP client connected to several stdio servers at once, routing calls by tool name."""

from __future__ import annotations

import json
import sys
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from typing import Any, Protocol

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


class ToolHost(Protocol):
    def tool_specs(self) -> list[dict[str, Any]]: ...

    async def call(self, name: str, arguments: dict[str, Any]) -> str: ...


@dataclass
class ServerConfig:
    name: str
    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] | None = None


def default_servers() -> list[ServerConfig]:
    # auguste-mcp (RAG tools) joins this list in TASK-4.
    return [ServerConfig("fxhoudinimcp", sys.executable, ["-m", "fxhoudinimcp"])]


class McpHub:
    def __init__(self, servers: list[ServerConfig]):
        self.servers = servers
        self._stack = AsyncExitStack()
        self._sessions: dict[str, ClientSession] = {}
        self._tools: dict[str, tuple[str, Any]] = {}

    async def __aenter__(self) -> McpHub:
        try:
            for server in self.servers:
                params = StdioServerParameters(command=server.command, args=server.args, env=server.env)
                read, write = await self._stack.enter_async_context(stdio_client(params))
                session = await self._stack.enter_async_context(ClientSession(read, write))
                await session.initialize()
                self._sessions[server.name] = session
                for tool in (await session.list_tools()).tools:
                    if tool.name in self._tools:
                        raise ValueError(f"tool {tool.name!r} exposed by both {self._tools[tool.name][0]} and {server.name}")
                    self._tools[tool.name] = (server.name, tool)
        except BaseException:
            await self._stack.aclose()
            raise
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self._stack.aclose()

    def tool_specs(self) -> list[dict[str, Any]]:
        return [
            {"type": "function", "function": {"name": t.name, "description": t.description or "", "parameters": t.input_schema}}
            for _, t in self._tools.values()
        ]

    async def call(self, name: str, arguments: dict[str, Any]) -> str:
        if name not in self._tools:
            return f"Error: unknown tool {name!r}"
        server, _ = self._tools[name]
        result = await self._sessions[server].call_tool(name, arguments)
        text = result_text(result)
        return f"Error: {text}" if result.is_error else text


def result_text(result: Any) -> str:
    parts = []
    for block in result.content:
        if getattr(block, "type", None) == "text":
            parts.append(block.text)
        else:
            parts.append(f"[{getattr(block, 'type', 'content')} omitted]")
    if not parts and result.structured_content is not None:
        parts.append(json.dumps(result.structured_content, default=str))
    return "\n".join(parts)
