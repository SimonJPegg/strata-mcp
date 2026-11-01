"""The system prompt that frames the Strata worker and bounds its behaviour."""

from __future__ import annotations

from strata_mcp.mapping import (
    MARKER_BLOCKED,
    MARKER_COMPLETED,
    MARKER_INFEASIBLE,
    MARKER_UNCLEAR,
)


def _tool_clause(has_read: bool, has_write: bool, has_commands: bool) -> str:
    """State the worker's granted tools, or the no-tools bound when none are granted.

    The prompt must not claim 'no tools' while the caller hands the worker
    fenced tools in the same call, so the clause is built from what was granted.
    """
    granted: list[str] = []
    if has_read:
        granted.append("read_file")
    if has_write:
        granted.append("write_file")
    if has_commands:
        granted.append("run_command")
    if not granted:
        return (
            "You have no filesystem, shell, or tools. Answer as text only. Do "
            "not ask for tools you lack or expand scope."
        )
    names = ", ".join(granted)
    return (
        f"Granted tools: {names}. Paths and commands are fenced to what the "
        "caller allowed; a refused call comes back as an error, not a crash — "
        "react to it, do not retry blindly. Use only granted tools; do not "
        "expand scope."
    )


def build_system_prompt(
    has_read: bool = False,
    has_write: bool = False,
    has_commands: bool = False,
) -> str:
    """Build the worker system prompt: frame, bound to granted tools, escape hatch."""
    return f"""You are a focused worker. A senior engineer delegated ONE scoped \
task. Do exactly that task, nothing more.

{_tool_clause(has_read, has_write, has_commands)}

End your reply with one status line:
- "{MARKER_COMPLETED}" task done.
- "{MARKER_BLOCKED}" cannot continue without more info; state what you need.
- "{MARKER_UNCLEAR}" task ambiguous; state what is unclear.
- "{MARKER_INFEASIBLE}" task cannot be done; state why.

Stuck, unsure, or ambiguous: STOP and report with the matching status line \
rather than guessing. A clear question beats a confident wrong answer."""
