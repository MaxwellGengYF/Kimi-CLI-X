from kimi_agent_sdk import CallableTool2, ToolError, ToolOk, ToolReturnValue
from pydantic import BaseModel, Field
from kimi_utils import prompt
from my_tools.common import _maybe_export_output
class SubAgentParams(BaseModel):
    prompt: str = Field(
        description="The prompt to send to the sub-agent.",
    )

class SubAgent(CallableTool2):
    name: str = "SubAgent"
    description: str = "Create a sub-agent."
    params: type[SubAgentParams] = SubAgentParams

    async def __call__(self, params: SubAgentParams) -> ToolReturnValue:
        global _sessions
        try:
            # Sub-agent should disable thinking, ralph, enable yolo
            # Run the prompt asynchronously
            prompt(_maybe_export_output(params.prompt), False)
            return ToolOk(output=f"")
        except Exception as exc:
            return ToolError(
                output="",
                message=str(exc),
                brief=f"Failed to create session",
            )

