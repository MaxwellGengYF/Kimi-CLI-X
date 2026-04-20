"""Comprehensive unit tests for kimi_cli.tools.file.grep_local internal helpers."""

from __future__ import annotations

import asyncio
import platform
import stat
import sys
import tempfile
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure kimi-cli src is importable when running pytest from repo root
sys.path.insert(0, str(Path(__file__).parent.parent / "kimi-cli" / "src"))

from kimi_cli.tools.file.grep_local import (
    RG_KILL_GRACE,
    RG_MAX_BUFFER,
    Params,
    _build_rg_args,
    _detect_target,
    _download_and_install_rg,
    _ensure_rg_path,
    _find_existing_rg,
    _is_eagain,
    _kill_process,
    _read_stream,
    _rg_binary_name,
    _strip_path_prefix,
)


# ---------------------------------------------------------------------------
# _rg_binary_name
# ---------------------------------------------------------------------------


def test_rg_binary_name_windows(monkeypatch):
    monkeypatch.setattr("kimi_cli.tools.file.grep_local.platform.system", lambda: "Windows")
    assert _rg_binary_name() == "rg.exe"


def test_rg_binary_name_non_windows(monkeypatch):
    monkeypatch.setattr("kimi_cli.tools.file.grep_local.platform.system", lambda: "Linux")
    assert _rg_binary_name() == "rg"


# ---------------------------------------------------------------------------
# _find_existing_rg
# ---------------------------------------------------------------------------


def test_find_existing_rg_in_share_dir(tmp_path, monkeypatch):
    bin_name = "rg.exe" if platform.system() == "Windows" else "rg"
    share_bin = tmp_path / "bin" / bin_name
    share_bin.parent.mkdir(parents=True)
    share_bin.write_text("fake rg")

    monkeypatch.setattr(
        "kimi_cli.tools.file.grep_local.get_share_dir", lambda: tmp_path
    )
    # Clear lru_cache before test
    _find_existing_rg.cache_clear()

    result = _find_existing_rg(bin_name)
    assert result == share_bin


def test_find_existing_rg_in_local_deps(tmp_path, monkeypatch):
    bin_name = "rg.exe" if platform.system() == "Windows" else "rg"
    # Simulate local dep path
    fake_kimi_cli_file = tmp_path / "kimi_cli" / "__init__.py"
    fake_kimi_cli_file.parent.mkdir(parents=True)
    fake_kimi_cli_file.write_text("")
    local_dep = tmp_path / "kimi_cli" / "deps" / "bin" / bin_name
    local_dep.parent.mkdir(parents=True)
    local_dep.write_text("fake rg")

    monkeypatch.setattr(
        "kimi_cli.tools.file.grep_local.get_share_dir", lambda: tmp_path / "nonexistent"
    )
    monkeypatch.setattr(
        "kimi_cli.tools.file.grep_local.kimi_cli.__file__", str(fake_kimi_cli_file)
    )
    _find_existing_rg.cache_clear()

    result = _find_existing_rg(bin_name)
    assert result == local_dep


def test_find_existing_rg_system_rg(tmp_path, monkeypatch):
    bin_name = "rg.exe" if platform.system() == "Windows" else "rg"
    fake_rg = tmp_path / bin_name
    fake_rg.write_text("fake rg")

    monkeypatch.setattr(
        "kimi_cli.tools.file.grep_local.get_share_dir", lambda: tmp_path / "nonexistent"
    )
    monkeypatch.setattr(
        "kimi_cli.tools.file.grep_local.kimi_cli.__file__", str(tmp_path / "kimi_cli" / "__init__.py")
    )
    monkeypatch.setattr(
        "kimi_cli.tools.file.grep_local.shutil.which", lambda x: str(fake_rg) if x in (bin_name, "rg") else None
    )
    _find_existing_rg.cache_clear()

    result = _find_existing_rg(bin_name)
    assert result == fake_rg


def test_find_existing_rg_not_found(tmp_path, monkeypatch):
    bin_name = "rg"
    monkeypatch.setattr(
        "kimi_cli.tools.file.grep_local.get_share_dir", lambda: tmp_path / "nonexistent"
    )
    monkeypatch.setattr(
        "kimi_cli.tools.file.grep_local.kimi_cli.__file__", str(tmp_path / "kimi_cli" / "__init__.py")
    )
    monkeypatch.setattr(
        "kimi_cli.tools.file.grep_local.shutil.which", lambda x: None
    )
    _find_existing_rg.cache_clear()

    assert _find_existing_rg(bin_name) is None


