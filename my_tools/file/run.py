"""run tool for executing a process from a path."""
import anyio
import asyncio
import os
import queue
import subprocess
import threading
import time
from pathlib import Path

from kimi_agent_sdk import CallableTool2, ToolError, ToolOk, ToolReturnValue
from pydantic import BaseModel, Field
from my_tools.common import _maybe_export_output_async, _export_to_temp_file_async
from my_tools.background.utils import BackgroundStream, generate_task_id, add_task


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
    run_in_background: bool = Field(
        default=False,
        description="Run in an independent background process. Returns immediately with a task_id. Use TaskList, TaskOutput, and TaskWait to manage. ALWAYS set to True with input detection use `Input` tool."
    )


class Run(CallableTool2):
    name: str = "Run"
    description: str = "Execute a program."
    params: type[RunParams] = RunParams

    async def __call__(self, params: RunParams) -> ToolReturnValue:
        # Handle background execution
        if params.run_in_background:
            return await self._run_in_background(params)
        output = ''
        try:
            # Run the command using async subprocess
            proc = await asyncio.create_subprocess_exec(
                params.path, *params.args,
                cwd=params.cwd,
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

            # Handle output export if needed
            if params.output_path:
                async with await anyio.open_file(params.output_path, 'w', encoding='utf-8', errors='replace') as f:
                    await f.write(output)
                output = f'saved to file `{params.output_path}`'
            # Return error if command failed
            if proc.returncode != 0:
                if output and not params.output_path:
                    temp_path, _ = await _export_to_temp_file_async(key=None, content=output, ext='.txt')
                    output = f'saved to file `{temp_path}`'
                return ToolError(
                    output=output,
                    message=f"Command failed with exit code {proc.returncode}",
                    brief="Command execution failed"
                )
            output = await _maybe_export_output_async(output)
            return ToolOk(output=output)

        except asyncio.TimeoutError:
            if output and not params.output_path:
                temp_path, _ = await _export_to_temp_file_async(key=None, content=output, ext='.txt')
                output = f'saved to file `{temp_path}`'

            return ToolError(
                output=output,
                message=f"Command timed out after {params.timeout} seconds",
                brief="Command execution timeout"
            )
        except Exception as exc:
            # Clean up
            if output and not params.output_path:
                temp_path, _ = await _export_to_temp_file_async(key=None, content=output, ext='.txt')
                output = f'saved to file `{temp_path}`'

            return ToolError(
                output=output,
                message=str(exc),
                brief="Failed to run process",
            )

    async def _run_in_background(self, params: RunParams) -> ToolReturnValue:
        """Run a process in the background and register it as a background task.

        Args:
            params: The run parameters.

        Returns:
            ToolOk with task_id on success, ToolError on failure.
        """
        # Shared state for stopping the process
        _stop_event = threading.Event()
        _process_ref = [None]  # Use list to hold reference in nested function

        def run_process_bg(q: queue.Queue[str]) -> bool:
            """Run the process and collect output into the queue."""
            process = None
            try:
                if _stop_event.is_set():
                    return False
                # Start the process
                process = subprocess.Popen(
                    [params.path] + params.args,
                    cwd=params.cwd,
                    stdin=subprocess.PIPE,  # Allow input via input_function
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
                    target=read_stream_one, args=(
                        process.stdout, ), daemon=True
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

            # Generate a task ID based on the executable name
            exe_name = Path(params.path).stem
            task_id = generate_task_id("run", exe_name)
            stream.start(run_process_bg, stop_function, input_function)
            # Register the task
            add_task(task_id, stream)

            # Return success with task_id
            return ToolOk(
                output=f"Process started in background.\nTask ID: {task_id}\n\nUse 'TaskList' to view all tasks, 'TaskOutput' to get output. 'TaskStop' to kill process., 'Input' to input to process"
            )

        except Exception as exc:
            return ToolError(
                output="",
                message=f"Failed to start background process: {str(exc)}",
                brief="Failed to start background task"
            )
