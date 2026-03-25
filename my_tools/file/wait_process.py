"""WaitProcess tool for waiting for a running process to complete."""
import asyncio
import time

from kimi_agent_sdk import CallableTool2, ToolError, ToolOk, ToolReturnValue
from pydantic import BaseModel, Field

from my_tools.file._utils import get_state, get_final_output


class WaitParams(BaseModel):
    timeout: int | None = Field(
        default=3,
        description="Timeout in seconds. If not specified, no timeout is applied. Should be less than 30",
    )


class WaitProcess(CallableTool2):
    name: str = "WaitProcess"
    description: str = "Wait for the global variable 'process' to finish. Timeout should be less than 30"
    params: type[WaitParams] = WaitParams

    async def __call__(self, params: WaitParams) -> ToolReturnValue:
        """Wait for the running process to complete."""
        state = get_state()
        start_time = time.time()
        timeout = params.timeout if params.timeout is not None else 3
        timeout = min(timeout, 30)
        if state.process is None:
            return ToolError(
                output="",
                message="No process is currently running.",
                brief="No active process",
            )

        try:
            if timeout is not None:
                while True:
                    return_code = state.process.poll()
                    if return_code is not None:
                        if state.reader_thread:
                            state.reader_thread.join(timeout=1)
                        state.set_reader_thread(None)
                        state.set_process(None)
                        output = get_final_output()
                        if return_code != 0:
                            return ToolError(
                                output=output,
                                message=f"Process exited with non-zero return code: {return_code}",
                                brief="Process failed",
                            )
                        else:
                            return ToolOk(output=output)
                    elapsed = time.time() - start_time
                    if elapsed > timeout:
                        message = f"Process is still working... "
                        return ToolError(
                            output=get_final_output(),
                            message=message,
                            brief="timeout",
                        )
                    await asyncio.sleep(0.05)
            else:
                return_code = state.process.wait()
                if state.reader_thread:
                    state.reader_thread.join(timeout=timeout)
                state.set_reader_thread(None)
                state.set_process(None)
                output = get_final_output()
                if return_code != 0:
                    return ToolError(
                        output=output,
                        message=f"Process exited with non-zero return code: {return_code}",
                        brief="Process failed",
                    )
                return ToolOk(output=output)

        except Exception as exc:
            return ToolError(
                output=get_final_output(),
                message=f"Failed to wait for process: {str(exc)}",
                brief="Wait failed",
            )
