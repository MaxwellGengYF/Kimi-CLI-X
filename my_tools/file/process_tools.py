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
    "input", "choose", "enter", "select", "option",
    "prompt", "type", "write", "provide", "give",
    "confirm", "yes/no", "y/n", "press",
]


def _check_for_input_prompt(text: str) -> bool:
    """Check if the text contains keywords indicating the process is waiting for input."""
    text_lower = text.lower()
    for keyword in INPUT_KEYWORDS:
        if keyword in text_lower:
            return True
    return False


def _read_stream_into_queue(stream, q: queue.Queue, stop_event: threading.Event):
    """Read from a stream and put data into a queue until stop_event is set."""
    try:
        while not stop_event.is_set():
            try:
                # Use a small timeout to allow checking stop_event periodically
                if hasattr(stream, 'read1'):
                    # For buffered streams, read1 is non-blocking if data is available
                    data = stream.read1(4096)
                else:
                    data = stream.read(4096)
                if data:
                    q.put(data)
                else:
                    # No data available, sleep briefly
                    time.sleep(0.01)
            except (IOError, OSError):
                # Stream might be closed
                break
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
        default=15 * 60,
        description="Timeout in seconds. If not specified, no timeout is applied.",
    )


_running_process: Optional[subprocess.Popen] = None
_running_process_timeout: float = 0
_stdout_queue: queue.Queue = queue.Queue()
_stderr_queue: queue.Queue = queue.Queue()
_stop_readers: threading.Event = threading.Event()
_reader_threads: list[threading.Thread] = []


def _start_reader_threads(process: subprocess.Popen):
    """Start threads to read stdout and stderr."""
    global _reader_threads, _stop_readers
    _stop_readers.clear()
    _reader_threads = []

    if process.stdout:
        stdout_thread = threading.Thread(
            target=_read_stream_into_queue,
            args=(process.stdout, _stdout_queue, _stop_readers),
            daemon=True
        )
        stdout_thread.start()
        _reader_threads.append(stdout_thread)

    if process.stderr:
        stderr_thread = threading.Thread(
            target=_read_stream_into_queue,
            args=(process.stderr, _stderr_queue, _stop_readers),
            daemon=True
        )
        stderr_thread.start()
        _reader_threads.append(stderr_thread)


def _stop_reader_threads():
    """Stop the reader threads."""
    global _stop_readers, _reader_threads
    _stop_readers.set()
    for thread in _reader_threads:
        thread.join(timeout=1.0)
    _reader_threads = []


def _drain_queues():
    """Drain all items from the queues and return them."""
    stdout_items = []
    stderr_items = []

    try:
        while True:
            stdout_items.append(_stdout_queue.get_nowait())
    except queue.Empty:
        pass

    try:
        while True:
            stderr_items.append(_stderr_queue.get_nowait())
    except queue.Empty:
        pass

    return stdout_items, stderr_items


