from kimi_agent_sdk import CallableTool2, ToolError, ToolOk, ToolReturnValue
from pydantic import BaseModel, Field

import json
import os
import subprocess
import time
from pathlib import Path
from my_tools.common import _maybe_export_output


class Params(BaseModel):
    file_path: str = Field(
        description="Path to the C++ file to validate."
    )
    project_root: str = Field(
        default=".",
        description="Root directory of the project (default: current directory)."
    )
    clangd_path: str = Field(
        default="clangd",
        description="Path to the clangd executable (default: 'clangd')."
    )
    verbose: bool = Field(
        default=False,
        description="Include verbose compilation arguments in output."
    )


class ClangdLSPClient:
    """Minimal LSP client for clangd to get diagnostics."""

    def __init__(self, clangd_path: str, compile_commands_dir: str):
        self.clangd_path = clangd_path
        self.compile_commands_dir = compile_commands_dir
        self.process = None
        self.request_id = 0
        self.diagnostics = []

    def start(self):
        """Start clangd process."""
        cmd = [
            self.clangd_path,
            "--compile-commands-dir=" + self.compile_commands_dir,
            "--log=error",
            "--clang-tidy=true",
            "--completion-style=bundled",
            "--pch-storage=memory",
            "--cross-file-rename=false",
        ]

        self.process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def stop(self):
        """Stop clangd process."""
        if self.process:
            try:
                self._send_request("shutdown", {})
                self._send_notification("exit", {})
                self.process.wait(timeout=2)
            except Exception:
                self.process.kill()
            finally:
                self.process = None

    def _send_message(self, message: bytes):
        """Send a message to clangd."""
        header = f"Content-Length: {len(message)}\r\n\r\n".encode()
        self.process.stdin.write(header + message)
        self.process.stdin.flush()

    def _send_request(self, method: str, params: dict) -> int:
        """Send a request to clangd."""
        self.request_id += 1
        message = {
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": method,
            "params": params,
        }
        self._send_message(json.dumps(message).encode())
        return self.request_id

    def _send_notification(self, method: str, params: dict):
        """Send a notification to clangd."""
        message = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }
        self._send_message(json.dumps(message).encode())

    def _read_message(self) -> dict:
        """Read a message from clangd."""
        # Read header
        header = b""
        while True:
            byte = self.process.stdout.read(1)
            if not byte:
                return None
            header += byte
            if header.endswith(b"\r\n\r\n"):
                break

        # Parse Content-Length
        content_length = 0
        for line in header.decode().split("\r\n"):
            if line.startswith("Content-Length:"):
                content_length = int(line.split(":")[1].strip())
                break

        if content_length == 0:
            return None

        # Read body
        body = self.process.stdout.read(content_length)
        return json.loads(body.decode())

    def initialize(self):
        """Initialize the LSP connection."""
        root_uri = Path(self.compile_commands_dir).resolve().as_uri()
        self._send_request(
            "initialize",
            {
                "processId": os.getpid(),
                "rootUri": root_uri,
                "capabilities": {},
                "workspaceFolders": [
                    {"uri": root_uri, "name": Path(
                        self.compile_commands_dir).name}
                ],
            },
        )

        # Wait for initialize response
        while True:
            msg = self._read_message()
            if msg and "id" in msg and msg.get("result"):
                break

        self._send_notification("initialized", {})

    def open_document(self, file_path: str, content: str):
        """Open a document in clangd."""
        uri = Path(file_path).resolve().as_uri()
        self._send_notification(
            "textDocument/didOpen",
            {
                "textDocument": {
                    "uri": uri,
                    "languageId": "cpp",
                    "version": 1,
                    "text": content,
                }
            },
        )

    def get_diagnostics(self, file_path: str, timeout: float = 10.0) -> list:
        """Get diagnostics for a file using textDocument/diagnostic."""
        uri = Path(file_path).resolve().as_uri()
        req_id = self._send_request(
            "textDocument/diagnostic",
            {
                "textDocument": {"uri": uri},
                "identifier": "syntax-check",
            },
        )

        start_time = time.time()
        while time.time() - start_time < timeout:
            msg = self._read_message()
            if msg is None:
                break

            # Check for diagnostic response
            if msg.get("id") == req_id and "result" in msg:
                result = msg["result"]
                if isinstance(result, dict) and "items" in result:
                    return result["items"]
                return []

            # Check for publishDiagnostics notification
            if msg.get("method") == "textDocument/publishDiagnostics":
                params = msg.get("params", {})
                if params.get("uri") == uri:
                    return params.get("diagnostics", [])

        return []


