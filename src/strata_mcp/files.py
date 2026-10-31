"""Fenced file access for the worker: paths must resolve within allowed dirs."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

from strata_mcp.errors import PathNotAllowedError


class ToolOutcome(BaseModel):
    """Result of a file tool operation; failures are data, never raised."""

    ok: bool
    content: str = ""
    error: str | None = None
    written_path: str | None = None


def resolve_within(requested: str, allowed_dirs: list[str]) -> Path:
    """Resolve a path and return it only if it sits within an allowed dir.

    Resolves symlinks and `..` to a real absolute path first, so escapes
    cannot slip through. An empty allowlist allows nothing.
    """
    resolved = Path(requested).resolve()
    for allowed in allowed_dirs:
        allowed_resolved = Path(allowed).resolve()
        if resolved == allowed_resolved or resolved.is_relative_to(allowed_resolved):
            return resolved
    raise PathNotAllowedError(requested)


def read_file_op(path: str, read_dirs_allowed: list[str]) -> ToolOutcome:
    """Read a UTF-8 file if it resolves within the allowed read dirs."""
    try:
        resolved = resolve_within(path, read_dirs_allowed)
    except PathNotAllowedError as exc:
        return ToolOutcome(ok=False, error=str(exc))
    try:
        text = resolved.read_text(encoding="utf-8")
    except OSError as exc:
        return ToolOutcome(ok=False, error=str(exc))
    return ToolOutcome(ok=True, content=text)


def write_file_op(path: str, content: str, write_dirs_allowed: list[str]) -> ToolOutcome:
    """Write UTF-8 content to a file if it resolves within the allowed write dirs."""
    try:
        resolved = resolve_within(path, write_dirs_allowed)
    except PathNotAllowedError as exc:
        return ToolOutcome(ok=False, error=str(exc))
    try:
        # The parent is created inside the fence: resolved is already proven to
        # sit within an allowed dir, so its parent does too.
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(content, encoding="utf-8")
    except OSError as exc:
        return ToolOutcome(ok=False, error=str(exc))
    return ToolOutcome(ok=True, written_path=str(resolved))
