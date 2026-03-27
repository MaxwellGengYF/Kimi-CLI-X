"""Tests for my_tools.cpp module."""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

import pytest

# Skip tests if kimi_agent_sdk is not available
pytest.importorskip("kimi_agent_sdk")

from my_tools.cpp import (
    ClangdLSPClient,
    CppSyntaxCheck,
    Params,
    find_clangd,
    format_diagnostic,
    load_compile_commands,
)
from kimi_agent_sdk import ToolError, ToolOk


class TestParams:
    """Tests for Params Pydantic model."""

    def test_params_defaults(self):
        """Test Params with default values."""
        params = Params(file_path="test.cpp")
        assert params.file_path == "test.cpp"
        assert params.project_root == "."
        assert params.clangd_path == "clangd"
        assert params.verbose is False

    def test_params_custom_values(self):
        """Test Params with custom values."""
        params = Params(
            file_path="main.cpp",
            project_root="/project",
            clangd_path="/usr/bin/clangd",
            verbose=True,
        )
        assert params.file_path == "main.cpp"
        assert params.project_root == "/project"
        assert params.clangd_path == "/usr/bin/clangd"
        assert params.verbose is True


class TestFormatDiagnostic:
    """Tests for format_diagnostic function."""

    def test_format_error_diagnostic(self):
        """Test formatting an error diagnostic."""
        diag = {
            "range": {"start": {"line": 10, "character": 5}},
            "severity": 1,
            "message": "expected ';'",
            "code": "expected_semicolon",
            "source": "clang",
        }
        result = format_diagnostic(diag)
        assert "Error: expected ';'" in result
        assert "[expected_semicolon]" in result
        assert "at line 11, col 6" in result

    def test_format_warning_diagnostic(self):
        """Test formatting a warning diagnostic."""
        diag = {
            "range": {"start": {"line": 5, "character": 0}},
            "severity": 2,
            "message": "unused variable",
            "source": "clang",
        }
        result = format_diagnostic(diag)
        assert "Warning: unused variable" in result
        assert "at line 6, col 1" in result

    def test_format_info_diagnostic(self):
        """Test formatting an info diagnostic."""
        diag = {
            "range": {"start": {"line": 0, "character": 0}},
            "severity": 3,
            "message": "information message",
        }
        result = format_diagnostic(diag)
        assert "Info: information message" in result

    def test_format_hint_diagnostic(self):
        """Test formatting a hint diagnostic."""
        diag = {
            "range": {"start": {"line": 1, "character": 2}},
            "severity": 4,
            "message": "hint message",
        }
        result = format_diagnostic(diag)
        assert "Hint: hint message" in result

    def test_format_without_code(self):
        """Test formatting diagnostic without code."""
        diag = {
            "range": {"start": {"line": 0, "character": 0}},
            "severity": 1,
            "message": "syntax error",
        }
        result = format_diagnostic(diag)
        assert "Error: syntax error" in result
        assert "[" not in result  # No code should be present

    def test_format_default_severity(self):
        """Test formatting diagnostic with default severity (0)."""
        diag = {
            "range": {"start": {"line": 0, "character": 0}},
            "message": "some error",
        }
        result = format_diagnostic(diag)
        assert "Error: some error" in result


class TestLoadCompileCommands:
    """Tests for load_compile_commands function."""

    def test_find_in_vscode_dir(self, tmp_path):
        """Test finding compile_commands.json in .vscode directory."""
        vscode_dir = tmp_path / ".vscode"
        vscode_dir.mkdir()
        compile_commands = vscode_dir / "compile_commands.json"
        compile_commands.write_text("[]")

        result = load_compile_commands(str(tmp_path))
        assert result == str(vscode_dir)

    def test_find_in_build_dir(self, tmp_path):
        """Test finding compile_commands.json in build directory."""
        build_dir = tmp_path / "build"
        build_dir.mkdir()
        compile_commands = build_dir / "compile_commands.json"
        compile_commands.write_text("[]")

        result = load_compile_commands(str(tmp_path))
        assert result == str(build_dir)

    def test_vscode_takes_precedence(self, tmp_path):
        """Test that .vscode takes precedence over build directory."""
        vscode_dir = tmp_path / ".vscode"
        vscode_dir.mkdir()
        build_dir = tmp_path / "build"
        build_dir.mkdir()

        (vscode_dir / "compile_commands.json").write_text("[]")
        (build_dir / "compile_commands.json").write_text("[]")

        result = load_compile_commands(str(tmp_path))
        assert result == str(vscode_dir)

    def test_file_not_found(self, tmp_path):
        """Test FileNotFoundError when compile_commands.json doesn't exist."""
        with pytest.raises(FileNotFoundError) as exc_info:
            load_compile_commands(str(tmp_path))
        assert "Could not find compile_commands.json" in str(exc_info.value)