# ---------------------------------------------------------------------------
# _detect_target
# ---------------------------------------------------------------------------


def test_detect_target_darwin_x86_64(monkeypatch):
    monkeypatch.setattr("platform.system", lambda: "Darwin")
    monkeypatch.setattr("platform.machine", lambda: "x86_64")
    assert _detect_target() == "x86_64-apple-darwin"


def test_detect_target_darwin_arm64(monkeypatch):
    monkeypatch.setattr("platform.system", lambda: "Darwin")
    monkeypatch.setattr("platform.machine", lambda: "arm64")
    assert _detect_target() == "aarch64-apple-darwin"


def test_detect_target_linux_x86_64(monkeypatch):
    monkeypatch.setattr("platform.system", lambda: "Linux")
    monkeypatch.setattr("platform.machine", lambda: "x86_64")
    assert _detect_target() == "x86_64-unknown-linux-musl"


def test_detect_target_linux_aarch64(monkeypatch):
    monkeypatch.setattr("platform.system", lambda: "Linux")
    monkeypatch.setattr("platform.machine", lambda: "aarch64")
    assert _detect_target() == "aarch64-unknown-linux-gnu"


def test_detect_target_windows_amd64(monkeypatch):
    monkeypatch.setattr("platform.system", lambda: "Windows")
    monkeypatch.setattr("platform.machine", lambda: "AMD64")
    assert _detect_target() == "x86_64-pc-windows-msvc"


def test_detect_target_unsupported_arch(monkeypatch):
    monkeypatch.setattr("platform.system", lambda: "Linux")
    monkeypatch.setattr("platform.machine", lambda: "riscv64")
    assert _detect_target() is None


def test_detect_target_unsupported_os(monkeypatch):
    monkeypatch.setattr("platform.system", lambda: "FreeBSD")
    monkeypatch.setattr("platform.machine", lambda: "x86_64")
    assert _detect_target() is None


# ---------------------------------------------------------------------------
# _download_and_install_rg
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_download_and_install_rg_unsupported_platform(monkeypatch):
    monkeypatch.setattr(
        "kimi_cli.tools.file.grep_local._detect_target", lambda: None
    )
    with pytest.raises(RuntimeError, match="Unsupported platform"):
        await _download_and_install_rg("rg")


@pytest.mark.asyncio
async def test_download_and_install_rg_windows_zip(tmp_path, monkeypatch):
    monkeypatch.setattr("kimi_cli.tools.file.grep_local._detect_target", lambda: "x86_64-pc-windows-msvc")
    monkeypatch.setattr(
        "kimi_cli.tools.file.grep_local.get_share_dir", lambda: tmp_path
    )

    # Build a fake zip archive containing rg.exe
    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zf:
        zf.writestr("ripgrep-15.0.0-x86_64-pc-windows-msvc/rg.exe", b"fake rg binary")
    zip_bytes = zip_buffer.getvalue()

    fake_resp = MagicMock()

    async def _iter_chunked(*args, **kwargs):
        yield zip_bytes

    fake_resp.content.iter_chunked = _iter_chunked
    fake_resp.raise_for_status = MagicMock()
    fake_session = MagicMock()
    fake_session.get = MagicMock(return_value=AsyncMock(__aenter__=AsyncMock(return_value=fake_resp), __aexit__=AsyncMock(return_value=None)))

    class _FakeClientSessionCM:
        async def __aenter__(self):
            return fake_session
        async def __aexit__(self, exc_type, exc, tb):
            return None

    def _fake_new_client_session(*, timeout):
        return _FakeClientSessionCM()

    monkeypatch.setattr(
        "kimi_cli.tools.file.grep_local.new_client_session", _fake_new_client_session
    )

    result = await _download_and_install_rg("rg.exe")
    assert result.name == "rg.exe"
    assert result.read_text() == "fake rg binary"
    # Check executable permissions were added
    mode = result.stat().st_mode
    assert mode & stat.S_IXUSR


