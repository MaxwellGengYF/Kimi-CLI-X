"""Input tool for sending input to a running process."""
import asyncio

from kimi_agent_sdk import CallableTool2, ToolError, ToolOk, ToolReturnValue
from pydantic import BaseModel, Field
from my_tools.background.utils import get_all_tasks

class InputParams(BaseModel):
    task_id: str = Field(
        description="Task ID to input to."
    )
    text: str = Field(
        description="Text to send to the running process's stdin."
    )


class Input(CallableTool2):
    name: str = "Input"
    description: str = "Send text input to a running process's stdin."
    params: type[InputParams] = InputParams

    async def __call__(self, params: InputParams) -> ToolReturnValue:
        tasks = get_all_tasks()
        task = tasks.get(params.task_id)
        if task is None:
            return ToolError(
                output="",
                message=f"Task not found: {params.task_id}",
                brief="Task not found"
            )
        if not task.input(params.text):
            return ToolError(
                output="",
                message="Failed to send input to process",
                brief="Input failed"
            )
        return ToolOk(output=f"Input sent to task {params.task_id}")