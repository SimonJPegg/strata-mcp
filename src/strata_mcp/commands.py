"""Fenced command runner: only exact-match, pre-approved commands run, never via a shell."""

from __future__ import annotations

import shlex
import subprocess
from pathlib import Path

from pydantic import BaseModel

from strata_mcp.errors import PathNotAllowedError
from strata_mcp.files import resolve_within

# A scrubbed env keeps parent-process secrets and PATH hijacks out of worker commands.
_SCRUBBED_ENV: dict[str, str] = {
    "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
}


class CommandOutcome(BaseModel):
    """Records a run so the caller, not the runner, judges non-zero exits."""

    ok: bool
    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = None
    command: str = ""
    error: str | None = None


def effective_timeout_s(requested_timeout_s: int | None, max_timeout_s: int) -> int:
    """Clamp a caller's timeout to the ceiling so no run can outlive the budget."""
    if requested_timeout_s is None or requested_timeout_s <= 0:
        return max_timeout_s
    return min(requested_timeout_s, max_timeout_s)


def _refusal(command: str, reason: str) -> CommandOutcome:
    """Give every refusal the same shape so the worker reads a consistent failure."""
    return CommandOutcome(ok=False, command=command, error=reason)


def _resolve_cwd(cwd: str | None, write_dirs_allowed: list[str]) -> Path:
    """Fence the working directory inside the granted write dirs (first dir by default)."""
    requested = cwd if cwd is not None else write_dirs_allowed[0]
    return resolve_within(requested, write_dirs_allowed)


def _parse_argv(command: str) -> list[str]:
    """Split an approved command into argv without a shell; raises ValueError on bad quoting."""
    return shlex.split(command)


def _run_argv(argv: list[str], workdir: Path, timeout_s: int) -> subprocess.CompletedProcess[str]:
    """Execute argv with no shell and a scrubbed environment, capturing output.

    The environment is rebuilt from the allowlist so the worker cannot inherit
    secrets (e.g. an API key) from the host process.
    """
    return subprocess.run(
        argv,
        shell=False,
        cwd=str(workdir),
        env=dict(_SCRUBBED_ENV),
        capture_output=True,
        text=True,
        timeout=timeout_s,
        check=False,
    )


def _completed_outcome(command: str, completed: subprocess.CompletedProcess[str]) -> CommandOutcome:
    """Wrap a finished run in an ok outcome, keeping its exit code."""
    return CommandOutcome(
        ok=True,
        stdout=completed.stdout,
        stderr=completed.stderr,
        exit_code=completed.returncode,
        command=command,
    )


def _execute(command: str, workdir: Path, timeout_s: int) -> CommandOutcome:
    """Run argv with shell=False, turning timeout and OSError into refusals, not raises."""
    try:
        argv = _parse_argv(command)
    except ValueError as exc:
        # An unbalanced quote or trailing backslash in the approved string is a
        # refusal, not a crash: failures are data in this runner.
        return _refusal(command, f"could not parse command: {exc}")
    try:
        completed = _run_argv(argv, workdir, timeout_s)
    except subprocess.TimeoutExpired:
        return _refusal(command, f"timed out after {timeout_s}s")
    except OSError as exc:
        return _refusal(command, f"execution failed: {exc}")
    return _completed_outcome(command, completed)


def _grant_refusal(
    command: str,
    allowed_commands: list[str],
    write_dirs_allowed: list[str],
) -> str | None:
    """Return why the caller's grants do not allow this command, or None if they do."""
    if command not in allowed_commands:
        return f"command not in allowed list: {command!r}"
    if not write_dirs_allowed:
        return "no write dirs granted for command cwd"
    return None


def run_command_op(
    command: str,
    requested_timeout_s: int | None,
    allowed_commands: list[str],
    write_dirs_allowed: list[str],
    max_timeout_s: int,
    cwd: str | None = None,
) -> CommandOutcome:
    """Run a caller-approved command only on exact string match, never raising at the caller."""
    refusal = _grant_refusal(command, allowed_commands, write_dirs_allowed)
    if refusal is not None:
        return _refusal(command, refusal)
    try:
        workdir = _resolve_cwd(cwd, write_dirs_allowed)
    except PathNotAllowedError as exc:
        return _refusal(command, f"cwd not within granted dirs: {exc}")
    return _execute(command, workdir, effective_timeout_s(requested_timeout_s, max_timeout_s))
