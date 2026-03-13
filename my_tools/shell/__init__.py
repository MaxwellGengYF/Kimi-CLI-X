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
MIN_TIMEOUT = 10 * 60
MAX_TIMEOUT = 15 * 60
# On Windows platform, check if pwsh (PowerShell Core) exists
def _check_command_exists(command: str) -> bool:
    """Check if a command exists in the system PATH."""
    import shutil
    return shutil.which(command) is not None
# Try to use cmd, should be faster
_default_pwsh = 'cmd'
# _default_pwsh = 'powershell'
# if sys.platform == 'win32':
#     if not _check_command_exists('pwsh'):
#         print("PowerShell Core (pwsh) not found. Falling back to Windows PowerShell (powershell).")
#     else:
#         _default_pwsh = 'pwsh'

class Params(BaseModel):
    command: str = Field(description="The bash command to execute.")
    timeout: int = Field(
        description=(
            "The timeout in seconds for the command to execute. "
            "If the command takes longer than this, it will be killed."
        ),
        default=60,
        ge=1,
        le=MAX_TIMEOUT,
    )

def parse_command(command: str) -> str:
    """Replace '&&' with ';' only when not inside single or double quotes."""
    result = []
    i = 0
    in_single_quote = False
    in_double_quote = False
    
    while i < len(command):
        char = command[i]
        
        # Handle quote toggling (ignore escaped quotes)
        if char == "'" and not in_double_quote:
            # Check if escaped (preceded by odd number of backslashes)
            backslash_count = 0
            j = i - 1
            while j >= 0 and command[j] == "\\":
                backslash_count += 1
                j -= 1
            if backslash_count % 2 == 0:
                in_single_quote = not in_single_quote
        elif char == '"' and not in_single_quote:
            # Check if escaped
            backslash_count = 0
            j = i - 1
            while j >= 0 and command[j] == "\\":
                backslash_count += 1
                j -= 1
            if backslash_count % 2 == 0:
                in_double_quote = not in_double_quote
        
        # Check for '&&' replacement
        if _default_pwsh != 'powershell':
            if not in_single_quote and not in_double_quote and command[i] == ";":
                result.append('&&')
                i += 1
            else:
                result.append(char)
                i += 1
        else:
            if not in_single_quote and not in_double_quote and i + 1 < len(command) and command[i:i+2] == "&&":
                result.append(";")
                i += 2
            else:
                result.append(char)
                i += 1
    
    return "".join(result)
    

class Shell(CallableTool2[Params]):
    name: str = "Shell"
    params: type[Params] = Params

    def __init__(self, approval: Approval, environment: Environment):
        is_powershell = environment.shell_name == "Windows PowerShell"
        super().__init__(
            description=load_desc(
                Path(__file__).parent / ("cmd.md" if is_powershell else "bash.md"),
                {"SHELL": f"{environment.shell_name} (`{environment.shell_path}`)"},
            )
        )
        self._approval = approval
        self._is_powershell = is_powershell
        self._shell_path = environment.shell_path

    @override
    async def __call__(self, params: Params) -> ToolReturnValue:
        builder = ToolResultBuilder()

        if not params.command:
            return builder.error("Command cannot be empty.", brief="Empty command")
        if self._is_powershell:
            command = parse_command(params.command)
        else:
            command = params.command
        timeout = max(params.timeout, MIN_TIMEOUT)
        if not await self._approval.request(
            self.name,
            "run command",
            f"Run command `{command}`",
            display=[
                ShellDisplayBlock(
                    language=_default_pwsh if self._is_powershell else "bash",
                    command=command,
                )
            ],
        ):
            return ToolRejectedError()

        def stdout_cb(line: bytes):
            line_str = line.decode(encoding="utf-8", errors="replace")
            print(line_str, end='')
            builder.write(line_str)

        def stderr_cb(line: bytes):
            line_str = line.decode(encoding="utf-8", errors="replace")
            print(line_str, end='')
            builder.write(line_str)

        try:
            exitcode = await self._run_shell_command(
                command, stdout_cb, stderr_cb, timeout
            )
            print('')

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

    def _shell_args(self, command: str) -> tuple[str, ...]:
        if self._is_powershell:
            return (str(self._shell_path), "/c", command)
            # powershell
            # return (str(self._shell_path), "-command", command)
        return (str(self._shell_path), "-c", command)
