"""run tool for executing a process from a path."""
import anyio
import asyncio
from pathlib import Path
import shlex
import sys
import tempfile

from kimi_agent_sdk import CallableTool2, ToolError, ToolOk, ToolReturnValue
from pydantic import BaseModel, Field
from kimi_cli.session import Session
from kimix.tools.common import _maybe_export_output_async, _export_to_temp_file_async, ProcessTask
from kimix.tools.file.bash import _BASH_COMMANDS, _WINDOWS_ALIASES
from kimix.tools.file.bash.run_bash import run_bash
from kimi_cli.tools.display import ShellDisplayBlock

_HUGE_CMD_THRESHOLD = 10000
"""Character count above which command display is culled to only the path."""

_DEFAULT_FORBIDDEN_COMMANDS = [
    "taskkill",
    "kill",
    "killall",
    "pkill",
    "xkill",
    "rd",
    "format",
    "fdisk",
    "dd",
    "mkfs",
    "shutdown",
    "reboot",
    "poweroff",
    "halt",
    "reg",
    "regedit",
    "regedt32",
]


class RunParams(BaseModel):
    path: str = Field(
        description="Executable path."
    )
    args: list[str] = Field(
        default_factory=list,
        description="Command arguments."
    )
    timeout: int = Field(
        default=10,
        ge=3,
        le=300,
        description="Timeout in seconds."
    )
    output_path: str | None = Field(
        default=None,
        description="Output file path."
    )
    cwd: str | None = Field(
        default=None,
        description="Working directory."
    )
    env: list[str] | None = Field(
        default=None,
        description="Environment variables to set for the subprocess, in 'KEY=VALUE' format. If no '=' is present, the value is set to '1'."
    )
    run_in_background: bool = Field(
        default=False,
        description="Run the process in the background and return immediately."
    )

