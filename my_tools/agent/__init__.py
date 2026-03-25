from kimi_agent_sdk import CallableTool2, ToolError, ToolOk, ToolReturnValue
from pydantic import BaseModel, Field
from kimi_utils import prompt, _create_session_async

class CreateSessionParams(BaseModel):
    prompt: str = Field(
        description="The prompt to send to the agent session.",
    )

class CreateAgent(CallableTool2):
    name: str = "CreateAgent"
    description: str = "Create a new agent session and run a prompt asynchronously."
    params: type[CreateSessionParams] = CreateSessionParams

    async def __call__(self, params: CreateSessionParams) -> ToolReturnValue:
        global _sessions
        try:
            # Sub-agent should disable thinking, ralph, enable yolo
            # Run the prompt asynchronously
            prompt(params.prompt, False)
            return ToolOk(output=f"")
        except Exception as exc:
            return ToolError(
                output="",
                message=str(exc),
                brief=f"Failed to create session",
            )

