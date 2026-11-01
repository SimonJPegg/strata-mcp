"""Core delegation logic: run one task against the Strata worker, time it,
and return a WorkerResult. Kept separate from MCP wiring for testability."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable

from loguru import logger

from strata_mcp.client import StrataClient, ToolDispatch, ToolLoopResult, WireObject
from strata_mcp.config import StrataConfig
from strata_mcp.errors import (
    CommandsNeedWriteDirError,
    OversizedContextError,
    RuntimeBackstopError,
    StrataClientError,
)
from strata_mcp.mapping import error_result, status_from_output
from strata_mcp.prompt import build_system_prompt
from strata_mcp.result import ReasoningEffort, WorkerResult, WorkerStatus
from strata_mcp.tools import build_tools, make_dispatch

# Heartbeat cadence for the in-flight log line. A module constant would be a
# global; keep it as a default argument so callers can override in tests.
_DEFAULT_HEARTBEAT_S = 30.0
# Default cap on tool-use rounds. A small bound: enough for a bounded file job,
# low enough that a confused worker cannot loop indefinitely.
_DEFAULT_MAX_TOOL_ROUNDS = 8
# Default per-command timeout ceiling in seconds. The worker may request less;
# anything more is clamped to this. Bounds a hung command, not the delegation.
_DEFAULT_MAX_COMMAND_TIMEOUT_S = 300
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


def _capture_work(
    work: Callable[[], WorkerResult],
    results: list[WorkerResult],
    failures: list[BaseException],
) -> Callable[[], None]:
    """Build the thread target that records work()'s result or its failure.

    The exception is stashed rather than raised so it can be re-raised on the
    main thread, where the heartbeat loop is not left waiting on a dead thread.
    """

    def _target() -> None:
        try:
            results.append(work())
        except BaseException as exc:  # re-raised by the caller below
            failures.append(exc)

    return _target


def _await_thread(
    thread: threading.Thread,
    start: float,
    heartbeat_s: float,
    max_runtime_s: float | None,
) -> None:
    """Join the worker thread in slices, logging elapsed time and enforcing the cap."""
    while thread.is_alive():
        thread.join(timeout=heartbeat_s)
        elapsed = time.monotonic() - start
        if thread.is_alive():
            logger.info("delegate_task still running ({:.0f}s elapsed)", elapsed)
        if max_runtime_s is not None and elapsed >= max_runtime_s and thread.is_alive():
            raise RuntimeBackstopError(max_runtime_s)


def _run_with_heartbeat(
    work: Callable[[], WorkerResult],
    heartbeat_s: float,
    max_runtime_s: float | None,
) -> WorkerResult:
    """Run work in a thread, logging a heartbeat and enforcing an optional cap.

    The worker call is blocking, so it runs in a thread; the main thread logs
    elapsed time periodically and applies the optional runtime backstop.
    """
    results: list[WorkerResult] = []
    failures: list[BaseException] = []

    thread = threading.Thread(target=_capture_work(work, results, failures), daemon=True)
    start = time.monotonic()
    thread.start()
    _await_thread(thread, start, heartbeat_s, max_runtime_s)

    if failures:
        raise failures[0]
    return results[0]


def _chosen_model(client: StrataClient, model: str | None) -> str:
    """Use the caller's chosen model, else the first model Strata advertises."""
    if model:
        return model
    return client.discover_models()[0]


def _text_worker_result(
    client: StrataClient,
    chosen: str,
    system_prompt: str,
    user_content: str,
    effort: str | None,
) -> WorkerResult:
    """Run the text-only path: one completion, mapped to an envelope."""
    completion = client.complete(chosen, system_prompt, user_content, effort)
    return WorkerResult(
        status=status_from_output(completion.output),
        output=completion.output,
        token_usage=completion.token_usage,
    )