class Run(CallableTool2):
    name: str = "Run"
    description: str = "Run a process from a path."
    params: type[RunParams] = RunParams

    async def __call__(self, params: RunParams) -> ToolReturnValue:
        global _running_process, _stdout_queue, _stderr_queue, _running_process_timeout
        _running_process_timeout = max(params.timeout, 5.0)
        process = None
        stdout_buffer = []
        stderr_buffer = []

        try:
            # Check if there's already a running process
            if _running_process:
                if params.path == '#interrup':
                    # Kill/interrupt the existing running process
                    try:
                        _running_process.terminate()
                        try:
                            _running_process.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            _running_process.kill()
                            _running_process.wait()
                    except Exception:
                        return ToolError(output="Previous process interrupted.")
                    _stop_reader_threads()
                    _running_process = None
                    return ToolOk(output="Previous process interrupted.")
                else:
                    # Return error, tell agent to use Input tool, or input '#interrup' to kill this process
                    return ToolError(
                        output="",
                        message="Another process is already running. Use the 'Input' tool to interact with it, or run with path='#interrup' to kill the running process.",
                        brief="Another process is running",
                    )

            # Clear the queues
            while not _stdout_queue.empty():
                _stdout_queue.get_nowait()
            while not _stderr_queue.empty():
                _stderr_queue.get_nowait()

            # Start the process
            process = subprocess.Popen(
                [params.path] + params.args,
                cwd=params.cwd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=0,
            )
            _running_process = process

            # Start reader threads
            _start_reader_threads(process)

            # Polling loop
            last_output_time = time.time()

            while process.poll() is None:
                # Check timeout
                if params.timeout is not None:
                    elapsed = time.time() - last_output_time
                    if elapsed > params.timeout:
                        process.kill()
                        process.wait()
                        _stop_reader_threads()
                        _running_process = None
                        return ToolError(
                            output="",
                            message=f"Process timed out after {params.timeout} seconds",
                            brief="Process timed out",
                        )

                # Get data from queues
                stdout_items, stderr_items = _drain_queues()
                input_prompt_detected = False

                for data in stdout_items:
                    stdout_buffer.append(data)
                    decoded = data.decode('utf-8', errors='replace')
                    if _check_for_input_prompt(decoded):
                        input_prompt_detected = True
                    last_output_time = time.time()

                for data in stderr_items:
                    stderr_buffer.append(data)
                    last_output_time = time.time()

                # If input prompt detected, return early and tell agent to use Input tool
                if input_prompt_detected:
                    _stop_reader_threads()
                    stdout = b"".join(stdout_buffer).decode(
                        'utf-8', errors='replace')
                    stderr = b"".join(stderr_buffer).decode(
                        'utf-8', errors='replace')
                    output_lines = [
                        "Process is waiting for input. Use the 'Input' tool to send input.",
                        "",
                        "Process output so far:",
                    ]
                    if stdout:
                        output_lines.append("STDOUT:")
                        output_lines.append(stdout)
                    if stderr:
                        output_lines.append("STDERR:")
                        output_lines.append(stderr)
                    _running_process = None
                    return ToolOk(output=_maybe_export_output("\n".join(output_lines)))

                # Yield control to allow other async tasks to run
                await asyncio.sleep(0.01)

            # Process has exited, get remaining output
            _stop_reader_threads()
            remaining_stdout, remaining_stderr = _drain_queues()

            for data in remaining_stdout:
                stdout_buffer.append(data)
            for data in remaining_stderr:
                stderr_buffer.append(data)

            return_code = process.returncode
            _running_process = None
            stdout = b"".join(stdout_buffer).decode('utf-8', errors='replace')
            stderr = b"".join(stderr_buffer).decode('utf-8', errors='replace')

            output_lines = [
                f"Return Code: {return_code}",
            ]

            if stdout:
                output_lines.append(stdout)

            if stderr:
                output_lines.append(stderr)

            output_text = "\n".join(output_lines)

            if params.dest:
                with open(params.dest, 'w', encoding='utf-8') as f:
                    f.write(output_text)
                output_text = f"Output saved to {params.dest}"

            if return_code != 0:
                return ToolError(
                    output=_maybe_export_output(output_text),
                    message=f"Process exited with non-zero return code: {return_code}",
                    brief="Process failed",
                )

            return ToolOk(output=_maybe_export_output(output_text))
        except Exception as exc:
            if process is not None and process.poll() is None:
                process.kill()
                process.wait()
            _stop_reader_threads()
            _running_process = None
            return ToolError(
                output="",
                message=str(exc),
                brief="Failed to run process",
            )


class InputParams(BaseModel):
    input: str = Field(
        description="The input string to send to the running subprocess.",
    )


