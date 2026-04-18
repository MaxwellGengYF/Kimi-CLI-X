"""run tool for executing a process from a path."""
import anyio
import asyncio
from pathlib import Path

from kimi_agent_sdk import CallableTool2, ToolError, ToolOk, ToolReturnValue
from pydantic import BaseModel, Field
from my_tools.common import _maybe_export_output_async, _export_to_temp_file_async, ProcessTask


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
    run_in_background: bool = Field(
        default=False,
        description="Run in an independent background process. Returns immediately with a task_id. Use TaskList, TaskOutput, and TaskWait to manage. ALWAYS set to True with input detection use `Input` tool."
    )


class Run(CallableTool2):
    name: str = "Run"
    description: str = "Execute a program."
    params: type[RunParams] = RunParams

    async def __call__(self, params: RunParams) -> ToolReturnValue:
        # Handle background execution
        if params.run_in_background:
            return await self._run_in_background(params)
        output = ''
        try:
            # Run the command using async subprocess
            proc = await asyncio.create_subprocess_exec(
                params.path, *params.args,
                cwd=params.cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            # Wait for process with optional timeout
            if params.timeout is not None:
                stdout_data, stderr_data = await asyncio.wait_for(
                    proc.communicate(), timeout=params.timeout
                )
            else:
                stdout_data, stderr_data = await proc.communicate()

            # Decode output with utf-8 and replace errors
            stdout_text = stdout_data.decode('utf-8', errors='replace')
            stderr_text = stderr_data.decode('utf-8', errors='replace')

            # Combine stdout and stderr
            output_parts = []
            if stdout_text:
                output_parts.append(stdout_text)
            if stderr_text:
                output_parts.append(f"[stderr] {stderr_text}")
            output = "\n".join(output_parts)

            # Handle output export if needed
            if params.output_path:
                async with await anyio.open_file(params.output_path, 'w', encoding='utf-8', errors='replace') as f:
                    await f.write(output)
                output = f'saved to file `{params.output_path}`'
            # Return error if command failed
            if proc.returncode != 0:
                if output and not params.output_path:
                    temp_path, _ = await _export_to_temp_file_async(key=None, content=output, ext='.txt')
                    output = f'saved to file `{temp_path}`'
                return ToolError(
                    output=output,
                    message=f"Command failed with exit code {proc.returncode}",
                    brief="Command execution failed"
                )
            output = await _maybe_export_output_async(output)
            return ToolOk(output=output)

        except asyncio.TimeoutError:
            if output and not params.output_path:
                temp_path, _ = await _export_to_temp_file_async(key=None, content=output, ext='.txt')
                output = f'saved to file `{temp_path}`'

            return ToolError(
                output=output,
                message=f"Command timed out after {params.timeout} seconds",
                brief="Command execution timeout"
            )
        except Exception as exc:
            # Clean up
            if output and not params.output_path:
                temp_path, _ = await _export_to_temp_file_async(key=None, content=output, ext='.txt')
                output = f'saved to file `{temp_path}`'

            return ToolError(
                output=output,
                message=str(exc),
                brief="Failed to run process",
            )

    async def _run_in_background(self, params: RunParams) -> ToolReturnValue:
        """Run a process in the background and register it as a background task.

        Args:
            params: The run parameters.

        Returns:
            ToolOk with task_id on success, ToolError on failure.
        """
        try:
            task = ProcessTask(params.path, params.args, params.cwd)
            task_id = task.start("run", Path(params.path).stem)

            # Return success with task_id
            return ToolOk(
                output=f"Process started in background.\nTask ID: {task_id}\n\nUse 'TaskList' to view all tasks, 'TaskOutput' to get output. 'TaskStop' to kill process., 'Input' to input to process"
            )

        except Exception as exc:
            return ToolError(
                output="",
                message=f"Failed to start background process: {str(exc)}",
                brief="Failed to start background task"
            )
