import json
import sys
import textwrap

import pytest

from auguste.agent.claude_code import ClaudeCodeAgent, find_claude, short_name

# Stands in for the `claude` CLI: asks the permission callback like Claude Code
# does, then prints stream-json lines.
FAKE_CLAUDE = textwrap.dedent(
    """
    import json, sys, urllib.request
    argv = sys.argv[1:]
    open(LOG, "a").write(json.dumps(argv) + "\\n")
    config = json.loads(argv[argv.index("--mcp-config") + 1])
    url = config["mcpServers"]["auguste"]["args"][-1]
    tool, args = TOOL
    def out(m): print(json.dumps(m), flush=True)
    out({"type": "system", "subtype": "init", "session_id": "s1"})
    out({"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "t1", "name": "mcp__fxhoudini__" + tool, "input": args}]}})
    body = json.dumps({"tool_name": "mcp__fxhoudini__" + tool, "input": args, "tool_use_id": "t1"}).encode()
    answer = json.loads(urllib.request.urlopen(urllib.request.Request(url, data=body, method="POST")).read())
    if answer["behavior"] == "allow":
        out({"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t1", "content": [{"type": "text", "text": "ran"}]}]}})
    else:
        out({"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t1", "is_error": True, "content": answer["message"]}]}})
    out({"type": "assistant", "message": {"content": [{"type": "text", "text": "ok"}]}})
    out({"type": "result", "subtype": "success", "is_error": False, "session_id": "s1", "usage": {"input_tokens": 3, "output_tokens": 2}})
    """
)


@pytest.fixture
def fake_claude(tmp_path):
    def make(tool, args):
        log = tmp_path / "argv.log"
        script = tmp_path / "claude"
        script.write_text(f"#!{sys.executable}\nLOG = {str(log)!r}\nTOOL = {[tool, args]!r}\n{FAKE_CLAUDE}")
        script.chmod(0o755)
        return str(script), log

    return make


async def collect(agent, text="go"):
    return [e.as_dict() async for e in agent.run(text)]


async def test_safe_tool_runs_without_asking(fake_claude, tmp_path):
    claude, log = fake_claude("get_scene_info", {})
    asked = []

    async def confirm(call, tier):
        asked.append(call)
        return True

    agent = ClaudeCodeAgent(confirm, claude=claude, servers=[], workdir=tmp_path)
    events = await collect(agent)
    assert [e["type"] for e in events] == ["tool_call", "tool_result", "text", "done"]
    assert events[0]["name"] == "get_scene_info" and events[0]["tier"] == "safe"
    assert events[-1] == {"type": "done", "reason": "finished", "tokens": 5}
    assert asked == []
    # the second run continues the same Claude Code session
    await collect(agent)
    first, second = [json.loads(line) for line in log.read_text().splitlines()]
    assert "--resume" not in first and second[second.index("--resume") + 1] == "s1"
    assert first[first.index("--tools") + 1] == ""


async def test_dangerous_tool_declined(fake_claude, tmp_path):
    claude, _ = fake_claude("execute_python", {"code": "1"})

    async def confirm(call, tier):
        assert (call.id, call.name, tier.value) == ("t1", "execute_python", "dangerous")
        return False

    events = await collect(ClaudeCodeAgent(confirm, claude=claude, servers=[], workdir=tmp_path))
    assert [e["type"] for e in events] == ["tool_call", "confirm", "tool_skipped", "text", "done"]
    assert events[2]["reason"] == "declined"


async def test_missing_cli(tmp_path):
    agent = ClaudeCodeAgent(None, claude=str(tmp_path / "nope"), servers=[], workdir=tmp_path)
    assert [e["type"] for e in await collect(agent)] == ["error", "done"]


def test_short_name():
    assert short_name("mcp__fxhoudini__create_node") == "create_node"
    assert short_name("Bash") == "Bash"


def test_find_claude_prefers_env(monkeypatch):
    monkeypatch.setenv("AUGUSTE_CLAUDE", "/custom/claude")
    assert find_claude() == "/custom/claude"


def test_find_claude_falls_back_to_install_location(monkeypatch, tmp_path):
    binary = tmp_path / "claude"
    binary.write_text("#!/bin/sh\n")
    binary.chmod(0o755)
    monkeypatch.delenv("AUGUSTE_CLAUDE", raising=False)
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    monkeypatch.setattr("auguste.agent.claude_code.CLAUDE_LOCATIONS", (str(binary),))
    assert find_claude() == str(binary)
