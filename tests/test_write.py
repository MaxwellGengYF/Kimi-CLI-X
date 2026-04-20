"""Comprehensive unit tests for kimi_cli.tools.file.write."""

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
from kimi_cli.tools.file.write import (
    Params,
    WriteFile,
)
from kosong.tooling import ToolError, ToolReturnValue


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_runtime(work_dir: KaosPath) -> Any:
    """Create a minimal fake Runtime with only the fields WriteFile needs."""
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
) -> WriteFile:
    """Create a WriteFile tool with a mocked approval."""
    runtime = _make_runtime(work_dir)
    approval = _make_approval(approved=approved, feedback=feedback)
    return WriteFile(runtime, approval)


# ---------------------------------------------------------------------------
# Params model
# ---------------------------------------------------------------------------


def test_params_defaults() -> None:
    p = Params(path="foo.txt", content="hello")
    assert p.path == "foo.txt"
    assert p.content == "hello"
    assert p.mode == "overwrite"
    assert p.fix_foramt is True


def test_params_custom() -> None:
    p = Params(path="foo.txt", content="hello", mode="append", fix_foramt=False)
    assert p.path == "foo.txt"
    assert p.content == "hello"
    assert p.mode == "append"
    assert p.fix_foramt is False


# ---------------------------------------------------------------------------
# Empty path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_path() -> None:
    tool = _make_tool(KaosPath("/tmp"))
    result = await tool(Params(path="", content="hello"))
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

    result = await tool(Params(path="../outside.txt", content="hello"))
    assert isinstance(result, ToolError)
    assert result.is_error
    assert "Invalid path" in result.brief
    assert "absolute path" in result.message


@pytest.mark.asyncio
async def test_absolute_path_outside_workspace_allowed(tmp_path: Path) -> None:
    work_dir = KaosPath(str(tmp_path / "work"))
    await work_dir.mkdir(parents=True, exist_ok=True)
    outside = tmp_path / "outside.txt"

    tool = _make_tool(work_dir)
    result = await tool(Params(path=str(outside), content="hello"))
    assert isinstance(result, ToolReturnValue)
    assert not result.is_error
    assert outside.read_text(encoding="utf-8") == "hello"


# ---------------------------------------------------------------------------
# Parent directory handling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_creates_parent_directories(tmp_path: Path) -> None:
    work_dir = KaosPath(str(tmp_path))
    nested = tmp_path / "a" / "b" / "c.txt"

    tool = _make_tool(work_dir)
    result = await tool(Params(path=str(nested), content="deep"))
    assert isinstance(result, ToolReturnValue)
    assert not result.is_error
    assert nested.read_text(encoding="utf-8") == "deep"


@pytest.mark.asyncio
async def test_parent_directory_creation_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    work_dir = KaosPath(str(tmp_path))
    target = tmp_path / "missing" / "file.txt"

    async def _broken_mkdir(self: KaosPath, **kwargs: Any) -> None:
        raise OSError("cannot create dir")

    monkeypatch.setattr(
        "kimi_cli.tools.file.write.KaosPath.mkdir",
        _broken_mkdir,
    )

    tool = _make_tool(work_dir)
    result = await tool(Params(path=str(target), content="hello"))
    assert isinstance(result, ToolError)
    assert result.is_error
    assert "Parent directory not found" in result.brief


# ---------------------------------------------------------------------------
# Invalid mode (enforced by Pydantic Literal)
# ---------------------------------------------------------------------------


def test_invalid_mode_rejected_by_pydantic() -> None:
    with pytest.raises(Exception):
        Params(path="foo.txt", content="hello", mode="invalid")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Overwrite mode
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_overwrite_new_file(tmp_path: Path) -> None:
    work_dir = KaosPath(str(tmp_path))
    f = tmp_path / "file.txt"

    tool = _make_tool(work_dir)
    result = await tool(Params(path=str(f), content="hello"))
    assert isinstance(result, ToolReturnValue)
    assert not result.is_error
    assert "overwritten" in result.message
    assert f.read_text(encoding="utf-8") == "hello"


@pytest.mark.asyncio
async def test_overwrite_existing_file(tmp_path: Path) -> None:
    work_dir = KaosPath(str(tmp_path))
    f = tmp_path / "file.txt"
    f.write_text("old content", encoding="utf-8")

    tool = _make_tool(work_dir)
    result = await tool(Params(path=str(f), content="new content"))
    assert isinstance(result, ToolReturnValue)
    assert not result.is_error
    assert "overwritten" in result.message
    assert f.read_text(encoding="utf-8") == "new content"


