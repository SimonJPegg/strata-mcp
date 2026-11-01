"""Tests for the bounded tool-use loop in StrataClient.complete_with_tools."""

from __future__ import annotations

import json

import httpx

from strata_mcp.client import StrataClient, ToolEffect
from strata_mcp.config import StrataConfig


def _client(handler) -> StrataClient:
    config = StrataConfig(model_context_size=65536)
    return StrataClient(config, httpx.Client(transport=httpx.MockTransport(handler)))


def _tool_call(call_id: str, name: str, args: dict) -> dict:
    return {
        "id": call_id,
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(args)},
    }


def _assistant_with_tool_calls(calls: list[dict]) -> httpx.Response:
    return httpx.Response(
        200,
        json={"choices": [{"finish_reason": "tool_calls", "message": {"tool_calls": calls}}]},
    )


def _final(content: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


_TOOLS = [{"type": "function", "function": {"name": "read_file", "parameters": {}}}]


def test_loop_executes_tools_then_completes() -> None:
    # Round 1: model asks for read_file. Round 2: model gives final answer.
    responses = iter(
        [
            _assistant_with_tool_calls([_tool_call("c1", "read_file", {"path": "a.txt"})]),
            _final("done reading"),
        ]
    )
    seen_messages: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen_messages.append(body["messages"])
        return next(responses)

    dispatched: list[tuple[str, dict]] = []

    def dispatch(name: str, args: dict) -> tuple[str, ToolEffect | None]:
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

    def dispatch(name: str, args: dict) -> tuple[str, ToolEffect | None]:
        return ("ok", ToolEffect(written_path="/box/out.txt"))

    result = _client(handler).complete_with_tools(
        "m", "sys", "write out.txt", _TOOLS, dispatch, max_tool_rounds=5
    )

    assert result.written_paths == ["/box/out.txt"]


def test_loop_stops_at_round_cap() -> None:
    # Model never stops asking for tools.
    def handler(request: httpx.Request) -> httpx.Response:
        return _assistant_with_tool_calls([_tool_call("c", "read_file", {"path": "x"})])

    def dispatch(name: str, args: dict) -> tuple[str, str | None]:
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

    received: list[dict] = []

    def dispatch(name: str, args: dict) -> tuple[str, str | None]:
        received.append(args)
        return ("ok", None)

    result = _client(handler).complete_with_tools(
        "m", "sys", "bad args", _TOOLS, dispatch, max_tool_rounds=5
    )

    assert result.output == "recovered"
    assert received == [{}]
