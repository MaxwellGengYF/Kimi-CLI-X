"""run tool for executing a process from a path."""
import asyncio
import os
import queue
import subprocess
import threading
import time
from pathlib import Path

from kimi_agent_sdk import CallableTool2, ToolError, ToolOk, ToolReturnValue
from pydantic import BaseModel, Field
from my_tools.common import _maybe_export_output
from my_tools.background.utils import BackgroundStream, generate_task_id, add_task


class RunParams(BaseModel):
    path: str = Field(
        description="Executable path."
    )
    args: list[str] = Field(
        default_factory=list,
        description="Command arguments."
    )
    timeout: int | None = Field(
        default=120,
        description="Timeout in seconds (default: no timeout)."
    )
    cwd: str | None = Field(
        default=None,
        description="Working directory (default: current directory)."
    )
    output_path: str | None = Field(
        default=None,
        description="Output file path (optional)."
    )


class Run(CallableTool2):
    name: str = "Run"
    description: str = "Execute a program."
    params: type[RunParams] = RunParams

    async def __call__(self, params: RunParams) -> ToolReturnValue:
        output = ''
        try:
            # Run the command using subprocess.run
            result = subprocess.run(
                [params.path] + params.args,
                cwd=params.cwd,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                timeout=params.timeout
            )

            # Combine stdout and stderr
            output_parts = []
            if result.stdout:
                output_parts.append(result.stdout)
            if result.stderr:
                output_parts.append(f"[stderr] {result.stderr}")
            output = "\n".join(output_parts)

            # Handle output export if needed
            if params.output_path:
                Path(params.output_path).write_text(
                    output, encoding='utf-8', errors='replace')
                output = f'saved to {params.output_path}'
            else:
                output = _maybe_export_output(output)
            # Return error if command failed
            if result.returncode != 0:
                return ToolError(
                    output=output,
                    message=f"Command failed with exit code {result.returncode}",
                    brief="Command execution failed"
                )
            return ToolOk(output=output)

        except Exception as exc:
            # Clean up
            return ToolError(
                output=output,
                message=str(exc),
                brief="Failed to run process",
            )