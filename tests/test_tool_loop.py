"""Tests for the bounded tool-use loop in StrataClient.complete_with_tools."""

from __future__ import annotations

import json
from collections.abc import Callable

import httpx
import pytest

from strata_mcp.client import StrataClient, ToolEffect, WireObject
from strata_mcp.config import StrataConfig
from strata_mcp.errors import CompletionResponseError, StrataUnreachableError


def _client(handler: Callable[[httpx.Request], httpx.Response]) -> StrataClient:
    config = StrataConfig(model_context_size=65536)
    return StrataClient(config, httpx.Client(transport=httpx.MockTransport(handler)))


def _tool_call(call_id: str, name: str, args: WireObject) -> WireObject:
    return {
        "id": call_id,
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(args)},
    }


def _assistant_with_tool_calls(calls: list[WireObject]) -> httpx.Response:
    return httpx.Response(
        200,
        json={"choices": [{"finish_reason": "tool_calls", "message": {"tool_calls": calls}}]},
    )


def _final(content: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


_TOOLS: list[WireObject] = [
    {"type": "function", "function": {"name": "read_file", "parameters": {}}}
]


def _noop_dispatch(name: str, args: WireObject) -> tuple[str, ToolEffect | None]:
    """Dispatcher that acknowledges a call without acting: for budget/shape tests."""
    return ("ok", None)


def test_loop_executes_tools_then_completes() -> None:
    # Round 1: model asks for read_file. Round 2: model gives final answer.
    responses = iter(
        [
            _assistant_with_tool_calls([_tool_call("c1", "read_file", {"path": "a.txt"})]),
            _final("done reading"),
        ]
    )
    # Each request body's "messages" is a *list* of wire messages, so the
    # collected entries are lists, not single wire objects.
    seen_messages: list[list[WireObject]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen_messages.append(body["messages"])
        return next(responses)

    dispatched: list[tuple[str, WireObject]] = []

    def dispatch(name: str, args: WireObject) -> tuple[str, ToolEffect | None]:
        dispatched.append((name, args))
        return ("file contents here", None)

    result = _client(handler).complete_with_tools(
        "m", "sys", "read a.txt", _TOOLS, dispatch, max_tool_rounds=5
    )

    assert result.output == "done reading"
    assert result.hit_round_cap is False
    assert result.rounds_used == 2
    assert dispatched == [("read_file", {"path": "a.txt"})]
    # Second request must carry the appended assistant + tool messages.
    assert any(m.get("role") == "tool" for m in seen_messages[1])


def test_loop_tracks_written_paths() -> None:
    responses = iter(
        [
            _assistant_with_tool_calls([_tool_call("c1", "write_file", {"path": "out.txt"})]),
            _final("wrote it"),
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return next(responses)

    def dispatch(name: str, args: WireObject) -> tuple[str, ToolEffect | None]:
        return ("ok", ToolEffect(written_path="/box/out.txt"))

    result = _client(handler).complete_with_tools(
        "m", "sys", "write out.txt", _TOOLS, dispatch, max_tool_rounds=5
    )

    assert result.written_paths == ["/box/out.txt"]


def test_loop_stops_at_round_cap() -> None:
    # Model never stops asking for tools.
    def handler(request: httpx.Request) -> httpx.Response:
        return _assistant_with_tool_calls([_tool_call("c", "read_file", {"path": "x"})])

    # The loop's ToolDispatch contract returns ToolEffect | None, not str; the
    # old loose annotation let a wrong return type slip through.
    def dispatch(name: str, args: WireObject) -> tuple[str, ToolEffect | None]:
        return ("content", None)

    result = _client(handler).complete_with_tools(
        "m", "sys", "loop forever", _TOOLS, dispatch, max_tool_rounds=3
    )

    assert result.hit_round_cap is True
    assert result.rounds_used == 3


def test_loop_handles_malformed_tool_arguments() -> None:
    # arguments is not valid JSON -> dispatch receives {}.
    bad_call = {
        "id": "c1",
        "type": "function",
        "function": {"name": "read_file", "arguments": "not json{"},
    }
    responses = iter(
        [
            httpx.Response(
                200,
                json={"choices": [{"message": {"tool_calls": [bad_call]}}]},
            ),
            _final("recovered"),
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return next(responses)

    received: list[WireObject] = []

    # The loop's ToolDispatch contract returns ToolEffect | None, not str; the
    # old loose annotation let a wrong return type slip through.
    def dispatch(name: str, args: WireObject) -> tuple[str, ToolEffect | None]:
        received.append(args)
        return ("ok", None)

    result = _client(handler).complete_with_tools(
        "m", "sys", "bad args", _TOOLS, dispatch, max_tool_rounds=5
    )

    assert result.output == "recovered"
    assert received == [{}]


def test_loop_malformed_envelope_maps_to_response_error() -> None:
    # The engine returns a body with no 'choices': must become a typed
    # CompletionResponseError, not an unhandled KeyError escaping the loop.
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": "shape"})

    def dispatch(name: str, args: WireObject) -> tuple[str, ToolEffect | None]:
        return ("ok", None)

    with pytest.raises(CompletionResponseError):
        _client(handler).complete_with_tools("m", "sys", "q", _TOOLS, dispatch, max_tool_rounds=5)


def test_loop_skips_malformed_tool_call_entry() -> None:
    # A tool_calls list whose entry is missing 'function' must not crash the
    # loop; the bad entry is skipped and the run still completes.
    bad_entry = {"id": "c1", "type": "function"}  # no 'function' key
    responses = iter(
        [
            httpx.Response(200, json={"choices": [{"message": {"tool_calls": [bad_entry]}}]}),
            _final("recovered after skipping bad call"),
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return next(responses)

    dispatched: list[str] = []

    def dispatch(name: str, args: WireObject) -> tuple[str, ToolEffect | None]:
        dispatched.append(name)
        return ("ok", None)

    result = _client(handler).complete_with_tools(
        "m", "sys", "q", _TOOLS, dispatch, max_tool_rounds=5
    )

    assert result.output == "recovered after skipping bad call"
    assert dispatched == []  # the malformed call was skipped, never dispatched


def test_tool_loop_request_bodies_carry_the_granted_tools() -> None:
    # A tool-using request must advertise the tools, or the engine cannot call
    # them and the worker silently degenerates to a text-only answer.
    seen: list[WireObject] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return _final("answered")

    _client(handler).complete_with_tools("m", "sys", "q", _TOOLS, _noop_dispatch, max_tool_rounds=2)

    assert "tools" in seen[0]
    assert seen[0]["tool_choice"] == "auto"


def test_zero_round_budget_never_reaches_the_engine() -> None:
    # A caller may grant tools but no rounds: the loop must return the capped
    # envelope without spending a request, not hang or recurse.
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(request.url.path)
        return _final("never reached")

    result = _client(handler).complete_with_tools(
        "m", "sys", "q", _TOOLS, _noop_dispatch, max_tool_rounds=0
    )

    assert requested == []
    assert result.hit_round_cap is True
    assert result.rounds_used == 0
    assert result.output == ""


def test_tool_call_entry_that_is_not_a_mapping_is_skipped() -> None:
    # The engine can emit anything in a tool_calls list; a bare string must not
    # crash the loop or be dispatched under some invented name.
    responses = iter(
        [
            httpx.Response(200, json={"choices": [{"message": {"tool_calls": ["not-a-call"]}}]}),
            _final("recovered"),
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return next(responses)

    dispatched: list[str] = []

    def dispatch(name: str, args: WireObject) -> tuple[str, ToolEffect | None]:
        dispatched.append(name)
        return ("ok", None)

    result = _client(handler).complete_with_tools(
        "m", "sys", "q", _TOOLS, dispatch, max_tool_rounds=5
    )

    assert result.output == "recovered"
    assert dispatched == []


def test_arguments_that_are_not_a_mapping_reach_dispatch_empty() -> None:
    # Valid JSON that is not an object (an array) decodes fine but carries no
    # keys; the dispatcher must see no arguments rather than crash.
    call = {
        "id": "c1",
        "type": "function",
        "function": {"name": "read_file", "arguments": json.dumps([1, 2])},
    }
    responses = iter(
        [
            httpx.Response(200, json={"choices": [{"message": {"tool_calls": [call]}}]}),
            _final("recovered"),
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return next(responses)

    received: list[WireObject] = []

    def dispatch(name: str, args: WireObject) -> tuple[str, ToolEffect | None]:
        received.append(args)
        return ("ok", None)

    result = _client(handler).complete_with_tools(
        "m", "sys", "q", _TOOLS, dispatch, max_tool_rounds=5
    )

    assert result.output == "recovered"
    assert received == [{}]


def test_transport_failure_mid_loop_still_maps_to_unreachable() -> None:
    # The engine dying between rounds is the same failure as dying before the
    # first: a typed error the delegation layer turns into an envelope.
    calls = iter([_assistant_with_tool_calls([_tool_call("c1", "read_file", {"path": "a"})])])

    def handler(request: httpx.Request) -> httpx.Response:
        try:
            return next(calls)
        except StopIteration:
            raise httpx.ConnectError("refused") from None

    def dispatch(name: str, args: WireObject) -> tuple[str, ToolEffect | None]:
        return ("content", None)

    with pytest.raises(StrataUnreachableError):
        _client(handler).complete_with_tools("m", "sys", "q", _TOOLS, dispatch, max_tool_rounds=5)
