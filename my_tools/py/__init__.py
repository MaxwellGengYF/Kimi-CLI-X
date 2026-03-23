import asyncio
import sys
from io import StringIO
from my_tools.common import _maybe_export_output
from kimi_agent_sdk import CallableTool2, ToolError, ToolOk, ToolReturnValue
from pydantic import BaseModel, Field

# Token limit threshold - if output exceeds this, export to temp file
# Using 8000 as a conservative threshold to stay well below typical model limits
OUTPUT_TOKEN_LIMIT = 8000


class Params(BaseModel):
    code: str = Field(
        description="The Python code to execute. ",
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

class Python(CallableTool2):
    name: str = "Python"
    description: str = "Execute Python code using exec function. Consider as Shell, os, sys, subprocess, pathlib, json, pathlib, Path already imported."
    params: type[Params] = Params
    globals_dict = None
    locals_dict = None

    async def __call__(self, params: Params) -> ToolReturnValue:
        if self.globals_dict is None:
            self.globals_dict = dict()
            self.locals_dict = dict()
            exec('''
import os
import sys
import subprocess
import pathlib
import json
from pathlib import Path
'''.strip(), self.globals_dict, self.locals_dict)

        # Capture stdout during exec
        old_stdout = sys.stdout
        captured_output = StringIO()
        sys.stdout = captured_output

        def _exec_code():
            exec(params.code, self.globals_dict, self.locals_dict)

        try:
            if params.timeout:
                await asyncio.wait_for(
                    asyncio.to_thread(_exec_code),
                    timeout=params.timeout
                )
            else:
                _exec_code()
            output = captured_output.getvalue()
            if params.dest:
                with open(params.dest, 'w', encoding='utf-8') as f:
                    f.write(output)
                return ToolOk(output=f"Output saved to {params.dest}")
            if not output:
                result = output
                return ToolOk(output='')
            return ToolOk(output=_maybe_export_output(result))
        except asyncio.TimeoutError:
            output = captured_output.getvalue()
            if params.dest:
                with open(params.dest, 'w', encoding='utf-8') as f:
                    f.write(output)
                return ToolError(
                    output=f"Output saved to {params.dest}",
                    message=f"Python code execution timed out after {params.timeout} seconds",
                    brief="Python code execution timed out",
                )
            if not output:
                return ToolError(
                    output='',
                    message=f"Python code execution timed out after {params.timeout} seconds",
                    brief="Python code execution timed out",
                )
            result = output
            return ToolError(
                output=_maybe_export_output(result),
                message=f"Python code execution timed out after {params.timeout} seconds",
                brief="Python code execution timed out",
            )
        except Exception as exc:
            output = captured_output.getvalue()
            if params.dest:
                with open(params.dest, 'w', encoding='utf-8') as f:
                    f.write(output)
                return ToolError(
                    output=f"Output saved to {params.dest}",
                    message=str(exc),
                    brief="Failed to execute Python code",
                )
            if not output:
                return ToolError(
                    output='',
                    message=str(exc),
                    brief="Failed to execute Python code",
                )
            result = output
            return ToolError(
                output=_maybe_export_output(result),
                message=str(exc),
                brief="Failed to execute Python code",
            )

        finally:
            sys.stdout = old_stdout
