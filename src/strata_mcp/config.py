"""Configuration model for the backend connection and delegation limits."""

from __future__ import annotations

import tomllib
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

from strata_mcp.errors import (
    BlankBaseUrlError,
    ConfigFileNotFoundError,
    ConfigParseError,
    ConfigValidationError,
    MissingApiKeyForProviderError,
    UnknownProviderError,
)
from strata_mcp.providers import known_providers, provider_profile


class StrataConfig(BaseModel):
    """Connection settings and limits for reaching the configured backend.

    Exists so connection details live in config, not tool parameters, keeping
    the worker's attention on the task rather than on plumbing.
    """

    # The backend provider. Selects defaults, required headers, and how
    # capabilities are parsed from the model-listing endpoint.
    provider: str = Field(default="strata")
    # The provider's OpenAI-compatible base URL; defaults to the provider's
    # own local address and is overridable per deployment.
    base_url: str | None = Field(default=None)
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
    def _base_url_not_blank(cls, value: str | None) -> str | None:
        """Reject a blank base_url early; a blank URL cannot reach the backend."""
        if value is None:
            return None
        if not value.strip():
            raise BlankBaseUrlError
        return value.rstrip("/")

    @field_validator("provider")
    @classmethod
    def _provider_is_known(cls, value: str) -> str:
        """Reject an unknown provider early; only configured dialects can be loaded."""
        if value not in known_providers():
            raise UnknownProviderError(value)
        return value

    @property
    def endpoint(self) -> str:
        """Return the effective base URL, so callers never handle the unset case."""
        if self.base_url is not None:
            return self.base_url
        return provider_profile(self.provider).default_base_url.rstrip("/")

    @model_validator(mode="after")
    def _apply_provider_defaults(self) -> StrataConfig:
        """Apply provider-specific defaults when the operator did not override them."""
        if self.base_url is None:
            self.base_url = self.endpoint
        return self

    @model_validator(mode="after")
    def _provider_requires_api_key(self) -> StrataConfig:
        """Providers that always require a key must have one configured."""
        if self.provider == "opencode-go" and not self.api_key:
            raise MissingApiKeyForProviderError(self.provider)
        return self


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
        for error in exc.errors():
            # Pydantic wraps validator exceptions in ctx; these two stay
            # specific for callers. Blank base_url deliberately stays wrapped.
            original = error.get("ctx", {}).get("error")
            if isinstance(
                original,
                (MissingApiKeyForProviderError, UnknownProviderError),
            ):
                raise original from exc
        raise ConfigValidationError(str(path), str(exc)) from exc
