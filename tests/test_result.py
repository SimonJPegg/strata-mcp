"""Tests for the WorkerResult envelope and status enum."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from strata_mcp.result import ReasoningEffort, WorkerResult, WorkerStatus


def test_ok_result_carries_output() -> None:
    result = WorkerResult(status=WorkerStatus.OK, output="done", elapsed_s=1.5)

    assert result.status is WorkerStatus.OK
    assert result.output == "done"
    assert result.elapsed_s == 1.5
    assert result.error is None


@pytest.mark.parametrize(
    "status",
    [WorkerStatus.OK, WorkerStatus.NEEDS_INPUT, WorkerStatus.REJECTED],
)
def test_non_error_statuses_do_not_require_message(status: WorkerStatus) -> None:
    result = WorkerResult(status=status, output="text")

    assert result.error is None


def test_invalid_status_is_rejected() -> None:
    with pytest.raises(ValidationError):
        WorkerResult(status="exploded", output="")


def test_error_status_requires_error_message() -> None:
    with pytest.raises(ValidationError):
        WorkerResult(status=WorkerStatus.ERROR)


def test_error_status_with_message_is_valid() -> None:
    result = WorkerResult(status=WorkerStatus.ERROR, error="Strata unreachable")

    assert result.status is WorkerStatus.ERROR
    assert result.error == "Strata unreachable"


def test_status_serialises_to_string_value() -> None:
    result = WorkerResult(status=WorkerStatus.NEEDS_INPUT, output="which file?")

    assert result.model_dump()["status"] == "needs_input"


def test_reasoning_effort_rejects_invalid_value() -> None:
    with pytest.raises(ValueError):
        ReasoningEffort("extreme")


def test_reasoning_effort_accepts_valid_values() -> None:
    assert ReasoningEffort("none") is ReasoningEffort.NONE
    assert ReasoningEffort("high") is ReasoningEffort.HIGH