class TestFindClangd:
    """Tests for find_clangd function."""

    def test_explicit_path_exists(self, tmp_path):
        """Test when explicit clangd path exists."""
        clangd_path = tmp_path / "clangd"
        clangd_path.write_text("")

        result = find_clangd(str(clangd_path), str(tmp_path))
        assert result == str(clangd_path)

    def test_from_vscode_settings(self, tmp_path):
        """Test reading clangd path from .vscode/settings.json."""
        vscode_dir = tmp_path / ".vscode"
        vscode_dir.mkdir()
        settings_path = vscode_dir / "settings.json"
        custom_clangd = tmp_path / "custom_clangd"
        custom_clangd.write_text("")

        settings = {"clangd.path": str(custom_clangd)}
        settings_path.write_text(json.dumps(settings))

        result = find_clangd("clangd", str(tmp_path))
        assert result == str(custom_clangd.resolve())

    def test_from_vscode_settings_relative_path(self, tmp_path):
        """Test reading relative clangd path from .vscode/settings.json."""
        vscode_dir = tmp_path / ".vscode"
        vscode_dir.mkdir()
        settings_path = vscode_dir / "settings.json"
        custom_clangd = tmp_path / "bin" / "clangd"
        custom_clangd.parent.mkdir()
        custom_clangd.write_text("")

        settings = {"clangd.path": "bin/clangd"}
        settings_path.write_text(json.dumps(settings))

        result = find_clangd("clangd", str(tmp_path))
        assert result == str(custom_clangd.resolve())

    def test_from_vscode_settings_invalid_json(self, tmp_path):
        """Test handling invalid JSON in settings.json."""
        vscode_dir = tmp_path / ".vscode"
        vscode_dir.mkdir()
        settings_path = vscode_dir / "settings.json"
        settings_path.write_text("invalid json")

        result = find_clangd("clangd", str(tmp_path))
        assert result == "clangd"

    def test_fallback_to_where_command(self, tmp_path):
        """Test fallback to 'where' command when path doesn't exist."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="C:\\Program Files\\clangd.exe\n"
            )
            result = find_clangd("clangd", str(tmp_path))
            assert "clangd.exe" in result

    def test_fallback_to_where_command_failure(self, tmp_path):
        """Test fallback when 'where' command fails."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="")
            result = find_clangd("clangd", str(tmp_path))
            assert result == "clangd"


