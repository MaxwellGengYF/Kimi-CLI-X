from kimi_agent_sdk import CallableTool2, ToolError, ToolOk, ToolReturnValue
from pydantic import BaseModel, Field


class Params(BaseModel):
    path: str = Field(
        description="The path of the directory to create.",
    )
    parents: bool = Field(
        default=False,
        description="If True, create parent directories as needed. If False, raise an error if parent directories do not exist.",
    )


class Mkdir(CallableTool2):
    name: str = "Mkdir"
    description: str = "Create a directory on the target path."
    params: type[Params] = Params

    async def __call__(self, params: Params) -> ToolReturnValue:
        import os
        
        try:
            if params.parents:
                os.makedirs(params.path, exist_ok=True)
            else:
                os.mkdir(params.path)
            return ToolOk(output=f"Directory created: {params.path}")
        except Exception as exc:
            return ToolError(
                output="",
                message=str(exc),
                brief="Failed to create directory",
            )
