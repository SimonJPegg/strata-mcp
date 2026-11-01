"""Builds the tool specs offered to the worker and dispatches their calls.

Tools are opt-in: a tool is only built when its grant is non-empty, so a caller
that grants nothing gets a plain text-only worker. File access needs a directory
allowlist; command running needs a non-empty command menu plus a write dir.
"""

from __future__ import annotations

from strata_mcp.client import CommandRun, ToolDispatch, ToolEffect, WireObject
from strata_mcp.commands import CommandOutcome, run_command_op
from strata_mcp.files import read_file_op, write_file_op

_READ_TOOL = {
    "type": "function",
    "function": {
        "name": "read_file",
        "description": "Read a UTF-8 text file. Only paths inside granted dirs are allowed.",
        "parameters": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
}

_WRITE_TOOL = {
    "type": "function",
    "function": {
        "name": "write_file",
        "description": "Write a UTF-8 text file. Only paths inside granted dirs are allowed.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
        },
    },
}

_RUN_COMMAND_TOOL = {
    "type": "function",
    "function": {
        "name": "run_command",
        "description": (
            "Run a pre-approved command. 'command' must EXACTLY match an allowed "
            "entry; you cannot add arguments or compose. Optional timeout_s is "
            "clamped to the caller's ceiling. Returns stdout, stderr, exit code."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "command": {"type": "string"},
                "timeout_s": {"type": "integer"},
            },
            "required": ["command"],
        },
    },
}


def build_tools(
    read_dirs_allowed: list[str],
    write_dirs_allowed: list[str],
    allowed_commands: list[str],
) -> list[WireObject]:
    """Return the tool specs for the granted tools (empty when none granted)."""
    tools: list[WireObject] = []
    if read_dirs_allowed:
        tools.append(_READ_TOOL)
    if write_dirs_allowed:
        tools.append(_WRITE_TOOL)
    if allowed_commands:
        tools.append(_RUN_COMMAND_TOOL)
    return tools


def _dispatch_read(
    args: WireObject,
    read_dirs_allowed: list[str],
) -> tuple[str, ToolEffect | None]:
    """Run a read_file call through the fence, returning content or an error string."""
    outcome = read_file_op(str(args.get("path", "")), read_dirs_allowed)
    return (outcome.content if outcome.ok else f"ERROR: {outcome.error}", None)


def _dispatch_write(
    args: WireObject,
    write_dirs_allowed: list[str],
) -> tuple[str, ToolEffect | None]:
    """Run a write_file call through the fence, reporting the written path on success."""
    outcome = write_file_op(
        str(args.get("path", "")), str(args.get("content", "")), write_dirs_allowed
    )
    if outcome.ok:
        return ("written", ToolEffect(written_path=outcome.written_path))
    return (f"ERROR: {outcome.error}", None)


def _requested_timeout(args: WireObject) -> int | None:
    """Read the optional timeout_s from a tool call's arguments.

    Anything the model sends is untrusted: only a real integer counts as a
    requested timeout. A bool is rejected because `true` is not a duration, and
    a non-int leaves the caller's cap in effect rather than guessing.
    """
    timeout = args.get("timeout_s")
    if isinstance(timeout, int) and not isinstance(timeout, bool):
        return timeout
    return None


def _dispatch_command(
    args: WireObject,
    allowed_commands: list[str],
    write_dirs_allowed: list[str],
    max_command_timeout_s: int,
) -> tuple[str, ToolEffect | None]:
    """Run a run_command call through the exact-match, shell-free, fenced runner."""
    outcome = run_command_op(
        command=str(args.get("command", "")),
        requested_timeout_s=_requested_timeout(args),
        allowed_commands=allowed_commands,
        write_dirs_allowed=write_dirs_allowed,
        max_timeout_s=max_command_timeout_s,
    )
    if not outcome.ok:
        return (f"ERROR: {outcome.error}", None)
    return (_command_report(outcome), _command_effect(outcome))


def _command_report(outcome: CommandOutcome) -> str:
    """Render a finished command so the worker can read exit code and output."""
    return f"exit={outcome.exit_code}\nstdout:\n{outcome.stdout}\nstderr:\n{outcome.stderr}"


def _command_effect(outcome: CommandOutcome) -> ToolEffect:
    """Record which approved command ran and its exit code, for the caller."""
    return ToolEffect(command_run=CommandRun(command=outcome.command, exit_code=outcome.exit_code))


def make_dispatch(
    read_dirs_allowed: list[str],
    write_dirs_allowed: list[str],
    allowed_commands: list[str],
    max_command_timeout_s: int,
) -> ToolDispatch:
    """Build a dispatcher that runs granted tool calls through their fences.

    Returns (content_for_the_model, effect_or_None). An unknown tool or a refused
    operation comes back as content the worker can read and react to, never as a
    raised exception.
    """

    def dispatch(name: str, args: WireObject) -> tuple[str, ToolEffect | None]:
        if name == "read_file" and read_dirs_allowed:
            return _dispatch_read(args, read_dirs_allowed)
        if name == "write_file" and write_dirs_allowed:
            return _dispatch_write(args, write_dirs_allowed)
        if name == "run_command" and allowed_commands:
            return _dispatch_command(
                args, allowed_commands, write_dirs_allowed, max_command_timeout_s
            )
        return (f"ERROR: tool '{name}' is not available", None)

    return dispatch
