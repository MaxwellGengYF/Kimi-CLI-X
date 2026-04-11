"""Background task management tools."""
import asyncio

from kimi_agent_sdk import CallableTool2, ToolError, ToolOk, ToolReturnValue
from pydantic import BaseModel, Field

from .utils import generate_task_id, remove_task_id, add_task, get_all_tasks, BackgroundStream
from my_tools.common import _maybe_export_output

class TaskListParams(BaseModel):
    """Parameters for TaskList tool."""
    pass


class TaskList(CallableTool2):
    """List all background tasks."""
    name: str = "TaskList"
    description: str = "List background tasks with their status."
    params: type[BaseModel] = TaskListParams

    async def __call__(self, params: TaskListParams) -> ToolReturnValue:
        """Return formatted info of all tasks."""
        try:
            tasks = get_all_tasks()
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
        description='block and wait task.'
    )
    wait_time: int = Field(
        default=0,
        description="Time to wait before capturing output in seconds."
    )


class TaskOutput(CallableTool2):
    """Get output from a background task."""
    name: str = "TaskOutput"
    description: str = "Get accumulated output from a background task."
    params: type[BaseModel] = TaskOutputParams

    async def __call__(self, params: TaskOutputParams) -> ToolReturnValue:
        """Return the output of a task_id."""
        try:
            tasks = get_all_tasks()
            stream: BackgroundStream | None = None
            if params.block:
                stream = tasks.pop(params.task_id)
            else:
                stream = tasks.get(params.task_id)
            if stream is None:
                return ToolError(
                    message=f"Task '{params.task_id}' not found",
                    output="",
                    brief=f"Task '{params.task_id}' not found"
                )
            if params.block:
                stream.wait()
            else:
                # Wait before capturing output
                if params.wait_time > 0:
                    await asyncio.sleep(params.wait_time)
            output = _maybe_export_output(stream.pop_output())
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
    description: str = "Stop and cancel a background task by its task ID."
    params: type[BaseModel] = TaskStopParams

    async def __call__(self, params: TaskStopParams) -> ToolReturnValue:
        """Stop and cancel the task with the given task_id."""
        try:
            tasks = get_all_tasks()
            if params.task_id not in tasks:
                return ToolError(
                    message=f"Task '{params.task_id}' not found",
                    output="",
                    brief=f"Task '{params.task_id}' not found"
                )
            
            stream = tasks.pop(params.task_id)
            stopped = stream.stop()
            remove_task_id(params.task_id)
            
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
