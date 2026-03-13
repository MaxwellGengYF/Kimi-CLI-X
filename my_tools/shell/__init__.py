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


import re
from typing import List, Tuple, Optional
command_map = {
    'ls': 'Get-ChildItem',
    'dir': 'Get-ChildItem',  # bash dir is different, but usually means ls
    'cd': 'Set-Location',
    'pwd': 'Get-Location',
    'cat': 'Get-Content',
    'mkdir': 'New-Item -ItemType Directory',
    'rm': 'Remove-Item',
    'cp': 'Copy-Item',
    'mv': 'Move-Item',
    'grep': 'Select-String',
    'ps': 'Get-Process',
    'kill': 'Stop-Process',
    'echo': 'Write-Output',
    'touch': 'New-Item -ItemType File',
    'which': 'Get-Command',
    'wc': 'Measure-Object',
    'curl': 'Invoke-WebRequest',
    'wget': 'Invoke-WebRequest',
    'man': 'Get-Help',
    'find': 'Get-ChildItem -Recurse',
    'head': 'Select-Object -First',
    'tail': 'Get-Content -Tail',
    'sleep': 'Start-Sleep',
    'clear': 'Clear-Host',
    'exit': 'Exit',
    'history': 'Get-History',
    'alias': 'Get-Alias',
    'unalias': 'Remove-Item alias:',
    'df': 'Get-Volume',
    'du': 'Get-ChildItem -Recurse | Measure-Object -Property Length -Sum',
    'chmod': 'Set-ItemProperty',
    'chown': 'Set-Acl',
    'diff': 'Compare-Object',
    'env': 'Get-ChildItem env:',
    'tee': 'Tee-Object',
    'time': 'Measure-Command',
    'date': 'Get-Date',
    'whoami': 'whoami',
    'hostname': 'hostname',
    'uname': 'Get-ComputerInfo',
    'uptime': 'Get-Uptime',
    'id': 'whoami /user',
    'groups': 'whoami /groups',
    'ln': 'New-Item -ItemType SymbolicLink',
    'ln -s': 'New-Item -ItemType SymbolicLink',
    'readlink': 'Get-Item',
    'realpath': 'Resolve-Path',
    'basename': 'Split-Path -Leaf',
    'dirname': 'Split-Path -Parent',
    'mktemp': 'New-TemporaryFile',
    'xargs': 'ForEach-Object',
    'yes': 'while ($true) { Write-Output "y" }',
    'seq': '1..',
    'shuf': 'Get-Random',
    'uniq': 'Get-Unique',
    'cut': 'ForEach-Object { $_.Split(" ") }',
    'paste': 'Join-String',
    'tr': 'ForEach-Object { $_ -replace }',
    'fold': 'Format-Wide',
    'split': 'Split-Path',
    'join': 'Join-Path',
    'tar': 'tar',
    'gzip': 'Compress-Archive',
    'gunzip': 'Expand-Archive',
    'zip': 'Compress-Archive',
    'unzip': 'Expand-Archive',
    'rsync': 'robocopy',
    'scp': 'Copy-Item',
    'ssh': 'ssh',
    'nc': 'Test-NetConnection',
    'ping': 'Test-Connection',
    'netstat': 'Get-NetTCPConnection',
    'ifconfig': 'Get-NetIPAddress',
    'ip': 'Get-NetIPAddress',
    'route': 'Get-NetRoute',
    'nslookup': 'Resolve-DnsName',
    'dig': 'Resolve-DnsName',
    'host': 'Resolve-DnsName',
    'curl': 'Invoke-WebRequest',
    'wget': 'Invoke-WebRequest',
    'jq': 'ConvertFrom-Json',
    'base64': '[Convert]::ToBase64String',
    'md5sum': 'Get-FileHash -Algorithm MD5',
    'sha256sum': 'Get-FileHash -Algorithm SHA256',
    'sha512sum': 'Get-FileHash -Algorithm SHA512'
}


