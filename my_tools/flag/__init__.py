from kimi_agent_sdk import CallableTool2, ToolError, ToolOk, ToolReturnValue
from pydantic import BaseModel, Field
import threading

_flag = threading.local()


def reset_flag() -> None:
    global _flag
    _flag.flag = False


def check_flag() -> bool:
    global _flag
    return hasattr(_flag, 'flag') and _flag.flag == True


def _set_flag(value) -> bool:
    global _flag
    _flag.flag = value == True


class FlagParams(BaseModel):
    pass


class SetFlag(CallableTool2):
    name: str = "SetFlag"
    description: str = "Set the flag"
    params: type[FlagParams] = FlagParams

    async def __call__(self,  params: FlagParams) -> ToolReturnValue:
        global _flag
        _flag.flag = True
        return ToolOk(output=f"ok")
