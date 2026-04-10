"""kill tool for terminating the currently running process."""
from kimi_agent_sdk import CallableTool2, ToolError, ToolOk, ToolReturnValue
from pydantic import BaseModel

from my_tools.file._utils import get_state, get_final_output


class KillParams(BaseModel):
    pass


class Kill(CallableTool2):
    name: str = "Kill"
    description: str = "Terminate the active process."
    params: type[KillParams] = KillParams

    async def __call__(self, params: KillParams) -> ToolReturnValue:
        """Kill the running process."""
        state = get_state()

        if state.process is None:
            return ToolError(
                output="",
                message="No process is currently running.",
                brief="No active process",
            )

        try:
            state.process.kill()
            state.process.wait()
            state.join(timeout=1)
            state.set_process(None)
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
