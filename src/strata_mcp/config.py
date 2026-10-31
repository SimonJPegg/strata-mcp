"""Configuration model for the Strata connection and delegation limits."""

from __future__ import annotations

import tomllib
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError, field_validator

from strata_mcp.errors import (
    BlankBaseUrlError,
    ConfigFileNotFoundError,
    ConfigParseError,
    ConfigValidationError,
)


class StrataConfig(BaseModel):
    """Connection settings and limits for reaching a local Strata server.

    Exists so connection details live in config, not tool parameters, keeping
    the worker's attention on the task rather than on plumbing.
    """

    # Strata's default OpenAI-compatible address; overridable per deployment.
    base_url: str = Field(default="http://127.0.0.1:8080/v1")
    # Context length Strata was launched with (--context). Advisory budget the
    # server surfaces to the caller; see the oversized-context backstop.
    model_context_size: int = Field(gt=0)
    # Safety backstop only. None means no enforced wall-clock limit.
    max_runtime_s: float | None = Field(default=None, gt=0)
    # Only needed beyond localhost; localhost serves without a key by default.
    api_key: str | None = Field(default=None)
    # Sampling temperature applied to every completion. Defaults to 0 so a
    # bounded worker is literal and as reproducible as the engine allows.
    # Note: 0 does not guarantee determinism on MoE models, whose expert
    # routing can still vary; it only removes the sampling-layer randomness.
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)

    @field_validator("base_url")
    @classmethod
    def _base_url_not_blank(cls, value: str) -> str:
        """Reject a blank base_url early; a blank URL cannot reach Strata."""
        if not value.strip():
            raise BlankBaseUrlError
        return value.rstrip("/")


def load_config(path: Path) -> StrataConfig:
    """Load and validate config from a TOML file, with explicit errors.

    Each failure mode (missing file, bad TOML, invalid values) maps to a
    specific exception so callers can report precisely rather than guess.
    """
    if not path.is_file():
        raise ConfigFileNotFoundError(str(path))

    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ConfigParseError(str(path), str(exc)) from exc

    try:
        return StrataConfig.model_validate(raw)
    except ValidationError as exc:
        raise ConfigValidationError(str(path), str(exc)) from exc
