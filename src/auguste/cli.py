"""auguste serve | chat | install-houdini"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from auguste.agent.claude_code import ClaudeCodeAgent, auth_status
from auguste.agent.loop import Confirm
from auguste.agent.mcp_clients import McpHub, default_servers
from auguste.agent.policy import Policy, Tier
from auguste.agent.providers.base import ToolCall
from auguste.settings import REPO_ROOT, load_dotenv

# claude-code: the user's Claude Code login (subscription). litellm: local models
# such as ollama/qwen3; needs `pip install auguste[local]`.
BACKENDS = ("claude-code", "litellm")


def _agent_factory(args: argparse.Namespace, hub: McpHub | None):
    policy = Policy(ask_mutating=args.ask_mutating)
    if args.backend == "claude-code":
        return lambda confirm: ClaudeCodeAgent(confirm, policy, model=args.model, max_turns=args.max_turns)

    from auguste.agent.loop import Agent
    from auguste.agent.providers.litellm import LiteLLMProvider

    provider = LiteLLMProvider(args.model)
    return lambda confirm: Agent(provider, hub, confirm, policy, max_turns=args.max_turns, max_tokens=args.max_tokens)


@asynccontextmanager
async def _hub(args: argparse.Namespace):
    """LiteLLM needs our own MCP connections; Claude Code starts the servers itself."""
    if args.backend == "claude-code":
        yield None
        return
    async with McpHub(default_servers()) as hub:
        yield hub


def _info(args: argparse.Namespace) -> dict:
    info: dict = {"backend": args.backend, "model": args.model or "default"}
    if args.backend == "claude-code":
        status = auth_status() or {}
        info["auth"] = bool(status.get("loggedIn"))
        info["account"] = status.get("authMethod")
    return info


def serve(args: argparse.Namespace) -> None:
    import uvicorn

    from auguste.api.server import create_app

    info = _info(args)
    factory = {}

    @asynccontextmanager
    async def lifespan(app):
        async with _hub(args) as hub:
            if hub is not None:
                info["tools"] = len(hub.tool_specs())
            factory["make"] = _agent_factory(args, hub)
            yield

    app = create_app(lambda confirm: factory["make"](confirm), info, lifespan)
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="info")


async def _chat(args: argparse.Namespace) -> None:
    async def confirm(call: ToolCall, tier: Tier) -> bool:
        answer = await asyncio.to_thread(
            input, f"  ! {tier.value} tool {call.name}({json.dumps(call.arguments)}). Run it? [y/N] "
        )
        return answer.strip().lower() in {"y", "yes"}

    async with _hub(args) as hub:
        agent = _agent_factory(args, hub)(confirm)
        print(f"Auguste chat ({args.backend}, {args.model or 'default model'}). Empty line to quit.")
        while True:
            text = (await asyncio.to_thread(input, "> ")).strip()
            if not text:
                return
            async for event in agent.run(text):
                if event.type == "text":
                    print(event.data["text"])
                elif event.type == "tool_call":
                    print(f"  -> {event.data['name']} [{event.data['tier']}]")
                elif event.type == "tool_skipped":
                    print(f"  x {event.data['name']} ({event.data['reason']})")
                elif event.type == "error":
                    print(f"  error: {event.data['message']}")
                elif event.type == "done" and event.data["reason"] != "finished":
                    print(f"  [stopped: {event.data['reason']}]")


def install_houdini(args: argparse.Namespace) -> None:
    package = {
        "env": [
            {"AUGUSTE": REPO_ROOT.as_posix()},
            {"AUGUSTE_PYTHON": Path(sys.executable).as_posix()},
            {"PYTHONPATH": {"value": "$AUGUSTE/houdini/python", "method": "append"}},
        ],
        "path": "$AUGUSTE/houdini",
    }
    target = Path(args.packages_dir).expanduser() / "auguste.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(package, indent=4) + "\n")
    print(f"Wrote {target}. Restart Houdini, then add the 'Auguste' shelf.")


def main(argv: list[str] | None = None) -> None:
    load_dotenv()
    default_backend = os.environ.get("AUGUSTE_BACKEND", "claude-code")
    default_model = os.environ.get("AUGUSTE_MODEL") or None
    parser = argparse.ArgumentParser(prog="auguste")
    sub = parser.add_subparsers(dest="command", required=True)

    for name, func in (("serve", serve), ("chat", lambda a: asyncio.run(_chat(a)))):
        p = sub.add_parser(name)
        p.add_argument("--backend", choices=BACKENDS, default=default_backend)
        p.add_argument("--model", default=default_model, help="claude-code: alias like sonnet; litellm: e.g. ollama/qwen3")
        p.add_argument("--max-turns", type=int, default=20)
        p.add_argument("--max-tokens", type=int, default=400_000)
        p.add_argument("--ask-mutating", action="store_true", help="also ask before mutating tools")
        if name == "serve":
            p.add_argument("--port", type=int, default=int(os.environ.get("AUGUSTE_PORT", "8765")))
        p.set_defaults(func=func)

    p = sub.add_parser("install-houdini", help="write the Auguste Houdini package json")
    p.add_argument("packages_dir", help="a Houdini packages directory")
    p.set_defaults(func=install_houdini)

    args = parser.parse_args(argv)
    if getattr(args, "backend", None) == "litellm" and not args.model:
        parser.error("--model (or AUGUSTE_MODEL) is required with --backend litellm")
    args.func(args)


if __name__ == "__main__":
    main()
