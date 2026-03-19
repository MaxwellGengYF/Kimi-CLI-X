import re
from typing import Optional
import my_tools.shell.to_powershell_cmd as to_powershell_cmd

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

        # Default: return with variable conversion
        # Handle basic commands (with pipe detection)
        cmd_result = self._convert_command(stripped)
        if cmd_result:
            return indent_str + cmd_result

        return indent_str + self._convert_variables(stripped)

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
        func = to_powershell_cmd._command_map.get(cmd)
        if func is not None:
            return func(line)
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
        func = to_powershell_cmd._command_map.get(cmd)
        if func is not None:
            return func(line)
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
    lists = ['||', '&&', ';', '|', '& ', ' & ']
    set = {i for i in lists}
    commands = multiple_split(command, lists)

    for i in range(len(commands)):
        cmd = commands[i]
        if cmd == '&&' or cmd.strip() == '&':
            commands[i] = ';'
        else:
            if not cmd in set:
                commands[i] = convert_command(cmd)

    return ' '.join(commands)
