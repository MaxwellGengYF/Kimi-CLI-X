import asyncio
import queue
import threading
from kimi_agent_sdk import CallableTool2, ToolError, ToolOk, ToolReturnValue
from pydantic import BaseModel, Field
from kimi_cli.session import Session
from kimix.utils import prompt, close_session_async, _create_session_async
from my_tools.common import _maybe_export_output_async
from my_tools.background.utils import BackgroundStream, generate_task_id, add_task

# Thread-local storage to track SubAgentScope context
_sub_agent_scope = threading.local()


class SubAgentParams(BaseModel):
    prompt: str = Field(
        description="Task instructions for the sub-agent."
    )
    thinking: bool = Field(
        default=False,
        description="Enable deep-thinking mode for complex tasks."
    )
    run_in_background: bool = Field(
        default=False,
        description="Run in an independent background process. Returns immediately with a task_id. Use TaskList, TaskOutput to manage."
    )


class Agent(CallableTool2):
    name: str = "Agent"
    description: str = "Launch a sub-agent for a task."
    params: type[SubAgentParams] = SubAgentParams

    def __init__(self, session: Session):
        super().__init__()
        self._session = session

    async def __call__(self, params: SubAgentParams) -> ToolReturnValue:
        # Handle background execution
        if params.run_in_background:
            return await self._run_in_background(params)

        # Check if already inside a SubAgentScope
        if getattr(_sub_agent_scope, 'active', False):
            return ToolError(
                output="",
                message="You are a sub-agent, SubAgent cannot be called within this scope.",
                brief="Nested SubAgent call detected",
            )

        try:
            output_strs = []

            def output_function(fn: str, is_thinking: bool) -> None:
                # Main agent no need to get thinking-output
                if fn and not is_thinking:
                    output_strs.append(fn)

            async def prompt_async(cancel_callable=None):
                session = None
                try:
                    import kimix.base as base
                    _sub_agent_scope.active = True
                    session = await _create_session_async(
                        thinking=params.thinking,
                        plan_mode=False,
                        agent_file=base._default_agent_file_dir / 'agent_subagent.yaml', is_sub_agent=True)
                    import kimix.utils as utils
                    await utils.prompt_async(prompt_str=params.prompt, session=session, output_function=output_function, cancel_callable=cancel_callable)
                except Exception as e:
                    return str(e)
                finally:
                    if session:
                        await close_session_async(session)
                    _sub_agent_scope.active = False
                return None

            err_msg = await prompt_async()
            output = await _maybe_export_output_async('\n'.join(output_strs))
            if err_msg:
                return ToolError(output=output, message=err_msg, brief='')
            return ToolOk(output=output)
        except Exception as exc:
            return ToolError(
                output="",
                message=str(exc),
                brief="Failed to create session",
            )

    async def _run_in_background(self, params: SubAgentParams) -> ToolReturnValue:
        """Run the sub-agent in the background and register it as a background task.

        Args:
            params: The sub-agent parameters.

        Returns:
            ToolOk with task_id on success, ToolError on failure.
        """
        # Check if already inside a SubAgentScope
        if getattr(_sub_agent_scope, 'active', False):
            return ToolError(
                output="",
                message="You are a sub-agent, SubAgent cannot be called within this scope.",
                brief="Nested SubAgent call detected",
            )

        # Shared state for stopping the task
        _stop_event = threading.Event()

        def run_agent_bg(q: queue.Queue[str]) -> bool:
            """Run the sub-agent and collect output into the queue."""
            try:
                if _stop_event.is_set():
                    return False

                output_strs = []

                def output_function(fn: str, is_thinking: bool) -> None:
                    if fn and (not is_thinking):
                        output_strs.append(fn)

                async def prompt_async(cancel_callable=None):
                    session = None
                    try:
                        import kimix.base as base
                        _sub_agent_scope.active = True
                        session = await _create_session_async(
                            thinking=params.thinking,
                            plan_mode=False,
                            agent_file=base._default_agent_file_dir / 'agent_subagent.yaml')
                        import kimix.utils as utils
                        await utils.prompt_async(prompt_str=params.prompt, session=session,
                                                output_function=output_function, cancel_callable=cancel_callable)
                    except Exception as e:
                        return str(e)
                    finally:
                        if session:
                            await close_session_async(session)
                        _sub_agent_scope.active = False
                    return None

                err_msg = asyncio.run(prompt_async(_stop_event.is_set))

                # Collect output
                output = '\n'.join(output_strs)
                if output:
                    q.put_nowait(output)

                if err_msg:
                    q.put_nowait(f"\n[Error: {err_msg}]")
                    return False
                else:
                    q.put_nowait("\n[Sub-agent completed]")
                    return True

            except Exception as e:
                q.put_nowait(f"\n[Error: {str(e)}]")
                return False
            finally:
                _stop_event.set()

        def stop_function():
            """Signal the background task to stop."""
            _stop_event.set()

        try:
            # Create and start the background stream
            stream = BackgroundStream()
            task_id = generate_task_id(self._session, "agent", "subagent")
            stream.start(run_agent_bg, stop_function)
            # Register the task
            add_task(self._session, task_id, stream)

            return ToolOk(
                output=f"Sub-agent started in background.\nTask ID: {task_id}\n\nUse 'TaskList' to view all tasks, 'TaskOutput' to get output, 'TaskWait' to wait for completion, 'TaskStop' to stop the sub-agent."
            )

        except Exception as exc:
            return ToolError(
                output="",
                message=f"Failed to start background sub-agent: {str(exc)}",
                brief="Failed to start background task"
            )
