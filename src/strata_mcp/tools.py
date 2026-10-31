"""Builds the file-tool specs offered to the worker and dispatches their calls.

File tools are opt-in: a tool is only built when its directory allowlist is
non-empty, so a caller that grants nothing gets a plain text-only worker.
"""

from __future__ import annotations

from collections.abc import Callable

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


def build_tools(read_dirs_allowed: list[str], write_dirs_allowed: list[str]) -> list[dict]:
    """Return the tool specs for the granted file tools (empty when none granted)."""
    tools: list[dict] = []
    if read_dirs_allowed:
        tools.append(_READ_TOOL)
    if write_dirs_allowed:
        tools.append(_WRITE_TOOL)
    return tools


def make_dispatch(
    read_dirs_allowed: list[str], write_dirs_allowed: list[str]
) -> Callable[[str, dict], tuple[str, str | None]]:
    """Build a dispatcher that runs file tool calls through the fence.

    Returns (content_for_the_model, written_path_or_None). An unknown tool or a
    refused path comes back as content the worker can read and react to, never
    as a raised exception.
    """

    def dispatch(name: str, args: dict) -> tuple[str, str | None]:
        if name == "read_file" and read_dirs_allowed:
            outcome = read_file_op(str(args.get("path", "")), read_dirs_allowed)
            return (outcome.content if outcome.ok else f"ERROR: {outcome.error}", None)
        if name == "write_file" and write_dirs_allowed:
            outcome = write_file_op(
                str(args.get("path", "")), str(args.get("content", "")), write_dirs_allowed
            )
            if outcome.ok:
                return ("written", outcome.written_path)
            return (f"ERROR: {outcome.error}", None)
        return (f"ERROR: tool '{name}' is not available", None)

    return dispatch