@pytest.mark.asyncio
async def test_download_and_install_rg_linux_tar(tmp_path, monkeypatch):
    import tarfile

    monkeypatch.setattr("kimi_cli.tools.file.grep_local._detect_target", lambda: "x86_64-unknown-linux-musl")
    monkeypatch.setattr(
        "kimi_cli.tools.file.grep_local.get_share_dir", lambda: tmp_path
    )

    # Build a fake tar.gz archive containing rg
    tar_buffer = BytesIO()
    with tarfile.open(fileobj=tar_buffer, mode="w:gz") as tar:
        data = b"fake rg binary"
        info = tarfile.TarInfo(name="ripgrep-15.0.0-x86_64-unknown-linux-musl/rg")
        info.size = len(data)
        tar.addfile(info, BytesIO(data))
    tar_bytes = tar_buffer.getvalue()

    fake_resp = MagicMock()

    async def _iter_chunked(*args, **kwargs):
        yield tar_bytes

    fake_resp.content.iter_chunked = _iter_chunked
    fake_resp.raise_for_status = MagicMock()
    fake_session = MagicMock()
    fake_session.get = MagicMock(return_value=AsyncMock(__aenter__=AsyncMock(return_value=fake_resp), __aexit__=AsyncMock(return_value=None)))

    class _FakeClientSessionCM:
        async def __aenter__(self):
            return fake_session
        async def __aexit__(self, exc_type, exc, tb):
            return None

    def _fake_new_client_session(*, timeout):
        return _FakeClientSessionCM()

    monkeypatch.setattr(
        "kimi_cli.tools.file.grep_local.new_client_session", _fake_new_client_session
    )

    result = await _download_and_install_rg("rg")
    assert result.name == "rg"
    assert result.read_text() == "fake rg binary"


@pytest.mark.asyncio
async def test_download_and_install_rg_bad_archive(tmp_path, monkeypatch):
    monkeypatch.setattr("kimi_cli.tools.file.grep_local._detect_target", lambda: "x86_64-pc-windows-msvc")
    monkeypatch.setattr(
        "kimi_cli.tools.file.grep_local.get_share_dir", lambda: tmp_path
    )

    fake_resp = MagicMock()

    async def _iter_chunked(*args, **kwargs):
        yield b"not a valid zip"

    fake_resp.content.iter_chunked = _iter_chunked
    fake_resp.raise_for_status = MagicMock()
    fake_session = MagicMock()
    fake_session.get = MagicMock(return_value=AsyncMock(__aenter__=AsyncMock(return_value=fake_resp), __aexit__=AsyncMock(return_value=None)))

    class _FakeClientSessionCM:
        async def __aenter__(self):
            return fake_session
        async def __aexit__(self, exc_type, exc, tb):
            return None

    def _fake_new_client_session(*, timeout):
        return _FakeClientSessionCM()

    monkeypatch.setattr(
        "kimi_cli.tools.file.grep_local.new_client_session", _fake_new_client_session
    )

    with pytest.raises(RuntimeError, match="Failed to extract"):
        await _download_and_install_rg("rg.exe")


@pytest.mark.asyncio
async def test_download_and_install_rg_network_error(tmp_path, monkeypatch):
    monkeypatch.setattr("kimi_cli.tools.file.grep_local._detect_target", lambda: "x86_64-pc-windows-msvc")
    monkeypatch.setattr(
        "kimi_cli.tools.file.grep_local.get_share_dir", lambda: tmp_path
    )

    import aiohttp

    fake_resp = MagicMock()

    def _iter_chunked(*args, **kwargs):
        raise aiohttp.ClientError("connection refused")

    fake_resp.content.iter_chunked = _iter_chunked
    fake_resp.raise_for_status = MagicMock()
    fake_session = MagicMock()
    fake_session.get = MagicMock(return_value=AsyncMock(__aenter__=AsyncMock(return_value=fake_resp), __aexit__=AsyncMock(return_value=None)))

    class _FakeClientSessionCM:
        async def __aenter__(self):
            return fake_session
        async def __aexit__(self, exc_type, exc, tb):
            return None

    def _fake_new_client_session(*, timeout):
        return _FakeClientSessionCM()

    monkeypatch.setattr(
        "kimi_cli.tools.file.grep_local.new_client_session", _fake_new_client_session
    )

    with pytest.raises(RuntimeError, match="Failed to download"):
        await _download_and_install_rg("rg.exe")


# ---------------------------------------------------------------------------
# _ensure_rg_path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ensure_rg_path_found_existing(tmp_path, monkeypatch):
    bin_name = "rg.exe" if platform.system() == "Windows" else "rg"
    fake_rg = tmp_path / bin_name
    fake_rg.write_text("fake")

    monkeypatch.setattr(
        "kimi_cli.tools.file.grep_local._find_existing_rg", lambda x: fake_rg
    )
    _find_existing_rg.cache_clear()

    path = await _ensure_rg_path()
    assert path == str(fake_rg)


