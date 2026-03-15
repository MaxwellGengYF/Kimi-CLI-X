from kimi_agent_sdk import CallableTool2, ToolError, ToolOk, ToolReturnValue
from pydantic import BaseModel, Field
from kimi_utils import create_session, async_prompt

_sessions = {}


class CreateSessionParams(BaseModel):
    prompt: str = Field(
        description="The prompt to send to the agent session.",
    )
    session_id: str = Field(
        default=None,
        description="The session ID. If not provided, a default ID will be generated.",
    )


class CreateSession(CallableTool2):
    name: str = "CreateSession"
    description: str = "Create a new agent session and run a prompt asynchronously."
    params: type[CreateSessionParams] = CreateSessionParams

    async def __call__(self, params: CreateSessionParams) -> ToolReturnValue:
        global _sessions
        
        try:
            # Create a new session
            session = create_session(session_id=params.session_id)
            
            # Get the session_id (in case it was auto-generated)
            sid = params.session_id if params.session_id else str(len(_sessions))
            
            # Run the prompt asynchronously
            process = async_prompt(params.prompt, session)
            
            # Save the process to global _sessions dict
            _sessions[sid] = {
                "session": session,
                "process": process,
                "finished": False,
            }
            
            return ToolOk(output=f"Session '{sid}' created and prompt is running asynchronously.")
        except Exception as exc:
            return ToolError(
                output="",
                message=str(exc),
                brief=f"Failed to create session",
            )


class WaitSessionParams(BaseModel):
    session_id: str = Field(
        description="The session ID to wait for.",
    )
    timeout: float = Field(
        default=None,
        description="Timeout in seconds. If not provided, wait indefinitely.",
    )


class WaitSession(CallableTool2):
    name: str = "WaitSession"
    description: str = "Wait for a session to finish."
    params: type[WaitSessionParams] = WaitSessionParams

    async def __call__(self, params: WaitSessionParams) -> ToolReturnValue:
        global _sessions
        
        try:
            if params.session_id not in _sessions:
                return ToolError(
                    output="",
                    message=f"Session '{params.session_id}' not found in _sessions.",
                    brief="Session not found",
                )
            
            session_info = _sessions[params.session_id]
            if session_info["finished"]:
                return ToolOk(output=f"Session '{params.session_id}' finished.")
            process = session_info["process"]
            
            # Wait for the process to finish
            if params.timeout:
                process.join(timeout=params.timeout)
                if process.is_alive():
                    return ToolOk(output=f"Timeout reached while waiting for session '{params.session_id}'.")
            else:
                process.join()
            
            # Mark as finished
            session_info["finished"] = True
            
            # Close the session
            from kimi_utils import close_session
            close_session(session_info["session"])
            del session_info["process"]
            del session_info["session"]
            
            return ToolOk(output=f"Session '{params.session_id}' finished.")
        except Exception as exc:
            return ToolError(
                output="",
                message=str(exc),
                brief=f"Failed to wait for session",
            )
