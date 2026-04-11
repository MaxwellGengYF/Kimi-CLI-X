import asyncio
import subprocess
import sys
import os
import traceback
import queue
import threading
from my_tools.common import _maybe_export_output
from kimi_agent_sdk import CallableTool2, ToolError, ToolOk, ToolReturnValue
from pydantic import BaseModel, Field
from my_tools.common import _export_to_temp_file
from pathlib import Path
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
    description: str = "Execute Python code."
    params: type[Params] = Params

    async def __call__(self, params: Params) -> ToolReturnValue:
        # Handle background execution
        if params.run_in_background:
            return await self._run_in_background(params)

        import io
        import contextlib

        def _exec_code(code: str):
            # Create a restricted globals dict for safer execution
            exec_globals = {"__builtins__": __builtins__,
                            '__name__': '__main__'}
            # Use exec_globals as locals too so functions can reference each other
            # This is needed for recursive function calls to work properly

            # Capture stdout and stderr
            stdout_buffer = io.StringIO()
            stderr_buffer = io.StringIO()
            exception = None
            with contextlib.redirect_stdout(stdout_buffer), contextlib.redirect_stderr(stderr_buffer):
                try:
                    exec(code, exec_globals, exec_globals)
                except Exception as e:
                    # Capture full exception info including traceback
                    exception = traceback.format_exc()

            return stdout_buffer.getvalue(), stderr_buffer.getvalue(), exception

        try:
            # Run code in an independent thread
            stdout, stderr, exception = await asyncio.to_thread(_exec_code, params.code)

            # Combine outputs
            output_parts = []
            if stdout:
                output_parts.append(stdout)
            if stderr:
                output_parts.append(stderr)
            output = "".join(output_parts)

            # Handle dest parameter if provided
            if params.dest:
                Path(params.dest).write_text(output, encoding='utf-8')
                output = f'output exported to: {params.dest}'
            else:
                output = _maybe_export_output(output)
            if exception:
                return ToolError(message=exception, output=output, brief="Python execution error")
            return ToolOk(output=output)
        except Exception as e:
            return ToolError(message=str(e), brief="Python tool error")

    async def _run_in_background(self, params: Params) -> ToolReturnValue:
        """Run Python code in the background using exec in a thread."""
        import io
        import contextlib

        # Shared state for stopping the thread
        _stop_event = threading.Event()

        def run_python_bg(q: queue.Queue[str]) -> None:
            """Run Python code with exec and capture output."""
            exec_globals = {
                "__builtins__": __builtins__,
                "__name__": "__main__",
                "_stop_requested": _stop_event,  # Provide stop event to user code
            }
            stdout_buffer = io.StringIO()
            stderr_buffer = io.StringIO()

            with contextlib.redirect_stdout(stdout_buffer), contextlib.redirect_stderr(stderr_buffer):
                try:
                    exec(params.code, exec_globals, exec_globals)
                except Exception:
                    print(traceback.format_exc(), file=stderr_buffer)

            output = stdout_buffer.getvalue()
            error = stderr_buffer.getvalue()

            if output:
                q.put_nowait(output)
            if error:
                q.put_nowait("[stderr] " + error)

            if params.dest and (output or error):
                try:
                    Path(params.dest).write_text(output + error, encoding="utf-8")
                    q.put_nowait(f"\n[Output exported to: {params.dest}]")
                except Exception as e:
                    q.put_nowait(f"\n[Error exporting to dest: {e}]")

            if _stop_event.is_set():
                q.put_nowait("\n[Process stopped by user]")
            else:
                q.put_nowait("\n[Process completed]")

        def stop_function():
            """Signal the background thread to stop."""
            _stop_event.set()

        try:
            stream = BackgroundStream()
            task_id = generate_task_id("python")
            stream.start(run_python_bg, stop_function)
            add_task(task_id, stream)

            return ToolOk(
                output=f"Python process started in background.\nTask ID: {task_id}\n\nUse 'TaskList' to view all tasks, 'TaskOutput' to get output, and 'TaskWait' to wait for completion."
            )
        except Exception as exc:
            return ToolError(
                message=f"Failed to start background Python process: {str(exc)}",
                brief="Failed to start background task"
            )