@pytest.mark.asyncio
async def test_ensure_rg_path_downloads_when_missing(tmp_path, monkeypatch):
    bin_name = "rg"
    fake_rg = tmp_path / bin_name
    fake_rg.write_text("downloaded")

    call_count = 0

    def _fake_find_existing(bin_name):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return None
        return fake_rg

    monkeypatch.setattr(
        "kimi_cli.tools.file.grep_local._find_existing_rg", _fake_find_existing
    )
    monkeypatch.setattr(
        "kimi_cli.tools.file.grep_local._download_and_install_rg",
        AsyncMock(return_value=fake_rg),
    )
    _find_existing_rg.cache_clear()

    path = await _ensure_rg_path()
    assert path == str(fake_rg)


# ---------------------------------------------------------------------------
# _build_rg_args
# ---------------------------------------------------------------------------


def test_build_rg_args_no_max_columns_in_content_mode():
    params = Params(pattern="foo", path="/tmp", output_mode="content")
    args = _build_rg_args("/usr/bin/rg", params)
    assert "--max-columns" not in args


def test_build_rg_args_max_columns_in_files_with_matches():
    params = Params(pattern="foo", path="/tmp", output_mode="files_with_matches")
    args = _build_rg_args("/usr/bin/rg", params)
    assert "--max-columns" in args
    idx = args.index("--max-columns")
    assert args[idx + 1] == "500"


def test_build_rg_args_include_ignored():
    params = Params(pattern="foo", path="/tmp", include_ignored=True)
    args = _build_rg_args("/usr/bin/rg", params)
    assert "--no-ignore" in args


def test_build_rg_args_vcs_globs_always_present():
    params = Params(pattern="foo", path="/tmp")
    args = _build_rg_args("/usr/bin/rg", params)
    for vcs in (".git", ".svn", ".hg", ".bzr", ".jj", ".sl"):
        assert f"!{vcs}" in args


def test_build_rg_args_single_threaded():
    params = Params(pattern="foo", path="/tmp")
    args = _build_rg_args("/usr/bin/rg", params, single_threaded=True)
    idx = args.index("-j")
    assert args[idx + 1] == "1"


def test_build_rg_args_ignore_case():
    params = Params.model_validate({"pattern": "foo", "path": "/tmp", "-i": True})
    args = _build_rg_args("/usr/bin/rg", params)
    assert "--ignore-case" in args


def test_build_rg_args_multiline():
    params = Params(pattern="foo", path="/tmp", multiline=True)
    args = _build_rg_args("/usr/bin/rg", params)
    assert "--multiline" in args
    assert "--multiline-dotall" in args


def test_build_rg_args_content_context():
    params = Params.model_validate(
        {
            "pattern": "foo",
            "path": "/tmp",
            "output_mode": "content",
            "-B": 2,
            "-A": 3,
            "-C": 1,
        }
    )
    args = _build_rg_args("/usr/bin/rg", params)
    assert "--before-context" in args
    assert "--after-context" in args
    assert "--context" in args


def test_build_rg_args_content_no_line_number():
    params = Params.model_validate(
        {"pattern": "foo", "path": "/tmp", "output_mode": "content", "-n": False}
    )
    args = _build_rg_args("/usr/bin/rg", params)
    assert "--line-number" not in args


def test_build_rg_args_glob_and_type():
    params = Params(pattern="foo", path="/tmp", glob="*.py", type="py")
    args = _build_rg_args("/usr/bin/rg", params)
    assert "--glob" in args
    assert "*.py" in args
    assert "--type" in args
    assert "py" in args


def test_build_rg_args_pattern_path_after_dd():
    params = Params(pattern="-foo", path="~/bar")
    args = _build_rg_args("/usr/bin/rg", params)
    dd_idx = args.index("--")
    assert args[dd_idx + 1] == "-foo"
    assert not args[dd_idx + 2].startswith("~")


# ---------------------------------------------------------------------------
# _read_stream
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_read_stream_basic():
    reader = asyncio.StreamReader()
    reader.feed_data(b"hello world")
    reader.feed_eof()
    buf = bytearray()
    truncated = await _read_stream(reader, buf, 1000)
    assert not truncated
    assert buf == b"hello world"


