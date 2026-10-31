"""Tests for the server tool wrapper: surfaces context size, returns result."""

from __future__ import annotations

import httpx

from strata_mcp.config import StrataConfig
from strata_mcp.mapping import MARKER_COMPLETED
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
    import asyncio

    config = StrataConfig(model_context_size=4096)

    server = build_server(config)

    tools = asyncio.run(server.list_tools())
    assert any(t.name == "delegate_task" for t in tools)


def test_build_server_registers_list_models() -> None:
    import asyncio

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
    import asyncio

    server = build_server(StrataConfig(model_context_size=4096))
    tools = {t.name: t for t in asyncio.run(server.list_tools())}

    for name in ("delegate_task", "list_models"):
        desc = tools[name].description or ""
        assert desc.strip()
        assert len(desc) < 200


def test_list_models_impl_returns_ids() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [{"id": "a"}, {"id": "b"}]})

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    assert list_models_impl(StrataConfig(model_context_size=4096), http_client) == ["a", "b"]


def test_chosen_model_is_used() -> None:
    import json as json_mod

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
        StrataConfig(model_context_size=4096), task="t", context="",
        model="second", http_client=http_client,
    )

    assert seen["model"] == "second"


def test_omitted_model_defaults_to_first() -> None:
    import json as json_mod

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
    import json as json_mod

    from strata_mcp.result import ReasoningEffort

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
        StrataConfig(model_context_size=4096), task="t", context="",
        reasoning_effort=ReasoningEffort.NONE, http_client=http_client,
    )

    assert seen["effort"] == "none"


def test_reasoning_effort_absent_when_omitted() -> None:
    import json as json_mod

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
