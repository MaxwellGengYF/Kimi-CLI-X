import asyncio
import subprocess
import sys
import os
import traceback
from my_tools.common import _maybe_export_output
from kimi_agent_sdk import CallableTool2, ToolError, ToolOk, ToolReturnValue
from pydantic import BaseModel, Field
from my_tools.common import _export_to_temp_file
from pathlib import Path

class Params(BaseModel):
    code: str = Field(
        description="The Python code.",
    )
    dest: str | None = Field(
        default=None,
        description="The destination path to save the output. If provided, output will be saved to this file.",
    )
    timeout: float | None = Field(
        default=None,
        ge=0,
        description="Timeout in seconds. If not specified, no timeout is applied.",
    )


# Force UTF-8 encoding for subprocess on Windows
os.environ['PYTHONIOENCODING'] = 'utf-8'


class Python(CallableTool2):
    name: str = "Python"
    description: str = "Execute Python code"
    params: type[Params] = Params

    async def __call__(self, params: Params) -> ToolReturnValue:
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
