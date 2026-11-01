"""Tests proving the runner only executes exact-match, shell-free, fenced commands."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from strata_mcp.commands import effective_timeout_s, run_command_op


def test_exact_match_runs_and_captures_output(tmp_path: Path) -> None:
    outcome = run_command_op(
        command="echo hello",
        requested_timeout_s=10,
        allowed_commands=["echo hello"],
        write_dirs_allowed=[str(tmp_path)],
        max_timeout_s=30,
        cwd=str(tmp_path),
    )
    assert outcome.ok is True
    assert outcome.exit_code == 0
    assert outcome.stdout.strip() == "hello"
    assert outcome.command == "echo hello"
    assert outcome.error is None


@pytest.mark.parametrize(
    "command",
    [
        "echo hello world",  # allowed entry with extra args appended
        "echo hello; echo world",  # same entry plus shell metacharacters
        "ls",  # simply unlisted
        "echo hell",  # prefix of an allowed entry must not match
        "",  # empty command
    ],
)
def test_non_exact_command_is_refused(command: str, tmp_path: Path) -> None:
    outcome = run_command_op(
        command=command,
        requested_timeout_s=10,
        allowed_commands=["echo hello"],
        write_dirs_allowed=[str(tmp_path)],
        max_timeout_s=30,
        cwd=str(tmp_path),
    )
    assert outcome.ok is False
    assert outcome.exit_code is None
    assert "not in allowed list" in (outcome.error or "")


def test_nonzero_exit_is_a_successful_run(tmp_path: Path) -> None:
    outcome = run_command_op(
        command="false",
        requested_timeout_s=10,
        allowed_commands=["false"],
        write_dirs_allowed=[str(tmp_path)],
        max_timeout_s=30,
        cwd=str(tmp_path),
    )
    assert outcome.ok is True
    assert outcome.exit_code != 0


def test_cwd_outside_granted_dirs_is_refused(tmp_path: Path) -> None:
    outside = str(tmp_path.parent)  # parent contains tmp_path, so it is not inside it
    outcome = run_command_op(
        command="echo hello",
        requested_timeout_s=10,
        allowed_commands=["echo hello"],
        write_dirs_allowed=[str(tmp_path)],
        max_timeout_s=30,
        cwd=outside,
    )
    assert outcome.ok is False
    assert "cwd not within granted dirs" in (outcome.error or "")


def test_cwd_defaults_to_first_granted_dir(tmp_path: Path) -> None:
    outcome = run_command_op(
        command="echo hello",
        requested_timeout_s=10,
        allowed_commands=["echo hello"],
        write_dirs_allowed=[str(tmp_path)],
        max_timeout_s=30,
    )
    assert outcome.ok is True
    assert outcome.stdout.strip() == "hello"


@pytest.mark.parametrize(
    ("requested", "ceiling", "expected"),
    [(5, 30, 5), (60, 30, 30), (None, 30, 30), (0, 30, 30), (-1, 30, 30)],
)
def test_effective_timeout_is_clamped_to_ceiling(
    requested: int | None, ceiling: int, expected: int
) -> None:
    assert effective_timeout_s(requested, ceiling) == expected


def test_timeout_above_ceiling_is_clamped_in_practice(tmp_path: Path) -> None:
    started = time.monotonic()
    outcome = run_command_op(
        command="sleep 5",
        requested_timeout_s=100,  # far above the ceiling
        allowed_commands=["sleep 5"],
        write_dirs_allowed=[str(tmp_path)],
        max_timeout_s=1,
        cwd=str(tmp_path),
    )
    elapsed = time.monotonic() - started
    assert outcome.ok is False
    assert "timed out" in (outcome.error or "")
    assert elapsed < 3.0  # the 1s ceiling won, not the requested 100s


def test_shell_metacharacters_are_not_interpreted(tmp_path: Path) -> None:
    outcome = run_command_op(
        command="echo a; echo b",
        requested_timeout_s=10,
        allowed_commands=["echo a; echo b"],
        write_dirs_allowed=[str(tmp_path)],
        max_timeout_s=30,
        cwd=str(tmp_path),
    )
    assert outcome.ok is True
    assert outcome.exit_code == 0
    assert outcome.stdout.strip() == "a; echo b"  # one argv, literal text, no second command


def test_missing_executable_is_a_refusal_not_a_raise(tmp_path: Path) -> None:
    outcome = run_command_op(
        command="definitely-not-a-real-binary",
        requested_timeout_s=10,
        allowed_commands=["definitely-not-a-real-binary"],
        write_dirs_allowed=[str(tmp_path)],
        max_timeout_s=30,
        cwd=str(tmp_path),
    )
    assert outcome.ok is False
    assert "execution failed" in (outcome.error or "")


def test_unparseable_command_is_a_refusal_not_a_raise(tmp_path: Path) -> None:
    # An unbalanced quote makes shlex.split raise ValueError; it must map to a
    # refusal (failures are data in this runner), not crash the delegation.
    bad = 'echo "unterminated'
    outcome = run_command_op(
        command=bad,
        requested_timeout_s=10,
        allowed_commands=[bad],  # it is on the menu; parsing is what fails
        write_dirs_allowed=[str(tmp_path)],
        max_timeout_s=30,
        cwd=str(tmp_path),
    )
    assert outcome.ok is False
    assert outcome.exit_code is None
    assert "could not parse command" in (outcome.error or "")


@pytest.mark.parametrize(
    ("command", "allowed", "fragment"),
    [
        ("echo hello", ["echo hello"], "no write dirs granted"),
        ("ls", ["echo hello"], "not in allowed list"),
    ],
)
def test_missing_grant_is_a_refusal(
    command: str, allowed: list[str], fragment: str, tmp_path: Path
) -> None:
    # Commands only run inside a fenced cwd, so either missing grant refuses
    # before anything is executed.
    outcome = run_command_op(
        command=command,
        requested_timeout_s=10,
        allowed_commands=allowed,
        write_dirs_allowed=[],
        max_timeout_s=30,
        cwd=str(tmp_path),
    )

    assert outcome.ok is False
    assert outcome.exit_code is None
    assert fragment in (outcome.error or "")
