"""Tests for provider profiles and capability parsing."""

from __future__ import annotations

import pytest

from strata_mcp.providers import (
    ReasoningProvenance,
    known_providers,
    parse_opencode_go_reasoning,
    parse_reasoning,
    parse_strata_reasoning,
    provider_profile,
)


def test_provider_profiles_know_connection_defaults() -> None:
    strata = provider_profile("strata")
    assert strata.default_base_url == "http://127.0.0.1:8080/v1"
    assert not strata.requires_api_key
    assert not strata.requires_session
    assert strata.fallback_reasoning_levels == ["none", "low", "medium", "high"]

    go = provider_profile("opencode-go")
    assert go.default_base_url == "https://opencode.ai/inference/go/openai/v1"
    assert go.requires_api_key
    assert go.requires_session
    assert go.session_header == "x-opencode-session"


def test_parse_go_reasoning_extracts_levels_and_default() -> None:
    entry = {
        "id": "gpt-5.6-luna",
        "capabilities": {
            "reasoning": {
                "supported": True,
                "effort": ["none", "low", "medium", "high", "xhigh", "max"],
                "default": {"type": "effort", "value": "medium"},
            },
        },
    }

    levels, default = parse_opencode_go_reasoning(entry)

    assert levels == ["none", "low", "medium", "high", "xhigh", "max"]
    assert default == "medium"


def test_parse_go_reasoning_ignores_default_not_in_levels() -> None:
    entry = {
        "id": "x",
        "capabilities": {
            "reasoning": {
                "supported": True,
                "effort": ["low", "high"],
                "default": {"type": "effort", "value": "medium"},
            },
        },
    }

    levels, default = parse_opencode_go_reasoning(entry)

    assert levels == ["low", "high"]
    assert default is None


def test_parse_go_reasoning_degrades_when_only_toggle_is_present() -> None:
    entry = {
        "id": "kimi-k2.7-code",
        "capabilities": {
            "reasoning": {"supported": True, "toggle": True},
        },
    }

    assert parse_opencode_go_reasoning(entry) == (None, None)


def test_parse_go_reasoning_degrades_for_malformed_capabilities() -> None:
    entry = {
        "id": "broken",
        "capabilities": {
            "reasoning": {
                "supported": True,
                "effort": "high",  # not a list
            },
        },
    }

    assert parse_opencode_go_reasoning(entry) == (None, None)


def test_parse_strata_reasoning_returns_no_advertised_levels() -> None:
    assert parse_strata_reasoning({"id": "model", "meta": {"n_ctx": 32768}}) == (
        None,
        None,
    )


@pytest.mark.parametrize("provider", ["strata", "ollama", "opencode-go"])
def test_parse_reasoning_dispatches_by_provider(provider: str) -> None:
    entry = {"id": "x"}
    result = parse_reasoning(provider, entry)
    if provider == "opencode-go":
        assert result == (None, None)
    else:
        assert result == (None, None)


def test_discovered_model_holds_reasoning_provenance() -> None:
    from strata_mcp.providers import DiscoveredModel

    model = DiscoveredModel(
        id="m",
        reasoning_levels=["low", "high"],
        reasoning_default="low",
        reasoning_provenance=ReasoningProvenance.ADVERTISED,
    )
    assert model.reasoning_provenance == ReasoningProvenance.ADVERTISED


def test_known_providers_is_derived_from_the_profiles() -> None:
    assert known_providers() == {"strata", "ollama", "opencode-go"}
    assert all(provider_profile(name).name == name for name in known_providers())
