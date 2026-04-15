
import anyio
from kimi_agent_sdk import CallableTool2, ToolError, ToolOk, ToolReturnValue
from pydantic import BaseModel, Field
from my_tools.common import _maybe_export_output_async

from my_tools.file.chdir import Cd

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
            await anyio.to_thread.run_sync(lambda: os.makedirs(params.path, exist_ok=True))
            return ToolOk(output=await _maybe_export_output_async(f"Directory created: {params.path}", params.path))
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

        def _remove():
            if os.path.isdir(params.path):
                shutil.rmtree(params.path)
            else:
                os.remove(params.path)

        try:
            await anyio.to_thread.run_sync(_remove)
            return ToolOk(output=await _maybe_export_output_async(f"Deleted: {params.path}"))
        except Exception as exc:
            return ToolError(
                output="",
                message=str(exc),
                brief="Failed to delete file or directory",
            )
