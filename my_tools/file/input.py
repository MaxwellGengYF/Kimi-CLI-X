"""Input tool for sending input to a running process."""
import asyncio

from kimi_agent_sdk import CallableTool2, ToolError, ToolOk, ToolReturnValue
from pydantic import BaseModel, Field

from my_tools.file._utils import get_state, get_final_output


class inputParams(BaseModel):
    text: str = Field(
        description="Text to send to the running process's stdin."
    )


class input(CallableTool2):
    name: str = "input"
    description: str = "Send text input to a running process's stdin."
    params: type[inputParams] = inputParams

    async def __call__(self, params: inputParams) -> ToolReturnValue:
        """Send input text to the running process's stdin."""
        state = get_state()

        if state.process is None:
            return ToolError(
                output="",
                message="No process is currently running. Use run tool to start a process first.",
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
            import time
            start_time = time.time()
            return_value = state.process.poll()
            while (time.time() - start_time) < 3.0 and return_value is None:
                time.sleep(0.05)
                return_value = state.process.poll()
            
            if return_value is None:
                return ToolOk(
                    output=get_final_output(),
                    message=f"Input sent to process: {repr(params.text)}, process still running...",
                    brief="Input sent",
                )
            else:
                if return_value == 0:
                    return ToolOk(
                        output=get_final_output(),
                        message=f"Input sent to process: {repr(params.text)}, process run success",
                        brief="Input sent",
                    )
                else:
                    return ToolError(
                        output=get_final_output(),
                        message=f"Input sent to process: {repr(params.text)}, process failed with {return_value}",
                        brief="Input sent, Run failed",
                    )
        except Exception as exc:
            return ToolError(
                output=get_final_output(),
                message=f"Failed to send input: {str(exc)}",
                brief="Input failed",
            )