class TestClangdLSPClient:
    """Tests for ClangdLSPClient class."""

    def test_init(self):
        """Test client initialization."""
        client = ClangdLSPClient("clangd", "/project")
        assert client.clangd_path == "clangd"
        assert client.compile_commands_dir == "/project"
        assert client.process is None
        assert client.request_id == 0
        assert client.diagnostics == []

    @patch("subprocess.Popen")
    def test_start(self, mock_popen):
        """Test starting clangd process."""
        mock_popen.return_value = MagicMock()
        client = ClangdLSPClient("clangd", "/project")
        client.start()

        mock_popen.assert_called_once()
        args = mock_popen.call_args[0][0]
        assert "clangd" in args[0]
        assert any("--compile-commands-dir=/project" in arg for arg in args)

    @patch("subprocess.Popen")
    def test_stop(self, mock_popen):
        """Test stopping clangd process."""
        mock_process = MagicMock()
        mock_process.wait = MagicMock()
        mock_popen.return_value = mock_process

        client = ClangdLSPClient("clangd", "/project")
        client.start()
        client.stop()

        mock_process.wait.assert_called_once_with(timeout=2)

    @patch("subprocess.Popen")
    def test_stop_kill_on_timeout(self, mock_popen):
        """Test killing clangd process when shutdown times out."""
        mock_process = MagicMock()
        mock_process.wait = MagicMock(side_effect=subprocess.TimeoutExpired("cmd", 2))
        mock_process.kill = MagicMock()
        mock_popen.return_value = mock_process

        client = ClangdLSPClient("clangd", "/project")
        client.start()
        client.stop()

        mock_process.kill.assert_called_once()

    def test_send_request_increments_id(self):
        """Test that request ID increments with each request."""
        client = ClangdLSPClient("clangd", "/project")
        client.process = MagicMock()
        client.process.stdin = MagicMock()

        id1 = client._send_request("test", {})
        id2 = client._send_request("test", {})
        id3 = client._send_request("test", {})

        assert id1 == 1
        assert id2 == 2
        assert id3 == 3

    def test_read_message(self):
        """Test reading message from clangd."""
        client = ClangdLSPClient("clangd", "/project")
        mock_stdout = MagicMock()

        # Simulate reading header and body
        header = b"Content-Length: 26\r\n\r\n"
        body = b'{"jsonrpc":"2.0","id":1}'
        mock_stdout.read = MagicMock(side_effect=list(header + body) + [b''])

        client.process = MagicMock()
        client.process.stdout = mock_stdout

        result = client._read_message()
        assert result == {"jsonrpc": "2.0", "id": 1}

    def test_read_message_empty(self):
        """Test reading empty message."""
        client = ClangdLSPClient("clangd", "/project")
        mock_stdout = MagicMock()
        mock_stdout.read = MagicMock(return_value=b"")

        client.process = MagicMock()
        client.process.stdout = mock_stdout

        result = client._read_message()
        assert result is None

    def test_format_diagnostic_integration(self):
        """Integration test for format_diagnostic with real data."""
        diag = {
            "range": {
                "start": {"line": 42, "character": 10},
                "end": {"line": 42, "character": 15}
            },
            "severity": 1,
            "code": "undeclared_var",
            "message": "use of undeclared identifier 'foo'",
            "source": "clang"
        }
        result = format_diagnostic(diag)
        assert "Error: use of undeclared identifier 'foo'" in result
        assert "[undeclared_var]" in result
        assert "at line 43, col 11" in result


