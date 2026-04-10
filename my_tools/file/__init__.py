
from kimi_agent_sdk import CallableTool2, ToolError, ToolOk, ToolReturnValue
from pydantic import BaseModel, Field
from my_tools.common import _maybe_export_output

from my_tools.file.chdir import Cd
from my_tools.file.kill_process import Kill, KillParams
from my_tools.file.input import Input, InputParams
from my_tools.file.run import Run, RunParams
from my_tools.file.wait_process import Wait, WaitParams


class LsParams(BaseModel):
    directory: str = Field(
        default=".",
        description="Target directory path."
    )
    long_format: bool = Field(
        default=False,
        description="Show detailed file information."
    )
    recursive: bool = Field(
        default=False,
        description="List subdirectories recursively."
    )


class Ls(CallableTool2):
    name: str = "Ls"
    description: str = "List directory contents."
    params: type[LsParams] = LsParams

    async def __call__(self, params: LsParams) -> ToolReturnValue:
        import os
        from datetime import datetime

        def format_file_info(path: str, name: str) -> str:
            """Format file info for long format listing."""
            full_path = os.path.join(path, name)
            try:
                stat = os.stat(full_path)
                size = stat.st_size
                mtime = datetime.fromtimestamp(
                    stat.st_mtime).strftime("%Y-%m-%d %H:%M")
                ftype = "d" if os.path.isdir(full_path) else "-"
                mode = oct(stat.st_mode)[-3:]
                return f"{ftype}{mode:>9} {size:>10} {mtime} {name}"
            except Exception:
                return f"?????????? ???????? ?????????? {name}"

        def list_directory(path: str, prefix: str = "") -> list[str]:
            """List directory contents, optionally recursively."""
            result = []
            try:
                items = os.listdir(path)
            except Exception as exc:
                raise exc
            # Sort items (directories first, then alphabetically)
            items.sort(key=lambda x: (not os.path.isdir(
                os.path.join(path, x)), x.lower()))

            for item in items:
                if params.long_format:
                    result.append(prefix + format_file_info(path, item))
                else:
                    result.append(prefix + item)

                # Recursively list subdirectories if requested
                if params.recursive and os.path.isdir(os.path.join(path, item)):
                    result.append("")
                    subdir = os.path.join(path, item)
                    result.append(f"{prefix}{item}:")
                    result.extend(list_directory(subdir, prefix + "  "))

            return result

        try:
            lines = list_directory(params.directory)
            return ToolOk(output=_maybe_export_output("\n".join(lines) if lines else "(empty directory)"))
        except Exception as exc:
            return ToolError(
                output="",
                message=str(exc),
                brief="Failed to list files",
            )


class MkdirParams(BaseModel):
    path: str = Field(
        description="Directory path to create."
    )


class Mkdir(CallableTool2):
    name: str = "Mkdir"
    description: str = "Create a directory (including parent directories if needed)."
    params: type[MkdirParams] = MkdirParams

    async def __call__(self, params: MkdirParams) -> ToolReturnValue:
        import os

        try:
            os.makedirs(params.path, exist_ok=True)
            return ToolOk(output=_maybe_export_output(f"Directory created: {params.path}", params.path))
        except Exception as exc:
            return ToolError(
                output="",
                message=str(exc),
                brief="Failed to create directory",
            )


class RmParams(BaseModel):
    path: str = Field(
        description="Path to the file or directory to delete."
    )


class Rm(CallableTool2):
    name: str = "Rm"
    description: str = "Delete a file or directory."
    params: type[RmParams] = RmParams

    async def __call__(self, params: RmParams) -> ToolReturnValue:
        import shutil
        import os

        try:
            if os.path.isdir(params.path):
                shutil.rmtree(params.path)
            else:
                os.remove(params.path)
            return ToolOk(output=_maybe_export_output(f"Deleted: {params.path}"))
        except Exception as exc:
            return ToolError(
                output="",
                message=str(exc),
                brief="Failed to delete file or directory",
            )
