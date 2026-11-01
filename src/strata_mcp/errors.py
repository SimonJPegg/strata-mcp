"""Explicit exception types raised while loading or validating configuration."""

from __future__ import annotations


class ConfigError(ValueError):
    """Base for configuration problems, so callers can catch one type."""


class BlankBaseUrlError(ConfigError):
    """Raised when base_url is empty or whitespace; it cannot reach Strata."""

    def __init__(self) -> None:
        super().__init__("base_url must not be empty")


class ConfigFileNotFoundError(ConfigError):
    """Raised when the configured config file path does not exist."""

    def __init__(self, path: str) -> None:
        super().__init__(f"config file not found: {path}")


class ConfigParseError(ConfigError):
    """Raised when the config file is not valid TOML."""

    def __init__(self, path: str, detail: str) -> None:
        super().__init__(f"could not parse config file {path}: {detail}")


class ConfigValidationError(ConfigError):
    """Raised when parsed config does not satisfy the StrataConfig model."""

    def __init__(self, path: str, detail: str) -> None:
        super().__init__(f"invalid config in {path}: {detail}")


class StrataClientError(Exception):
    """Base for failures talking to Strata, caught and mapped to results."""


class StrataUnreachableError(StrataClientError):
    """Raised when Strata cannot be reached at the configured base URL."""

    def __init__(self, base_url: str) -> None:
        super().__init__(f"could not reach Strata at {base_url}")


class ModelDiscoveryError(StrataClientError):
    """Raised when the loaded model id cannot be discovered from /v1/models."""

    def __init__(self, cause: object = "no usable model id") -> None:
        super().__init__(f"could not discover model from /v1/models: {cause}")


class CompletionResponseError(StrataClientError):
    """Raised when a completion response is empty or malformed."""

    def __init__(self, cause: object = "empty or malformed response") -> None:
        super().__init__(f"invalid completion response: {cause}")


class MissingErrorMessageError(ValueError):
    """Raised when a WorkerResult has error status but no error message."""

    def __init__(self) -> None:
        super().__init__("error status requires an error message")


class OversizedContextError(StrataClientError):
    """Raised when task+context exceed the declared model context size."""

    def __init__(self, estimated_tokens: int, limit: int) -> None:
        super().__init__(f"estimated {estimated_tokens} tokens exceed model context size {limit}")


class RuntimeBackstopError(StrataClientError):
    """Raised when a delegation exceeds the configured max runtime backstop."""

    def __init__(self, max_runtime_s: float) -> None:
        super().__init__(f"delegation exceeded max runtime backstop of {max_runtime_s}s")


class PathNotAllowedError(Exception):
    """Raised when a requested file path resolves outside the allowed dirs."""

    def __init__(self, path: str) -> None:
        super().__init__(f"path not allowed: {path}")


class CommandsNeedWriteDirError(ValueError):
    """Raised when allowed_commands is set but no write dir gives commands a cwd."""

    def __init__(self) -> None:
        super().__init__("allowed_commands requires a non-empty write_dirs_allowed")
