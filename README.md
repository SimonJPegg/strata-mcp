# strata-mcp

An MCP server that hands a scoped task to a local model and returns a structured
result.

Run it from Kiro, Claude Code, OpenCode, whatever. Chat with the expensive model.
Pass the grunt work to the free one. (*cough* electric *cough*)

Tested on Kiro. It works, but Kiro doesn't show status updates, so a long task looks identical to a stuck one.

## Prerequisites

- [`uv`](https://docs.astral.sh/uv/) for dependency management.
- A running inference backend with a model loaded, reachable over an
  OpenAI-compatible API. Strata, for example:

  ```bash
  strata launch --family qwen --model q2_0 --context 32k --yes --no-tui
  ```

  Check it is up. Note the address, the model, and whether a key is required:

  ```bash
  curl -fsS http://127.0.0.1:8080/health
  curl -fsS http://127.0.0.1:8080/v1/models   # 401 means a key is required
  ```

## Install

For development, sync with uv:

```bash
uv sync
```

To put `strata-mcp` on your PATH, use pipx. From a checkout:

```bash
pipx install .
```

Or from GitHub:

```bash
pipx install "git+https://github.com/simonjpegg/strata-mcp.git"
```

## Configure

The server reads a TOML config file. It looks here:

1. `STRATA_MCP_CONFIG`, if set.
2. Otherwise `~/.config/strata-mcp/config.toml` (honouring `XDG_CONFIG_HOME`).

```toml
# ~/.config/strata-mcp/config.toml
# Backend provider. Picks the default URL and required headers.
# Allowed: strata | ollama | opencode-go
provider = "strata"

# The provider's OpenAI-compatible base URL. Only override if your backend
# listens somewhere else.
# base_url = "http://127.0.0.1:8080/v1"

# Context length the loaded model was launched with. Advisory.
model_context_size = 32768

# Safety backstop in seconds. Omit for no wall-clock limit.
# max_runtime_s = 3600

# Sampling temperature (0.0-2.0). Defaults to 0.0 so the worker is literal.
# 0.0 removes randomness but doesn't guarantee identical output on MoE models.
# temperature = 0.0

# Required for opencode-go. Also required when Strata runs with a key
# (/health reports "api_key": true, or /v1/models returns 401).
# api_key = "your-api-key"
```

The model id comes from `GET /v1/models`. You don't configure it. `provider`
defaults to `strata`, so existing config files keep working.

## Run

Installed, with a config file at the discovered location:

```bash
strata-mcp
```

From a checkout, or to point at a specific config:

```bash
STRATA_MCP_CONFIG=./config.toml uv run strata-mcp
```

## Wiring an MCP host

Point your host at the command. Installed, the entry is just:

```json
{
  "mcpServers": {
    "strata-mcp": {
      "command": "strata-mcp"
    }
  }
}
```

From a checkout, use `uv run` and set `STRATA_MCP_CONFIG`:

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

## Recommended agent configs

Recomended agent configs exist in `agents/`:

- `agents/kiro-agent.json` — a Kiro agent that registers the server and biases it
toward `delegate_task` for bounded work.
- `agents/opencode.json` — the OpenCode `mcp` block to register the server.
- `agents/opencode-AGENTS.md` — the steer to paste into your project `AGENTS.md`,
since OpenCode takes its usage guidance from there.


## The `delegate_task` tool

```
delegate_task(task: str, context: str = "", model: str | None = None, reasoning_effort: str | None = None) -> DelegateTaskResult
```

- `task` — the scoped instruction for the worker.
- `context` — only what the worker needs. The local window is the scarce
  resource. Send the minimum.
- `model` — optional model id (see `list_models`). Omitted, the first model the
  engine reports is used.
- `reasoning_effort` — optional level taken from the chosen model's entry in
  `list_models`. Passed through unchanged. Omitted, the backend default applies.
  If the backend rejects the level, the result has `status: error` and a message
  so you can retry.

  This used to be a closed enum (`none | low | medium | high`). It isn't anymore.
  Different models advertise different ladders. OpenCode Go might offer
  `minimal`, `xhigh`, or `max`. Call `list_models` first and pick a level the
  model actually accepts. A level set without a model applies to the first model
  in the list, which may not advertise it.

  Some backends silently clamp a level rather than reject it. A requested `max`
  may run as `high`. The result envelope doesn't echo the applied level. Treat
  reasoning control as best-effort.

The response carries:

- `result` — a `WorkerResult` with `status`, `output`, `elapsed_s`, optional
  `token_usage`, and `error` (set when `status` is `error`).
- `model_context_size` — the declared window, so the caller can budget the next
  call.

## The `list_models` tool

```
list_models() -> list[{
  id: str,
  reasoning_levels: list[str],
  reasoning_default: str | None,
  reasoning_provenance: "advertised" | "assumed"
}]
```

Returns the models the engine reports from `/v1/models`, so the caller can pick
one and a reasoning level for `delegate_task`.

- `id` — the model identifier to pass to `delegate_task(model=...)`.
- `reasoning_levels` — the levels the model accepts for `reasoning_effort`.
- `reasoning_default` — the backend's advertised default level, when it declares one.
- `reasoning_provenance` — `advertised` when the levels came from the backend's
  metadata, or `assumed` when they are the provider's fallback set. Strata and
  Ollama don't advertise per-model reasoning ladders, so they use the fallback
  `none | low | medium | high`.

Raw provider metadata is trimmed. Costs, modalities, SDK hints: none of it
makes it into the response. Keeps the result small in the caller's context.

### A note on `model_context_size`

`model_context_size` a value set in config. The server does not read it
per model. The OpenAI-compatible `/v1/models` endpoint doesn't reliably report
context length across providers. So the operator declares one advisory window
that matches how the engine was launched. 

### Result status

| status        | meaning                                             |
|---------------|-----------------------------------------------------|
| `ok`          | the worker reported completed work                  |
| `needs_input` | the worker is blocked or found the task unclear     |
| `rejected`    | the worker judged the task infeasible               |
| `error`       | transport/engine failure, oversized context, or the runtime backstop fired |

## How the worker behaves

The worker runs under a system prompt with three jobs:

1. **Frame** — a focused worker doing one scoped task.
2. **Bound** — one scoped task, no scope creep. Text only until you grant it
   file or command access per call.
3. **Escape** — ambiguous, blocked, or impossible, it stops and self-reports
   instead of grinding on.

It self-reports by ending its reply with a status line, which the server maps to
a result status:

| marker               | mapped status |
|----------------------|---------------|
| `STATUS: COMPLETED`  | `ok`          |
| `STATUS: BLOCKED`    | `needs_input` |
| `STATUS: UNCLEAR`    | `needs_input` |
| `STATUS: INFEASIBLE` | `rejected`    |

Do not trust the self-report. A weak model can be confidently wrong. The caller
validates every result whatever the reported status says. Acceptance criteria
never go to the worker. The caller judges against them after the worker returns.

## File tools

By default the worker is text-only. Grant it directories per call and the server
fences it to them:

```
delegate_task(
  task, context,
  read_dirs_allowed=["/path/the/worker/may/read"],
  write_dirs_allowed=["/path/the/worker/may/write"],
  max_tool_rounds=8,
)
```

- `read_dirs_allowed` — grant a non-empty list and the worker gets a `read_file`
  tool scoped to those directories. Omit it and there is no read tool.
- `write_dirs_allowed` — same for `write_file`. Omit it and the worker cannot
  write anything.
- `max_tool_rounds` — how many tool calls the worker may make before the loop
  stops and hands back. Stops a confused model looping forever.

The result gains `files_written`, the paths the worker actually wrote, so you can
check the changes on disk.


- The allowlist you pass **is** the blast radius. The server lets the worker
  touch anything inside those directories and nothing outside them. 
- The server enforces the fence on every call. It resolves the real path first,
  so `..`, symlinks, and absolute paths that point outside the granted
  directories are refused. 
- Reads are fenced too
- You still validate. 


## Command tools

You can also let the worker run commands. An allowlist, not a shell. 

```
delegate_task(
  task, context,
  write_dirs_allowed=["/repo/scratch"],
  allowed_commands=["pytest -q", "ruff check ."],
  max_command_timeout_s=300,
)
```

- `allowed_commands` — the exact command strings the worker may run. Grant a
  non-empty list and the worker gets a `run_command` tool. Omit it and there is
  no command tool.
- `max_command_timeout_s` — the ceiling on a single command. The worker may ask
  for less per call. It cannot ask for more. A command that overruns is killed.
- `allowed_commands` needs a non-empty `write_dirs_allowed`. Commands run inside
  a granted write dir, so without one there is nowhere fenced to run.

The result gains `commands_run`, each command that actually ran with its exit
code, so you can see what happened without taking the worker's word for it.

## Development

```bash
uv run ruff check .
uv run pytest
```
