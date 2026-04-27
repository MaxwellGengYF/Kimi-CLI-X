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
        self._session_id = session.id

    async def __call__(self, params: TaskListParams) -> ToolReturnValue:
        """Return formatted info of all tasks."""
        try:
            tasks = get_all_tasks(self._session_id)
            if not tasks:
                return ToolOk(output="No background tasks running.")
            
            lines = []
            for task_id, stream in tasks.items():
                status = stream.is_started()
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
        default = True,
        description='block and wait task.'
    )
    timeout: int = Field(
        default=60,
        ge=1,
        le=300,
        description="Timeout in seconds."
    )
    output_path: str | None = Field(
        default=None,
        description="Output file path (optional)."
    )


class TaskOutput(CallableTool2):
    """Get output from a background task."""
    name: str = "TaskOutput"
    description: str = "Get background task output."
    params: type[BaseModel] = TaskOutputParams
    def __del__(self):
        session_id = getattr(self, '_session_id', None)
        if session_id is not None:
            discard_all_tasks(session_id)

    def __init__(self, session: Session):
        super().__init__()
        self._session_id = session.id

    async def __call__(self, params: TaskOutputParams) -> ToolReturnValue:
        """Return the output of a task_id."""
        try:
            tasks = get_all_tasks(self._session_id)
            stream: BackgroundStream | None = None
            stream = tasks.get(params.task_id)
            if stream is None:
                return ToolError(
                    message=f"Task '{params.task_id}' not found",
                    output="",
                    brief=f"Task '{params.task_id}' not found"
                )
            if params.block or params.timeout > 0:
                await asyncio.to_thread(stream.wait, params.timeout if params.timeout > 0 else None)
            task_alive = stream.thread_is_alive()
            output = stream.get_output() if task_alive else stream.pop_output()
            if not task_alive:
                remove_task_id(self._session_id, params.task_id)
            if params.output_path:
                from pathlib import Path
                import anyio
                path = Path(params.output_path)
                async with await anyio.open_file(path, 'w', encoding='utf-8') as f:
                    await f.write(output)
                output = f"{'Task is still running, ' if task_alive else ''}output exported to file `{path}`"
            elif output and task_alive and not stream.success():
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


class TaskStopParams(BaseModel):
    """Parameters for TaskStop tool."""
    task_id: str = Field(
        description="Task ID to stop and cancel."
    )


class TaskStop(CallableTool2):
    """Stop and cancel a background task."""
    name: str = "TaskStop"
    description: str = "Cancel a background task."
    params: type[BaseModel] = TaskStopParams

    def __init__(self, session: Session):
        super().__init__()
        self._session_id = session.id

    async def __call__(self, params: TaskStopParams) -> ToolReturnValue:
        """Stop and cancel the task with the given task_id."""
        try:
            tasks = get_all_tasks(self._session_id)
            if params.task_id not in tasks:
                return ToolError(
                    message=f"Task '{params.task_id}' not found",
                    output="",
                    brief=f"Task '{params.task_id}' not found"
                )
            
            stream = tasks.pop(params.task_id)
            stopped = stream.stop()
            remove_task_id(self._session_id, params.task_id)
            
            if stopped:
                return ToolOk(output=f"Task '{params.task_id}' has been stopped.")
            else:
                return ToolOk(output=f"Task '{params.task_id}' was not running or already stopped.")
        except Exception as e:
            return ToolError(
                message=str(e),
                output="Failed to stop task",
                brief="Task stop error"
            )


__all__ = [
    # Tool classes
    "TaskList",
    "TaskListParams",
    "TaskOutput",
    "TaskOutputParams",
    "TaskStop",
    "TaskStopParams",
    # Utility functions
    "generate_task_id",
    "remove_task_id",
    "add_task",
    "get_all_tasks",
]
