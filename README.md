# strata-mcp

An MCP server that hands a scoped task to a local model and returns a structured
result.

Intended to be run from within Kiro/ClaudeCode/OpenCode/Whatever. Plan and chat with
the expensive LLM, pass the grunt work to the free (*cough* electric *cough*) one.

Your local model is slower, but that's the price you pay.

The worker is text-only by default. Grant it directories per call and it can
read and write files inside them, fenced (see File tools). It never runs
commands.

## Prerequisites

- [`uv`](https://docs.astral.sh/uv/) for dependency management.
- A running Strata server with a model loaded, reachable over its
  OpenAI-compatible API. For example:

  ```bash
  strata launch --family qwen --model q2_0 --context 32k --yes --no-tui
  ```

  Check it is up, and note the address, model, and whether a key is required:

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

The server reads a TOML config file, discovered in this order:

1. the path in `STRATA_MCP_CONFIG`, if set
2. otherwise `~/.config/strata-mcp/config.toml` (honouring `XDG_CONFIG_HOME`)

```toml
# ~/.config/strata-mcp/config.toml  (or the path in STRATA_MCP_CONFIG)
# Strata's OpenAI-compatible base URL (default shown).
base_url = "http://127.0.0.1:8080/v1"

# The context length Strata was launched with (its --context value).
# Surfaced to the caller so it can budget how much to send. Advisory.
model_context_size = 32768

# Optional safety backstop in seconds. Omit for no time limit.
# max_runtime_s = 3600

# Optional sampling temperature on every completion (0.0-2.0). Defaults to 0.0
# so the worker is literal. 0.0 removes sampling randomness but does not
# guarantee identical output on MoE models, whose expert routing still varies.
# temperature = 0.0

# Required only when Strata runs with a key (its /health reports
# "api_key": true, and /v1/models returns 401 without one).
# api_key = "your-strata-api-key"
```

The model id is discovered from `GET /v1/models`. You do not configure it.

## Run

Installed, with a config file at the discovered location, it runs as a plain
command speaking MCP over stdio:

```bash
strata-mcp
```

From a checkout, or to point at a specific config file:

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

Registering the server is half the job. The host agent also has to reach for it.
The `agents/` folder has starting configs that register strata-mcp and steer the
agent to delegate bounded grunt work rather than burn its own context on it:

- `agents/kiro-agent.json` — a Kiro agent that registers the server and carries
  a prompt biasing it toward `delegate_task` for bounded work.
- `agents/opencode.json` — the OpenCode `mcp` block to register the server.
- `agents/opencode-AGENTS.md` — the steer to paste into your project `AGENTS.md`,
  since OpenCode takes its usage guidance from there.

These bias the agent toward delegating. They do not force it. The habit lives in
the prompt, the mechanism lives in the server.

## The `delegate_task` tool

```
delegate_task(task: str, context: str = "", model: str | None = None, reasoning_effort: str | None = None) -> DelegateTaskResult
```

- `task` — the scoped instruction for the worker.
- `context` — only what the worker needs. The local window is the scarce
  resource. Send the minimum.
- `model` — optional model id (see `list_models`). Omitted, the first model the
  engine reports is used.
- `reasoning_effort` — optional, one of `none | low | medium | high`. One
  thinking control across backends: Strata and Ollama both honour
  `reasoning_effort` on the OpenAI-compatible endpoint, and `none` turns the
  reasoning phase off for fast bounded tasks. Omitted, the backend default
  applies (thinking on). It is best-effort and depends on the model. Some ignore
  the levels, and this Qwen treats `low` and `medium` the same.

The response carries:

- `result` — a `WorkerResult` with `status`, `output`, `elapsed_s`, optional
  `token_usage`, and `error` (set when `status` is `error`).
- `model_context_size` — the declared window, so the caller can budget the next
  call.

## The `list_models` tool

```
list_models() -> list[str]
```

Returns the model ids the engine reports from `/v1/models`, so the caller can
pick one for `delegate_task`. Strata serves one model, so you get one id. Ollama
serves many, so you get the lot and choose.

### A note on `model_context_size`

`model_context_size` is one value you set in config. The server does not read it
per model from the engine, on purpose. The OpenAI-compatible `/v1/models`
endpoint does not reliably report context length. Strata gives it, Ollama does
not and will silently truncate to an internal default. So the operator declares
one advisory window that matches how the engine was launched. Pick a model whose
real window differs and the configured value is still what gets surfaced and used
for the oversized-context guard.

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

By default the worker is text-only. If you want it to read or write files, you
grant directories per call and the server fences it to them:

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

Read this part carefully, because it is where the blast radius lives:

- The allowlist you pass **is** the blast radius. The server will let the worker
  touch anything inside those directories and nothing outside them. Pass the
  repo root and a confused model can scribble over the repo. Pass a scratch dir
  and the damage is contained to the scratch dir. Choose tight.
- The server enforces the fence on every call. It resolves the real path first,
  so `..`, symlinks, and absolute paths that point outside the granted
  directories are refused. A refused path comes back to the worker as a failed
  tool call, not a crash, and not a silent escape.
- Reads are fenced too, not just writes. A worker with a read tool pointed at
  your home directory can read your keys and leak them into its output. Grant
  read dirs as tightly as write dirs.
- You still validate. The worker having hands does not make it trustworthy. It
  writes into the box you drew, you check `files_written` and the files
  themselves, and you decide what to keep.

## Command tools

You can also let the worker run commands. Not a shell — a menu. You pre-approve
the exact commands, the worker picks from them:

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

This is the tightest fence in the project, and it has to be, because a command
is the widest blast radius:

- The worker runs a command only by matching an entry **exactly**. It cannot add
  an argument, cannot chain, cannot invent one. You wrote the whole command line.
  The worker only chooses which to run.
- There is no shell. The command is split to an argument list and run directly,
  so `;`, `|`, `>`, globs, and `&&` are not interpreted. An entry like
  `echo a; echo b` prints that literal string. It does not run two commands.
- Commands run in a granted write dir with a scrubbed environment, so the worker
  cannot read ambient secrets out of your shell or hijack a command through an
  environment variable.
- The fence governs **which** command and **where**, not what the command does.
  Approve `rm -rf .` and it will delete the contents of the write dir you gave
  it. The safety is that you write the command, not the worker. Approve only
  commands you would run yourself.

## Development

```bash
uv run ruff check .
uv run pytest
```
