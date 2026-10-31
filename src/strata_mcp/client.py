"""Thin OpenAI-compatible client for a local Strata inference server."""

from __future__ import annotations

import httpx
from pydantic import BaseModel

from strata_mcp.config import StrataConfig
from strata_mcp.errors import (
    CompletionResponseError,
    ModelDiscoveryError,
    StrataUnreachableError,
)


class TokenUsage(BaseModel):
    """Prompt and completion token counts, when Strata reports them."""

    prompt_tokens: int
    completion_tokens: int


class CompletionResult(BaseModel):
    """The parsed outcome of one chat-completion call."""

    output: str
    token_usage: TokenUsage | None = None


def _auth_headers(api_key: str | None) -> dict[str, str]:
    """Build auth headers; empty when no key is configured (localhost case)."""
    if api_key:
        return {"Authorization": f"Bearer {api_key}"}
    return {}


class StrataClient:
    """Reaches a local Strata server over its OpenAI-compatible API.

    Exists to isolate all HTTP concerns so the delegation tool stays pure
    orchestration and failures map to typed errors rather than leaking.
    """

    def __init__(self, config: StrataConfig, client: httpx.Client) -> None:
        # The httpx.Client is injected so tests can supply a MockTransport.
        self._config = config
        self._client = client

    def discover_models(self) -> list[str]:
        """Return all available model ids from GET /v1/models, in order."""
        try:
            response = self._client.get(
                f"{self._config.base_url}/models",
                headers=_auth_headers(self._config.api_key),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise ModelDiscoveryError(exc) from exc
        except httpx.HTTPError as exc:
            raise StrataUnreachableError(self._config.base_url) from exc

        return _all_model_ids(response)

    def complete(
        self,
        model: str,
        system_prompt: str,
        user_content: str,
        reasoning_effort: str | None = None,
    ) -> CompletionResult:
        """Send one blocking chat completion and parse the result."""
        payload: dict[str, object] = {
            "model": model,
            # Temperature comes from config (default 0): a worker doing a
            # bounded task should be literal and as reproducible as the engine
            # allows. See StrataConfig.temperature for the MoE determinism note.
            "temperature": self._config.temperature,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
        }
        # Unified thinking control: sent only when the caller set it, so an
        # unset value leaves the backend's own default in effect.
        if reasoning_effort is not None:
            payload["reasoning_effort"] = reasoning_effort
        try:
            response = self._client.post(
                f"{self._config.base_url}/chat/completions",
                headers=_auth_headers(self._config.api_key),
                json=payload,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise CompletionResponseError(exc) from exc
        except httpx.HTTPError as exc:
            raise StrataUnreachableError(self._config.base_url) from exc

        return _parse_completion(response)


def _all_model_ids(response: httpx.Response) -> list[str]:
    """Extract all model ids from a /v1/models response body, in order."""
    try:
        models = response.json()["data"]
    except (ValueError, KeyError, TypeError) as exc:
        raise ModelDiscoveryError(exc) from exc

    if not isinstance(models, list) or not models:
        raise ModelDiscoveryError

    model_ids: list[str] = []
    for model in models:
        try:
            model_id = model["id"]
        except (KeyError, TypeError) as exc:
            raise ModelDiscoveryError(exc) from exc
        if not isinstance(model_id, str) or not model_id:
            raise ModelDiscoveryError
        model_ids.append(model_id)
    return model_ids


def _parse_completion(response: httpx.Response) -> CompletionResult:
    """Parse output text and optional token usage from a completion body."""
    try:
        data = response.json()
        content = data["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise CompletionResponseError(exc) from exc

    if not isinstance(content, str) or not content.strip():
        raise CompletionResponseError

    return CompletionResult(output=content, token_usage=_parse_usage(data))


def _parse_usage(data: dict) -> TokenUsage | None:
    """Return token usage when both counts are present, else None."""
    usage = data.get("usage")
    if not isinstance(usage, dict):
        return None
    prompt = usage.get("prompt_tokens")
    completion = usage.get("completion_tokens")
    if isinstance(prompt, int) and isinstance(completion, int):
        return TokenUsage(prompt_tokens=prompt, completion_tokens=completion)
    return None
