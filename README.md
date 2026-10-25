# Auguste

An AI assistant inside Houdini. Ask it in plain language to look at the scene, build networks or change parameters, and it does the work through Houdini's own API. Anything risky (running code, deleting nodes, saving or writing files) needs your approval first.

Auguste runs on the **Claude Code subscription you already have**. It needs no API key and adds no per-token billing. Local models (Ollama, LM Studio…) are also supported through LiteLLM.

> Status: MVP. Chat dialog in Houdini, agent sidecar, confirmation policy. RAG over your own files and Docker packaging are next.

## How it works

```
Houdini ──(shelf: Start Session)──> Auguste dialog (PySide, stdlib only)
                                        │  local HTTP, 127.0.0.1:8765
                                        ▼
                                  auguste serve  (sidecar)
                                        │  claude -p  (your subscription)
                                        ▼
                                  fxhoudinimcp  ──>  Houdini plugin (hwebserver :8100)
```

- **[fxhoudinimcp](https://github.com/healkeiser/fxhoudinimcp)** (pinned, MIT) provides the Houdini ↔ MCP layer: 216 tools. Auguste uses it as is, with no fork.
- **The sidecar** (`auguste serve`) runs the agent. It drives the Claude Code CLI headless and translates its stream into chat events.
- **The policy** sorts every tool into *safe*, *mutating* or *dangerous*. Dangerous calls always show an approval card in the dialog. If you decline, the tool never runs.
- **The dialog** contains no LLM SDK. It only talks to the sidecar, and starts the sidecar if it isn't running.

## Requirements

- Houdini 21.0 or 22.0
- Python 3.11+
- [Claude Code](https://claude.com/claude-code), signed in: `claude auth login`
- fxhoudinimcp's Houdini plugin installed: `python -m fxhoudinimcp install`

## Install

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e .                 # add '.[local]' for local models, '.[dev]' for tests
python -m fxhoudinimcp install   # Houdini plugin for the MCP layer
auguste install-houdini ~/Library/Preferences/houdini/21.0/packages   # your Houdini packages dir
cp .env.example .env             # optional settings
```

Restart Houdini, add the **Auguste** shelf, then click **Start Session**.

## Usage

- **In Houdini:** use the shelf → *Start Session*, then chat. Approve or decline dangerous actions on their cards. Use *Stop* to end a run.
- **From a terminal:** `auguste chat` (prompts `y/N` for confirmations).
- **Sidecar only:** `auguste serve [--port 8765]`.

Common options: `--backend claude-code|litellm`, `--model sonnet` (or `ollama/qwen3`), `--max-turns 20`, `--ask-mutating` (also confirm mutating tools).

## Configuration

`.env` at the repo root. Real environment variables take precedence.

| Variable | Default | Purpose |
|---|---|---|
| `AUGUSTE_BACKEND` | `claude-code` | `claude-code` or `litellm` |
| `AUGUSTE_MODEL` | account default | `sonnet` / `opus` / `haiku`, or a LiteLLM model id |
| `AUGUSTE_CLAUDE` | auto-detect | Path to `claude` (Houdini started from the GUI doesn't get your shell PATH) |
| `AUGUSTE_PORT` | `8765` | Sidecar port |

## Development

```bash
pip install -e '.[dev]'
pytest
```

Tasks are tracked with [Backlog.md](https://backlog.md) (`backlog task list`). See [docs/auguste-docs.md](docs/auguste-docs.md) for the full technical documentation.

## License

See [LICENCE.md](LICENCE.md).
