from kimi_agent_sdk import CallableTool2, ToolError, ToolOk, ToolReturnValue
from pydantic import BaseModel, Field


class Params(BaseModel):
    source: str = Field(
        description="The source file or directory to move.",
    )
    destination: str = Field(
        description="The destination path to move to.",
    )


class Move(CallableTool2):
    name: str = "Move"
    description: str = "Move a directory or file to another path."
    params: type[Params] = Params

    async def __call__(self, params: Params) -> ToolReturnValue:
        import shutil
        
        try:
            shutil.move(params.source, params.destination)
            return ToolOk(output=f"Moved '{params.source}' to '{params.destination}'")
        except Exception as exc:
            return ToolError(
                output="",
                message=str(exc),
                brief="Failed to move file or directory",
            )
