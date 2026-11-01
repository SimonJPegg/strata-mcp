"""End-to-end tests for run_delegation using a mocked Strata transport."""

from __future__ import annotations

import json as json_mod
import time
from collections.abc import Callable

import httpx
import pytest
from loguru import logger

from strata_mcp.client import StrataClient, WireObject
from strata_mcp.config import StrataConfig
from strata_mcp.delegation import run_delegation
from strata_mcp.mapping import MARKER_BLOCKED, MARKER_COMPLETED
from strata_mcp.result import WorkerStatus


def _client(handler: Callable[[httpx.Request], httpx.Response]) -> StrataClient:
    transport = httpx.MockTransport(handler)
    config = StrataConfig(model_context_size=65536)
    return StrataClient(config, httpx.Client(transport=transport))


def _config() -> StrataConfig:
    return StrataConfig(model_context_size=65536)


def _ok_handler(content: str):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": "qwen-local"}]})
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": content}}],
                "usage": {"prompt_tokens": 20, "completion_tokens": 40},
            },
        )

    return handler


def test_completed_task_returns_ok_envelope() -> None:
    client = _client(_ok_handler(f"Here is the answer.\n{MARKER_COMPLETED}"))

    result = run_delegation(client, _config(), task="sum 2 and 2", context="")

    assert result.status is WorkerStatus.OK
    assert "Here is the answer." in result.output
    assert result.elapsed_s >= 0.0
    assert result.token_usage is not None
    assert result.token_usage.completion_tokens == 40


def test_blocked_task_returns_needs_input() -> None:
    client = _client(_ok_handler(f"Which file did you mean?\n{MARKER_BLOCKED}"))

    result = run_delegation(client, _config(), task="edit the config", context="")

    assert result.status is WorkerStatus.NEEDS_INPUT


def test_unreachable_strata_returns_error_envelope() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    client = _client(handler)

    result = run_delegation(client, _config(), task="anything", context="")

    assert result.status is WorkerStatus.ERROR
    assert result.error is not None
    assert result.elapsed_s >= 0.0


def test_context_is_included_in_user_message() -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": "m"}]})
        body = json_mod.loads(request.content)
        seen["user"] = body["messages"][1]["content"]
        return httpx.Response(
            200, json={"choices": [{"message": {"content": f"ok\n{MARKER_COMPLETED}"}}]}
        )

    client = _client(handler)
    run_delegation(client, _config(), task="my task", context="important context")

    assert "my task" in seen["user"]
    assert "important context" in seen["user"]


def test_oversized_context_returns_error_without_calling_strata() -> None:
    called = {"hit": False}

    def handler(request: httpx.Request) -> httpx.Response:
        called["hit"] = True
        return httpx.Response(200, json={"data": [{"id": "m"}]})

    transport = httpx.MockTransport(handler)
    # Tiny window so a modest context plainly overflows.
    config = StrataConfig(model_context_size=4)
    client = StrataClient(config, httpx.Client(transport=transport))

    result = run_delegation(client, config, task="x" * 500, context="y" * 500)

    assert result.status is WorkerStatus.ERROR
    assert result.error is not None
    assert "exceed model context size" in result.error
    assert called["hit"] is False  # Strata never contacted


def test_no_backstop_does_not_terminate_a_normal_call() -> None:
    client = _client(_ok_handler(f"done\n{MARKER_COMPLETED}"))
    config = StrataConfig(model_context_size=65536, max_runtime_s=None)

    result = run_delegation(client, config, task="t", context="")

    assert result.status is WorkerStatus.OK


def test_runtime_backstop_terminates_a_slow_call() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": "m"}]})
        time.sleep(0.5)  # exceed the tiny backstop below
        return httpx.Response(200, json={"choices": [{"message": {"content": "late"}}]})

    transport = httpx.MockTransport(handler)
    config = StrataConfig(model_context_size=65536, max_runtime_s=0.1)
    client = StrataClient(config, httpx.Client(transport=transport))

    result = run_delegation(client, config, task="t", context="", heartbeat_s=0.05)

    assert result.status is WorkerStatus.ERROR
    assert result.error is not None
    assert "max runtime backstop" in result.error


def test_heartbeat_logged_for_a_slow_call() -> None:
    messages: list[str] = []
    sink_id = logger.add(lambda m: messages.append(m), level="INFO")
    try:

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/v1/models":
                return httpx.Response(200, json={"data": [{"id": "m"}]})
            time.sleep(0.2)
            return httpx.Response(
                200, json={"choices": [{"message": {"content": f"ok\n{MARKER_COMPLETED}"}}]}
            )

        transport = httpx.MockTransport(handler)
        config = StrataConfig(model_context_size=65536)
        client = StrataClient(config, httpx.Client(transport=transport))

        run_delegation(client, config, task="t", context="", heartbeat_s=0.05)
    finally:
        logger.remove(sink_id)

    assert any("still running" in m for m in messages)


@pytest.mark.parametrize(
    ("failing_path", "status"),
    [("/v1/models", 500), ("/v1/models", 401), ("/v1/chat/completions", 500)],
)
def test_engine_failure_at_either_stage_returns_an_error_envelope(
    failing_path: str, status: int
) -> None:
    # Discovery and completion are different calls that can each fail: neither
    # may raise to the caller, and both must say what went wrong.
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == failing_path:
            return httpx.Response(status, json={"error": "engine"})
        if request.url.path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": "m"}]})
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    result = run_delegation(_client(handler), _config(), "t", "")

    assert result.status is WorkerStatus.ERROR
    assert result.error is not None
    assert not result.output


@pytest.mark.parametrize(
    "unusable_body",
    [{"no_data": []}, {"data": ["bare-string"]}, {"choices": [{"oops": {}}]}],
)
def test_unusable_engine_body_returns_an_error_envelope(unusable_body: WireObject) -> None:
    # A misbehaving engine is data, not a crash: a body the parser cannot read
    # ends the delegation as an error envelope rather than a KeyError.
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=unusable_body)

    result = run_delegation(_client(handler), _config(), "t", "")

    assert result.status is WorkerStatus.ERROR
    assert result.error is not None
