# strata-mcp

An MCP server that delegates a single scoped task to a local
[Strata](https://github.com/Niko1221/Strata)-backed worker and returns a
structured result.

The idea: a capable orchestrator (such as Kiro) keeps the planning and the
judgement, and hands bounded, well-specified work to a cheap local model running
in Strata. The orchestrator validates every result it gets back. This is the
text-only first stage — the worker produces an answer; it does not touch the
filesystem or run commands.

## Prerequisites

- [`uv`](https://docs.astral.sh/uv/) for dependency management.
- A running Strata server with a model loaded, reachable over its
  OpenAI-compatible API. For example:

  ```bash
  strata launch --family qwen --model q2_0 --context 32k --yes --no-tui
  ```

  Verify it is up and note the address, model, and whether an API key is
  required:

  ```bash
  curl -fsS http://127.0.0.1:8080/health
  curl -fsS http://127.0.0.1:8080/v1/models   # 401 means an API key is required
  ```

## Install

For development, sync the project with uv:

```bash
uv sync
```

To install `strata-mcp` as a command on your PATH, use pipx. From a local
checkout:

```bash
pipx install .
```

Or directly from GitHub once the project is pushed to a remote:

```bash
pipx install "git+https://github.com/simonjpegg/strata-mcp.git"
```

## Configure

The server reads a TOML config file. It is discovered in this order:

1. the path in the `STRATA_MCP_CONFIG` environment variable, if set;
2. otherwise `strata-mcp/config.toml` under `XDG_CONFIG_HOME` (defaulting to
   `~/.config`), i.e. `~/.config/strata-mcp/config.toml`.

```toml
# ~/.config/strata-mcp/config.toml  (or the path in STRATA_MCP_CONFIG)
# Strata's OpenAI-compatible base URL (default shown).
base_url = "http://127.0.0.1:8080/v1"

# The context length Strata was launched with (its --context value).
# Surfaced to the caller so it can budget how much to send. Advisory.
model_context_size = 32768

# Optional safety backstop in seconds. Omit for no enforced time limit.
# max_runtime_s = 3600

# Optional sampling temperature applied to every completion (0.0–2.0).
# Defaults to 0.0 so the worker is literal and bounded. Note: 0.0 removes
# sampling randomness but does not guarantee identical output on MoE models,
# whose expert routing can still vary run to run.
# temperature = 0.0

# Optional. Required only when Strata is launched with an API key
# (its /health reports "api_key": true, and /v1/models returns 401 without one).
# api_key = "your-strata-api-key"
```

The loaded model is discovered automatically from `GET /v1/models`; you do not
configure a model name.

## Run

Once installed (see Install) with a config file at the discovered location, the
server runs as a plain command that speaks MCP over stdio:

```bash
strata-mcp
```

For development from a checkout, or to point at a specific config file:

```bash
STRATA_MCP_CONFIG=./config.toml uv run strata-mcp
```

## Wiring an MCP host

Point your MCP host at the server command. With `strata-mcp` installed and a
config file at the discovered location, the entry is just:

```json
{
  "mcpServers": {
    "strata-mcp": {
      "command": "strata-mcp"
    }
  }
}
```

For a development checkout, or to point at a specific config file, use `uv run`
and set `STRATA_MCP_CONFIG`:

```json
{
  "mcpServers": {
    "strata-mcp": {
      "command": "uv",
      "args": ["run", "strata-mcp"],
      "env": {
        "STRATA_MCP_CONFIG": "/absolute/path/to/config.toml"
      }
    }
  }
}
```

## The `delegate_task` tool

```
delegate_task(task: str, context: str = "", model: str | None = None, reasoning_effort: str | None = None) -> DelegateTaskResult
```

- `task` — the scoped instruction for the worker.
- `context` — only the snippets the worker needs. The local context window is
  the scarce resource; send the minimum.
- `model` — optional. The model id to use (see `list_models`). When omitted,
  the first model the engine reports is used.
- `reasoning_effort` — optional, one of `none | low | medium | high`. A unified
  thinking control: both Strata and Ollama honour `reasoning_effort` on the
  OpenAI-compatible endpoint, with `none` turning the reasoning phase off
  (useful for fast, bounded tasks). When omitted, the backend's default applies
  (thinking on). Best-effort and model-dependent — some models ignore levels or
  collapse them (e.g. this Qwen treats `low` and `medium` the same).

The response carries:

- `result` — a `WorkerResult` with `status`, `output`, `elapsed_s`, optional
  `token_usage`, and `error` (set when `status` is `error`).
- `model_context_size` — the declared window, so the caller can budget the next
  call.

## The `list_models` tool

```
list_models() -> list[str]
```

Returns the model identifiers the engine reports from `/v1/models`, so the
caller can pick one to pass to `delegate_task`. With a single-model backend such
as Strata this returns one id; with a multi-model backend such as Ollama it
returns all available ids, and the caller chooses which fits the task.

### A note on `model_context_size`

`model_context_size` is a single value you set in config; it is **not** derived
per model from the engine. This is deliberate: the OpenAI-compatible
`/v1/models` endpoint does not reliably expose context length across backends.
Strata reports it, but Ollama's endpoint does not and may silently truncate to
an internal default. So the operator declares one advisory window that matches
how the engine was launched. If you select a model whose real window differs
from the configured value, the configured value is still what is surfaced and
used for the oversized-context guard.

### Result status

| status        | meaning                                             |
|---------------|-----------------------------------------------------|
| `ok`          | the worker reported completed work                  |
| `needs_input` | the worker is blocked or found the task unclear     |
| `rejected`    | the worker judged the task infeasible               |
| `error`       | transport/engine failure, oversized context, or the runtime backstop fired |

## How the worker behaves

The worker runs under a system prompt with three jobs:

1. **Frame** — it is a focused worker doing one scoped task.
2. **Bound** — it has no filesystem, shell, or tools; it answers in text only
   and does not expand scope.
3. **Escape** — if the task is ambiguous, it is blocked, or it cannot complete
   the task, it stops and self-reports rather than grinding on.

To self-report, the worker ends its reply with one of these status lines, which
the server maps to a result status:

| marker               | mapped status |
|----------------------|---------------|
| `STATUS: COMPLETED`  | `ok`          |
| `STATUS: BLOCKED`    | `needs_input` |
| `STATUS: UNCLEAR`    | `needs_input` |
| `STATUS: INFEASIBLE` | `rejected`    |

Self-reporting is not trusted as correct. A weak model can be confidently
wrong, so the caller validates every result regardless of the reported status —
and performs any filesystem writes itself. Acceptance criteria are deliberately
not sent to the worker; the caller judges against them after the worker returns.

## Development

```bash
uv run ruff check .
uv run pytest
```
