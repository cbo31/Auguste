# Auguste technical documentation

This document covers the MVP: the agent sidecar, the confirmation policy and the Houdini dialog. For the roadmap see [plan.md](plan.md). For the backend decision see [adr/0001-subscription-backend.md](adr/0001-subscription-backend.md).

## 1. Components

| Component | Location | Runs in | Role |
|---|---|---|---|
| Houdini dialog | `houdini/python/auguste_houdini/dialog.py` | Houdini (PySide6, PySide2 fallback) | Chat UI, tool rows, approval cards, stop button. Stdlib + Qt only. |
| Shelf | `houdini/toolbar/auguste.shelf` | Houdini | *Start Session* → `auguste_houdini.show()` |
| CLI | `src/auguste/cli.py` | venv Python | `serve`, `chat`, `install-houdini` |
| HTTP API | `src/auguste/api/server.py` | sidecar (Starlette + uvicorn) | Sessions, streamed events, confirmations, stop |
| Claude Code agent | `src/auguste/agent/claude_code.py` | sidecar | Default backend: drives `claude -p` |
| Permission bridge | `src/auguste/agent/permission_mcp.py`, `callback.py` | Claude Code subprocess / sidecar | Routes every tool use back to Auguste's policy |
| LiteLLM agent | `src/auguste/agent/loop.py`, `providers/`, `mcp_clients.py` | sidecar | Optional backend for local models; Auguste runs the tool loop itself |
| Policy | `src/auguste/agent/policy.py` | sidecar | Tool tiers and confirmation rules |
| Settings | `src/auguste/settings.py` | sidecar | Loads `.env` from the repo root |
| Houdini MCP layer | `fxhoudinimcp==2.28.2` (dependency) | MCP server + Houdini plugin | 216 Houdini tools over `hwebserver` (port 8100) |

## 2. Request flow (Claude Code backend)

1. The user clicks **Start Session**. The dialog calls `GET /health`. If the sidecar doesn't answer, the dialog starts `$AUGUSTE_PYTHON -m auguste serve --port $AUGUSTE_PORT`, with logs in `<tmp>/auguste-sidecar.log`, and waits up to 90 s for it.
2. The dialog calls `POST /sessions` and gets a `session_id`.
3. The dialog sends a message with `POST /sessions/{sid}/messages`. The response is an NDJSON stream of events, read on a worker thread because Houdini's main thread has to stay free to execute the tool calls.
4. `ClaudeCodeAgent` runs:
   ```
   claude -p --output-format stream-json --strict-mcp-config --mcp-config <fxhoudinimcp + auguste approve>
          --permission-prompt-tool mcp__auguste__approve [--resume <session>] [--model ...] --max-turns N
   ```
   It removes `ANTHROPIC_API_KEY` from the environment so billing always stays on the subscription.
5. Before each tool use, Claude Code calls `mcp__auguste__approve`. That stdio server posts to a one-run localhost callback with a random token in its path. There, `Policy` either allows the call or emits a `confirm` event and waits for the user.
6. The user answers in the approval card, which sends `POST /sessions/{sid}/confirm {"id", "approved"}`. A declined call is never executed.
7. Later messages continue the same Claude Code session with `--resume`.

With `--backend litellm`, steps 4–5 are replaced by `Agent` in `loop.py`. Auguste opens its own MCP connections (`McpHub`), sends the tool specs to the model, applies `Policy` before each call, and enforces both `max_turns` and `max_tokens`.

## 3. HTTP API

The API listens on `127.0.0.1` only.

| Method | Path | Body | Response |
|---|---|---|---|
| GET | `/health` | — | `{ok, backend, model, auth, account}` (`tools` with LiteLLM) |
| POST | `/sessions` | — | `{session_id}` |
| POST | `/sessions/{sid}/messages` | `{text}` | NDJSON event stream. `409` if the session is busy |
| POST | `/sessions/{sid}/confirm` | `{id, approved}` | `{ok}`. `404` if there is no pending call |
| POST | `/sessions/{sid}/stop` | — | `{ok}` |
| WS | `/sessions/{sid}/ws` | messages / confirmations | the same events |

