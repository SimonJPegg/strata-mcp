# Design

## Context

See proposal.md — Why. Stage 1 sends one completion and maps the reply to a
`WorkerResult`. Stage 2 adds a multi-round loop: the model may return
`tool_calls` (OpenAI function-calling, verified live on Strata — a probe
returned a well-formed `read_file` call with valid JSON args), the server runs
the call, appends the result as a `tool` message, and calls again. The worker is
a weak quantised model, so containment and bounds matter more than cleverness.

## Goals / Non-Goals

**Goals:**
- A bounded tool-use loop offering `read_file` / `write_file`, opt-in and fenced.
- The caller draws the fence (`read_dirs_allowed`, `write_dirs_allowed`) and sets
  the loop budget (`max_tool_rounds`); the server enforces both.
- `files_written` on the result for cheap on-disk validation.

**Non-Goals:**
- `web_search` or any network tool.
- Shell / command execution. "I need a command" escalates to the orchestrator.
- A sandbox the server owns: the caller chooses the directories, the server only
  enforces them. No scratch-dir promotion model.

## Decisions

### Caller sets policy, server enforces it
The caller passes the allowed directories and the round budget. The server
treats these as hard limits: file tools exist only when their allowlist is
non-empty, and every path is checked against the fence. This keeps strata-mcp a
mechanism, not a policy-maker, while guaranteeing a weak worker cannot climb out
of the box the caller drew.

### Path validation
Resolve the requested path to a real, absolute path (following symlinks), then
require it to be within one of the allowed directories (prefix check on the
resolved parent). Reject `..` traversal, symlink escape, and absolute paths
outside the fence. A refused path returns a failed `tool` result to the worker
(so it can adjust or escalate), never a silent pass and never a raised
exception to the caller.

### Opt-in degrades to Stage 1
No allowlists means no file tools offered, which is exactly the Stage 1
text-only worker. Stage 2 is a strict superset: existing callers that pass
neither field get unchanged behaviour.

### Loop bound is rounds, not wall-clock
`max_tool_rounds` caps iterations, distinct from the (absent) wall-clock
timeout. A slow-but-progressing call is still never killed on time; a
round-looping worker is stopped on count. On reaching the cap the server returns
the work so far with the normal status mapping.

### Escalation reuses `needs_input`
An ungranted directory or an unavailable capability is a blocked state, which
`needs_input` already models. The worker says what it needs in its output; no
new status value. Keeps the envelope stable.

### Contract changes
Input: `read_dirs_allowed: list[str] = []`, `write_dirs_allowed: list[str] = []`,
`max_tool_rounds: int = <default>`. Output: `files_written: list[str]` on the
result. Per-parameter descriptions carry the fence contract (on the wire where
the host surfaces them); the dense server `instructions` gain only a short
"file access is opt-in" clause; the README carries the full safety writeup.

## Risks / Trade-offs

- **Caller draws a reckless fence** (e.g. repo root, or `/`) → the worker can
  write widely. Mitigation: the server still enforces *that* fence exactly, and
  the README is explicit that the allowlist is the blast radius — choose it
  tightly. The server cannot second-guess a caller's intent, only contain it.
- **Weak model mis-uses tools in a loop** (wrong paths, repeated calls, malformed
  args) → Mitigation: fence refusals come back as failed tool calls the worker
  can react to; `max_tool_rounds` stops runaway loops; the caller validates
  `files_written` regardless.
- **Partial writes on an aborted loop** → files written before the cap/abort
  remain on disk. Mitigation: `files_written` reports them so the caller can
  inspect or roll back; the caller owns the real tree.
- **read_file leaks sensitive files into worker/output** → Mitigation: reads are
  fenced too; the caller must grant read dirs explicitly.

## Open Questions

- Default value for `max_tool_rounds` (candidate: a small number like 8-10,
  matching common practice). Does not change the approach; settle during build.
- Whether `write_file` should create missing parent dirs inside the fence, or
  only write to existing ones. Lean: create within the fence. Settle during build.
