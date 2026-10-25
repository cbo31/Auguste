"""Agent backed by the user's Claude Code CLI, so runs use their claude.ai subscription
instead of an API key. Claude Code runs the tool loop and calls the MCP servers itself;
every tool use is routed through Auguste's policy via --permission-prompt-tool.

Emits the same events as loop.Agent, so the API and the Houdini dialog don't care
which backend is running.
"""

from __future__ import annotations

import asyncio
import json
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from auguste.agent.loop import SYSTEM_PROMPT, Confirm, Event
from auguste.agent.mcp_clients import ServerConfig, default_servers
from auguste.agent.policy import Policy
from auguste.agent.providers.base import ToolCall

PERMISSION_TOOL = "mcp__auguste__approve"
DECLINED = "The user declined this tool call. It was not run."
STOPPED = "The run was stopped by the user. This tool call was not run."
RESULT_REASONS = {"success": "finished", "error_max_turns": "max_turns"}


# Apps started from the Dock/Finder (Houdini) don't get the shell PATH, so look
# where the Claude Code installers put the binary.
CLAUDE_LOCATIONS = ("~/.local/bin/claude", "~/.claude/local/claude", "/opt/homebrew/bin/claude", "/usr/local/bin/claude")


def find_claude() -> str:
    """$AUGUSTE_CLAUDE, else `claude` on PATH, else a known install location."""
    if env := os.environ.get("AUGUSTE_CLAUDE"):
        return env
    if found := shutil.which("claude"):
        return found
    for location in CLAUDE_LOCATIONS:
        path = Path(location).expanduser()
        if os.access(path, os.X_OK):
            return str(path)
    return "claude"


def auth_status(claude: str | None = None) -> dict[str, Any] | None:
    """`claude auth status` as a dict, or None when the CLI is missing or fails."""
    try:
        out = subprocess.run([claude or find_claude(), "auth", "status"], capture_output=True, text=True, timeout=20)
        return json.loads(out.stdout)
    except Exception:
        return None


def short_name(tool: str) -> str:
    """mcp__fxhoudini__create_node -> create_node, the name the policy knows."""
    parts = tool.split("__", 2)
    return parts[2] if len(parts) == 3 and parts[0] == "mcp" else tool


def result_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    parts = []
    for block in content or []:
        if block.get("type") == "text":
            parts.append(block["text"])
        else:
            parts.append(f"[{block.get('type', 'content')} omitted]")
    return "\n".join(parts)


