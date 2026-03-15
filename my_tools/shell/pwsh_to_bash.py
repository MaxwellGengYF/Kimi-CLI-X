import re
from typing import Optional
_command_map = {
    'ls': 'Get-ChildItem',
    'ver': '$PSVersionTable',
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

        # Handle cat with no args (read from stdin)
        if stripped == 'cat':
            # In PowerShell pipeline, we just pass through
            return 'Write-Output'
        if stripped.startswith('cat '):
            args = stripped[4:].strip()
            return f'Get-Content {args}'

        # Handle grep
        if stripped.startswith('grep '):
            args = stripped[5:].strip()
            # Extract pattern (remove quotes if present)
            match = re.match(r'^["\']([^"\']+)["\']$', args)
            if match:
                pattern = match.group(1)
                return f'Select-String -Pattern "{pattern}"'
            return f'Select-String -Pattern "{args}"'

        # Handle tr
        if stripped.startswith('tr '):
            # Pattern for quoted arguments: tr " " "\n" or tr ' ' '\n'
            match = re.match(
                r'^tr\s+["\']([^"\']*)["\']\s+["\']([^"\']*)["\']$', stripped)
            if match:
                from_chars = match.group(1)
                to_chars = match.group(2)
                # For space to newline conversion (both literal \n and actual newline)
                if from_chars == ' ' and (to_chars == '\\n' or to_chars == '\n'):
                    # Split on space and output each item on new line
                    return 'ForEach-Object { $_.Split(" ") } | ForEach-Object { $_ }'
                # For other character replacements
                return f'ForEach-Object {{ $_ -replace "{from_chars}", "{to_chars}" }}'
            return stripped

        # Handle sort
        if stripped == 'sort':
            return 'Sort-Object'

        # Handle sed
        if stripped.startswith('sed '):
            match = re.match(
                r'^sed\s+["\']?s/([^/]+)/([^/]*)/["\']?$', stripped)
            if match:
                old = match.group(1)
                new = match.group(2)
                return f'ForEach-Object {{ $_ -replace "{old}", "{new}" }}'
            return stripped

        # Handle awk {print $n}
        if stripped.startswith('awk '):
            match = re.match(
                r'^awk\s+["\']?\{\s*print\s+\$(\d+)\s*\}["\']?$', stripped)
            if match:
                n = int(match.group(1))
                return f'ForEach-Object {{ ($_.Split(" "))[{n-1}] }}'
            return stripped

        # Handle ls with various flags (-la, -a, -h, -t)
        if stripped.startswith('ls '):
            return self._convert_ls(stripped)

        # Default: return with variable conversion
        # Handle basic commands (with pipe detection)
        cmd_result = self._convert_command(stripped)
        if cmd_result:
            return indent_str + cmd_result

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

    def _convert_ls(self, cmd: str) -> str:
        """Convert ls command with flags to PowerShell equivalent."""
        parts = cmd.split()
        if len(parts) < 2:
            return 'Get-ChildItem'

        # Parse flags (e.g., -la, -a, -lh, -lat)
        flags = set()
        for part in parts[1:]:
            if part.startswith('-'):
                for char in part[1:]:
                    flags.add(char)

        # Build PowerShell command
        base_cmd = 'Get-ChildItem'
        if 'a' in flags:
            base_cmd += ' -Force'

        # Determine if we need sorting (-t) or formatting (-l, -h)
        need_sort = 't' in flags
        need_format = 'l' in flags or 'h' in flags

        if not need_sort and not need_format:
            return base_cmd

        result = base_cmd

        # Add sorting by time if -t flag present
        if need_sort:
            result += ' | Sort-Object LastWriteTime -Descending'

        # Add detailed formatting if -l or -h flag present
        if need_format:
            if 'h' in flags:
                # Human-readable sizes with detailed listing
                result += " | Select-Object Mode, LastWriteTime, @{N='Size';E={if($_.Length -ge 1GB){'{0:N1}G' -f($_.Length/1GB)}elseif($_.Length -ge 1MB){'{0:N1}M' -f($_.Length/1MB)}elseif($_.Length -ge 1KB){'{0:N1}K' -f($_.Length/1KB)}else{$_.Length}}}, Name | Format-Table -AutoSize"
            else:
                # Standard detailed listing
                result += ' | Select-Object Mode, LastWriteTime, Length, Name | Format-Table -AutoSize'

        return result

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
        if cmd in _command_map:
            if args:
                return f'{_command_map[cmd]} {args_str}'
            return _command_map[cmd]

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
        if cmd in _command_map:
            if args:
                return f'{_command_map[cmd]} {args_str}'
            return _command_map[cmd]

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


def parse_command(command: str) -> str:
    """Replace '&&' with ';' only when not inside single or double quotes."""
    result = []
    i = 0
    in_single_quote = False
    in_double_quote = False
    cmd = ""
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
        if not in_single_quote and not in_double_quote and i + 1 < len(command) and command[i:i+2] == "&&":
            if len(result) > 0:
                cmd += convert_command("".join(result)) + ";"
                result.clear()
            else:
                result.append(";")
            i += 2
        else:
            result.append(char)
            i += 1
    if len(result) > 0:
        cmd += convert_command("".join(result))
    return cmd
