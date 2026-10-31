"""Maps a worker's self-reported ending marker to an envelope status.

The worker is instructed (see prompt.py) to end its reply with one of a small
set of markers. The caller cannot trust these as correct, but they let the
envelope carry the worker's intent so Kiro can branch on it.
"""

from __future__ import annotations

from strata_mcp.errors import StrataClientError
from strata_mcp.result import WorkerResult, WorkerStatus

# Markers the worker is told to emit. Kept here so the prompt and the mapper
# share one source of truth.
MARKER_COMPLETED = "STATUS: COMPLETED"
MARKER_BLOCKED = "STATUS: BLOCKED"
MARKER_UNCLEAR = "STATUS: UNCLEAR"
MARKER_INFEASIBLE = "STATUS: INFEASIBLE"

_MARKER_TO_STATUS = {
    MARKER_COMPLETED: WorkerStatus.OK,
    MARKER_BLOCKED: WorkerStatus.NEEDS_INPUT,
    MARKER_UNCLEAR: WorkerStatus.NEEDS_INPUT,
    MARKER_INFEASIBLE: WorkerStatus.REJECTED,
}


def status_from_output(output: str) -> WorkerStatus:
    """Infer the status from the worker's self-reported marker.

    A missing or unrecognised marker is treated as completed work: the output
    still stands and Kiro validates it regardless of the claimed status.
    """
    for marker, status in _MARKER_TO_STATUS.items():
        if marker in output:
            return status
    return WorkerStatus.OK


def error_result(exc: StrataClientError, elapsed_s: float) -> WorkerResult:
    """Build an error envelope from a client failure, preserving elapsed time."""
    return WorkerResult(
        status=WorkerStatus.ERROR,
        elapsed_s=elapsed_s,
        error=str(exc),
    )
