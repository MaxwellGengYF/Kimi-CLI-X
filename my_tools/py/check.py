import asyncio
import subprocess
import sys
import os
from my_tools.common import _maybe_export_output
from kimi_agent_sdk import CallableTool2, ToolError, ToolOk, ToolReturnValue
from pydantic import BaseModel, Field
from pathlib import Path


class Params(BaseModel):
    code: str = Field(
        description="The Python code to analyze.",
    )


class PySyntaxCheck(CallableTool2):
    name: str = "PySyntaxCheck"
    description: str = "Check Python code syntax and style using ruff, returns errors, warnings, and hints"
    params: type[Params] = Params

    async def __call__(self, params: Params) -> ToolReturnValue:
        # Try to import ruff, install if not available
        try:
            import ruff
        except ImportError:
            try:
                subprocess.check_call([sys.executable, "-m", "pip", "install", "ruff"])
                import ruff
            except Exception as e:
                return ToolError(
                    message=f"Failed to install ruff: {str(e)}",
                    brief="Ruff installation failed"
                )

        # Write code to a temp file for ruff to analyze
        temp_file = None
        try:
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
                f.write(params.code)
                temp_file = f.name

            # Run ruff check to get errors and warnings
            result = await asyncio.to_thread(
                subprocess.run,
                [sys.executable, "-m", "ruff", "check", temp_file, "--output-format=json"],
                capture_output=True,
                text=True
            )

            import json
            errors = []
            warnings = []
            hints = []

            if result.stdout:
                try:
                    diagnostics = json.loads(result.stdout)
                    for diag in diagnostics:
                        message = diag.get('message', '')
                        code = diag.get('code', '')
                        severity = diag.get('severity', 'error')
                        location = f"Line {diag.get('location', {}).get('row', '?')}, Col {diag.get('location', {}).get('column', '?')}"
                        
                        item = f"[{code}] {message} ({location})"
                        
                        if severity == 'error':
                            errors.append(item)
                        elif severity == 'warning':
                            warnings.append(item)
                        else:
                            hints.append(item)
                except json.JSONDecodeError:
                    pass

            # Also check for formatting issues as hints
            fmt_result = await asyncio.to_thread(
                subprocess.run,
                [sys.executable, "-m", "ruff", "format", temp_file, "--check", "--output-format=json"],
                capture_output=True,
                text=True
            )

            if fmt_result.stdout:
                try:
                    fmt_diagnostics = json.loads(fmt_result.stdout)
                    for diag in fmt_diagnostics:
                        message = diag.get('message', 'Formatting issue')
                        location = f"Line {diag.get('start_location', {}).get('row', '?')}"
                        hints.append(f"[format] {message} ({location})")
                except json.JSONDecodeError:
                    pass

            output_parts = []
            if errors:
                output_parts.append("Errors:\n" + "\n".join(f"  - {e}" for e in errors))
            if warnings:
                output_parts.append("Warnings:\n" + "\n".join(f"  - {w}" for w in warnings))
            if hints:
                output_parts.append("Hints:\n" + "\n".join(f"  - {h}" for h in hints))

            if not output_parts:
                output = "No issues found. Code looks good!"
            else:
                output = "\n\n".join(output_parts)

            output = _maybe_export_output(output)
            return ToolOk(output=output)

        except Exception as e:
            return ToolError(message=str(e), brief="PySyntaxCheck error")
        finally:
            if temp_file and os.path.exists(temp_file):
                os.unlink(temp_file)
