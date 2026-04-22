"""Python syntax/type check tool using mypy."""

import asyncio
import json
import sys
from pathlib import Path

from kimi_agent_sdk import CallableTool2, ToolError, ToolOk, ToolReturnValue
from pydantic import BaseModel, Field

from my_tools.common import _maybe_export_output_async


class Params(BaseModel):
    """Parameters for Python syntax/type check."""

    file_path: str = Field(
        description="Path to the Python file to validate."
    )
    project_root: str = Field(
        default=".",
        description="Root directory of the project for mypy config discovery (default: current directory)."
    )
    verbose: bool = Field(
        default=False,
        description="Include verbose mypy output."
    )


class MypyCheck(CallableTool2):
    """Check Python syntax and types using mypy."""

    name: str = "MypyCheck"
    description: str = (
        "Validate Python file syntax and types using mypy. "
        "Checks for type errors, syntax issues, and static analysis problems."
    )
    params: type[Params] = Params

    async def __call__(self, params: Params) -> ToolReturnValue:
        file_path = Path(params.file_path)

        if not await asyncio.to_thread(file_path.exists):
            return ToolError(
                output="",
                message=f"File not found: {file_path}",
                brief="File not found",
            )

        ext = file_path.suffix.lower()
        if ext != ".py":
            msg = f"Unsupported file extension: {ext}. Only .py files are supported."
            return ToolError(
                output=msg,
                message=msg,
                brief="Unsupported file type",
            )

        project_root = Path(params.project_root).resolve()

        # Build mypy command
        cmd = [
            sys.executable,
            "-m",
            "mypy",
            str(file_path),
            "--output",
            "json",
        ]
        if params.verbose:
            cmd.append("--verbose")

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(project_root),
            )
            stdout, stderr = await proc.communicate()
        except Exception as e:
            return ToolError(
                output="",
                message=f"Failed to run mypy: {e}",
                brief="mypy execution failed",
            )

        # Parse mypy JSON output
        diagnostics = []
        for line in stdout.decode("utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                diag = json.loads(line)
            except json.JSONDecodeError:
                continue

            diagnostics.append({
                "file": diag.get("file", ""),
                "line": diag.get("line", 0),
                "col": diag.get("column", 0),
                "severity": diag.get("severity", "error"),
                "message": diag.get("message", ""),
                "code": diag.get("code") or "",
            })

        # Also capture stderr if any
        stderr_lines = [
            stripped
            for line in stderr.decode("utf-8", errors="replace").splitlines()
            if (stripped := line.strip()) and not stripped.startswith("LOG:")
        ]

        if not diagnostics and proc.returncode == 0:
            output = f"No issues found in {file_path.name}."
            if params.verbose:
                output += f"\nProject root: {project_root}"
            output = await _maybe_export_output_async(output)
            return ToolOk(output=output)

        # Format diagnostics
        lines = []
        errors = 0
        warnings = 0
        notes = 0

        for diag in diagnostics:
            severity = diag["severity"]
            msg = f"{severity.capitalize()}: {diag['message']}"
            if diag.get("code"):
                msg += f" [{diag['code']}]"
            loc = f"line {diag['line']}, col {diag['col']}"
            msg += f" at {loc}"
            lines.append(msg)

            if severity == "error":
                errors += 1
            elif severity == "warning":
                warnings += 1
            else:
                notes += 1

        if stderr_lines:
            lines.append("")
            lines.append("Additional output:")
            for sl in stderr_lines:
                lines.append(f"  {sl}")

        summary = f"\n{'-' * 60}\nTotal: {errors} error(s), {warnings} warning(s), {notes} note(s)"
        output = "\n".join(lines) + summary

        if params.verbose:
            output += f"\nProject root: {project_root}"

        output = await _maybe_export_output_async(output)
        if errors == 0:
            return ToolOk(output=output)
            
        return ToolError(
            output=output,
            message=f"",
            brief=f"Python syntax check failed",
        )
