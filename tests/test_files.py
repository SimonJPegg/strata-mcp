"""Tests for the path fence: only paths within allowed dirs are accepted."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from strata_mcp.errors import PathNotAllowedError
from strata_mcp.files import read_file_op, resolve_within, write_file_op


def test_file_inside_allowed_dir(tmp_path: Path) -> None:
    (tmp_path / "f.txt").write_text("x")

    result = resolve_within(str(tmp_path / "f.txt"), [str(tmp_path)])

    assert result == (tmp_path / "f.txt").resolve()


def test_allowed_dir_root_itself(tmp_path: Path) -> None:
    assert resolve_within(str(tmp_path), [str(tmp_path)]) == tmp_path.resolve()


def test_nested_path_inside(tmp_path: Path) -> None:
    (tmp_path / "sub").mkdir()

    assert resolve_within(str(tmp_path / "sub"), [str(tmp_path)]) == (tmp_path / "sub").resolve()


def test_dotdot_escape_is_refused(tmp_path: Path) -> None:
    box = tmp_path / "box"
    box.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()

    with pytest.raises(PathNotAllowedError):
        resolve_within(str(box / ".." / "outside" / "secret.txt"), [str(box)])


def test_absolute_path_outside_is_refused(tmp_path: Path) -> None:
    box = tmp_path / "box"
    box.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()

    with pytest.raises(PathNotAllowedError):
        resolve_within(str(outside / "secret.txt"), [str(box)])


def test_empty_allowlist_refuses_everything(tmp_path: Path) -> None:
    (tmp_path / "f.txt").write_text("x")

    with pytest.raises(PathNotAllowedError):
        resolve_within(str(tmp_path / "f.txt"), [])


def test_symlink_escape_is_refused(tmp_path: Path) -> None:
    box = tmp_path / "box"
    box.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("s")
    # A symlink inside the box pointing out of it must not grant access.
    os.symlink(outside, box / "escape")

    with pytest.raises(PathNotAllowedError):
        resolve_within(str(box / "escape" / "secret.txt"), [str(box)])


def test_sibling_prefix_is_not_inside(tmp_path: Path) -> None:
    box = tmp_path / "box"
    box.mkdir()
    sibling = tmp_path / "box2"
    sibling.mkdir()
    (sibling / "f.txt").write_text("y")

    # /box2 shares a string prefix with /box but is not within it.
    with pytest.raises(PathNotAllowedError):
        resolve_within(str(sibling / "f.txt"), [str(box)])


def test_read_file_op_reads_inside_fence(tmp_path: Path) -> None:
    (tmp_path / "f.txt").write_text("hello", encoding="utf-8")

    outcome = read_file_op(str(tmp_path / "f.txt"), [str(tmp_path)])

    assert outcome.ok is True
    assert outcome.content == "hello"
    assert outcome.error is None


def test_read_file_op_refused_outside_fence(tmp_path: Path) -> None:
    box = tmp_path / "box"
    box.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("s", encoding="utf-8")

    outcome = read_file_op(str(outside / "secret.txt"), [str(box)])

    assert outcome.ok is False
    assert outcome.error is not None
    assert outcome.content == ""


def test_write_file_op_writes_inside_fence(tmp_path: Path) -> None:
    target = tmp_path / "out.txt"

    outcome = write_file_op(str(target), "written", [str(tmp_path)])

    assert outcome.ok is True
    assert target.read_text(encoding="utf-8") == "written"


def test_write_file_op_refused_outside_fence(tmp_path: Path) -> None:
    box = tmp_path / "box"
    box.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()

    outcome = write_file_op(str(outside / "x.txt"), "nope", [str(box)])

    assert outcome.ok is False
    assert outcome.error is not None
    assert not (outside / "x.txt").exists()


def test_write_file_op_creates_nested_parents_inside_fence(tmp_path: Path) -> None:
    target = tmp_path / "a" / "b" / "c" / "deep.txt"

    outcome = write_file_op(str(target), "deep", [str(tmp_path)])

    assert outcome.ok is True
    assert target.read_text(encoding="utf-8") == "deep"
    assert outcome.written_path == str(target.resolve())


def test_write_file_op_records_written_path(tmp_path: Path) -> None:
    target = tmp_path / "out.txt"

    outcome = write_file_op(str(target), "x", [str(tmp_path)])

    assert outcome.written_path == str(target.resolve())


def test_read_file_op_missing_file_is_a_refusal(tmp_path: Path) -> None:
    outcome = read_file_op(str(tmp_path / "nope.txt"), [str(tmp_path)])

    assert outcome.ok is False
    assert outcome.content == ""
    assert outcome.error is not None


def test_read_file_op_directory_target_is_a_refusal(tmp_path: Path) -> None:
    # A directory passes the fence, so the read itself must fail as data.
    outcome = read_file_op(str(tmp_path), [str(tmp_path)])

    assert outcome.ok is False
    assert outcome.content == ""
    assert outcome.error is not None


@pytest.mark.parametrize(
    ("name", "raw"),
    [
        ("latin1.bin", b"\xff\xfe\x00not utf-8"),
        ("utf16.txt", "encoded".encode("utf-16")),
        ("lone_lead_byte.bin", b"\xe2\x28\xa1"),  # invalid UTF-8 sequence
    ],
)
def test_read_file_op_undecodable_bytes_is_a_refusal(tmp_path: Path, name: str, raw: bytes) -> None:
    # UnicodeDecodeError subclasses ValueError, not OSError: had the read only
    # caught OSError, a binary file would raise out of the tool loop and abort
    # the delegation. Failures are data, so the worker must be told instead.
    (tmp_path / name).write_bytes(raw)

    outcome = read_file_op(str(tmp_path / name), [str(tmp_path)])

    assert outcome.ok is False
    assert outcome.content == ""
    assert outcome.error is not None


def test_read_file_op_without_grant_is_refused(tmp_path: Path) -> None:
    (tmp_path / "f.txt").write_text("x", encoding="utf-8")

    outcome = read_file_op(str(tmp_path / "f.txt"), [])

    assert outcome.ok is False
    assert outcome.content == ""
    assert outcome.error is not None


def test_write_file_op_without_grant_is_refused(tmp_path: Path) -> None:
    target = tmp_path / "f.txt"

    outcome = write_file_op(str(target), "x", [])

    assert outcome.ok is False
    assert outcome.written_path is None
    assert not target.exists()


def test_write_file_op_over_existing_directory_is_a_refusal(tmp_path: Path) -> None:
    target = tmp_path / "dir"
    target.mkdir()

    outcome = write_file_op(str(target), "x", [str(tmp_path)])

    assert outcome.ok is False
    assert outcome.written_path is None


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores directory permissions")
def test_write_file_op_unwritable_path_is_a_refusal(tmp_path: Path) -> None:
    locked = tmp_path / "locked"
    locked.mkdir()
    locked.chmod(0o555)

    outcome = write_file_op(str(locked / "x.txt"), "x", [str(tmp_path)])

    assert outcome.ok is False
    assert outcome.written_path is None
    assert not (locked / "x.txt").exists()
