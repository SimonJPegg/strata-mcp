"""Tests for load_config: happy path and each explicit failure mode."""

from __future__ import annotations

from pathlib import Path

import pytest

from strata_mcp.config import load_config
from strata_mcp.errors import (
    ConfigFileNotFoundError,
    ConfigParseError,
    ConfigValidationError,
    MissingApiKeyForProviderError,
    UnknownProviderError,
)


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "config.toml"
    path.write_text(text, encoding="utf-8")
    return path


def test_loads_valid_toml_file(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        """
        base_url = "http://127.0.0.1:8080/v1"
        model_context_size = 32768
        max_runtime_s = 3600.0
        api_key = "secret"
        """,
    )

    config = load_config(path)

    assert config.base_url == "http://127.0.0.1:8080/v1"
    assert config.model_context_size == 32768
    assert config.max_runtime_s == 3600.0
    assert config.api_key == "secret"


def test_loads_minimal_toml_with_defaults(tmp_path: Path) -> None:
    path = _write(tmp_path, "model_context_size = 8192\n")

    config = load_config(path)

    assert config.provider == "strata"
    assert config.base_url == "http://127.0.0.1:8080/v1"
    assert config.max_runtime_s is None
    assert config.api_key is None
    assert config.temperature == 0.0


def test_loads_temperature_from_toml(tmp_path: Path) -> None:
    path = _write(tmp_path, "model_context_size = 8192\ntemperature = 0.5\n")

    config = load_config(path)

    assert config.temperature == 0.5


def test_loads_provider_from_toml(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        """
        provider = "opencode-go"
        model_context_size = 8192
        api_key = "secret"
        """,
    )

    config = load_config(path)

    assert config.provider == "opencode-go"
    assert config.api_key == "secret"


def test_missing_file_raises_not_found(tmp_path: Path) -> None:
    with pytest.raises(ConfigFileNotFoundError):
        load_config(tmp_path / "does-not-exist.toml")


def test_malformed_toml_raises_parse_error(tmp_path: Path) -> None:
    path = _write(tmp_path, "this is = = not toml\n")

    with pytest.raises(ConfigParseError):
        load_config(path)


def test_missing_required_field_raises_validation_error(tmp_path: Path) -> None:
    # model_context_size omitted -> StrataConfig rejects it.
    path = _write(tmp_path, 'base_url = "http://127.0.0.1:8080/v1"\n')

    with pytest.raises(ConfigValidationError):
        load_config(path)


def test_non_positive_context_size_raises_validation_error(tmp_path: Path) -> None:
    path = _write(tmp_path, "model_context_size = 0\n")

    with pytest.raises(ConfigValidationError):
        load_config(path)


def test_blank_base_url_raises_validation_error(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        'base_url = "   "\nmodel_context_size = 4096\n',
    )

    with pytest.raises(ConfigValidationError):
        load_config(path)


def test_unknown_provider_in_toml_raises_error(tmp_path: Path) -> None:
    path = _write(tmp_path, 'provider = "unknown"\nmodel_context_size = 4096\n')

    with pytest.raises(UnknownProviderError):
        load_config(path)


def test_opencode_go_without_key_in_toml_raises_error(tmp_path: Path) -> None:
    path = _write(tmp_path, 'provider = "opencode-go"\nmodel_context_size = 4096\n')

    with pytest.raises(MissingApiKeyForProviderError):
        load_config(path)
