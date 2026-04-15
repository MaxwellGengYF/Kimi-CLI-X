import asyncio
import subprocess
import sys
import os
import queue
import threading
import time
from my_tools.common import _maybe_export_output_async
from kimi_agent_sdk import CallableTool2, ToolError, ToolOk, ToolReturnValue
from pydantic import BaseModel, Field
from pathlib import Path
import anyio
from .check import PySyntaxCheck
from my_tools.background.utils import BackgroundStream, generate_task_id, add_task


class Params(BaseModel):
    code: str = Field(
        description="Python code to execute.",
    )
    dest: str | None = Field(
        default=None,
        description="Output file path (optional)."
    )
    timeout: float | None = Field(
        default=None,
        ge=0,
        description="Timeout in seconds (default: no timeout)."
    )
    run_in_background: bool = Field(
        default=False,
        description="Run in an independent background process. Returns immediately with a task_id. Use TaskList, TaskOutput, and TaskWait to manage."
    )


# Force UTF-8 encoding for subprocess on Windows
os.environ['PYTHONIOENCODING'] = 'utf-8'


class Python(CallableTool2):
    name: str = "Python"
    description: str = "Execute Python code in subprocess."
    params: type[Params] = Params

    async def __call__(self, params: Params) -> ToolReturnValue:
        # Handle background execution
        if params.run_in_background:
            return await self._run_in_background(params)

        output = ''
        try:
            # Run the Python code using async subprocess
            # Use python -c to execute the code directly
            proc = await asyncio.create_subprocess_exec(
                sys.executable, '-c', params.code,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            # Wait for process with optional timeout
            if params.timeout is not None:
                stdout_data, stderr_data = await asyncio.wait_for(
                    proc.communicate(), timeout=params.timeout
                )
            else:
                stdout_data, stderr_data = await proc.communicate()

            # Decode output with utf-8 and replace errors
            stdout_text = stdout_data.decode('utf-8', errors='replace')
            stderr_text = stderr_data.decode('utf-8', errors='replace')

            # Combine stdout and stderr
            output_parts = []
            if stdout_text:
                output_parts.append(stdout_text)
            if stderr_text:
                output_parts.append(f"[stderr] {stderr_text}")
            output = "\n".join(output_parts)

            # Handle dest parameter if provided
            if params.dest:
                async with await anyio.open_file(params.dest, 'w', encoding='utf-8', errors='replace') as f:
                    await f.write(output)
                output = f'output exported to: {params.dest}'
            else:
                output = await _maybe_export_output_async(output)

            # Return error if command failed
            if proc.returncode != 0:
                return ToolError(
                    output=output,
                    message=f"Python execution failed with exit code {proc.returncode}",
                    brief="Python execution error"
                )
            return ToolOk(output=output)

        except asyncio.TimeoutError:
            return ToolError(
                output=output,
                message=f"Python execution timed out after {params.timeout} seconds",
                brief="Python execution timeout"
            )
        except Exception as exc:
            return ToolError(
                output=output,
                message=str(exc),
                brief="Python tool error"
            )

    async def _run_in_background(self, params: Params) -> ToolReturnValue:
        """Run Python code in the background using subprocess.

        Args:
            params: The Python execution parameters.

        Returns:
            ToolOk with task_id on success, ToolError on failure.
        """
        # Shared state for stopping the process
        _stop_event = threading.Event()
        _process_ref = [None]  # Use list to hold reference in nested function

        def run_python_bg(q: queue.Queue[str]) -> bool:
            """Run the Python process and collect output into the queue."""
            process = None
            try:
                if _stop_event.is_set():
                    return False

                # Start the Python process
                process = subprocess.Popen(
                    [sys.executable, '-u', '-c', params.code],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding='utf-8',
                    errors='replace'
                )
                _process_ref[0] = process

                # Read stdout and stderr concurrently with stop checking
                def read_stream(stream, is_stderr: bool = False):
                    try:
                        while True:
                            if stream.closed or _stop_event.is_set():
                                break
                            data = stream.read()
                            if data:
                                prefix = "[stderr] " if is_stderr else ""
                                q.put_nowait(prefix + data)
                            else:
                                time.sleep(0.01)
                    except (IOError, OSError, ValueError):
                        pass

                def read_stream_one(stream):
                    try:
                        while True:
                            if stream.closed or _stop_event.is_set():
                                break
                            data = stream.read(1)
                            if data:
                                q.put_nowait(data)
                            else:
                                time.sleep(0.01)
                    except (IOError, OSError, ValueError):
                        pass

                # Start reader threads
                stdout_thread = threading.Thread(
                    target=read_stream_one, args=(process.stdout,), daemon=True
                )
                stderr_thread = threading.Thread(
                    target=read_stream, args=(process.stderr, True), daemon=True
                )
                stdout_thread.start()
                stderr_thread.start()

                # Wait for process completion with periodic stop checking
                while process.poll() is None:
                    if _stop_event.is_set():
                        process.terminate()
                        try:
                            process.wait(timeout=2)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait()
                        break
                    time.sleep(0.1)

                # Wait for readers to finish
                stdout_thread.join(timeout=1)
                stderr_thread.join(timeout=1)

                # Read any remaining data from stdout and stderr
                try:
                    remaining_stdout = process.stdout.read()
                    if remaining_stdout:
                        q.put_nowait(remaining_stdout)
                except (IOError, OSError, ValueError):
                    pass
                try:
                    remaining_stderr = process.stderr.read()
                    if remaining_stderr:
                        q.put_nowait("[stderr] " + remaining_stderr)
                except (IOError, OSError, ValueError):
                    pass

                # Report completion status
                return_code = process.poll()
                if _stop_event.is_set():
                    q.put_nowait("\n[Process stopped by user]")
                    return False
                elif return_code is not None and return_code != 0:
                    q.put_nowait(f"\n[Process exited with code {return_code}]")
                    return False
                return True

                # Handle dest parameter if provided
                if params.dest:
                    try:
                        # Collect all output for export
                        full_output = []
                        # Note: We can't easily reconstruct from queue, so this is handled separately
                        # The output will still be streamed via the queue
                    except Exception as e:
                        q.put_nowait(f"\n[Error exporting to dest: {e}]")

            except Exception as e:
                q.put_nowait(f"\n[Error: {str(e)}]")
                return False
            finally:
                _stop_event.set()
                if process is not None and process.poll() is None:
                    try:
                        process.kill()
                        process.wait()
                    except:
                        pass

        def stop_function():
            """Signal the background process to stop."""
            _stop_event.set()
            # Also try to terminate the process directly if it's running
            proc: subprocess.Popen = _process_ref[0]
            if proc is not None and proc.poll() is None:
                try:
                    proc.terminate()
                except Exception:
                    pass

        def input_function(data: str) -> bool:
            """Push data to the process's stdin.
            
            Args:
                data: The string data to write to stdin.
                
            Returns:
                True if data was written successfully, False otherwise.
            """
            proc: subprocess.Popen = None
            # Wait for the process to be available
            while True:
                if _stop_event.is_set():
                    return False
                proc = _process_ref[0]
                if proc is None:
                    time.sleep(0.05)
                else:
                    break
            
            # Write data to stdin
            try:
                if proc.stdin is not None and proc.poll() is None:
                    proc.stdin.write(data)
                    proc.stdin.flush()
                    return True
            except (IOError, OSError, ValueError):
                # Process may have terminated or stdin is closed
                pass
            return False

        try:
            # Create and start the background stream
            stream = BackgroundStream()
            task_id = generate_task_id("python")
            stream.start(run_python_bg, stop_function, input_function)
            # Register the task
            add_task(task_id, stream)

            return ToolOk(
                output=f"Python process started in background.\nTask ID: {task_id}\n\nUse 'TaskList' to view all tasks, 'TaskOutput' to get output, 'TaskWait' to wait for completion, 'TaskStop' to kill process, 'Input' to input to process."
            )

        except Exception as exc:
            return ToolError(
                output="",
                message=f"Failed to start background Python process: {str(exc)}",
                brief="Failed to start background task"
            )
