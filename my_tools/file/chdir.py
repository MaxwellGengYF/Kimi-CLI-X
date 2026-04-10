"""Chdir tool for changing the current working directory."""
import os

from kimi_agent_sdk import CallableTool2, ToolError, ToolOk, ToolReturnValue
from pydantic import BaseModel, Field


class CdParams(BaseModel):
    path: str = Field(
        description="Target directory."
    )


class Cd(CallableTool2):
    name: str = "Cd"
    description: str = "Change working directory."
    params: type[CdParams] = CdParams

    async def __call__(self, params: CdParams) -> ToolReturnValue:
        """Change the current working directory using os.chdir."""
        try:
            os.chdir(params.path)
            return ToolOk(
                output="",
                message=f"Changed directory to: {os.getcwd()}",
                brief="Directory changed",
            )
        except FileNotFoundError:
            return ToolError(
                output="",
                message=f"Directory not found: {params.path}",
                brief="Directory not found",
            )
        except PermissionError:
            return ToolError(
                output="",
                message=f"Permission denied: {params.path}",
                brief="Permission denied",
            )
        except Exception as exc:
            return ToolError(
                output="",
                message=f"Failed to change directory: {str(exc)}",
                brief="Chdir failed",
            )
