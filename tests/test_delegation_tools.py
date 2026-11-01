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


def test_allowed_commands_without_write_dir_is_rejected() -> None:
    # A command menu with no write dir has no fenced cwd: refuse up front.
    def handler(request: httpx.Request) -> httpx.Response:
        return _models()

    result = run_delegation(
        _client(handler),
        StrataConfig(model_context_size=65536),
        "run tests",
        "",
        allowed_commands=["echo hi"],
    )

    assert result.status is WorkerStatus.ERROR
    assert "write_dirs_allowed" in (result.error or "")


def test_granted_command_runs_through_loop_and_reports_commands_run(tmp_path: Path) -> None:
    box = str(tmp_path)
    seen: dict = {}
    responses = iter(
        [
            _models(),
            httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "tool_calls": [_tool_call("run_command", {"command": "echo hi"})]
                            }
                        }
                    ]
                },
            ),
            httpx.Response(
                200, json={"choices": [{"message": {"content": f"ran it\n{MARKER_COMPLETED}"}}]}
            ),
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/chat/completions":
            seen.setdefault("bodies", []).append(json.loads(request.content))
        return next(responses)

    result = run_delegation(
        _client(handler),
        StrataConfig(model_context_size=65536),
        "run echo",
        "",
        write_dirs_allowed=[box],
        allowed_commands=["echo hi"],
    )

    assert result.status is WorkerStatus.OK
    # The command tool was offered.
    tool_names = {
        t["function"]["name"] for t in seen["bodies"][0]["tools"]
    }
    assert "run_command" in tool_names
    # The executed command is reported with its exit code.
    assert len(result.commands_run) == 1
    assert result.commands_run[0].command == "echo hi"
    assert result.commands_run[0].exit_code == 0


def test_no_commands_means_no_command_tool(tmp_path: Path) -> None:
    box = str(tmp_path)
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/models":
            return _models()
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200, json={"choices": [{"message": {"content": f"t\n{MARKER_COMPLETED}"}}]}
        )

    run_delegation(
        _client(handler),
        StrataConfig(model_context_size=65536),
        "t",
        "",
        write_dirs_allowed=[box],
    )

    tool_names = {t["function"]["name"] for t in seen["body"]["tools"]}
    assert "run_command" not in tool_names
