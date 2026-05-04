"""rm tool - remove files or directories."""
import os
import shutil
from pathlib import Path

from kimi_agent_sdk import CallableTool2, ToolError, ToolOk, ToolReturnValue
from .params import Params

from kimix.tools.common import _maybe_export_output_async

_RECURSIVE_FLAGS = frozenset({"-r", "-R", "--recursive"})
_FORCE_FLAGS = frozenset({"-f", "--force"})
_BOTH_FLAGS = frozenset({"-rf", "-fr"})


class Rm(CallableTool2[Params]):
    name: str = "Rm"
    description: str = "Remove files or directories."
    params: type[Params] = Params

    async def __call__(self, params: Params) -> ToolReturnValue:
        try:
            recursive = False
            force = False
            paths = []
            for arg in params.args:
                if arg in _RECURSIVE_FLAGS:
                    recursive = True
                elif arg in _FORCE_FLAGS:
                    force = True
                elif arg in _BOTH_FLAGS:
                    recursive = True
                    force = True
                elif not arg.startswith("-"):
                    paths.append(arg)

            if not paths:
                return ToolError(message="rm: missing operand", output="", brief="missing operand")

            cwd = params.cwd or os.getcwd()
            errors = []
            for p in paths:
                target = os.path.join(cwd, p) if not os.path.isabs(p) else p
                try:
                    if os.path.isdir(target):
                        if recursive:
                            shutil.rmtree(target)
                        elif not force:
                            errors.append(f"rm: cannot remove '{p}': Is a directory")
                    else:
                        os.remove(target)
                except FileNotFoundError:
                    if not force:
                        errors.append(f"rm: cannot remove '{p}': No such file or directory")
                except OSError as e:
                    if not force:
                        errors.append(f"rm: cannot remove '{p}': {e}")

            if errors:
                output = "\n".join(errors)
                if params.output_path:
                    with open(params.output_path, "w", encoding="utf-8") as f:
                        f.write(output)
                    output = f"saved to file `{params.output_path}`"
                return ToolError(message=output, output=output, brief="rm failed")

            output = ""
            if params.output_path:
                with open(params.output_path, "w", encoding="utf-8") as f:
                    f.write(output)
                output = f"saved to file `{params.output_path}`"
            return ToolOk(output=output)
        except Exception as e:
            return ToolError(message=str(e), output="", brief="rm failed")
