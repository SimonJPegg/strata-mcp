"""Live integration tests against a running local Strata instance.

Skipped unless STRATA_MCP_IT=1. These assert only behaviour that is
deterministic given a reachable Strata — invariants of our own code, never the
model's output text or its compliance with the prompt (which are not
reproducible on a quantised MoE model). Reads connection details from the
environment so no credentials are hardcoded:

    STRATA_MCP_IT=1 \\
    STRATA_IT_BASE_URL=http://127.0.0.1:8080/v1 \\
    STRATA_IT_CONTEXT=65536 \\
    STRATA_IT_API_KEY=... \\
    uv run pytest tests/test_integration.py -v
"""

from __future__ import annotations

import json as json_mod
import os
import time

import httpx
import pytest

from strata_mcp.client import StrataClient
from strata_mcp.config import StrataConfig
from strata_mcp.delegation import run_delegation
from strata_mcp.result import WorkerStatus
from strata_mcp.server import delegate_task_impl

pytestmark = pytest.mark.skipif(
    os.environ.get("STRATA_MCP_IT") != "1",
    reason="live Strata integration; set STRATA_MCP_IT=1 to run",
)

_VALID_STATUSES = set(WorkerStatus)


def _base_url() -> str:
    return os.environ.get("STRATA_IT_BASE_URL", "http://127.0.0.1:8080/v1")


def _api_key() -> str | None:
    return os.environ.get("STRATA_IT_API_KEY")


def _config(**overrides: object) -> StrataConfig:
    params: dict[str, object] = {
        "base_url": _base_url(),
        "model_context_size": int(os.environ.get("STRATA_IT_CONTEXT", "65536")),
        "api_key": _api_key(),
    }
    params.update(overrides)
    return StrataConfig(**params)


def _client(config: StrataConfig) -> StrataClient:
    return StrataClient(config, httpx.Client(timeout=None))


def test_model_discovery_returns_a_real_id() -> None:
    model = _client(_config()).discover_model()

    assert isinstance(model, str)
    assert model != ""


def test_delegation_returns_a_valid_envelope() -> None:
    response = delegate_task_impl(
        _config(), task="Reply with exactly the word: pong", context=""
    )

    # Deterministic invariants of our code, not the model's text.
    assert response.result.status in _VALID_STATUSES
    assert response.result.status is not WorkerStatus.ERROR
    assert response.result.output.strip() != ""
    assert response.result.elapsed_s >= 0.0
    assert response.model_context_size > 0


def test_real_engine_populates_token_usage() -> None:
    result = run_delegation(
        _client(_config()), _config(), task="Reply with: ok", context=""
    )

    assert result.status is not WorkerStatus.ERROR
    assert result.token_usage is not None
    assert result.token_usage.prompt_tokens > 0
    assert result.token_usage.completion_tokens > 0


def test_missing_api_key_is_rejected_when_required() -> None:
    if not _api_key():
        pytest.skip("Strata instance does not require an API key")

    result = run_delegation(
        _client(_config(api_key=None)), _config(api_key=None), task="hi", context=""
    )

    # Discovery/completion should fail auth and surface as a structured error.
    assert result.status is WorkerStatus.ERROR
    assert result.error is not None


def test_slow_real_call_is_not_timed_out() -> None:
    # Regression guard: a real completion commonly runs longer than httpx's
    # former default 5s timeout. It must still return a result, not an error.
    result = run_delegation(
        _client(_config()),
        _config(),
        task="Write a detailed six sentence explanation of how a hash map works.",
        context="",
    )

    assert result.status is not WorkerStatus.ERROR
    assert result.output.strip() != ""


def test_configured_temperature_reaches_strata() -> None:
    # Assert at the wire level that our configured temperature is sent, which
    # is deterministic regardless of what the model then generates. Uses a
    # recording transport: this checks our code's payload, not the engine.
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "m"}]})
        seen["temperature"] = json_mod.loads(request.content)["temperature"]
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    config = _config(temperature=0.0)
    client = StrataClient(config, httpx.Client(transport=httpx.MockTransport(handler)))
    run_delegation(client, config, task="Reply with: ok", context="")

    assert seen["temperature"] == 0.0


def test_oversized_context_never_contacts_strata() -> None:
    # Deterministic: the pre-check fires on size alone, before any network call.
    tiny = _config(model_context_size=4)

    start = time.monotonic()
    result = run_delegation(_client(tiny), tiny, task="x" * 1000, context="y" * 1000)
    elapsed = time.monotonic() - start

    assert result.status is WorkerStatus.ERROR
    assert result.error is not None
    assert "exceed model context size" in result.error
    assert elapsed < 1.0  # no network round-trip happened
