"""Thin OpenAI-compatible client for a local Strata inference server."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

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


# OpenAI wire payloads (messages, tool specs, tool-call entries) carry arbitrary
# JSON values: every consumer validates with isinstance at the use site before
# reading a value, so Any is the honest value type rather than a guessed one.
WireObject = dict[str, Any]

# A tool dispatcher executes one tool call by name and JSON-decoded args, and
# returns (content_for_the_model, optional_effect). Injected by the delegation
# layer so the client stays free of filesystem and subprocess knowledge.
ToolDispatch = Callable[[str, WireObject], "tuple[str, ToolEffect | None]"]


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
        return _all_model_ids(self._get_models())

    def _get_models(self) -> httpx.Response:
        """GET /v1/models, mapping a bad status and an unreachable server to typed errors."""
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
        return response

    def complete(
        self,
        model: str,
        system_prompt: str,
        user_content: str,
        reasoning_effort: str | None = None,
    ) -> CompletionResult:
        """Send one blocking chat completion and parse the result."""
        payload = _completion_payload(
            model=model,
            messages=_chat_messages(system_prompt, user_content),
            tools=None,
            temperature=self._config.temperature,
            reasoning_effort=reasoning_effort,
        )
        return _parse_completion(self._post_completion(payload))

    def _post_completion(self, payload: WireObject) -> httpx.Response:
        """POST one chat completion, mapping a transport failure to a typed error."""
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
        return response

    def complete_with_tools(
        self,
        model: str,
        system_prompt: str,
        user_content: str,
        tools: list[WireObject],
        dispatch: ToolDispatch,
        max_tool_rounds: int,
        reasoning_effort: str | None = None,
    ) -> ToolLoopResult:
        """Run a bounded OpenAI-compatible tool-calling loop and return the result.

        Each round sends the running conversation; a message with no tool calls is
        the worker's final answer. A malformed tool call is fed back as a skipped
        call rather than raising: failures are data inside this loop.
        """
        messages = _chat_messages(system_prompt, user_content)
        written_paths: list[str] = []
        commands_run: list[CommandRun] = []

        for round_index in range(max_tool_rounds):
            payload = _completion_payload(
                model=model,
                messages=messages,
                tools=tools,
                temperature=self._config.temperature,
                reasoning_effort=reasoning_effort,
            )
            message = _first_message(self._post_completion(payload))
            tool_calls = message.get("tool_calls")
            if not tool_calls:
                return _final_result(message, round_index, written_paths, commands_run)
            messages.append(message)
            messages.extend(_run_tool_round(tool_calls, dispatch, written_paths, commands_run))

        return _round_cap_result(max_tool_rounds, written_paths, commands_run)


def _chat_messages(system_prompt: str, user_content: str) -> list[WireObject]:
    """Build the opening system/user messages every completion request carries."""
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]


def _completion_payload(
    model: str,
    messages: list[WireObject],
    tools: list[WireObject] | None,
    temperature: float,
    reasoning_effort: str | None,
) -> WireObject:
    """Build one chat-completion body. Temperature comes from config, never the caller.

    Tools and tool_choice are omitted when there are none, so a text-only request
    stays exactly the body the backend expects. The thinking control is sent only
    when set, leaving the backend's own default in effect otherwise.
    """
    payload: WireObject = {
        "model": model,
        "temperature": temperature,
        "messages": messages,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
    if reasoning_effort is not None:
        payload["reasoning_effort"] = reasoning_effort
    return payload


def _first_message(response: httpx.Response) -> WireObject:
    """Return the first choice's message from a completion body, or a typed error."""
    try:
        message = response.json()["choices"][0]["message"]
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise CompletionResponseError(exc) from exc
    return message


def _final_result(
    message: WireObject,
    round_index: int,
    written_paths: list[str],
    commands_run: list[CommandRun],
) -> ToolLoopResult:
    """Close the loop when the model asked for no tools: that message is the answer."""
    return ToolLoopResult(
        output=message.get("content") or "",
        rounds_used=round_index + 1,
        hit_round_cap=False,
        written_paths=written_paths,
        commands_run=commands_run,
    )


