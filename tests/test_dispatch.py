"""Tests for the tool dispatcher: every call is fenced, refusals are content."""

from __future__ import annotations

from pathlib import Path

import pytest

from strata_mcp.client import ToolEffect
from strata_mcp.tools import build_tools, make_dispatch


def test_grants_select_exactly_the_matching_tools() -> None:
    # A grant list builds its tool and nothing else: no grant means no tool.
    names = {tool["function"]["name"] for tool in build_tools(["/in"], [], [])}

    assert names == {"read_file"}


def test_no_grants_build_no_tools() -> None:
    assert build_tools([], [], []) == []


def test_ungranted_tool_call_is_refused_as_content(tmp_path: Path) -> None:
    # The engine can ask for any tool at all; one it was not granted must be
    # refused as readable content, and must not touch the filesystem.
    dispatch = make_dispatch([str(tmp_path)], [], [], 30)
    target = tmp_path / "x.txt"

    content, effect = dispatch("write_file", {"path": str(target), "content": "hi"})

    assert content.startswith("ERROR:")
    assert "not available" in content
    assert effect is None
    assert not target.exists()


def test_unknown_tool_name_is_refused_as_content(tmp_path: Path) -> None:
    dispatch = make_dispatch([str(tmp_path)], [str(tmp_path)], ["ls"], 30)

    content, effect = dispatch("delete_file", {"path": str(tmp_path)})

    assert content.startswith("ERROR:")
    assert effect is None


def test_missing_path_argument_is_refused_not_a_raise(tmp_path: Path) -> None:
    # A call with no arguments resolves the empty path; it must be refused by
    # the fence rather than read from the current directory.
    dispatch = make_dispatch([str(tmp_path)], [], [], 30)

    content, effect = dispatch("read_file", {})

    assert content.startswith("ERROR:")
    assert effect is None


def test_read_outside_the_fence_is_reported_to_the_worker(tmp_path: Path) -> None:
    box = tmp_path / "box"
    box.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("s", encoding="utf-8")
    dispatch = make_dispatch([str(box)], [], [], 30)

    content, effect = dispatch("read_file", {"path": str(outside / "secret.txt")})

    assert content.startswith("ERROR:")
    assert effect is None


def test_undecodable_file_is_reported_not_raised(tmp_path: Path) -> None:
    # A binary file inside the fence is data the worker should be told about:
    # an exception here would end the delegation mid-task.
    binary = tmp_path / "raw.bin"
    binary.write_bytes(b"\xff\xfe\x00binary")
    dispatch = make_dispatch([str(tmp_path)], [], [], 30)

    content, effect = dispatch("read_file", {"path": str(binary)})

    assert content.startswith("ERROR:")
    assert effect is None


def test_write_over_a_directory_is_reported(tmp_path: Path) -> None:
    target = tmp_path / "dir"
    target.mkdir()
    dispatch = make_dispatch([], [str(tmp_path)], [], 30)

    content, effect = dispatch("write_file", {"path": str(target), "content": "x"})

    assert content.startswith("ERROR:")
    assert effect is None


def test_successful_write_reports_its_path(tmp_path: Path) -> None:
    target = tmp_path / "out.txt"
    dispatch = make_dispatch([], [str(tmp_path)], [], 30)

    content, effect = dispatch("write_file", {"path": str(target), "content": "hi"})

    assert content == "written"
    assert isinstance(effect, ToolEffect)
    assert effect.written_path == str(target.resolve())
    assert target.read_text(encoding="utf-8") == "hi"


def test_command_without_a_granted_menu_is_refused(tmp_path: Path) -> None:
    dispatch = make_dispatch([], [str(tmp_path)], [], 30)

    content, effect = dispatch("run_command", {"command": "echo hi"})

    assert content.startswith("ERROR:")
    assert effect is None


def test_unlisted_command_is_refused_before_it_runs(tmp_path: Path) -> None:
    dispatch = make_dispatch([], [str(tmp_path)], ["echo hi"], 30)

    content, effect = dispatch("run_command", {"command": "echo hi; rm -rf /"})

    assert content.startswith("ERROR:")
    assert "not in allowed list" in content
    assert effect is None


@pytest.mark.parametrize("timeout_s", [True, False])
def test_boolean_timeout_is_not_a_duration(tmp_path: Path, timeout_s: bool) -> None:
    # A bool is not a duration: `timeout_s: true` must not be read as one
    # second, which would kill a granted command that is still working. It is
    # dropped, so the caller's ceiling governs and the run finishes.
    dispatch = make_dispatch([], [str(tmp_path)], ["sleep 2"], 30)

    content, effect = dispatch("run_command", {"command": "sleep 2", "timeout_s": timeout_s})

    assert content.startswith("exit=0")
    assert effect is not None
    assert effect.command_run is not None
    assert effect.command_run.exit_code == 0


def test_non_integer_timeout_falls_back_to_the_ceiling(tmp_path: Path) -> None:
    # The model can send anything: a string timeout is ignored rather than
    # passed to subprocess, and the caller's ceiling still applies.
    dispatch = make_dispatch([], [str(tmp_path)], ["sleep 5"], 1)

    content, effect = dispatch("run_command", {"command": "sleep 5", "timeout_s": "100"})

    assert content.startswith("ERROR:")
    assert "timed out after 1s" in content
