"""run tool for executing a process from a path."""
import anyio
import asyncio
from pathlib import Path

from kimi_agent_sdk import CallableTool2, ToolError, ToolOk, ToolReturnValue
from pydantic import BaseModel, Field
from kimi_cli.session import Session
from my_tools.common import _maybe_export_output_async, _export_to_temp_file_async, ProcessTask


class RunParams(BaseModel):
    path: str = Field(
        description="Executable path."
    )
    args: list[str] = Field(
        default_factory=list,
        description="Command arguments."
    )
    timeout: int = Field(
        default=10,
        ge=3,
        le=180,
        description="Timeout in seconds."
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
        description="Run in an independent background process. Returns immediately with a task_id. Use TaskList, TaskOutput. ALWAYS set to True with input detection use `Input` tool."
    )


class Run(CallableTool2[RunParams]):
    name: str = "Run"
    description: str = "Run an executable."
    params: type[RunParams] = RunParams

    def __init__(self, session: Session):
        import os
        os.environ['PYTHONIOENCODING'] = 'utf-8'
        super().__init__()
        self._session = session

    async def __call__(self, params: RunParams) -> ToolReturnValue:
        import sys
        # check if using python
        if params.path == 'python':
            params.path = sys.executable
        # Handle background execution
        if params.run_in_background:
            return await self._run_in_background(params)

        task = ProcessTask(params.path, params.args, params.cwd)
        task_id = task.start(self._session, "run", Path(params.path).stem)

        # Wait for completion with timeout (allow a small buffer for cleanup)
        wait_timeout = params.timeout
        await anyio.to_thread.run_sync(task.wait, wait_timeout)
        
        if task.thread_is_alive():
            return ToolError(
                output=f'Running in background. task_id: `{task_id}`. use `TaskOutput` or `TaskList` tool',
                message="Process timeout",
                brief="Timeout"
            )
        # Clean up foreground task registration
        from my_tools.background.utils import remove_task_id
        remove_task_id(self._session, task_id)

        # Get output
        output = task.stream.pop_output() if task.stream else ""

        # Handle output export if needed
        if params.output_path:
            async with await anyio.open_file(params.output_path, 'w', encoding='utf-8', errors='replace') as f:
                await f.write(output)
            output = f'saved to file `{params.output_path}`'
        
        # Check success
        success = task.stream.success() if task.stream else False


        if not success:
            if output and not params.output_path:
                temp_path, _ = await _export_to_temp_file_async(key=None, content=output, ext='.txt')
                output = f'saved to file `{temp_path}`'
            return ToolError(
                output=output,
                message="Command execution failed",
                brief="Command execution failed"
            )

        output = await _maybe_export_output_async(output)
        return ToolOk(output=output)

    async def _run_in_background(self, params: RunParams) -> ToolReturnValue:
        """Run a process in the background and register it as a background task.

        Args:
            params: The run parameters.

        Returns:
            ToolOk with task_id on success, ToolError on failure.
        """
        try:
            task = ProcessTask(params.path, params.args, params.cwd)
            task_id = task.start(self._session, "run", Path(params.path).stem)

            # Return success with task_id
            return ToolOk(
                output=f"Process started in background.\nTask ID: {task_id}\n\nUse 'TaskList' to view all tasks, 'TaskOutput' to get output, 'Input' to input to process"
            )

        except Exception as exc:
            return ToolError(
                output="",
                message=f"Failed to start background process: {str(exc)}",
                brief="Failed to start background task"
            )
