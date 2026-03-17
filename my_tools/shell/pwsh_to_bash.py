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

        # Handle rm with various flags (-r, -f, -rf)
        if stripped.startswith('rm '):
            return self._convert_rm(stripped)

        # Handle cp with various flags (-r, -f)
        if stripped.startswith('cp '):
            return self._convert_cp(stripped)

        # Handle mv with various flags (-f)
        if stripped.startswith('mv '):
            return self._convert_mv(stripped)

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

    def _convert_rm(self, cmd: str) -> str:
        """Convert rm command with flags to PowerShell equivalent."""
        parts = cmd.split()
        if len(parts) < 2:
            return 'Remove-Item'

        # Parse flags
        flags = set()
        args = []
        for part in parts[1:]:
            if part.startswith('-'):
                for char in part[1:]:
                    flags.add(char)
            else:
                args.append(part)

        # Build PowerShell command
        base_cmd = 'Remove-Item'
        ps_flags = []

        # -r or -R for recursive
        if 'r' in flags or 'R' in flags:
            ps_flags.append('-Recurse')

        # -f for force
        if 'f' in flags:
            ps_flags.append('-Force')

        # Add remaining arguments (file paths)
        args_str = ' '.join(args)
        if ps_flags:
            return f"{base_cmd} {args_str} {' '.join(ps_flags)}"
        return f'{base_cmd} {args_str}'

    def _convert_cp(self, cmd: str) -> str:
        """Convert cp command with flags to PowerShell equivalent."""
        parts = cmd.split()
        if len(parts) < 3:
            return 'Copy-Item'

        # Parse flags
        flags = set()
        args = []
        for part in parts[1:]:
            if part.startswith('-'):
                for char in part[1:]:
                    flags.add(char)
            else:
                args.append(part)

        # Build PowerShell command
        base_cmd = 'Copy-Item'
        ps_flags = []

        # -r or -R for recursive (directories)
        if 'r' in flags or 'R' in flags:
            ps_flags.append('-Recurse')

        # -f for force (overwrite)
        if 'f' in flags:
            ps_flags.append('-Force')

        # Handle source and destination
        if len(args) >= 2:
            source = args[0]
            dest = args[1]
            if ps_flags:
                return f"{base_cmd} {source} {dest} {' '.join(ps_flags)}"
            return f'{base_cmd} {source} {dest}'
        elif len(args) == 1:
            return f'{base_cmd} {args[0]}'
        return base_cmd

    def _convert_mv(self, cmd: str) -> str:
        """Convert mv command with flags to PowerShell equivalent."""
        parts = cmd.split()
        if len(parts) < 3:
            return 'Move-Item'

        # Parse flags
        flags = set()
        args = []
        for part in parts[1:]:
            if part.startswith('-'):
                for char in part[1:]:
                    flags.add(char)
            else:
                args.append(part)

        # Build PowerShell command
        base_cmd = 'Move-Item'
        ps_flags = []

        # -f for force (overwrite)
        if 'f' in flags:
            ps_flags.append('-Force')

        # Handle source and destination
        if len(args) >= 2:
            source = args[0]
            dest = args[1]
            if ps_flags:
                return f"{base_cmd} {source} {dest} {' '.join(ps_flags)}"
            return f'{base_cmd} {source} {dest}'
        elif len(args) == 1:
            return f'{base_cmd} {args[0]}'
        return base_cmd

    def _convert_ls(self, cmd: str) -> str:
        """Convert ls command with flags to PowerShell equivalent."""
        parts = cmd.split()
        if len(parts) < 2:
            return 'Get-ChildItem'

        # Parse flags (e.g., -la, -a, -lh, -lat)
        flags = set()
        final_cmd = []
        for part in parts[1:]:
            if part.startswith('-'):
                for char in part[1:]:
                    flags.add(char)
            else:
                final_cmd.append(part)
        # Build PowerShell command
        base_cmd = 'Get-ChildItem'
        if 'a' in flags:
            base_cmd += ' -Force'

        # Determine if we need sorting (-t) or formatting (-l, -h)
        need_sort = 't' in flags
        need_format = ('l' in flags or 'h' in flags) and len(final_cmd) == 0

        if not need_sort and not need_format:
            return base_cmd + " " + "".join(final_cmd)

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

        return result + " " + "".join(final_cmd)

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


def multiple_split(text, delimiters, maxsplit=-1):
    """
    Split a string using multiple delimiters.

    Args:
        text: The string to split.
        *delimiters: One or more delimiter strings to split on.
        maxsplit: Maximum number of splits to do. -1 means no limit.

    Returns:
        A list of strings after splitting.

    Examples:
        >>> multiple_split("a,b;c", ",", ";")
        ['a', 'b', 'c']
        >>> multiple_split("a::b||c", "::", "||")
        ['a', 'b', 'c']
    """
    if not delimiters:
        return [text] if text else []

    if not text:
        return []

    # Sort delimiters by length (longest first) to avoid partial matches
    sorted_delims = sorted(delimiters, key=len, reverse=True)
    result = []
    current = text
    split_count = 0

    while current:
        if maxsplit >= 0 and split_count >= maxsplit:
            result.append(current)
            break

        # Find the earliest delimiter
        earliest_pos = -1
        earliest_delim = None

        for delim in sorted_delims:
            pos = current.find(delim)
            if pos != -1:
                if earliest_pos == -1 or pos < earliest_pos:
                    earliest_pos = pos
                    earliest_delim = delim

        if earliest_pos == -1:
            # No more delimiters found
            result.append(current)
            break

        # Add the part before the delimiter
        if earliest_pos > 0 or result:  # Keep empty parts if not at start
            result.append(current[:earliest_pos])
            result.append(earliest_delim)

        # Move past the delimiter
        current = current[earliest_pos + len(earliest_delim):]
        split_count += 1

    return result


def parse_command(command: str) -> str:
    lists = ['||', '&&', ';', '|', '& ']
    set = {i for i in lists}
    commands = multiple_split(command, lists)

    for i in range(len(commands)):
        cmd = commands[i]
        if cmd == '&&':
            commands[i] = ';'
        else:
            if not cmd in set:
                commands[i] = convert_command(cmd)

    return ' '.join(commands)
