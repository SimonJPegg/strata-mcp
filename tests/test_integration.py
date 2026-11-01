"""Live integration tests against a running local Strata instance.

Skipped unless STRATA_MCP_IT=1. These assert only behaviour that is
deterministic given a reachable Strata — invariants of our own code, never the
model's output text or its compliance with the prompt (which are not
reproducible on a quantised MoE model). Reads connection details from the
environment so no credentials are hardcoded:

    STRATA_MCP_IT=1 \\
    STRATA_IT_BASE_URL=http://127.0.0.1:8080/v1 \\
    STRATA_IT_CONTEXT=65536 \\
    STRATA_IT_API_KEY=... \\
    uv run pytest tests/test_integration.py -v
"""

from __future__ import annotations

import json as json_mod
import os
import time
from pathlib import Path
from typing import Any

import httpx
import pytest

from strata_mcp.client import StrataClient
from strata_mcp.config import StrataConfig
from strata_mcp.delegation import run_delegation
from strata_mcp.result import ReasoningEffort, WorkerStatus
from strata_mcp.server import delegate_task_impl, list_models_impl
from strata_mcp.tools import make_dispatch

pytestmark = pytest.mark.skipif(
    os.environ.get("STRATA_MCP_IT") != "1",
    reason="live Strata integration; set STRATA_MCP_IT=1 to run",
)

_VALID_STATUSES = set(WorkerStatus)


def _base_url() -> str:
    return os.environ.get("STRATA_IT_BASE_URL", "http://127.0.0.1:8080/v1")


def _api_key() -> str | None:
    return os.environ.get("STRATA_IT_API_KEY")


def _config(**overrides: object) -> StrataConfig:
    # Unpacked kwargs into the pydantic constructor: keys name specific fields,
    # so Any per key is the honest granularity, not a lazy catch-all.
    params: dict[str, Any] = {
        "base_url": _base_url(),
        "model_context_size": int(os.environ.get("STRATA_IT_CONTEXT", "65536")),
        "api_key": _api_key(),
    }
    params.update(overrides)
    return StrataConfig(**params)


def _client(config: StrataConfig) -> StrataClient:
    return StrataClient(config, httpx.Client(timeout=None))


def test_model_discovery_returns_real_ids() -> None:
    models = _client(_config()).discover_models()

    assert isinstance(models, list)
    assert models
    assert all(isinstance(m, str) and m for m in models)


def test_delegation_returns_a_valid_envelope() -> None:
    response = delegate_task_impl(_config(), task="Reply with exactly the word: pong", context="")

    # Deterministic invariants of our code, not the model's text.
    assert response.result.status in _VALID_STATUSES
    assert response.result.status is not WorkerStatus.ERROR
    assert response.result.output.strip() != ""
    assert response.result.elapsed_s >= 0.0
    assert response.model_context_size > 0


def test_real_engine_populates_token_usage() -> None:
    result = run_delegation(_client(_config()), _config(), task="Reply with: ok", context="")

    assert result.status is not WorkerStatus.ERROR
    assert result.token_usage is not None
    assert result.token_usage.prompt_tokens > 0
    assert result.token_usage.completion_tokens > 0


def test_missing_api_key_is_rejected_when_required() -> None:
    if not _api_key():
        pytest.skip("Strata instance does not require an API key")

    result = run_delegation(
        _client(_config(api_key=None)), _config(api_key=None), task="hi", context=""
    )

    # Discovery/completion should fail auth and surface as a structured error.
    assert result.status is WorkerStatus.ERROR
    assert result.error is not None


def test_slow_real_call_is_not_timed_out() -> None:
    # Regression guard: a real completion commonly runs longer than httpx's
    # former default 5s timeout. It must still return a result, not an error.
    result = run_delegation(
        _client(_config()),
        _config(),
        task="Write a detailed six sentence explanation of how a hash map works.",
        context="",
    )

    assert result.status is not WorkerStatus.ERROR
    assert result.output.strip() != ""


def test_configured_temperature_reaches_strata() -> None:
    # Assert at the wire level that our configured temperature is sent, which
    # is deterministic regardless of what the model then generates. Uses a
    # recording transport: this checks our code's payload, not the engine.
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "m"}]})
        seen["temperature"] = json_mod.loads(request.content)["temperature"]
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    config = _config(temperature=0.0)
    client = StrataClient(config, httpx.Client(transport=httpx.MockTransport(handler)))
    run_delegation(client, config, task="Reply with: ok", context="")

    assert seen["temperature"] == 0.0