Event types: `text`, `tool_call` (with `tier`), `confirm`, `tool_result`, `tool_skipped` (with `reason`), `error`, `done` (with `reason`: `finished`, `stopped`, `max_turns`, `max_tokens`, `error`).

## 4. Confirmation policy

The source of truth is [fxhoudinimcp-tools.md](fxhoudinimcp-tools.md), which is mirrored in `policy.py`.

- **safe**: read-only, runs without asking.
- **mutating**: changes the scene but can be undone. Runs without asking unless `--ask-mutating` is set.
- **dangerous**: always asks. Covers code execution, deletes, file writes, scene replacement, HDA changes, long cooks and renders, and process control.

The tier is looked up in this order:
1. `extra_tiers` (tools registered by other servers, e.g. the future `auguste-mcp`).
2. A per-name override.
3. The module default.
4. **Unknown tools are dangerous.**

Argument escalation then raises a call to *dangerous* when:
- a capture/render tool is given an `output_path` (it writes a file);
- a node-creating tool creates a `python` node type;
- an expression is set with `language=python`;
- a parameter named `python`, `pythoncode`, `code` or `script` is set.

## 5. Houdini integration

`auguste install-houdini <packages_dir>` writes `auguste.json`:

```json
{
  "env": [
    {"AUGUSTE": "<repo root>"},
    {"AUGUSTE_PYTHON": "<venv python>"},
    {"PYTHONPATH": {"value": "$AUGUSTE/houdini/python", "method": "append"}}
  ],
  "path": "$AUGUSTE/houdini"
}
```

The dialog starts the sidecar with `PYTHONHOME`, `PYTHONPATH` and `PYTHONSTARTUP` removed, so that Houdini's Python doesn't leak into the venv. Houdini started from the GUI has a minimal PATH, so `find_claude()` looks in `AUGUSTE_CLAUDE`, then `PATH`, then `~/.local/bin`, `~/.claude/local`, `/opt/homebrew/bin` and `/usr/local/bin`.

## 6. Configuration

| Variable | Default | Used by |
|---|---|---|
| `AUGUSTE_BACKEND` | `claude-code` | CLI |
| `AUGUSTE_MODEL` | empty (account default) | CLI. Required with `litellm` |
| `AUGUSTE_CLAUDE` | auto | `find_claude()` |
| `AUGUSTE_PORT` | `8765` | CLI `serve`, dialog |
| `AUGUSTE_PYTHON`, `AUGUSTE` | set by the Houdini package | dialog |

CLI flags: `--backend`, `--model`, `--max-turns` (20), `--max-tokens` (400k, LiteLLM only), `--ask-mutating`, `--port`.

## 7. Troubleshooting

- **"Not signed in" in the dialog.** Run `claude auth login`. If `claude` isn't in a standard location, set `AUGUSTE_CLAUDE`. Auth is read once at startup, so kill the running sidecar to pick up changes.
- **The sidecar runs old code or settings.** A sidecar that is already running is reused. Stop it (`lsof -i :8765` → kill), then click *Start Session* again.
- **The sidecar doesn't start.** Check `<tmp>/auguste-sidecar.log`. Make sure `AUGUSTE_PYTHON` is set (re-run `install-houdini`).
- **The tools can't reach Houdini.** Make sure the fxhoudinimcp plugin is installed and listening (ports 8100–8115).
- **A usage limit was reached.** Subscription limits show up as `error` events.

## 8. Tests

```bash
pip install -e '.[dev]'
pytest            # tests/unit: policy, providers (mocked), loop, Claude Code stream translation, API
```

## 9. Roadmap

| Task | Status |
|---|---|
| TASK-1 Adopt fxhoudinimcp | Done |
| TASK-2 Agent sidecar, multi-provider loop, confirmation policy | Done |
| TASK-7 Claude auth from the Houdini dialog | Done |
| TASK-3 Houdini Python panel (dockable, replaces the dialog) | To do |
| TASK-4 Personal RAG over user files (`auguste-mcp`, LanceDB) | To do |
| TASK-5 Docker packaging | To do |
