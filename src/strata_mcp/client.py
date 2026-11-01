"""Thin OpenAI-compatible client for a local Strata inference server."""

from __future__ import annotations

import json
from collections.abc import Callable

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


class CommandRun(BaseModel):
    """One executed command and its exit code, surfaced to the caller."""

    command: str
    exit_code: int | None = None


class ToolEffect(BaseModel):
    """Side effect of a tool call: a written path and/or an executed command."""

    written_path: str | None = None
    command_run: CommandRun | None = None


class ToolLoopResult(BaseModel):
    """Outcome of a bounded tool-use loop."""

    output: str
    rounds_used: int
    hit_round_cap: bool = False
    written_paths: list[str] = []
    commands_run: list[CommandRun] = []


# A tool dispatcher executes one tool call by name and JSON-decoded args, and
# returns (content_for_the_model, optional_effect). Injected by the delegation
# layer so the client stays free of filesystem and subprocess knowledge.
ToolDispatch = Callable[[str, dict], "tuple[str, ToolEffect | None]"]


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

    def complete_with_tools(
        self,
        model: str,
        system_prompt: str,
        user_content: str,
        tools: list[dict],
        dispatch: ToolDispatch,
        max_tool_rounds: int,
        reasoning_effort: str | None = None,
    ) -> ToolLoopResult:
        """Run a bounded OpenAI-compatible tool-calling loop and return the result."""
        messages: list[dict] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]
        written_paths: list[str] = []
        commands_run: list[CommandRun] = []

        for round_index in range(max_tool_rounds):
            payload: dict[str, object] = {
                "model": model,
                "temperature": self._config.temperature,
                "messages": messages,
                "tools": tools,
                "tool_choice": "auto",
            }
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

            msg = response.json()["choices"][0]["message"]
            tool_calls = msg.get("tool_calls")

            if not tool_calls:
                return ToolLoopResult(
                    output=msg.get("content") or "",
                    rounds_used=round_index + 1,
                    hit_round_cap=False,
                    written_paths=written_paths,
                    commands_run=commands_run,
                )

            messages.append(msg)
            for tc in tool_calls:
                name = tc["function"]["name"]
                try:
                    args = json.loads(tc["function"]["arguments"])
                except json.JSONDecodeError:
                    args = {}
                content, effect = dispatch(name, args)
                if effect is not None and effect.written_path is not None:
                    written_paths.append(effect.written_path)
                if effect is not None and effect.command_run is not None:
                    commands_run.append(effect.command_run)
                messages.append(
                    {"role": "tool", "tool_call_id": tc["id"], "content": content}
                )

        return ToolLoopResult(
            output="",
            rounds_used=max_tool_rounds,
            hit_round_cap=True,
            written_paths=written_paths,
            commands_run=commands_run,
        )


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
