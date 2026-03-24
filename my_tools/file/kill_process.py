"""KillProcess tool for terminating the currently running process."""
from kimi_agent_sdk import CallableTool2, ToolError, ToolOk, ToolReturnValue
from pydantic import BaseModel

from my_tools.file._state import process, reader_thread
from my_tools.file._utils import get_final_output


class KillParams(BaseModel):
    pass


class KillProcess(CallableTool2):
    name: str = "KillProcess"
    description: str = "Kill the currently running process."
    params: type[KillParams] = KillParams

    async def __call__(self, params: KillParams) -> ToolReturnValue:
        """Kill the running process."""
        global process, reader_thread

        if process is None:
            return ToolError(
                output="",
                message="No process is currently running.",
                brief="No active process",
            )

        try:
            process.kill()
            process.wait()
            reader_thread.join(timeout=1)
            reader_thread = None
            process = None
            output = get_final_output()
            return ToolOk(
                output=output,
                message="Process killed successfully",
                brief="Process killed",
            )
        except Exception as exc:
            return ToolError(
                output=get_final_output(),
                message=f"Failed to kill process: {str(exc)}",
                brief="Kill failed",
            )
