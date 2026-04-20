"""Comprehensive unit tests for kimi_cli.tools.file.read."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "kimi-cli" / "src"))

from kaos.path import KaosPath

from kimi_cli.tools.file.read import (
    MAX_BYTES,
    MAX_LINE_LENGTH,
    MAX_LINES,
    Params,
    ReadFile,
)
from kosong.tooling import ToolError, ToolOk


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_runtime(work_dir: KaosPath) -> Any:
    """Create a minimal fake Runtime with only the fields ReadFile needs."""
    runtime = MagicMock()
    builtin_args = MagicMock()
    builtin_args.KIMI_WORK_DIR = work_dir
    runtime.builtin_args = builtin_args
    runtime.additional_dirs = []
    return runtime


# ---------------------------------------------------------------------------
# Params model
# ---------------------------------------------------------------------------


def test_params_defaults() -> None:
    p = Params(path="foo.txt")
    assert p.path == "foo.txt"
    assert p.line_offset == 1
    assert p.n_lines == MAX_LINES


def test_params_custom() -> None:
    p = Params(path="foo.txt", line_offset=5, n_lines=10)
    assert p.path == "foo.txt"
    assert p.line_offset == 5
    assert p.n_lines == 10


def test_params_line_offset_zero_invalid() -> None:
    with pytest.raises(ValueError, match="line_offset cannot be 0"):
        Params(path="foo.txt", line_offset=0)


def test_params_line_offset_too_negative() -> None:
    with pytest.raises(ValueError, match=f"line_offset cannot be less than -{MAX_LINES}"):
        Params(path="foo.txt", line_offset=-(MAX_LINES + 1))


def test_params_n_lines_min() -> None:
    with pytest.raises(ValueError):
        Params(path="foo.txt", n_lines=0)


# ---------------------------------------------------------------------------
# Empty path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_path() -> None:
    runtime = _make_runtime(KaosPath("/tmp"))
    tool = ReadFile(runtime)
    result = await tool(Params(path=""))
    assert isinstance(result, ToolError)
    assert result.is_error
    assert "Empty file path" in result.brief


# ---------------------------------------------------------------------------
# Path validation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_relative_path_outside_workspace(tmp_path: Path) -> None:
    work_dir = KaosPath(str(tmp_path / "work"))
    runtime = _make_runtime(work_dir)
    tool = ReadFile(runtime)

    result = await tool(Params(path="../outside.txt"))
    assert isinstance(result, ToolError)
    assert result.is_error
    assert "Invalid path" in result.brief
    assert "absolute path" in result.message


@pytest.mark.asyncio
async def test_absolute_path_outside_workspace_allowed(tmp_path: Path) -> None:
    work_dir = KaosPath(str(tmp_path / "work"))
    await work_dir.mkdir(parents=True, exist_ok=True)
    outside = tmp_path / "outside.txt"
    outside.write_text("hello", encoding="utf-8")

    runtime = _make_runtime(work_dir)
    tool = ReadFile(runtime)

    result = await tool(Params(path=str(outside)))
    assert isinstance(result, ToolOk)
    assert not result.is_error


# ---------------------------------------------------------------------------
# Sensitive file blocking
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sensitive_file_blocked(tmp_path: Path) -> None:
    work_dir = KaosPath(str(tmp_path))
    runtime = _make_runtime(work_dir)
    tool = ReadFile(runtime)

    env_file = tmp_path / ".env"
    env_file.write_text("SECRET=1", encoding="utf-8")

    result = await tool(Params(path=str(env_file)))
    assert isinstance(result, ToolError)
    assert result.is_error
    assert "Sensitive file" in result.brief


@pytest.mark.asyncio
async def test_sensitive_file_exemption(tmp_path: Path) -> None:
    work_dir = KaosPath(str(tmp_path))
    runtime = _make_runtime(work_dir)
    tool = ReadFile(runtime)

    env_example = tmp_path / ".env.example"
    env_example.write_text("FOO=bar", encoding="utf-8")

    result = await tool(Params(path=str(env_example)))
    assert isinstance(result, ToolOk)
    assert not result.is_error


# ---------------------------------------------------------------------------
# File not found / not a file
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_file_not_found(tmp_path: Path) -> None:
    work_dir = KaosPath(str(tmp_path))
    runtime = _make_runtime(work_dir)
    tool = ReadFile(runtime)

    result = await tool(Params(path=str(tmp_path / "nonexistent.txt")))
    assert isinstance(result, ToolError)
    assert result.is_error
    assert "File not found" in result.brief


@pytest.mark.asyncio
async def test_path_is_directory(tmp_path: Path) -> None:
    work_dir = KaosPath(str(tmp_path))
    runtime = _make_runtime(work_dir)
    tool = ReadFile(runtime)

    subdir = tmp_path / "subdir"
    subdir.mkdir()

    result = await tool(Params(path=str(subdir)))
    assert isinstance(result, ToolError)
    assert result.is_error
    assert "Invalid path" in result.brief


# ---------------------------------------------------------------------------
# Unsupported / unreadable file types
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_image_file_blocked(tmp_path: Path) -> None:
    work_dir = KaosPath(str(tmp_path))
    runtime = _make_runtime(work_dir)
    tool = ReadFile(runtime)

    img = tmp_path / "photo.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"fake" * 10)

    result = await tool(Params(path=str(img)))
    assert isinstance(result, ToolError)
    assert result.is_error
    assert "Unsupported file type" in result.brief


@pytest.mark.asyncio
async def test_video_file_blocked(tmp_path: Path) -> None:
    work_dir = KaosPath(str(tmp_path))
    runtime = _make_runtime(work_dir)
    tool = ReadFile(runtime)

    vid = tmp_path / "movie.mp4"
    vid.write_bytes(b"\x00\x00\x00\x20ftypisom" + b"fake" * 10)

    result = await tool(Params(path=str(vid)))
    assert isinstance(result, ToolError)
    assert result.is_error
    assert "Unsupported file type" in result.brief


@pytest.mark.asyncio
async def test_unknown_file_type_blocked(tmp_path: Path) -> None:
    work_dir = KaosPath(str(tmp_path))
    runtime = _make_runtime(work_dir)
    tool = ReadFile(runtime)

    binary = tmp_path / "data.bin"
    binary.write_bytes(b"\x00\x01\x02\x03" * 10)

    result = await tool(Params(path=str(binary)))
    assert isinstance(result, ToolError)
    assert result.is_error
    assert "File not readable" in result.brief


# ---------------------------------------------------------------------------
# Forward read — basic
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_read_basic(tmp_path: Path) -> None:
    work_dir = KaosPath(str(tmp_path))
    runtime = _make_runtime(work_dir)
    tool = ReadFile(runtime)

    f = tmp_path / "file.txt"
    f.write_text("line1\nline2\nline3\n", encoding="utf-8")

    result = await tool(Params(path=str(f)))
    assert isinstance(result, ToolOk)
    assert not result.is_error
    assert "     1\tline1\n     2\tline2\n     3\tline3\n" == result.output
    assert "3 lines read from file starting from line 1." in result.message
    assert "Total lines in file: 3." in result.message
    assert "End of file reached." in result.message


@pytest.mark.asyncio
async def test_read_no_trailing_newline(tmp_path: Path) -> None:
    work_dir = KaosPath(str(tmp_path))
    runtime = _make_runtime(work_dir)
    tool = ReadFile(runtime)

    f = tmp_path / "file.txt"
    f.write_text("line1\nline2", encoding="utf-8")

    result = await tool(Params(path=str(f)))
    assert isinstance(result, ToolOk)
    lines = result.output.splitlines()
    assert len(lines) == 2
    assert "Total lines in file: 2." in result.message


@pytest.mark.asyncio
async def test_read_with_line_offset(tmp_path: Path) -> None:
    work_dir = KaosPath(str(tmp_path))
    runtime = _make_runtime(work_dir)
    tool = ReadFile(runtime)

    f = tmp_path / "file.txt"
    f.write_text("a\nb\nc\nd\n", encoding="utf-8")

    result = await tool(Params(path=str(f), line_offset=2))
    assert isinstance(result, ToolOk)
    assert "     2\tb\n     3\tc\n     4\td\n" == result.output
    assert "3 lines read from file starting from line 2." in result.message


@pytest.mark.asyncio
async def test_read_with_n_lines(tmp_path: Path) -> None:
    work_dir = KaosPath(str(tmp_path))
    runtime = _make_runtime(work_dir)
    tool = ReadFile(runtime)

    f = tmp_path / "file.txt"
    f.write_text("a\nb\nc\nd\n", encoding="utf-8")

    result = await tool(Params(path=str(f), line_offset=1, n_lines=2))
    assert isinstance(result, ToolOk)
    assert "     1\ta\n     2\tb\n" == result.output
    assert "2 lines read from file starting from line 1." in result.message


@pytest.mark.asyncio
async def test_read_offset_beyond_eof(tmp_path: Path) -> None:
    work_dir = KaosPath(str(tmp_path))
    runtime = _make_runtime(work_dir)
    tool = ReadFile(runtime)

    f = tmp_path / "file.txt"
    f.write_text("a\nb\n", encoding="utf-8")

    result = await tool(Params(path=str(f), line_offset=10))
    assert isinstance(result, ToolOk)
    assert result.output == ""
    assert "No lines read from file." in result.message
    assert "Total lines in file: 2." in result.message


# ---------------------------------------------------------------------------
# Forward read — limits
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_read_max_lines_limit(tmp_path: Path) -> None:
    work_dir = KaosPath(str(tmp_path))
    runtime = _make_runtime(work_dir)
    tool = ReadFile(runtime)

    f = tmp_path / "file.txt"
    f.write_text("\n".join(f"line{i}" for i in range(MAX_LINES + 5)) + "\n")

    result = await tool(Params(path=str(f), line_offset=1, n_lines=MAX_LINES + 10))
    assert isinstance(result, ToolOk)
    assert result.output.count("\n") == MAX_LINES
    assert f"Max {MAX_LINES} lines reached." in result.message


@pytest.mark.asyncio
async def test_read_max_bytes_limit(tmp_path: Path) -> None:
    work_dir = KaosPath(str(tmp_path))
    runtime = _make_runtime(work_dir)
    tool = ReadFile(runtime)

    f = tmp_path / "file.txt"
    # Each line is ~100 bytes; 2000 lines > 100KB
    # 600 lines * ~301 bytes each = ~180600 bytes > 102400, and 600 < 1000 (MAX_LINES)
    f.write_text("\n".join("x" * 300 for _ in range(600)) + "\n")

    result = await tool(Params(path=str(f), line_offset=1, n_lines=600))
    assert isinstance(result, ToolOk)
    assert f"Max {MAX_BYTES} bytes reached." in result.message


# ---------------------------------------------------------------------------
# Forward read — line truncation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_read_truncates_long_lines(tmp_path: Path) -> None:
    work_dir = KaosPath(str(tmp_path))
    runtime = _make_runtime(work_dir)
    tool = ReadFile(runtime)

    f = tmp_path / "file.txt"
    f.write_text("short\n" + "x" * (MAX_LINE_LENGTH + 50) + "\n", encoding="utf-8")

    result = await tool(Params(path=str(f)))
    assert isinstance(result, ToolOk)
    lines = result.output.splitlines()
    assert len(lines) == 2
    second_line_content = lines[1].split("\t", 1)[1]
    assert len(second_line_content) <= MAX_LINE_LENGTH + 10  # allow for "..." marker
    assert "Lines [2] were truncated." in result.message


# ---------------------------------------------------------------------------
# Tail read — basic
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_read_tail_basic(tmp_path: Path) -> None:
    work_dir = KaosPath(str(tmp_path))
    runtime = _make_runtime(work_dir)
    tool = ReadFile(runtime)

    f = tmp_path / "file.txt"
    f.write_text("a\nb\nc\nd\ne\n", encoding="utf-8")

    result = await tool(Params(path=str(f), line_offset=-3))
    assert isinstance(result, ToolOk)
    assert "     3\tc\n     4\td\n     5\te\n" == result.output
    assert "3 lines read from file starting from line 3." in result.message
    assert "End of file reached." in result.message


@pytest.mark.asyncio
async def test_read_tail_with_n_lines(tmp_path: Path) -> None:
    work_dir = KaosPath(str(tmp_path))
    runtime = _make_runtime(work_dir)
    tool = ReadFile(runtime)

    f = tmp_path / "file.txt"
    f.write_text("a\nb\nc\nd\ne\n", encoding="utf-8")

    result = await tool(Params(path=str(f), line_offset=-5, n_lines=2))
    assert isinstance(result, ToolOk)
    assert "     1\ta\n     2\tb\n" == result.output
    assert "2 lines read from file starting from line 1." in result.message


@pytest.mark.asyncio
async def test_read_tail_n_lines_less_than_tail_count(tmp_path: Path) -> None:
    work_dir = KaosPath(str(tmp_path))
    runtime = _make_runtime(work_dir)
    tool = ReadFile(runtime)

    f = tmp_path / "file.txt"
    f.write_text("a\nb\nc\nd\ne\n", encoding="utf-8")

    result = await tool(Params(path=str(f), line_offset=-5, n_lines=3))
    assert isinstance(result, ToolOk)
    assert "     1\ta\n     2\tb\n     3\tc\n" == result.output


@pytest.mark.asyncio
async def test_read_tail_negative_offset_beyond_total(tmp_path: Path) -> None:
    work_dir = KaosPath(str(tmp_path))
    runtime = _make_runtime(work_dir)
    tool = ReadFile(runtime)

    f = tmp_path / "file.txt"
    f.write_text("a\nb\n", encoding="utf-8")

    result = await tool(Params(path=str(f), line_offset=-10))
    assert isinstance(result, ToolOk)
    assert "     1\ta\n     2\tb\n" == result.output
    assert "End of file reached." in result.message


# ---------------------------------------------------------------------------
# Tail read — limits
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_read_tail_max_lines_limit(tmp_path: Path) -> None:
    work_dir = KaosPath(str(tmp_path))
    runtime = _make_runtime(work_dir)
    tool = ReadFile(runtime)

    f = tmp_path / "file.txt"
    f.write_text("\n".join(f"line{i}" for i in range(MAX_LINES + 5)) + "\n")

    result = await tool(Params(path=str(f), line_offset=-MAX_LINES, n_lines=MAX_LINES + 10))
    assert isinstance(result, ToolOk)
    assert result.output.count("\n") == MAX_LINES
    # max_lines_reached in tail mode requires tail_count > MAX_LINES, which is
    # impossible given Params validation. End of file is reported instead.
    assert "End of file reached." in result.message


@pytest.mark.asyncio
async def test_read_tail_max_bytes_limit(tmp_path: Path) -> None:
    work_dir = KaosPath(str(tmp_path))
    runtime = _make_runtime(work_dir)
    tool = ReadFile(runtime)

    f = tmp_path / "file.txt"
    # Create lines that exceed MAX_BYTES when tailing many of them
    # 1000 lines * ~301 bytes each = ~301000 bytes > 102400
    f.write_text("\n".join("x" * 300 for _ in range(1200)) + "\n")

    result = await tool(Params(path=str(f), line_offset=-MAX_LINES, n_lines=MAX_LINES))
    assert isinstance(result, ToolOk)
    assert f"Max {MAX_BYTES} bytes reached." in result.message


# ---------------------------------------------------------------------------
# Tail read — line truncation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_read_tail_truncates_long_lines(tmp_path: Path) -> None:
    work_dir = KaosPath(str(tmp_path))
    runtime = _make_runtime(work_dir)
    tool = ReadFile(runtime)

    f = tmp_path / "file.txt"
    f.write_text("short\n" + "x" * (MAX_LINE_LENGTH + 50) + "\n", encoding="utf-8")

    result = await tool(Params(path=str(f), line_offset=-2))
    assert isinstance(result, ToolOk)
    lines = result.output.splitlines()
    assert len(lines) == 2
    second_line_content = lines[1].split("\t", 1)[1]
    assert len(second_line_content) <= MAX_LINE_LENGTH + 10
    assert "Lines [2] were truncated." in result.message


# ---------------------------------------------------------------------------
# Exception handling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_read_exception_handling(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    work_dir = KaosPath(str(tmp_path))
    runtime = _make_runtime(work_dir)
    tool = ReadFile(runtime)

    f = tmp_path / "file.txt"
    f.write_text("hello", encoding="utf-8")

    async def _broken_read_lines(self: KaosPath, **kwargs: Any) -> Any:
        raise RuntimeError("disk fail")
        yield ""  # type: ignore[unreachable]

    monkeypatch.setattr(
        "kimi_cli.tools.file.read.KaosPath.read_lines",
        _broken_read_lines,
    )

    result = await tool(Params(path=str(f)))
    assert isinstance(result, ToolError)
    assert result.is_error
    assert "Failed to read file" in result.brief
    assert "disk fail" in result.message


# ---------------------------------------------------------------------------
# Class attributes
# ---------------------------------------------------------------------------


def test_read_class_attributes() -> None:
    from unittest.mock import MagicMock

    runtime = MagicMock()
    runtime.builtin_args.KIMI_WORK_DIR = KaosPath("/tmp")
    runtime.additional_dirs = []
    tool = ReadFile(runtime)
    assert ReadFile.name == "ReadFile"
    assert ReadFile.params is Params
    assert "Read text files" in tool.description
