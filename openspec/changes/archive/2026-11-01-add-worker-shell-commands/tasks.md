# Tasks

## 1. Command runner

- [x] 1.1 Implement a command runner that takes an approved command string, parses it to an argv with `shlex`, and executes it with `shell=False`, a working directory resolved inside the granted write dirs via the existing `resolve_within` fence, and a scrubbed minimal environment, returning stdout/stderr/exit-code as a value (never raising); verify unit tests cover a successful run, a non-zero exit returned as a result, a cwd-escape attempt refused by the fence, and that no shell metacharacters in an entry are interpreted

## 2. Exact-match gate and timeout

- [x] 2.1 Gate execution on an exact match against `allowed_commands` (no prefix, no added arguments, no composition), returning a failed tool result for any non-match, and verify tests cover an exact match running, an allowed command with extra args refused, and an unlisted command refused
- [x] 2.2 Apply a per-command timeout: take the worker's requested timeout, clamp it to `max_command_timeout_s`, apply the ceiling when none is given, and terminate an overrunning command returning a failed tool result; verify tests cover clamp-to-ceiling, default-to-ceiling, and a timed-out command terminated as a failed result

## 3. Tool and result wiring

- [x] 3.1 Add a `run_command` tool spec and dispatch (offered only when `allowed_commands` is non-empty) into the existing tool-use loop, and verify a mocked-transport test runs a scripted command call through the loop and feeds the result back
- [x] 3.2 Add `commands_run` (each executed command with its exit code) to the result envelope and populate it from the loop, and verify a test asserts executed commands are reported

## 4. Contract and delegation

- [x] 4.1 Add `allowed_commands` and `max_command_timeout_s` to `run_delegation` and `delegate_task`, offering the command tool only when `allowed_commands` is non-empty, and rejecting the delegation when `allowed_commands` is set but `write_dirs_allowed` is empty; verify tests cover tool-offered-when-granted, no-tool-when-omitted, and the write-dir-required rejection

## 5. Documentation

- [x] 5.1 Replace the README's "it never runs commands" promise with a fenced command-running section (opt-in menu, exact-match only, no shell, cwd fence, clamped timeout, scrubbed env, the caller owns what the command does), add the contract to each new parameter's description, and add a one-line menu-model note to the agent prompts; verify the README and tool/param descriptions match the implemented contract

## 6. Integration

- [x] 6.1 Against live Strata, delegate a task with `allowed_commands` (e.g. a command that writes a known file) and a granted write dir, and verify the command ran, its effect appears on disk, `commands_run` lists it with its exit code, and an attempt to run an unlisted command is refused

## 7. Release

- [x] 7.1 Bump the version to 0.3.0 in `pyproject.toml`, confirm `uv sync --frozen`, `uv run ruff check .`, and `uv run pytest` all pass, then (user-run) tag and release 0.3.0
