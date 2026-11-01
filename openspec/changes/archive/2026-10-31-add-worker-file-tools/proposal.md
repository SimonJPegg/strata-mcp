# Proposal

## Why

Stage 1 keeps the worker text-only: it answers, and the orchestrator writes any
files. That means the orchestrator pays (in its own expensive tokens) to apply
every change the worker describes. Giving the worker fenced file tools lets it
do the apply itself for bounded jobs, so the orchestrator only plans, sets the
boundary, and validates what came back. This is the planned second stage: the
worker gets hands, but only inside a box the caller draws.

## What Changes

- The worker can run a tool-use loop calling `read_file` and `write_file`, which
  the server executes and feeds back, until the worker finishes or the loop
  budget runs out.
- `delegate_task` gains `read_dirs_allowed`, `write_dirs_allowed`, and
  `max_tool_rounds`. The caller draws the fence and sets the loop budget.
- File tools are opt-in and fenced. A tool is offered only when its matching
  allowlist is non-empty. With neither allowlist set, the worker has no file
  tools and behaves exactly as Stage 1.
- The server enforces the fence. Every read and write path must resolve inside
  an allowed directory. Paths that escape (`..`, symlinks, absolute paths
  outside the fence) are refused.
- The result reports `files_written` so the orchestrator can validate on disk
  without re-reading everything.
- When the worker needs a directory or a tool it was not granted, it stops with
  `needs_input` and says what it needs, rather than failing or guessing.

## Capabilities

### New Capabilities
<!-- None. -->

### Modified Capabilities
- `worker-delegation`: the worker gains an opt-in, fenced file-tool loop; the
  delegation contract gains fence and loop-budget inputs and a written-files
  output.

## Impact

- `client.py`: support a tool-call loop over the OpenAI `tools` / `tool_calls`
  protocol (verified working on Strata and documented for Ollama).
- `server.py` / `delegation.py`: new tool-loop orchestration, fence enforcement,
  path validation, loop-round cap, and the new input/output fields.
- `result.py`: `files_written` on the result envelope.
- README: an explicit safety section on fencing, enforcement, and reads vs
  writes. Per-parameter descriptions carry the fence contract. The server
  instructions gain a short note that file access is opt-in.
- Release hygiene: remove the stale `0.1.0` assets left on the `0.1.1` GitHub
  release.
