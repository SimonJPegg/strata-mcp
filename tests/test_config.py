"""Tests for the StrataConfig model: defaults, validation, field behaviour."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from strata_mcp.config import StrataConfig


def test_minimal_config_applies_defaults() -> None:
    config = StrataConfig(model_context_size=32768)

    assert config.base_url == "http://127.0.0.1:8080/v1"
    assert config.model_context_size == 32768
    assert config.max_runtime_s is None
    assert config.api_key is None
    assert config.temperature == 0.0


@pytest.mark.parametrize("bad_temp", [-0.1, 2.1, 5.0])
def test_out_of_range_temperature_is_rejected(bad_temp: float) -> None:
    with pytest.raises(ValidationError):
        StrataConfig(model_context_size=4096, temperature=bad_temp)


@pytest.mark.parametrize("good_temp", [0.0, 0.7, 2.0])
def test_in_range_temperature_is_accepted(good_temp: float) -> None:
    config = StrataConfig(model_context_size=4096, temperature=good_temp)

    assert config.temperature == good_temp


def test_full_config_round_trips_values() -> None:
    config = StrataConfig(
        base_url="http://10.0.0.5:9000/v1",
        model_context_size=8192,
        max_runtime_s=3600.0,
        api_key="secret-token",
    )

    assert config.base_url == "http://10.0.0.5:9000/v1"
    assert config.model_context_size == 8192
    assert config.max_runtime_s == 3600.0
    assert config.api_key == "secret-token"


def test_trailing_slash_is_stripped_from_base_url() -> None:
    config = StrataConfig(base_url="http://127.0.0.1:8080/v1/", model_context_size=4096)

    assert config.base_url == "http://127.0.0.1:8080/v1"


@pytest.mark.parametrize("bad_size", [0, -1, -4096])
def test_non_positive_context_size_is_rejected(bad_size: int) -> None:
    with pytest.raises(ValidationError):
        StrataConfig(model_context_size=bad_size)


def test_blank_base_url_is_rejected() -> None:
    with pytest.raises(ValidationError):
        StrataConfig(base_url="   ", model_context_size=4096)


@pytest.mark.parametrize("bad_runtime", [0, -5.0])
def test_non_positive_max_runtime_is_rejected(bad_runtime: float) -> None:
    with pytest.raises(ValidationError):
        StrataConfig(model_context_size=4096, max_runtime_s=bad_runtime)
