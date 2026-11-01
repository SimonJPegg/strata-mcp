"""Tests for StrataClient: discovery, request shape, auth, parsing, failures."""

from __future__ import annotations

import json as json_mod
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from strata_mcp.client import StrataClient, WireObject
from strata_mcp.config import StrataConfig
from strata_mcp.errors import (
    CompletionResponseError,
    ModelDiscoveryError,
    StrataUnreachableError,
)


def _client(
    handler: Callable[[httpx.Request], httpx.Response],
    api_key: str | None = None,
) -> StrataClient:
    config = StrataConfig(model_context_size=4096, api_key=api_key)
    transport = httpx.MockTransport(handler)
    return StrataClient(config, httpx.Client(transport=transport))


def test_discover_models_returns_all_listed_ids() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/models"
        assert request.method == "GET"
        return httpx.Response(200, json={"data": [{"id": "qwen3-flash"}, {"id": "other"}]})

    assert _client(handler).discover_models() == ["qwen3-flash", "other"]


def test_discover_models_single_model() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [{"id": "only-one"}]})

    assert _client(handler).discover_models() == ["only-one"]


def test_requests_omit_auth_header_without_key() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert "authorization" not in {k.lower() for k in request.headers}
        return httpx.Response(200, json={"data": [{"id": "m"}]})

    _client(handler).discover_models()


def test_requests_include_bearer_header_with_key() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer secret-token"
        return httpx.Response(200, json={"data": [{"id": "m"}]})

    _client(handler, api_key="secret-token").discover_models()


def test_completion_request_shape() -> None:
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
    def handler(request: httpx.Request) -> httpx.Response:
        body = json_mod.loads(request.content)
        assert body["temperature"] == 0.0
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    _client(handler).complete("m", "sys", "q")


def test_completion_sends_reasoning_effort_when_set() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json_mod.loads(request.content)
        assert body["reasoning_effort"] == "none"
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    _client(handler).complete("m", "sys", "q", reasoning_effort="none")


def test_completion_omits_reasoning_effort_when_unset() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json_mod.loads(request.content)
        assert "reasoning_effort" not in body
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    _client(handler).complete("m", "sys", "q")


def test_discovery_maps_connect_error_to_unreachable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    with pytest.raises(StrataUnreachableError):
        _client(handler).discover_models()


def test_discovery_maps_bad_status_to_discovery_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={})

    with pytest.raises(ModelDiscoveryError):
        _client(handler).discover_models()


def test_discovery_rejects_empty_model_list() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": []})

    with pytest.raises(ModelDiscoveryError):
        _client(handler).discover_models()


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


@pytest.mark.parametrize(
    "body",
    [
        {"no_data": []},  # no 'data' key at all
        {"data": {"id": "m"}},  # 'data' is a mapping, not the advertised list
        {"data": [{"name": "unnamed"}]},  # entry carries no id
        {"data": [{"id": ""}]},  # an empty id cannot be selected
        {"data": [{"id": 7}]},  # id is not a string
        {"data": ["bare-string"]},  # entry is not a mapping
    ],
)
def test_discovery_rejects_unusable_model_entries(body: WireObject) -> None:
    # Every engine is a peer: an unusable body is a typed discovery failure,
    # never a KeyError or AttributeError escaping to the caller.
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=body)

    with pytest.raises(ModelDiscoveryError):
        _client(handler).discover_models()


def test_discovery_bad_status_wins_over_body_shape() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "bad request"})

    with pytest.raises(ModelDiscoveryError):
        _client(handler).discover_models()


def test_completion_bad_status_maps_to_response_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="engine down")

    with pytest.raises(CompletionResponseError):
        _client(handler).complete("m", "sys", "q")


@pytest.mark.parametrize("content", [None, 7, ["chunk"], "   \n\t "])
def test_completion_rejects_unusable_content(content: Any) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    with pytest.raises(CompletionResponseError):
        _client(handler).complete("m", "sys", "q")


@pytest.mark.parametrize(
    "usage",
    [
        "not-a-mapping",
        None,
        {"prompt_tokens": 5},  # completion count missing
        {"prompt_tokens": "5", "completion_tokens": 6},  # counts not ints
    ],
)
def test_completion_ignores_unusable_usage(usage: Any) -> None:
    # Usage is advisory: an unusable shape must not fail an otherwise good
    # completion, and must not invent a token count either.
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "answer"}}],
                "usage": usage,
            },
        )

    result = _client(handler).complete("m", "sys", "q")

    assert result.output == "answer"
    assert result.token_usage is None
