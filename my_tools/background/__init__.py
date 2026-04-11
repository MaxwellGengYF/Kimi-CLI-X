"""Background task management tools."""
from kimi_agent_sdk import CallableTool2, ToolError, ToolOk, ToolReturnValue
from pydantic import BaseModel, Field

from .utils import generate_task_id, remove_task_id, add_task, join_task, get_all_tasks


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


class TaskOutput(CallableTool2):
    """Get output from a background task."""
    name: str = "TaskOutput"
    description: str = "Get accumulated output from a background task."
    params: type[BaseModel] = TaskOutputParams

    async def __call__(self, params: TaskOutputParams) -> ToolReturnValue:
        """Return the output of a task_id."""
        try:
            tasks = get_all_tasks()
            if params.task_id not in tasks:
                return ToolError(
                    message=f"Task '{params.task_id}' not found",
                    output="",
                    brief=f"Task '{params.task_id}' not found"
                )
            
            stream = tasks[params.task_id]
            output = stream.pop_output()
            return ToolOk(output=output if output else "(no output)")
        except Exception as e:
            return ToolError(
                message=str(e),
                output="Failed to get task output",
                brief="Task output error"
            )


class TaskWaitParams(BaseModel):
    """Parameters for TaskWait."""
    task_id: str = Field(
        description="Task ID to wait for."
    )


class TaskWait(CallableTool2):
    """Wait for a background task to complete."""
    name: str = "TaskWait"
    description: str = "Wait for a background task to complete."
    params: type[BaseModel] = TaskWaitParams

    async def __call__(self, params: TaskWaitParams) -> ToolReturnValue:
        """Wait for a specific task_id."""
        try:
            # join_task returns True if task was found and joined, False otherwise
            success = join_task(params.task_id)
            if not success:
                return ToolError(
                    message=f"Task '{params.task_id}' not found",
                    output="",
                    brief=f"Task '{params.task_id}' not found"
                )
            
            return ToolOk(output=f"Task '{params.task_id}' completed.")
        except Exception as e:
            return ToolError(
                message=str(e),
                output="Failed to wait for task",
                brief="Task wait error"
            )


__all__ = [
    # Tool classes
    "TaskList",
    "TaskListParams",
    "TaskOutput",
    "TaskOutputParams",
    "TaskWait",
    "TaskWaitParams",
    # Utility functions
    "generate_task_id",
    "remove_task_id",
    "add_task",
    "join_task",
    "get_all_tasks",
]
