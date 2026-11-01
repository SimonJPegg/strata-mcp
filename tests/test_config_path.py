"""Tests for config path resolution: env var precedence and XDG fallback."""

from __future__ import annotations

from pathlib import Path

import pytest

from strata_mcp.server import _resolve_config_path

_ENV = "STRATA_MCP_CONFIG"
_XDG = "XDG_CONFIG_HOME"


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(_ENV, raising=False)
    monkeypatch.delenv(_XDG, raising=False)


def test_env_var_takes_precedence(clean_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(_ENV, "/tmp/explicit.toml")
    monkeypatch.setenv(_XDG, "/xdg")

    assert _resolve_config_path() == Path("/tmp/explicit.toml")


def test_xdg_fallback_when_env_unset(clean_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(_XDG, "/xdg")

    assert _resolve_config_path() == Path("/xdg/strata-mcp/config.toml")


def test_home_config_default(clean_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    # A lambda cannot annotate its cls parameter, so pyrefly sees implicit Any
    # here; the classmethod wrapper is what makes Path.home() bind correctly.
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: Path("/home/tester")))  # pyrefly: ignore[implicit-any-lambda]

    assert _resolve_config_path() == Path("/home/tester/.config/strata-mcp/config.toml")


def test_empty_env_var_falls_through_to_xdg(
    clean_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    # An empty value must not be treated as a configured path.
    monkeypatch.setenv(_ENV, "")
    monkeypatch.setenv(_XDG, "/xdg")

    assert _resolve_config_path() == Path("/xdg/strata-mcp/config.toml")
