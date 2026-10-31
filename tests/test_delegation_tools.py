"""Tests for run_delegation with fenced file tools (Stage 2 wiring)."""

from __future__ import annotations

import json
from pathlib import Path

import httpx

from strata_mcp.client import StrataClient
from strata_mcp.config import StrataConfig
from strata_mcp.delegation import run_delegation
from strata_mcp.mapping import MARKER_COMPLETED
from strata_mcp.result import WorkerStatus


def _client(handler) -> StrataClient:
    return StrataClient(
        StrataConfig(model_context_size=65536), httpx.Client(transport=httpx.MockTransport(handler))
    )


def _models() -> httpx.Response:
    return httpx.Response(200, json={"data": [{"id": "m"}]})


def _tool_call(name: str, args: dict) -> dict:
    return {
        "id": "c1",
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(args)},
    }


def test_no_allowlists_uses_text_only_path(tmp_path: Path) -> None:
    # With no dirs granted, the request must carry NO tools.
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/models":
            return _models()
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200, json={"choices": [{"message": {"content": f"text\n{MARKER_COMPLETED}"}}]}
        )

    result = run_delegation(_client(handler), StrataConfig(model_context_size=65536), "t", "")

    assert result.status is WorkerStatus.OK
    assert "tools" not in seen["body"]


def test_granted_write_runs_tool_loop_and_reports_written(tmp_path: Path) -> None:
    box = str(tmp_path)
    responses = iter(
        [
            _models(),
            httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "tool_calls": [
                                    _tool_call(
                                        "write_file", {"path": f"{box}/out.txt", "content": "hi"}
                                    )
                                ]
                            }
                        }
                    ]
                },
            ),
            httpx.Response(
                200, json={"choices": [{"message": {"content": f"done\n{MARKER_COMPLETED}"}}]}
            ),
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return next(responses)

    result = run_delegation(
        _client(handler),
        StrataConfig(model_context_size=65536),
        "write a file",
        "",
        write_dirs_allowed=[box],
    )

    assert result.status is WorkerStatus.OK
    assert (tmp_path / "out.txt").read_text() == "hi"
    assert result.files_written == [str((tmp_path / "out.txt").resolve())]


def test_round_cap_returns_needs_input() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/models":
            return _models()
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"tool_calls": [_tool_call("read_file", {"path": "/tmp/x"})]}}
                ]
            },
        )

    result = run_delegation(
        _client(handler),
        StrataConfig(model_context_size=65536),
        "loop",
        "",
        read_dirs_allowed=["/tmp"],
        max_tool_rounds=2,
    )

    assert result.status is WorkerStatus.NEEDS_INPUT
