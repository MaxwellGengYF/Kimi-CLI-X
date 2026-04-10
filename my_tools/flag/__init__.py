from kimi_agent_sdk import CallableTool2, ToolError, ToolOk, ToolReturnValue
from pydantic import BaseModel, Field
import threading

_flag = threading.local()


def reset_flag() -> None:
    global _flag
    _flag.value = None


def check_flag() -> str:
    global _flag
    return getattr(_flag, 'value', None)


class Params(BaseModel):
    value: str = Field(default="1", description="Value to assign to the flag.")


class SetValue(CallableTool2):
    name: str = "SetValue"
    description: str = "Set a thread-local flag value."
    params: type[Params] = Params

    async def __call__(self,  params: Params) -> ToolReturnValue:
        global _flag
        _flag.value = params.value
        return ToolOk(output=f"")
