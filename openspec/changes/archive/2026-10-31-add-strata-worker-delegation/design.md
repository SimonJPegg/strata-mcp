# Design

## Context

See proposal.md — Why. Strata runs a local model behind an OpenAI/Anthropic
compatible API on localhost; it pre-loads a single model and does not hot-swap.
The repository is empty, so this is a greenfield Python project built to the
project's standards (pydantic, loguru, pytest, functional style). The server is
pure I/O orchestration: parse a tool call, shape a prompt, make one HTTP call,
wait, return a structured result.

This change delivers the first of two planned stages:

- **Stage 1 (this change): text-only worker.** The worker produces an answer
  and does not touch the filesystem or run commands. Kiro writes any files and
  validates the result.
- **Stage 2 (future, out of scope here): worker with hands.** The worker gains
  filesystem and shell tools inside a sandbox and edits files directly; Kiro
  validates the result on disk.

The Stage 1 tool contract is a strict subset of Stage 2 so the later stage
extends it rather than replaces it.

## Goals / Non-Goals

**Goals:**
- A `strata-mcp` MCP server exposing one tool, `delegate_task(task, context)`.
- A single blocking completion against Strata's OpenAI-compatible endpoint.
- A `WorkerResult` envelope that makes every outcome — including failure —
  first-class data rather than an exception.
- A worker system prompt that frames the worker, bounds it to the task, and
  tells it to stop and self-report when stuck or unclear.

**Non-Goals:**
- Streaming tokens back to the host.
- Worker filesystem/shell access or a sandbox (Stage 2).

## Decisions

### Language and dialect
Python, using the MCP Python SDK and pydantic for the contract and payloads.
The server calls Strata over its OpenAI-compatible chat-completions API.

### One tool, `delegate_task(task, context)`
Input is lean: `task` (the scoped instruction) and `context` (only the snippets
the worker needs). The local model's context window is the scarce resource, so
the caller sends the minimum required. Acceptance criteria are not sent to the
worker; the caller judges against them after the worker returns.

### Result envelope with first-class outcome status
`WorkerResult { status, output, elapsed_s, token_usage?, error? }` where
`status ∈ {ok, needs_input, rejected, error}`. `elapsed_s` reports call duration;
`token_usage` aids debugging. Failures return as data, not exceptions, so the
caller's validation step branches on the outcome. The status values map to the
worker's self-reported endings (completed → ok, blocked/unclear → needs_input,
infeasible → rejected) plus transport/engine failures (→ error).

### Liveness by self-report
The worker's system prompt instructs it to stop and return early with a specific
question when a task is ambiguous or it is stuck, rather than continuing
indefinitely. A stuck worker thus returns a normal result the caller can act on.
There is no enforced wall-clock timeout; an optional, generous max-runtime
backstop in config guards against an indefinite block.

### Config file for connection
Base URL (Strata default `http://127.0.0.1:8080/v1`), the optional max-runtime
backstop, the loaded model's context size, and an optional API key (for
non-localhost use; localhost needs none) live in a TOML config file parsed with
the stdlib `tomllib`. The server surfaces the declared context size to the
caller at call time so the caller can budget how much `context` to send; the
size is advisory, with the oversized-context error as the backstop. The model
identifier is discovered at runtime from Strata's `/v1/models` endpoint rather
than configured, since Strata serves one loaded model. The configured context
size must match the `--context` Strata was launched with.

## Risks / Trade-offs

- **Weak-model metacognition** → self-report catches honest confusion but not
  confidently wrong output. Mitigation: the caller validates every return
  regardless of the reported status.
- **No automatic wedge detection** → a truly wedged worker blocks the host until
  it returns. Mitigation: heartbeat log lines so the operator can see the call
  is alive and interrupt it; the optional config backstop bounds the worst case.
- **Oversized context** → the local window is small; too much `context`
  truncates or errors. Mitigation: the caller budgets against the declared
  context size the server surfaces and sends the minimum needed; the server
  returns an `error` result rather than crashing.
- **Misused delegation** → judgement-heavy or ambiguous work produces poor
  results on a weak local model. Mitigation: usage guidance — good candidates
  are bounded, well-specified, low-ambiguity tasks.

## Migration Plan

Greenfield; nothing to migrate. Stage 2 adds worker tools (read/write/shell)
inside the same `delegate_task` contract plus a sandbox; the envelope already
carries the fields Stage 2 needs.

## Open Questions

- Whether Strata's `/v1/models` reports the model's context length, or whether
  the config-declared size is the only source. Either way the config value is
  authoritative for budgeting; this only affects whether the server can
  cross-check it. Build-time check.
