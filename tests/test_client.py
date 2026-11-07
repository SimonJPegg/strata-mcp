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
from strata_mcp.providers import (
    DiscoveredModel,
    ReasoningProvenance,
    provider_headers,
    server_user_agent,
)


def _client(
    handler: Callable[[httpx.Request], httpx.Response],
    api_key: str | None = None,
    provider: str = "strata",
    session_id: str | None = None,
) -> StrataClient:
    kwargs: dict[str, Any] = {"model_context_size": 4096, "api_key": api_key}
    if provider == "opencode-go":
        kwargs["api_key"] = api_key or "go-key"
    config = StrataConfig(provider=provider, **kwargs)
    headers = provider_headers(provider, session_id)
    transport = httpx.MockTransport(handler)
    return StrataClient(config, httpx.Client(transport=transport), headers=headers)


def _assumed_entry(model_id: str) -> DiscoveredModel:
    return DiscoveredModel(
        id=model_id,
        reasoning_levels=["none", "low", "medium", "high"],
        reasoning_default=None,
        reasoning_provenance=ReasoningProvenance.ASSUMED,
    )


def test_discover_models_returns_all_listed_ids() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/models"
        assert request.method == "GET"
        return httpx.Response(200, json={"data": [{"id": "qwen3-flash"}, {"id": "other"}]})

    models = _client(handler).discover_models()

    assert [m.id for m in models] == ["qwen3-flash", "other"]
    assert models == [_assumed_entry("qwen3-flash"), _assumed_entry("other")]


def test_discover_models_single_model() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [{"id": "only-one"}]})

    models = _client(handler).discover_models()

    assert models == [_assumed_entry("only-one")]


def test_discover_models_parses_go_advertised_levels() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "glm-5.3",
                        "capabilities": {
                            "reasoning": {
                                "supported": True,
                                "effort": ["low", "high", "max"],
                                "default": {"type": "effort", "value": "high"},
                            },
                        },
                    },
                ],
            },
        )

    models = _client(handler, provider="opencode-go").discover_models()

    assert models == [
        DiscoveredModel(
            id="glm-5.3",
            reasoning_levels=["low", "high", "max"],
            reasoning_default="high",
            reasoning_provenance=ReasoningProvenance.ADVERTISED,
        ),
    ]


def test_discover_models_degrades_malformed_go_capabilities() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "broken",
                        "capabilities": {
                            "reasoning": {
                                "supported": True,
                                "effort": "high",  # not a list
                            },
                        },
                    },
                ],
            },
        )

    models = _client(handler, provider="opencode-go").discover_models()

    assert models[0].id == "broken"
    assert models[0].reasoning_provenance == ReasoningProvenance.ASSUMED


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


def test_user_agent_is_sent_on_every_request() -> None:
    seen: set[str] = set()

    def handler(request: httpx.Request) -> httpx.Response:
        seen.add(request.url.path)
        assert request.headers["User-Agent"] == server_user_agent()
        if request.url.path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": "m"}]})
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    client = _client(handler)
    client.discover_models()
    client.complete("m", "sys", "q")

    assert "/v1/models" in seen
    assert "/v1/chat/completions" in seen


def test_session_header_is_stable_for_go_and_absent_for_strata() -> None:
    go_sessions: list[str] = []

    def go_handler(request: httpx.Request) -> httpx.Response:
        go_sessions.append(request.headers.get("x-opencode-session", ""))
        return httpx.Response(200, json={"data": [{"id": "m"}]})

    go_client = _client(go_handler, provider="opencode-go", session_id="session-abc")
    go_client.discover_models()
    go_client.discover_models()

    assert go_sessions == ["session-abc", "session-abc"]

    def strata_handler(request: httpx.Request) -> httpx.Response:
        assert "x-opencode-session" not in request.headers
        return httpx.Response(200, json={"data": [{"id": "m"}]})

    _client(strata_handler).discover_models()


def test_completion_bad_status_error_carries_the_response_body() -> None:
    # The body holds the backend's reason (e.g. a region block); dropping it
    # makes a 400 look like a payload bug.
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": {"message": "model blocked in region"}})

    with pytest.raises(CompletionResponseError, match=r"HTTP 400.*model blocked in region"):
        _client(handler).complete("m", "sys", "q")


def test_discovery_bad_status_error_carries_the_response_body() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="key required")

    with pytest.raises(ModelDiscoveryError, match=r"HTTP 401: key required"):
        _client(handler).discover_models()


def test_bad_status_with_empty_body_reports_status_only() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(502)

    with pytest.raises(CompletionResponseError, match=r"HTTP 502$"):
        _client(handler).complete("m", "sys", "q")


def test_oversized_error_body_is_truncated() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="x" * 5000)

    with pytest.raises(CompletionResponseError) as excinfo:
        _client(handler).complete("m", "sys", "q")

    assert len(str(excinfo.value)) < 400