class TestCppSyntaxCheck:
    """Tests for CppSyntaxCheck tool."""

    @pytest.fixture
    def tool(self):
        """Create a CppSyntaxCheck instance."""
        return CppSyntaxCheck()

    @pytest.fixture
    def temp_cpp_file(self, tmp_path):
        """Create a temporary C++ file."""
        cpp_file = tmp_path / "test.cpp"
        cpp_file.write_text("int main() { return 0; }")
        return cpp_file

    @pytest.mark.asyncio
    async def test_file_not_found(self, tool):
        """Test error when file doesn't exist."""
        params = Params(file_path="/nonexistent/file.cpp")
        result = await tool(params)

        assert isinstance(result, ToolError)
        assert "File not found" in result.brief

    @pytest.mark.asyncio
    async def test_clangd_not_found(self, tool, tmp_path):
        """Test error when clangd is not found."""
        cpp_file = tmp_path / "test.cpp"
        cpp_file.write_text("int main() {}")

        with patch.object(Path, "exists", return_value=False):
            params = Params(file_path=str(cpp_file), clangd_path="/nonexistent/clangd")
            result = await tool(params)

        assert isinstance(result, ToolError)
        assert "clangd not found" in result.brief

    @pytest.mark.asyncio
    async def test_successful_check_no_errors(self, tool, tmp_path):
        """Test successful check with no errors."""
        cpp_file = tmp_path / "test.cpp"
        cpp_file.write_text("int main() { return 0; }")

        # Create compile_commands.json
        build_dir = tmp_path / "build"
        build_dir.mkdir()
        compile_commands = build_dir / "compile_commands.json"
        compile_commands.write_text(json.dumps([
            {
                "directory": str(tmp_path),
                "file": "test.cpp",
                "arguments": ["g++", "-c", "test.cpp"]
            }
        ]))

        mock_client = MagicMock()
        mock_client.get_diagnostics = MagicMock(return_value=[])

        with patch("my_tools.cpp.ClangdLSPClient", return_value=mock_client):
            with patch("my_tools.cpp.find_clangd", return_value="clangd"):
                params = Params(file_path=str(cpp_file), project_root=str(tmp_path))
                result = await tool(params)

        assert isinstance(result, ToolOk)

    @pytest.mark.asyncio
    async def test_check_with_errors(self, tool, tmp_path):
        """Test check that finds errors."""
        cpp_file = tmp_path / "test.cpp"
        cpp_file.write_text("int main() { return undefined_var; }")

        # Create compile_commands.json
        build_dir = tmp_path / "build"
        build_dir.mkdir()
        compile_commands = build_dir / "compile_commands.json"
        compile_commands.write_text(json.dumps([
            {
                "directory": str(tmp_path),
                "file": "test.cpp",
                "arguments": ["g++", "-c", "test.cpp"]
            }
        ]))

        mock_client = MagicMock()
        mock_client.get_diagnostics = MagicMock(return_value=[
            {
                "range": {"start": {"line": 0, "character": 20}},
                "severity": 1,
                "message": "use of undeclared identifier 'undefined_var'"
            }
        ])

        with patch("my_tools.cpp.ClangdLSPClient", return_value=mock_client):
            with patch("my_tools.cpp.find_clangd", return_value="clangd"):
                params = Params(file_path=str(cpp_file), project_root=str(tmp_path))
                result = await tool(params)

        assert isinstance(result, ToolError)
        assert "1 error(s)" in result.brief

    @pytest.mark.asyncio
    async def test_check_with_warnings_only(self, tool, tmp_path):
        """Test check that finds only warnings."""
        cpp_file = tmp_path / "test.cpp"
        cpp_file.write_text("int main() { int x; }")

        # Create compile_commands.json
        build_dir = tmp_path / "build"
        build_dir.mkdir()
        compile_commands = build_dir / "compile_commands.json"
        compile_commands.write_text(json.dumps([
            {
                "directory": str(tmp_path),
                "file": "test.cpp",
                "arguments": ["g++", "-c", "test.cpp"]
            }
        ]))

        mock_client = MagicMock()
        mock_client.get_diagnostics = MagicMock(return_value=[
            {
                "range": {"start": {"line": 0, "character": 14}},
                "severity": 2,
                "message": "unused variable 'x'"
            }
        ])

        with patch("my_tools.cpp.ClangdLSPClient", return_value=mock_client):
            with patch("my_tools.cpp.find_clangd", return_value="clangd"):
                params = Params(file_path=str(cpp_file), project_root=str(tmp_path))
                result = await tool(params)

        # Warnings only should return ToolOk
        assert isinstance(result, ToolOk)
        assert "1 warning(s)" in result.output

    @pytest.mark.asyncio
    async def test_file_not_in_compile_commands(self, tool, tmp_path):
        """Test error when file is not in compile_commands.json."""
        cpp_file = tmp_path / "missing.cpp"
        cpp_file.write_text("int main() {}")

        # Create compile_commands.json without the file
        build_dir = tmp_path / "build"
        build_dir.mkdir()
        compile_commands = build_dir / "compile_commands.json"
        compile_commands.write_text(json.dumps([
            {
                "directory": str(tmp_path),
                "file": "other.cpp",
                "arguments": ["g++", "-c", "other.cpp"]
            }
        ]))

        params = Params(file_path=str(cpp_file), project_root=str(tmp_path))
        result = await tool(params)

        assert isinstance(result, ToolError)
        assert "File not in compile_commands.json" in result.brief

    @pytest.mark.asyncio
    async def test_invalid_compile_commands_json(self, tool, tmp_path):
        """Test error with invalid compile_commands.json."""
        cpp_file = tmp_path / "test.cpp"
        cpp_file.write_text("int main() {}")

        build_dir = tmp_path / "build"
        build_dir.mkdir()
        compile_commands = build_dir / "compile_commands.json"
        compile_commands.write_text("invalid json")

        params = Params(file_path=str(cpp_file), project_root=str(tmp_path))
        result = await tool(params)

        assert isinstance(result, ToolError)
        assert "compile_commands.json decode error" in result.message

    @pytest.mark.asyncio
    async def test_exception_during_check(self, tool, tmp_path):
        """Test handling exception during check."""
        cpp_file = tmp_path / "test.cpp"
        cpp_file.write_text("int main() {}")

        build_dir = tmp_path / "build"
        build_dir.mkdir()
        compile_commands = build_dir / "compile_commands.json"
        compile_commands.write_text(json.dumps([]))

        mock_client = MagicMock()
        mock_client.start = MagicMock(side_effect=Exception("Connection failed"))

        with patch("my_tools.cpp.ClangdLSPClient", return_value=mock_client):
            with patch("my_tools.cpp.find_clangd", return_value="clangd"):
                params = Params(file_path=str(cpp_file), project_root=str(tmp_path))
                result = await tool(params)

        assert isinstance(result, ToolError)
        assert "Failed to check C++ syntax" in result.brief

    @pytest.mark.asyncio
    async def test_verbose_mode(self, tool, tmp_path):
        """Test verbose mode includes compile arguments."""
        cpp_file = tmp_path / "test.cpp"
        cpp_file.write_text("int main() { return 0; }")

        build_dir = tmp_path / "build"
        build_dir.mkdir()
        compile_commands = build_dir / "compile_commands.json"
        compile_commands.write_text(json.dumps([
            {
                "directory": str(tmp_path),
                "file": "test.cpp",
                "arguments": ["g++", "-std=c++17", "-c", "test.cpp"]
            }
        ]))

        mock_client = MagicMock()
        mock_client.get_diagnostics = MagicMock(return_value=[])

        with patch("my_tools.cpp.ClangdLSPClient", return_value=mock_client):
            with patch("my_tools.cpp.find_clangd", return_value="clangd"):
                params = Params(
                    file_path=str(cpp_file),
                    project_root=str(tmp_path),
                    verbose=True
                )
                result = await tool(params)

        assert isinstance(result, ToolOk)


