"""Background task management tools."""
import asyncio

from kimi_agent_sdk import CallableTool2, ToolError, ToolOk, ToolReturnValue
from pydantic import BaseModel, Field
from kimi_cli.session import Session

from .utils import generate_task_id, remove_task_id, add_task, get_all_tasks, BackgroundStream, discard_all_tasks
from my_tools.common import _maybe_export_output_async, _export_to_temp_file_async


class TaskListParams(BaseModel):
    """Parameters for TaskList tool."""
    pass


class TaskList(CallableTool2):
    """List all background tasks."""
    name: str = "TaskList"
    description: str = "List background tasks."
    params: type[BaseModel] = TaskListParams

    def __init__(self, session: Session):
        super().__init__()
        self._session = session

    async def __call__(self, params: TaskListParams) -> ToolReturnValue:
        """Return formatted info of all tasks."""
        try:
            tasks = get_all_tasks(self._session)
            if not tasks:
                return ToolOk(output="No background tasks running.")

            lines = []
            for task_id, stream in tasks.items():
                status = await stream.is_started()
                if status:
                    lines.append(task_id)

            return ToolOk(output="\n".join(lines))
        except Exception as e:
            return ToolError(
                message=str(e),
                output="Failed to retrieve task list",
                brief="Task list error"
            )


class TaskOutputParams(BaseModel):
    """Parameters for TaskOutput."""
    task_id: str = Field(
        description="Task ID to get output from."
    )
    block: bool = Field(
        default=True,
        description='block and wait task.'
    )
    timeout: int = Field(
        default=60,
        ge=3,
        le=300,
        description="Timeout in seconds."
    )
    output_path: str | None = Field(
        default=None,
        description="Output file path (optional)."
    )
    kill: bool = Field(
        default=False,
        description="Force stop the process after timeout."
    )


class TaskOutput(CallableTool2):
    """Get output from a background task."""
    name: str = "TaskOutput"
    description: str = "Get background task output."
    params: type[BaseModel] = TaskOutputParams

    def __del__(self):
        session = getattr(self, '_session', None)
        if session is not None:
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(discard_all_tasks(session))
            except RuntimeError:
                pass

    def __init__(self, session: Session):
        super().__init__()
        self._session = session

    async def __call__(self, params: TaskOutputParams) -> ToolReturnValue:
        """Return the output of a task_id."""
        try:
            tasks = get_all_tasks(self._session)
            stream: BackgroundStream | None = None
            stream = tasks.get(params.task_id.strip())
            if stream is None:
                return ToolError(
                    message=f"Task '{params.task_id}' not found",
                    output="",
                    brief=f"Task '{params.task_id}' not found"
                )
            if params.block:
                await stream.wait(params.timeout)
            task_alive = await stream.thread_is_alive()
            if params.kill and task_alive:
                await stream.stop()
                task_alive = False
            output = await stream.get_output() if task_alive else await stream.pop_output()
            if not task_alive:
                remove_task_id(self._session, params.task_id)
            if params.output_path:
                from pathlib import Path
                import anyio
                path = Path(params.output_path)
                async with await anyio.open_file(path, 'w', encoding='utf-8') as f:
                    await f.write(output)
                output = f"{'Task is still running, ' if task_alive else ''}output exported to file `{path}`"
            elif output and task_alive and not await stream.success():
                temp_path, _ = await _export_to_temp_file_async(key=None, content=output, ext='.txt')
                output = f"Output exported to file `{temp_path}`"
            else:
                output = await _maybe_export_output_async(output)
            return ToolOk(output=output if output else "(no output)")
        except Exception as e:
            return ToolError(
                message=str(e),
                output="Failed to get task output",
                brief="Task output error"
            )


__all__ = [
    # Tool classes
    "TaskList",
    "TaskListParams",
    "TaskOutput",
    "TaskOutputParams",
    # Utility functions
    "generate_task_id",
    "remove_task_id",
    "add_task",
    "get_all_tasks",
]