# ---------------------------------------------------------------------------
# Append mode
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_append_to_new_file(tmp_path: Path) -> None:
    work_dir = KaosPath(str(tmp_path))
    f = tmp_path / "file.txt"

    tool = _make_tool(work_dir)
    result = await tool(Params(path=str(f), content="hello", mode="append"))
    assert isinstance(result, ToolReturnValue)
    assert not result.is_error
    assert "appended to" in result.message
    assert f.read_text(encoding="utf-8") == "hello"


@pytest.mark.asyncio
async def test_append_to_existing_file(tmp_path: Path) -> None:
    work_dir = KaosPath(str(tmp_path))
    f = tmp_path / "file.txt"
    f.write_text("hello ", encoding="utf-8")

    tool = _make_tool(work_dir)
    result = await tool(Params(path=str(f), content="world", mode="append"))
    assert isinstance(result, ToolReturnValue)
    assert not result.is_error
    assert "appended to" in result.message
    assert f.read_text(encoding="utf-8") == "hello world"


# ---------------------------------------------------------------------------
# Approval behaviour
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_workspace_write_requests_approval(tmp_path: Path) -> None:
    work_dir = KaosPath(str(tmp_path))
    f = tmp_path / "file.txt"

    approval = _make_approval(approved=True)
    runtime = _make_runtime(work_dir)
    tool = WriteFile(runtime, approval)

    result = await tool(Params(path=str(f), content="hello"))
    assert isinstance(result, ToolReturnValue)
    assert not result.is_error
    approval.request.assert_awaited_once()
    call_args = approval.request.call_args
    assert call_args is not None
    assert call_args.args[1] == "edit file"


@pytest.mark.asyncio
async def test_outside_workspace_write_requests_edit_outside(tmp_path: Path) -> None:
    work_dir = KaosPath(str(tmp_path / "work"))
    await work_dir.mkdir(parents=True, exist_ok=True)
    outside = tmp_path / "outside.txt"

    approval = _make_approval(approved=True)
    runtime = _make_runtime(work_dir)
    tool = WriteFile(runtime, approval)

    result = await tool(Params(path=str(outside), content="hello"))
    assert isinstance(result, ToolReturnValue)
    assert not result.is_error
    approval.request.assert_awaited_once()
    call_args = approval.request.call_args
    assert call_args is not None
    assert call_args.args[1] == "edit file outside working directory"


@pytest.mark.asyncio
async def test_write_rejected(tmp_path: Path) -> None:
    work_dir = KaosPath(str(tmp_path))
    f = tmp_path / "file.txt"

    approval = _make_approval(approved=False, feedback="don't write")
    runtime = _make_runtime(work_dir)
    tool = WriteFile(runtime, approval)

    result = await tool(Params(path=str(f), content="hello"))
    assert isinstance(result, ToolError)
    assert result.is_error
    assert "Rejected" in result.brief
    assert not f.exists()


# ---------------------------------------------------------------------------
# Plan mode
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_plan_mode_no_plan_file(tmp_path: Path) -> None:
    work_dir = KaosPath(str(tmp_path))
    f = tmp_path / "file.txt"

    tool = _make_tool(work_dir)
    tool.bind_plan_mode(checker=lambda: True, path_getter=lambda: None)

    result = await tool(Params(path=str(f), content="hello"))
    assert isinstance(result, ToolError)
    assert result.is_error
    assert "Plan file unavailable" in result.brief


@pytest.mark.asyncio
async def test_plan_mode_wrong_file(tmp_path: Path) -> None:
    work_dir = KaosPath(str(tmp_path))
    plan_file = tmp_path / "plan.md"
    plan_file.write_text("plan content", encoding="utf-8")
    other_file = tmp_path / "other.txt"

    tool = _make_tool(work_dir)
    tool.bind_plan_mode(
        checker=lambda: True,
        path_getter=lambda: plan_file,
    )

    result = await tool(Params(path=str(other_file), content="hello"))
    assert isinstance(result, ToolError)
    assert result.is_error
    assert "Plan mode restriction" in result.brief


@pytest.mark.asyncio
async def test_plan_mode_write_plan_file_auto_approved(tmp_path: Path) -> None:
    work_dir = KaosPath(str(tmp_path))
    plan_file = tmp_path / "plan.md"
    plan_file.write_text("old plan", encoding="utf-8")

    approval = _make_approval(approved=True)
    runtime = _make_runtime(work_dir)
    tool = WriteFile(runtime, approval)
    tool.bind_plan_mode(
        checker=lambda: True,
        path_getter=lambda: plan_file,
    )

    result = await tool(Params(path=str(plan_file), content="new plan"))
    assert isinstance(result, ToolReturnValue)
    assert not result.is_error
    approval.request.assert_not_called()
    assert plan_file.read_text(encoding="utf-8") == "new plan"


