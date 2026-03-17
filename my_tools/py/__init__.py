from kimi_agent_sdk import CallableTool2, ToolError, ToolOk, ToolReturnValue
from pydantic import BaseModel, Field


class Params(BaseModel):
    code: str = Field(
        description="The Python code to execute. ",
    )


class Python(CallableTool2):
    name: str = "Python"
    description: str = "Execute Python code using exec function."
    params: type[Params] = Params
    globals_dict = dict()
    locals_dict = dict()

    async def __call__(self, params: Params) -> ToolReturnValue:
        try:
            exec(params.code, self.globals_dict, self.locals_dict)
            return ToolOk(output="Code executed successfully.")
        except Exception as exc:
            return ToolError(
                output="",
                message=str(exc),
                brief="Failed to execute Python code",
            )