def load_compile_commands(project_root: str = ".") -> str:
    """Find and validate compile_commands.json location."""
    vscode_dir = Path(project_root) / ".vscode"
    compile_commands = vscode_dir / "compile_commands.json"

    if compile_commands.exists():
        return str(vscode_dir)

    # Try build directory
    build_dir = Path(project_root) / "build"
    compile_commands = build_dir / "compile_commands.json"
    if compile_commands.exists():
        return str(build_dir)

    raise FileNotFoundError(
        "Could not find compile_commands.json in .vscode or build directory"
    )


def format_diagnostic(diag: dict) -> str:
    """Format a diagnostic message."""
    range_info = diag.get("range", {})
    start = range_info.get("start", {})
    line = start.get("line", 0) + 1  # LSP uses 0-based indexing
    character = start.get("character", 0) + 1

    severity = diag.get("severity", 1)
    severity_str = ["Error", "Error", "Warning", "Info", "Hint"][
        min(severity, 4)
    ]

    message = diag.get("message", "")
    code = diag.get("code", "")
    source = diag.get("source", "clangd")

    result = f"{severity_str}: {message}"
    if code:
        result += f" [{code}]"
    result += f" at line {line}, col {character}"

    return result


def find_clangd(clangd_path: str, project_root: str) -> str:
    """Find clangd executable."""
    # Read clangd.path from .vscode/settings.json if not explicitly provided
    if clangd_path == "clangd":
        settings_path = Path(project_root) / ".vscode" / "settings.json"
        if settings_path.exists():
            try:
                with open(settings_path, "r", encoding="utf-8") as f:
                    settings = json.load(f)
                config_clangd_path = settings.get("clangd.path")
                if config_clangd_path:
                    # Resolve relative path from project root
                    resolved_path = Path(project_root) / config_clangd_path
                    if resolved_path.exists():
                        clangd_path = str(resolved_path.resolve())
                    else:
                        # Try as absolute path
                        config_path = Path(config_clangd_path)
                        if config_path.exists():
                            clangd_path = str(config_path.resolve())
            except (json.JSONDecodeError, IOError):
                pass  # Fall back to default behavior

    if not Path(clangd_path).exists():
        # Try to find in PATH
        try:
            result = subprocess.run(
                ["where", clangd_path],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                clangd_path = result.stdout.strip().split("\n")[0].strip()
        except Exception:
            pass

    return clangd_path


class CppSyntaxCheck(CallableTool2):
    name: str = "CppSyntaxCheck"
    description: str = "Validate C++ file syntax using clangd."
    params: type[Params] = Params

    async def __call__(self, params: Params) -> ToolReturnValue:
        file_path = Path(params.file_path).resolve()

        if not file_path.exists():
            return ToolError(
                output="",
                message=f"File not found: {file_path}",
                brief="File not found",
            )

        # Find compile_commands.json
        file_args = ''
        try:
            compile_commands_dir = load_compile_commands(params.project_root)
        except FileNotFoundError:
            compile_commands_dir = params.project_root
        else:
            # Check if file_path is in compile_commands.json
            compile_commands_path = Path(
                compile_commands_dir) / "compile_commands.json"
            if not compile_commands_path.exists():
                output = ""
                if params.verbose:
                    output = _maybe_export_output(f'Compile arguments:\n' + file_args)
                return ToolError(
                    output=output,
                    message=f"compile_commands.json not found.",
                    brief=f"This tool is invalid.",
                )

            try:
                with open(compile_commands_path, "r", encoding="utf-8") as f:
                    compile_commands = json.load(f)
                file_maps = dict()
                for entry in compile_commands:
                    name = entry.get("file", None).replace(
                        '\\', '/').replace('//', '/')
                    args = entry.get('arguments', [])
                    args = '\n'.join(args)
                    if not name:
                        continue
                    file_maps[name] = args
                # Check if params.file_path matches any entry
                rel_path = str(file_path.relative_to(
                    Path(params.project_root).resolve()))
                file_path_str = str(rel_path).replace(
                    '\\', '/').replace('//', '/')
                file_args = file_maps.get(file_path_str)
                if file_args is None:
                    # Try with relative path
                    try:
                        file_args = file_maps.get(rel_path)
                        if file_args is None:
                            return ToolError(
                                output="",
                                message=f"File not found in compile_commands.json: {params.file_path}",
                                brief=f"File not in compile_commands.json. Please ensure the file is included in the build system.",
                            )
                    except ValueError:
                        return ToolError(
                            output="",
                            message=f"File not found in compile_commands.json: {params.file_path}",
                            brief=f"File not in compile_commands.json. Please ensure the file is included in the build system.",
                        )
            except (json.JSONDecodeError, IOError) as e:
                output = ""
                if params.verbose:
                    output = _maybe_export_output(f'Compile arguments:\n{file_args}\nError: {e}')
                return ToolError(
                    output=output,
                    message=f"compile_commands.json decode error: {e}",
                    brief=f"This tool is invalid.",
                )

        # Find clangd
        clangd_path = find_clangd(params.clangd_path, params.project_root)
        if not Path(clangd_path).exists():
            output = ''
            if params.verbose:
                output = _maybe_export_output(f'Compile arguments:\n' + file_args)
            return ToolError(
                output=output,
                message=f"clangd not found: {clangd_path}",
                brief="clangd not found. Please install clangd or provide correct path.",
            )

        # Read file content
        try:
            content = file_path.read_text(encoding="utf-8")
        except Exception as e:
            output = ''
            if params.verbose:
                output = _maybe_export_output(f'Compile arguments:\n' + file_args)
            return ToolError(
                output=output,
                message=str(e),
                brief="Failed to read file",
            )

        # Create and use clangd client
        client = ClangdLSPClient(clangd_path, compile_commands_dir)

        try:
            client.start()
            client.initialize()
            client.open_document(str(file_path), content)

            # Wait for clangd to process
            time.sleep(0.5)

            diagnostics = client.get_diagnostics(str(file_path))

            if not diagnostics:
                output = 'No issues found!'
                if params.verbose:
                    output += f'Compile arguments:\n' + file_args
                output = _maybe_export_output(output)
                return ToolOk(output=output)

            errors = 0
            warnings = 0
            formatted_diagnostics = []

            for diag in diagnostics:
                formatted_diagnostics.append(format_diagnostic(diag))
                severity = diag.get("severity", 1)
                if severity <= 1:
                    errors += 1
                elif severity == 2:
                    warnings += 1

            summary = f"\n{'-' * 60}\nTotal: {errors} error(s), {warnings} warning(s)"
            output = "\n".join(formatted_diagnostics) + summary

            if errors > 0:
                if params.verbose:
                    output += f'Compile arguments:\n' + file_args
                output = _maybe_export_output(output)
                return ToolError(
                    output=output,
                    message=f"Found {errors} error(s), {warnings} warning(s)",
                    brief=f"C++ syntax errors: {errors} error(s), {warnings} warning(s)",
                )
            else:
                if params.verbose:
                    output += f'Compile arguments:\n' + file_args
                output = _maybe_export_output(output)
                return ToolOk(output=output)

        except Exception as e:
            output = ''
            if params.verbose:
                output = f'Compile arguments:\n' + file_args
            output = _maybe_export_output(output)
            return ToolError(
                output=output,
                message=str(e),
                brief="Failed to check C++ syntax",
            )
        finally:
            client.stop()