def test_oversized_context_never_contacts_strata() -> None:
    # Deterministic: the pre-check fires on size alone, before any network call.
    tiny = _config(model_context_size=4)

    start = time.monotonic()
    result = run_delegation(_client(tiny), tiny, task="x" * 1000, context="y" * 1000)
    elapsed = time.monotonic() - start

    assert result.status is WorkerStatus.ERROR
    assert result.error is not None
    assert "exceed model context size" in result.error
    assert elapsed < 1.0  # no network round-trip happened


def test_list_models_and_explicit_model_delegation() -> None:
    config = _config()
    http = httpx.Client(timeout=None)
    try:
        models = list_models_impl(config, http)
    finally:
        http.close()

    assert models  # at least one model reported
    assert all(isinstance(m, str) and m for m in models)

    # Delegate with an explicit model id taken from the live list.
    response = delegate_task_impl(config, task="Reply with: ok", context="", model=models[0])

    assert response.result.status is not WorkerStatus.ERROR
    assert response.result.output.strip() != ""


def test_reasoning_effort_none_reduces_tokens() -> None:
    config = _config()
    task = "What is 17 + 25? Answer with just the number."

    default = delegate_task_impl(config, task=task, context="")
    no_think = delegate_task_impl(
        config, task=task, context="", reasoning_effort=ReasoningEffort.NONE
    )

    assert default.result.token_usage is not None
    assert no_think.result.token_usage is not None
    # Turning thinking off must not produce MORE completion tokens; on this
    # model it produces dramatically fewer. Assert the deterministic direction.
    assert (
        no_think.result.token_usage.completion_tokens
        <= default.result.token_usage.completion_tokens
    )


def test_file_tools_fence_holds_against_live_worker(tmp_path: Path) -> None:
    """Live: grant a temp dir, ask the worker to write; assert the fence holds.

    The model's compliance is not asserted (it is non-deterministic). What is
    asserted is our contract: a valid status, and every reported written path
    sits inside the granted directory — the fence is never escaped, whatever the
    worker did.
    """
    box = tmp_path / "box"
    box.mkdir()
    (box / "seed.txt").write_text("the secret word is plum", encoding="utf-8")

    config = _config()
    response = delegate_task_impl(
        config,
        task=(
            "Read seed.txt in the granted directory, then write a file named "
            "copy.txt in the same directory containing the secret word."
        ),
        context=f"The granted directory is {box}.",
        read_dirs_allowed=[str(box)],
        write_dirs_allowed=[str(box)],
        max_tool_rounds=6,
    )

    assert response.result.status in _VALID_STATUSES
    # The fence invariant: anything written is inside the granted box.
    for written in response.result.files_written:
        assert os.path.realpath(written).startswith(os.path.realpath(box))


def test_file_tools_refuse_outside_fence_is_deterministic(tmp_path: Path) -> None:
    """The fence refusal does not depend on the model: the dispatcher refuses
    an out-of-fence path directly."""
    box = tmp_path / "box"
    box.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()

    dispatch = make_dispatch([str(box)], [str(box)], [], 300)
    content, effect = dispatch("write_file", {"path": str(outside / "x.txt"), "content": "no"})

    assert effect is None
    assert content.startswith("ERROR")
    assert not (outside / "x.txt").exists()


def test_command_tool_runs_through_the_stack(tmp_path: Path) -> None:
    """Live: grant an exact command menu and assert our invariants hold.

    The model's compliance is not asserted. What is asserted is our contract:
    a valid status, and every reported command came from the granted menu with
    an exit code — the worker never ran anything off-menu.
    """
    box = tmp_path / "box"
    box.mkdir()
    menu = ["echo strata-was-here"]

    config = _config()
    response = delegate_task_impl(
        config,
        task=(
            "Run the approved command, then report that you ran it. The command "
            "is exactly: echo strata-was-here"
        ),
        context=f"The granted working directory is {box}.",
        write_dirs_allowed=[str(box)],
        allowed_commands=menu,
        max_command_timeout_s=30,
        max_tool_rounds=6,
    )

    assert response.result.status in _VALID_STATUSES
    # The menu invariant: anything run came from the granted list, with an exit code.
    for run in response.result.commands_run:
        assert run.command in menu
        assert run.exit_code is not None


def test_command_tool_refuses_off_menu_is_deterministic(tmp_path: Path) -> None:
    """The off-menu refusal does not depend on the model: the dispatcher refuses
    a command not in the granted menu directly."""
    box = tmp_path / "box"
    box.mkdir()

    dispatch = make_dispatch([], [str(box)], ["echo ok"], 30)
    content, effect = dispatch("run_command", {"command": "rm -rf /"})

    assert effect is None
    assert content.startswith("ERROR")