@pytest.mark.asyncio
async def test_not_plan_mode_ignores_plan_bindings(tmp_path: Path) -> None:
    work_dir = KaosPath(str(tmp_path))
    f = tmp_path / "file.txt"

    tool = _make_tool(work_dir)
    tool.bind_plan_mode(checker=lambda: False, path_getter=lambda: Path("/fake/plan.md"))

    result = await tool(Params(path=str(f), content="hello"))
    assert isinstance(result, ToolReturnValue)
    assert not result.is_error
    assert f.read_text(encoding="utf-8") == "hello"


# ---------------------------------------------------------------------------
# JSON format validation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_json_valid_no_error(tmp_path: Path) -> None:
    work_dir = KaosPath(str(tmp_path))
    f = tmp_path / "data.json"

    tool = _make_tool(work_dir)
    result = await tool(Params(path=str(f), content='{"key": "value"}'))
    assert isinstance(result, ToolReturnValue)
    assert not result.is_error


@pytest.mark.asyncio
async def test_json_invalid_fix_foramt_true(tmp_path: Path) -> None:
    work_dir = KaosPath(str(tmp_path))
    f = tmp_path / "data.json"

    tool = _make_tool(work_dir)
    result = await tool(Params(path=str(f), content='{"key": "value",}'))
    assert isinstance(result, ToolReturnValue)
    assert not result.is_error
    parsed = json.loads(f.read_text(encoding="utf-8"))
    assert parsed == {"key": "value"}


@pytest.mark.asyncio
async def test_json_invalid_fix_foramt_false(tmp_path: Path) -> None:
    work_dir = KaosPath(str(tmp_path))
    f = tmp_path / "data.json"

    tool = _make_tool(work_dir)
    result = await tool(
        Params(path=str(f), content='{"key": "value",}', fix_foramt=False)
    )
    assert isinstance(result, ToolError)
    assert result.is_error
    assert "Format validation failed" in result.brief


@pytest.mark.asyncio
async def test_json_invalid_demjson3_fails(tmp_path: Path) -> None:
    work_dir = KaosPath(str(tmp_path))
    f = tmp_path / "data.json"

    tool = _make_tool(work_dir)
    result = await tool(Params(path=str(f), content="this is not json"))
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

    tool = _make_tool(work_dir)
    result = await tool(Params(path=str(f), content="<root><item>value</item></root>"))
    assert isinstance(result, ToolReturnValue)
    assert not result.is_error


@pytest.mark.asyncio
async def test_xml_invalid_returns_error(tmp_path: Path) -> None:
    work_dir = KaosPath(str(tmp_path))
    f = tmp_path / "data.xml"

    tool = _make_tool(work_dir)
    result = await tool(Params(path=str(f), content="<root><item>value</item>"))
    assert isinstance(result, ToolError)
    assert result.is_error
    assert "Format validation failed" in result.brief
    assert "XML parse error" in result.message


# ---------------------------------------------------------------------------
# Exception handling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_exception_during_write(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    work_dir = KaosPath(str(tmp_path))
    f = tmp_path / "file.txt"

    async def _broken_write_text(self: KaosPath, content: str, **kwargs: Any) -> None:
        raise RuntimeError("disk fail")

    monkeypatch.setattr(
        "kimi_cli.tools.file.write.KaosPath.write_text",
        _broken_write_text,
    )

    tool = _make_tool(work_dir)
    result = await tool(Params(path=str(f), content="hello"))
    assert isinstance(result, ToolError)
    assert result.is_error
    assert "Failed to write file" in result.brief
    assert "disk fail" in result.message


# ---------------------------------------------------------------------------
# bind_plan_mode
# ---------------------------------------------------------------------------


def test_bind_plan_mode_sets_attributes(tmp_path: Path) -> None:
    tool = _make_tool(KaosPath(str(tmp_path)))

    checker = lambda: True
    getter = lambda: Path("/plan.md")

    tool.bind_plan_mode(checker, getter)
    assert tool._plan_mode_checker is checker
    assert tool._plan_file_path_getter is getter


# ---------------------------------------------------------------------------
# Class attributes
# ---------------------------------------------------------------------------


def test_write_class_attributes() -> None:
    runtime = MagicMock()
    runtime.builtin_args.KIMI_WORK_DIR = KaosPath("/tmp")
    runtime.additional_dirs = []
    approval = MagicMock()
    tool = WriteFile(runtime, approval)
    assert WriteFile.name == "WriteFile"
    assert WriteFile.params is Params
    assert "Write to files" in tool.description
