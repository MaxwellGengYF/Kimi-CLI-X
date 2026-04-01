import os
import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import override

import kaos
from kaos import AsyncReadable
from kosong.tooling import CallableTool2, ToolReturnValue
from pydantic import BaseModel, Field

from kimi_cli.soul.approval import Approval
from kimi_cli.tools.display import ShellDisplayBlock
from kimi_cli.tools.utils import ToolRejectedError, ToolResultBuilder, load_desc
from kimi_cli.utils.environment import Environment
from kimi_cli.utils.subprocess_env import get_clean_env
import sys
from my_tools.common import _maybe_export_output

MIN_TIMEOUT = 10 * 60
MAX_TIMEOUT = 15 * 60


def _check_command_exists(command: str) -> bool:
    """Check if a command exists in the system PATH."""
    import shutil
    return shutil.which(command) is not None


class Params(BaseModel):
    command: str = Field(description="The command to execute.")
    timeout: int = Field(
        description=(
            "The timeout in seconds for the command to execute. "
            "If the command takes longer than this, it will be killed."
        ),
        default=60,
        ge=1,
        le=MAX_TIMEOUT,
    )


class BaseShell(CallableTool2[Params]):
    """Base class for shell execution tools."""
    
    params: type[Params] = Params

    def __init__(self, name: str, description: str, approval: Approval, shell_path: str, shell_name: str):
        super().__init__(
            name=name,
            description=load_desc(
                Path(__file__).parent / description,
                {"SHELL": f"{shell_name} (`{shell_path}`)"},
            )
        )
        self._approval = approval
        self._shell_path = shell_path

    @override
    async def __call__(self, params: Params) -> ToolReturnValue:
        builder = ToolResultBuilder()

        if not params.command:
            return builder.error("Command cannot be empty.", brief="Empty command")

        command = params.command
        timeout = max(params.timeout, MIN_TIMEOUT)
        
        if not await self._approval.request(
            self.name,
            "run command",
            f"Run command `{command}`",
            display=[
                ShellDisplayBlock(
                    language=self._get_language(),
                    command=command,
                )
            ],
        ):
            return ToolRejectedError()

        def stdout_cb(line: bytes):
            line_str = line.decode(encoding="utf-8", errors="replace")
            builder.write(_maybe_export_output(line_str))

        def stderr_cb(line: bytes):
            line_str = line.decode(encoding="utf-8", errors="replace")
            builder.write(_maybe_export_output(line_str))

        try:
            exitcode = await self._run_shell_command(
                command, stdout_cb, stderr_cb, timeout
            )

            if exitcode == 0:
                return builder.ok("Command executed successfully.")
            else:
                return builder.error(
                    f"Command failed with exit code: {exitcode}.",
                    brief=f"Failed with exit code: {exitcode}",
                )
        except TimeoutError:
            return builder.error(
                f"Command killed by timeout ({timeout}s)",
                brief=f"Killed by timeout ({timeout}s)",
            )

    async def _run_shell_command(
        self,
        command: str,
        stdout_cb: Callable[[bytes], None],
        stderr_cb: Callable[[bytes], None],
        timeout: int,
    ) -> int:
        async def _read_stream(stream: AsyncReadable, cb: Callable[[bytes], None]):
            while True:
                line = await stream.readline()
                if line:
                    cb(line)
                else:
                    break

        process = await kaos.exec(*self._shell_args(command), env=get_clean_env())
        try:
            await asyncio.wait_for(
                asyncio.gather(
                    _read_stream(process.stdout, stdout_cb),
                    _read_stream(process.stderr, stderr_cb),
                ),
                timeout,
            )
            return await process.wait()
        except TimeoutError:
            await process.kill()
            raise

    def _get_language(self) -> str:
        """Get the display language for the shell."""
        raise NotImplementedError

    def _shell_args(self, command: str) -> tuple[str, ...]:
        """Get the shell arguments for executing a command."""
        raise NotImplementedError


class PowerShell(BaseShell):
    """PowerShell execution tool."""

    def __init__(self, approval: Approval, environment: Environment):
        # Determine PowerShell executable
        if sys.platform == "win32":
            if _check_command_exists("pwsh"):
                shell_path = "pwsh"
                shell_name = "PowerShell Core"
            else:
                shell_path = "powershell"
                shell_name = "Windows PowerShell"
        else:
            shell_path = "pwsh" if _check_command_exists("pwsh") else "powershell"
            shell_name = "PowerShell Core" if shell_path == "pwsh" else "PowerShell"
        
        # Use environment shell_path if available and it's PowerShell
        if hasattr(environment, 'shell_path') and environment.shell_path:
            env_shell = str(environment.shell_path).lower()
            if "powershell" in env_shell or "pwsh" in env_shell:
                shell_path = str(environment.shell_path)
        if hasattr(environment, 'shell_name') and environment.shell_name:
            if "powershell" in environment.shell_name.lower():
                shell_name = environment.shell_name

        super().__init__(
            name="PowerShell",
            description="powershell.md",
            approval=approval,
            shell_path=shell_path,
            shell_name=shell_name,
        )

    def _get_language(self) -> str:
        return "powershell"

    def _shell_args(self, command: str) -> tuple[str, ...]:
        return (str(self._shell_path), "-command", command)


class Bash(BaseShell):
    """Bash execution tool."""

    def __init__(self, approval: Approval, environment: Environment):
        # Determine Bash executable
        if sys.platform == "win32":
            # On Windows, try to find bash (Git Bash, WSL, etc.)
            shell_path = "bash"
            if hasattr(environment, 'shell_path') and environment.shell_path:
                env_shell = str(environment.shell_path).lower()
                if "bash" in env_shell:
                    shell_path = str(environment.shell_path)
        else:
            shell_path = "/bin/bash"
            if hasattr(environment, 'shell_path') and environment.shell_path:
                shell_path = str(environment.shell_path)
        
        shell_name = "Bash"
        if hasattr(environment, 'shell_name') and environment.shell_name:
            if "bash" in environment.shell_name.lower():
                shell_name = environment.shell_name

        super().__init__(
            name="Bash",
            description="bash.md",
            approval=approval,
            shell_path=shell_path,
            shell_name=shell_name,
        )

    def _get_language(self) -> str:
        return "bash"

    def _shell_args(self, command: str) -> tuple[str, ...]:
        return (str(self._shell_path), "-c", command)
