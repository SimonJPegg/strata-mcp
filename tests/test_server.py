"""Tests for the server tool wrapper: surfaces context size, returns result."""

from __future__ import annotations

import httpx

from strata_mcp.config import StrataConfig
from strata_mcp.mapping import MARKER_COMPLETED
from strata_mcp.result import WorkerStatus
from strata_mcp.server import build_server, delegate_task_impl


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
