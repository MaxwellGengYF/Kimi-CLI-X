"""Input tool for sending input to a running process."""
import asyncio

from kimi_agent_sdk import CallableTool2, ToolError, ToolOk, ToolReturnValue
from pydantic import BaseModel, Field

from my_tools.file._utils import get_state, get_final_output


class InputParams(BaseModel):
    text: str = Field(
        description="The string to send to the process's stdin.",
    )


class Input(CallableTool2):
    name: str = "Input"
    description: str = "Send input to a running process."
    params: type[InputParams] = InputParams

    async def __call__(self, params: InputParams) -> ToolReturnValue:
        """Send input text to the running process's stdin."""
        state = get_state()

        if state.process is None:
            return ToolError(
                output="",
                message="No process is currently running. Use Run tool to start a process first.",
                brief="No active process",
            )

        if state.process.poll() is not None:
            return ToolError(
                output=get_final_output(),
                message=f"Process has already exited with return code: {state.process.returncode}",
                brief="Process not running",
            )

        try:
            # Ensure the input ends with a newline
            input_text = params.text
            if not input_text.endswith('\n'):
                input_text += '\n'

            state.process.stdin.write(input_text)
            state.process.stdin.flush()
            await asyncio.sleep(1.0)

            return ToolOk(
                output=get_final_output(),
                message=f"Input sent to process: {repr(params.text)}",
                brief="Input sent",
            )
        except Exception as exc:
            return ToolError(
                output=get_final_output(),
                message=f"Failed to send input: {str(exc)}",
                brief="Input failed",
            )
