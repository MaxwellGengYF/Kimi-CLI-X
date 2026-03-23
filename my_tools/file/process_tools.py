import os
import subprocess
import asyncio
import time
import threading
import queue

from kimi_agent_sdk import CallableTool2, ToolError, ToolOk, ToolReturnValue
from pydantic import BaseModel, Field
from my_tools.common import _maybe_export_output
from typing import Optional


# Keywords that indicate the process is waiting for user input
INPUT_KEYWORDS = [
    "input", "choose", "enter",
    "prompt", "write", "provide",
    "confirm", "yes/no", "y/n"
]


def _check_for_input_prompt(text: str) -> bool:
    """Check if the text contains keywords indicating the process is waiting for input."""
    text_lower = text.lower()
    for keyword in INPUT_KEYWORDS:
        if keyword in text_lower:
            return True
    return False


stdout_lines = []
output_queue: queue.Queue = queue.Queue()
reader_thread: Optional[threading.Thread] = None
process: Optional[subprocess.Popen] = None
timeout = None
start_time = None


def get_output_text():
    try:
        while True:
            data = output_queue.get_nowait()
            stdout_lines.append(data)
    except queue.Empty:
        pass

    return "".join(stdout_lines)


def get_final_output(dest, output_text=None):
    if output_text == None:
        output_text = get_output_text()
    if dest:
        with open(dest, 'w', encoding='utf-8') as f:
            f.write(output_text)
        output_text = f"Output saved to {dest}"
    return _maybe_export_output(output_text)


def _read_streams_into_queue(process: subprocess.Popen, streams, q: queue.Queue):
    """Read from multiple streams and put data into a single queue until stop_event is set.

    Args:
        streams: List of (stream, label) tuples where label is 'stdout' or 'stderr'
        q: Thread-safe queue for collecting output
        stop_event: Event to signal the thread to stop
    """
    import sys

    try:
        while process.poll() is None:
            any_data = False

            for stream, label in streams:
                if stream.closed:
                    continue

                try:
                    data = stream.read(1)
                    if data:
                        q.put(data)
                        any_data = True
                except (IOError, OSError, ValueError):
                    # Stream might be closed
                    continue
                except BlockingIOError:
                    # No data available (non-blocking mode)
                    continue

            # If no data was read, sleep briefly
            if not any_data:
                time.sleep(0.01)

    except Exception as e:
        import agent_utils
        agent_utils.print_error(str(e))


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
    dest: str | None = Field(
        default=None,
        description="The destination path to save the output. If provided, output will be saved to this file.",
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
        global reader_thread, process, timeout, start_time
        if process and process.poll() is None:
            if params.path == '#wait':
                if params.timeout is not None:
                    while True:
                        return_code = process.poll()
                        if return_code is not None:
                            reader_thread.join(timeout=1)
                            reader_thread = None
                            process = None
                            output = get_final_output(params.dest)
                            if return_code != 0:
                                return ToolError(
                                    output=output,
                                    message=f"Process exited with non-zero return code: {return_code}",
                                    brief="Process failed",
                                )
                            else:
                                return ToolOk(output=output)
                        elapsed = time.time() - start_time
                        if elapsed > params.timeout:
                            process.kill()
                            process.wait()
                            reader_thread.join(timeout=1)
                            reader_thread = None
                            process = None
                            output = get_final_output(params.dest)
                            message = f"Process timed out after {params.timeout} seconds"
                            return ToolError(
                                output=output,
                                message=message,
                                brief="Process timed out",
                            )
                else:
                    process.wait()
                    reader_thread.join(timeout=1)
                    reader_thread = None
                    process = None
                    output = get_final_output(params.dest)
                    if return_code != 0:
                        return ToolError(
                            output=output,
                            message=f"Process exited with non-zero return code: {return_code}",
                            brief="Process failed",
                        )

                    return ToolOk(output=output)

            elif params.path == '#kill':
                process.kill()
                process.wait()
                reader_thread.join(timeout=1)
                reader_thread = None
                process = None
                output = get_final_output(params.dest)
                message = f"Process killed"
                return ToolOk(
                    output=output,
                    message=message,
                    brief="Process killed")

            return ToolError(
                output='',
                message='Process still running, set path="#wait" to wait, or set path="#kill" to kill process',
                brief="",
            )
        elif params.path.startswith('#'):
            return ToolError(
                output='',
                message='Invalid command',
                brief="")
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
            timeout = params.timeout
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
                            output=get_final_output(params.dest, tex),
                            message=message,
                            brief="",
                        )
                if params.timeout is not None and elapsed > params.timeout:
                    process.kill()
                    process.wait()
                    reader_thread.join(timeout=1)
                    reader_thread = None
                    process = None
                    output = get_final_output(params.dest)
                    message = f"Process timed out after {params.timeout} seconds"
                    return ToolError(
                        output=output,
                        message=message,
                        brief="Process timed out",
                    )

                # Yield control to allow other async tasks to run
                await asyncio.sleep(0.05)

            # Collect all output from queue
            output = get_final_output(params.dest)
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
                output="",
                message=str(exc),
                brief="Failed to run process",
            )


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
        global process

        if process is None:
            return ToolError(
                output="",
                message="No process is currently running. Use Run tool to start a process first.",
                brief="No active process",
            )

        if process.poll() is not None:
            return ToolError(
                output='',
                message=f"Process has already exited with return code: {process.returncode}",
                brief="Process not running",
            )

        try:
            # Ensure the input ends with a newline
            input_text = params.text
            if not input_text.endswith('\n'):
                input_text += '\n'

            process.stdin.write(input_text)
            process.stdin.flush()

            return ToolOk(
                output='',
                message=f"Input sent to process: {repr(params.text)}",
                brief="Input sent",
            )
        except Exception as exc:
            return ToolError(
                output='',
                message=f"Failed to send input: {str(exc)}",
                brief="Input failed",
            )
