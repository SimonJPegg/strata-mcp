"""Tests for the server tool wrapper: surfaces context size, returns result."""

from __future__ import annotations

import asyncio
import json as json_mod
from typing import Any

import httpx
import pytest

import strata_mcp.server as server_mod
from strata_mcp.config import StrataConfig
from strata_mcp.mapping import MARKER_COMPLETED
from strata_mcp.providers import DiscoveredModel, ReasoningProvenance
from strata_mcp.result import WorkerStatus
from strata_mcp.server import build_server, delegate_task_impl, list_models_impl


def _handler(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/v1/models":
        return httpx.Response(200, json={"data": [{"id": "qwen-local"}]})
    return httpx.Response(
        200, json={"choices": [{"message": {"content": f"answer\n{MARKER_COMPLETED}"}}]}
    )


def test_tool_surfaces_declared_context_size() -> None:
    config = StrataConfig(model_context_size=65536)
    http_client = httpx.Client(transport=httpx.MockTransport(_handler))

    response = delegate_task_impl(config, task="t", context="", http_client=http_client)

    assert response.model_context_size == 65536
    assert response.result.status is WorkerStatus.OK
    assert "answer" in response.result.output


def test_build_server_registers_delegate_task() -> None:
    config = StrataConfig(model_context_size=4096)

    server = build_server(config)

    tools = asyncio.run(server.list_tools())
    assert any(t.name == "delegate_task" for t in tools)


def test_build_server_registers_list_models() -> None:
    server = build_server(StrataConfig(model_context_size=4096))

    tools = asyncio.run(server.list_tools())
    names = {t.name for t in tools}
    assert "list_models" in names
    assert "delegate_task" in names


def test_server_exposes_concise_instructions() -> None:
    server = build_server(StrataConfig(model_context_size=4096))

    assert server.instructions
    assert "delegate" in server.instructions.lower()
    # Dense: guidance is loaded into the host context, so keep it short.
    assert len(server.instructions) < 300


def test_tool_descriptions_are_dense() -> None:
    server = build_server(StrataConfig(model_context_size=4096))
    tools = {t.name: t for t in asyncio.run(server.list_tools())}

    for name in ("delegate_task", "list_models"):
        desc = tools[name].description or ""
        assert desc.strip()
        assert len(desc) < 200


def test_list_models_impl_returns_entries() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [{"id": "a"}, {"id": "b"}]})

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    models = list_models_impl(StrataConfig(model_context_size=4096), http_client)

    assert models == [
        DiscoveredModel(
            id="a",
            reasoning_levels=["none", "low", "medium", "high"],
            reasoning_default=None,
            reasoning_provenance=ReasoningProvenance.ASSUMED,
        ),
        DiscoveredModel(
            id="b",
            reasoning_levels=["none", "low", "medium", "high"],
            reasoning_default=None,
            reasoning_provenance=ReasoningProvenance.ASSUMED,
        ),
    ]


def test_chosen_model_is_used() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": "first"}, {"id": "second"}]})
        seen["model"] = json_mod.loads(request.content)["model"]
        return httpx.Response(
            200, json={"choices": [{"message": {"content": f"ok\n{MARKER_COMPLETED}"}}]}
        )

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    delegate_task_impl(
        StrataConfig(model_context_size=4096),
        task="t",
        context="",
        model="second",
        http_client=http_client,
    )

    assert seen["model"] == "second"


def test_omitted_model_defaults_to_first() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": "first"}, {"id": "second"}]})
        seen["model"] = json_mod.loads(request.content)["model"]
        return httpx.Response(
            200, json={"choices": [{"message": {"content": f"ok\n{MARKER_COMPLETED}"}}]}
        )

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    delegate_task_impl(
        StrataConfig(model_context_size=4096), task="t", context="", http_client=http_client
    )

    assert seen["model"] == "first"


def test_reasoning_effort_reaches_request_when_set() -> None:

    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": "m"}]})
        body = json_mod.loads(request.content)
        seen["effort"] = body.get("reasoning_effort", "<absent>")
        return httpx.Response(
            200, json={"choices": [{"message": {"content": f"ok\n{MARKER_COMPLETED}"}}]}
        )

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    delegate_task_impl(
        StrataConfig(model_context_size=4096),
        task="t",
        context="",
        reasoning_effort="none",
        http_client=http_client,
    )

    assert seen["effort"] == "none"


def test_reasoning_effort_arbitrary_string_reaches_request() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": "m"}]})
        body = json_mod.loads(request.content)
        seen["effort"] = body.get("reasoning_effort", "<absent>")
        return httpx.Response(
            200, json={"choices": [{"message": {"content": f"ok\n{MARKER_COMPLETED}"}}]}
        )

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    delegate_task_impl(
        StrataConfig(model_context_size=4096),
        task="t",
        context="",
        reasoning_effort="xhigh",
        http_client=http_client,
    )

    assert seen["effort"] == "xhigh"


def test_reasoning_effort_absent_when_omitted() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": "m"}]})
        body = json_mod.loads(request.content)
        seen["effort"] = body.get("reasoning_effort", "<absent>")
        return httpx.Response(
            200, json={"choices": [{"message": {"content": f"ok\n{MARKER_COMPLETED}"}}]}
        )

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    delegate_task_impl(
        StrataConfig(model_context_size=4096), task="t", context="", http_client=http_client
    )

    assert seen["effort"] == "<absent>"


def test_rejected_reasoning_level_returns_structured_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": "m"}]})
        return httpx.Response(400, json={"error": "reasoning_effort not supported"})

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    response = delegate_task_impl(
        StrataConfig(model_context_size=4096),
        task="t",
        context="",
        reasoning_effort="xhigh",
        http_client=http_client,
    )

    assert response.result.status is WorkerStatus.ERROR
    assert response.result.error is not None


def test_constructed_client_timeout_derives_from_backstop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # When no client is injected, the server builds one whose timeout is the
    # configured max_runtime_s so a hung request is bounded (finding 2).

    captured: dict[str, object] = {}
    real_client = httpx.Client

    # Spying on httpx.Client calls: the kwargs carry the timeout under test,
    # and Any is the honest type for a passthrough monkeypatch.
    def spy(*args: Any, **kwargs: Any) -> httpx.Client:
        captured["timeout"] = kwargs.get("timeout", "<unset>")
        return real_client(
            *args,
            transport=httpx.MockTransport(_handler),
            **{k: v for k, v in kwargs.items() if k != "transport"},
        )

    monkeypatch.setattr(server_mod.httpx, "Client", spy)

    delegate_task_impl(
        StrataConfig(model_context_size=4096, max_runtime_s=30.0),
        task="t",
        context="",
    )

    assert captured["timeout"] == 30.0


def test_constructed_client_has_no_timeout_without_backstop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # No backstop configured => no request timeout, preserving the
    # "slow-but-working call must not be killed" guarantee.

    captured: dict[str, object] = {}
    real_client = httpx.Client

    # Spying on httpx.Client calls: the kwargs carry the timeout under test,
    # and Any is the honest type for a passthrough monkeypatch.
    def spy(*args: Any, **kwargs: Any) -> httpx.Client:
        captured["timeout"] = kwargs.get("timeout", "<unset>")
        return real_client(
            *args,
            transport=httpx.MockTransport(_handler),
            **{k: v for k, v in kwargs.items() if k != "transport"},
        )

    monkeypatch.setattr(server_mod.httpx, "Client", spy)

    delegate_task_impl(StrataConfig(model_context_size=4096), task="t", context="")

    assert captured["timeout"] is None
