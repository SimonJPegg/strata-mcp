# Design

## Context

The worker already has fenced file tools (`read_file`, `write_file`) and runs a
bounded tool-use loop. This change adds a third tool, `run_command`, under the
same fence-and-loop model. The project has held a "no commands" invariant since
the first stage; this change reverses it deliberately, for the narrow case of a
caller pre-approving exact commands the worker may run.

The existing path fence (`resolve_within`) and the `max_tool_rounds` loop bound
are reused. The worker is a weak local model whose self-report is never trusted,
so every control here is caller-set and server-enforced.

## Goals / Non-Goals

**Goals:**
- Let the worker run commands the caller pre-approved, and react to their output
  in the same loop it uses for files.
- Keep the blast radius with the caller: the caller writes the exact commands and
  the working-directory fence; the worker only triggers.
- Make the dangerous paths unreachable rather than merely discouraged.

**Non-Goals:**
- A general shell. No pipes, redirection, chaining, or shell builtins.
- The worker composing or parameterising commands. It picks from a fixed menu.
- Network or package-install policy. Whatever the approved command does is the
  caller's judgement; the fence governs *which* command and *where*, not its
  effects.

## Decisions

**The menu, not the shell.** `allowed_commands` is a list of exact command
strings the caller writes. The worker runs one by matching it exactly. It cannot
add arguments or invent a command. This collapses the injection surface: the
worker never builds a command line, so argument injection, `git -c
core.pager=…`, and flag smuggling are not reachable. The power granted is "run
approved command N", not "construct a command".

**`shell=False`, always.** Each approved entry is parsed to an argv with `shlex`
and executed without a shell. Even though the caller wrote the string, running it
through a shell would let a careless entry do more than it reads. No shell means
the entry is exactly what runs — no globbing, no `;`, no `|`, no `>`.

**cwd inside the write fence.** Commands run with a working directory resolved
through the existing `resolve_within` against `write_dirs_allowed`. A non-empty
`allowed_commands` therefore requires a non-empty `write_dirs_allowed`: there is
always a fenced cwd, and never an "run in an unknown directory" default. The
worker may name which granted dir; absent one, the first is used.

**Worker picks the timeout, caller sets the ceiling.** The worker supplies a
per-command timeout so it can allow a slow test suite more time than a quick
lint. The server clamps it to `max_command_timeout_s`; a worker that omits one,
or asks for more, gets the ceiling. This keeps the "no hard wall-clock timeout on
the delegation" invariant intact — the delegation is still unbounded — while
bounding each command, so a hung process cannot stall the loop forever. A killed
command returns as a failed tool call.

**Scrubbed environment.** Commands run with a minimal environment rather than the
server's full env, so the worker cannot read ambient secrets (tokens, keys) that
happen to be exported, and env-var-based command hijacking (`GIT_PAGER`,
`PAGER`) has nothing to latch onto.

**`commands_run` on the result.** The result reports each executed command and
its exit code, alongside `files_written`. The caller validates against this, not
the worker's prose, which can be confidently wrong.

## Risks / Trade-offs

- **A dangerous command on the menu.** The fence governs which command and where,
  not what the command does. `rm -rf .` as an approved entry inside a write dir
  will delete that dir's contents. This is the caller's responsibility, and the
  README says so plainly — the same contract as the directory allowlist.
- **`shlex` parse vs the caller's intent.** Parsing the string to argv can differ
  from a shell's parse for exotic quoting. Accepted: the common case
  (`pytest -q`, `ruff check .`) parses identically, and refusing shell semantics
  is the point. A caller needing shell features writes a wrapper script and
  approves *that*.
- **No pipes means more rounds.** `a | b` becomes run `a`, run `b`, with the
  worker bridging. Costs loop rounds, bounded by `max_tool_rounds`. Accepted —
  it keeps the fence real rather than theatre.

## Open Questions

None. Version bumps to 0.3.0.