@pytest.mark.asyncio
async def test_read_stream_truncation():
    reader = asyncio.StreamReader()
    data = b"x" * 200
    reader.feed_data(data)
    reader.feed_eof()
    buf = bytearray()
    truncated = await _read_stream(reader, buf, 100)
    assert truncated
    assert len(buf) == 100
    assert buf == b"x" * 100


@pytest.mark.asyncio
async def test_read_stream_truncation_flag():
    reader = asyncio.StreamReader()
    data = b"x" * 200
    reader.feed_data(data)
    reader.feed_eof()
    buf = bytearray()
    flag: list[bool] = [False]
    truncated = await _read_stream(reader, buf, 100, flag)
    assert truncated
    assert flag[0] is True


@pytest.mark.asyncio
async def test_read_stream_exact_limit():
    reader = asyncio.StreamReader()
    data = b"x" * 100
    reader.feed_data(data)
    reader.feed_eof()
    buf = bytearray()
    truncated = await _read_stream(reader, buf, 100)
    assert not truncated
    assert buf == b"x" * 100


@pytest.mark.asyncio
async def test_read_stream_multiple_chunks():
    reader = asyncio.StreamReader()
    for i in range(5):
        reader.feed_data(f"chunk{i}".encode())
    reader.feed_eof()
    buf = bytearray()
    truncated = await _read_stream(reader, buf, 1000)
    assert not truncated
    assert buf == b"chunk0chunk1chunk2chunk3chunk4"


@pytest.mark.asyncio
async def test_read_stream_drains_after_limit():
    reader = asyncio.StreamReader()
    reader.feed_data(b"x" * 50)
    reader.feed_data(b"y" * 1000)
    reader.feed_eof()
    buf = bytearray()
    truncated = await _read_stream(reader, buf, 50)
    assert truncated
    assert buf == b"x" * 50


# ---------------------------------------------------------------------------
# _kill_process
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_kill_process_terminates_gracefully():
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-c", "pass",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await _kill_process(proc)
    assert proc.returncode is not None


@pytest.mark.asyncio
async def test_kill_process_force_kill():
    # Start a process that ignores SIGTERM (sleep long enough)
    # On Windows this is less deterministic, so we mock
    proc = MagicMock()
    proc.terminate = MagicMock()
    proc.kill = MagicMock()
    proc.wait = AsyncMock(side_effect=[asyncio.TimeoutError, None])

    await _kill_process(proc)
    proc.terminate.assert_called_once()
    proc.kill.assert_called_once()


# ---------------------------------------------------------------------------
# _is_eagain
# ---------------------------------------------------------------------------


def test_is_eagain_linux():
    assert _is_eagain("some os error 11 happened") is True


def test_is_eagain_resource_temporarily_unavailable():
    assert _is_eagain("Resource temporarily unavailable") is True


def test_is_eagain_no_match():
    assert _is_eagain("some random error") is False


def test_is_eagain_empty():
    assert _is_eagain("") is False


# ---------------------------------------------------------------------------
# _strip_path_prefix
# ---------------------------------------------------------------------------


def test_strip_path_prefix_empty():
    assert _strip_path_prefix([], "/home/user") == []


def test_strip_path_prefix_single_line():
    assert _strip_path_prefix(["/home/user/file.py"], "/home/user") == ["file.py"]


def test_strip_path_prefix_mixed_separators():
    output = ["/home/user/project/src/a.py:10:hello"]
    result = _strip_path_prefix(output, "/home/user/project/")
    assert result == ["src/a.py:10:hello"]


def test_strip_path_prefix_no_prefix_kept():
    output = ["other/path/file.py", "/home/user/file.py"]
    result = _strip_path_prefix(output, "/home/user")
    assert result == ["other/path/file.py", "file.py"]


def test_strip_path_prefix_backslash():
    output = ["C:\\project\\src\\a.py:10:hello"]
    result = _strip_path_prefix(output, "C:\\project")
    assert result == ["src\\a.py:10:hello"]


def test_strip_path_prefix_preserves_non_matching_lines():
    output = ["--", "match line", "--"]
    result = _strip_path_prefix(output, "/no/match")
    assert result == ["--", "match line", "--"]


# ---------------------------------------------------------------------------
# Params model
# ---------------------------------------------------------------------------


