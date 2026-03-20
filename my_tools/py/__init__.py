import sys
from io import StringIO

from kimi_agent_sdk import CallableTool2, ToolError, ToolOk, ToolReturnValue
from pydantic import BaseModel, Field


class Params(BaseModel):
    code: str = Field(
        description="The Python code to execute. ",
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
        
        try:
            exec(params.code, self.globals_dict, self.locals_dict)
            output = captured_output.getvalue()
            return ToolOk(output=output if output else "Code executed successfully.")
        except Exception as exc:
            output = captured_output.getvalue()
            return ToolError(
                output=output,
                message=str(exc),
                brief="Failed to execute Python code",
            )
        finally:
            sys.stdout = old_stdout
