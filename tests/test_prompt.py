"""Tests that the worker system prompt contains its three required jobs."""

from __future__ import annotations

from strata_mcp.mapping import (
    MARKER_BLOCKED,
    MARKER_COMPLETED,
    MARKER_INFEASIBLE,
    MARKER_UNCLEAR,
)
from strata_mcp.prompt import build_system_prompt


def test_prompt_frames_the_worker() -> None:
    prompt = build_system_prompt().lower()

    assert "focused worker" in prompt
    assert "one" in prompt and "task" in prompt


def test_prompt_bounds_the_worker_to_no_tools_by_default() -> None:
    prompt = build_system_prompt().lower()

    assert "no filesystem, shell, or tools" in prompt
    assert "text only" in prompt


def test_prompt_names_granted_tools_instead_of_denying_them() -> None:
    # The prompt must not claim 'no tools' when the caller granted some.
    prompt = build_system_prompt(has_read=True, has_write=True, has_commands=True)

    assert "read_file" in prompt
    assert "write_file" in prompt
    assert "run_command" in prompt
    assert "fenced" in prompt
    assert "text only" not in prompt.lower()


def test_prompt_lists_only_granted_tools() -> None:
    prompt = build_system_prompt(has_write=True)

    assert "write_file" in prompt
    assert "read_file" not in prompt
    assert "run_command" not in prompt


def test_prompt_gives_an_escape_hatch() -> None:
    prompt = build_system_prompt().lower()

    assert "stop" in prompt
    assert "rather than guessing" in prompt or "rather than" in prompt


def test_prompt_lists_every_status_marker() -> None:
    prompt = build_system_prompt()

    for marker in (MARKER_COMPLETED, MARKER_BLOCKED, MARKER_UNCLEAR, MARKER_INFEASIBLE):
        assert marker in prompt
