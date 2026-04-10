"""Run tool for executing a process from a path."""
import asyncio
import subprocess
import threading
import time

from kimi_agent_sdk import CallableTool2, ToolError, ToolOk, ToolReturnValue
from pydantic import BaseModel, Field
from my_tools.common import _maybe_export_output
from my_tools.file._utils import (
    get_state,
    get_final_output, get_output_text, _check_for_input_prompt, _read_streams_into_queue
)


class RunParams(BaseModel):
    path: str = Field(
        description="Executable path."
    )
    args: list[str] = Field(
        default_factory=list,
        description="Command arguments."
    )
    timeout: int | None = Field(
        default=120,
        description="Timeout in seconds (default: no timeout)."
    )
    cwd: str | None = Field(
        default=None,
        description="Working directory (default: current directory)."
    )
    output_path: str | None = Field(
        default=None,
        description="Output file path (optional)."
    )
    detect_input: bool = Field(
        default=False,
        description="Return early if process requires input."
    )


class Run(CallableTool2):
    name: str = "Run"
    description: str = "Execute a program."
    params: type[RunParams] = RunParams

    async def __call__(self, params: RunParams) -> ToolReturnValue:
        """Run a process with real-time output collection using thread-safe queue.

        Both stdout and stderr are collected into a single thread-safe queue using
        one reader thread for efficient output handling.
        """
        state = get_state()

        def unfinished():
            if state.process.poll() is not None:
                return False
            time.sleep(0.5)
            return state.process.poll() is None

        if state.process and unfinished():
            return ToolError(
                output=get_final_output(),
                message='Process still running, use "WaitProcess" tool to wait, or use "KillProcess" to terminate.',
                brief="",
            )
        try:
            start_time = time.time()
            return_code = None
            state.set_stdout_lines()
            # Start the process
            state.set_process(subprocess.Popen(
                [params.path] + params.args,
                cwd=params.cwd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8',
                errors='replace'
            ), params.detect_input)
            state.name = params.path
            state.output_path = params.output_path
            state.set_reader_threads([
                threading.Thread(
                target=_read_streams_into_queue,
                args=(state.process, state.process.stdout, state.output_queue, params.detect_input),
                daemon=True
            ),
                threading.Thread(
                target=_read_streams_into_queue,
                args=(state.process, state.process.stderr, state.output_queue, False),
                daemon=True
            )
            ])
            state.start()

            # Wait for process to complete with timeout

            # if params.input_text:
            #     if not params.input_text.endswith('\n'):
            #         params.input_text += '\n'
            #     state.process.stdin.write(params.input_text)
            #     state.process.stdin.flush()
            while return_code is None:
                # Check if process has finished
                return_code = state.process.poll()
                if return_code is not None:
                    break

                # Check timeout
                elapsed = time.time() - start_time
                if params.detect_input and (time.time() - state.last_write_time) > min(params.timeout, 3):
                    tex = get_output_text()
                    if _check_for_input_prompt(tex):
                        message = f"Process still running, 'Input' tool may used to input to process."
                        return ToolError(
                            output=get_final_output(),
                            message=message,
                            brief="",
                        )
                if params.timeout is not None and elapsed > params.timeout:
                    state.process.kill()
                    state.process.wait()
                    state.join(timeout=1)
                    state.set_process(None)
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
            state.join(timeout=1)
            state.set_process(None)
            if return_code != 0:
                return ToolError(
                    output=output,
                    message=f"Process exited with non-zero return code: {return_code}",
                    brief="Process failed",
                )

            return ToolOk(output=output)

        except Exception as exc:
            # Clean up
            state.set_process(None)
            return ToolError(
                output=get_final_output(),
                message=str(exc),
                brief="Failed to run process",
            )
