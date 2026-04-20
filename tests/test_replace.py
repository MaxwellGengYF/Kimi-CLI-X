"""Comprehensive unit tests for kimi_cli.tools.file.replace."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "kimi-cli" / "src"))

from kaos.path import KaosPath

from kimi_cli.soul.approval import ApprovalResult
from kimi_cli.tools.file.replace import (
    Edit,
    Params,
    StrReplaceFile,
)
from kosong.tooling import ToolError, ToolReturnValue


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_runtime(work_dir: KaosPath) -> Any:
    """Create a minimal fake Runtime with only the fields StrReplaceFile needs."""
    runtime = MagicMock()
    builtin_args = MagicMock()
    builtin_args.KIMI_WORK_DIR = work_dir
    runtime.builtin_args = builtin_args
    runtime.additional_dirs = []
    return runtime


def _make_approval(approved: bool = True, feedback: str = "") -> Any:
    """Create a mock Approval that always returns the given result."""
    approval = MagicMock()
    approval.request = AsyncMock(
        return_value=ApprovalResult(approved=approved, feedback=feedback)
    )
    return approval


def _make_tool(
    work_dir: KaosPath,
    *,
    approved: bool = True,
    feedback: str = "",
) -> StrReplaceFile:
    """Create a StrReplaceFile tool with a mocked approval."""
    runtime = _make_runtime(work_dir)
    approval = _make_approval(approved=approved, feedback=feedback)
    return StrReplaceFile(runtime, approval)


# ---------------------------------------------------------------------------
# Edit / Params model
# ---------------------------------------------------------------------------


def test_edit_defaults() -> None:
    e = Edit(old="foo", new="bar")
    assert e.old == "foo"
    assert e.new == "bar"
    assert e.replace_all is False


def test_edit_replace_all() -> None:
    e = Edit(old="foo", new="bar", replace_all=True)
    assert e.replace_all is True


def test_params_defaults() -> None:
    p = Params(path="foo.txt", edit=Edit(old="a", new="b"))
    assert p.path == "foo.txt"
    assert isinstance(p.edit, Edit)
    assert p.fix_foramt is True


def test_params_with_edit_list() -> None:
    edits = [Edit(old="a", new="b"), Edit(old="c", new="d")]
    p = Params(path="foo.txt", edit=edits)
    assert isinstance(p.edit, list)
    assert len(p.edit) == 2


# ---------------------------------------------------------------------------
# Empty path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_path(tmp_path: Path) -> None:
    work_dir = KaosPath(str(tmp_path))
    tool = _make_tool(work_dir)
    result = await tool(Params(path="", edit=Edit(old="a", new="b")))
    assert isinstance(result, ToolError)
    assert result.is_error
    assert "Empty file path" in result.brief


# ---------------------------------------------------------------------------
# Path validation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_relative_path_outside_workspace(tmp_path: Path) -> None:
    work_dir = KaosPath(str(tmp_path / "work"))
    await work_dir.mkdir(parents=True, exist_ok=True)
    tool = _make_tool(work_dir)

    result = await tool(Params(path="../outside.txt", edit=Edit(old="a", new="b")))
    assert isinstance(result, ToolError)
    assert result.is_error
    assert "Invalid path" in result.brief
    assert "absolute path" in result.message


@pytest.mark.asyncio
async def test_absolute_path_outside_workspace_allowed(tmp_path: Path) -> None:
    work_dir = KaosPath(str(tmp_path / "work"))
    await work_dir.mkdir(parents=True, exist_ok=True)
    outside = tmp_path / "outside.txt"
    outside.write_text("hello world", encoding="utf-8")

    tool = _make_tool(work_dir)
    result = await tool(Params(path=str(outside), edit=Edit(old="world", new="universe")))
    assert isinstance(result, ToolReturnValue)
    assert not result.is_error
    assert outside.read_text(encoding="utf-8") == "hello universe"


# ---------------------------------------------------------------------------
# File not found / not a file
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_file_not_found(tmp_path: Path) -> None:
    work_dir = KaosPath(str(tmp_path))
    tool = _make_tool(work_dir)

    result = await tool(Params(path=str(tmp_path / "nonexistent.txt"), edit=Edit(old="a", new="b")))
    assert isinstance(result, ToolError)
    assert result.is_error
    assert "File not found" in result.brief


@pytest.mark.asyncio
async def test_path_is_directory(tmp_path: Path) -> None:
    work_dir = KaosPath(str(tmp_path))
    subdir = tmp_path / "subdir"
    subdir.mkdir()

    tool = _make_tool(work_dir)
    result = await tool(Params(path=str(subdir), edit=Edit(old="a", new="b")))
    assert isinstance(result, ToolError)
    assert result.is_error
    assert "Invalid path" in result.brief


# ---------------------------------------------------------------------------
# No replacements made
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_replacements_made(tmp_path: Path) -> None:
    work_dir = KaosPath(str(tmp_path))
    f = tmp_path / "file.txt"
    f.write_text("hello world", encoding="utf-8")

    tool = _make_tool(work_dir)
    result = await tool(Params(path=str(f), edit=Edit(old="notfound", new="replaced")))
    assert isinstance(result, ToolError)
    assert result.is_error
    assert "No replacements made" in result.brief


# ---------------------------------------------------------------------------
# Single edit success
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_single_edit_success(tmp_path: Path) -> None:
    work_dir = KaosPath(str(tmp_path))
    f = tmp_path / "file.txt"
    f.write_text("hello world", encoding="utf-8")

    tool = _make_tool(work_dir)
    result = await tool(Params(path=str(f), edit=Edit(old="world", new="universe")))
    assert isinstance(result, ToolReturnValue)
    assert not result.is_error
    assert "Applied 1 edit(s) with 1 total replacement(s)" in result.message
    assert f.read_text(encoding="utf-8") == "hello universe"


@pytest.mark.asyncio
async def test_single_edit_replace_all(tmp_path: Path) -> None:
    work_dir = KaosPath(str(tmp_path))
    f = tmp_path / "file.txt"
    f.write_text("foo bar foo baz foo", encoding="utf-8")

    tool = _make_tool(work_dir)
    result = await tool(
        Params(path=str(f), edit=Edit(old="foo", new="FOO", replace_all=True))
    )
    assert isinstance(result, ToolReturnValue)
    assert not result.is_error
    assert "Applied 1 edit(s) with 3 total replacement(s)" in result.message
    assert f.read_text(encoding="utf-8") == "FOO bar FOO baz FOO"


@pytest.mark.asyncio
async def test_single_edit_replace_first_only(tmp_path: Path) -> None:
    work_dir = KaosPath(str(tmp_path))
    f = tmp_path / "file.txt"
    f.write_text("foo bar foo baz", encoding="utf-8")

    tool = _make_tool(work_dir)
    result = await tool(
        Params(path=str(f), edit=Edit(old="foo", new="FOO", replace_all=False))
    )
    assert isinstance(result, ToolReturnValue)
    assert not result.is_error
    assert "Applied 1 edit(s) with 1 total replacement(s)" in result.message
    assert f.read_text(encoding="utf-8") == "FOO bar foo baz"


# ---------------------------------------------------------------------------
# Multiple edits
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_multiple_edits_success(tmp_path: Path) -> None:
    work_dir = KaosPath(str(tmp_path))
    f = tmp_path / "file.txt"
    f.write_text("hello world foo bar", encoding="utf-8")

    edits = [
        Edit(old="world", new="universe"),
        Edit(old="foo", new="baz"),
    ]
    tool = _make_tool(work_dir)
    result = await tool(Params(path=str(f), edit=edits))
    assert isinstance(result, ToolReturnValue)
    assert not result.is_error
    assert "Applied 2 edit(s) with 2 total replacement(s)" in result.message
    assert f.read_text(encoding="utf-8") == "hello universe baz bar"


@pytest.mark.asyncio
async def test_multiple_edits_with_replace_all(tmp_path: Path) -> None:
    work_dir = KaosPath(str(tmp_path))
    f = tmp_path / "file.txt"
    f.write_text("foo bar foo baz foo", encoding="utf-8")

    edits = [
        Edit(old="foo", new="FOO", replace_all=True),
        Edit(old="baz", new="BAZ"),
    ]
    tool = _make_tool(work_dir)
    result = await tool(Params(path=str(f), edit=edits))
    assert isinstance(result, ToolReturnValue)
    assert not result.is_error
    # 3 replacements for first edit + 1 for second = 4
    assert "Applied 2 edit(s) with 4 total replacement(s)" in result.message
    assert f.read_text(encoding="utf-8") == "FOO bar FOO BAZ FOO"


# ---------------------------------------------------------------------------
# Approval behaviour
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_workspace_edit_requests_approval(tmp_path: Path) -> None:
    work_dir = KaosPath(str(tmp_path))
    f = tmp_path / "file.txt"
    f.write_text("hello world", encoding="utf-8")

    approval = _make_approval(approved=True)
    runtime = _make_runtime(work_dir)
    tool = StrReplaceFile(runtime, approval)

    result = await tool(Params(path=str(f), edit=Edit(old="world", new="universe")))
    assert isinstance(result, ToolReturnValue)
    assert not result.is_error
    approval.request.assert_awaited_once()
    call_args = approval.request.call_args
    assert call_args is not None
    assert call_args.args[1] == "edit file"


@pytest.mark.asyncio
async def test_outside_workspace_edit_requests_edit_outside(tmp_path: Path) -> None:
    work_dir = KaosPath(str(tmp_path / "work"))
    await work_dir.mkdir(parents=True, exist_ok=True)
    outside = tmp_path / "outside.txt"
    outside.write_text("hello world", encoding="utf-8")

    approval = _make_approval(approved=True)
    runtime = _make_runtime(work_dir)
    tool = StrReplaceFile(runtime, approval)

    result = await tool(Params(path=str(outside), edit=Edit(old="world", new="universe")))
    assert isinstance(result, ToolReturnValue)
    assert not result.is_error
    approval.request.assert_awaited_once()
    call_args = approval.request.call_args
    assert call_args is not None
    assert call_args.args[1] == "edit file outside working directory"


@pytest.mark.asyncio
async def test_edit_rejected(tmp_path: Path) -> None:
    work_dir = KaosPath(str(tmp_path))
    f = tmp_path / "file.txt"
    f.write_text("hello world", encoding="utf-8")

    approval = _make_approval(approved=False, feedback="don't touch this")
    runtime = _make_runtime(work_dir)
    tool = StrReplaceFile(runtime, approval)

    result = await tool(Params(path=str(f), edit=Edit(old="world", new="universe")))
    assert isinstance(result, ToolError)
    assert result.is_error
    assert "Rejected" in result.brief
    # File should remain unchanged
    assert f.read_text(encoding="utf-8") == "hello world"


# ---------------------------------------------------------------------------
# Plan mode
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_plan_mode_no_plan_file(tmp_path: Path) -> None:
    work_dir = KaosPath(str(tmp_path))
    f = tmp_path / "file.txt"
    f.write_text("hello world", encoding="utf-8")

    tool = _make_tool(work_dir)
    tool.bind_plan_mode(checker=lambda: True, path_getter=lambda: None)

    result = await tool(Params(path=str(f), edit=Edit(old="world", new="universe")))
    assert isinstance(result, ToolError)
    assert result.is_error
    assert "Plan file unavailable" in result.brief


@pytest.mark.asyncio
async def test_plan_mode_wrong_file(tmp_path: Path) -> None:
    work_dir = KaosPath(str(tmp_path))
    plan_file = tmp_path / "plan.md"
    plan_file.write_text("plan content", encoding="utf-8")
    other_file = tmp_path / "other.txt"
    other_file.write_text("hello world", encoding="utf-8")

    tool = _make_tool(work_dir)
    tool.bind_plan_mode(
        checker=lambda: True,
        path_getter=lambda: plan_file,
    )

    result = await tool(Params(path=str(other_file), edit=Edit(old="world", new="universe")))
    assert isinstance(result, ToolError)
    assert result.is_error
    assert "Plan mode restriction" in result.brief


@pytest.mark.asyncio
async def test_plan_mode_edit_plan_file_not_created(tmp_path: Path) -> None:
    work_dir = KaosPath(str(tmp_path))
    plan_file = tmp_path / "plan.md"
    # Do NOT create the plan file

    tool = _make_tool(work_dir)
    tool.bind_plan_mode(
        checker=lambda: True,
        path_getter=lambda: plan_file,
    )

    result = await tool(Params(path=str(plan_file), edit=Edit(old="plan", new="PLAN")))
    assert isinstance(result, ToolError)
    assert result.is_error
    assert "Plan file not created" in result.brief


@pytest.mark.asyncio
async def test_plan_mode_edit_plan_file_auto_approved(tmp_path: Path) -> None:
    work_dir = KaosPath(str(tmp_path))
    plan_file = tmp_path / "plan.md"
    plan_file.write_text("hello plan", encoding="utf-8")

    approval = _make_approval(approved=True)
    runtime = _make_runtime(work_dir)
    tool = StrReplaceFile(runtime, approval)
    tool.bind_plan_mode(
        checker=lambda: True,
        path_getter=lambda: plan_file,
    )

    result = await tool(Params(path=str(plan_file), edit=Edit(old="plan", new="PLAN")))
    assert isinstance(result, ToolReturnValue)
    assert not result.is_error
    # Plan file edits are auto-approved; approval.request should NOT be called
    approval.request.assert_not_called()
    assert plan_file.read_text(encoding="utf-8") == "hello PLAN"


@pytest.mark.asyncio
async def test_not_plan_mode_ignores_plan_bindings(tmp_path: Path) -> None:
    work_dir = KaosPath(str(tmp_path))
    f = tmp_path / "file.txt"
    f.write_text("hello world", encoding="utf-8")

    tool = _make_tool(work_dir)
    tool.bind_plan_mode(checker=lambda: False, path_getter=lambda: Path("/fake/plan.md"))

    result = await tool(Params(path=str(f), edit=Edit(old="world", new="universe")))
    assert isinstance(result, ToolReturnValue)
    assert not result.is_error
    assert f.read_text(encoding="utf-8") == "hello universe"


# ---------------------------------------------------------------------------
# JSON format validation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_json_valid_no_error(tmp_path: Path) -> None:
    work_dir = KaosPath(str(tmp_path))
    f = tmp_path / "data.json"
    f.write_text('{"key": "value"}', encoding="utf-8")

    tool = _make_tool(work_dir)
    result = await tool(Params(path=str(f), edit=Edit(old="value", new="new_value")))
    assert isinstance(result, ToolReturnValue)
    assert not result.is_error


@pytest.mark.asyncio
async def test_json_invalid_fix_foramt_true(tmp_path: Path) -> None:
    work_dir = KaosPath(str(tmp_path))
    f = tmp_path / "data.json"
    # trailing comma is invalid JSON but demjson3 can parse it
    f.write_text('{"key": "value",}', encoding="utf-8")

    tool = _make_tool(work_dir)
    result = await tool(Params(path=str(f), edit=Edit(old="value", new="new_value")))
    assert isinstance(result, ToolReturnValue)
    assert not result.is_error
    # demjson3 should have fixed the JSON
    parsed = json.loads(f.read_text(encoding="utf-8"))
    assert parsed == {"key": "new_value"}


@pytest.mark.asyncio
async def test_json_invalid_fix_foramt_false(tmp_path: Path) -> None:
    work_dir = KaosPath(str(tmp_path))
    f = tmp_path / "data.json"
    # Write invalid JSON that cannot be fixed by simple json.dumps
    f.write_text('{"key": "value",}', encoding="utf-8")

    tool = _make_tool(work_dir)
    result = await tool(
        Params(path=str(f), edit=Edit(old="value", new="new_value"), fix_foramt=False)
    )
    assert isinstance(result, ToolError)
    assert result.is_error
    assert "Format validation failed" in result.brief


@pytest.mark.asyncio
async def test_json_invalid_demjson3_fails(tmp_path: Path) -> None:
    work_dir = KaosPath(str(tmp_path))
    f = tmp_path / "data.json"
    # Completely unparseable JSON
    f.write_text("this is not json at all", encoding="utf-8")

    tool = _make_tool(work_dir)
    result = await tool(Params(path=str(f), edit=Edit(old="not", new="still_not")))
    assert isinstance(result, ToolError)
    assert result.is_error
    assert "Format validation failed" in result.brief
    assert "JSON decode error" in result.message


# ---------------------------------------------------------------------------
# XML format validation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_xml_valid_no_error(tmp_path: Path) -> None:
    work_dir = KaosPath(str(tmp_path))
    f = tmp_path / "data.xml"
    f.write_text("<root><item>old</item></root>", encoding="utf-8")

    tool = _make_tool(work_dir)
    result = await tool(Params(path=str(f), edit=Edit(old="old", new="new")))
    assert isinstance(result, ToolReturnValue)
    assert not result.is_error


@pytest.mark.asyncio
async def test_xml_invalid_returns_error(tmp_path: Path) -> None:
    work_dir = KaosPath(str(tmp_path))
    f = tmp_path / "data.xml"
    f.write_text("<root><item>old</item>", encoding="utf-8")

    tool = _make_tool(work_dir)
    result = await tool(Params(path=str(f), edit=Edit(old="old", new="new")))
    assert isinstance(result, ToolError)
    assert result.is_error
    assert "Format validation failed" in result.brief
    assert "XML parse error" in result.message


# ---------------------------------------------------------------------------
# Exception handling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_exception_during_read(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    work_dir = KaosPath(str(tmp_path))
    f = tmp_path / "file.txt"
    f.write_text("hello world", encoding="utf-8")

    async def _broken_read_text(self: KaosPath, **kwargs: Any) -> str:
        raise RuntimeError("disk fail")

    monkeypatch.setattr(
        "kimi_cli.tools.file.replace.KaosPath.read_text",
        _broken_read_text,
    )

    tool = _make_tool(work_dir)
    result = await tool(Params(path=str(f), edit=Edit(old="world", new="universe")))
    assert isinstance(result, ToolError)
    assert result.is_error
    assert "Failed to edit file" in result.brief
    assert "disk fail" in result.message


# ---------------------------------------------------------------------------
# bind_plan_mode
# ---------------------------------------------------------------------------


def test_bind_plan_mode_sets_attributes(tmp_path: Path) -> None:
    work_dir = KaosPath(str(tmp_path))
    tool = _make_tool(work_dir)

    checker = lambda: True
    getter = lambda: Path("/plan.md")

    tool.bind_plan_mode(checker, getter)
    assert tool._plan_mode_checker is checker
    assert tool._plan_file_path_getter is getter


# ---------------------------------------------------------------------------
# Class attributes
# ---------------------------------------------------------------------------


def test_replace_class_attributes() -> None:
    runtime = MagicMock()
    runtime.builtin_args.KIMI_WORK_DIR = KaosPath("/tmp")
    runtime.additional_dirs = []
    approval = MagicMock()
    tool = StrReplaceFile(runtime, approval)
    assert StrReplaceFile.name == "StrReplaceFile"
    assert StrReplaceFile.params is Params
    assert "replace" in tool.description.lower()
