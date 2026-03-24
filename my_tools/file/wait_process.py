"""WaitProcess tool for waiting for a running process to complete."""
import asyncio
import time

from kimi_agent_sdk import CallableTool2, ToolError, ToolOk, ToolReturnValue
from pydantic import BaseModel, Field

from my_tools.file._state import process, reader_thread
from my_tools.file._utils import get_final_output


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
        global process, reader_thread
        start_time = time.time()
        timeout = params.timeout if params.timeout is not None else 3
        timeout = min(timeout, 30)
        if process is None:
            return ToolError(
                output="",
                message="No process is currently running.",
                brief="No active process",
            )

        try:
            if timeout is not None:
                while True:
                    return_code = process.poll()
                    if return_code is not None:
                        reader_thread.join(timeout=1)
                        reader_thread = None
                        process = None
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
                return_code = process.wait()
                reader_thread.join(timeout=timeout)
                reader_thread = None
                process = None
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
