"""Tests for StrataClient: discovery, request shape, auth, parsing, failures."""

from __future__ import annotations

import httpx
import pytest

from strata_mcp.client import StrataClient
from strata_mcp.config import StrataConfig
from strata_mcp.errors import (
    CompletionResponseError,
    ModelDiscoveryError,
    StrataUnreachableError,
)


def _client(handler, api_key: str | None = None) -> StrataClient:
    config = StrataConfig(model_context_size=4096, api_key=api_key)
    transport = httpx.MockTransport(handler)
    return StrataClient(config, httpx.Client(transport=transport))


def test_discover_model_returns_first_listed_id() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/models"
        assert request.method == "GET"
        return httpx.Response(200, json={"data": [{"id": "qwen3-flash"}, {"id": "other"}]})

    assert _client(handler).discover_model() == "qwen3-flash"


def test_requests_omit_auth_header_without_key() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert "authorization" not in {k.lower() for k in request.headers}
        return httpx.Response(200, json={"data": [{"id": "m"}]})

    _client(handler).discover_model()


def test_requests_include_bearer_header_with_key() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer secret-token"
        return httpx.Response(200, json={"data": [{"id": "m"}]})

    _client(handler, api_key="secret-token").discover_model()


def test_completion_request_shape() -> None:
    import json as json_mod

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat/completions"
        assert request.method == "POST"
        body = json_mod.loads(request.content)
        assert body["model"] == "qwen3-flash"
        assert body["messages"][0] == {"role": "system", "content": "sys"}
        assert body["messages"][1] == {"role": "user", "content": "do the thing"}
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "done"}}]},
        )

    result = _client(handler).complete("qwen3-flash", "sys", "do the thing")
    assert result.output == "done"


def test_completion_sends_configured_temperature() -> None:
    import json as json_mod

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": "m"}]})
        body = json_mod.loads(request.content)
        assert body["temperature"] == 0.3
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    config = StrataConfig(model_context_size=4096, temperature=0.3)
    client = StrataClient(config, httpx.Client(transport=httpx.MockTransport(handler)))
    client.complete("m", "sys", "q")


def test_completion_defaults_to_zero_temperature() -> None:
    import json as json_mod

    def handler(request: httpx.Request) -> httpx.Response:
        body = json_mod.loads(request.content)
        assert body["temperature"] == 0.0
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    _client(handler).complete("m", "sys", "q")


def test_discovery_maps_connect_error_to_unreachable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    with pytest.raises(StrataUnreachableError):
        _client(handler).discover_model()


def test_discovery_maps_bad_status_to_discovery_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={})

    with pytest.raises(ModelDiscoveryError):
        _client(handler).discover_model()


def test_discovery_rejects_empty_model_list() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": []})

    with pytest.raises(ModelDiscoveryError):
        _client(handler).discover_model()


def test_completion_with_usage_is_parsed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "answer"}}],
                "usage": {"prompt_tokens": 12, "completion_tokens": 34},
            },
        )

    result = _client(handler).complete("m", "sys", "q")
    assert result.output == "answer"
    assert result.token_usage is not None
    assert result.token_usage.prompt_tokens == 12
    assert result.token_usage.completion_tokens == 34


def test_completion_without_usage_has_none() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": "answer"}}]})

    result = _client(handler).complete("m", "sys", "q")
    assert result.token_usage is None


def test_completion_connect_error_maps_to_unreachable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    with pytest.raises(StrataUnreachableError):
        _client(handler).complete("m", "sys", "q")


def test_completion_empty_content_maps_to_response_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": "   "}}]})

    with pytest.raises(CompletionResponseError):
        _client(handler).complete("m", "sys", "q")


def test_completion_malformed_body_maps_to_response_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": "shape"})

    with pytest.raises(CompletionResponseError):
        _client(handler).complete("m", "sys", "q")
