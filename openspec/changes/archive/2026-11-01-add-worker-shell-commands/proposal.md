# Proposal

## Why

The worker can read and write files, but it cannot run anything. A caller who
wants it to do real grunt work — write a function, then run the tests; fix a
lint error, then re-run the linter — has to run the commands itself and feed the
output back by hand. That breaks the delegation: the loop the worker is good at
(act, see the result, act again) stops at the one step that proves the work.

Letting the worker run commands sounds dangerous, and a general shell would be.
But the common case is narrow: the caller already knows which commands are
safe — `pytest -q`, `ruff check .` — and wants the worker to run those and react
to the output. That is a menu the caller writes, not a shell the worker drives.

## What Changes

- The delegation tool accepts `allowed_commands`: an exact list of command
  strings the caller pre-approves. The worker is offered a `run_command` tool
  only when the list is non-empty.
- The worker may run a command only by matching an entry exactly. It cannot add
  arguments, compose commands, or invent one. The caller wrote the whole command
  line; the worker chooses which to run.
- Commands run with `shell=False` (parsed to argv via `shlex`), inside one of
  the granted write directories as the working directory, with a scrubbed
  environment. No shell interpretation, no pipes, no redirection, no chaining.
- The worker supplies a per-command timeout, clamped to a caller-set ceiling
  (`max_command_timeout_s`). A command that overruns is killed and reported as a
  failed tool call, not left to hang the delegation.
- The result gains `commands_run`: the commands that actually executed, with
  their exit codes, so the caller can see what happened without trusting the
  worker's account.
- `allowed_commands` requires a non-empty `write_dirs_allowed`, so there is
  always a fenced working directory. The text-only and file-only behaviours are
  unchanged when `allowed_commands` is omitted.

This reverses the long-standing "the worker never runs commands" invariant. That
is a deliberate, fenced evolution, not an accident, and the spec records it.

## Capabilities

### Modified Capabilities
- `worker-delegation`: the worker gains an opt-in, caller-fenced command-running
  capability; the "no commands" guarantee becomes "no commands unless the caller
  pre-approves an exact list".

## Impact

- `src/strata_mcp/`: a command-runner module (exact-match, `shlex` to argv,
  `shell=False`, cwd fenced via the existing `resolve_within`, timeout clamp,
  scrubbed env); `tools.py` gains a `run_command` spec and dispatch; `result.py`
  gains `commands_run`; `delegation.py` and `server.py` thread
  `allowed_commands` and `max_command_timeout_s` through the contract.
- README: the "it never runs commands" promise is replaced with the fenced
  command section; the agent prompts gain a line on the menu model.
- Version bumps to 0.3.0 (new capability).
- Security-sensitive: tests cover the sad paths — a command not on the menu, an
  attempt to add arguments, a non-zero exit, a timeout, and a cwd escape attempt.
