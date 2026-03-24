"""Run tool for executing a process from a path."""
import asyncio
import subprocess
import threading
import time

from kimi_agent_sdk import CallableTool2, ToolError, ToolOk, ToolReturnValue
from pydantic import BaseModel, Field

from my_tools.file._state import process, reader_thread, stdout_lines, output_queue
from my_tools.file._utils import get_final_output, _check_for_input_prompt, _read_streams_into_queue


class RunParams(BaseModel):
    path: str = Field(
        description="The path to the executable to run.",
    )
    args: list[str] = Field(
        default_factory=list,
        description="List of arguments to pass to the executable.",
    )
    cwd: str | None = Field(
        default=None,
        description="Working directory to run the process in. If not specified, uses the current directory.",
    )
    timeout: int | None = Field(
        default=120,
        description="Timeout in seconds. If not specified, no timeout is applied.",
    )
    detect_input: bool = Field(
        default=False,
        description="Enable Detect input mode, if process requires input, early return.",
    )


class Run(CallableTool2):
    name: str = "Run"
    description: str = "Run a process from a path."
    params: type[RunParams] = RunParams

    async def __call__(self, params: RunParams) -> ToolReturnValue:
        """Run a process with real-time output collection using thread-safe queue.

        Both stdout and stderr are collected into a single thread-safe queue using
        one reader thread for efficient output handling.
        """
        # Single thread-safe queue for collecting all output (both stdout and stderr)
        global reader_thread, process

        def unfinished():
            if process.poll() is not None:
                return False
            time.sleep(0.5)
            return process.poll() is None

        if process and unfinished() is None:
            return ToolError(
                output=get_final_output(),
                message='Process still running, use "WaitProcess" tool to wait, or use "KillProcess" to terminate.',
                brief="",
            )
        try:
            start_time = time.time()
            return_code = None
            global stdout_lines
            stdout_lines = []
            # Start the process
            process = subprocess.Popen(
                [params.path] + params.args,
                cwd=params.cwd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,  # Line buffered
                universal_newlines=True
            )
            # Start a single reader thread for both stdout and stderr
            streams = [(process.stdout, 'stdout')]
            reader_thread = threading.Thread(
                target=_read_streams_into_queue,
                args=(process, streams, output_queue),
                daemon=True
            )
            reader_thread.start()

            # Wait for process to complete with timeout

            # if params.input_text:
            #     if not params.input_text.endswith('\n'):
            #         params.input_text += '\n'
            #     process.stdin.write(params.input_text)
            #     process.stdin.flush()
            while return_code is None:
                # Check if process has finished
                return_code = process.poll()
                if return_code is not None:
                    break

                # Check timeout
                elapsed = time.time() - start_time
                if params.detect_input:
                    tex = get_output_text()
                    if _check_for_input_prompt(tex):
                        message = f"'Input' tool may used to input to process."
                        return ToolError(
                            output=get_final_output(tex),
                            message=message,
                            brief="",
                        )
                if params.timeout is not None and elapsed > params.timeout:
                    process.kill()
                    process.wait()
                    reader_thread.join(timeout=1)
                    reader_thread = None
                    process = None
                    output = get_final_output()
                    message = f"Process timed out after {params.timeout} seconds"
                    return ToolError(
                        output=output,
                        message=message,
                        brief="Process timed out",
                    )

                # Yield control to allow other async tasks to run
                await asyncio.sleep(0.05)

            # Collect all output from queue
            output = get_final_output()
            reader_thread.join(timeout=1)
            reader_thread = None
            process = None
            if return_code != 0:
                return ToolError(
                    output=output,
                    message=f"Process exited with non-zero return code: {return_code}",
                    brief="Process failed",
                )

            return ToolOk(output=output)

        except Exception as exc:
            # Clean up
            process = None
            reader_thread = None
            return ToolError(
                output=get_final_output(),
                message=str(exc),
                brief="Failed to run process",
            )
