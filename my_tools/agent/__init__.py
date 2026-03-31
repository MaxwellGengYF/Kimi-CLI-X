from kimi_agent_sdk import CallableTool2, ToolError, ToolOk, ToolReturnValue
from pydantic import BaseModel, Field
from kimi_utils import prompt, _create_session_async
from pathlib import Path

class CreateAgentParams(BaseModel):
    prompt_path: str = Field(
        description="The path to the prompt file to send to the agent session.",
    )

class CreateAgent(CallableTool2):
    name: str = "CreateAgent"
    description: str = "Create a sub-agent."
    params: type[CreateAgentParams] = CreateAgentParams

    async def __call__(self, params: CreateAgentParams) -> ToolReturnValue:
        global _sessions
        try:
            # Sub-agent should disable thinking, ralph, enable yolo
            # Run the prompt asynchronously
            prompt_content = Path(params.prompt_path).read_text(encoding='utf-8')
            prompt(prompt_content, False)
            return ToolOk(output=f"")
        except Exception as exc:
            return ToolError(
                output="",
                message=str(exc),
                brief=f"Failed to create session",
            )

