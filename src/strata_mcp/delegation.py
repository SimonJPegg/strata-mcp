"""Core delegation logic: run one task against the Strata worker, time it,
and return a WorkerResult. Kept separate from MCP wiring for testability."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable

from loguru import logger

from strata_mcp.client import StrataClient
from strata_mcp.config import StrataConfig
from strata_mcp.errors import (
    OversizedContextError,
    RuntimeBackstopError,
    StrataClientError,
)
from strata_mcp.mapping import error_result, status_from_output
from strata_mcp.prompt import build_system_prompt
from strata_mcp.result import WorkerResult, WorkerStatus

# Heartbeat cadence for the in-flight log line. A module constant would be a
# global; keep it as a default argument so callers can override in tests.
_DEFAULT_HEARTBEAT_S = 30.0
# Rough characters-per-token estimate for the oversized-context pre-check. The
# check is a cheap guard, not an exact tokeniser; Strata enforces the real cap.
_CHARS_PER_TOKEN = 4


def _compose_user_content(task: str, context: str) -> str:
    """Combine the scoped task and its context into one user message."""
    if context.strip():
        return f"Task:\n{task}\n\nContext:\n{context}"
    return f"Task:\n{task}"


def _estimated_tokens(text: str) -> int:
    """Cheap token estimate for the oversized-context guard."""
    return len(text) // _CHARS_PER_TOKEN


def _run_with_heartbeat(
    work: Callable[[], WorkerResult],
    heartbeat_s: float,
    max_runtime_s: float | None,
) -> WorkerResult:
    """Run work in a thread, logging a heartbeat and enforcing an optional cap.

    The worker call is blocking, so it runs in a thread; the main thread logs
    elapsed time periodically and applies the optional runtime backstop.
    """
    result: list[WorkerResult] = []
    failure: list[BaseException] = []

    def _target() -> None:
        try:
            result.append(work())
        except BaseException as exc:  # re-raised on the main thread below
            failure.append(exc)

    thread = threading.Thread(target=_target, daemon=True)
    start = time.monotonic()
    thread.start()

    while thread.is_alive():
        thread.join(timeout=heartbeat_s)
        elapsed = time.monotonic() - start
        if thread.is_alive():
            logger.info("delegate_task still running ({:.0f}s elapsed)", elapsed)
        if max_runtime_s is not None and elapsed >= max_runtime_s and thread.is_alive():
            raise RuntimeBackstopError(max_runtime_s)

    if failure:
        raise failure[0]
    return result[0]


def run_delegation(
    client: StrataClient,
    config: StrataConfig,
    task: str,
    context: str,
    heartbeat_s: float = _DEFAULT_HEARTBEAT_S,
) -> WorkerResult:
    """Delegate one task to the Strata worker and return a structured result.

    Guards oversized context before calling Strata, discovers the model, sends
    one blocking completion with a heartbeat and optional runtime backstop,
    times the call, and maps the worker's ending to a status. All failures
    become an error envelope rather than propagating.
    """
    system_prompt = build_system_prompt()
    user_content = _compose_user_content(task, context)

    start = time.monotonic()

    oversized = _oversized_result(system_prompt, user_content, config, start)
    if oversized is not None:
        return oversized

    def _work() -> WorkerResult:
        model = client.discover_model()
        completion = client.complete(model, system_prompt, user_content)
        return WorkerResult(
            status=status_from_output(completion.output),
            output=completion.output,
            token_usage=completion.token_usage,
        )

    try:
        result = _run_with_heartbeat(_work, heartbeat_s, config.max_runtime_s)
    except (StrataClientError, RuntimeBackstopError) as exc:
        return error_result(exc, elapsed_s=time.monotonic() - start)

    return result.model_copy(update={"elapsed_s": time.monotonic() - start})


def _oversized_result(
    system_prompt: str,
    user_content: str,
    config: StrataConfig,
    start: float,
) -> WorkerResult | None:
    """Return an error envelope if the prompt plainly exceeds the window."""
    estimated = _estimated_tokens(system_prompt) + _estimated_tokens(user_content)
    if estimated <= config.model_context_size:
        return None
    exc = OversizedContextError(estimated, config.model_context_size)
    return WorkerResult(
        status=WorkerStatus.ERROR,
        elapsed_s=time.monotonic() - start,
        error=str(exc),
    )
