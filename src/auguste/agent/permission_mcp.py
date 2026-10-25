"""Stdio MCP server that Claude Code calls (--permission-prompt-tool) before each tool use.
It forwards the request to the sidecar callback URL and waits for the user's answer.

Run as: python -m auguste.agent.permission_mcp <callback_url>
"""

from __future__ import annotations

import asyncio
import json
import sys
import urllib.request
from typing import Any

from mcp.server.mcpserver import MCPServer


def _post(url: str, payload: dict[str, Any]) -> str:
    request = urllib.request.Request(
        url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        # No timeout: the user may take a while to answer the approval card.
        with urllib.request.urlopen(request) as response:
            return response.read().decode()
    except Exception as exc:
        return json.dumps({"behavior": "deny", "message": f"Auguste approval failed: {exc}"})


def build(url: str) -> MCPServer:
    server = MCPServer("auguste")

    @server.tool(description="Asks the Auguste user whether a tool call may run.", structured_output=False)
    async def approve(tool_name: str, input: dict[str, Any], tool_use_id: str | None = None) -> str:
        return await asyncio.to_thread(_post, url, {"tool_name": tool_name, "input": input, "tool_use_id": tool_use_id})

    return server


if __name__ == "__main__":
    build(sys.argv[1]).run("stdio")
