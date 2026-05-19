import asyncio
import sys
import os
import tempfile

import anyio
from kimix.tools.common import _maybe_export_output_async, _export_to_temp_file_async, ProcessTask
from kimi_agent_sdk import CallableTool2, ToolError, ToolOk, ToolReturnValue
from pydantic import BaseModel, Field
from kimi_cli.session import Session
from kimix.base import colorful_text, Color


class Params(BaseModel):
    code: str = Field(
        description="Python code to execute.",
    )
    output_path: str | None = Field(
        default=None,
        description="Output file path."
    )
    timeout: int = Field(
        default=10,
        ge=3,
        le=60,
        description="Timeout in seconds."
    )


class Python(CallableTool2[Params]):
    name: str = "Python"
    description: str = "Execute Python code."
    params: type[Params] = Params

    def __init__(self, session: Session):
        super().__init__()
        self._session = session
        self._semaphore = asyncio.Semaphore(8)

    async def __call__(self, params: Params) -> ToolReturnValue:
        async with self._semaphore:
            # Force UTF-8 encoding for subprocess on Windows and Unix
            env = {"PYTHONIOENCODING": "utf-8"}
            script_path: str | None = None

            # Windows CreateProcessW has a ~32767 char command-line limit.
            # Use a temp file for very long code to avoid truncation/failure.
            if len(params.code) > 30000:
                with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
                    f.write(params.code)
                    script_path = f.name
                args = [script_path]
            else:
                args = ['-c', params.code]

            task = ProcessTask(sys.executable, args, env=env)
            task_id = await task.start(self._session, "python", "python")

            # Wait for completion with timeout (allow a small buffer for cleanup)
            wait_timeout = params.timeout
            await task.wait(wait_timeout)

            if await task.thread_is_alive():
                output = await task.stream.get_output() if task.stream else ""
                return ToolError(
                    output=output,
                    message=f"Running in background. task_id: `{task_id}`. use `TaskOutput` or `Input`",
                    brief="Timeout"
                )
            # Clean up foreground task registration
            from kimix.tools.background.utils import remove_task_id
            remove_task_id(self._session, task_id)
            # Get output
            output = await task.stream.pop_output() if task.stream else ""

            # Clean up temp file since process has finished
            if script_path is not None:
                try:
                    os.remove(script_path)
                except Exception:
                    pass

            # Handle output_path parameter if provided
            if params.output_path:
                async with await anyio.open_file(params.output_path, 'w', encoding='utf-8', errors='replace') as f:
                    await f.write(output)
                output = f'output exported to: {params.output_path}'
            else:
                output = await _maybe_export_output_async(output)

            # Check success
            success = await task.stream.success() if task.stream else False



            if not success:
                if output and not params.output_path:
                    temp_path, _ = await _export_to_temp_file_async(key=None, content=output, ext='.txt')
                    output = f'saved to file `{temp_path}`'
                return ToolError(
                    output=output,
                    message="Python execution failed",
                    brief="Python execution error"
                )

            colored_code = colorful_text(params.code, fg=Color.BLACK)
            return ToolOk(output=f"{colored_code}\n\n{output}")
