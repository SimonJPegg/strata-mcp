# Proposal

## Why

Driving a capable cloud agent (Kiro) is expensive per token, yet much of the
work it does is bounded, well-specified grunt work that a local model could
handle for free. Strata runs a capable model locally and exposes an
OpenAI/Anthropic-compatible API on localhost. If Kiro can delegate bounded
subtasks to that local model and judge the results itself, the expensive agent
keeps the planning and judgement while the cheap local model does the apply —
cutting cost without giving up Kiro's oversight.

## What Changes

- Introduce `strata-mcp`: a Python MCP server that lets Kiro delegate a scoped
  task to a local Strata-backed worker and receive a structured result.
- Expose a single MCP tool, `delegate_task(task, context)`, that runs one
  self-contained completion against Strata's OpenAI-compatible endpoint and
  returns a `WorkerResult` envelope.
- The worker is text-only in this change: it produces an answer, it does
  not touch the filesystem or run commands. Kiro holds the pen — it writes
  files and validates the result.
- Liveness is handled by the worker self-reporting via its system prompt
  (completed / blocked / unclear / infeasible), not by streaming, timeouts, or
  GPU polling. Kiro validates every return regardless of what the worker claims.
- Connection details (base URL, optional runtime backstop, the loaded model's
  context size, optional API key for non-localhost use) live in a config file;
  the server surfaces the context size to the caller so it can budget how much
  to send. The model identifier is discovered from Strata's `/v1/models`
  endpoint rather than configured — Strata serves one loaded model.
- **Non-goals (this change):** a future stage where the worker gains
  filesystem/shell access and a sandbox, streaming, and out-of-band
  GPU-utilisation liveness. These are recorded as the intended future direction
  in the design, not built here.

## Capabilities

### New Capabilities
- `worker-delegation`: Kiro delegates a single scoped task to a local
  Strata-backed worker and receives a structured result it can judge. Owns the
  tool contract, the result envelope and its outcome states, the worker's
  self-reporting behaviour, and the plan/apply/validate loop semantics.
- `strata-connection`: How the server reaches the local Strata inference engine
  — OpenAI-compatible dialect, config-driven connection, and the failure modes
  (Strata unreachable, bad/empty response, oversized context) surfaced as
  structured results rather than crashes.

### Modified Capabilities
<!-- None. Greenfield repo with no existing specs. -->

## Impact

- **New project scaffold**: a `uv`-managed Python package implementing an MCP
  server (official MCP Python SDK), modelled with pydantic per project standards.
- **New dependencies**: the MCP Python SDK and an OpenAI-compatible HTTP client
  to call Strata. Pinned via `uv` with a committed lockfile for reproducible
  builds.
- **New config file**: connection settings (base URL — Strata default
  `http://127.0.0.1:8080/v1`, optional runtime backstop, model context size to
  match Strata's launch `--context`, optional API key). The model id is
  discovered at runtime from `/v1/models`, not configured.
- **Runtime dependency**: a running local Strata server (`strata launch`) with a
  model loaded, reachable over its OpenAI-compatible API.
- **No existing code affected** — the repository is currently empty.
