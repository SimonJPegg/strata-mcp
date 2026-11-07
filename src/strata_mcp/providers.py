"""Provider profiles and capability parsing for each backend the server can speak to."""

from __future__ import annotations

import importlib.metadata
from collections.abc import Callable
from enum import StrEnum
from typing import Any

from pydantic import BaseModel


class ReasoningProvenance(StrEnum):
    """Whether reasoning levels came from the backend or from a provider fallback."""

    ADVERTISED = "advertised"
    ASSUMED = "assumed"


class DiscoveredModel(BaseModel):
    """One model discovered from the backend, with reasoning capability hints."""

    id: str
    reasoning_levels: list[str]
    reasoning_default: str | None
    reasoning_provenance: ReasoningProvenance


class ProviderProfile(BaseModel):
    """Static connection dialect and fallback defaults for one backend provider."""

    name: str
    default_base_url: str
    requires_api_key: bool
    requires_session: bool
    session_header: str | None
    fallback_reasoning_levels: list[str]


ReasoningParser = Callable[[object], tuple[list[str] | None, str | None]]


def _provider_profiles() -> dict[str, ProviderProfile]:
    """Build the profile table; a function so no module-level state exists."""
    basic_levels = ["none", "low", "medium", "high"]
    return {
        "strata": ProviderProfile(
            name="strata",
            default_base_url="http://127.0.0.1:8080/v1",
            requires_api_key=False,
            requires_session=False,
            session_header=None,
            fallback_reasoning_levels=basic_levels,
        ),
        "ollama": ProviderProfile(
            name="ollama",
            default_base_url="http://127.0.0.1:11434/v1",
            requires_api_key=False,
            requires_session=False,
            session_header=None,
            fallback_reasoning_levels=basic_levels,
        ),
        "opencode-go": ProviderProfile(
            name="opencode-go",
            default_base_url="https://opencode.ai/inference/go/openai/v1",
            requires_api_key=True,
            requires_session=True,
            session_header="x-opencode-session",
            fallback_reasoning_levels=["none", "minimal", "low", "medium", "high", "xhigh", "max"],
        ),
    }


def known_providers() -> frozenset[str]:
    """Return the provider names the server can speak to; the single source of truth."""
    return frozenset(_provider_profiles())


def provider_profile(name: str) -> ProviderProfile:
    """Return the profile for a known provider name."""
    return _provider_profiles()[name]


def _get(mapping: object, key: str) -> Any:
    """Safely read a key from a mapping-shaped value."""
    if isinstance(mapping, dict):
        return mapping.get(key)
    return None


def _string_list(value: object) -> list[str] | None:
    """Return a value if it is a list of non-empty strings, else None."""
    if not isinstance(value, list) or not value:
        return None
    if not all(isinstance(item, str) and item for item in value):
        return None
    return value


def parse_opencode_go_reasoning(entry: object) -> tuple[list[str] | None, str | None]:
    """Parse reasoning levels from an OpenCode Go /v1/models entry.

    Go advertises per-model ladders under capabilities.reasoning.effort, plus
    an optional default effort. Anything else (toggle-only, malformed, or
    missing capabilities) degrades to None so the caller applies the provider
    fallback and marks it assumed.
    """
    capabilities = _get(entry, "capabilities")
    if not isinstance(capabilities, dict):
        return None, None

    reasoning = capabilities.get("reasoning")
    if not isinstance(reasoning, dict):
        return None, None

    levels = _string_list(reasoning.get("effort"))
    if levels is None:
        return None, None

    default_level: str | None = None
    default_obj = reasoning.get("default")
    if isinstance(default_obj, dict) and default_obj.get("type") == "effort":
        default_value = default_obj.get("value")
        if isinstance(default_value, str) and default_value in levels:
            default_level = default_value

    return levels, default_level


def parse_strata_reasoning(_entry: object) -> tuple[list[str] | None, str | None]:
    """Strata does not advertise per-model reasoning levels; rely on fallback."""
    return None, None


def parse_ollama_reasoning(_entry: object) -> tuple[list[str] | None, str | None]:
    """Ollama's OpenAI-compatible endpoint does not advertise reasoning levels."""
    return None, None


def _reasoning_parsers() -> dict[str, ReasoningParser]:
    """Map each provider to its dialect parser; a function so no module-level state exists."""
    return {
        "strata": parse_strata_reasoning,
        "ollama": parse_ollama_reasoning,
        "opencode-go": parse_opencode_go_reasoning,
    }


def parse_reasoning(provider: str, entry: object) -> tuple[list[str] | None, str | None]:
    """Parse reasoning levels from a /models entry for the configured provider."""
    parser = _reasoning_parsers()[provider]
    return parser(entry)


def server_user_agent() -> str:
    """Return an identifying User-Agent for the server, with package version."""
    try:
        version = importlib.metadata.version("strata-mcp")
    except importlib.metadata.PackageNotFoundError:
        version = "0.0.0"
    return f"strata-mcp/{version}"


def provider_headers(provider: str, session_id: str | None = None) -> dict[str, str]:
    """Build request headers the provider requires, including User-Agent."""
    profile = provider_profile(provider)
    headers = {"User-Agent": server_user_agent()}
    if profile.requires_session and session_id and profile.session_header:
        headers[profile.session_header] = session_id
    return headers