def test_params_defaults():
    p = Params(pattern="test")
    assert p.path == "."
    assert p.glob is None
    assert p.output_mode == "files_with_matches"
    assert p.before_context is None
    assert p.after_context is None
    assert p.context is None
    assert p.line_number is True
    assert p.ignore_case is False
    assert p.type is None
    assert p.head_limit == 250
    assert p.offset == 0
    assert p.multiline is False
    assert p.include_ignored is False


def test_params_head_limit_zero():
    p = Params(pattern="test", head_limit=0)
    assert p.head_limit == 0


def test_params_invalid_head_limit():
    with pytest.raises(ValueError):
        Params(pattern="test", head_limit=-1)


def test_params_invalid_offset():
    with pytest.raises(ValueError):
        Params(pattern="test", offset=-1)


# ---------------------------------------------------------------------------
# Integration-style tests via Grep class mocking rg subprocess
# ---------------------------------------------------------------------------


class FakeProcess:
    """Fake asyncio.subprocess.Process for testing Grep.__call__."""

    def __init__(self, stdout_data: bytes, stderr_data: bytes, returncode: int = 0):
        self._stdout = stdout_data
        self._stderr = stderr_data
        self._returncode = returncode
        self.stdout = asyncio.StreamReader()
        self.stdout.feed_data(stdout_data)
        self.stdout.feed_eof()
        self.stderr = asyncio.StreamReader()
        self.stderr.feed_data(stderr_data)
        self.stderr.feed_eof()

    async def wait(self):
        return self._returncode

    @property
    def returncode(self):
        return self._returncode

    def terminate(self):
        pass

    def kill(self):
        pass


@pytest.mark.asyncio
async def test_grep_call_files_with_matches(monkeypatch, tmp_path):
    from kimi_cli.tools.file.grep_local import Grep

    test_file = tmp_path / "a.py"
    test_file.write_text("hello\n")

    fake_rg_path = "/fake/rg"
    monkeypatch.setattr(
        "kimi_cli.tools.file.grep_local._ensure_rg_path", AsyncMock(return_value=fake_rg_path)
    )

    async def fake_create_subprocess_exec(*args, **kwargs):
        out = f"{tmp_path / 'a.py'}\n".encode()
        return FakeProcess(out, b"", returncode=0)

    monkeypatch.setattr(
        "asyncio.create_subprocess_exec", fake_create_subprocess_exec
    )

    tool = Grep()
    result = await tool(Params(pattern="hello", path=str(tmp_path), output_mode="files_with_matches"))
    assert not result.is_error
    assert "a.py" in result.output


@pytest.mark.asyncio
async def test_grep_call_no_matches(monkeypatch, tmp_path):
    from kimi_cli.tools.file.grep_local import Grep

    fake_rg_path = "/fake/rg"
    monkeypatch.setattr(
        "kimi_cli.tools.file.grep_local._ensure_rg_path", AsyncMock(return_value=fake_rg_path)
    )

    async def fake_create_subprocess_exec(*args, **kwargs):
        return FakeProcess(b"", b"", returncode=1)

    monkeypatch.setattr(
        "asyncio.create_subprocess_exec", fake_create_subprocess_exec
    )

    tool = Grep()
    result = await tool(Params(pattern="nomatch", path=str(tmp_path), output_mode="files_with_matches"))
    assert not result.is_error
    assert result.output == ""
    assert "No matches found" in result.message


@pytest.mark.asyncio
async def test_grep_call_rg_error(monkeypatch, tmp_path):
    from kimi_cli.tools.file.grep_local import Grep

    fake_rg_path = "/fake/rg"
    monkeypatch.setattr(
        "kimi_cli.tools.file.grep_local._ensure_rg_path", AsyncMock(return_value=fake_rg_path)
    )

    async def fake_create_subprocess_exec(*args, **kwargs):
        return FakeProcess(b"", b"bad regex", returncode=2)

    monkeypatch.setattr(
        "asyncio.create_subprocess_exec", fake_create_subprocess_exec
    )

    tool = Grep()
    result = await tool(Params(pattern="[bad", path=str(tmp_path), output_mode="files_with_matches"))
    assert result.is_error
    assert "Failed to grep" in result.message


