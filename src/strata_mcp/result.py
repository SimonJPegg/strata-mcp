"""The structured result envelope returned for every delegation."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, model_validator

from strata_mcp.client import TokenUsage
from strata_mcp.errors import MissingErrorMessageError


class WorkerStatus(StrEnum):
    """The outcome of a delegation, which the caller branches on.

    OK: worker completed. NEEDS_INPUT: blocked/unclear, asked a question.
    REJECTED: worker judged the task infeasible. ERROR: transport/engine
    failure before or during the call.
    """

    OK = "ok"
    NEEDS_INPUT = "needs_input"
    REJECTED = "rejected"
    ERROR = "error"


class WorkerResult(BaseModel):
    """Every delegation outcome as data, so failures never surface as raises."""

    status: WorkerStatus
    output: str = ""
    elapsed_s: float = 0.0
    token_usage: TokenUsage | None = None
    error: str | None = None

    @model_validator(mode="after")
    def _error_requires_message(self) -> WorkerResult:
        """An ERROR result must carry a message so the caller knows why."""
        if self.status is WorkerStatus.ERROR and not self.error:
            raise MissingErrorMessageError
        return self