class TestIntegration:
    """Integration tests that test multiple components together."""

    def test_full_workflow_mocked(self, tmp_path):
        """Test the full workflow with mocked clangd."""
        cpp_file = tmp_path / "test.cpp"
        cpp_file.write_text("int main() { return 0; }")

        build_dir = tmp_path / "build"
        build_dir.mkdir()
        compile_commands = build_dir / "compile_commands.json"
        compile_commands.write_text(json.dumps([
            {
                "directory": str(tmp_path),
                "file": "test.cpp",
                "arguments": ["g++", "-c", "test.cpp"]
            }
        ]))

        # Test load_compile_commands
        commands_dir = load_compile_commands(str(tmp_path))
        assert commands_dir == str(build_dir)

        # Test find_clangd
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="clangd\n")
            clangd = find_clangd("clangd", str(tmp_path))
            assert "clangd" in clangd

    def test_format_diagnostics_batch(self):
        """Test formatting multiple diagnostics."""
        diagnostics = [
            {
                "range": {"start": {"line": 0, "character": 0}},
                "severity": 1,
                "message": "error 1",
                "code": "E001"
            },
            {
                "range": {"start": {"line": 1, "character": 5}},
                "severity": 2,
                "message": "warning 1",
                "code": "W001"
            },
            {
                "range": {"start": {"line": 2, "character": 10}},
                "severity": 3,
                "message": "info 1",
            }
        ]

        formatted = [format_diagnostic(d) for d in diagnostics]

        assert "Error: error 1 [E001]" in formatted[0]
        assert "at line 1, col 1" in formatted[0]

        assert "Warning: warning 1 [W001]" in formatted[1]
        assert "at line 2, col 6" in formatted[1]

        assert "Info: info 1" in formatted[2]
        assert "at line 3, col 11" in formatted[2]
