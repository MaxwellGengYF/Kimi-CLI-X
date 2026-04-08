import asyncio
import threading
from kimi_agent_sdk import CallableTool2, ToolError, ToolOk, ToolReturnValue
from pydantic import BaseModel, Field
from kimi_utils import prompt, create_session, close_session
from my_tools.common import _maybe_export_output

# Thread-local storage to track SubAgentScope context
_sub_agent_scope = threading.local()


class SubAgentParams(BaseModel):
    prompt: str = Field(
        description="The prompt to send to the sub-agent",
    )
    thinking: bool = Field(
        default=False,
        description='Enable deep-thinking mode, default false'
    )
    # thinking:


class SubAgent(CallableTool2):
    name: str = "SubAgent"
    description: str = "Create a sub-agent."
    params: type[SubAgentParams] = SubAgentParams

    async def __call__(self, params: SubAgentParams) -> ToolReturnValue:
        # Check if already inside a SubAgentScope
        if getattr(_sub_agent_scope, 'active', False):
            return ToolError(
                output="",
                message="You are a sub-agent, SubAgent cannot be called within this scope.",
                brief="Nested SubAgent call detected",
            )

        try:
            output_strs = []

            def output_function(fn):
                if fn:
                    output_strs.append(fn)

            def prompt_func():
                session = None
                try:
                    _sub_agent_scope.active = True
                    session = create_session(
                        thinking=params.thinking,
                        plan_mode=False)
                    prompt(prompt_str=params.prompt, session=session,
                           output_function=output_function)
                except Exception as e:
                    return str(e)
                finally:
                    if session:
                        close_session(session)
                    _sub_agent_scope.active = False
                return None

            err_msg = await asyncio.to_thread(prompt_func)
            output = _maybe_export_output('\n'.join(output_strs))
            if err_msg:
                return ToolError(output=output, message=err_msg, brief='')
            return ToolOk(output=output)
        except Exception as exc:
            return ToolError(
                output="",
                message=str(exc),
                brief="Failed to create session",
            )