def _tool_worker_result(
    client: StrataClient,
    chosen: str,
    system_prompt: str,
    user_content: str,
    tools: list[WireObject],
    dispatch: ToolDispatch,
    max_tool_rounds: int,
    effort: str | None,
) -> WorkerResult:
    """Run the fenced tool loop and map its outcome to an envelope."""
    loop = client.complete_with_tools(
        chosen, system_prompt, user_content, tools, dispatch, max_tool_rounds, effort
    )
    if loop.hit_round_cap:
        return _round_cap_envelope(loop)
    return WorkerResult(
        status=status_from_output(loop.output),
        output=loop.output,
        files_written=loop.written_paths,
        commands_run=loop.commands_run,
    )


def _round_cap_envelope(loop: ToolLoopResult) -> WorkerResult:
    """Out of rounds is a blocked state, not a transport error: ask the caller for more."""
    return WorkerResult(
        status=WorkerStatus.NEEDS_INPUT,
        output=f"stopped after {loop.rounds_used} tool rounds without finishing",
        files_written=loop.written_paths,
        commands_run=loop.commands_run,
    )


def run_delegation(
    client: StrataClient,
    config: StrataConfig,
    task: str,
    context: str,
    model: str | None = None,
    reasoning_effort: ReasoningEffort | None = None,
    read_dirs_allowed: list[str] | None = None,
    write_dirs_allowed: list[str] | None = None,
    max_tool_rounds: int = _DEFAULT_MAX_TOOL_ROUNDS,
    allowed_commands: list[str] | None = None,
    max_command_timeout_s: int = _DEFAULT_MAX_COMMAND_TIMEOUT_S,
    heartbeat_s: float = _DEFAULT_HEARTBEAT_S,
) -> WorkerResult:
    """Delegate one task to the Strata worker and return a structured result.

    Guards oversized context, selects the model, and runs the worker. When the
    caller grants file directories or a command menu, the worker runs a bounded
    tool-use loop with fenced read_file/write_file/run_command; otherwise it is
    a single text-only completion. All failures become an error envelope rather
    than propagating.
    """
    read_dirs = read_dirs_allowed or []
    write_dirs = write_dirs_allowed or []
    commands = allowed_commands or []
    system_prompt = build_system_prompt(
        has_read=bool(read_dirs),
        has_write=bool(write_dirs),
        has_commands=bool(commands),
    )
    user_content = _compose_user_content(task, context)

    start = time.monotonic()

    if commands and not write_dirs:
        # Commands always run inside a fenced working directory, so a command
        # menu with no write dir has nowhere safe to run; refuse up front.
        return WorkerResult(
            status=WorkerStatus.ERROR,
            elapsed_s=time.monotonic() - start,
            error=str(CommandsNeedWriteDirError()),
        )

    oversized = _oversized_result(system_prompt, user_content, config, start)
    if oversized is not None:
        return oversized

    def _work() -> WorkerResult:
        chosen = _chosen_model(client, model)
        effort = reasoning_effort.value if reasoning_effort else None
        tools = build_tools(read_dirs, write_dirs, commands)
        if not tools:
            return _text_worker_result(client, chosen, system_prompt, user_content, effort)
        return _tool_worker_result(
            client,
            chosen,
            system_prompt,
            user_content,
            tools,
            make_dispatch(read_dirs, write_dirs, commands, max_command_timeout_s),
            max_tool_rounds,
            effort,
        )

    try:
        result = _run_with_heartbeat(_work, heartbeat_s, config.max_runtime_s)
    except StrataClientError as exc:
        # Covers every Strata failure, including the runtime backstop: a
        # delegation that overran its cap is an error envelope, not a raise.
        return error_result(exc, elapsed_s=time.monotonic() - start)

    return _stamp_elapsed(result, start)


def _stamp_elapsed(result: WorkerResult, start: float) -> WorkerResult:
    """Stamp the finished delegation with its wall-clock time without mutating the input."""
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
    return error_result(
        OversizedContextError(estimated, config.model_context_size),
        elapsed_s=time.monotonic() - start,
    )
