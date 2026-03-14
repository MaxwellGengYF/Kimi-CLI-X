from kimi_agent_sdk import CallableTool2, ToolError, ToolOk, ToolReturnValue
from pydantic import BaseModel, Field


class Params(BaseModel):
    code: str = Field(
        description="The Python code to execute.",
    )
    globals_dict: dict = Field(
        default={},
        description="Global variables to provide to the exec context.",
    )
    locals_dict: dict = Field(
        default={},
        description="Local variables to provide to the exec context.",
    )


class Python(CallableTool2):
    name: str = "Python"
    description: str = "Execute Python code using exec function."
    params: type[Params] = Params

    async def __call__(self, params: Params) -> ToolReturnValue:
        try:
            exec(params.code, params.globals_dict, params.locals_dict)
            return ToolOk(output="Code executed successfully.")
        except Exception as exc:
            return ToolError(
                output="",
                message=str(exc),
                brief="Failed to execute Python code",
            )