class BashToPowerShellConverter:
    """Converts bash commands to platform-appropriate syntax (PowerShell on Unix-like, cmd.exe on Windows)."""

    def __init__(self):
        pass

    def convert(self, bash_code: str) -> str:
        """Convert bash code to appropriate shell syntax."""
        lines = bash_code.strip().split('\n')
        result_lines = []

        for line in lines:
            converted = self.convert_line(line)
            if converted is not None:
                if isinstance(converted, list):
                    result_lines.extend(converted)
                else:
                    result_lines.append(converted)

        return '\n'.join(result_lines)

    def convert_line(self, line: str) -> Optional[str]:
        """Convert a single line of bash to appropriate shell syntax."""
        stripped = line.strip()

        # Preserve empty lines
        if not stripped:
            return ''

        # Calculate indentation
        indent = len(line) - len(line.lstrip())
        indent_str = ' ' * indent

        # Handle comments
        if stripped.startswith('#'):
            return stripped

        # Handle exit command
        if stripped == 'exit' or stripped.startswith('exit '):
            return stripped  # exit works in both

        # Handle control structures
        if stripped in ['fi', 'done', 'esac']:
            return indent_str + '}'
        if stripped in ['then', 'do']:
            return None  # Skip these
        elif stripped == 'else':
            return indent_str + '} else {'

        # Handle echo commands first (special handling for redirections and pipes)
        if stripped.startswith('echo '):
            result = self._convert_echo_command(stripped)
            return indent_str + result

        # Handle basic commands (with pipe detection)
        cmd_result = self._convert_command(stripped)
        if cmd_result:
            return indent_str + cmd_result

        # Default: return with variable conversion
        return indent_str + self._convert_variables(stripped)

    def _convert_variable_assignment(self, line: str) -> Optional[str]:
        """Convert bash variable assignment."""
        # Handle export VAR=value
        export_match = re.match(
            r'^export\s+([a-zA-Z_][a-zA-Z0-9_]*)=(.+)$', line)
        if export_match:
            var_name = export_match.group(1)
            value = export_match.group(2).strip()

            return f'$env:{var_name} = {value}'

        # Handle VAR=value && export VAR
        match = re.match(r'^([a-zA-Z_][a-zA-Z0-9_]*)=(.+)$', line)
        if match:
            var_name = match.group(1)
            value = match.group(2).strip()

            return f'${var_name} = {value}'

        return None

    def _convert_compound_command(self, line: str) -> Optional[str]:
        """Convert compound commands with && for Windows."""
        # Handle set VAR=value && echo %VAR% pattern
        # In cmd.exe, %VAR% is expanded at parse time, not at execution time
        # We need to enable delayed expansion and use !VAR!
        if line.startswith('set ') and ' && ' in line:
            parts = line.split(' && ', 1)
            first_cmd = parts[0].strip()
            second_cmd = parts[1].strip()

            # Parse set command: set VAR=value
            match = re.match(
                r'^set\s+([a-zA-Z_][a-zA-Z0-9_]*)=(.+)$', first_cmd)
            if match:
                var_name = match.group(1)
                value = match.group(2)

                # Convert second command, replacing %VAR% with !VAR! for delayed expansion
                second_cmd_converted = second_cmd.replace(
                    f'%{var_name}%', f'!{var_name}!')
                # Also handle any other %VAR% patterns
                second_cmd_converted = re.sub(
                    r'%([a-zA-Z_][a-zA-Z0-9_]*)%', r'!\1!', second_cmd_converted)

                # Use cmd /V:ON to enable delayed expansion
                return f'cmd /V:ON /C "{first_cmd} && {second_cmd_converted}"'

        # Handle TEST_VAR=test_value && echo $TEST_VAR (bash style on Windows)
        match = re.match(r'^([a-zA-Z_][a-zA-Z0-9_]*)=(.+?)\s+&&\s+(.+)$', line)
        if match:
            var_name = match.group(1)
            value = match.group(2)
            second_cmd = match.group(3)

            # Replace $VAR or ${VAR} with !VAR! for delayed expansion
            second_cmd_converted = re.sub(
                r'\$\{([^}]+)\}', r'!\1!', second_cmd)
            second_cmd_converted = re.sub(
                r'\$(\w+)', r'!\1!', second_cmd_converted)

            return f'cmd /V:ON /C "set {var_name}={value} && {second_cmd_converted}"'

        return None

    def _convert_test_condition(self, condition: str) -> str:
        """Convert bash test condition [ ] to PowerShell."""
        condition = condition.strip()

        # File tests
        if re.match(r'^-f\s+', condition):
            file_path = condition[2:].strip().strip('"\'')
            return f'Test-Path "{file_path}" -PathType Leaf'
        if re.match(r'^-d\s+', condition):
            dir_path = condition[2:].strip().strip('"\'')
            return f'Test-Path "{dir_path}" -PathType Container'
        if re.match(r'^-e\s+', condition):
            path = condition[2:].strip().strip('"\'')
            return f'Test-Path "{path}"'
        if re.match(r'^-z\s+', condition):
            var = condition[2:].strip()
            var = self._convert_variables(var)
            return f'[string]::IsNullOrEmpty({var})'
        if re.match(r'^-n\s+', condition):
            var = condition[2:].strip()
            var = self._convert_variables(var)
            return f'(-not [string]::IsNullOrEmpty({var}))'

        # String comparisons
        match = re.match(r'^"?\$(\w+)"?\s*=\s*"?(.+?)?$', condition)
        if match:
            var = f'${match.group(1)}'
            val = match.group(2)
            return f'{var} -eq "{val}"'

        match = re.match(r'^"?\$(\w+)"?\s*!=\s*"?(.+?)?$', condition)
        if match:
            var = f'${match.group(1)}'
            val = match.group(2)
            return f'{var} -ne "{val}"'

        # Numeric comparisons
        match = re.match(r'^(.+?)\s+-eq\s+(.+)$', condition)
        if match:
            left = self._convert_variables(match.group(1).strip())
            right = match.group(2).strip()
            return f'{left} -eq {right}'

        match = re.match(r'^(.+?)\s+-ne\s+(.+)$', condition)
        if match:
            left = self._convert_variables(match.group(1).strip())
            right = match.group(2).strip()
            return f'{left} -ne {right}'

        match = re.match(r'^(.+?)\s+-lt\s+(.+)$', condition)
        if match:
            left = self._convert_variables(match.group(1).strip())
            right = match.group(2).strip()
            return f'{left} -lt {right}'

        match = re.match(r'^(.+?)\s+-gt\s+(.+)$', condition)
        if match:
            left = self._convert_variables(match.group(1).strip())
            right = match.group(2).strip()
            return f'{left} -gt {right}'

        return self._convert_variables(condition)

    def _convert_echo_command(self, line: str) -> str:
        """Convert echo command with redirection and pipe support."""
        # Check for pipes first
        if '|' in line:
            idx = line.index('|')
            echo_part = line[:idx].strip()
            rest = line[idx+1:].strip()

            echo_content = echo_part[4:].strip()  # Remove 'echo '
            rest_converted = self._convert_piped_command(rest)
            return f'Write-Output {echo_content} | {rest_converted}'

        # Check for redirection
        if '>>' in line:
            parts = line.split('>>', 1)
            content = parts[0][4:].strip()  # Remove 'echo '
            file_path = parts[1].strip()

            return f'{content} >> {file_path}'

        elif '>' in line:
            parts = line.split('>', 1)
            content = parts[0][4:].strip()  # Remove 'echo '
            file_path = parts[1].strip()

            return f'{content} > {file_path}'

        # Simple echo without redirection or pipes
        content = line[4:].strip()  # Remove 'echo '

        # Handle echo -e flag
        if content.startswith('-e '):
            content = content[3:].strip()

        return f'Write-Output {content}'

    def _bash_to_ps_command(self, cmd: str, is_last: bool = False) -> str:
        """Convert a single bash command to PowerShell equivalent."""
        cmd = cmd.strip()

        # Handle echo
        if cmd.startswith('echo '):
            content = cmd[5:].strip()
            # Handle -e flag - interpret escape sequences
            if content.startswith('-e '):
                content = content[3:].strip()
                # For multi-line content with \n, use an array
                if '\\n' in content:
                    # Remove quotes if present
                    if (content.startswith('"') and content.endswith('"')) or (content.startswith("'") and content.endswith("'")):
                        content = content[1:-1]
                    lines = content.split('\\n')
                    # Create PowerShell array
                    lines_quoted = ['"' + line + '"' for line in lines if line]
                    return '@(' + ', '.join(lines_quoted) + ')' if lines_quoted else '@()'
                content = content.replace('\\t', '`t')  # tab
                content = content.replace('\\r', '`r')  # carriage return
            # Ensure content is properly quoted for PowerShell
            if ' ' in content and not (content.startswith('"') or content.startswith("'")):
                content = f'"{content}"'
            return f'Write-Output {content}'

        # Handle cat with no args (read from stdin)
        if cmd == 'cat':
            # In PowerShell pipeline, we just pass through
            return 'Write-Output'
        if cmd.startswith('cat '):
            args = cmd[4:].strip()
            return f'Get-Content {args}'

        # Handle grep
        if cmd.startswith('grep '):
            args = cmd[5:].strip()
            # Extract pattern (remove quotes if present)
            match = re.match(r'^["\']([^"\']+)["\']$', args)
            if match:
                pattern = match.group(1)
                return f'Select-String -Pattern "{pattern}"'
            return f'Select-String -Pattern "{args}"'

        # Handle tr
        if cmd.startswith('tr '):
            # Pattern for quoted arguments: tr " " "\n" or tr ' ' '\n'
            match = re.match(
                r'^tr\s+["\']([^"\']*)["\']\s+["\']([^"\']*)["\']$', cmd)
            if match:
                from_chars = match.group(1)
                to_chars = match.group(2)
                # For space to newline conversion (both literal \n and actual newline)
                if from_chars == ' ' and (to_chars == '\\n' or to_chars == '\n'):
                    # Split on space and output each item on new line
                    return 'ForEach-Object { $_.Split(" ") } | ForEach-Object { $_ }'
                # For other character replacements
                return f'ForEach-Object {{ $_ -replace "{from_chars}", "{to_chars}" }}'
            return cmd

        # Handle sort
        if cmd == 'sort':
            return 'Sort-Object'

        # Handle sed
        if cmd.startswith('sed '):
            match = re.match(r'^sed\s+["\']?s/([^/]+)/([^/]*)/["\']?$', cmd)
            if match:
                old = match.group(1)
                new = match.group(2)
                return f'ForEach-Object {{ $_ -replace "{old}", "{new}" }}'
            return cmd

        # Handle awk {print $n}
        if cmd.startswith('awk '):
            match = re.match(
                r'^awk\s+["\']?\{\s*print\s+\$(\d+)\s*\}["\']?$', cmd)
            if match:
                n = int(match.group(1))
                return f'ForEach-Object {{ ($_.Split(" "))[{n-1}] }}'
            return cmd

        return cmd

    def _convert_command(self, line: str) -> Optional[str]:
        """Convert bash commands (handles pipes by calling _convert_piped_command)."""
        # Handle pipes
        if '|' in line:
            return self._convert_piped_command(line)

        parts = line.split()
        if not parts:
            return line

        cmd = parts[0]
        args = parts[1:] if len(parts) > 1 else []
        args_str = ' '.join(args)

        if cmd in command_map:
            if args:
                return f'{command_map[cmd]} {args_str}'
            return command_map[cmd]

        return line

    def _convert_piped_command(self, line: str) -> str:
        """Convert piped commands - converts individual commands without recursing on pipes."""
        commands = line.split('|')
        converted_commands = []

        for cmd in commands:
            cmd = cmd.strip()
            # Convert each command without calling _convert_command (which would recurse)
            converted = self._convert_single_command(cmd)
            converted_commands.append(converted)

        return ' | '.join(converted_commands)

    def _convert_single_command(self, line: str) -> str:
        """Convert a single command (no pipes)."""
        parts = line.split()
        if not parts:
            return line

        cmd = parts[0]
        args = parts[1:] if len(parts) > 1 else []
        args_str = ' '.join(args)
        # PowerShell commands

        if cmd in command_map:
            if args:
                return f'{command_map[cmd]} {args_str}'
            return command_map[cmd]

        return line

    def _convert_variables(self, text: str) -> str:
        """Convert bash variable syntax."""
        # ${var} -> $var (already compatible)
        text = re.sub(r'\$\{([^}]+)\}', r'$\1', text)
        return text

    def _escape_for_cmd(self, text: str) -> str:
        """Escape special characters for cmd.exe."""
        # Escape special characters that cmd.exe interprets
        # ^ is the escape character in cmd
        special_chars = ['<', '>', '&', '|', '^']
        result = text
        for char in special_chars:
            result = result.replace(char, f'^{char}')
        return result


