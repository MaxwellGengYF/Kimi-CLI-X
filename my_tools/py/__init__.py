import asyncio
import subprocess
import sys
import os
from my_tools.common import _maybe_export_output
from kimi_agent_sdk import CallableTool2, ToolError, ToolOk, ToolReturnValue
from pydantic import BaseModel, Field
from my_tools.common import _export_to_temp_file


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
env = os.environ.copy()
env['PYTHONIOENCODING'] = 'utf-8'


class Python(CallableTool2):
    name: str = "Python"
    description: str = "Execute Python code in a file"
    params: type[Params] = Params

    async def __call__(self, params: Params) -> ToolReturnValue:
        # Save code to temp file
        from hashlib import md5
        key = md5(params.code.encode('utf-8')).hexdigest()
        temp_file, _ = _export_to_temp_file(key, params.code)

        try:

            # Run the script as subprocess
            proc = await asyncio.create_subprocess_exec(
                sys.executable, temp_file,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=params.timeout
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                return ToolError(
                    output="",
                    message=f"Python code execution timed out after {params.timeout} seconds",
                    brief="Python code execution timed out",
                )

            # Decode output
            output = stdout.decode('utf-8', errors='replace')
            error_output = stderr.decode('utf-8', errors='replace')

            # Combine stdout and stderr if there's any stderr
            full_output = output
            if error_output:
                if full_output:
                    full_output += "\n" + error_output
                else:
                    full_output = error_output

            # Handle process return code
            if proc.returncode != 0:
                if params.dest:
                    if full_output:
                        with open(params.dest, 'w', encoding='utf-8') as f:
                            f.write(full_output)
                    return ToolError(
                        output=f"Output saved to {params.dest}" if full_output else '',
                        message=f"Process exited with code {proc.returncode}",
                        brief="Failed to execute Python code",
                    )
                return ToolError(
                    output=_maybe_export_output(full_output),
                    message=f"Process exited with code {proc.returncode}",
                    brief="Failed to execute Python code",
                )

            # Success case
            if params.dest:
                if full_output:
                    with open(params.dest, 'w', encoding='utf-8') as f:
                        f.write(full_output)
                return ToolOk(output=f"Output saved to {params.dest}" if full_output else '')
            return ToolOk(output=_maybe_export_output(full_output))

        except Exception as exc:
            if params.dest:
                return ToolError(
                    output=f"",
                    message=str(exc),
                    brief="Failed to execute Python code",
                )
            return ToolError(
                output="",
                message=str(exc),
                brief="Failed to execute Python code",
            )
        finally:
            # Clean up temp file
            try:
                os.remove(temp_file)
            except Exception:
                pass
