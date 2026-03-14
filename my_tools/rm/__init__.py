from kimi_agent_sdk import CallableTool2, ToolError, ToolOk, ToolReturnValue
from pydantic import BaseModel, Field


class Params(BaseModel):
    path: str = Field(
        description="The file or directory path to remove.",
    )
    recursive: bool = Field(
        default=False,
        description="If True, remove directories recursively. Required for non-empty directories.",
    )


class Remove(CallableTool2):
    name: str = "Remove"
    description: str = "Remove a file or directory."
    params: type[Params] = Params

    async def __call__(self, params: Params) -> ToolReturnValue:
        import os
        import shutil
        
        try:
            if not os.path.exists(params.path):
                return ToolError(
                    output="",
                    message=f"Path does not exist: {params.path}",
                    brief="Path not found",
                )
            
            if os.path.isdir(params.path):
                if params.recursive:
                    shutil.rmtree(params.path)
                else:
                    os.rmdir(params.path)
            else:
                os.remove(params.path)
            
            return ToolOk(output=f"Removed: {params.path}")
        except Exception as exc:
            return ToolError(
                output="",
                message=str(exc),
                brief="Failed to remove path",
            )