@pytest.mark.asyncio
async def test_grep_call_eagain_retries(monkeypatch, tmp_path):
    from kimi_cli.tools.file.grep_local import Grep

    fake_rg_path = "/fake/rg"
    monkeypatch.setattr(
        "kimi_cli.tools.file.grep_local._ensure_rg_path", AsyncMock(return_value=fake_rg_path)
    )

    call_count = 0

    async def fake_create_subprocess_exec(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return FakeProcess(b"", b"os error 11", returncode=2)
        return FakeProcess(b"found\n", b"", returncode=0)

    monkeypatch.setattr(
        "asyncio.create_subprocess_exec", fake_create_subprocess_exec
    )

    tool = Grep()
    result = await tool(Params(pattern="found", path=str(tmp_path), output_mode="files_with_matches"))
    assert not result.is_error
    assert call_count == 2


@pytest.mark.asyncio
async def test_grep_call_count_matches_summary(monkeypatch, tmp_path):
    from kimi_cli.tools.file.grep_local import Grep

    fake_rg_path = "/fake/rg"
    monkeypatch.setattr(
        "kimi_cli.tools.file.grep_local._ensure_rg_path", AsyncMock(return_value=fake_rg_path)
    )

    async def fake_create_subprocess_exec(*args, **kwargs):
        out = b"a.py:3\nb.py:5\n"
        return FakeProcess(out, b"", returncode=0)

    monkeypatch.setattr(
        "asyncio.create_subprocess_exec", fake_create_subprocess_exec
    )

    tool = Grep()
    result = await tool(Params(pattern="hello", path=str(tmp_path), output_mode="count_matches"))
    assert not result.is_error
    assert "Found 8 total occurrences across 2 files" in result.message


@pytest.mark.asyncio
async def test_grep_call_content_with_line_numbers(monkeypatch, tmp_path):
    from kimi_cli.tools.file.grep_local import Grep

    fake_rg_path = "/fake/rg"
    monkeypatch.setattr(
        "kimi_cli.tools.file.grep_local._ensure_rg_path", AsyncMock(return_value=fake_rg_path)
    )

    async def fake_create_subprocess_exec(*args, **kwargs):
        out = b"a.py:1:hello world\n"
        return FakeProcess(out, b"", returncode=0)

    monkeypatch.setattr(
        "asyncio.create_subprocess_exec", fake_create_subprocess_exec
    )

    tool = Grep()
    result = await tool(Params(pattern="hello", path=str(tmp_path), output_mode="content"))
    assert not result.is_error
    assert "hello world" in result.output


@pytest.mark.asyncio
async def test_grep_call_timeout_with_partial_results(monkeypatch, tmp_path):
    from kimi_cli.tools.file.grep_local import Grep

    fake_rg_path = "/fake/rg"
    monkeypatch.setattr(
        "kimi_cli.tools.file.grep_local._ensure_rg_path", AsyncMock(return_value=fake_rg_path)
    )

    class SlowFakeProcess:
        def __init__(self):
            self.stdout = asyncio.StreamReader()
            self.stderr = asyncio.StreamReader()
            self._returncode = None

        async def wait(self):
            # Simulate hanging until killed/terminated
            while self._returncode is None:
                await asyncio.sleep(0.01)
            return self._returncode

        @property
        def returncode(self):
            return self._returncode

        def terminate(self):
            self._returncode = -1

        def kill(self):
            self._returncode = -1

    async def fake_create_subprocess_exec(*args, **kwargs):
        proc = SlowFakeProcess()
        proc.stdout.feed_data(b"partial result\n")
        # Don't feed_eof so stream hangs until timeout
        return proc

    monkeypatch.setattr(
        "asyncio.create_subprocess_exec", fake_create_subprocess_exec
    )
    # Reduce timeout for test speed
    monkeypatch.setattr("kimi_cli.tools.file.grep_local.RG_TIMEOUT", 0.1)

    tool = Grep()
    result = await tool(Params(pattern="partial", path=str(tmp_path), output_mode="files_with_matches"))
    assert not result.is_error
    assert "partial result" in result.output
    assert "timed out" in result.message.lower()


@pytest.mark.asyncio
async def test_grep_call_timeout_no_partial_results(monkeypatch, tmp_path):
    from kimi_cli.tools.file.grep_local import Grep

    fake_rg_path = "/fake/rg"
    monkeypatch.setattr(
        "kimi_cli.tools.file.grep_local._ensure_rg_path", AsyncMock(return_value=fake_rg_path)
    )

    class SlowFakeProcess:
        def __init__(self):
            self.stdout = asyncio.StreamReader()
            self.stderr = asyncio.StreamReader()
            self._returncode = None

        async def wait(self):
            # Simulate hanging until killed/terminated
            while self._returncode is None:
                await asyncio.sleep(0.01)
            return self._returncode

        @property
        def returncode(self):
            return self._returncode

        def terminate(self):
            self._returncode = -1

        def kill(self):
            self._returncode = -1

    async def fake_create_subprocess_exec(*args, **kwargs):
        proc = SlowFakeProcess()
        # No data fed
        return proc

    monkeypatch.setattr(
        "asyncio.create_subprocess_exec", fake_create_subprocess_exec
    )
    monkeypatch.setattr("kimi_cli.tools.file.grep_local.RG_TIMEOUT", 0.1)

    tool = Grep()
    result = await tool(Params(pattern="nothing", path=str(tmp_path), output_mode="files_with_matches"))
    assert result.is_error
    assert "timed out" in result.message.lower()


@pytest.mark.asyncio
async def test_grep_call_buffer_truncated(monkeypatch, tmp_path):
    from kimi_cli.tools.file.grep_local import Grep

    fake_rg_path = "/fake/rg"
    monkeypatch.setattr(
        "kimi_cli.tools.file.grep_local._ensure_rg_path", AsyncMock(return_value=fake_rg_path)
    )

    async def fake_create_subprocess_exec(*args, **kwargs):
        # Feed data larger than RG_MAX_BUFFER
        huge = b"x" * (RG_MAX_BUFFER + 1000)
        return FakeProcess(huge, b"", returncode=0)

    monkeypatch.setattr(
        "asyncio.create_subprocess_exec", fake_create_subprocess_exec
    )

    tool = Grep()
    result = await tool(Params(pattern="x", path=str(tmp_path), output_mode="content"))
    assert not result.is_error
    assert "buffer limit" in result.message.lower() or "truncated" in result.message.lower()


@pytest.mark.asyncio
async def test_grep_call_offset_pagination(monkeypatch, tmp_path):
    from kimi_cli.tools.file.grep_local import Grep

    fake_rg_path = "/fake/rg"
    monkeypatch.setattr(
        "kimi_cli.tools.file.grep_local._ensure_rg_path", AsyncMock(return_value=fake_rg_path)
    )

    async def fake_create_subprocess_exec(*args, **kwargs):
        out = b"\n".join(f"line{i}".encode() for i in range(10)) + b"\n"
        return FakeProcess(out, b"", returncode=0)

    monkeypatch.setattr(
        "asyncio.create_subprocess_exec", fake_create_subprocess_exec
    )

    tool = Grep()
    result = await tool(
        Params(pattern="line", path=str(tmp_path), output_mode="files_with_matches", offset=3, head_limit=3)
    )
    assert not result.is_error
    assert isinstance(result.output, str)
    lines = [x for x in result.output.split("\n") if x.strip()]
    assert len(lines) == 3
    assert "line3" in result.output
    assert "line0" not in result.output
    assert "Use offset=6" in result.message


@pytest.mark.asyncio
async def test_grep_call_sensitive_file_filtering(monkeypatch, tmp_path):
    from kimi_cli.tools.file.grep_local import Grep

    fake_rg_path = "/fake/rg"
    monkeypatch.setattr(
        "kimi_cli.tools.file.grep_local._ensure_rg_path", AsyncMock(return_value=fake_rg_path)
    )

    async def fake_create_subprocess_exec(*args, **kwargs):
        out = b"a.py\n.env\nb.py\n"
        return FakeProcess(out, b"", returncode=0)

    monkeypatch.setattr(
        "asyncio.create_subprocess_exec", fake_create_subprocess_exec
    )

    tool = Grep()
    result = await tool(Params(pattern="secret", path=str(tmp_path), output_mode="files_with_matches"))
    assert not result.is_error
    assert "a.py" in result.output
    assert "b.py" in result.output
    assert ".env" not in result.output
    assert "sensitive" in result.message.lower()


@pytest.mark.asyncio
async def test_grep_call_exception_handling(monkeypatch, tmp_path):
    from kimi_cli.tools.file.grep_local import Grep

    monkeypatch.setattr(
        "kimi_cli.tools.file.grep_local._ensure_rg_path",
        AsyncMock(side_effect=RuntimeError("boom")),
    )

    tool = Grep()
    result = await tool(Params(pattern="hello", path=str(tmp_path), output_mode="files_with_matches"))
    assert result.is_error
    assert "Failed to grep" in result.message
    assert "boom" in result.message
