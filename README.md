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
# strata-mcp.toml
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

```bash
STRATA_MCP_CONFIG=./strata-mcp.toml uv run strata-mcp
```

The server speaks MCP over stdio.

## Wiring an MCP host

Point your MCP host at the server command. A typical stdio server entry:

```json
{
  "mcpServers": {
    "strata-mcp": {
      "command": "uv",
      "args": ["run", "strata-mcp"],
      "env": {
        "STRATA_MCP_CONFIG": "/absolute/path/to/strata-mcp.toml"
      }
    }
  }
}
```

## The `delegate_task` tool

```
delegate_task(task: str, context: str = "") -> DelegateTaskResult
```

- `task` — the scoped instruction for the worker.
- `context` — only the snippets the worker needs. The local context window is
  the scarce resource; send the minimum.

The response carries:

- `result` — a `WorkerResult` with `status`, `output`, `elapsed_s`, optional
  `token_usage`, and `error` (set when `status` is `error`).
- `model_context_size` — the declared window, so the caller can budget the next
  call.

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
