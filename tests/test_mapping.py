"""Tests for mapping a worker's self-reported ending to an envelope status."""

from __future__ import annotations

import pytest

from strata_mcp.errors import StrataUnreachableError
from strata_mcp.mapping import (
    MARKER_BLOCKED,
    MARKER_COMPLETED,
    MARKER_INFEASIBLE,
    MARKER_UNCLEAR,
    error_result,
    status_from_output,
)
from strata_mcp.result import WorkerStatus


@pytest.mark.parametrize(
    ("marker", "expected"),
    [
        (MARKER_COMPLETED, WorkerStatus.OK),
        (MARKER_BLOCKED, WorkerStatus.NEEDS_INPUT),
        (MARKER_UNCLEAR, WorkerStatus.NEEDS_INPUT),
        (MARKER_INFEASIBLE, WorkerStatus.REJECTED),
    ],
)
def test_marker_maps_to_expected_status(marker: str, expected: WorkerStatus) -> None:
    output = f"some work here\n{marker}"

    assert status_from_output(output) == expected


def test_missing_marker_defaults_to_ok() -> None:
    assert status_from_output("just some output, no marker") is WorkerStatus.OK


def test_unrecognised_marker_defaults_to_ok() -> None:
    assert status_from_output("STATUS: WOBBLY") is WorkerStatus.OK


def test_transport_failure_maps_to_error_result() -> None:
    result = error_result(StrataUnreachableError("http://127.0.0.1:8080/v1"), elapsed_s=2.0)

    assert result.status is WorkerStatus.ERROR
    assert result.elapsed_s == 2.0
    assert result.error is not None
    assert "could not reach Strata" in result.error