# Create module-level function
converter = BashToPowerShellConverter()
def convert_command(bash_cmd: str) -> str:
    """Convert a single bash command to appropriate shell syntax."""
    return converter.convert(bash_cmd)


MIN_TIMEOUT = 10 * 60
MAX_TIMEOUT = 15 * 60
# On Windows platform, check if pwsh (PowerShell Core) exists


def _check_command_exists(command: str) -> bool:
    """Check if a command exists in the system PATH."""
    import shutil
    return shutil.which(command) is not None


# Try to use cmd, should be faster
_default_pwsh = 'powershell'
if sys.platform == 'win32':
    if not _check_command_exists('pwsh'):
        print("PowerShell Core (pwsh) not found. Falling back to Windows PowerShell (powershell).")
    else:
        _default_pwsh = 'pwsh'


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



class Shell(CallableTool2[Params]):
    name: str = "Shell"
    params: type[Params] = Params

    def __init__(self, approval: Approval, environment: Environment):
        is_powershell = environment.shell_name == "Windows PowerShell"
        super().__init__(
            description=load_desc(
                Path(__file__).parent /
                "powershell.md" if is_powershell else
                ("bash.md"),
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
            command = convert_command(params.command)
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
            builder.write(line_str)

        def stderr_cb(line: bytes):
            line_str = line.decode(encoding="utf-8", errors="replace")
            builder.write(line_str)

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

    def _shell_args(self, command: str) -> tuple[str, ...]:
        if self._is_powershell:
            return (str(self._shell_path), "-command", command)
        return (str(self._shell_path), "-c", command)