def _round_cap_result(
    max_tool_rounds: int,
    written_paths: list[str],
    commands_run: list[CommandRun],
) -> ToolLoopResult:
    """Report the work done so far when the round budget ran out mid-task."""
    return ToolLoopResult(
        output="",
        rounds_used=max_tool_rounds,
        hit_round_cap=True,
        written_paths=written_paths,
        commands_run=commands_run,
    )


def _run_tool_round(
    tool_calls: list[WireObject],
    dispatch: ToolDispatch,
    written_paths: list[str],
    commands_run: list[CommandRun],
) -> list[WireObject]:
    """Execute one round's tool calls, returning the tool messages to feed back.

    Malformed calls contribute nothing: the loop stays alive so the worker can
    recover, rather than a parse failure ending the delegation.
    """
    messages: list[WireObject] = []
    for tool_call in tool_calls:
        message = _run_tool_call(tool_call, dispatch, written_paths, commands_run)
        if message is not None:
            messages.append(message)
    return messages


def _run_tool_call(
    tool_call: WireObject,
    dispatch: ToolDispatch,
    written_paths: list[str],
    commands_run: list[CommandRun],
) -> WireObject | None:
    """Run one tool call and return its tool message, or None if the call is malformed."""
    fields = _tool_call_fields(tool_call)
    if fields is None:
        return None
    call_id, name, raw_args = fields
    content, effect = dispatch(name, _decode_args(raw_args))
    _record_effect(effect, written_paths, commands_run)
    return {"role": "tool", "tool_call_id": call_id, "content": content}


def _tool_call_fields(tool_call: WireObject) -> tuple[Any, Any, Any] | None:
    """Pull id, name and raw arguments out of a wire tool call, or None if malformed.

    Missing keys, a non-mapping shape and an unexpected type are all data here:
    the model can emit anything, and none of it must end the delegation. The
    values are Any because they come from arbitrary JSON; consumers validate.
    """
    try:
        return (tool_call["id"], tool_call["function"]["name"], tool_call["function"]["arguments"])
    except KeyError, IndexError, TypeError:
        return None


def _decode_args(raw_args: Any) -> WireObject:
    """Decode a tool call's JSON arguments; anything unusable becomes no arguments."""
    try:
        decoded = json.loads(raw_args)
    except json.JSONDecodeError, TypeError:
        return {}
    # A JSON array or scalar decodes fine but has no keys for a dispatcher to read.
    if not isinstance(decoded, dict):
        return {}
    return {str(key): value for key, value in decoded.items()}


def _record_effect(
    effect: ToolEffect | None,
    written_paths: list[str],
    commands_run: list[CommandRun],
) -> None:
    """Accumulate a tool call's side effects so the caller can report what was touched."""
    if effect is not None and effect.written_path is not None:
        written_paths.append(effect.written_path)
    if effect is not None and effect.command_run is not None:
        commands_run.append(effect.command_run)


def _all_model_ids(response: httpx.Response) -> list[str]:
    """Extract all model ids from a /v1/models body, in order."""
    return [_model_id(entry) for entry in _model_entries(response)]


def _model_entries(response: httpx.Response) -> list[object]:
    """Return the advertised model entries, or a typed error when the body is unusable."""
    try:
        entries = response.json()["data"]
    except (ValueError, KeyError, TypeError) as exc:
        raise ModelDiscoveryError(exc) from exc

    if not isinstance(entries, list) or not entries:
        raise ModelDiscoveryError
    return entries


def _model_id(entry: Any) -> str:
    """Return one advertised model's id, or a typed error if it is missing or unusable.

    An entry is arbitrary JSON from the engine, so it is validated here rather
    than assumed: a bare string or a mapping without an id is a discovery failure.
    """
    try:
        model_id = entry["id"]
    except (KeyError, TypeError) as exc:
        raise ModelDiscoveryError(exc) from exc

    if not isinstance(model_id, str) or not model_id:
        raise ModelDiscoveryError
    return model_id


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


def _parse_usage(data: WireObject) -> TokenUsage | None:
    """Return token usage when both counts are present, else None."""
    usage = data.get("usage")
    if not isinstance(usage, dict):
        return None
    prompt = usage.get("prompt_tokens")
    completion = usage.get("completion_tokens")
    if isinstance(prompt, int) and isinstance(completion, int):
        return TokenUsage(prompt_tokens=prompt, completion_tokens=completion)
    return None
