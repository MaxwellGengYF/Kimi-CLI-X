"""Comprehensive unit tests for kimi_cli.tools.file.glob."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest

# Ensure kimi-cli src is importable when running pytest from repo root
sys.path.insert(0, str(Path(__file__).parent.parent / "kimi-cli" / "src"))

from kaos.path import KaosPath

from kimi_cli.tools.file.glob import Glob, MAX_MATCHES, Params
from kosong.tooling import ToolError, ToolOk


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_runtime(work_dir: KaosPath) -> Any:
    """Create a minimal fake Runtime with only the fields Glob needs."""
    runtime = MagicMock()
    builtin_args = MagicMock()
    builtin_args.KIMI_WORK_DIR = work_dir
    runtime.builtin_args = builtin_args
    runtime.additional_dirs = []
    runtime.skills_dirs = []
    return runtime


# ---------------------------------------------------------------------------
# Params model
# ---------------------------------------------------------------------------


def test_params_defaults() -> None:
    p = Params(pattern="*.py")
    assert p.pattern == "*.py"
    assert p.directory is None
    assert p.include_dirs is True


def test_params_custom() -> None:
    p = Params(pattern="*.txt", directory="/tmp", include_dirs=False)
    assert p.pattern == "*.txt"
    assert p.directory == "/tmp"
    assert p.include_dirs is False


# ---------------------------------------------------------------------------
# _validate_pattern
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_validate_pattern_starts_with_double_star(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    work_dir = KaosPath(str(tmp_path))
    runtime = _make_runtime(work_dir)
    tool = Glob(runtime)

    monkeypatch.setattr(
        "kimi_cli.tools.file.glob.list_directory",
        AsyncMock(return_value="mocked listing"),
    )

    result = await tool._validate_pattern("**/*.py")
    assert result is not None
    assert result.is_error
    assert "Unsafe pattern" in result.brief
    assert "starts with '**'" in result.message


@pytest.mark.asyncio
async def test_validate_pattern_ok(tmp_path: Path) -> None:
    work_dir = KaosPath(str(tmp_path))
    runtime = _make_runtime(work_dir)
    tool = Glob(runtime)

    result = await tool._validate_pattern("src/*.py")
    assert result is None


@pytest.mark.asyncio
async def test_validate_pattern_single_star_ok(tmp_path: Path) -> None:
    work_dir = KaosPath(str(tmp_path))
    runtime = _make_runtime(work_dir)
    tool = Glob(runtime)

    result = await tool._validate_pattern("*/*.py")
    assert result is None


# ---------------------------------------------------------------------------
# Basic success cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_glob_basic_files_and_dirs(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("a")
    (tmp_path / "b.py").write_text("b")
    (tmp_path / "c").mkdir()
    (tmp_path / "c" / "d.py").write_text("d")

    runtime = _make_runtime(KaosPath(str(tmp_path)))
    tool = Glob(runtime)

    result = await tool(Params(pattern="*.py"))
    assert isinstance(result, ToolOk)
    assert not result.is_error
    assert isinstance(result.output, str)
    lines = result.output.split("\n")
    assert "a.py" in lines
    assert "b.py" in lines
    assert "c/d.py" not in lines  # non-recursive


@pytest.mark.asyncio
async def test_glob_includes_dirs_by_default(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "README.md").write_text("readme")

    runtime = _make_runtime(KaosPath(str(tmp_path)))
    tool = Glob(runtime)

    result = await tool(Params(pattern="*"))
    assert isinstance(result, ToolOk)
    assert isinstance(result.output, str)
    lines = result.output.split("\n")
    assert "README.md" in lines
    assert "src" in lines


@pytest.mark.asyncio
async def test_glob_exclude_dirs(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "README.md").write_text("readme")

    runtime = _make_runtime(KaosPath(str(tmp_path)))
    tool = Glob(runtime)

    result = await tool(Params(pattern="*", include_dirs=False))
    assert isinstance(result, ToolOk)
    assert isinstance(result.output, str)
    lines = result.output.split("\n")
    assert "README.md" in lines
    assert "src" not in lines


@pytest.mark.asyncio
async def test_glob_no_matches(tmp_path: Path) -> None:
    runtime = _make_runtime(KaosPath(str(tmp_path)))
    tool = Glob(runtime)

    result = await tool(Params(pattern="*.nonexistent"))
    assert isinstance(result, ToolOk)
    assert result.output == ""
    assert "No matches found" in result.message


@pytest.mark.asyncio
async def test_glob_results_sorted(tmp_path: Path) -> None:
    (tmp_path / "z.py").write_text("z")
    (tmp_path / "a.py").write_text("a")
    (tmp_path / "m.py").write_text("m")

    runtime = _make_runtime(KaosPath(str(tmp_path)))
    tool = Glob(runtime)

    result = await tool(Params(pattern="*.py"))
    assert isinstance(result, ToolOk)
    assert isinstance(result.output, str)
    lines = result.output.split("\n")
    assert lines == ["a.py", "m.py", "z.py"]


@pytest.mark.asyncio
async def test_glob_relative_to_search_dir(tmp_path: Path) -> None:
    subdir = tmp_path / "sub"
    subdir.mkdir()
    (subdir / "file.py").write_text("file")

    runtime = _make_runtime(KaosPath(str(tmp_path)))
    tool = Glob(runtime)

    result = await tool(Params(pattern="*.py", directory=str(subdir)))
    assert isinstance(result, ToolOk)
    assert isinstance(result.output, str)
    assert result.output == "file.py"


@pytest.mark.asyncio
async def test_glob_recursive_pattern(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("a")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "b.py").write_text("b")
    (tmp_path / "src" / "nested").mkdir()
    (tmp_path / "src" / "nested" / "c.py").write_text("c")

    runtime = _make_runtime(KaosPath(str(tmp_path)))
    tool = Glob(runtime)

    result = await tool(Params(pattern="src/**/*.py"))
    assert isinstance(result, ToolOk)
    assert isinstance(result.output, str)
    lines = result.output.split("\n")
    # Use os.path.join for platform-aware path separators
    import os
    assert os.path.join("src", "b.py") in lines
    assert os.path.join("src", "nested", "c.py") in lines
    assert "a.py" not in lines


@pytest.mark.asyncio
async def test_glob_uses_work_dir_when_no_directory_given(tmp_path: Path) -> None:
    (tmp_path / "work.py").write_text("work")

    runtime = _make_runtime(KaosPath(str(tmp_path)))
    tool = Glob(runtime)

    result = await tool(Params(pattern="*.py"))
    assert isinstance(result, ToolOk)
    assert isinstance(result.output, str)
    assert "work.py" in result.output


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_glob_double_star_pattern_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runtime = _make_runtime(KaosPath(str(tmp_path)))
    tool = Glob(runtime)

    monkeypatch.setattr(
        "kimi_cli.tools.file.glob.list_directory",
        AsyncMock(return_value="mocked listing"),
    )

    result = await tool(Params(pattern="**/*.py"))
    assert isinstance(result, ToolError)
    assert result.is_error
    assert "Unsafe pattern" in result.brief


@pytest.mark.asyncio
async def test_glob_nonexistent_directory(tmp_path: Path) -> None:
    runtime = _make_runtime(KaosPath(str(tmp_path)))
    tool = Glob(runtime)

    result = await tool(Params(pattern="*.py", directory=str(tmp_path / "nope")))
    assert isinstance(result, ToolError)
    assert result.is_error
    assert "Directory not found" in result.brief


@pytest.mark.asyncio
async def test_glob_directory_is_a_file(tmp_path: Path) -> None:
    fake_dir = tmp_path / "notadir"
    fake_dir.write_text("i am a file")

    runtime = _make_runtime(KaosPath(str(tmp_path)))
    tool = Glob(runtime)

    result = await tool(Params(pattern="*.py", directory=str(fake_dir)))
    assert isinstance(result, ToolError)
    assert result.is_error
    assert "Invalid directory" in result.brief


@pytest.mark.asyncio
async def test_glob_exception_handling(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runtime = _make_runtime(KaosPath(str(tmp_path)))
    tool = Glob(runtime)

    async def _broken_glob(self: KaosPath, pattern: str) -> AsyncGenerator[KaosPath, None]:
        raise RuntimeError("boom")
        yield KaosPath("")  # type: ignore[unreachable]

    monkeypatch.setattr(
        "kimi_cli.tools.file.glob.KaosPath.glob",
        _broken_glob,
    )

    result = await tool(Params(pattern="*.py"))
    assert isinstance(result, ToolError)
    assert result.is_error
    assert "Glob failed" in result.brief
    assert "boom" in result.message


# ---------------------------------------------------------------------------
# MAX_MATCHES truncation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_glob_truncates_at_max_matches(tmp_path: Path) -> None:
    runtime = _make_runtime(KaosPath(str(tmp_path)))
    tool = Glob(runtime)

    # Create many files
    for i in range(MAX_MATCHES + 10):
        (tmp_path / f"file{i:04d}.py").write_text("x")

    result = await tool(Params(pattern="*.py"))
    assert isinstance(result, ToolOk)
    assert isinstance(result.output, str)
    lines = result.output.split("\n")
    assert len(lines) == MAX_MATCHES
    assert f"Only the first {MAX_MATCHES} matches" in result.message


@pytest.mark.asyncio
async def test_glob_exactly_max_matches_no_truncation_message(tmp_path: Path) -> None:
    runtime = _make_runtime(KaosPath(str(tmp_path)))
    tool = Glob(runtime)

    for i in range(MAX_MATCHES):
        (tmp_path / f"file{i:04d}.py").write_text("x")

    result = await tool(Params(pattern="*.py"))
    assert isinstance(result, ToolOk)
    assert isinstance(result.output, str)
    lines = result.output.split("\n")
    assert len(lines) == MAX_MATCHES
    assert "Only the first" not in result.message


# ---------------------------------------------------------------------------
# Directory expansion (expanduser)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_glob_expands_user_directory(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    runtime = _make_runtime(KaosPath(str(tmp_path)))
    tool = Glob(runtime)

    fake_home = tmp_path / "home"
    fake_home.mkdir()
    (fake_home / "test.py").write_text("test")

    monkeypatch.setattr(
        "kimi_cli.tools.file.glob.KaosPath.expanduser",
        lambda self: KaosPath(str(fake_home)) if str(self).startswith("~") else self,
    )

    result = await tool(Params(pattern="*.py", directory="~"))
    assert isinstance(result, ToolOk)
    assert isinstance(result.output, str)
    assert "test.py" in result.output


# ---------------------------------------------------------------------------
# Class attributes
# ---------------------------------------------------------------------------


def test_glob_class_attributes() -> None:
    from kimi_cli.tools.file.glob import Glob, Params

    assert Glob.name == "Glob"
    assert Glob.params is Params
    assert "glob" in Glob.description.lower()