class Run(CallableTool2[RunParams]):
    name: str = "Run"
    description: str = "Run an executable or bash command."
    params: type[RunParams] = RunParams

    def __init__(self, session: Session):
        import os
        os.environ['PYTHONIOENCODING'] = 'utf-8'
        super().__init__()
        self._session = session
        self._semaphore = asyncio.Semaphore(8)


    async def __call__(self, params: RunParams) -> ToolReturnValue:
        import os
        script_path: str | None = None
        try:
            # params.path may contain arguments, split it respecting quotes, then insert to the start of params.args
            # Try progressively longer prefixes to find an existing file, so paths with spaces are handled.
            if " " in params.path:
                try:
                    parts = shlex.split(params.path)
                except ValueError:
                    parts = params.path.split(" ")
                candidate = parts[0]
                for i in range(1, len(parts)):
                    candidate += " " + parts[i]
                    try:
                        is_file = Path(candidate).is_file()
                    except OSError:
                        is_file = False
                    if is_file:
                        params.path = candidate
                        remaining = parts[i + 1 :]
                        if remaining:
                            params.args = remaining + params.args
                        break
                else:
                    params.path = parts[0]
                    remaining = parts[1:]
                    if remaining:
                        params.args = remaining + params.args

            display_args = [arg[:100] + '...' if len(arg) > 100 else arg for arg in params.args]
            cmd_str = shlex.join([params.path] + display_args)
            display_cmd = params.path if len(cmd_str) > _HUGE_CMD_THRESHOLD else cmd_str

            # Check forbidden commands (default + user-configured)
            forbidden_commands = _DEFAULT_FORBIDDEN_COMMANDS + self._session.custom_config.get("config_json", {}).get("forbidden_commands", [])
            if forbidden_commands:
                full_cmd = " ".join([params.path] + params.args)
                normalized_cmd = " ".join(full_cmd.split())
                cmd_tokens = normalized_cmd.split()
                for forbidden in forbidden_commands:
                    if not isinstance(forbidden, str) or not forbidden:
                        continue
                    normalized_forbidden = " ".join(forbidden.split())
                    forbidden_tokens = normalized_forbidden.split()
                    if len(forbidden_tokens) > len(cmd_tokens):
                        continue
                    if cmd_tokens[:len(forbidden_tokens)] == forbidden_tokens:
                        return ToolError(
                            output="",
                            message=f"Command `{full_cmd}` is forbidden by config rule: `{forbidden}`.",
                            brief=display_cmd,
                        )

            # Check if params.path is a valid process name first (executable in PATH or existing file),
            # then fall back to bash built-in commands.
            import shutil

            is_process = False
            is_py = False
            if (params.path == 'python' and (shutil.which('python') is None) and (not Path('./python').exists())) or (params.path == 'python.exe' and (shutil.which('python.exe') is None) and (not Path('./python.exe').exists())):
                params.path = sys.executable
                is_process = True
                is_py = True
            elif os.sep in params.path or "/" in params.path:
                # Contains path separator - check if it's an existing file
                is_process = Path(params.path).is_file()
            else:
                # Bare command name - check if it's in PATH
                is_process = shutil.which(params.path) is not None

            if not is_process:
                # Not a real process - check if it's a bash built-in command.
                # Check original command name first, then try Windows alias.
                warning = " WARNING: This tool does not support shell commands; use `Python` tool."
                if params.path in _BASH_COMMANDS:
                    result = await run_bash(params, self._session)
                    return ToolReturnValue(
                        is_error=result.is_error,
                        message=(result.message or "") + warning, brief=result.brief or "", output=result.output,
                        display=result.display
                    )
                bash_name = _WINDOWS_ALIASES.get(params.path, params.path)
                if bash_name in _BASH_COMMANDS:
                    result = await run_bash(params, self._session)
                    return ToolReturnValue(
                        is_error=result.is_error,
                        message=(result.message or "") + warning, brief=result.brief or "", output=result.output,
                        display=result.display
                    )
                else:
                    return ToolError(
                        output="",
                        message=f"Command not found: '{params.path}' is not a valid executable or bash built-in command." + warning,
                        brief=display_cmd,
                    )


            # Handle extremely long python -c scripts via temp file (Windows CreateProcessW ~32767 limit)
            if is_py:
                c_idx = next((i for i, a in enumerate(params.args) if a == '-c'), None)
                if c_idx is not None and c_idx + 1 < len(params.args) and len(params.args[c_idx + 1]) > 30000:
                    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
                        f.write(params.args[c_idx + 1])
                        script_path = f.name
                    # Replace -c <code> with <script_path>, preserving leading options and trailing args
                    params.args = params.args[:c_idx] + [script_path] + params.args[c_idx + 2:]

            async with self._semaphore:
                env_dict: dict[str, str] | None = None
                if params.env:
                    env_dict = {}
                    for item in params.env:
                        if '=' in item:
                            key, value = item.split('=', 1)
                            env_dict[key] = value
                        else:
                            env_dict[item] = '1'
                task = ProcessTask(params.path, params.args, params.cwd, env_dict)
                task_id = await task.start(self._session, "run", Path(params.path).stem)

                if params.run_in_background:
                    return ToolOk(
                        output=f"Running in background. task_id: `{task_id}`. Use `TaskOutput` tool to retrieve output.",
                        brief="Background task started",
                        display_block=ShellDisplayBlock(language="shell", command=display_cmd),
                    )

                # Wait for completion with timeout (allow a small buffer for cleanup)
                wait_timeout = params.timeout
                await task.wait(wait_timeout)
                
                if await task.thread_is_alive():
                    output = await task.stream.get_output() if task.stream else ""
                    return ToolError(
                        output=output,
                        message=f"Running in background. task_id: `{task_id}`. use `TaskOutput` or `Input`",
                        brief=display_cmd,
                    )
                # Clean up foreground task registration
                from kimix.tools.background.utils import remove_task_id
                remove_task_id(self._session, task_id)

                # Get output
                output = await task.stream.pop_output() if task.stream else ""

                # Clean up temp file since process has finished
                # Handle output export if needed
                if params.output_path:
                    async with await anyio.open_file(params.output_path, 'w', encoding='utf-8', errors='replace') as f:
                        await f.write(output)
                    output = f'saved to file `{params.output_path}`'
                
                # Check success
                success = await task.stream.success() if task.stream else False

                if not success:
                    if output and not params.output_path:
                        temp_path, _ = await _export_to_temp_file_async(key=None, content=output, ext='.txt')
                        output = f'saved to file `{temp_path}`'
                    return ToolError(
                        output=output,
                        message="Command execution failed",
                        brief=display_cmd,
                    )

                output = await _maybe_export_output_async(output)
                return ToolOk(
                    output=output,
                    brief="Command executed successfully",
                    display_block=ShellDisplayBlock(language="shell", command=display_cmd),
                )
        except Exception as e:
            return ToolError(
                output='',
                message='Internal error, quit current session now.',
                brief='Internal error'
            )
        finally:
            if script_path is not None:
                try:
                    os.remove(script_path)
                except Exception:
                    pass