class Input(CallableTool2):
    name: str = "Input"
    description: str = "Input string to a running subprocess."
    params: type[InputParams] = InputParams

    async def __call__(self, params: InputParams) -> ToolReturnValue:
        global _running_process

        if _running_process is None:
            return ToolError(
                output="",
                message="No running process found. Start a process with Run first.",
                brief="No running process",
            )
        if not params.input:
            return ToolError(
                output="",
                message="No input",
                brief="No input",
            )
        process = _running_process

        # Restart reader threads to ensure we can read output
        _start_reader_threads(process)

        # Check if process is done
        if process.poll() is not None:
            _stop_reader_threads()
            _running_process = None
            return ToolOk(output=f"Process has already exited with code {process.returncode}")

        # Check if stdin is available for input
        if process.stdin is None or process.stdin.closed:
            return ToolError(
                output="",
                message="Process does not accept input (stdin is not available)",
                brief="Process does not accept input",
            )

        try:
            # Send input to the process
            input_bytes = params.input.encode('utf-8')
            # Add newline if not present (most interactive programs expect it)
            if not input_bytes.endswith(b'\n'):
                input_bytes += b'\n'
            process.stdin.write(input_bytes)
            process.stdin.flush()

            # Wait a bit for the process to process the input and produce output
            await asyncio.sleep(0.1)

            # Read any available output from queues
            stdout_buffer = []
            stderr_buffer = []
            input_prompt_detected = False

            # Collect output for a short period
            timeout = min(_running_process_timeout, 60)
            last_output_time = time.time()
            while True:  # 50 * 0.01s = 0.5s
                if timeout > 1e-4:
                    elapsed = time.time() - last_output_time
                    if elapsed > timeout:
                        if input_prompt_detected:
                            break
                        else:
                            # Timeout without input prompt, kill process
                            try:
                                process.terminate()
                                try:
                                    process.wait(timeout=5)
                                except subprocess.TimeoutExpired:
                                    process.kill()
                                    process.wait()
                            except Exception:
                                pass
                            _stop_reader_threads()
                            _running_process = None
                            return ToolError(
                                output="",
                                message=f"Process timed out after {timeout} seconds",
                                brief="Process timed out",
                            )
                    
                stdout_items, stderr_items = _drain_queues()
                for data in stdout_items:
                    stdout_buffer.append(data)
                    decoded = data.decode('utf-8', errors='replace')
                    if _check_for_input_prompt(decoded):
                        input_prompt_detected = True
                        last_output_time = time.time()
                        # only wait 3 seconds while find another input
                        timeout = min(last_output_time, 1)

                for data in stderr_items:
                    stderr_buffer.append(data)

                # Check if process has exited
                if process.poll() is not None:
                    break

                await asyncio.sleep(0.01)

            # Get any remaining output
            stdout_items, stderr_items = _drain_queues()

            for data in stdout_items:
                stdout_buffer.append(data)
                decoded = data.decode('utf-8', errors='replace')
                if _check_for_input_prompt(decoded):
                    input_prompt_detected = True

            for data in stderr_items:
                stderr_buffer.append(data)

            stdout = b"".join(stdout_buffer).decode(
                'utf-8', errors='replace') if stdout_buffer else ""
            stderr = b"".join(stderr_buffer).decode(
                'utf-8', errors='replace') if stderr_buffer else ""

            # If input prompt detected, return early and tell agent to use Input tool again
            if input_prompt_detected:
                output_lines = [
                    "Input sent successfully. Process is waiting for more input. Use the 'Input' tool to send more input.",
                    "",
                    "Process output so far:",
                ]
                if stdout:
                    output_lines.append("STDOUT:")
                    output_lines.append(stdout)
                if stderr:
                    output_lines.append("STDERR:")
                    output_lines.append(stderr)
                return ToolOk(output=_maybe_export_output("\n".join(output_lines)))

            output_lines = ["Input sent successfully."]
            if stdout:
                output_lines.append("STDOUT:")
                output_lines.append(stdout)
            if stderr:
                output_lines.append("STDERR:")
                output_lines.append(stderr)

            return ToolOk(output=_maybe_export_output("\n".join(output_lines)))

        except (IOError, OSError) as exc:
            return ToolError(
                output="",
                message=f"Failed to send input to process: {str(exc)}",
                brief="Failed to send input",
            )
        except Exception as exc:
            return ToolError(
                output="",
                message=f"Unexpected error: {str(exc)}",
                brief="Failed to send input",
            )