class ClaudeCodeAgent:
    def __init__(
        self,
        confirm: Confirm,
        policy: Policy | None = None,
        model: str | None = None,
        max_turns: int = 20,
        servers: list[ServerConfig] | None = None,
        claude: str | None = None,
        system_prompt: str = SYSTEM_PROMPT,
        workdir: Path | None = None,
    ):
        self.confirm = confirm
        self.policy = policy or Policy()
        self.model = model
        self.max_turns = max_turns
        self.servers = default_servers() if servers is None else servers
        self.claude = claude or find_claude()
        self.system_prompt = system_prompt
        # A neutral cwd keeps project CLAUDE.md files out; --resume needs the same one.
        self.workdir = workdir or Path(tempfile.gettempdir()) / "auguste-claude"
        self.session_id: str | None = None
        self._proc: asyncio.subprocess.Process | None = None
        self._queue: asyncio.Queue[Event | None] = asyncio.Queue()
        self._calls: dict[str, dict[str, Any]] = {}  # tool_use_id -> tool_call event data
        self._skipped: dict[str, str] = {}  # tool_use_id -> reason
        self._stopped = False

    def stop(self) -> None:
        self._stopped = True
        if self._proc and self._proc.returncode is None:
            self._proc.terminate()

    async def permission(self, request: dict[str, Any]) -> dict[str, Any]:
        """Answers one --permission-prompt-tool request with Claude Code's allow/deny shape."""
        arguments = request.get("input") or {}
        name = short_name(str(request.get("tool_name", "")))
        info = self._calls.get(str(request.get("tool_use_id"))) or self._last_call(name)
        if info is None:
            tier = self.policy.tier(name, arguments)
            info = {"id": request.get("tool_use_id") or secrets.token_hex(6), "name": name, "arguments": arguments, "tier": tier.value}
        approved = not self._stopped
        if approved and self.policy.needs_confirmation(name, arguments):
            await self._queue.put(Event("confirm", info))
            call = ToolCall(info["id"], name, arguments)
            approved = await self.confirm(call, self.policy.tier(name, arguments)) and not self._stopped
        if approved:
            return {"behavior": "allow", "updatedInput": arguments}
        self._skipped[info["id"]] = "stopped" if self._stopped else "declined"
        return {"behavior": "deny", "message": STOPPED if self._stopped else DECLINED}

    def _last_call(self, name: str) -> dict[str, Any] | None:
        for info in reversed(self._calls.values()):
            if info["name"] == name and info["id"] not in self._skipped:
                return info
        return None

    def _command(self, text: str, url: str) -> list[str]:
        servers = {s.name: {"command": s.command, "args": s.args, **({"env": s.env} if s.env else {})} for s in self.servers}
        servers["auguste"] = {"command": sys.executable, "args": ["-m", "auguste.agent.permission_mcp", url]}
        command = [
            self.claude, "-p", text,
            "--output-format", "stream-json", "--verbose",
            "--mcp-config", json.dumps({"mcpServers": servers}), "--strict-mcp-config",
            "--permission-prompt-tool", PERMISSION_TOOL, "--permission-mode", "default",
            "--tools", "",  # no Bash, Edit, etc.: only the MCP tools
            "--setting-sources", "",  # ignore the user's allow rules and hooks
            "--append-system-prompt", self.system_prompt,
            "--max-turns", str(self.max_turns),
        ]
        if self.model:
            command += ["--model", self.model]
        if self.session_id:
            command += ["--resume", self.session_id]
        return command

    async def run(self, user_text: str) -> AsyncIterator[Event]:
        """Run one user request. The Claude Code session carries the history between runs."""
        from auguste.agent.callback import CallbackServer

        self._stopped = False
        self._calls.clear()
        self._skipped.clear()
        self._queue = asyncio.Queue()
        if shutil.which(self.claude) is None:
            yield Event("error", {"message": f"'{self.claude}' not found. Install Claude Code and run `claude auth login`."})
            yield Event("done", {"reason": "error"})
            return
        self.workdir.mkdir(parents=True, exist_ok=True)
        async with CallbackServer(self.permission) as url:
            env = {**os.environ, "MCP_TOOL_TIMEOUT": str(24 * 3600 * 1000)}  # approvals can wait
            env.pop("ANTHROPIC_API_KEY", None)  # use the subscription, never a stray key
            self._proc = await asyncio.create_subprocess_exec(
                *self._command(user_text, url),
                cwd=self.workdir, env=env,
                stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                limit=16 * 1024 * 1024,
            )
            reader = asyncio.create_task(self._read(self._proc))
            try:
                while (event := await self._queue.get()) is not None:
                    yield event
            finally:
                self.stop()
                await reader

    async def _read(self, proc: asyncio.subprocess.Process) -> None:
        done = False
        try:
            assert proc.stdout is not None
            async for line in proc.stdout:
                try:
                    message = json.loads(line)
                except json.JSONDecodeError:
                    continue
                for event in self._translate(message):
                    done = done or event.type == "done"
                    await self._queue.put(event)
            stderr = (await proc.stderr.read()).decode(errors="replace").strip() if proc.stderr else ""
            await proc.wait()
            if not done:
                if self._stopped:
                    await self._queue.put(Event("done", {"reason": "stopped"}))
                else:
                    await self._queue.put(Event("error", {"message": stderr or f"claude exited with code {proc.returncode}"}))
                    await self._queue.put(Event("done", {"reason": "error"}))
        finally:
            await self._queue.put(None)

    def _translate(self, message: dict[str, Any]) -> list[Event]:
        kind = message.get("type")
        if message.get("session_id"):
            self.session_id = message["session_id"]
        events: list[Event] = []
        if kind == "assistant":
            for block in message.get("message", {}).get("content", []):
                if block.get("type") == "text" and block.get("text"):
                    events.append(Event("text", {"text": block["text"]}))
                elif block.get("type") == "tool_use":
                    name, arguments = short_name(block["name"]), block.get("input") or {}
                    info = {"id": block["id"], "name": name, "arguments": arguments, "tier": self.policy.tier(name, arguments).value}
                    self._calls[block["id"]] = info
                    events.append(Event("tool_call", info))
        elif kind == "user":
            content = message.get("message", {}).get("content", [])
            for block in content if isinstance(content, list) else []:
                if block.get("type") != "tool_result":
                    continue
                call_id = block.get("tool_use_id")
                info = self._calls.get(call_id, {"id": call_id, "name": "?", "arguments": {}, "tier": "dangerous"})
                if call_id in self._skipped:
                    events.append(Event("tool_skipped", {**info, "reason": self._skipped[call_id]}))
                else:
                    text = result_text(block.get("content"))
                    result = f"Error: {text}" if block.get("is_error") else text
                    events.append(Event("tool_result", {"id": call_id, "name": info["name"], "result": result}))
        elif kind == "result":
            usage = message.get("usage") or {}
            tokens = (usage.get("input_tokens") or 0) + (usage.get("output_tokens") or 0)
            reason = RESULT_REASONS.get(message.get("subtype"), "error")
            if self._stopped:
                reason = "stopped"
            elif reason == "error" or (reason == "finished" and message.get("is_error")):
                # e.g. "Not logged in" or a usage limit reached
                reason = "error"
                detail = message.get("result") or ", ".join(map(str, message.get("errors") or [])) or message.get("subtype")
                events.append(Event("error", {"message": f"Claude Code: {detail}"}))
            events.append(Event("done", {"reason": reason, "tokens": tokens}))
        return events
