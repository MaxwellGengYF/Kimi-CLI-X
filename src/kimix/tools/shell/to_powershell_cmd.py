import os
import re
from typing import Any, Dict, List, Optional, Set, Tuple, Union
from urllib.parse import urlparse

def _convert_ver(cmd: str) -> str:
    if not cmd or not cmd.strip():
        return '$PSVersionTable'
    parts = _parse_command_line(cmd)
    if not parts:
        return '$PSVersionTable'
    if parts[0] in ('ver', '/bin/ver', '/usr/bin/ver'):
        parts = parts[1:]
    if not parts:
        return '$PSVersionTable'
    flags: Set[str] = set()
    long_flags: Set[str] = set()
    i = 0
    while i < len(parts):
        part = parts[i]
        if part == '--':
            break
        if part.startswith('/') and len(part) >= 2:
            if len(part) == 2 and part[1].isalpha():
                part = '-' + part[1:]
            elif len(part) > 2 and part[1].isalpha():
                part = '--' + part[1:]
        if part.startswith('--'):
            long_opt = part[2:]
            if '=' in long_opt:
                opt_name, _ = long_opt.split('=', 1)
                long_flags.add(opt_name)
            else:
                long_flags.add(long_opt)
            i += 1
            continue
        if part.startswith('-') and len(part) > 1:
            opt_chars = part[1:]
            for char in opt_chars:
                flags.add(char)
            i += 1
            continue
        i += 1
    return _build_ver_powershell_command(flags, long_flags)
def _build_ver_powershell_command(flags: Set[str], long_flags: Set[str]) -> str:
    show_all = 'a' in flags or 'all' in long_flags
    show_shell = 's' in flags or 'shell' in long_flags
    show_os = 'o' in flags or 'os' in long_flags
    show_ps = 'p' in flags or 'ps' in long_flags or 'powershell' in long_flags
    show_help = 'h' in flags or 'help' in long_flags
    verbose = 'v' in flags or 'verbose' in long_flags
    commands: List[str] = []
    if show_help:
        return 'Write-Output "ver - Display version information\nUsage: ver [options]\nOptions:\n  -a, --all          Show all version information\n  -s, --shell        Show shell version only\n  -o, --os           Show OS version only\n  -p, --ps, --powershell  Show PowerShell version\n  -v, --verbose      Verbose output\n  -h, --help         Show this help message"'
    if show_all:
        commands.append('$PSVersionTable')
        if verbose:
            commands.append('Get-ComputerInfo | Select-Object WindowsProductName, WindowsVersion, OsName, OsVersion, TotalPhysicalMemory, CsProcessors')
            commands.append('$host')
        else:
            commands.append('Get-ComputerInfo | Select-Object WindowsProductName, WindowsVersion, OsName, OsVersion')
    elif show_shell:
        commands.append('$PSVersionTable.PSVersion')
    elif show_os:
        if verbose:
            commands.append('Get-ComputerInfo | Select-Object OsName, OsVersion, OsBuildNumber, WindowsVersion')
        else:
            commands.append('Get-ComputerInfo | Select-Object OsName, OsVersion')
    elif show_ps:
        commands.append('$PSVersionTable.PSVersion')
        if verbose:
            commands.append('$PSVersionTable')
    else:
        commands.append('$PSVersionTable')
        if verbose:
            commands.append('Get-ComputerInfo | Select-Object WindowsProductName, WindowsVersion')
    return '; '.join(commands)
def _convert_ls(cmd: str) -> str:
    parts = cmd.split()
    if len(parts) < 2:
        return 'Get-ChildItem'
    flags = set()
    final_cmd = []
    for part in parts[1:]:
        if part.startswith('-'):
            for char in part[1:]:
                flags.add(char)
        else:
            final_cmd.append(part)
    base_cmd = 'Get-ChildItem'
    if 'a' in flags:
        base_cmd += ' -Force'
    need_sort = 't' in flags
    need_format = ('l' in flags or 'h' in flags) and len(final_cmd) == 0
    if not need_sort and not need_format:
        return base_cmd + " " + "".join(final_cmd)
    result = base_cmd
    if need_sort:
        result += ' | Sort-Object LastWriteTime -Descending'
    if need_format:
        if 'h' in flags:
            result += " | Select-Object Mode, LastWriteTime, @{N='Size';E={if($_.Length -ge 1GB){'{0:N1}G' -f($_.Length/1GB)}elseif($_.Length -ge 1MB){'{0:N1}M' -f($_.Length/1MB)}elseif($_.Length -ge 1KB){'{0:N1}K' -f($_.Length/1KB)}else{$_.Length}}}, Name | Format-Table -AutoSize"
        else:
            result += ' | Select-Object Mode, LastWriteTime, Length, Name | Format-Table -AutoSize'
    return result + " " + "".join(final_cmd)
def _parse_command_line(cmd: str) -> List[str]:
    parts = []
    current = []
    in_single_quote = False
    in_double_quote = False
    for char in cmd:
        if char == "'" and not in_double_quote:
            in_single_quote = not in_single_quote
            continue
        elif char == '"' and not in_single_quote:
            in_double_quote = not in_double_quote
            continue
        elif char.isspace() and not in_single_quote and not in_double_quote:
            if current:
                parts.append(''.join(current))
                current = []
            continue
        current.append(char)
    if current:
        parts.append(''.join(current))
    return parts
def _build_powershell_command(
    flags: Set[str],
    long_flags: Set[str],
    paths: List[str]
) -> str:
    base_cmd = 'Get-ChildItem'
    ps_flags: List[str] = []
    all_flag = 'all' in long_flags or 'almost-all' in long_flags
    almost_all = 'almost-all' in long_flags
    human_readable = 'human-readable' in long_flags
    recursive = 'recursive' in long_flags
    directory_only = 'directory' in long_flags
    sort_by_time = 'sort=time' in long_flags or 't' in flags
    sort_by_size = 'sort=size' in long_flags or 'S' in flags
    reverse_sort = 'reverse' in long_flags
    show_version = 'version' in long_flags or 'V' in flags
    show_help = 'help' in long_flags
    if 'a' in flags or all_flag:
        ps_flags.append('-Force')
    if almost_all:
        ps_flags.append('-Force')
    if 'R' in flags or recursive:
        ps_flags.append('-Recurse')
    if 'd' in flags or directory_only:
        ps_flags.append('-Directory')
    result_parts = [base_cmd]
    result_parts.extend(ps_flags)
    if paths:
        quoted_paths = []
        for p in paths:
            if ' ' in p and not (p.startswith('"') or p.startswith("'")):
                quoted_paths.append(f'"{p}"')
            else:
                quoted_paths.append(p)
        result_parts.extend(quoted_paths)
    pipeline_parts: List[str] = []
    need_sort = sort_by_time or sort_by_size or 't' in flags or 'S' in flags
    need_format = 'l' in flags or human_readable or 's' in flags or '1' in flags
    need_reverse = 'r' in flags or reverse_sort
    if need_sort:
        if sort_by_size or 'S' in flags:
            sort_prop = 'Length'
        else:
            sort_prop = 'LastWriteTime'
        sort_cmd = f'Sort-Object {sort_prop}'
        if not need_reverse:
            sort_cmd += ' -Descending'
        pipeline_parts.append(sort_cmd)
    elif need_reverse:
        pipeline_parts.append('Sort-Object -Descending')
    if 'l' in flags or human_readable or 's' in flags:
        select_parts = ['Mode', 'LastWriteTime']
        if 's' in flags:
            select_parts.append("@{N='Blocks';E={[math]::Ceiling($_.Length/512)}}")
        if human_readable or 'h' in flags:
            size_expr = (
                "@{N='Size';E={"
                "if($_.Length -ge 1GB){'{0:N1}G' -f($_.Length/1GB)}"
                "elseif($_.Length -ge 1MB){'{0:N1}M' -f($_.Length/1MB)}"
                "elseif($_.Length -ge 1KB){'{0:N1}K' -f($_.Length/1KB)}"
                "else{$_.Length}}}"
            )
            select_parts.append(size_expr)
        else:
            select_parts.append('Length')
        select_parts.append('Name')
        select_cmd = f"Select-Object {', '.join(select_parts)}"
        pipeline_parts.append(select_cmd)
        pipeline_parts.append('Format-Table -AutoSize')
    elif '1' in flags:
        pipeline_parts.append('Select-Object Name')
        pipeline_parts.append('Format-List')
    elif 'm' in flags:
        pipeline_parts.append("ForEach-Object { $_.Name }")
        pipeline_parts.append("Join-String -Separator ', '")
    elif 'x' in flags:
        pipeline_parts.append('Select-Object Name')
        pipeline_parts.append('Format-Table -HideTableHeaders')
    result = ' '.join(result_parts)
    if pipeline_parts:
        result += ' | ' + ' | '.join(pipeline_parts)
    return result
def _convert_dir(cmd: str) -> str:
    if not cmd or not cmd.strip():
        return 'Get-ChildItem'
    parts = _parse_command_line(cmd)
    if not parts:
        return 'Get-ChildItem'
    if parts[0].lower() in ('dir', 'cmd.exe/dir'):
        parts = parts[1:]
    if not parts:
        return 'Get-ChildItem'
    flags: Set[str] = set()
    flag_values: dict = {}
    paths: List[str] = []
    show_owner = False
    show_streams = False
    use_lowercase = False
    disable_thousand_sep = False
    time_field = 'W'
    wide_columns = False
    bare_format = False
    recursive = False
    i = 0
    while i < len(parts):
        part = parts[i]
        if part.startswith('/') and len(part) >= 2:
            flag_content = part[1:]
            if ':' in flag_content:
                flag_name, flag_value = flag_content.split(':', 1)
                flag_name = flag_name.upper()
                flag_value = flag_value.upper()
                flag_values[flag_name] = flag_value
                flags.add(flag_name[0])
                i += 1
                continue
            flag_chars = flag_content.upper()
            for char in flag_chars:
                flags.add(char)
            i += 1
            continue
        if part.startswith('-') and len(part) > 1:
            flag_content = part[1:].upper()
            if ':' in flag_content:
                flag_name, flag_value = flag_content.split(':', 1)
                flag_name = flag_name.upper()
                flag_value = flag_value.upper()
                flag_values[flag_name] = flag_value
                flags.add(flag_name[0])
                i += 1
                continue
            for char in flag_content:
                flags.add(char)
            i += 1
            continue
        paths.append(part)
        i += 1
    return _build_dir_powershell_command(
        flags, flag_values, paths
    )
def _build_dir_powershell_command(
    flags: Set[str],
    flag_values: dict,
    paths: List[str]
) -> str:
    base_cmd = 'Get-ChildItem'
    ps_params: List[str] = []
    pipeline_parts: List[str] = []
    wide_format = 'W' in flags
    bare_format = 'B' in flags
    recursive = 'S' in flags
    show_owner = 'Q' in flags
    show_streams = 'R' in flags
    use_lowercase = 'L' in flags
    disable_thousand_sep = 'C' in flags and '/-C' in str(flags)
    if 'A' in flag_values or 'A' in flags:
        attr_value = flag_values.get('A', '')
        if attr_value:
            if attr_value == 'H':
                ps_params.append('-Hidden')
            elif attr_value == 'S':
                ps_params.append('-System')
            elif attr_value == 'R':
                ps_params.append('-ReadOnly')
            elif attr_value == 'D':
                ps_params.append('-Directory')
            elif attr_value == '-H':
                pass
            elif attr_value == '-D':
                ps_params.append('-File')
        else:
            ps_params.append('-Force')
    time_field = 'LastWriteTime'
    if 'T' in flag_values:
        t_value = flag_values.get('T', 'W')
        if t_value == 'C':
            time_field = 'CreationTime'
        elif t_value == 'A':
            time_field = 'LastAccessTime'
        elif t_value == 'W':
            time_field = 'LastWriteTime'
    sort_property = None
    sort_descending = False
    if 'O' in flag_values:
        o_value = flag_values.get('O', 'N')
        if o_value == 'N':
            sort_property = 'Name'
        elif o_value == 'S':
            sort_property = 'Length'
        elif o_value == 'E':
            sort_property = 'Extension'
        elif o_value == 'D':
            sort_property = time_field
        elif o_value == '-N':
            sort_property = 'Name'
            sort_descending = True
        elif o_value == '-S':
            sort_property = 'Length'
            sort_descending = True
        elif o_value == '-D':
            sort_property = time_field
            sort_descending = True
    if recursive:
        ps_params.append('-Recurse')
    result_parts = [base_cmd]
    result_parts.extend(ps_params)
    if paths:
        quoted_paths = []
        for p in paths:
            if ' ' in p and not (p.startswith('"') or p.startswith("'")):
                quoted_paths.append(f'"{p}"')
            else:
                quoted_paths.append(p)
        result_parts.extend(quoted_paths)
    if sort_property:
        sort_cmd = f'Sort-Object {sort_property}'
        if sort_descending:
            sort_cmd += ' -Descending'
        pipeline_parts.append(sort_cmd)
    if wide_format:
        pipeline_parts.append('Format-Wide -Column 5')
    elif bare_format:
        pipeline_parts.append('Select-Object Name')
    else:
        select_parts = ['Mode', time_field]
        if disable_thousand_sep:
            select_parts.append('Length')
        else:
            select_parts.append('Length')
        if show_owner:
            select_parts.append('@{N=\'Owner\';E={(Get-Acl $_.FullName).Owner}}')
        if show_streams:
            select_parts.append('@{N=\'Stream\';E={Get-Item -Path $_.FullName -Stream * | ForEach-Object { $_.Stream }}}')
        select_parts.append('Name')
        select_cmd = f"Select-Object {', '.join(select_parts)}"
        pipeline_parts.append(select_cmd)
        pipeline_parts.append('Format-Table -AutoSize')
    result = ' '.join(result_parts)
    if pipeline_parts:
        result += ' | ' + ' | '.join(pipeline_parts)
    return result
def _convert_cd(cmd: str) -> str:
    if not cmd or not cmd.strip():
        return 'Set-Location ~'
    parts = _parse_command_line(cmd)
    if not parts:
        return 'Set-Location ~'
    if parts[0] in ('cd', 'chdir') or parts[0].endswith('/cd') or parts[0].endswith('\\cd'):
        parts = parts[1:]
    if not parts:
        return 'Set-Location ~'
    flags: Set[str] = set()
    long_flags: Set[str] = set()
    path_args: List[str] = []
    i = 0
    while i < len(parts):
        part = parts[i]
        if part == '--':
            path_args.extend(parts[i + 1:])
            break
        if part.startswith('/') and len(part) == 2 and part[1].isalpha():
            part = '-' + part[1:]
        if part.startswith('--'):
            long_opt = part[2:]
            if '=' in long_opt:
                opt_name, _ = long_opt.split('=', 1)
                long_flags.add(opt_name)
            else:
                long_flags.add(long_opt)
            i += 1
            continue
        if part.startswith('-') and len(part) > 1:
            opt_chars = part[1:]
            for char in opt_chars:
                flags.add(char)
            i += 1
            continue
        path_args.append(part)
        i += 1
    if not path_args:
        return 'Set-Location ~'
    path = path_args[0]
    if path == '~' or path.startswith('~/') or path.startswith('~\\'):
        pass
    if path == '-':
        pass
    if path == '..':
        pass
    if path == '.':
        pass
    if ' ' in path and not (path.startswith('"') or path.startswith("'")):
        path = f'"{path}"'
    return f'Set-Location {path}'
def _convert_pwd(cmd: str) -> str:
    if not cmd or not cmd.strip():
        return 'Get-Location'
    parts = _parse_command_line(cmd)
    if not parts:
        return 'Get-Location'
    if parts[0] in ('pwd', '/bin/pwd', '/usr/bin/pwd'):
        parts = parts[1:]
    if not parts:
        return 'Get-Location'
    flags: Set[str] = set()
    long_flags: Set[str] = set()
    i = 0
    while i < len(parts):
        part = parts[i]
        if part == '--':
            break
        if part.startswith('/') and len(part) >= 2:
            if len(part) == 2 and part[1].isalpha():
                part = '-' + part[1:]
            elif len(part) > 2 and part[1].isalpha():
                part = '--' + part[1:]
        if part.startswith('--'):
            long_opt = part[2:]
            if '=' in long_opt:
                opt_name, _ = long_opt.split('=', 1)
                long_flags.add(opt_name)
            else:
                long_flags.add(long_opt)
            i += 1
            continue
        if part.startswith('-') and len(part) > 1:
            opt_chars = part[1:]
            for char in opt_chars:
                flags.add(char)
            i += 1
            continue
        i += 1
    return _build_pwd_powershell_command(flags, long_flags)
def _build_pwd_powershell_command(flags: Set[str], long_flags: Set[str]) -> str:
    logical = 'L' in flags or 'logical' in long_flags
    physical = 'P' in flags or 'physical' in long_flags
    show_help = 'help' in long_flags or 'h' in flags
    show_version = 'version' in long_flags or 'v' in flags
    if show_help:
        return (
            'Write-Output "pwd - Print name of current working directory\\n'
            'Usage: pwd [options]\\n'
            'Options:\\n'
            '  -L, --logical   Print logical current working directory\\n'
            '  -P, --physical  Print physical current working directory (all symlinks resolved)\\n'
            '  --help          Show this help message\\n'
            '  --version       Show version information"'
        )
    if show_version:
        return 'Write-Output "pwd version 8.32"'
    if physical:
        return '(Resolve-Path .).Path'
    return 'Get-Location'
def _convert_cat(cmd: str) -> str:
    if not cmd or not cmd.strip():
        return 'Get-Content'
    parts = _parse_command_line(cmd)
    if not parts:
        return 'Get-Content'
    if parts[0] in ('cat', '/bin/cat', '/usr/bin/cat'):
        parts = parts[1:]
    if not parts:
        return 'Get-Content'
    flags: Set[str] = set()
    long_flags: Set[str] = set()
    files: List[str] = []
    i = 0
    while i < len(parts):
        part = parts[i]
        if part == '--':
            files.extend(parts[i + 1:])
            break
        if part.startswith('/') and len(part) >= 2:
            if len(part) == 2 and part[1].isalpha():
                part = '-' + part[1:]
            elif len(part) > 2 and part[1].isalpha():
                part = '--' + part[1:]
        if part.startswith('--'):
            long_opt = part[2:]
            if '=' in long_opt:
                opt_name, _ = long_opt.split('=', 1)
                long_flags.add(opt_name)
            else:
                long_flags.add(long_opt)
            i += 1
            continue
        if part.startswith('-') and len(part) > 1:
            opt_chars = part[1:]
            for char in opt_chars:
                flags.add(char)
            i += 1
            continue
        files.append(part)
        i += 1
    return _build_cat_powershell_command(flags, long_flags, files)
def _build_cat_powershell_command(
    flags: Set[str],
    long_flags: Set[str],
    files: List[str]
) -> str:
    show_help = 'help' in long_flags
    show_version = 'version' in long_flags
    if show_help:
        return (
            'Write-Output "cat - Concatenate and display file contents\\n'
            'Usage: cat [options] [file...]\\n'
            'Options:\\n'
            '  -A, --show-all          Equivalent to -vET\\n'
            '  -b, --number-nonblank   Number non-empty output lines\\n'
            '  -e                      Equivalent to -vE\\n'
            '  -E, --show-ends         Display $ at end of each line\\n'
            '  -n, --number            Number all output lines\\n'
            '  -s, --squeeze-blank     Suppress repeated empty output lines\\n'
            '  -t                      Equivalent to -vT\\n'
            '  -T, --show-tabs         Display TAB characters as ^I\\n'
            '  -u                      Ignored (unbuffered)\\n'
            '  -v, --show-nonprinting  Show non-printing characters\\n'
            '  --help                  Display this help\\n'
            '  --version               Display version information"'
        )
    if show_version:
        return 'Write-Output "cat version 8.32"'
    show_all = 'A' in flags or 'show-all' in long_flags
    number_nonblank = 'b' in flags or 'number-nonblank' in long_flags
    show_ends_e = 'e' in flags
    show_ends = 'E' in flags or 'show-ends' in long_flags or show_ends_e
    number_all = 'n' in flags or 'number' in long_flags
    squeeze_blank = 's' in flags or 'squeeze-blank' in long_flags
    show_tabs_t = 't' in flags
    show_tabs = 'T' in flags or 'show-tabs' in long_flags or show_tabs_t
    show_nonprinting = 'v' in flags or 'show-nonprinting' in long_flags or show_all or show_ends_e or show_tabs_t
    if show_all:
        show_nonprinting = True
        show_ends = True
        show_tabs = True
    if number_nonblank:
        number_all = False
    if files:
        quoted_files = []
        for f in files:
            if ' ' in f and not (f.startswith('"') or f.startswith("'")):
                quoted_files.append(f'"{f}"')
            else:
                quoted_files.append(f)
        if len(quoted_files) == 1:
            base_cmd = f"Get-Content {quoted_files[0]}"
        else:
            base_cmd = f"Get-Content {', '.join(quoted_files)}"
    else:
        base_cmd = 'Get-Content'
    pipeline_parts: List[str] = []
    if squeeze_blank:
        pipeline_parts.append(
            'ForEach-Object { '
            'if ($_.Trim() -eq "") { '
            'if (!$script:lastWasEmpty) { $_; $script:lastWasEmpty = $true } '
            '} else { $_; $script:lastWasEmpty = $false } '
            '} -Begin { $script:lastWasEmpty = $false }'
        )
    if show_tabs:
        pipeline_parts.append("ForEach-Object { $_ -replace \"\t\", \"^I\" }")
    if show_ends:
        pipeline_parts.append("ForEach-Object { $_ + '$' }")
    if number_all:
        pipeline_parts.append(
            'ForEach-Object { $i=1 } { "{0,6}  $_" -f $i; $i++ }'
        )
    elif number_nonblank:
        pipeline_parts.append(
            'ForEach-Object { $i=1 } { '
            'if ($_.Trim() -ne "") { "{0,6}  $_" -f $i; $i++ } else { $_ } '
            '}'
        )
    if show_nonprinting and not (show_tabs or show_ends):
        pipeline_parts.append(
            'ForEach-Object { '
            '$result = $_; '
            'for ($c = 0; $c -lt $result.Length; $c++) { '
            '$b = [int][char]$result[$c]; '
            'if ($b -lt 32 -and $b -ne 9 -and $b -ne 10) { '
            '$result = $result.Substring(0, $c) + "^" + [char]($b + 64) + $result.Substring($c + 1); '
            '$c++ } '
            '}; $result }'
        )
    result = base_cmd
    if pipeline_parts:
        result += ' | ' + ' | '.join(pipeline_parts)
    return result
def _convert_mkdir(cmd: str) -> str:
    if not cmd or not cmd.strip():
        return 'New-Item -ItemType Directory'
    parts = _parse_command_line(cmd)
    if not parts:
        return 'New-Item -ItemType Directory'
    if parts[0] in ('mkdir', '/bin/mkdir', '/usr/bin/mkdir'):
        parts = parts[1:]
    if not parts:
        return 'New-Item -ItemType Directory'
    flags: Set[str] = set()
    long_flags: Set[str] = set()
    mode_value: Optional[str] = None
    context_value: Optional[str] = None
    directories: List[str] = []
    i = 0
    while i < len(parts):
        part = parts[i]
        if part == '--':
            directories.extend(parts[i + 1:])
            break
        if part.startswith('/') and len(part) >= 2:
            if len(part) == 2 and part[1].isalpha():
                part = '-' + part[1:]
            elif len(part) > 2 and part[1].isalpha():
                part = '--' + part[1:]
        if part.startswith('--'):
            long_opt = part[2:]
            if '=' in long_opt:
                opt_name, opt_value = long_opt.split('=', 1)
                long_flags.add(opt_name)
                if opt_name == 'mode':
                    mode_value = opt_value
                elif opt_name == 'context':
                    context_value = opt_value
            else:
                long_flags.add(long_opt)
                if long_opt == 'mode' and i + 1 < len(parts):
                    i += 1
                    mode_value = parts[i]
                elif long_opt == 'context' and i + 1 < len(parts):
                    i += 1
                    context_value = parts[i]
            i += 1
            continue
        if part.startswith('-') and len(part) > 1:
            opt_chars = part[1:]
            for j, char in enumerate(opt_chars):
                flags.add(char)
                if char == 'm' and j == len(opt_chars) - 1 and i + 1 < len(parts):
                    i += 1
                    next_part = parts[i]
                    if not next_part.startswith('-') and not (next_part.startswith('/') and len(next_part) >= 2 and next_part[1].isalpha()):
                        mode_value = next_part
                    else:
                        i -= 1
                elif char == 'Z' and j == len(opt_chars) - 1 and i + 1 < len(parts):
                    i += 1
                    next_part = parts[i]
                    if not next_part.startswith('-') and not (next_part.startswith('/') and len(next_part) >= 2 and next_part[1].isalpha()):
                        context_value = next_part
                    else:
                        i -= 1
            i += 1
            continue
        directories.append(part)
        i += 1
    return _build_mkdir_powershell_command(flags, long_flags, mode_value, context_value, directories)
def _build_mkdir_powershell_command(
    flags: Set[str],
    long_flags: Set[str],
    mode_value: Optional[str],
    context_value: Optional[str],
    directories: List[str]
) -> str:
    show_help = 'help' in long_flags
    show_version = 'version' in long_flags
    if show_help:
        return (
            'Write-Output "mkdir - Create directories\n'
            'Usage: mkdir [options] directory...\n'
            'Options:\n'
            '  -p, --parents     Create parent directories as needed\n'
            '  -m, --mode=MODE   Set file mode (permissions)\n'
            '  -v, --verbose     Print message for each created directory\n'
            '  -Z, --context=CTX Set SELinux security context\n'
            '  --help            Display this help\n'
            '  --version         Display version information"'
        )
    if show_version:
        return 'Write-Output "mkdir version 8.32"'
    parents = 'p' in flags or 'parents' in long_flags
    verbose = 'v' in flags or 'verbose' in long_flags
    base_cmd = 'New-Item -ItemType Directory'
    ps_params: List[str] = []
    if parents:
        ps_params.append('-Force')
    if verbose:
        ps_params.append('-Verbose')
    if directories:
        quoted_dirs = []
        for d in directories:
            if ' ' in d and not (d.startswith('"') or d.startswith("'")):
                quoted_dirs.append(f'"{d}"')
            else:
                quoted_dirs.append(d)
        if len(quoted_dirs) == 1:
            ps_params.append(f'-Path {quoted_dirs[0]}')
        else:
            ps_params.append(f'-Path {", ".join(quoted_dirs)}')
    result_parts = [base_cmd]
    result_parts.extend(ps_params)
    return ' '.join(result_parts)
def convert_ls_command(cmd: str) -> str:
    return _convert_ls(cmd)
def convert_cat_command(cmd: str) -> str:
    return _convert_cat(cmd)
def _convert_rm(cmd: str) -> str:
    if not cmd or not cmd.strip():
        return 'Remove-Item'
    parts = _parse_command_line(cmd)
    if not parts:
        return 'Remove-Item'
    if parts[0] in ('rm', '/bin/rm', '/usr/bin/rm'):
        parts = parts[1:]
    if not parts:
        return 'Remove-Item'
    flags: Set[str] = set()
    long_flags: Set[str] = set()
    files: List[str] = []
    i = 0
    while i < len(parts):
        part = parts[i]
        if part == '--':
            files.extend(parts[i + 1:])
            break
        if part.startswith('/') and len(part) == 2 and part[1].isalpha():
            part = '-' + part[1:]
        if part.startswith('--'):
            long_opt = part[2:]
            if '=' in long_opt:
                opt_name, _ = long_opt.split('=', 1)
                long_flags.add(opt_name)
            else:
                long_flags.add(long_opt)
            i += 1
            continue
        if part.startswith('-') and len(part) > 1:
            opt_chars = part[1:]
            for char in opt_chars:
                flags.add(char)
            i += 1
            continue
        files.append(part)
        i += 1
    return _build_rm_powershell_command(flags, long_flags, files)
def _build_rm_powershell_command(
    flags: Set[str],
    long_flags: Set[str],
    files: List[str]
) -> str:
    show_help = 'help' in long_flags
    show_version = 'version' in long_flags
    if show_help:
        return (
            'Write-Output "rm - Remove files or directories\n'
            'Usage: rm [options] file...\n'
            'Options:\n'
            '  -f, --force              Ignore non-existent files, never prompt\n'
            '  -i                       Prompt before every removal\n'
            '  -I                       Prompt once before removing many files\n'
            '  -r, -R, --recursive      Remove directories and their contents\n'
            '  -d, --dir                Remove empty directories\n'
            '  -v, --verbose            Explain what is being done\n'
            '  --help                   Display this help\n'
            '  --version                Display version information\n'
            '  --no-preserve-root       Do not treat \"/\" specially\n'
            '  --one-file-system        Skip directories on different file systems"'
        )
    if show_version:
        return 'Write-Output "rm (coreutils) 8.32"'
    force = 'f' in flags or 'force' in long_flags
    interactive_always = 'i' in flags
    interactive_once = 'I' in flags
    recursive = 'r' in flags or 'R' in flags or 'recursive' in long_flags
    remove_empty_dir = 'd' in flags or 'dir' in long_flags
    verbose = 'v' in flags or 'verbose' in long_flags
    no_preserve_root = 'no-preserve-root' in long_flags
    one_file_system = 'one-file-system' in long_flags
    base_cmd = 'Remove-Item'
    ps_params: List[str] = []
    if recursive:
        ps_params.append('-Recurse')
    if force:
        ps_params.append('-Force')
    if interactive_always:
        ps_params.append('-Confirm')
    elif interactive_once:
        ps_params.append('-Confirm')
    if verbose:
        ps_params.append('-Verbose')
    if files:
        quoted_files = []
        for f in files:
            if ' ' in f and not (f.startswith('"') or f.startswith("'")):
                quoted_files.append(f'"{f}"')
            else:
                quoted_files.append(f)
        if len(quoted_files) == 1:
            ps_params.append(f'-Path {quoted_files[0]}')
        else:
            ps_params.append(f'-Path {", ".join(quoted_files)}')
    result_parts = [base_cmd]
    result_parts.extend(ps_params)
    return ' '.join(result_parts)
def convert_rm_command(cmd: str) -> str:
    return _convert_rm(cmd)
def _convert_cp(cmd: str) -> str:
    if not cmd or not cmd.strip():
        return 'Copy-Item'
    parts = _parse_command_line(cmd)
    if not parts:
        return 'Copy-Item'
    if parts[0] in ('cp', '/bin/cp', '/usr/bin/cp'):
        parts = parts[1:]
    if not parts:
        return 'Copy-Item'
    flags: Set[str] = set()
    long_flags: Set[str] = set()
    preserve_attrs: Optional[List[str]] = None
    no_preserve_attrs: Optional[List[str]] = None
    target_dir: Optional[str] = None
    sources: List[str] = []
    destination: Optional[str] = None
    i = 0
    while i < len(parts):
        part = parts[i]
        if part == '--':
            remaining = parts[i + 1:]
            if target_dir:
                sources.extend(remaining)
            elif len(remaining) >= 2:
                sources.extend(remaining[:-1])
                destination = remaining[-1]
            elif len(remaining) == 1:
                sources.append(remaining[0])
            break
        if part.startswith('/') and len(part) == 2 and part[1].isalpha():
            part = '-' + part[1:]
        if part.startswith('--'):
            long_opt = part[2:]
            if '=' in long_opt:
                opt_name, opt_value = long_opt.split('=', 1)
                long_flags.add(opt_name)
                if opt_name == 'target-directory':
                    target_dir = opt_value
                elif opt_name == 'preserve':
                    if opt_value:
                        preserve_attrs = opt_value.split(',')
                elif opt_name == 'no-preserve':
                    if opt_value:
                        no_preserve_attrs = opt_value.split(',')
                elif opt_name == 'backup':
                    long_flags.add('backup')
                elif opt_name == 'reflink':
                    long_flags.add('reflink')
                elif opt_name == 'sparse':
                    long_flags.add('sparse')
            else:
                long_flags.add(long_opt)
                if long_opt == 'target-directory' and i + 1 < len(parts):
                    i += 1
                    next_part = parts[i]
                    if not next_part.startswith('-') and not (next_part.startswith('/') and len(next_part) == 2 and next_part[1].isalpha()):
                        target_dir = next_part
                    else:
                        i -= 1
            i += 1
            continue
        if part.startswith('-') and len(part) > 1:
            opt_chars = part[1:]
            for j, char in enumerate(opt_chars):
                flags.add(char)
                if char == 't' and j == len(opt_chars) - 1 and i + 1 < len(parts):
                    i += 1
                    next_part = parts[i]
                    if not next_part.startswith('-') and not (next_part.startswith('/') and len(next_part) == 2 and next_part[1].isalpha()):
                        target_dir = next_part
                    else:
                        i -= 1
            i += 1
            continue
        sources.append(part)
        i += 1
    if target_dir:
        destination = target_dir
    elif len(sources) >= 2 and not destination:
        destination = sources[-1]
        sources = sources[:-1]
    return _build_cp_powershell_command(
        flags, long_flags, preserve_attrs, no_preserve_attrs, sources, destination
    )
def _build_cp_powershell_command(
    flags: Set[str],
    long_flags: Set[str],
    preserve_attrs: Optional[List[str]],
    no_preserve_attrs: Optional[List[str]],
    sources: List[str],
    destination: Optional[str]
) -> str:
    show_help = 'help' in long_flags
    show_version = 'version' in long_flags
    if show_help:
        return (
            'Write-Output "cp - Copy files and directories\n'
            'Usage: cp [options] source dest\n'
            '   or: cp [options] source... directory\n'
            'Options:\n'
            '  -a, --archive                Same as -dR --preserve=all\n'
            '  -b, --backup                 Make backup before removal\n'
            '  -d                           Same as --no-dereference --preserve=links\n'
            '  -f, --force                  Overwrite existing files without prompting\n'
            '  -i, --interactive            Prompt before overwriting\n'
            '  -l, --link                   Hard link files instead of copying\n'
            '  -L, --dereference            Always follow symbolic links in SOURCE\n'
            '  -n, --no-clobber             Do not overwrite existing files\n'
            '  -p                           Same as --preserve=mode,ownership,timestamps\n'
            '  -P, --no-dereference         Never follow symbolic links in SOURCE\n'
            '  -R, -r, --recursive          Copy directories recursively\n'
            '  -s, --symbolic-link          Make symbolic links instead of copying\n'
            '  -t, --target-directory=DIR   Copy all SOURCE arguments into DIR\n'
            '  -T, --no-target-directory    Treat DEST as a normal file\n'
            '  -u, --update                 Copy only when source is newer or missing\n'
            '  -v, --verbose                Explain what is being done\n'
            '  -x, --one-file-system        Stay on this file system\n'
            '  --parents                    Use full source file name under DIRECTORY\n'
            '  --preserve[=ATTR_LIST]       Preserve attributes\n'
            '  --no-preserve=ATTR_LIST      Don\'t preserve attributes\n'
            '  --remove-destination         Remove each destination file before copying\n'
            '  --help                       Display this help\n'
            '  --version                    Display version information"'
        )
    if show_version:
        return 'Write-Output "cp (coreutils) 8.32"'
    archive = 'a' in flags or 'archive' in long_flags
    backup = 'b' in flags or 'backup' in long_flags
    dereference = 'L' in flags or 'dereference' in long_flags
    force = 'f' in flags or 'force' in long_flags
    interactive = 'i' in flags or 'interactive' in long_flags
    link = 'l' in flags or 'link' in long_flags
    no_clobber = 'n' in flags or 'no-clobber' in long_flags
    preserve = 'p' in flags or 'preserve' in long_flags
    no_dereference = 'P' in flags or 'no-dereference' in long_flags
    recursive = 'r' in flags or 'R' in flags or 'recursive' in long_flags
    symbolic_link = 's' in flags or 'symbolic-link' in long_flags
    update = 'u' in flags or 'update' in long_flags
    verbose = 'v' in flags or 'verbose' in long_flags
    one_file_system = 'x' in flags or 'one-file-system' in long_flags
    parents = 'parents' in long_flags
    remove_destination = 'remove-destination' in long_flags
    copy_contents = 'copy-contents' in long_flags
    strip_trailing_slashes = 'strip-trailing-slashes' in long_flags
    no_target_directory = 'T' in flags or 'no-target-directory' in long_flags
    if archive:
        recursive = True
        preserve = True
    base_cmd = 'Copy-Item'
    ps_params: List[str] = []
    if recursive:
        ps_params.append('-Recurse')
    if force:
        ps_params.append('-Force')
    if interactive:
        ps_params.append('-Confirm')
    if verbose:
        ps_params.append('-Verbose')
    if sources:
        quoted_sources = []
        for s in sources:
            if ' ' in s and not (s.startswith('"') or s.startswith("'")):
                quoted_sources.append(f'"{s}"')
            else:
                quoted_sources.append(s)
        if len(quoted_sources) == 1:
            ps_params.append(f'-Path {quoted_sources[0]}')
        else:
            ps_params.append(f'-Path {", ".join(quoted_sources)}')
    else:
        ps_params.append('-Path <source>')
    if destination:
        if ' ' in destination and not (destination.startswith('"') or destination.startswith("'")):
            destination = f'"{destination}"'
        ps_params.append(f'-Destination {destination}')
    else:
        ps_params.append('-Destination <dest>')
    result_parts = [base_cmd]
    result_parts.extend(ps_params)
    return ' '.join(result_parts)
def convert_cp_command(cmd: str) -> str:
    return _convert_cp(cmd)
def _convert_mv(cmd: str) -> str:
    parts = cmd.split()
    if len(parts) < 3:
        return 'Move-Item'
    flags = set()
    args = []
    for part in parts[1:]:
        if part.startswith('-'):
            for char in part[1:]:
                flags.add(char)
        else:
            args.append(part)
    base_cmd = 'Move-Item'
    ps_flags = []
    if 'f' in flags:
        ps_flags.append('-Force')
    if len(args) >= 2:
        source = args[0]
        dest = args[1]
        if ps_flags:
            return f"{base_cmd} {source} {dest} {' '.join(ps_flags)}"
        return f'{base_cmd} {source} {dest}'
    elif len(args) == 1:
        return f'{base_cmd} {args[0]}'
    return base_cmd
def _build_mv_powershell_command(
    flags: Set[str],
    long_flags: Set[str],
    sources: List[str],
    destination: Optional[str]
) -> str:
    show_help = 'help' in long_flags
    show_version = 'version' in long_flags
    if show_help:
        return (
            'Write-Output "mv - Move (rename) files\n'
            'Usage: mv [options] source dest\n'
            '   or: mv [options] source... directory\n'
            'Options:\n'
            '  -f, --force                  Do not prompt before overwriting\n'
            '  -i, --interactive            Prompt before overwriting\n'
            '  -n, --no-clobber             Do not overwrite existing files\n'
            '  -u, --update                 Move only when source is newer\n'
            '  -v, --verbose                Explain what is being done\n'
            '  -t, --target-directory=DIR   Move all SOURCE arguments into DIR\n'
            '  -T, --no-target-directory    Treat DEST as a normal file\n'
            '  --backup[=CONTROL]           Make backup before removal\n'
            '  --strip-trailing-slashes     Remove trailing slashes from sources\n'
            '  --help                       Display this help\n'
            '  --version                    Display version information"'
        )
    if show_version:
        return 'Write-Output "mv (coreutils) 8.32"'
    force = 'f' in flags or 'force' in long_flags
    interactive = 'i' in flags or 'interactive' in long_flags
    no_clobber = 'n' in flags or 'no-clobber' in long_flags
    update = 'u' in flags or 'update' in long_flags
    verbose = 'v' in flags or 'verbose' in long_flags
    backup = 'b' in flags or 'backup' in long_flags
    strip_trailing_slashes = 'strip-trailing-slashes' in long_flags
    no_target_directory = 'T' in flags or 'no-target-directory' in long_flags
    base_cmd = 'Move-Item'
    ps_params: List[str] = []
    if force:
        ps_params.append('-Force')
    if interactive:
        ps_params.append('-Confirm')
    if verbose:
        ps_params.append('-Verbose')
    if sources:
        quoted_sources = []
        for s in sources:
            if ' ' in s and not (s.startswith('"') or s.startswith("'")):
                quoted_sources.append(f'"{s}"')
            else:
                quoted_sources.append(s)
        if len(quoted_sources) == 1:
            ps_params.append(f'-Path {quoted_sources[0]}')
        else:
            ps_params.append(f'-Path {", ".join(quoted_sources)}')
    else:
        ps_params.append('-Path <source>')
    if destination:
        if ' ' in destination and not (destination.startswith('"') or destination.startswith("'")):
            destination = f'"{destination}"'
        ps_params.append(f'-Destination {destination}')
    else:
        ps_params.append('-Destination <dest>')
    result_parts = [base_cmd]
    result_parts.extend(ps_params)
    return ' '.join(result_parts)
def convert_mv_command(cmd: str) -> str:
    return _convert_mv(cmd)
def _convert_grep(cmd: str) -> str:
    if not cmd or not cmd.strip():
        return 'Select-String'
    parts = _parse_command_line(cmd)
    if not parts:
        return 'Select-String'
    if parts[0] in ('grep', '/bin/grep', '/usr/bin/grep', 'egrep', 'fgrep'):
        parts = parts[1:]
    if not parts:
        return 'Select-String'
    flags: Set[str] = set()
    long_flags: Set[str] = set()
    flag_values: dict = {}
    patterns: List[str] = []
    files: List[str] = []
    i = 0
    while i < len(parts):
        part = parts[i]
        if part == '--':
            remaining = parts[i + 1:]
            if remaining:
                if not patterns:
                    patterns.append(remaining[0])
                    files.extend(remaining[1:])
                else:
                    files.extend(remaining)
            break
        if part.startswith('/') and len(part) >= 2:
            if len(part) == 2 and part[1].isalpha():
                part = '-' + part[1:]
            elif len(part) > 2 and part[1].isalpha():
                part = '--' + part[1:]
        if part.startswith('--'):
            long_opt = part[2:]
            if '=' in long_opt:
                opt_name, opt_value = long_opt.split('=', 1)
                long_flags.add(opt_name)
                flag_values[opt_name] = opt_value
            else:
                long_flags.add(long_opt)
                if long_opt in ('regexp', 'file', 'max-count', 'include', 'exclude', 'exclude-dir', 'label'):
                    if i + 1 < len(parts):
                        i += 1
                        flag_values[long_opt] = parts[i]
            i += 1
            continue
        if part.startswith('-') and len(part) > 1:
            opt_chars = part[1:]
            for j, char in enumerate(opt_chars):
                flags.add(char)
                if char in ('e', 'f', 'm') and j == len(opt_chars) - 1 and i + 1 < len(parts):
                    i += 1
                    flag_values[char] = parts[i]
                elif char in ('A', 'B', 'C') and j == len(opt_chars) - 1 and i + 1 < len(parts):
                    i += 1
                    flag_values[char] = parts[i]
            i += 1
            continue
        if not patterns and 'e' not in flag_values and 'f' not in flag_values and 'regexp' not in flag_values and 'file' not in flag_values:
            patterns.append(part)
        else:
            files.append(part)
        i += 1
    return _build_grep_powershell_command(flags, long_flags, flag_values, patterns, files)
def _build_grep_powershell_command(
    flags: Set[str],
    long_flags: Set[str],
    flag_values: dict,
    patterns: List[str],
    files: List[str]
) -> str:
    show_help = 'help' in long_flags
    show_version = 'version' in long_flags
    if show_help:
        return (
            'Write-Output "grep - Search for patterns in files\n'
            'Usage: grep [options] pattern [file...]\n'
            'Options:\n'
            '  -i, --ignore-case          Ignore case distinctions\n'
            '  -v, --invert-match         Select non-matching lines\n'
            '  -n, --line-number          Print line number with output\n'
            '  -l, --files-with-matches   Print only names of files with matches\n'
            '  -L, --files-without-match  Print only names of files without matches\n'
            '  -c, --count                Print count of matching lines\n'
            '  -w, --word-regexp          Match whole words only\n'
            '  -x, --line-regexp          Match whole lines only\n'
            '  -r, -R, --recursive        Read all files recursively\n'
            '  -E, --extended-regexp      Use extended regular expressions\n'
            '  -F, --fixed-strings        Treat pattern as fixed strings\n'
            '  -e, --regexp=PATTERN       Use PATTERN for matching\n'
            '  -f, --file=FILE            Read patterns from FILE\n'
            '  -H, --with-filename        Print filename with each match\n'
            '  -h, --no-filename          Suppress filename prefix\n'
            '  -o, --only-matching        Show only matching part\n'
            '  -q, --quiet, --silent      Suppress output\n'
            '  -s, --no-messages          Suppress error messages\n'
            '  -m, --max-count=NUM        Stop after NUM matches\n'
            '  -A, --after-context=NUM    Print NUM lines after match\n'
            '  -B, --before-context=NUM   Print NUM lines before match\n'
            '  -C, --context=NUM          Print NUM lines before and after\n'
            '  --include=PATTERN          Search only files matching pattern\n'
            '  --exclude=PATTERN          Skip files matching pattern\n'
            '  --exclude-dir=PATTERN      Skip directories matching pattern\n'
            '  --help                     Display this help\n'
            '  --version                  Display version information"'
        )
    if show_version:
        return 'Write-Output "grep (GNU grep) 3.7"'
    ignore_case = 'i' in flags or 'ignore-case' in long_flags
    invert_match = 'v' in flags or 'invert-match' in long_flags
    line_number = 'n' in flags or 'line-number' in long_flags
    files_with_matches = 'l' in flags or 'files-with-matches' in long_flags
    files_without_match = 'L' in flags or 'files-without-match' in long_flags
    count_only = 'c' in flags or 'count' in long_flags
    word_regexp = 'w' in flags or 'word-regexp' in long_flags
    line_regexp = 'x' in flags or 'line-regexp' in long_flags
    recursive = 'r' in flags or 'R' in flags or 'recursive' in long_flags
    extended_regexp = 'E' in flags or 'extended-regexp' in long_flags
    fixed_strings = 'F' in flags or 'fixed-strings' in long_flags
    with_filename = 'H' in flags or 'with-filename' in long_flags
    no_filename = 'h' in flags or 'no-filename' in long_flags
    only_matching = 'o' in flags or 'only-matching' in long_flags
    quiet = 'q' in flags or 'quiet' in long_flags or 'silent' in long_flags
    no_messages = 's' in flags or 'no-messages' in long_flags
    if 'e' in flag_values:
        patterns = [flag_values['e']]
    elif 'regexp' in flag_values:
        patterns = [flag_values['regexp']]
    elif 'f' in flag_values or 'file' in flag_values:
        pattern_file = flag_values.get('f') or flag_values.get('file', '')
        patterns = [f"(Get-Content {pattern_file})"]
    base_cmd = 'Select-String'
    ps_params: List[str] = []
    pipeline_parts: List[str] = []
    if patterns:
        pattern = patterns[0]
        if '"' in pattern and "'" not in pattern:
            pattern_quoted = f"'{pattern}'"
        else:
            escaped_pattern = pattern.replace('"', '`"')
            pattern_quoted = f'"{escaped_pattern}"'
        if word_regexp:
            escaped_pattern = pattern.replace('"', '`"')
            pattern_quoted = f'"\\b{escaped_pattern}\\b"'
        if line_regexp:
            escaped_pattern = pattern.replace('"', '`"')
            pattern_quoted = f'"^{escaped_pattern}$"'
        ps_params.append(f'-Pattern {pattern_quoted}')
    else:
        ps_params.append('-Pattern <pattern>')
    if files:
        quoted_files = []
        for f in files:
            if ' ' in f and not (f.startswith('"') or f.startswith("'")):
                quoted_files.append(f'"{f}"')
            else:
                quoted_files.append(f)
        if len(quoted_files) == 1:
            ps_params.append(f'-Path {quoted_files[0]}')
        else:
            ps_params.append(f'-Path {", ".join(quoted_files)}')
    if recursive:
        ps_params.append('-Recurse')
    if ignore_case:
        ps_params.append('-CaseSensitive:$false')
    if invert_match:
        ps_params.append('-NotMatch')
    if fixed_strings:
        ps_params.append('-SimpleMatch')
    if files_with_matches:
        pipeline_parts.append('Select-Object -ExpandProperty Filename -Unique')
    elif files_without_match:
        pipeline_parts.append('Select-Object -ExpandProperty Filename -Unique')
        pipeline_parts.append('ForEach-Object { "Non-matching: $_" }')
    elif count_only:
        pipeline_parts.append('Group-Object Filename | Select-Object Name, Count')
    else:
        format_parts: List[str] = []
        if only_matching:
            ps_params.append('-AllMatches')
            pipeline_parts.append('ForEach-Object { $_.Matches | ForEach-Object { $_.Value } }')
        elif line_number:
            if with_filename or (len(files) > 1 and not no_filename):
                pipeline_parts.append('ForEach-Object { "$($_.Filename):$($_.LineNumber): $($_.Line)" }')
            else:
                pipeline_parts.append('ForEach-Object { "$($_.LineNumber): $($_.Line)" }')
        elif with_filename or (len(files) > 1 and not no_filename):
            pipeline_parts.append('ForEach-Object { "$($_.Filename): $($_.Line)" }')
        elif no_filename:
            pipeline_parts.append('ForEach-Object { $_.Line }')
        else:
            pipeline_parts.append('ForEach-Object { $_.Line }')
    if quiet:
        pipeline_parts.append('Out-Null')
    if 'm' in flag_values or 'max-count' in flag_values:
        max_count = flag_values.get('m') or flag_values.get('max-count', '1')
        pipeline_parts.insert(0, f'Select-Object -First {max_count}')
    context_before = 0
    context_after = 0
    if 'B' in flag_values or 'before-context' in flag_values:
        context_before = int(flag_values.get('B') or flag_values.get('before-context', 0))
    if 'A' in flag_values or 'after-context' in flag_values:
        context_after = int(flag_values.get('A') or flag_values.get('after-context', 0))
    if 'C' in flag_values or 'context' in flag_values:
        context_val = int(flag_values.get('C') or flag_values.get('context', 0))
        context_before = context_val
        context_after = context_val
    if context_before > 0 or context_after > 0:
        ps_params.append(f'-Context {context_before},{context_after}')
    result_parts = [base_cmd]
    result_parts.extend(ps_params)
    result = ' '.join(result_parts)
    if pipeline_parts:
        result += ' | ' + ' | '.join(pipeline_parts)
    return result
def convert_grep_command(cmd: str) -> str:
    return _convert_grep(cmd)
def _convert_ps(cmd: str) -> str:
    if not cmd or not cmd.strip():
        return 'Get-Process'
    parts = _parse_command_line(cmd)
    if not parts:
        return 'Get-Process'
    if parts[0] in ('ps', '/bin/ps', '/usr/bin/ps'):
        parts = parts[1:]
    if not parts:
        return 'Get-Process'
    flags: Set[str] = set()
    long_flags: Set[str] = set()
    flag_values: dict = {}
    i = 0
    while i < len(parts):
        part = parts[i]
        if part == '--':
            i += 1
            continue
        if part.startswith('/') and len(part) >= 2:
            if len(part) == 2 and part[1].isalpha():
                part = '-' + part[1:]
            elif len(part) > 2 and part[1].isalpha():
                part = '--' + part[1:]
        if part.startswith('--'):
            long_opt = part[2:]
            if '=' in long_opt:
                opt_name, opt_value = long_opt.split('=', 1)
                long_flags.add(opt_name)
                flag_values[opt_name] = opt_value
            else:
                long_flags.add(long_opt)
                if long_opt in ('pid', 'User', 'Group', 'format'):
                    if i + 1 < len(parts):
                        i += 1
                        flag_values[long_opt] = parts[i]
            i += 1
            continue
        if part.startswith('-') and len(part) > 1:
            opt_chars = part[1:]
            for j, char in enumerate(opt_chars):
                flags.add(char)
                if char in ('p', 'C', 'U', 'G', 'o') and j == len(opt_chars) - 1 and i + 1 < len(parts):
                    i += 1
                    flag_values[char] = parts[i]
            i += 1
            continue
        i += 1
    return _build_ps_powershell_command(flags, long_flags, flag_values)
def _build_ps_powershell_command(
    flags: Set[str],
    long_flags: Set[str],
    flag_values: dict
) -> str:
    show_help = 'help' in long_flags
    show_version = 'version' in long_flags
    if show_help:
        return (
            'Write-Output "ps - Report a snapshot of the current processes\\n'
            'Usage: ps [options]\\n'
            'Options:\\n'
            '  -e, -A          Select all processes\\n'
            '  -a              Select all except session leaders\\n'
            '  -f              Full-format listing\\n'
            '  -F              Extra full-format listing\\n'
            '  -l              Long format\\n'
            '  -u              User-oriented format\\n'
            '  -x              Include processes without controlling terminal\\n'
            '  -w, -ww         Wide output\\n'
            '  -p, --pid       Select by process ID\\n'
            '  -C              Select by command name\\n'
            '  -U, --User      Select by user ID\\n'
            '  -G, --Group     Select by group ID\\n'
            '  -o, --format    User-defined format\\n'
            '  --no-headers    Suppress header line\\n'
            '  --help          Display this help\\n'
            '  --version       Display version information"'
        )
    if show_version:
        return 'Write-Output "ps from procps-ng 3.3.17"'
    all_processes = 'e' in flags or 'A' in flags or 'a' in flags
    full_format = 'f' in flags
    extra_full_format = 'F' in flags
    long_format = 'l' in flags
    user_oriented = 'u' in flags
    no_tty = 'x' in flags
    wide_output = 'w' in flags or 'ww' in long_flags
    no_headers = 'no-headers' in long_flags
    select_by_pid = 'p' in flag_values or 'pid' in flag_values
    select_by_name = 'C' in flag_values
    select_by_user = 'U' in flag_values or 'User' in flag_values
    select_by_group = 'G' in flag_values or 'Group' in flag_values
    user_format = 'o' in flag_values or 'format' in flag_values
    base_cmd = 'Get-Process'
    ps_params: List[str] = []
    pipeline_parts: List[str] = []
    if select_by_pid:
        pid_value = flag_values.get('p') or flag_values.get('pid', '')
        ps_params.append(f'-Id {pid_value}')
    if select_by_name:
        name_value = flag_values.get('C', '')
        ps_params.append(f'-Name {name_value}')
    if user_format:
        format_spec = flag_values.get('o') or flag_values.get('format', '')
        format_mapping = {
            'pid': 'Id',
            'ppid': 'Parent.Id',
            'pgid': 'Parent.Id',
            'comm': 'ProcessName',
            'command': 'Path',
            'cmd': 'Path',
            'args': 'CommandLine',
            'user': 'UserName',
            'uid': 'Id',
            'gid': 'Id',
            'pcpu': 'CPU',
            'pmem': 'WorkingSet64',
            'vsz': 'VirtualMemorySize64',
            'rss': 'WorkingSet64',
            'tty': 'MainWindowHandle',
            'stat': 'Responding',
            'start': 'StartTime',
            'time': 'TotalProcessorTime',
            'etime': 'UserProcessorTime',
            'nice': 'PriorityClass',
            'thcount': 'Threads.Count',
        }
        format_fields = [f.strip() for f in format_spec.replace(',', ' ').split()]
        ps_properties = []
        for field in format_fields:
            if field in format_mapping:
                ps_properties.append(format_mapping[field])
            else:
                ps_properties.append(field)
        if ps_properties:
            pipeline_parts.append(f"Select-Object {', '.join(ps_properties)}")
    if user_oriented and not user_format:
        if select_by_user:
            user_name = flag_values.get('U') or flag_values.get('User', '')
            pipeline_parts.append(f'Where-Object {{ $_.UserName -like "*{user_name}*" }}')
        pipeline_parts.append('Select-Object UserName, CPU, Id, ProcessName')
        pipeline_parts.append('Format-Table -AutoSize')
    elif full_format or extra_full_format:
        if not user_format:
            if extra_full_format:
                pipeline_parts.append('Select-Object Id, Parent.Id, CPU, WorkingSet, VirtualMemorySize, ProcessName, Path')
            else:
                pipeline_parts.append('Select-Object Id, CPU, WorkingSet, ProcessName')
        pipeline_parts.append('Format-Table -AutoSize')
    elif long_format:
        if not user_format:
            pipeline_parts.append('Select-Object Id, PriorityClass, CPU, WorkingSet, PagedMemorySize, ProcessName')
        pipeline_parts.append('Format-Table -AutoSize')
    elif wide_output or no_headers:
        if not user_format:
            pipeline_parts.append('Format-Table -AutoSize')
        if no_headers:
            pipeline_parts.append('Format-Table -HideTableHeaders')
    elif select_by_pid or select_by_name:
        pass
    else:
        if not user_format:
            pipeline_parts.append('Format-Table -AutoSize')
    result_parts = [base_cmd]
    result_parts.extend(ps_params)
    result = ' '.join(result_parts)
    if pipeline_parts:
        result += ' | ' + ' | '.join(pipeline_parts)
    return result
def _convert_man(cmd: str) -> str:
    if not cmd or not cmd.strip():
        return 'Get-Help'
    parts = _parse_command_line(cmd)
    if not parts:
        return 'Get-Help'
    if parts[0] in ('man', '/usr/bin/man', '/bin/man'):
        parts = parts[1:]
    if not parts:
        return 'Get-Help'
    flags: Set[str] = set()
    long_flags: Set[str] = set()
    flag_values: dict = {}
    sections: List[str] = []
    pages: List[str] = []
    i = 0
    while i < len(parts):
        part = parts[i]
        if part == '--':
            remaining = parts[i + 1:]
            for item in remaining:
                if item.isdigit() or (len(item) == 1 and item in '123456789n'):
                    sections.append(item)
                else:
                    pages.append(item)
            break
        if part.startswith('/') and len(part) >= 2:
            if len(part) == 2 and part[1].isalpha():
                part = '-' + part[1:]
            elif len(part) > 2 and part[1].isalpha():
                part = '--' + part[1:]
        if part.startswith('--'):
            long_opt = part[2:]
            if '=' in long_opt:
                opt_name, opt_value = long_opt.split('=', 1)
                long_flags.add(opt_name)
                flag_values[opt_name] = opt_value
            else:
                long_flags.add(long_opt)
                if long_opt in ('section', 'sections', 'locale', 'config-file') and i + 1 < len(parts):
                    i += 1
                    flag_values[long_opt] = parts[i]
            i += 1
            continue
        if part.startswith('-') and len(part) > 1:
            opt_chars = part[1:]
            for j, char in enumerate(opt_chars):
                flags.add(char)
                if char in ('s', 'L', 'C') and j == len(opt_chars) - 1 and i + 1 < len(parts):
                    i += 1
                    flag_values[char] = parts[i]
            i += 1
            continue
        if part.isdigit() or (len(part) == 1 and part in '123456789n'):
            sections.append(part)
        else:
            pages.append(part)
        i += 1
    return _build_man_powershell_command(flags, long_flags, flag_values, sections, pages)
def _build_man_powershell_command(
    flags: Set[str],
    long_flags: Set[str],
    flag_values: dict,
    sections: List[str],
    pages: List[str]
) -> str:
    show_help = 'help' in long_flags or '?' in flags
    show_usage = 'usage' in long_flags
    show_version = 'version' in long_flags or 'V' in flags
    if show_help:
        return (
            'Write-Output "man - Display manual pages\n'
            'Usage: man [options] [section] page...\n'
            'Options:\n'
            '  -k, --apropos        Search for keyword in all pages\n'
            '  -f, --whatis         Display one-line descriptions\n'
            '  -a, --all            Open all matching pages\n'
            '  -w, --where          Print location of man page\n'
            '  -K                   Global search for text\n'
            '  -i, --ignore-case    Case insensitive search\n'
            '  -I, --match-case     Case sensitive search\n'
            '  -l, --local-file     Treat argument as local file\n'
            '  -L, --locale         Set locale for output\n'
            '  -s, --sections       List of sections to search\n'
            '  -?, --help           Display help\n'
            '  --usage              Show brief usage\n'
            '  -V, --version        Display version"'
        )
    if show_usage:
        return 'Write-Output "Usage: man [options] [section] page..."'
    if show_version:
        return 'Write-Output "man 2.9.4"'
    apropos = 'k' in flags or 'apropos' in long_flags
    whatis = 'f' in flags or 'whatis' in long_flags
    all_pages = 'a' in flags or 'all' in long_flags
    where_flag = 'w' in flags or 'where' in long_flags or 'location' in long_flags
    global_search = 'K' in flags
    ignore_case = 'i' in flags or 'ignore-case' in long_flags
    match_case = 'I' in flags or 'match-case' in long_flags
    local_file = 'l' in flags or 'local-file' in long_flags
    if 's' in flag_values:
        section_value = flag_values['s']
        sections.extend(section_value.split(':'))
    if 'section' in flag_values:
        sections.extend(flag_values['section'].split(':'))
    if 'sections' in flag_values:
        sections.extend(flag_values['sections'].split(':'))
    if apropos:
        if pages:
            if len(pages) == 1:
                return f'Get-Help *{pages[0]}*'
            else:
                search_terms = ', '.join([f'"*{p}*"' for p in pages])
                return f'Get-Help @({search_terms})'
        else:
            return 'Get-Help'
    if whatis:
        if pages:
            if len(pages) == 1:
                return f'Get-Command {pages[0]} | Select-Object Name, CommandType, Source, Version'
            else:
                page_list = ', '.join(pages)
                return f'Get-Command @({page_list}) | Select-Object Name, CommandType, Source, Version'
        else:
            return 'Get-Command | Select-Object Name, CommandType -First 20'
    if global_search:
        if pages:
            if len(pages) == 1:
                return f'Get-Help * | Select-String -Pattern "{pages[0]}"'
            else:
                patterns = ', '.join([f'"{p}"' for p in pages])
                return f'Get-Help * | Select-String -Pattern @({patterns})'
        else:
            return 'Get-Help *'
    if where_flag:
        if pages:
            if len(pages) == 1:
                return f'Get-Help {pages[0]} | Select-Object Name, ModuleName, Category'
            else:
                page_list = ', '.join(pages)
                return f'Get-Help @({page_list}) | Select-Object Name, ModuleName, Category'
        else:
            return 'Write-Output "No page specified"'
    if local_file:
        if pages:
            if len(pages) == 1:
                return f'Get-Content {pages[0]}'
            else:
                page_list = ', '.join(pages)
                return f'Get-Content {page_list}'
        else:
            return 'Get-Content'
    if pages:
        ps_params: List[str] = []
        if all_pages:
            ps_params.append('-Full')
        if len(pages) == 1:
            page = pages[0]
            if ' ' in page and not (page.startswith('"') or page.startswith("'")):
                page = f'"{page}"'
            result = f'Get-Help {page}'
            if ps_params:
                result += ' ' + ' '.join(ps_params)
            return result
        else:
            page_list = []
            for p in pages:
                if ' ' in p and not (p.startswith('"') or p.startswith("'")):
                    page_list.append(f'"{p}"')
                else:
                    page_list.append(p)
            pages_str = ', '.join(page_list)
            result = f'Get-Help @({pages_str})'
            if ps_params:
                result += ' ' + ' '.join(ps_params)
            return result
    else:
        return 'Get-Help'
def convert_man_command(cmd: str) -> str:
    return _convert_man(cmd)
def convert_ps_command(cmd: str) -> str:
    return _convert_ps(cmd)
def _convert_kill(cmd: str) -> str:
    if not cmd or not cmd.strip():
        return 'Stop-Process'
    parts = _parse_command_line(cmd)
    if not parts:
        return 'Stop-Process'
    if parts[0] in ('kill', '/bin/kill', '/usr/bin/kill'):
        parts = parts[1:]
    if not parts:
        return 'Stop-Process'
    flags: Set[str] = set()
    long_flags: Set[str] = set()
    signal: Optional[str] = None
    list_signals = False
    table_signals = False
    print_only = False
    pids: List[str] = []
    names: List[str] = []
    i = 0
    while i < len(parts):
        part = parts[i]
        if part == '--':
            remaining = parts[i + 1:]
            for r in remaining:
                if r.isdigit():
                    pids.append(r)
                else:
                    names.append(r)
            break
        if part.startswith('/') and len(part) >= 2:
            rest = part[1:]
            if rest.isdigit():
                part = '-' + rest
            elif len(part) == 2 and part[1].isalpha():
                part = '-' + rest
            elif rest.isupper() and rest not in ('LIST', 'TABLE', 'HELP', 'VERSION'):
                part = '-' + rest
            elif rest.startswith('SIG') and len(rest) > 3 and rest[3:].isalpha():
                part = '-' + rest
            elif len(part) > 2 and part[1].isalpha():
                part = '--' + rest
        if part.startswith('--'):
            long_opt = part[2:]
            if '=' in long_opt:
                opt_name, opt_value = long_opt.split('=', 1)
                long_flags.add(opt_name)
                if opt_name == 'signal':
                    signal = opt_value
            else:
                long_flags.add(long_opt)
                if long_opt == 'signal' and i + 1 < len(parts):
                    i += 1
                    signal = parts[i]
            i += 1
            continue
        if part.startswith('-') and len(part) > 1:
            opt_chars = part[1:]
            if opt_chars.isdigit():
                signal = opt_chars
                i += 1
                continue
            if (len(opt_chars) > 1 and opt_chars.isalpha() and opt_chars not in ('l', 'L', 'a', 'p', 'q')) or \
               (opt_chars.startswith('SIG') and len(opt_chars) > 3 and opt_chars[3:].isalpha()):
                signal = opt_chars
                i += 1
                continue
            for j, char in enumerate(opt_chars):
                flags.add(char)
                if char == 's' and j == len(opt_chars) - 1 and i + 1 < len(parts):
                    i += 1
                    signal = parts[i]
            i += 1
            continue
        if part.lstrip('-').isdigit():
            pids.append(part.lstrip('-'))
        else:
            names.append(part)
        i += 1
    return _build_kill_powershell_command(
        flags, long_flags, signal, pids, names
    )
def _build_kill_powershell_command(
    flags: Set[str],
    long_flags: Set[str],
    signal: Optional[str],
    pids: List[str],
    names: List[str]
) -> str:
    show_help = 'help' in long_flags
    show_version = 'version' in long_flags
    list_signals = 'l' in flags or 'list' in long_flags
    table_signals = 'L' in flags or 'table' in long_flags
    if show_help:
        return (
            'Write-Output "kill - Send signal to a process\n'
            'Usage: kill [options] <pid|name>...\n'
            'Options:\n'
            '  -s, --signal=SIGNAL    Specify the signal to send\n'
            '  -SIGNAL                Signal number or name (e.g., -9, -SIGKILL)\n'
            '  -l, --list             List signal names\n'
            '  -L, --table            List signal names in a table\n'
            '  -a                     Do not restrict command name to PID\n'
            '  -p                     Print PIDs without sending signals\n'
            '  -q                     Use sigqueue (ignored)\n'
            '  --help                 Display this help\n'
            '  --version              Display version information\n'
            '\n'
            'Signal mapping (bash -> PowerShell):\n'
            '  1/HUP/SIGHUP          Stop-Process (graceful restart not supported)\n'
            '  9/KILL/SIGKILL        Stop-Process -Force\n'
            '  15/TERM/SIGTERM       Stop-Process (default)\n'
            '  Other signals         Stop-Process (best effort)"'
        )
    if show_version:
        return 'Write-Output "kill from util-linux 2.37"'
    if list_signals or table_signals:
        signals = [
            "1) SIGHUP", "2) SIGINT", "3) SIGQUIT", "4) SIGILL",
            "5) SIGTRAP", "6) SIGABRT", "7) SIGBUS", "8) SIGFPE",
            "9) SIGKILL", "10) SIGUSR1", "11) SIGSEGV", "12) SIGUSR2",
            "13) SIGPIPE", "14) SIGALRM", "15) SIGTERM", "16) SIGSTKFLT",
            "17) SIGCHLD", "18) SIGCONT", "19) SIGSTOP", "20) SIGTSTP",
            "21) SIGTTIN", "22) SIGTTOU", "23) SIGURG", "24) SIGXCPU",
            "25) SIGXFSZ", "26) SIGVTALRM", "27) SIGPROF", "28) SIGWINCH",
            "29) SIGIO", "30) SIGPWR", "31) SIGSYS"
        ]
        if table_signals:
            signal_lines = []
            for i in range(0, len(signals), 4):
                row = signals[i:i+4]
                signal_lines.append('  '.join(row))
            return 'Write-Output "' + '\n'.join(signal_lines) + '"'
        else:
            return 'Write-Output "' + ' '.join(signals) + '"'
    use_force = False
    if signal:
        signal_upper = signal.upper()
        if signal == '9' or signal_upper in ('KILL', 'SIGKILL'):
            use_force = True
    base_cmd = 'Stop-Process'
    ps_params: List[str] = []
    if use_force:
        ps_params.append('-Force')
    if pids:
        if len(pids) == 1:
            ps_params.append(f'-Id {pids[0]}')
        else:
            ps_params.append(f'-Id {", ".join(pids)}')
    if names:
        if len(names) == 1:
            ps_params.append(f'-Name {names[0]}')
        else:
            ps_params.append(f'-Name {", ".join(names)}')
    if not pids and not names:
        return base_cmd
    result_parts = [base_cmd]
    result_parts.extend(ps_params)
    return ' '.join(result_parts)
def convert_kill_command(cmd: str) -> str:
    return _convert_kill(cmd)
def _convert_echo(line: str) -> str:
    if '|' in line:
        idx = line.index('|')
        echo_part = line[:idx].strip()
        rest = line[idx+1:].strip()
        echo_content = echo_part[4:].strip()
        rest_converted = _convert_piped_command(rest)
        return f'Write-Output {echo_content} | {rest_converted}'
    if '>>' in line:
        parts = line.split('>>', 1)
        content = parts[0][4:].strip()
        file_path = parts[1].strip()
        return f'{content} >> {file_path}'
    elif '>' in line:
        parts = line.split('>', 1)
        content = parts[0][4:].strip()
        file_path = parts[1].strip()
        return f'{content} > {file_path}'
    content = line[4:].strip()
    if content.startswith('-e '):
        content = content[3:].strip()
    return f'Write-Output {content}'
def _convert_escape_sequences(text: str, enable_escapes: bool) -> str:
    if not enable_escapes:
        return text
    result = []
    i = 0
    while i < len(text):
        if text[i] == '\\' and i + 1 < len(text):
            next_char = text[i + 1]
            if next_char == '\\':
                result.append('\\')
                i += 2
            elif next_char == 'a':
                result.append('`a')
                i += 2
            elif next_char == 'b':
                result.append('`b')
                i += 2
            elif next_char == 'c':
                return ''.join(result) + '\x00'
            elif next_char == 'e':
                result.append('`e')
                i += 2
            elif next_char == 'f':
                result.append('`f')
                i += 2
            elif next_char == 'n':
                result.append('`n')
                i += 2
            elif next_char == 'r':
                result.append('`r')
                i += 2
            elif next_char == 't':
                result.append('`t')
                i += 2
            elif next_char == 'v':
                result.append('`v')
                i += 2
            elif next_char == '0':
                j = i + 2
                octal_digits = ''
                while j < len(text) and j < i + 5 and text[j] in '01234567':
                    octal_digits += text[j]
                    j += 1
                if octal_digits:
                    try:
                        char_code = int(octal_digits, 8)
                        result.append(chr(char_code))
                    except (ValueError, OverflowError):
                        result.append('\\0' + octal_digits)
                    i = j
                else:
                    result.append('\x00')
                    i += 2
            elif next_char == 'x':
                j = i + 2
                hex_digits = ''
                while j < len(text) and j < i + 4 and text[j] in '0123456789abcdefABCDEF':
                    hex_digits += text[j]
                    j += 1
                if hex_digits:
                    try:
                        char_code = int(hex_digits, 16)
                        result.append(chr(char_code))
                    except (ValueError, OverflowError):
                        result.append('\\x' + hex_digits)
                    i = j
                else:
                    result.append('\\x')
                    i += 2
            else:
                result.append('\\' + next_char)
                i += 2
        else:
            result.append(text[i])
            i += 1
    return ''.join(result)
def convert_echo_command(cmd: str) -> str:
    return _convert_echo(cmd)
def _convert_touch(cmd: str) -> str:
    if not cmd or not cmd.strip():
        return 'New-Item -ItemType File'
    parts = _parse_command_line(cmd)
    if not parts:
        return 'New-Item -ItemType File'
    if parts[0] in ('touch', '/bin/touch', '/usr/bin/touch'):
        parts = parts[1:]
    if not parts:
        return 'New-Item -ItemType File'
    flags: Set[str] = set()
    long_flags: Set[str] = set()
    flag_values: dict = {}
    files: List[str] = []
    i = 0
    while i < len(parts):
        part = parts[i]
        if part == '--':
            files.extend(parts[i + 1:])
            break
        if part.startswith('/') and len(part) >= 2:
            if len(part) == 2 and part[1].isalpha():
                part = '-' + part[1:]
            elif len(part) > 2 and part[1].isalpha():
                part = '--' + part[1:]
        if part.startswith('--'):
            long_opt = part[2:]
            if '=' in long_opt:
                opt_name, opt_value = long_opt.split('=', 1)
                long_flags.add(opt_name)
                flag_values[opt_name] = opt_value
            else:
                long_flags.add(long_opt)
                if long_opt in ('date', 'reference', 'time') and i + 1 < len(parts):
                    i += 1
                    next_part = parts[i]
                    if not next_part.startswith('-') and not (next_part.startswith('/') and len(next_part) >= 2 and next_part[1].isalpha()):
                        flag_values[long_opt] = next_part
                    else:
                        i -= 1
            i += 1
            continue
        if part.startswith('-') and len(part) > 1:
            opt_chars = part[1:]
            for j, char in enumerate(opt_chars):
                flags.add(char)
                if char in ('d', 'r', 't') and j == len(opt_chars) - 1 and i + 1 < len(parts):
                    i += 1
                    next_part = parts[i]
                    if not next_part.startswith('-') and not (next_part.startswith('/') and len(next_part) >= 2 and next_part[1].isalpha()):
                        flag_values[char] = next_part
                    else:
                        i -= 1
            i += 1
            continue
        files.append(part)
        i += 1
    return _build_touch_powershell_command(flags, long_flags, flag_values, files)
def _build_touch_powershell_command(
    flags: Set[str],
    long_flags: Set[str],
    flag_values: dict,
    files: List[str]
) -> str:
    show_help = 'help' in long_flags
    show_version = 'version' in long_flags
    if show_help:
        return (
            'Write-Output "touch - Change file timestamps or create files\n'
            'Usage: touch [options] file...\n'
            'Options:\n'
            '  -a                    Change only the access time\n'
            '  -c, --no-create      Do not create any files\n'
            '  -d, --date=STRING    Parse STRING and use it instead of current time\n'
            '  -f                   (Ignored for BSD compatibility)\n'
            '  -h, --no-dereference Affect symbolic links instead of targets\n'
            '  -m                   Change only the modification time\n'
            '  -r, --reference=FILE Use this file\'s times instead of current time\n'
            '  -t STAMP             Use [[CC]YY]MMDDhhmm[.ss] instead of current time\n'
            '  --time=WORD          Change the specified time:\n'
            '                       access, atime, use (equivalent to -a)\n'
            '                       modify, mtime (equivalent to -m)\n'
            '  --help               Display this help\n'
            '  --version            Display version information"'
        )
    if show_version:
        return 'Write-Output "touch (GNU coreutils) 8.32"'
    access_time_only = 'a' in flags or 'time' in flag_values and flag_values.get('time') in ('access', 'atime', 'use')
    no_create = 'c' in flags or 'no-create' in long_flags
    modify_time_only = 'm' in flags or 'time' in flag_values and flag_values.get('time') in ('modify', 'mtime')
    no_dereference = 'h' in long_flags or 'no-dereference' in long_flags
    reference_file = flag_values.get('r') or flag_values.get('reference')
    timestamp = flag_values.get('t')
    date_string = flag_values.get('d') or flag_values.get('date')
    if not files:
        return 'New-Item -ItemType File'
    quoted_files = []
    for f in files:
        if ' ' in f and not (f.startswith('"') or f.startswith("'")):
            quoted_files.append(f'"{f}"')
        else:
            quoted_files.append(f)
    time_value = 'Get-Date'
    if reference_file:
        time_value = f'(Get-Item "{reference_file}").LastWriteTime'
    elif timestamp:
        time_value = f'[DateTime]::ParseExact("{timestamp}", "yyyyMMddHHmm", $null)'
    elif date_string:
        time_value = f'[DateTime]::Parse("{date_string}")'
    update_access = access_time_only or not modify_time_only
    update_modify = modify_time_only or not access_time_only
    commands: List[str] = []
    for file_path in quoted_files:
        if no_create:
            if update_access and update_modify:
                if no_dereference:
                    commands.append(
                        f'if (Test-Path {file_path}) {{ '
                        f'$f = Get-Item {file_path} -Force; '
                        f'$f.LastAccessTime = {time_value}; '
                        f'$f.LastWriteTime = {time_value} '
                        f'}}'
                    )
                else:
                    commands.append(
                        f'if (Test-Path {file_path}) {{ '
                        f'$f = Get-Item {file_path}; '
                        f'$f.LastAccessTime = {time_value}; '
                        f'$f.LastWriteTime = {time_value} '
                        f'}}'
                    )
            elif access_time_only:
                commands.append(
                    f'if (Test-Path {file_path}) {{ '
                    f'(Get-Item {file_path}).LastAccessTime = {time_value} '
                    f'}}'
                )
            elif modify_time_only:
                commands.append(
                    f'if (Test-Path {file_path}) {{ '
                    f'(Get-Item {file_path}).LastWriteTime = {time_value} '
                    f'}}'
                )
        else:
            if update_access and update_modify:
                commands.append(
                    f'if (Test-Path {file_path}) {{ '
                    f'$f = Get-Item {file_path}; '
                    f'$f.LastAccessTime = {time_value}; '
                    f'$f.LastWriteTime = {time_value} '
                    f'}} else {{ '
                    f'New-Item -ItemType File -Path {file_path} -Force '
                    f'}}'
                )
            elif access_time_only:
                commands.append(
                    f'if (Test-Path {file_path}) {{ '
                    f'(Get-Item {file_path}).LastAccessTime = {time_value} '
                    f'}} else {{ '
                    f'New-Item -ItemType File -Path {file_path} -Force '
                    f'}}'
                )
            elif modify_time_only:
                commands.append(
                    f'if (Test-Path {file_path}) {{ '
                    f'(Get-Item {file_path}).LastWriteTime = {time_value} '
                    f'}} else {{ '
                    f'New-Item -ItemType File -Path {file_path} -Force '
                    f'}}'
                )
    if len(commands) == 1:
        return commands[0]
    else:
        return '; '.join(commands)
def convert_touch_command(cmd: str) -> str:
    return _convert_touch(cmd)
def _convert_which(cmd: str) -> str:
    if not cmd or not cmd.strip():
        return 'Get-Command'
    parts = _parse_command_line(cmd)
    if not parts:
        return 'Get-Command'
    if parts[0] in ('which', '/bin/which', '/usr/bin/which'):
        parts = parts[1:]
    if not parts:
        return 'Get-Command'
    flags: Set[str] = set()
    long_flags: Set[str] = set()
    commands: List[str] = []
    i = 0
    while i < len(parts):
        part = parts[i]
        if part == '--':
            commands.extend(parts[i + 1:])
            break
        if part.startswith('/') and len(part) >= 2 and '/' not in part[1:]:
            if len(part) == 2 and part[1].isalpha():
                part = '-' + part[1:]
            elif len(part) > 2 and part[1].isalpha():
                part = '--' + part[1:]
        if part.startswith('--'):
            long_opt = part[2:]
            if '=' in long_opt:
                opt_name, _ = long_opt.split('=', 1)
                long_flags.add(opt_name)
            else:
                long_flags.add(long_opt)
            i += 1
            continue
        if part.startswith('-') and len(part) > 1:
            opt_chars = part[1:]
            for char in opt_chars:
                flags.add(char)
            i += 1
            continue
        commands.append(part)
        i += 1
    return _build_which_powershell_command(flags, long_flags, commands)
def _build_which_powershell_command(
    flags: Set[str],
    long_flags: Set[str],
    commands: List[str]
) -> str:
    show_help = 'help' in long_flags
    show_version = 'version' in long_flags
    if show_help:
        return (
            'Write-Output "which - Locate a command in the PATH\n'
            'Usage: which [options] program [...]\n'
            'Options:\n'
            '  -a, --all              Print all matches, not just the first\n'
            '  -i, --read-alias       Read aliases from stdin (ignored)\n'
            '      --skip-alias       Skip alias check (ignored)\n'
            '      --skip-dot         Skip directories starting with dot (ignored)\n'
            '      --skip-tilde       Skip directories starting with tilde (ignored)\n'
            '      --show-dot         Show dot for current directory (ignored)\n'
            '      --show-tilde       Show tilde for home directory (ignored)\n'
            '      --tty-only         Stop processing options on tty (ignored)\n'
            '      --help             Display this help\n'
            '      --version          Display version information\n'
            '\n'
            'Note: In PowerShell, Get-Command is used instead of which.\n'
            'The Source property displays the full path to the command."'
        )
    if show_version:
        return 'Write-Output "GNU which v2.21"'
    show_all = 'a' in flags or 'all' in long_flags
    base_cmd = 'Get-Command'
    if not commands:
        return base_cmd
    cmd_results: List[str] = []
    for command in commands:
        if ' ' in command and not (command.startswith('"') or command.startswith("'")):
            quoted_cmd = f'"{command}"'
        else:
            quoted_cmd = command
        if show_all:
            cmd_str = f'{base_cmd} {quoted_cmd} -All | Select-Object -ExpandProperty Source'
        else:
            cmd_str = f'{base_cmd} {quoted_cmd} | Select-Object -ExpandProperty Source'
        cmd_results.append(cmd_str)
    if len(cmd_results) == 1:
        return cmd_results[0]
    else:
        return '; '.join(cmd_results)
def convert_which_command(cmd: str) -> str:
    return _convert_which(cmd)
def _convert_wc(cmd: str) -> str:
    if not cmd or not cmd.strip():
        return 'Write-Output "Usage: wc [options] [file...]"'
    parts = _parse_command_line(cmd)
    if not parts:
        return 'Write-Output "Usage: wc [options] [file...]"'
    if parts[0] in ('wc', '/bin/wc', '/usr/bin/wc'):
        parts = parts[1:]
    if not parts:
        return 'Write-Output "Usage: wc [options] [file...]"'
    flags: Set[str] = set()
    long_flags: Set[str] = set()
    files: List[str] = []
    i = 0
    while i < len(parts):
        part = parts[i]
        if part == '--':
            files.extend(parts[i + 1:])
            break
        if part.startswith('/') and len(part) >= 2:
            if len(part) == 2 and part[1].isalpha():
                part = '-' + part[1:]
            elif len(part) > 2 and part[1].isalpha():
                part = '--' + part[1:]
        if part.startswith('--'):
            long_opt = part[2:]
            if '=' in long_opt:
                opt_name, _ = long_opt.split('=', 1)
                long_flags.add(opt_name)
            else:
                long_flags.add(long_opt)
            i += 1
            continue
        if part.startswith('-') and len(part) > 1:
            opt_chars = part[1:]
            for char in opt_chars:
                flags.add(char)
            i += 1
            continue
        files.append(part)
        i += 1
    return _build_wc_powershell_command(flags, long_flags, files)
def _build_wc_powershell_command(
    flags: Set[str],
    long_flags: Set[str],
    files: List[str]
) -> str:
    show_help = 'help' in long_flags
    show_version = 'version' in long_flags
    if show_help:
        return (
            'Write-Output "wc - Print newline, word, and byte counts for each file\\n'
            'Usage: wc [options] [file...]\\n'
            'Options:\\n'
            '  -c, --bytes            Print byte counts\\n'
            '  -m, --chars            Print character counts\\n'
            '  -l, --lines            Print newline counts\\n'
            '  -L, --max-line-length  Print maximum display width\\n'
            '  -w, --words            Print word counts\\n'
            '      --help             Display this help\\n'
            '      --version          Display version information\\n'
            '\\n'
            'If no file is specified, or when file is -, read standard input.\\n'
            'If no options are given, print lines, words, and bytes."'
        )
    if show_version:
        return 'Write-Output "wc (GNU coreutils) 8.32"'
    show_bytes = 'c' in flags or 'bytes' in long_flags
    show_chars = 'm' in flags or 'chars' in long_flags
    show_lines = 'l' in flags or 'lines' in long_flags
    show_max_line_length = 'L' in flags or 'max-line-length' in long_flags
    show_words = 'w' in flags or 'words' in long_flags
    if not (show_bytes or show_chars or show_lines or show_max_line_length or show_words):
        show_lines = True
        show_words = True
        show_bytes = True
    quoted_files = []
    for f in files:
        if ' ' in f and not (f.startswith('"') or f.startswith("'")):
            quoted_files.append(f'"{f}"')
        else:
            quoted_files.append(f)
    if not quoted_files:
        quoted_files = ['$input']
    commands: List[str] = []
    for file_path in quoted_files:
        count_exprs: List[str] = []
        var_decls: List[str] = []
        need_content = show_lines or show_words or show_chars or show_max_line_length
        need_raw_content = show_chars or show_max_line_length or show_words
        if need_content:
            if need_raw_content:
                var_decls.append(f'$content = Get-Content {file_path} -Raw')
            else:
                var_decls.append(f'$content = Get-Content {file_path}')
        if show_lines:
            if need_raw_content:
                var_decls.append('$lines = ($content -split "\\n").Count')
            else:
                var_decls.append('$lines = $content.Count')
            count_exprs.append('$lines')
        if show_words:
            if need_raw_content:
                var_decls.append('$words = ($content -split "\\s+" | Where-Object { $_ }).Count')
            else:
                var_decls.append('$words = ($content | Measure-Object -Word).Words')
            count_exprs.append('$words')
        if show_chars:
            var_decls.append('$chars = $content.Length')
            count_exprs.append('$chars')
        if show_bytes:
            if file_path == '$input':
                var_decls.append('$bytes = [System.Text.Encoding]::UTF8.GetByteCount($content)')
            else:
                var_decls.append(f'$bytes = (Get-Item {file_path}).Length')
            count_exprs.append('$bytes')
        if show_max_line_length:
            var_decls.append('$maxLen = ($content -split "\\n" | ForEach-Object { $_.Length } | Measure-Object -Maximum).Maximum')
            count_exprs.append('$maxLen')
        if len(count_exprs) == 1 and not var_decls:
            commands.append(count_exprs[0])
        elif len(count_exprs) == 1 and len(var_decls) == 1:
            result = f'{var_decls[0]}; Write-Output {count_exprs[0]}'
            commands.append(result)
        else:
            result_parts = var_decls[:]
            if file_path == '$input':
                output_expr = '"' + ' '.join(['{' + str(i) + '}' for i in range(len(count_exprs))]) + '"' + ' -f ' + ', '.join(count_exprs)
            else:
                display_name = file_path.strip('"\'')
                output_expr = '"' + ' '.join(['{' + str(i) + '}' for i in range(len(count_exprs))]) + ' ' + display_name + '"' + ' -f ' + ', '.join(count_exprs)
            result_parts.append(f'Write-Output {output_expr}')
            commands.append('; '.join(result_parts))
    if len(commands) == 1:
        return commands[0]
    else:
        return '; '.join(commands)
def convert_wc_command(cmd: str) -> str:
    return _convert_wc(cmd)
def _convert_find(cmd: str) -> str:
    parts = cmd.split()
    if len(parts) < 2:
        return 'Get-ChildItem -Recurse'
    path = '.'
    name_pattern = None
    file_type = None
    max_depth = None
    min_depth = None
    mtime = None
    size = None
    exec_cmd = None
    delete = False
    empty = False
    i = 1
    while i < len(parts):
        part = parts[i]
        if part.startswith('/'):
            part = '-' + part[1:]
        if part == '-name' or part == '-iname':
            if i + 1 < len(parts):
                name_pattern = parts[i + 1].strip('"\'')
                i += 1
        elif part == '-type':
            if i + 1 < len(parts):
                file_type = parts[i + 1]
                i += 1
        elif part == '-maxdepth':
            if i + 1 < len(parts):
                max_depth = int(parts[i + 1])
                i += 1
        elif part == '-mindepth':
            if i + 1 < len(parts):
                min_depth = int(parts[i + 1])
                i += 1
        elif part == '-mtime':
            if i + 1 < len(parts):
                mtime = parts[i + 1]
                i += 1
        elif part == '-size':
            if i + 1 < len(parts):
                size = parts[i + 1]
                i += 1
        elif part == '-exec':
            exec_parts = []
            i += 1
            while i < len(parts) and parts[i] != ';' and parts[i] != '+':
                if parts[i] == '{}':
                    exec_parts.append('$_')
                elif parts[i] == '{}':
                    exec_parts.append('$_')
                else:
                    exec_parts.append(parts[i])
                i += 1
            exec_cmd = ' '.join(exec_parts)
        elif part == '-delete':
            delete = True
        elif part == '-empty':
            empty = True
        elif part == '-o' or part == '-or':
            pass
        elif not part.startswith('-') and i == 1:
            path = part
        i += 1
    ps_cmd_parts = ['Get-ChildItem']
    if path != '.':
        ps_cmd_parts.append(path)
    if max_depth is not None:
        ps_cmd_parts.append(f'-Depth {max_depth}')
    else:
        ps_cmd_parts.append('-Recurse')
    filters = []
    if name_pattern:
        wildcard = name_pattern.replace('*', '*').replace('?', '?')
        filters.append(f"$_.Name -like '{wildcard}'")
    if file_type == 'f':
        filters.append('$_.PSIsContainer -eq $false')
    elif file_type == 'd':
        filters.append('$_.PSIsContainer -eq $true')
    if min_depth is not None:
        filters.append(f"$_.FullName.Split([System.IO.Path]::DirectorySeparatorChar).Length - {path.count('/') + 1} -ge {min_depth}")
    if mtime:
        if mtime.startswith('+'):
            days = int(mtime[1:])
            date = f"(Get-Date).AddDays(-{days})"
            filters.append(f"$_.LastWriteTime -lt {date}")
        elif mtime.startswith('-'):
            days = int(mtime[1:])
            date = f"(Get-Date).AddDays(-{days})"
            filters.append(f"$_.LastWriteTime -gt {date}")
        else:
            days = int(mtime)
            date_before = f"(Get-Date).AddDays(-{days - 1})"
            date_after = f"(Get-Date).AddDays(-{days + 1})"
            filters.append(f"$_.LastWriteTime -lt {date_before} -and $_.LastWriteTime -gt {date_after}")
    if size:
        if size.startswith('+'):
            size_bytes = self._parse_size(size[1:])
            filters.append(f"$_.Length -gt {size_bytes}")
        elif size.startswith('-'):
            size_bytes = self._parse_size(size[1:])
            filters.append(f"$_.Length -lt {size_bytes}")
        else:
            size_bytes = self._parse_size(size)
            filters.append(f"$_.Length -eq {size_bytes}")
    if empty:
        filters.append('($_.PSIsContainer -and (Get-ChildItem $_.FullName).Count -eq 0) -or (-not $_.PSIsContainer -and $_.Length -eq 0)')
    if filters:
        filter_str = ' -and '.join(filters)
        ps_cmd_parts.append(f"| Where-Object {{ {filter_str} }}")
    if delete:
        ps_cmd_parts.append('| Remove-Item')
    elif exec_cmd:
        ps_cmd_parts.append(f"| ForEach-Object {{ {exec_cmd} }}")
    else:
        ps_cmd_parts.append('| Select-Object -ExpandProperty FullName')
    return ' '.join(ps_cmd_parts)
def _build_find_powershell_command(
    paths: List[str],
    flags: Set[str],
    long_flags: Set[str],
    flag_values: dict
) -> str:
    show_help = 'help' in long_flags or 'h' in flags
    show_version = 'version' in long_flags
    if show_help:
        return (
            'Write-Output "find - Search for files in a directory hierarchy\\n'
            'Usage: find [path...] [expression]\\n'
            'Options:\\n'
            '  -name PATTERN         Base of file name matches pattern\\n'
            '  -iname PATTERN        Like -name but case insensitive\\n'
            '  -type TYPE            File type (f=file, d=directory, l=link)\\n'
            '  -mtime N              Modified N days ago\\n'
            '  -atime N              Accessed N days ago\\n'
            '  -ctime N              Changed N days ago\\n'
            '  -size N               File size (c=bytes, k=KB, M=MB, G=GB)\\n'
            '  -empty                Empty files or directories\\n'
            '  -maxdepth N           Descend at most N levels\\n'
            '  -mindepth N           Descend at least N levels\\n'
            '  -depth                Process contents before directory\\n'
            '  -exec CMD             Execute command on found files\\n'
            '  -print                Print file names (default)\\n'
            '  -ls                   List files like ls -dils\\n'
            '  -delete               Delete found files\\n'
            '  -prune                Don\'t descend into current directory\\n'
            '  -newer FILE           Modified more recently than FILE\\n'
            '  -user USER            File owned by USER\\n'
            '  -group GROUP          File belongs to GROUP\\n'
            '  -perm MODE            File permissions match MODE\\n'
            '  -not, !               Negate expression\\n'
            '  -o, -or               OR operator\\n'
            '  -a, -and              AND operator (default)\\n'
            '  --help                Display this help\\n'
            '  --version             Display version information"'
        )
    if show_version:
        return 'Write-Output "find (GNU findutils) 4.8.0"'
    base_cmd = 'Get-ChildItem'
    ps_params: List[str] = []
    pipeline_parts: List[str] = []
    if paths:
        quoted_paths = []
        for p in paths:
            if ' ' in p and not (p.startswith('"') or p.startswith("'")):
                quoted_paths.append(f'"{p}"')
            else:
                quoted_paths.append(p)
        if len(quoted_paths) == 1:
            ps_params.append(f'-Path {quoted_paths[0]}')
    maxdepth = flag_values.get('maxdepth')
    mindepth = flag_values.get('mindepth')
    if maxdepth:
        ps_params.append(f'-Depth {maxdepth}')
    elif 'depth' in long_flags or 'd' in flags:
        pass
    if not maxdepth or int(maxdepth) > 0:
        if '-Depth' not in ' '.join(ps_params):
            ps_params.append('-Recurse')
    file_type = flag_values.get('type')
    if file_type:
        if file_type == 'f':
            ps_params.append('-File')
        elif file_type == 'd':
            ps_params.append('-Directory')
        elif file_type == 'l':
            pipeline_parts.append('Where-Object { $_.Attributes -match "ReparsePoint" }')
    name_pattern = flag_values.get('name')
    iname_pattern = flag_values.get('iname')
    if name_pattern:
        pattern = name_pattern.replace('"', '`"')
        ps_params.append(f'-Filter "{pattern}"')
    elif iname_pattern:
        pattern = iname_pattern.replace('"', '`"')
        ps_params.append(f'-Filter "{pattern}"')
    if 'empty' in long_flags or 'empty' in flags:
        if file_type == 'd':
            pipeline_parts.append('Where-Object { $_.GetFiles().Count -eq 0 -and $_.GetDirectories().Count -eq 0 }')
        elif file_type == 'f':
            pipeline_parts.append('Where-Object { $_.Length -eq 0 }')
        else:
            pipeline_parts.append('Where-Object { ($_.PSIsContainer -and $_.GetFiles().Count -eq 0 -and $_.GetDirectories().Count -eq 0) -or (-not $_.PSIsContainer -and $_.Length -eq 0) }')
    size_spec = flag_values.get('size')
    if size_spec:
        size_match = re.match(r'^([+-]?)(\d+)([ckmMgG]?)$', size_spec)
        if size_match:
            sign, num, unit = size_match.groups()
            num = int(num)
            multiplier = 1
            if unit.lower() == 'c':
                multiplier = 1
            elif unit.lower() == 'k':
                multiplier = 1024
            elif unit.lower() == 'm':
                multiplier = 1024 * 1024
            elif unit.lower() == 'g':
                multiplier = 1024 * 1024 * 1024
            size_bytes = num * multiplier
            if sign == '+':
                pipeline_parts.append(f'Where-Object {{ $_.Length -gt {size_bytes} }}')
            elif sign == '-':
                pipeline_parts.append(f'Where-Object {{ $_.Length -lt {size_bytes} }}')
            else:
                pipeline_parts.append(f'Where-Object {{ $_.Length -eq {size_bytes} }}')
    mtime = flag_values.get('mtime')
    if mtime:
        mtime_match = re.match(r'^([+-]?)(\d+)$', mtime)
        if mtime_match:
            sign, days = mtime_match.groups()
            days = int(days)
            if sign == '+':
                pipeline_parts.append(f'Where-Object {{ $_.LastWriteTime -lt (Get-Date).AddDays(-{days}) }}')
            elif sign == '-':
                pipeline_parts.append(f'Where-Object {{ $_.LastWriteTime -gt (Get-Date).AddDays(-{days}) }}')
            else:
                pipeline_parts.append(f'Where-Object {{ ($_.LastWriteTime -ge (Get-Date).AddDays(-{days}).Date) -and ($_.LastWriteTime -lt (Get-Date).AddDays(-{days + 1}).Date) }}')
    atime = flag_values.get('atime')
    if atime:
        atime_match = re.match(r'^([+-]?)(\d+)$', atime)
        if atime_match:
            sign, days = atime_match.groups()
            days = int(days)
            if sign == '+':
                pipeline_parts.append(f'Where-Object {{ $_.LastAccessTime -lt (Get-Date).AddDays(-{days}) }}')
            elif sign == '-':
                pipeline_parts.append(f'Where-Object {{ $_.LastAccessTime -gt (Get-Date).AddDays(-{days}) }}')
            else:
                pipeline_parts.append(f'Where-Object {{ ($_.LastAccessTime -ge (Get-Date).AddDays(-{days}).Date) -and ($_.LastAccessTime -lt (Get-Date).AddDays(-{days + 1}).Date) }}')
    ctime = flag_values.get('ctime')
    if ctime:
        ctime_match = re.match(r'^([+-]?)(\d+)$', ctime)
        if ctime_match:
            sign, days = ctime_match.groups()
            days = int(days)
            if sign == '+':
                pipeline_parts.append(f'Where-Object {{ $_.CreationTime -lt (Get-Date).AddDays(-{days}) }}')
            elif sign == '-':
                pipeline_parts.append(f'Where-Object {{ $_.CreationTime -gt (Get-Date).AddDays(-{days}) }}')
            else:
                pipeline_parts.append(f'Where-Object {{ ($_.CreationTime -ge (Get-Date).AddDays(-{days}).Date) -and ($_.CreationTime -lt (Get-Date).AddDays(-{days + 1}).Date) }}')
    newer_file = flag_values.get('newer')
    if newer_file:
        if ' ' in newer_file and not (newer_file.startswith('"') or newer_file.startswith("'")):
            newer_file = f'"{newer_file}"'
        pipeline_parts.append(f'Where-Object {{ $_.LastWriteTime -gt (Get-Item {newer_file}).LastWriteTime }}')
    user = flag_values.get('user')
    if user:
        pipeline_parts.append(f'Where-Object {{ (Get-Acl $_.FullName).Owner -like "*{user}*" }}')
    perm = flag_values.get('perm')
    if perm:
        pass
    if 'prune' in long_flags:
        pass
    result_parts = [base_cmd]
    result_parts.extend(ps_params)
    result = ' '.join(result_parts)
    if pipeline_parts:
        result += ' | ' + ' | '.join(pipeline_parts)
    if 'delete' in long_flags or 'delete' in flags:
        if pipeline_parts:
            result += ' | Remove-Item -Force'
        else:
            result += ' | Remove-Item -Force'
    elif 'ls' in long_flags or 'ls' in flags:
        if pipeline_parts:
            result += ' | Select-Object Mode, LastWriteTime, Length, FullName | Format-Table -AutoSize'
        else:
            result += ' | Select-Object Mode, LastWriteTime, Length, FullName | Format-Table -AutoSize'
    elif 'print' in long_flags or 'print0' in long_flags or 'print' in flags or 'print0' in flags:
        if pipeline_parts:
            if 'print0' in long_flags:
                result += ' | ForEach-Object { Write-Host -NoNewline ($_.FullName + [char]0) }'
            else:
                result += ' | ForEach-Object { $_.FullName }'
        else:
            if 'print0' in long_flags:
                result += ' | ForEach-Object { Write-Host -NoNewline ($_.FullName + [char]0) }'
            else:
                result += ' | ForEach-Object { $_.FullName }'
    elif 'exec' in long_flags or 'exec' in flags or flag_values.get('exec'):
        exec_cmd = flag_values.get('exec', '')
        if exec_cmd:
            if '{}' in exec_cmd:
                result += f' | ForEach-Object {{ {exec_cmd.replace("{}", "$_.FullName")} }}'
            else:
                result += f' | ForEach-Object {{ {exec_cmd} $_.FullName }}'
    else:
        if pipeline_parts:
            result += ' | ForEach-Object { $_.FullName }'
        else:
            result += ' | ForEach-Object { $_.FullName }'
    return result
def convert_find_command(cmd: str) -> str:
    return _convert_find(cmd)
def _convert_alias(cmd: str) -> str:
    if not cmd or not cmd.strip():
        return 'Get-Alias'
    parts = _parse_command_line(cmd)
    if not parts:
        return 'Get-Alias'
    if parts[0] in ('alias', '/bin/alias', '/usr/bin/alias'):
        parts = parts[1:]
    if not parts:
        return 'Get-Alias'
    flags: Set[str] = set()
    long_flags: Set[str] = set()
    positional_args: List[str] = []
    i = 0
    while i < len(parts):
        part = parts[i]
        if part == '--':
            positional_args.extend(parts[i + 1:])
            break
        if part.startswith('/') and len(part) >= 2:
            if len(part) == 2 and part[1].isalpha():
                part = '-' + part[1:]
            elif len(part) > 2 and part[1].isalpha():
                part = '--' + part[1:]
        if part.startswith('--'):
            long_opt = part[2:]
            if '=' in long_opt:
                opt_name, _ = long_opt.split('=', 1)
                long_flags.add(opt_name)
            else:
                long_flags.add(long_opt)
            i += 1
            continue
        if part.startswith('-') and len(part) > 1:
            opt_chars = part[1:]
            for char in opt_chars:
                flags.add(char)
            i += 1
            continue
        positional_args.append(part)
        i += 1
    print_reusable = 'p' in flags
    if not positional_args:
        if print_reusable:
            return 'Get-Alias | Format-Table -AutoSize'
        return 'Get-Alias'
    results: List[str] = []
    for arg in positional_args:
        if '=' in arg:
            name, value = arg.split('=', 1)
            if (value.startswith('"') and value.endswith('"')) or \
               (value.startswith("'") and value.endswith("'")):
                value = value[1:-1]
            value = value.replace("'", "''")
            results.append(f"Set-Alias -Name {name} -Value '{value}'")
        else:
            if print_reusable:
                results.append(f"Get-Alias {arg} | Format-Table -AutoSize")
            else:
                results.append(f"Get-Alias {arg}")
    if len(results) == 1:
        return results[0]
    return '; '.join(results)
def _convert_base64(cmd: str) -> str:
    if not cmd or not cmd.strip():
        return '$input | ForEach-Object { [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($_)) }'
    parts = _parse_command_line(cmd)
    if not parts:
        return '$input | ForEach-Object { [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($_)) }'
    if parts[0] in ('base64', '/bin/base64', '/usr/bin/base64'):
        parts = parts[1:]
    if not parts:
        return '$input | ForEach-Object { [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($_)) }'
    options: Dict[str, Any] = {
        'decode': False,
        'ignore_garbage': False,
        'wrap': 76,
        'show_help': False,
        'show_version': False,
    }
    files: List[str] = []
    i = 0
    while i < len(parts):
        part = parts[i]
        if part == '--':
            files.extend(parts[i + 1:])
            break
        if part.startswith('/') and len(part) >= 2:
            if len(part) == 2 and part[1].isalpha():
                part = '-' + part[1:]
            elif len(part) > 2 and part[1].isalpha():
                part = '--' + part[1:]
        if part.startswith('--'):
            long_opt = part[2:]
            if '=' in long_opt:
                opt_name, opt_value = long_opt.split('=', 1)
                if opt_name in ('wrap', 'w'):
                    try:
                        options['wrap'] = int(opt_value)
                    except ValueError:
                        options['wrap'] = 76
                i += 1
                continue
            if long_opt == 'help':
                options['show_help'] = True
                i += 1
                continue
            elif long_opt == 'version':
                options['show_version'] = True
                i += 1
                continue
            elif long_opt == 'decode':
                options['decode'] = True
                i += 1
                continue
            elif long_opt == 'ignore-garbage':
                options['ignore_garbage'] = True
                i += 1
                continue
            elif long_opt == 'wrap':
                if i + 1 < len(parts):
                    i += 1
                    try:
                        options['wrap'] = int(parts[i])
                    except ValueError:
                        options['wrap'] = 76
                i += 1
                continue
            i += 1
            continue
        if part.startswith('-') and len(part) > 1:
            opt_chars = part[1:]
            j = 0
            while j < len(opt_chars):
                char = opt_chars[j]
                if char == 'd':
                    options['decode'] = True
                    j += 1
                elif char == 'i':
                    options['ignore_garbage'] = True
                    j += 1
                elif char == 'w':
                    if j + 1 < len(opt_chars):
                        wrap_str = opt_chars[j + 1:]
                        try:
                            options['wrap'] = int(wrap_str)
                        except ValueError:
                            options['wrap'] = 76
                        break
                    elif i + 1 < len(parts):
                        i += 1
                        try:
                            options['wrap'] = int(parts[i])
                        except ValueError:
                            options['wrap'] = 76
                    j += 1
                else:
                    j += 1
            i += 1
            continue
        files.append(part)
        i += 1
    return _build_base64_powershell_command(options, files)
def _build_base64_powershell_command(options: Dict[str, Any], files: List[str]) -> str:
    if options.get('show_help'):
        return (
            'Write-Output "Usage: base64 [OPTION]... [FILE]...\n'
            'Base64 encode or decode FILE, or standard input, to standard output.\n\n'
            '  -d, --decode          decode data\n'
            '  -i, --ignore-garbage  when decoding, ignore non-alphabet characters\n'
            '  -w, --wrap=COLS       wrap encoded lines after COLS character (default 76)\n'
            '      --help            display this help and exit\n'
            '      --version         output version information and exit"'
        )
    if options.get('show_version'):
        return 'Write-Output "base64 (GNU coreutils) 9.4"'
    decode = options.get('decode', False)
    ignore_garbage = options.get('ignore_garbage', False)
    wrap = options.get('wrap', 76)
    if not files:
        if decode:
            if ignore_garbage:
                return '$input | ForEach-Object { $clean = $_ -replace "[^A-Za-z0-9+/=]", ""; [System.Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($clean)) }'
            else:
                return '$input | ForEach-Object { [System.Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($_)) }'
        else:
            return '$input | ForEach-Object { [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($_)) }'
    commands = []
    for file_path in files:
        if file_path == '-':
            if decode:
                if ignore_garbage:
                    commands.append('$input | ForEach-Object { $clean = $_ -replace "[^A-Za-z0-9+/=]", ""; [System.Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($clean)) }')
                else:
                    commands.append('$input | ForEach-Object { [System.Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($_)) }')
            else:
                commands.append('$input | ForEach-Object { [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($_)) }')
            continue
        quoted_file = file_path
        if ' ' in file_path and not (file_path.startswith('"') or file_path.startswith("'")):
            quoted_file = f'"{file_path}"'
        cmd = _build_single_base64_command(quoted_file, decode, ignore_garbage, wrap)
        commands.append(cmd)
    if len(commands) == 1:
        return commands[0]
    return '; '.join(commands)
def _build_single_base64_command(file_path: str, decode: bool, ignore_garbage: bool, wrap: int) -> str:
    if not (file_path.startswith('"') or file_path.startswith("'") or file_path[-1] == '"' or file_path[-1] == "'"):
        file_path = f'"{file_path}"'
    if decode:
        if ignore_garbage:
            return (
                f'$content = [System.IO.File]::ReadAllText({file_path}) -replace "[^A-Za-z0-9+/=]", ""; '
                f'[System.Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($content))'
            )
        else:
            return (
                f'[System.Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('
                f'([System.IO.File]::ReadAllText({file_path}) -replace "\\s", "")))'
            )
    else:
        if wrap == 0:
            return f'[Convert]::ToBase64String([System.IO.File]::ReadAllBytes({file_path}))'
        elif wrap != 76:
            return (
                f'$bytes = [Convert]::ToBase64String([System.IO.File]::ReadAllBytes({file_path})); '
                f'$wrapped = $bytes -replace "(.{{{wrap}}})", "$1`n"; '
                f'$wrapped'
            )
        else:
            return f'[Convert]::ToBase64String([System.IO.File]::ReadAllBytes({file_path}))'

if __name__ == "__main__":
    test_cases = [
        "base64 file.txt",
        "base64 -d encoded.txt",
        "base64 -w 0 file.txt",
        "base64 --wrap=80 file.txt",
        "base64 -d -i encoded.txt",
        "base64",
        "base64 -d",
        "base64 --help",
        "base64 --version",
        "base64 /d encoded.txt",
        "base64 /i /d encoded.txt",
        "base64 -w80 file.txt",
        "base64 -w 64 file.txt",
        "base64 --decode --ignore-garbage file.b64",
        "base64 -",
        "base64 -d -",
    ]
    for test in test_cases:
        result = _convert_base64(test)
        print(f"Input:  {test}")
        print(f"Output: {result}")
        print()
def _convert_basename(cmd: str) -> str:
    if not cmd or not cmd.strip():
        return 'Write-Output "basename: missing operand"'
    parts = _parse_command_line(cmd)
    if not parts:
        return 'Write-Output "basename: missing operand"'
    if parts[0] in ('basename', '/bin/basename', '/usr/bin/basename'):
        parts = parts[1:]
    if not parts:
        return 'Write-Output "basename: missing operand"'
    multiple = False
    suffix: Optional[str] = None
    zero_terminated = False
    show_help = False
    show_version = False
    names: List[str] = []
    i = 0
    while i < len(parts):
        part = parts[i]
        if part == '--':
            names.extend(parts[i + 1:])
            break
        if part.startswith('/') and len(part) >= 2:
            opt_part = part[1:]
            if opt_part in ('a', 's', 'z'):
                part = '-' + opt_part
            elif opt_part in ('multiple', 'suffix', 'zero-terminated', 'help', 'version'):
                part = '--' + opt_part
            elif '=' in opt_part:
                opt_name = opt_part.split('=', 1)[0]
                if opt_name == 'suffix':
                    part = '--' + opt_part
        if part.startswith('--'):
            long_opt = part[2:]
            if '=' in long_opt:
                opt_name, opt_value = long_opt.split('=', 1)
                if opt_name == 'suffix':
                    suffix = opt_value
                i += 1
                continue
            if long_opt == 'help':
                show_help = True
                i += 1
                continue
            elif long_opt == 'version':
                show_version = True
                i += 1
                continue
            elif long_opt == 'multiple':
                multiple = True
                i += 1
                continue
            elif long_opt == 'zero-terminated':
                zero_terminated = True
                i += 1
                continue
            elif long_opt == 'suffix':
                if i + 1 < len(parts):
                    i += 1
                    suffix = parts[i]
                i += 1
                continue
            i += 1
            continue
        if part.startswith('-') and len(part) > 1:
            opt_chars = part[1:]
            j = 0
            while j < len(opt_chars):
                char = opt_chars[j]
                if char == 'a':
                    multiple = True
                    j += 1
                elif char == 's':
                    if j + 1 < len(opt_chars):
                        suffix = opt_chars[j + 1:]
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                        suffix = parts[i]
                    j += 1
                elif char == 'z':
                    zero_terminated = True
                    j += 1
                else:
                    j += 1
            i += 1
            continue
        names.append(part)
        i += 1
    if show_help:
        return (
            'Write-Output "Usage: basename [OPTION]... NAME...\n'
            'Strip directory and suffix from filenames.\n'
            '\n'
            '  -a, --multiple       support multiple arguments and treat each as a NAME\n'
            '  -s, --suffix=SUFFIX  remove a trailing SUFFIX; implies -a\n'
            '  -z, --zero-terminated  separate output with NUL rather than newline\n'
            '      --help           display this help and exit\n'
            '      --version        output version information and exit\n'
            '\n'
            'Examples:\n'
            '  basename /usr/bin/sort          -> "sort"\n'
            '  basename /usr/bin/sort .txt     -> "sort" (if input was sort.txt)\n'
            '  basename -s .txt /path/to/file.txt  -> "file"\n'
            '  basename -a any/str1 any/str2   -> "str1" followed by "str2""'
        )
    if show_version:
        return 'Write-Output "basename (GNU coreutils) 8.32"'
    if len(names) >= 2 and suffix is None and not multiple:
        potential_suffix = names[-1]
        if potential_suffix.startswith('.'):
            suffix = potential_suffix
            names = names[:-1]
    if not names:
        return 'Write-Output "basename: missing operand"'
    if suffix is not None:
        multiple = True
    commands = []
    for name in names:
        if ' ' in name and not (name.startswith('"') or name.startswith("'")):
            quoted_name = f'"{name}"'
        else:
            quoted_name = name
        base_cmd = f'Split-Path -Path {quoted_name} -Leaf'
        if suffix is not None:
            escaped_suffix = suffix.replace('\\', '\\\\').replace('.', '\\.').replace('*', '\\*').replace('+', '\\+').replace('?', '\\?').replace('[', '\\[').replace(']', '\\]').replace('(', '\\(').replace(')', '\\)').replace('{', '\\{').replace('}', '\\}').replace('^', '\\^').replace('$', '\\$').replace('|', '\\|')
            base_cmd = f'({base_cmd}) -replace "{escaped_suffix}$", ""'
        commands.append(base_cmd)
    if len(commands) == 1:
        result = commands[0]
    else:
        result = '; '.join(commands)
    if zero_terminated:
        result = f'{result} | ForEach-Object {{ Write-Host -NoNewline ($_ + [char]0) }}'
    return result
def _parse_mode(mode: str) -> Optional[List[Tuple[str, str, str]]]:
    if re.match(r'^[0-7]{1,4}$', mode):
        return _parse_numeric_mode(mode)
    return _parse_symbolic_mode(mode)
def _parse_numeric_mode(mode: str) -> List[Tuple[str, str, str]]:
    mode = mode.zfill(4)
    operations = []
    user_val = int(mode[1])
    if user_val & 4:
        operations.append(('u', '+', 'r'))
    if user_val & 2:
        operations.append(('u', '+', 'w'))
    if user_val & 1:
        operations.append(('u', '+', 'x'))
    group_val = int(mode[2])
    if group_val & 4:
        operations.append(('g', '+', 'r'))
    if group_val & 2:
        operations.append(('g', '+', 'w'))
    if group_val & 1:
        operations.append(('g', '+', 'x'))
    other_val = int(mode[3])
    if other_val & 4:
        operations.append(('o', '+', 'r'))
    if other_val & 2:
        operations.append(('o', '+', 'w'))
    if other_val & 1:
        operations.append(('o', '+', 'x'))
    return operations
def _parse_symbolic_mode(mode: str) -> Optional[List[Tuple[str, str, str]]]:
    operations = []
    clauses = mode.split(',')
    for clause in clauses:
        clause = clause.strip()
        if not clause:
            continue
        match = re.match(r'^([ugoa]*)([+=-])([rwxXst]*)$', clause)
        if not match:
            return None
        who_str, op, perm_str = match.groups()
        if not who_str:
            who_str = 'a'
        if 'a' in who_str:
            who_str = 'ugo'
        for w in who_str:
            for p in perm_str:
                operations.append((w, op, p))
    return operations if operations else None
def _mode_to_acl_rights(operations: List[Tuple[str, str, str]]) -> str:
    has_read = False
    has_write = False
    has_execute = False
    for who, op, perm in operations:
        if perm == 'r':
            has_read = True
        elif perm == 'w':
            has_write = True
        elif perm == 'x':
            has_execute = True
    rights = []
    if has_read:
        rights.append('Read')
    if has_write:
        rights.append('Write')
    if has_execute:
        rights.append('ExecuteFile')
    if not rights:
        return 'Read'
    return ', '.join(rights)
def _convert_chmod(cmd: str) -> str:
    if not cmd or not cmd.strip():
        return 'Write-Output "chmod: missing operand"'
    parts = _parse_command_line(cmd)
    if not parts:
        return 'Write-Output "chmod: missing operand"'
    if parts[0] in ('chmod', '/bin/chmod', '/usr/bin/chmod'):
        parts = parts[1:]
    if not parts:
        return 'Write-Output "chmod: missing operand"'
    changes_only = False
    silent = False
    recursive = False
    verbose = False
    reference_file: Optional[str] = None
    show_help = False
    show_version = False
    i = 0
    while i < len(parts):
        part = parts[i]
        if part == '--':
            i += 1
            break
        if part.startswith('/') and len(part) >= 2:
            if len(part) == 2 and part[1].isalpha():
                part = '-' + part[1:]
            elif len(part) > 2 and part[1].isalpha():
                part = '--' + part[1:]
        if part.startswith('--'):
            long_opt = part[2:]
            if '=' in long_opt:
                opt_name, opt_value = long_opt.split('=', 1)
                if opt_name == 'reference':
                    reference_file = opt_value
                i += 1
                continue
            if long_opt == 'help':
                show_help = True
                i += 1
                continue
            elif long_opt == 'version':
                show_version = True
                i += 1
                continue
            elif long_opt == 'changes':
                changes_only = True
                i += 1
                continue
            elif long_opt in ('silent', 'quiet'):
                silent = True
                i += 1
                continue
            elif long_opt == 'recursive':
                recursive = True
                i += 1
                continue
            elif long_opt == 'verbose':
                verbose = True
                i += 1
                continue
            elif long_opt == 'reference':
                if i + 1 < len(parts):
                    i += 1
                    reference_file = parts[i]
                i += 1
                continue
            i += 1
            continue
        if part.startswith('-') and len(part) > 1:
            opt_chars = part[1:]
            j = 0
            while j < len(opt_chars):
                char = opt_chars[j]
                if char == 'c':
                    changes_only = True
                    j += 1
                elif char == 'f':
                    silent = True
                    j += 1
                elif char == 'R':
                    recursive = True
                    j += 1
                elif char == 'v':
                    verbose = True
                    j += 1
                elif char == '-':
                    j += 1
                    i += 1
                    break
                else:
                    j += 1
            i += 1
            continue
        break
    if show_help:
        return (
            'Write-Output "Usage: chmod [OPTION]... MODE[,MODE]... FILE...\n'
            '  or:  chmod [OPTION]... OCTAL-MODE FILE...\n'
            '  or:  chmod [OPTION]... --reference=RFILE FILE...\n'
            'Change the mode of each FILE to MODE.\n'
            '\n'
            '  -c, --changes          like verbose but report only when a change is made\n'
            '  -f, --silent, --quiet  suppress most error messages\n'
            '  -R, --recursive        change files and directories recursively\n'
            '  -v, --verbose          output a diagnostic for every file processed\n'
            '      --reference=RFILE  use RFILE\'s mode instead of MODE values\n'
            '      --help     display this help and exit\n'
            '      --version  output version information and exit"'
        )
    if show_version:
        return 'Write-Output "chmod (GNU coreutils) 8.32"'
    remaining = parts[i:]
    if not remaining:
        return 'Write-Output "chmod: missing operand"'
    mode_str: Optional[str] = None
    files: List[str] = []
    if reference_file:
        files = remaining
    else:
        if remaining:
            mode_str = remaining[0]
            files = remaining[1:]
    if not files:
        return 'Write-Output "chmod: missing file operand"'
    operations = None
    if mode_str:
        operations = _parse_mode(mode_str)
    return _build_chmod_powershell_command(
        mode_str, operations, reference_file, files,
        changes_only, silent, recursive, verbose
    )
def _build_chmod_powershell_command(
    mode_str: Optional[str],
    operations: Optional[List[Tuple[str, str, str]]],
    reference_file: Optional[str],
    files: List[str],
    changes_only: bool,
    silent: bool,
    recursive: bool,
    verbose: bool
) -> str:
    quoted_files = []
    for f in files:
        if ' ' in f and not (f.startswith('"') or f.startswith("'")):
            quoted_files.append(f'"{f}"')
        else:
            quoted_files.append(f)
    commands = []
    if reference_file:
        ref = reference_file
        if ' ' in ref and not (ref.startswith('"') or ref.startswith("'")):
            ref = f'"{ref}"'
        for file_path in quoted_files:
            cmd = (
                f'$refAcl = Get-Acl {ref}; '
                f'$path = {file_path}; '
                f'$acl = Get-Acl $path; '
                f'$acl.SetAccessRuleProtection($refAcl.AreAccessRulesProtected, $false); '
                f'foreach ($rule in $refAcl.Access) {{ '
                f'$acl.SetAccessRule($rule); '
                f'}}; '
                f'Set-Acl $path $acl'
            )
            if verbose:
                cmd += f'; Write-Output "mode of `{file_path}` retained as `$($refAcl.ToString())`"'
            elif changes_only:
                cmd += '; if ($?) { Write-Output "changed permissions" }'
            commands.append(cmd)
        if len(commands) == 1:
            return commands[0]
        return '; '.join(commands)
    icacls_perm = _mode_to_icacls_perm(mode_str, operations)
    for file_path in quoted_files:
        if recursive:
            cmd = (
                f'Get-ChildItem -Path {file_path} -Recurse | '
                f'ForEach-Object {{ icacls $_.FullName {icacls_perm} }}'
            )
            if verbose:
                cmd += f'; Write-Output "changed permissions of `{file_path}` recursively"'
            elif changes_only:
                cmd += '; if ($?) { Write-Output "changed permissions" }'
        else:
            cmd = f'icacls {file_path} {icacls_perm}'
            if verbose:
                cmd += f'; Write-Output "mode of `{file_path}` changed to {mode_str}"'
            elif changes_only:
                cmd += '; if ($?) { Write-Output "changed permissions" }'
        commands.append(cmd)
    if len(commands) == 1:
        return commands[0]
    return '; '.join(commands)
def _mode_to_icacls_perm(mode_str: Optional[str], operations: Optional[List[Tuple[str, str, str]]]) -> str:
    if not mode_str:
        return '/grant *S-1-1-0:(OI)(CI)F'
    if re.match(r'^[0-7]{1,4}$', mode_str):
        mode_num = int(mode_str, 8)
        if mode_num == 0o777:
            return '/grant *S-1-1-0:(OI)(CI)F'
        elif mode_num == 0o755:
            return '/grant *S-1-1-0:(OI)(CI)RX'
        elif mode_num == 0o644:
            return '/grant *S-1-1-0:(OI)(CI)R'
        elif mode_num == 0o700:
            return '/grant %username%:(OI)(CI)F'
        elif mode_num == 0o600:
            return '/grant %username%:(OI)(CI)M'
        elif mode_num == 0o444:
            return '/grant *S-1-1-0:(OI)(CI)R'
        elif mode_num == 0o555:
            return '/grant *S-1-1-0:(OI)(CI)RX'
        elif mode_num == 0o111:
            return '/grant *S-1-1-0:(OI)(CI)X'
        elif mode_num == 0o222:
            return '/grant *S-1-1-0:(OI)(CI)W'
        elif mode_num == 0o333:
            return '/grant *S-1-1-0:(OI)(CI)W'
        elif mode_num == 0o666:
            return '/grant *S-1-1-0:(OI)(CI)M'
        elif mode_num == 0o711:
            return '/grant %username%:(OI)(CI)F; /grant *S-1-1-0:(OI)(CI)X'
        elif mode_num == 0o750:
            return '/grant %username%:(OI)(CI)F; /grant *S-1-5-32-545:(OI)(CI)RX'
        elif mode_num == 0o770:
            return '/grant %username%:(OI)(CI)F; /grant *S-1-5-32-545:(OI)(CI)F'
        elif mode_num == 0o440:
            return '/grant %username%:(OI)(CI)R; /grant *S-1-5-32-545:(OI)(CI)R'
        elif mode_num == 0o400:
            return '/grant %username%:(OI)(CI)R'
        elif mode_num == 0o200:
            return '/grant %username%:(OI)(CI)W'
        elif mode_num == 0o100:
            return '/grant %username%:(OI)(CI)X'
        else:
            return '/grant *S-1-1-0:(OI)(CI)M'
    if operations:
        has_read = False
        has_write = False
        has_execute = False
        for who, op, perm in operations:
            if op == '+':
                if perm == 'r':
                    has_read = True
                elif perm == 'w':
                    has_write = True
                elif perm == 'x':
                    has_execute = True
            elif op == '-':
                if perm == 'r':
                    has_read = False
                elif perm == 'w':
                    has_write = False
                elif perm == 'x':
                    has_execute = False
            elif op == '=':
                has_read = perm == 'r'
                has_write = perm == 'w'
                has_execute = perm == 'x'
        if has_read and has_write and has_execute:
            return '/grant *S-1-1-0:(OI)(CI)F'
        elif has_read and has_execute:
            return '/grant *S-1-1-0:(OI)(CI)RX'
        elif has_read and has_write:
            return '/grant *S-1-1-0:(OI)(CI)M'
        elif has_read:
            return '/grant *S-1-1-0:(OI)(CI)R'
        elif has_write:
            return '/grant *S-1-1-0:(OI)(CI)W'
        elif has_execute:
            return '/grant *S-1-1-0:(OI)(CI)X'
    return '/grant *S-1-1-0:(OI)(CI)M'
def _parse_owner_group(owner_spec: str) -> Tuple[str, Optional[str]]:
    if ':' in owner_spec:
        parts = owner_spec.split(':', 1)
        owner = parts[0] if parts[0] else None
        group = parts[1] if parts[1] else None
        return (owner, group)
    elif '.' in owner_spec:
        parts = owner_spec.split('.', 1)
        owner = parts[0] if parts[0] else None
        group = parts[1] if parts[1] else None
        return (owner, group)
    else:
        return (owner_spec, None)
def _convert_chown(cmd: str) -> str:
    if not cmd or not cmd.strip():
        return 'Write-Output "chown: missing operand"'
    parts = _parse_command_line(cmd)
    if not parts:
        return 'Write-Output "chown: missing operand"'
    if parts[0] in ('chown', '/bin/chown', '/usr/bin/chown'):
        parts = parts[1:]
    if not parts:
        return 'Write-Output "chown: missing operand"'
    changes_only = False
    silent = False
    no_dereference = False
    recursive = False
    verbose = False
    reference_file: Optional[str] = None
    show_help = False
    show_version = False
    i = 0
    while i < len(parts):
        part = parts[i]
        if part == '--':
            i += 1
            break
        if part.startswith('/') and len(part) >= 2:
            if len(part) == 2 and part[1].isalpha():
                part = '-' + part[1:]
            elif len(part) > 2 and part[1].isalpha():
                part = '--' + part[1:]
        if part.startswith('--'):
            long_opt = part[2:]
            if '=' in long_opt:
                opt_name, opt_value = long_opt.split('=', 1)
                if opt_name == 'reference':
                    reference_file = opt_value
                i += 1
                continue
            if long_opt == 'help':
                show_help = True
                i += 1
                continue
            elif long_opt == 'version':
                show_version = True
                i += 1
                continue
            elif long_opt == 'changes':
                changes_only = True
                i += 1
                continue
            elif long_opt in ('silent', 'quiet'):
                silent = True
                i += 1
                continue
            elif long_opt == 'no-dereference':
                no_dereference = True
                i += 1
                continue
            elif long_opt == 'recursive':
                recursive = True
                i += 1
                continue
            elif long_opt == 'verbose':
                verbose = True
                i += 1
                continue
            elif long_opt == 'reference':
                if i + 1 < len(parts):
                    i += 1
                    reference_file = parts[i]
                i += 1
                continue
            i += 1
            continue
        if part.startswith('-') and len(part) > 1:
            opt_chars = part[1:]
            j = 0
            while j < len(opt_chars):
                char = opt_chars[j]
                if char == 'c':
                    changes_only = True
                    j += 1
                elif char == 'f':
                    silent = True
                    j += 1
                elif char == 'h':
                    no_dereference = True
                    j += 1
                elif char == 'R':
                    recursive = True
                    j += 1
                elif char == 'v':
                    verbose = True
                    j += 1
                elif char == '-':
                    j += 1
                    i += 1
                    break
                else:
                    j += 1
            i += 1
            continue
        break
    if show_help:
        return (
            'Write-Output "Usage: chown [OPTION]... [OWNER][:[GROUP]] FILE...\n'
            '  or:  chown [OPTION]... --reference=RFILE FILE...\n'
            'Change the owner and/or group of each FILE to OWNER and/or GROUP.\n'
            '\n'
            '  -c, --changes          like verbose but report only when a change is made\n'
            '  -f, --silent, --quiet  suppress most error messages\n'
            '  -h, --no-dereference   affect symbolic links instead of any referenced file\n'
            '  -R, --recursive        operate on files and directories recursively\n'
            '  -v, --verbose          output a diagnostic for every file processed\n'
            '      --reference=RFILE  use RFILE\'s owner and group rather than\n'
            '                         specifying OWNER:GROUP values\n'
            '      --help     display this help and exit\n'
            '      --version  output version information and exit"'
        )
    if show_version:
        return 'Write-Output "chown (GNU coreutils) 8.32"'
    remaining = parts[i:]
    if not remaining:
        return 'Write-Output "chown: missing operand"'
    owner: Optional[str] = None
    group: Optional[str] = None
    files: List[str] = []
    if reference_file:
        files = remaining
    else:
        if remaining:
            owner_spec = remaining[0]
            owner, group = _parse_owner_group(owner_spec)
            files = remaining[1:]
    if not files:
        return 'Write-Output "chown: missing file operand"'
    return _build_chown_powershell_command(
        owner, group, reference_file, files,
        changes_only, silent, no_dereference, recursive, verbose
    )
def _build_chown_powershell_command(
    owner: Optional[str],
    group: Optional[str],
    reference_file: Optional[str],
    files: List[str],
    changes_only: bool,
    silent: bool,
    no_dereference: bool,
    recursive: bool,
    verbose: bool
) -> str:
    quoted_files = []
    for f in files:
        if ' ' in f and not (f.startswith('"') or f.startswith("'")):
            quoted_files.append(f'"{f}"')
        else:
            quoted_files.append(f)
    commands = []
    if recursive and len(files) == 1:
        file_path = quoted_files[0]
        if reference_file:
            ref = reference_file
            if ' ' in ref and not (ref.startswith('"') or ref.startswith("'")):
                ref = f'"{ref}"'
            cmd = (
                f'$refAcl = Get-Acl {ref}; '
                f'Get-ChildItem -Path {file_path} -Recurse | ForEach-Object {{ '
                f'$acl = Get-Acl $_.FullName; '
                f'$acl.SetOwner($refAcl.Owner); '
                f'Set-Acl $_.FullName $acl'
            )
            if verbose or changes_only:
                cmd += '; if ($?) { Write-Output "changed ownership of `$($_.FullName)`" }'
            cmd += ' }'
            commands.append(cmd)
        else:
            cmd = (
                f'Get-ChildItem -Path {file_path} -Recurse | ForEach-Object {{ '
                f'$acl = Get-Acl $_.FullName; '
            )
            if owner:
                cmd += f'$acl.SetOwner([System.Security.Principal.NTAccount]::new("{owner}")); '
            cmd += 'Set-Acl $_.FullName $acl'
            if verbose:
                owner_str = owner if owner else 'unchanged'
                cmd += f'; Write-Output "changed ownership of `$($_.FullName)` to {owner_str}"'
            elif changes_only:
                cmd += '; if ($?) { Write-Output "changed ownership of `$($_.FullName)`" }'
            cmd += ' }'
            commands.append(cmd)
    else:
        for file_path in quoted_files:
            if reference_file:
                ref = reference_file
                if ' ' in ref and not (ref.startswith('"') or ref.startswith("'")):
                    ref = f'"{ref}"'
                cmd = (
                    f'$refAcl = Get-Acl {ref}; '
                    f'$path = {file_path}; '
                    f'$acl = Get-Acl $path; '
                    f'$acl.SetOwner($refAcl.Owner); '
                    f'Set-Acl $path $acl'
                )
                if verbose:
                    cmd += f'; Write-Output "changed ownership of `{file_path}` to `$($refAcl.Owner)"'
                elif changes_only:
                    cmd += '; if ($?) { Write-Output "changed ownership" }'
                commands.append(cmd)
            else:
                cmd = f'$path = {file_path}; $acl = Get-Acl $path; '
                if owner:
                    cmd += f'$acl.SetOwner([System.Security.Principal.NTAccount]::new("{owner}")); '
                cmd += 'Set-Acl $path $acl'
                if verbose:
                    owner_str = owner if owner else 'unchanged'
                    cmd += f'; Write-Output "changed ownership of `{file_path}` to {owner_str}"'
                elif changes_only:
                    cmd += '; if ($?) { Write-Output "changed ownership" }'
                commands.append(cmd)
    if len(commands) == 1:
        return commands[0]
    else:
        return '; '.join(commands)
def _convert_clear(cmd: str) -> str:
    if not cmd or not cmd.strip():
        return 'Clear-Host'
    parts = _parse_command_line(cmd)
    if not parts:
        return 'Clear-Host'
    if parts[0] in ('clear', '/bin/clear', '/usr/bin/clear'):
        parts = parts[1:]
    if not parts:
        return 'Clear-Host'
    flags: Set[str] = set()
    long_flags: Set[str] = set()
    i = 0
    while i < len(parts):
        part = parts[i]
        if part == '--':
            break
        if part.startswith('/') and len(part) >= 2:
            if len(part) == 2 and part[1].isalpha():
                part = '-' + part[1:]
            elif len(part) > 2 and part[1].isalpha():
                part = '--' + part[1:]
        if part.startswith('--'):
            long_opt = part[2:]
            if '=' in long_opt:
                opt_name, _ = long_opt.split('=', 1)
                long_flags.add(opt_name)
            else:
                long_flags.add(long_opt)
            i += 1
            continue
        if part.startswith('-') and len(part) > 1:
            opt_chars = part[1:]
            for char in opt_chars:
                flags.add(char)
            i += 1
            continue
        i += 1
    return 'Clear-Host'
def _convert_curl(cmd: str) -> str:
    if not cmd or not cmd.strip():
        return 'Write-Output "usage: curl [options...] <url>"'
    parts = _parse_command_line(cmd)
    if not parts:
        return 'Write-Output "usage: curl [options...] <url>"'
    if parts[0] in ('curl', '/usr/bin/curl', '/bin/curl'):
        parts = parts[1:]
    if not parts:
        return 'Write-Output "usage: curl [options...] <url>"'
    options: Dict[str, Any] = {
        'method': None,
        'headers': {},
        'body': None,
        'data': [],
        'data_raw': [],
        'data_binary': [],
        'data_urlencode': [],
        'form_data': {},
        'user': None,
        'follow_redirects': False,
        'output': None,
        'remote_name': False,
        'silent': False,
        'verbose': False,
        'head_only': False,
        'include_headers': False,
        'insecure': False,
        'compressed': False,
        'user_agent': None,
        'referer': None,
        'cookies': None,
        'cookie_jar': None,
        'connect_timeout': None,
        'max_time': None,
        'retry': None,
        'proxy': None,
        'proxy_user': None,
        'show_error': False,
        'fail': False,
        'fail_with_body': False,
        'upload_file': None,
        'url': None,
        'force_get': False,
        'cert': None,
        'cacert': None,
        'capath': None,
        'cert_type': None,
        'key': None,
        'key_type': None,
        'pass_phrase': None,
        'write_out': None,
        'dump_header': None,
        'remote_header_name': False,
        'create_dirs': False,
        'continue_at': None,
        'limit_rate': None,
        'max_redirs': None,
        'netrc': False,
        'netrc_file': None,
        'netrc_optional': False,
        'auth_method': None,
        'oauth2_bearer': None,
        'aws_sigv4': None,
        'range': None,
        'resolve': [],
        'connect_to': None,
        'no_buffer': False,
        'http_version': None,
        'ftp_ssl': False,
        'ftp_ssl_control': False,
        'ftp_ssl_reqd': False,
        'ftp_port': None,
        'ftp_skip_pasv_ip': False,
        'ftp_pasv': True,
        'ftp_eprt': True,
        'ftp_epsv': True,
        'ftp_quotes': [],
        'ftp_create_dirs': False,
        'ftp_alternative_to_user': None,
        'time_cond': None,
        'ignore_content_length': False,
        'interface': None,
        'dns_interface': None,
        'dns_ipv4_addr': None,
        'dns_ipv6_addr': None,
        'dns_servers': None,
        'local_port': None,
        'keepalive_time': None,
        'no_keepalive': False,
        'tcp_nodelay': False,
        'tcp_fastopen': False,
        'use_ascii': False,
        'ciphers': None,
        'tls_version': None,
        'tls_max': None,
        'ssl_options': [],
        'tls13_ciphers': None,
        'pinnedpubkey': None,
        'proto': None,
        'proto_default': None,
        'proto_redir': None,
        'stderr': None,
        'libcurl': None,
        'manual': False,
        'help': False,
        'version': False,
    }
    VALID_SHORT_OPTS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789'
    VALID_SHORT_OPTS_WITH_VALUE = 'HXduHAbceFToACPQrwxzEJKS'
    i = 0
    while i < len(parts):
        part = parts[i]
        if part == '--':
            i += 1
            if i < len(parts) and options['url'] is None:
                options['url'] = parts[i]
            break
        if part.startswith('/') and len(part) >= 2:
            opt_part = part[1:]
            if len(opt_part) == 1 and opt_part in VALID_SHORT_OPTS:
                part = '-' + opt_part
            elif opt_part.startswith('-') and len(opt_part) > 1:
                part = opt_part
            elif '=' in opt_part:
                part = '--' + opt_part
            elif opt_part in ('request', 'header', 'data', 'user', 'output', 'location',
                              'silent', 'verbose', 'head', 'include', 'insecure', 'compressed',
                              'user-agent', 'referer', 'cookie', 'cookie-jar', 'form',
                              'connect-timeout', 'max-time', 'retry', 'proxy', 'upload-file',
                              'url', 'cert', 'cacert', 'capath', 'key', 'pass', 'write-out',
                              'dump-header', 'continue-at', 'limit-rate', 'max-redirs',
                              'netrc-file', 'oauth2-bearer', 'range', 'interface', 'ciphers',
                              'tls-max', 'proto', 'proto-default', 'proto-redir', 'stderr',
                              'libcurl', 'help', 'version', 'manual', 'aws-sigv4'):
                part = '--' + opt_part
            elif all(c in VALID_SHORT_OPTS for c in opt_part):
                part = '-' + opt_part
        if part.startswith('--'):
            long_opt = part[2:]
            if '=' in long_opt:
                opt_name, opt_value = long_opt.split('=', 1)
                if opt_name == 'request':
                    options['method'] = opt_value.upper()
                elif opt_name == 'header':
                    _add_header(options['headers'], opt_value)
                elif opt_name == 'data':
                    options['data'].append(opt_value)
                elif opt_name == 'data-raw':
                    options['data_raw'].append(opt_value)
                elif opt_name == 'data-binary':
                    options['data_binary'].append(opt_value)
                elif opt_name == 'data-urlencode':
                    options['data_urlencode'].append(opt_value)
                elif opt_name == 'form':
                    _add_form_data(options['form_data'], opt_value)
                elif opt_name == 'user':
                    options['user'] = opt_value
                elif opt_name == 'output':
                    options['output'] = opt_value
                elif opt_name == 'user-agent':
                    options['user_agent'] = opt_value
                elif opt_name == 'referer':
                    options['referer'] = opt_value
                elif opt_name == 'cookie':
                    options['cookies'] = opt_value
                elif opt_name == 'cookie-jar':
                    options['cookie_jar'] = opt_value
                elif opt_name == 'connect-timeout':
                    options['connect_timeout'] = opt_value
                elif opt_name == 'max-time':
                    options['max_time'] = opt_value
                elif opt_name == 'retry':
                    options['retry'] = opt_value
                elif opt_name == 'proxy':
                    options['proxy'] = opt_value
                elif opt_name == 'proxy-user':
                    options['proxy_user'] = opt_value
                elif opt_name == 'upload-file':
                    options['upload_file'] = opt_value
                elif opt_name == 'url':
                    options['url'] = opt_value
                elif opt_name == 'cert':
                    options['cert'] = opt_value
                elif opt_name == 'cacert':
                    options['cacert'] = opt_value
                elif opt_name == 'capath':
                    options['capath'] = opt_value
                elif opt_name == 'cert-type':
                    options['cert_type'] = opt_value
                elif opt_name == 'key':
                    options['key'] = opt_value
                elif opt_name == 'key-type':
                    options['key_type'] = opt_value
                elif opt_name == 'pass':
                    options['pass_phrase'] = opt_value
                elif opt_name == 'write-out':
                    options['write_out'] = opt_value
                elif opt_name == 'dump-header':
                    options['dump_header'] = opt_value
                elif opt_name == 'continue-at':
                    options['continue_at'] = opt_value
                elif opt_name == 'limit-rate':
                    options['limit_rate'] = opt_value
                elif opt_name == 'max-redirs':
                    options['max_redirs'] = opt_value
                elif opt_name == 'netrc-file':
                    options['netrc_file'] = opt_value
                elif opt_name == 'oauth2-bearer':
                    options['oauth2_bearer'] = opt_value
                elif opt_name == 'aws-sigv4':
                    options['aws_sigv4'] = opt_value
                elif opt_name == 'range':
                    options['range'] = opt_value
                elif opt_name == 'interface':
                    options['interface'] = opt_value
                elif opt_name == 'dns-interface':
                    options['dns_interface'] = opt_value
                elif opt_name == 'dns-ipv4-addr':
                    options['dns_ipv4_addr'] = opt_value
                elif opt_name == 'dns-ipv6-addr':
                    options['dns_ipv6_addr'] = opt_value
                elif opt_name == 'dns-servers':
                    options['dns_servers'] = opt_value
                elif opt_name == 'local-port':
                    options['local_port'] = opt_value
                elif opt_name == 'keepalive-time':
                    options['keepalive_time'] = opt_value
                elif opt_name == 'ciphers':
                    options['ciphers'] = opt_value
                elif opt_name == 'tls-max':
                    options['tls_max'] = opt_value
                elif opt_name == 'tls13-ciphers':
                    options['tls13_ciphers'] = opt_value
                elif opt_name == 'pinnedpubkey':
                    options['pinnedpubkey'] = opt_value
                elif opt_name == 'proto':
                    options['proto'] = opt_value
                elif opt_name == 'proto-default':
                    options['proto_default'] = opt_value
                elif opt_name == 'proto-redir':
                    options['proto_redir'] = opt_value
                elif opt_name == 'stderr':
                    options['stderr'] = opt_value
                elif opt_name == 'libcurl':
                    options['libcurl'] = opt_value
                elif opt_name == 'ftp-port':
                    options['ftp_port'] = opt_value
                elif opt_name == 'ftp-alternative-to-user':
                    options['ftp_alternative_to_user'] = opt_value
                elif opt_name == 'time-cond':
                    options['time_cond'] = opt_value
                elif opt_name == 'resolve':
                    options['resolve'].append(opt_value)
                elif opt_name == 'connect-to':
                    options['connect_to'] = opt_value
                i += 1
                continue
            if long_opt == 'location':
                options['follow_redirects'] = True
                i += 1
                continue
            elif long_opt == 'silent':
                options['silent'] = True
                i += 1
                continue
            elif long_opt == 'verbose':
                options['verbose'] = True
                i += 1
                continue
            elif long_opt == 'head':
                options['head_only'] = True
                i += 1
                continue
            elif long_opt == 'include':
                options['include_headers'] = True
                i += 1
                continue
            elif long_opt == 'insecure':
                options['insecure'] = True
                i += 1
                continue
            elif long_opt == 'compressed':
                options['compressed'] = True
                i += 1
                continue
            elif long_opt == 'remote-name':
                options['remote_name'] = True
                i += 1
                continue
            elif long_opt == 'remote-header-name':
                options['remote_header_name'] = True
                i += 1
                continue
            elif long_opt == 'show-error':
                options['show_error'] = True
                i += 1
                continue
            elif long_opt == 'fail':
                options['fail'] = True
                i += 1
                continue
            elif long_opt == 'fail-with-body':
                options['fail_with_body'] = True
                i += 1
                continue
            elif long_opt == 'get':
                options['force_get'] = True
                i += 1
                continue
            elif long_opt == 'create-dirs':
                options['create_dirs'] = True
                i += 1
                continue
            elif long_opt == 'netrc':
                options['netrc'] = True
                i += 1
                continue
            elif long_opt == 'netrc-optional':
                options['netrc_optional'] = True
                i += 1
                continue
            elif long_opt == 'basic':
                options['auth_method'] = 'basic'
                i += 1
                continue
            elif long_opt == 'digest':
                options['auth_method'] = 'digest'
                i += 1
                continue
            elif long_opt == 'ntlm':
                options['auth_method'] = 'ntlm'
                i += 1
                continue
            elif long_opt == 'negotiate':
                options['auth_method'] = 'negotiate'
                i += 1
                continue
            elif long_opt == 'no-buffer':
                options['no_buffer'] = True
                i += 1
                continue
            elif long_opt == 'ignore-content-length':
                options['ignore_content_length'] = True
                i += 1
                continue
            elif long_opt == 'no-keepalive':
                options['no_keepalive'] = True
                i += 1
                continue
            elif long_opt == 'tcp-nodelay':
                options['tcp_nodelay'] = True
                i += 1
                continue
            elif long_opt == 'tcp-fastopen':
                options['tcp_fastopen'] = True
                i += 1
                continue
            elif long_opt == 'use-ascii':
                options['use_ascii'] = True
                i += 1
                continue
            elif long_opt == 'ftp-ssl':
                options['ftp_ssl'] = True
                i += 1
                continue
            elif long_opt == 'ftp-ssl-control':
                options['ftp_ssl_control'] = True
                i += 1
                continue
            elif long_opt == 'ftp-ssl-reqd':
                options['ftp_ssl_reqd'] = True
                i += 1
                continue
            elif long_opt == 'ftp-skip-pasv-ip':
                options['ftp_skip_pasv_ip'] = True
                i += 1
                continue
            elif long_opt == 'ftp-pasv':
                options['ftp_pasv'] = True
                i += 1
                continue
            elif long_opt == 'ftp-port':
                if i + 1 < len(parts):
                    i += 1
                    options['ftp_port'] = parts[i]
                i += 1
                continue
            elif long_opt == 'ftp-eprt':
                options['ftp_eprt'] = True
                i += 1
                continue
            elif long_opt == 'ftp-epsv':
                options['ftp_epsv'] = True
                i += 1
                continue
            elif long_opt == 'ftp-create-dirs':
                options['ftp_create_dirs'] = True
                i += 1
                continue
            elif long_opt == 'ftp-alternative-to-user':
                if i + 1 < len(parts):
                    i += 1
                    options['ftp_alternative_to_user'] = parts[i]
                i += 1
                continue
            elif long_opt == 'http1.0':
                options['http_version'] = '1.0'
                i += 1
                continue
            elif long_opt == 'http1.1':
                options['http_version'] = '1.1'
                i += 1
                continue
            elif long_opt == 'http2':
                options['http_version'] = '2'
                i += 1
                continue
            elif long_opt == 'http2-prior-knowledge':
                options['http_version'] = '2'
                i += 1
                continue
            elif long_opt == 'tlsv1.0':
                options['tls_version'] = '1.0'
                i += 1
                continue
            elif long_opt == 'tlsv1.1':
                options['tls_version'] = '1.1'
                i += 1
                continue
            elif long_opt == 'tlsv1.2':
                options['tls_version'] = '1.2'
                i += 1
                continue
            elif long_opt == 'tlsv1.3':
                options['tls_version'] = '1.3'
                i += 1
                continue
            elif long_opt == 'ssl':
                options['ssl_options'].append('ssl')
                i += 1
                continue
            elif long_opt == 'sslv2':
                options['ssl_options'].append('sslv2')
                i += 1
                continue
            elif long_opt == 'sslv3':
                options['ssl_options'].append('sslv3')
                i += 1
                continue
            elif long_opt == 'help':
                options['help'] = True
                i += 1
                continue
            elif long_opt == 'version':
                options['version'] = True
                i += 1
                continue
            elif long_opt == 'manual':
                options['manual'] = True
                i += 1
                continue
            elif long_opt == 'request':
                if i + 1 < len(parts):
                    i += 1
                    options['method'] = parts[i].upper()
                i += 1
                continue
            elif long_opt == 'header':
                if i + 1 < len(parts):
                    i += 1
                    _add_header(options['headers'], parts[i])
                i += 1
                continue
            elif long_opt == 'data':
                if i + 1 < len(parts):
                    i += 1
                    options['data'].append(parts[i])
                i += 1
                continue
            elif long_opt == 'data-raw':
                if i + 1 < len(parts):
                    i += 1
                    options['data_raw'].append(parts[i])
                i += 1
                continue
            elif long_opt == 'data-binary':
                if i + 1 < len(parts):
                    i += 1
                    options['data_binary'].append(parts[i])
                i += 1
                continue
            elif long_opt == 'data-urlencode':
                if i + 1 < len(parts):
                    i += 1
                    options['data_urlencode'].append(parts[i])
                i += 1
                continue
            elif long_opt == 'form':
                if i + 1 < len(parts):
                    i += 1
                    _add_form_data(options['form_data'], parts[i])
                i += 1
                continue
            elif long_opt == 'user':
                if i + 1 < len(parts):
                    i += 1
                    options['user'] = parts[i]
                i += 1
                continue
            elif long_opt == 'output':
                if i + 1 < len(parts):
                    i += 1
                    options['output'] = parts[i]
                i += 1
                continue
            elif long_opt == 'user-agent':
                if i + 1 < len(parts):
                    i += 1
                    options['user_agent'] = parts[i]
                i += 1
                continue
            elif long_opt == 'referer':
                if i + 1 < len(parts):
                    i += 1
                    options['referer'] = parts[i]
                i += 1
                continue
            elif long_opt == 'cookie':
                if i + 1 < len(parts):
                    i += 1
                    options['cookies'] = parts[i]
                i += 1
                continue
            elif long_opt == 'cookie-jar':
                if i + 1 < len(parts):
                    i += 1
                    options['cookie_jar'] = parts[i]
                i += 1
                continue
            elif long_opt == 'connect-timeout':
                if i + 1 < len(parts):
                    i += 1
                    options['connect_timeout'] = parts[i]
                i += 1
                continue
            elif long_opt == 'max-time':
                if i + 1 < len(parts):
                    i += 1
                    options['max_time'] = parts[i]
                i += 1
                continue
            elif long_opt == 'retry':
                if i + 1 < len(parts):
                    i += 1
                    options['retry'] = parts[i]
                i += 1
                continue
            elif long_opt == 'proxy':
                if i + 1 < len(parts):
                    i += 1
                    options['proxy'] = parts[i]
                i += 1
                continue
            elif long_opt == 'proxy-user':
                if i + 1 < len(parts):
                    i += 1
                    options['proxy_user'] = parts[i]
                i += 1
                continue
            elif long_opt == 'upload-file':
                if i + 1 < len(parts):
                    i += 1
                    options['upload_file'] = parts[i]
                i += 1
                continue
            elif long_opt == 'url':
                if i + 1 < len(parts):
                    i += 1
                    options['url'] = parts[i]
                i += 1
                continue
            elif long_opt == 'cert':
                if i + 1 < len(parts):
                    i += 1
                    options['cert'] = parts[i]
                i += 1
                continue
            elif long_opt == 'cacert':
                if i + 1 < len(parts):
                    i += 1
                    options['cacert'] = parts[i]
                i += 1
                continue
            elif long_opt == 'capath':
                if i + 1 < len(parts):
                    i += 1
                    options['capath'] = parts[i]
                i += 1
                continue
            elif long_opt == 'cert-type':
                if i + 1 < len(parts):
                    i += 1
                    options['cert_type'] = parts[i]
                i += 1
                continue
            elif long_opt == 'key':
                if i + 1 < len(parts):
                    i += 1
                    options['key'] = parts[i]
                i += 1
                continue
            elif long_opt == 'key-type':
                if i + 1 < len(parts):
                    i += 1
                    options['key_type'] = parts[i]
                i += 1
                continue
            elif long_opt == 'pass':
                if i + 1 < len(parts):
                    i += 1
                    options['pass_phrase'] = parts[i]
                i += 1
                continue
            elif long_opt == 'write-out':
                if i + 1 < len(parts):
                    i += 1
                    options['write_out'] = parts[i]
                i += 1
                continue
            elif long_opt == 'dump-header':
                if i + 1 < len(parts):
                    i += 1
                    options['dump_header'] = parts[i]
                i += 1
                continue
            elif long_opt == 'continue-at':
                if i + 1 < len(parts):
                    i += 1
                    options['continue_at'] = parts[i]
                i += 1
                continue
            elif long_opt == 'limit-rate':
                if i + 1 < len(parts):
                    i += 1
                    options['limit_rate'] = parts[i]
                i += 1
                continue
            elif long_opt == 'max-redirs':
                if i + 1 < len(parts):
                    i += 1
                    options['max_redirs'] = parts[i]
                i += 1
                continue
            elif long_opt == 'netrc-file':
                if i + 1 < len(parts):
                    i += 1
                    options['netrc_file'] = parts[i]
                i += 1
                continue
            elif long_opt == 'oauth2-bearer':
                if i + 1 < len(parts):
                    i += 1
                    options['oauth2_bearer'] = parts[i]
                i += 1
                continue
            elif long_opt == 'aws-sigv4':
                if i + 1 < len(parts):
                    i += 1
                    options['aws_sigv4'] = parts[i]
                i += 1
                continue
            elif long_opt == 'range':
                if i + 1 < len(parts):
                    i += 1
                    options['range'] = parts[i]
                i += 1
                continue
            elif long_opt == 'interface':
                if i + 1 < len(parts):
                    i += 1
                    options['interface'] = parts[i]
                i += 1
                continue
            elif long_opt == 'ciphers':
                if i + 1 < len(parts):
                    i += 1
                    options['ciphers'] = parts[i]
                i += 1
                continue
            elif long_opt == 'tls-max':
                if i + 1 < len(parts):
                    i += 1
                    options['tls_max'] = parts[i]
                i += 1
                continue
            elif long_opt == 'resolve':
                if i + 1 < len(parts):
                    i += 1
                    options['resolve'].append(parts[i])
                i += 1
                continue
            elif long_opt == 'connect-to':
                if i + 1 < len(parts):
                    i += 1
                    options['connect_to'] = parts[i]
                i += 1
                continue
            i += 1
            continue
        if part.startswith('-') and len(part) > 1:
            opt_chars = part[1:]
            j = 0
            while j < len(opt_chars):
                char = opt_chars[j]
                if char == 'X':
                    if j + 1 < len(opt_chars):
                        options['method'] = opt_chars[j + 1:].upper()
                        break
                    elif i + 1 < len(parts):
                        i += 1
                        options['method'] = parts[i].upper()
                    j += 1
                elif char == 'H':
                    if j + 1 < len(opt_chars):
                        _add_header(options['headers'], opt_chars[j + 1:])
                        break
                    elif i + 1 < len(parts):
                        i += 1
                        _add_header(options['headers'], parts[i])
                    j += 1
                elif char == 'd':
                    if j + 1 < len(opt_chars):
                        options['data'].append(opt_chars[j + 1:])
                        break
                    elif i + 1 < len(parts):
                        i += 1
                        options['data'].append(parts[i])
                    j += 1
                elif char == 'u':
                    if j + 1 < len(opt_chars):
                        options['user'] = opt_chars[j + 1:]
                        break
                    elif i + 1 < len(parts):
                        i += 1
                        options['user'] = parts[i]
                    j += 1
                elif char == 'o':
                    if j + 1 < len(opt_chars):
                        options['output'] = opt_chars[j + 1:]
                        break
                    elif i + 1 < len(parts):
                        i += 1
                        options['output'] = parts[i]
                    j += 1
                elif char == 'O':
                    options['remote_name'] = True
                    j += 1
                elif char == 'L':
                    options['follow_redirects'] = True
                    j += 1
                elif char == 's':
                    options['silent'] = True
                    j += 1
                elif char == 'S':
                    options['show_error'] = True
                    j += 1
                elif char == 'v':
                    options['verbose'] = True
                    j += 1
                elif char == 'I':
                    options['head_only'] = True
                    j += 1
                elif char == 'i':
                    options['include_headers'] = True
                    j += 1
                elif char == 'k':
                    options['insecure'] = True
                    j += 1
                elif char == 'f':
                    options['fail'] = True
                    j += 1
                elif char == 'A':
                    if j + 1 < len(opt_chars):
                        options['user_agent'] = opt_chars[j + 1:]
                        break
                    elif i + 1 < len(parts):
                        i += 1
                        options['user_agent'] = parts[i]
                    j += 1
                elif char == 'e':
                    if j + 1 < len(opt_chars):
                        options['referer'] = opt_chars[j + 1:]
                        break
                    elif i + 1 < len(parts):
                        i += 1
                        options['referer'] = parts[i]
                    j += 1
                elif char == 'b':
                    if j + 1 < len(opt_chars):
                        options['cookies'] = opt_chars[j + 1:]
                        break
                    elif i + 1 < len(parts):
                        i += 1
                        options['cookies'] = parts[i]
                    j += 1
                elif char == 'c':
                    if j + 1 < len(opt_chars):
                        options['cookie_jar'] = opt_chars[j + 1:]
                        break
                    elif i + 1 < len(parts):
                        i += 1
                        options['cookie_jar'] = parts[i]
                    j += 1
                elif char == 'x':
                    if j + 1 < len(opt_chars):
                        options['proxy'] = opt_chars[j + 1:]
                        break
                    elif i + 1 < len(parts):
                        i += 1
                        options['proxy'] = parts[i]
                    j += 1
                elif char == 'U':
                    if j + 1 < len(opt_chars):
                        options['proxy_user'] = opt_chars[j + 1:]
                        break
                    elif i + 1 < len(parts):
                        i += 1
                        options['proxy_user'] = parts[i]
                    j += 1
                elif char == 'T':
                    if j + 1 < len(opt_chars):
                        options['upload_file'] = opt_chars[j + 1:]
                        break
                    elif i + 1 < len(parts):
                        i += 1
                        options['upload_file'] = parts[i]
                    j += 1
                elif char == 'G':
                    options['force_get'] = True
                    j += 1
                elif char == 'E':
                    if j + 1 < len(opt_chars):
                        options['cert'] = opt_chars[j + 1:]
                        break
                    elif i + 1 < len(parts):
                        i += 1
                        options['cert'] = parts[i]
                    j += 1
                elif char == 'J':
                    options['remote_header_name'] = True
                    j += 1
                elif char == 'C':
                    if j + 1 < len(opt_chars):
                        options['continue_at'] = opt_chars[j + 1:]
                        break
                    elif i + 1 < len(parts):
                        i += 1
                        options['continue_at'] = parts[i]
                    j += 1
                elif char == 'r':
                    if j + 1 < len(opt_chars):
                        options['range'] = opt_chars[j + 1:]
                        break
                    elif i + 1 < len(parts):
                        i += 1
                        options['range'] = parts[i]
                    j += 1
                elif char == 'D':
                    if j + 1 < len(opt_chars):
                        options['dump_header'] = opt_chars[j + 1:]
                        break
                    elif i + 1 < len(parts):
                        i += 1
                        options['dump_header'] = parts[i]
                    j += 1
                elif char == 'w':
                    if j + 1 < len(opt_chars):
                        options['write_out'] = opt_chars[j + 1:]
                        break
                    elif i + 1 < len(parts):
                        i += 1
                        options['write_out'] = parts[i]
                    j += 1
                elif char == 'F':
                    if j + 1 < len(opt_chars):
                        _add_form_data(options['form_data'], opt_chars[j + 1:])
                        break
                    elif i + 1 < len(parts):
                        i += 1
                        _add_form_data(options['form_data'], parts[i])
                    j += 1
                elif char == 'K':
                    if j + 1 < len(opt_chars):
                        break
                    elif i + 1 < len(parts):
                        i += 1
                    j += 1
                elif char == 'P':
                    if j + 1 < len(opt_chars):
                        options['ftp_port'] = opt_chars[j + 1:]
                        break
                    elif i + 1 < len(parts):
                        i += 1
                        options['ftp_port'] = parts[i]
                    j += 1
                elif char == 'Q':
                    if j + 1 < len(opt_chars):
                        options['ftp_quotes'].append(opt_chars[j + 1:])
                        break
                    elif i + 1 < len(parts):
                        i += 1
                        options['ftp_quotes'].append(parts[i])
                    j += 1
                elif char == 'B':
                    options['use_ascii'] = True
                    j += 1
                elif char == 'n':
                    options['netrc'] = True
                    j += 1
                elif char == 'N':
                    options['no_buffer'] = True
                    j += 1
                elif char == 'h':
                    options['help'] = True
                    j += 1
                elif char == 'V':
                    options['version'] = True
                    j += 1
                elif char == 'M':
                    options['manual'] = True
                    j += 1
                elif char == '0':
                    options['http_version'] = '1.0'
                    j += 1
                elif char == '1':
                    options['tls_version'] = '1.0'
                    j += 1
                elif char == '2':
                    options['ssl_options'].append('sslv2')
                    j += 1
                elif char == '3':
                    options['ssl_options'].append('sslv3')
                    j += 1
                elif char == '4':
                    j += 1
                elif char == '6':
                    j += 1
                elif char == 'a':
                    j += 1
                elif char == 'l':
                    j += 1
                elif char == 'p':
                    options['ftp_pasv'] = False
                    j += 1
                elif char == 't':
                    if j + 1 < len(opt_chars):
                        break
                    elif i + 1 < len(parts):
                        i += 1
                    j += 1
                elif char == 'y':
                    if j + 1 < len(opt_chars):
                        break
                    elif i + 1 < len(parts):
                        i += 1
                    j += 1
                elif char == 'Y':
                    if j + 1 < len(opt_chars):
                        break
                    elif i + 1 < len(parts):
                        i += 1
                    j += 1
                elif char == 'z':
                    if j + 1 < len(opt_chars):
                        options['time_cond'] = opt_chars[j + 1:]
                        break
                    elif i + 1 < len(parts):
                        i += 1
                        options['time_cond'] = parts[i]
                    j += 1
                elif char == 'm':
                    if j + 1 < len(opt_chars):
                        options['max_time'] = opt_chars[j + 1:]
                        break
                    elif i + 1 < len(parts):
                        i += 1
                        options['max_time'] = parts[i]
                    j += 1
                elif char == 'Z':
                    j += 1
                elif char == '#':
                    j += 1
                elif char == '~':
                    j += 1
                elif char == '?':
                    options['help'] = True
                    j += 1
                else:
                    j += 1
            i += 1
            continue
        if options['url'] is None:
            options['url'] = part
        i += 1
    return _build_curl_powershell_command(options)
def _add_header(headers: Dict[str, str], header_str: str) -> None:
    if ':' in header_str:
        name, value = header_str.split(':', 1)
        headers[name.strip()] = value.strip()
    else:
        headers[header_str] = ''
def _add_form_data(form_data: Dict[str, str], form_str: str) -> None:
    if '=' in form_str:
        name, value = form_str.split('=', 1)
        form_data[name] = value
    else:
        form_data[form_str] = ''
def _build_curl_powershell_command(options: Dict[str, Any]) -> str:
    if options.get('help'):
        return (
            'Write-Output "curl - transfer a URL\n'
            'Usage: curl [options...] <url>\n'
            'Options:\n'
            '  -X, --request <method>   Specify request method\n'
            '  -H, --header <header>    Add header\n'
            '  -d, --data <data>        HTTP POST data\n'
            '  -u, --user <user:pass>   User and password\n'
            '  -L, --location           Follow redirects\n'
            '  -o, --output <file>      Write output to file\n'
            '  -O, --remote-name        Write to file named like remote\n'
            '  -s, --silent             Silent mode\n'
            '  -v, --verbose            Verbose mode\n'
            '  -I, --head               Fetch headers only\n'
            '  -i, --include            Include response headers\n'
            '  -k, --insecure           Allow insecure SSL\n'
            '  -A, --user-agent <str>   Send User-Agent\n'
            '  -b, --cookie <data>      Send cookies\n'
            '  -c, --cookie-jar <file>  Save cookies to file\n'
            '  -F, --form <data>        Multipart form data\n'
            '  --compressed             Request compressed response\n'
            '  -h, --help               Display help\n'
            '  -V, --version            Display version"'
        )
    if options.get('version'):
        return 'Write-Output "curl 8.0.0"'
    if options.get('manual'):
        return 'Start-Process https://curl.se/docs/manpage.html'
    url = options.get('url')
    if not url:
        return 'Write-Output "curl: no URL specified"'
    use_rest_method = _should_use_rest_method(options)
    cmd_parts = []
    if use_rest_method:
        cmd_parts.append('Invoke-RestMethod')
    else:
        cmd_parts.append('Invoke-WebRequest')
    cmd_parts.append(f'-Uri "{url}"')
    method = options.get('method')
    if method:
        cmd_parts.append(f'-Method {method}')
    elif options.get('head_only'):
        cmd_parts.append('-Method HEAD')
    elif options.get('upload_file'):
        cmd_parts.append('-Method PUT')
    elif options.get('data') or options.get('data_raw') or options.get('data_binary') or options.get('data_urlencode'):
        cmd_parts.append('-Method POST')
    elif options.get('form_data'):
        cmd_parts.append('-Method POST')
    headers = options.get('headers', {}).copy()
    user_agent = options.get('user_agent')
    if user_agent:
        headers['User-Agent'] = user_agent
    referer = options.get('referer')
    if referer:
        headers['Referer'] = referer
    cookies = options.get('cookies')
    if cookies:
        headers['Cookie'] = cookies
    user = options.get('user')
    if user:
        headers['Authorization'] = f'Basic ([Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes("{user}")))'
    oauth2_bearer = options.get('oauth2_bearer')
    if oauth2_bearer:
        headers['Authorization'] = f'Bearer {oauth2_bearer}'
    range_val = options.get('range')
    if range_val:
        headers['Range'] = f'bytes={range_val}'
    if headers:
        header_strs = [f'"{k}"="{v}"' for k, v in headers.items()]
        cmd_parts.append(f'-Headers @{{{"; ".join(header_strs)}}}')
    body_parts = []
    body_parts.extend(options.get('data', []))
    body_parts.extend(options.get('data_raw', []))
    body_parts.extend(options.get('data_binary', []))
    body_parts.extend(options.get('data_urlencode', []))
    if body_parts:
        body_str = '&'.join(body_parts)
        cmd_parts.append(f'-Body "{body_str}"')
    elif options.get('form_data'):
        form_data = options.get('form_data', {})
        if form_data:
            form_strs = [f'"{k}"="{v}"' for k, v in form_data.items()]
            cmd_parts.append(f'-Form @{{{"; ".join(form_strs)}}}')
    elif options.get('upload_file'):
        upload_file = options.get('upload_file')
        cmd_parts.append(f'-InFile "{upload_file}"')
    output = options.get('output')
    if output:
        cmd_parts.append(f'-OutFile "{output}"')
    elif options.get('remote_name'):
        cmd_parts.append(f'-OutFile (Split-Path -Leaf "{url}")')
    proxy = options.get('proxy')
    if proxy:
        cmd_parts.append(f'-Proxy "{proxy}"')
    proxy_user = options.get('proxy_user')
    if proxy_user and proxy:
        cmd_parts.append(f'-ProxyUseDefaultCredentials')
    if options.get('insecure'):
        cmd_parts.append('-SkipCertificateCheck')
    max_time = options.get('max_time')
    if max_time:
        cmd_parts.append(f'-TimeoutSec {max_time}')
    elif options.get('connect_timeout'):
        cmd_parts.append(f'-TimeoutSec {options["connect_timeout"]}')
    if options.get('follow_redirects'):
        cmd_parts.append('-MaximumRedirection 10')
    max_redirs = options.get('max_redirs')
    if max_redirs:
        cmd_parts.append(f'-MaximumRedirection {max_redirs}')
    if options.get('verbose'):
        cmd_parts.append('-Verbose')
    if options.get('silent'):
        pass
    command = ' '.join(cmd_parts)
    if options.get('silent'):
        command = f'{command} | Out-Null'
    return command
def _should_use_rest_method(options: Dict[str, Any]) -> bool:
    if options.get('method') in ('POST', 'PUT', 'PATCH', 'DELETE'):
        return True
    if options.get('data') or options.get('data_raw') or options.get('form_data'):
        return True
    return False
if __name__ == "__main__":
    test_cases = [
        "curl https://example.com",
        "curl http://localhost:8080/api",
        "curl -X GET https://api.example.com/users",
        "curl -X POST https://api.example.com/users",
        "curl -X PUT https://api.example.com/users/1",
        "curl -X DELETE https://api.example.com/users/1",
        "curl -X PATCH https://api.example.com/users/1",
        "curl -H 'Authorization: Bearer token123' https://api.example.com",
        "curl -H 'Content-Type: application/json' -H 'Accept: application/json' https://api.example.com",
        "curl -d 'name=value' https://api.example.com",
        "curl -d 'name1=value1' -d 'name2=value2' https://api.example.com",
        "curl -X POST -d '{\"key\":\"value\"}' https://api.example.com",
        "curl -A 'Mozilla/5.0' https://example.com",
        "curl -e 'https://referer.com' https://example.com",
        "curl -u user:password https://api.example.com",
        "curl --oauth2-bearer token123 https://api.example.com",
        "curl -o output.txt https://example.com/file.txt",
        "curl -O https://example.com/file.txt",
        "curl -J -O https://example.com/file.txt",
        "curl -L https://example.com/redirect",
        "curl --max-redirs 5 -L https://example.com/redirect",
        "curl -k https://self-signed.example.com",
        "curl --insecure https://self-signed.example.com",
        "curl -b 'session=abc123' https://example.com",
        "curl -c cookies.txt https://example.com",
        "curl -s https://example.com",
        "curl -v https://example.com",
        "curl -sS https://example.com",
        "curl -I https://example.com",
        "curl --head https://example.com",
        "curl -i https://example.com",
        "curl -F 'file=@upload.txt' https://api.example.com/upload",
        "curl -F 'name=value' -F 'file=@upload.txt' https://api.example.com/upload",
        "curl -x http://proxy:8080 https://example.com",
        "curl --proxy http://proxy:8080 https://example.com",
        "curl --connect-timeout 30 https://example.com",
        "curl --max-time 60 https://example.com",
        "curl -m 60 https://example.com",
        "curl -T file.txt https://example.com/upload",
        "curl --upload-file file.txt https://example.com/upload",
        "curl -r 0-100 https://example.com/file.txt",
        "curl --compressed https://example.com",
        "curl /X POST https://api.example.com",
        "curl /H 'Authorization: Bearer token' https://api.example.com",
        "curl /L https://example.com/redirect",
        "curl /s https://example.com",
        "curl /v https://example.com",
        "curl /I https://example.com",
        "curl /k https://self-signed.example.com",
        "curl /o output.txt https://example.com/file.txt",
        "curl /O https://example.com/file.txt",
        "curl /X POST /d 'key=value' https://api.example.com",
        "curl /u user:pass https://api.example.com",
        "curl /request POST https://api.example.com",
        "curl /header 'Content-Type: application/json' https://api.example.com",
        "curl /location https://example.com",
        "curl /silent https://example.com",
        "curl /insecure https://example.com",
        "curl -vL https://example.com",
        "curl -sS https://example.com",
        "curl -Ik https://example.com",
        "curl -X POST -H 'Content-Type: application/json' -d '{\"name\":\"test\"}' https://api.example.com/users",
        "curl -X PUT -u admin:secret -H 'Accept: application/json' https://api.example.com/users/1",
        "curl -L -o file.zip -H 'User-Agent: MyApp' https://example.com/download",
        "curl -X POST -F 'file=@document.pdf' -F 'name=report' https://api.example.com/upload",
        "curl --help",
        "curl --version",
        "curl -h",
        "curl -V",
        "",
        "curl",
        "curl -X",
        "curl https://example.com -X POST",
    ]
    for test in test_cases:
        result = _convert_curl(test)
        print(f"Input:  {test}")
        print(f"Output: {result}")
        print()
def _convert_slash_to_dash(arg: str) -> str:
    if not arg.startswith('/') or len(arg) < 2:
        return arg
    if arg[1].isalpha():
        if len(arg) == 2:
            return '-' + arg[1:]
        else:
            return '--' + arg[1:]
    return arg
def _parse_list(list_str: str) -> List[Tuple[Optional[int], Optional[int]]]:
    ranges = []
    items = list_str.split(',')
    for item in items:
        item = item.strip()
        if not item:
            continue
        if '-' in item:
            if item.startswith('-'):
                try:
                    end = int(item[1:])
                    ranges.append((None, end))
                except ValueError:
                    pass
            elif item.endswith('-'):
                try:
                    start = int(item[:-1])
                    ranges.append((start, None))
                except ValueError:
                    pass
            else:
                parts = item.split('-', 1)
                try:
                    start = int(parts[0])
                    end = int(parts[1])
                    ranges.append((start, end))
                except ValueError:
                    pass
        else:
            try:
                n = int(item)
                ranges.append((n, n))
            except ValueError:
                pass
    return ranges
def _build_cut_powershell_command(
    mode: str,
    ranges: List[Tuple[Optional[int], Optional[int]]],
    delimiter: str,
    output_delimiter: Optional[str],
    complement: bool,
    only_delimited: bool,
    zero_terminated: bool,
    files: List[str]
) -> str:
    if not ranges:
        return 'Write-Error "cut: you must specify a list of bytes, characters, or fields"'
    indices = []
    for start, end in ranges:
        if start is None and end is not None:
            indices.extend(range(0, end))
        elif start is not None and end is None:
            indices.append((start - 1, None))
        elif start is not None and end is not None:
            indices.extend(range(start - 1, end))
    unique_indices = []
    seen = set()
    for idx in indices:
        if isinstance(idx, tuple):
            unique_indices.append(idx)
        elif idx not in seen:
            seen.add(idx)
            unique_indices.append(idx)
    simple_indices = [i for i in unique_indices if not isinstance(i, tuple)]
    range_indices = [i for i in unique_indices if isinstance(i, tuple)]
    simple_indices.sort()
    if complement:
        pass
    if files:
        quoted_files = []
        for f in files:
            if ' ' in f and not (f.startswith('"') or f.startswith("'")):
                quoted_files.append(f'"{f}"')
            else:
                quoted_files.append(f)
        file_list = ','.join(quoted_files)
        input_cmd = f'Get-Content {file_list}'
    else:
        input_cmd = '$input'
    if mode == 'bytes':
        ps_cmd = _build_bytes_command(input_cmd, simple_indices, range_indices, complement, zero_terminated)
    elif mode == 'chars':
        ps_cmd = _build_chars_command(input_cmd, simple_indices, range_indices, complement, zero_terminated)
    else:
        ps_cmd = _build_fields_command(
            input_cmd, simple_indices, range_indices, delimiter,
            output_delimiter, complement, only_delimited, zero_terminated
        )
    return ps_cmd
def _build_bytes_command(
    input_cmd: str,
    indices: List[int],
    range_indices: List[Tuple[int, None]],
    complement: bool,
    zero_terminated: bool
) -> str:
    if zero_terminated:
        input_cmd += ' -Delimiter "`0"'
    if complement:
        if not indices and not range_indices:
            return f'{input_cmd}'
        exclude_set = set(indices)
        idx_list = ','.join(str(i) for i in sorted(exclude_set))
        return (
            f'{input_cmd} | ForEach-Object {{ '
            f'$bytes = [System.Text.Encoding]::UTF8.GetBytes($_); '
            f'$exclude = @({idx_list}); '
            f'$result = @(); '
            f'for ($i = 0; $i -lt $bytes.Length; $i++) {{ '
            f'if ($exclude -notcontains $i) {{ $result += $bytes[$i] }} }}; '
            f'[System.Text.Encoding]::UTF8.GetString($result) }}'
        )
    if range_indices and not indices:
        start = range_indices[0][0]
        return f'{input_cmd} | ForEach-Object {{ $_.Substring({start}) }}'
    elif indices and not range_indices:
        if len(indices) == 1:
            return f'{input_cmd} | ForEach-Object {{ $_.Substring({indices[0]}, 1) }}'
        else:
            substrs = []
            for idx in indices:
                substrs.append(f'$_.Substring({idx}, 1)')
            return f'{input_cmd} | ForEach-Object {{ ' + ' + '.join(substrs) + ' }'
    else:
        idx_list = ','.join(str(i) for i in indices)
        range_parts = []
        for start, _ in range_indices:
            range_parts.append(f"$_.Substring({start})")
        if range_parts:
            return (
                f'{input_cmd} | ForEach-Object {{ '
                f'$result = ""; '
                f'foreach ($i in @({idx_list})) {{ '
                f'if ($i -lt $_.Length) {{ $result += $_.Substring($i, 1) }} }}; '
                f'$result }}'
            )
        else:
            return (
                f'{input_cmd} | ForEach-Object {{ '
                f'$result = ""; '
                f'foreach ($i in @({idx_list})) {{ '
                f'if ($i -lt $_.Length) {{ $result += $_.Substring($i, 1) }} }}; '
                f'$result }}'
            )
def _build_chars_command(
    input_cmd: str,
    indices: List[int],
    range_indices: List[Tuple[int, None]],
    complement: bool,
    zero_terminated: bool
) -> str:
    if zero_terminated:
        input_cmd += ' -Delimiter "`0"'
    if complement:
        if not indices and not range_indices:
            return f'{input_cmd}'
        idx_list = ','.join(str(i) for i in sorted(set(indices)))
        return (
            f'{input_cmd} | ForEach-Object {{ '
            f'$chars = $_.ToCharArray(); '
            f'$exclude = @({idx_list}); '
            f'$result = @(); '
            f'for ($i = 0; $i -lt $chars.Length; $i++) {{ '
            f'if ($exclude -notcontains $i) {{ $result += $chars[$i] }} }}; '
            f'-join $result }}'
        )
    if range_indices and not indices:
        start = range_indices[0][0]
        return f'{input_cmd} | ForEach-Object {{ $_.Substring({start}) }}'
    elif indices and not range_indices:
        if len(indices) == 1:
            return f'{input_cmd} | ForEach-Object {{ $_.Substring({indices[0]}, 1) }}'
        else:
            idx_list = ','.join(str(i) for i in indices)
            return (
                f'{input_cmd} | ForEach-Object {{ '
                f'$result = ""; '
                f'foreach ($i in @({idx_list})) {{ '
                f'if ($i -lt $_.Length) {{ $result += $_.Substring($i, 1) }} }}; '
                f'$result }}'
            )
    else:
        idx_list = ','.join(str(i) for i in indices)
        return (
            f'{input_cmd} | ForEach-Object {{ '
            f'$result = ""; '
            f'foreach ($i in @({idx_list})) {{ '
            f'if ($i -lt $_.Length) {{ $result += $_.Substring($i, 1) }} }}; '
            f'$result }}'
        )
def _build_fields_command(
    input_cmd: str,
    indices: List[int],
    range_indices: List[Tuple[int, None]],
    delimiter: str,
    output_delimiter: Optional[str],
    complement: bool,
    only_delimited: bool,
    zero_terminated: bool
) -> str:
    if zero_terminated:
        input_cmd += ' -Delimiter "`0"'
    escaped_delim = delimiter.replace('"', '`"').replace('$', '`$')
    out_delim = output_delimiter if output_delimiter is not None else escaped_delim
    out_delim = out_delim.replace('"', '`"').replace('$', '`$')
    if complement:
        idx_list = ','.join(str(i) for i in sorted(set(indices)))
        if only_delimited:
            filter_line = f'if ($_ -notlike "*{escaped_delim}*") {{ return }}'
        else:
            filter_line = ''
        return (
            f'{input_cmd} | ForEach-Object {{ '
            f'{filter_line}'
            f'$fields = $_.Split("{escaped_delim}"); '
            f'$exclude = @({idx_list}); '
            f'$result = @(); '
            f'for ($i = 0; $i -lt $fields.Length; $i++) {{ '
            f'if ($exclude -notcontains $i) {{ $result += $fields[$i] }} }}; '
            f'$result -join "{out_delim}" }}'
        )
    all_indices = list(indices)
    for start, _ in range_indices:
        all_indices.append((start, 'to_end'))
    if not all_indices:
        return f'{input_cmd}'
    if len(all_indices) > 1 and all(isinstance(i, int) for i in all_indices):
        sorted_indices = sorted(all_indices)
        is_consecutive = all(sorted_indices[i] + 1 == sorted_indices[i + 1] for i in range(len(sorted_indices) - 1))
        if is_consecutive:
            start_idx = sorted_indices[0]
            count = len(sorted_indices)
            if only_delimited:
                return (
                    f'{input_cmd} | ForEach-Object {{ '
                    f'if ($_ -notlike "*{escaped_delim}*") {{ return }}; '
                    f'$fields = $_.Split("{escaped_delim}"); '
                    f'if ({start_idx} -lt $fields.Length) {{ '
                    f'$selected = $fields[{start_idx}..([Math]::Min({start_idx + count - 1}, $fields.Length - 1))]; '
                    f'$selected -join "{out_delim}" }} }}'
                )
            else:
                return (
                    f'{input_cmd} | ForEach-Object {{ '
                    f'$fields = $_.Split("{escaped_delim}"); '
                    f'if ({start_idx} -lt $fields.Length) {{ '
                    f'$selected = $fields[{start_idx}..([Math]::Min({start_idx + count - 1}, $fields.Length - 1))]; '
                    f'$selected -join "{out_delim}" }} '
                    f'else {{ $_ }} }}'
                )
    has_range_to_end = any(isinstance(i, tuple) or (isinstance(i, tuple) and len(i) == 2 and i[1] == 'to_end') for i in all_indices)
    if has_range_to_end:
        simple_indices = [i for i in all_indices if isinstance(i, int)]
        range_starts = [i[0] for i in all_indices if isinstance(i, tuple)]
        idx_list = ','.join(str(i) for i in simple_indices)
        range_logic = ''
        for start in range_starts:
            if range_logic:
                range_logic += '; '
            range_logic += f'if ({start} -lt $fields.Length) {{ $result += $fields[{start}..($fields.Length - 1)] }}'
        if only_delimited:
            return (
                f'{input_cmd} | ForEach-Object {{ '
                f'if ($_ -notlike "*{escaped_delim}*") {{ return }}; '
                f'$fields = $_.Split("{escaped_delim}"); '
                f'$result = @(); '
                f'foreach ($i in @({idx_list})) {{ if ($i -lt $fields.Length) {{ $result += $fields[$i] }} }}; '
                f'{range_logic}; '
                f'$result -join "{out_delim}" }}'
            )
        else:
            return (
                f'{input_cmd} | ForEach-Object {{ '
                f'$fields = $_.Split("{escaped_delim}"); '
                f'$result = @(); '
                f'foreach ($i in @({idx_list})) {{ if ($i -lt $fields.Length) {{ $result += $fields[$i] }} }}; '
                f'{range_logic}; '
                f'$result -join "{out_delim}" }}'
            )
    idx_list = ','.join(str(i) for i in all_indices)
    if only_delimited:
        return (
            f'{input_cmd} | ForEach-Object {{ '
            f'if ($_ -notlike "*{escaped_delim}*") {{ return }}; '
            f'$fields = $_.Split("{escaped_delim}"); '
            f'$result = @(); '
            f'foreach ($i in @({idx_list})) {{ if ($i -lt $fields.Length) {{ $result += $fields[$i] }} }}; '
            f'$result -join "{out_delim}" }}'
        )
    else:
        return (
            f'{input_cmd} | ForEach-Object {{ '
            f'$fields = $_.Split("{escaped_delim}"); '
            f'$result = @(); '
            f'foreach ($i in @({idx_list})) {{ if ($i -lt $fields.Length) {{ $result += $fields[$i] }} }}; '
            f'$result -join "{out_delim}" }}'
        )
def _convert_cut(cmd: str) -> str:
    if not cmd or not cmd.strip():
        return 'Write-Output "Usage: cut OPTION... [FILE]..."'
    parts = _parse_command_line(cmd)
    if not parts:
        return 'Write-Output "Usage: cut OPTION... [FILE]..."'
    if parts[0] in ('cut', '/bin/cut', '/usr/bin/cut'):
        parts = parts[1:]
    if not parts:
        return 'Write-Output "Usage: cut OPTION... [FILE]..."'
    mode: Optional[str] = None
    list_str: Optional[str] = None
    delimiter = '\t'
    output_delimiter: Optional[str] = None
    complement = False
    only_delimited = False
    zero_terminated = False
    show_help = False
    show_version = False
    files: List[str] = []
    i = 0
    while i < len(parts):
        part = parts[i]
        part = _convert_slash_to_dash(part)
        if part == '--':
            files.extend(parts[i + 1:])
            break
        if part.startswith('--'):
            long_opt = part[2:]
            if long_opt == 'help':
                show_help = True
                i += 1
                continue
            if long_opt == 'version':
                show_version = True
                i += 1
                continue
            if long_opt == 'complement':
                complement = True
                i += 1
                continue
            if long_opt == 'only-delimited':
                only_delimited = True
                i += 1
                continue
            if long_opt == 'zero-terminated':
                zero_terminated = True
                i += 1
                continue
            if '=' in long_opt:
                opt_name, opt_value = long_opt.split('=', 1)
                if opt_name == 'bytes':
                    mode = 'bytes'
                    list_str = opt_value
                elif opt_name == 'characters':
                    mode = 'chars'
                    list_str = opt_value
                elif opt_name == 'fields':
                    mode = 'fields'
                    list_str = opt_value
                elif opt_name == 'delimiter':
                    delimiter = opt_value
                elif opt_name == 'output-delimiter':
                    output_delimiter = opt_value
                i += 1
                continue
            i += 1
            continue
        if part.startswith('-') and len(part) > 1:
            opt_chars = part[1:]
            j = 0
            while j < len(opt_chars):
                char = opt_chars[j]
                if char == 'b':
                    mode = 'bytes'
                    if j + 1 < len(opt_chars):
                        list_str = opt_chars[j + 1:]
                        break
                    elif i + 1 < len(parts):
                        i += 1
                        list_str = parts[i]
                    j += 1
                elif char == 'c':
                    mode = 'chars'
                    if j + 1 < len(opt_chars):
                        list_str = opt_chars[j + 1:]
                        break
                    elif i + 1 < len(parts):
                        i += 1
                        list_str = parts[i]
                    j += 1
                elif char == 'd':
                    if j + 1 < len(opt_chars):
                        delimiter = opt_chars[j + 1:]
                        break
                    elif i + 1 < len(parts):
                        i += 1
                        delimiter = parts[i]
                        if (delimiter.startswith('"') and delimiter.endswith('"')) or \
                           (delimiter.startswith("'") and delimiter.endswith("'")):
                            delimiter = delimiter[1:-1]
                    j += 1
                elif char == 'f':
                    mode = 'fields'
                    if j + 1 < len(opt_chars):
                        list_str = opt_chars[j + 1:]
                        break
                    elif i + 1 < len(parts):
                        i += 1
                        list_str = parts[i]
                    j += 1
                elif char == 'n':
                    j += 1
                elif char == 's':
                    only_delimited = True
                    j += 1
                elif char == 'z':
                    zero_terminated = True
                    j += 1
                else:
                    j += 1
            i += 1
            continue
        files.append(part)
        i += 1
    if show_help:
        return (
            'Write-Output "cut - remove sections from each line of files\n'
            'Usage: cut OPTION... [FILE]...\n'
            'Print selected parts of lines from each FILE to standard output.\n'
            'With no FILE, or when FILE is -, read standard input.\n\n'
            'Mandatory arguments to long options are mandatory for short options too.\n'
            '  -b, --bytes=LIST        select only these bytes\n'
            '  -c, --characters=LIST   select only these characters\n'
            '  -d, --delimiter=DELIM   use DELIM instead of TAB for field delimiter\n'
            '  -f, --fields=LIST       select only these fields; also print any line\n'
            '                           that contains no delimiter character, unless\n'
            '                           the -s option is specified\n'
            '  -n                      (ignored)\n'
            '      --complement        complement the set of selected bytes, characters or fields\n'
            '  -s, --only-delimited    do not print lines not containing delimiters\n'
            '      --output-delimiter=STRING\n'
            '                           use STRING as the output delimiter\n'
            '                           the default is to use the input delimiter\n'
            '  -z, --zero-terminated   line delimiter is NUL, not newline\n'
            '      --help              display this help and exit\n'
            '      --version           output version information and exit\n\n'
            'Use one, and only one of -b, -c or -f.\n'
            'Each LIST is made up of one range, or many ranges separated by commas.\n'
            'Selected input is written in the same order that it is read, and is\n'
            'written exactly once.\n'
            'Each range is one of:\n'
            '  N     N\'th byte, character or field, counted from 1\n'
            '  N-    from N\'th byte, character or field, to end of line\n'
            '  N-M   from N\'th to M\'th (included) byte, character or field\n'
            '  -M    from first to M\'th (included) byte, character or field"'
        )
    if show_version:
        return 'Write-Output "cut (GNU coreutils) 8.32"'
    if mode is None:
        return 'Write-Error "cut: you must specify a list of bytes, characters, or fields"'
    if list_str is None:
        return 'Write-Error "cut: option requires an argument"'
    ranges = _parse_list(list_str)
    if not ranges:
        return 'Write-Error "cut: invalid range"'
    return _build_cut_powershell_command(
        mode, ranges, delimiter, output_delimiter,
        complement, only_delimited, zero_terminated, files
    )
if __name__ == "__main__":
    test_cases = [
        "cut -f 1 file.txt",
        "cut -f 1,3,5 file.txt",
        "cut -f 1-3 file.txt",
        "cut -f 3- file.txt",
        "cut -f -3 file.txt",
        "cut -d ',' -f 1,3 file.txt",
        "cut -d',' -f1,3 file.txt",
        "cut -c 1-5 file.txt",
        "cut -c 1,3,5 file.txt",
        "cut -b 1-10 file.txt",
        "cut -s -f 2 file.txt",
        "cut --complement -f 1 file.txt",
        "cut --output-delimiter='|' -f 1,2 file.txt",
        "cut /f 1 file.txt",
        "cut /d ',' /f 1 file.txt",
        "cut --fields=1,2 --delimiter=',' file.txt",
        "cut -f 1 -",
        "cut --help",
        "cut --version",
    ]
    for test in test_cases:
        result = _convert_cut(test)
        print(f"Input:  {test}")
        print(f"Output: {result}")
        print()
def _convert_date(cmd: str) -> str:
    if not cmd or not cmd.strip():
        return 'Get-Date'
    parts = _parse_command_line(cmd)
    if not parts:
        return 'Get-Date'
    if parts[0] in ('date', '/bin/date', '/usr/bin/date'):
        parts = parts[1:]
    if not parts:
        return 'Get-Date'
    date_string: Optional[str] = None
    file_path: Optional[str] = None
    iso_format: Optional[str] = None
    rfc_email = False
    reference_file: Optional[str] = None
    set_string: Optional[str] = None
    utc_mode = False
    show_help = False
    show_version = False
    format_string: Optional[str] = None
    i = 0
    while i < len(parts):
        part = parts[i]
        if part == '--':
            i += 1
            if i < len(parts):
                remaining = parts[i]
                if remaining.startswith('+'):
                    format_string = remaining[1:]
            break
        if part.startswith('/') and len(part) >= 2 and part[1].isalpha():
            if len(part) == 2:
                part = '-' + part[1:]
            else:
                sub_part = part[1:]
                if '=' in sub_part:
                    part = '--' + sub_part
                elif sub_part in ('date', 'file', 'iso-8601', 'reference', 'set',
                                  'utc', 'universal', 'help', 'version', 'rfc-email'):
                    part = '--' + sub_part
                else:
                    part = '-' + sub_part
        if part.startswith('+'):
            format_string = part[1:]
            i += 1
            continue
        if part.startswith('--'):
            long_opt = part[2:]
            if '=' in long_opt:
                opt_name, opt_value = long_opt.split('=', 1)
                if opt_name == 'date':
                    date_string = opt_value
                elif opt_name == 'file':
                    file_path = opt_value
                elif opt_name == 'iso-8601':
                    iso_format = opt_value if opt_value else 'date'
                elif opt_name == 'reference':
                    reference_file = opt_value
                elif opt_name == 'set':
                    set_string = opt_value
                i += 1
                continue
            if long_opt == 'help':
                show_help = True
                i += 1
                continue
            elif long_opt == 'version':
                show_version = True
                i += 1
                continue
            elif long_opt == 'date':
                if i + 1 < len(parts):
                    i += 1
                    date_string = parts[i]
                i += 1
                continue
            elif long_opt == 'file':
                if i + 1 < len(parts):
                    i += 1
                    file_path = parts[i]
                i += 1
                continue
            elif long_opt == 'iso-8601':
                iso_format = 'date'
                i += 1
                continue
            elif long_opt == 'rfc-email':
                rfc_email = True
                i += 1
                continue
            elif long_opt == 'reference':
                if i + 1 < len(parts):
                    i += 1
                    reference_file = parts[i]
                i += 1
                continue
            elif long_opt == 'set':
                if i + 1 < len(parts):
                    i += 1
                    set_string = parts[i]
                i += 1
                continue
            elif long_opt in ('utc', 'universal'):
                utc_mode = True
                i += 1
                continue
            i += 1
            continue
        if part.startswith('-') and len(part) > 1:
            opt_chars = part[1:]
            j = 0
            while j < len(opt_chars):
                char = opt_chars[j]
                if char == 'd':
                    if j + 1 < len(opt_chars):
                        date_string = opt_chars[j + 1:]
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                        date_string = parts[i]
                    j += 1
                elif char == 'f':
                    if j + 1 < len(opt_chars):
                        file_path = opt_chars[j + 1:]
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                        file_path = parts[i]
                    j += 1
                elif char == 'I':
                    iso_format = 'date'
                    if j + 1 < len(opt_chars):
                        remaining = opt_chars[j + 1:]
                        if remaining.startswith('hours') or remaining == 'h':
                            iso_format = 'h'
                            j = len(opt_chars)
                        elif remaining.startswith('minutes') or remaining == 'm':
                            iso_format = 'm'
                            j = len(opt_chars)
                        elif remaining.startswith('seconds') or remaining == 's':
                            iso_format = 's'
                            j = len(opt_chars)
                        elif remaining[0] in ('h', 'm', 's'):
                            iso_format = remaining[0]
                            j += 1
                    j += 1
                elif char == 'R':
                    rfc_email = True
                    j += 1
                elif char == 'r':
                    if j + 1 < len(opt_chars):
                        reference_file = opt_chars[j + 1:]
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                        reference_file = parts[i]
                    j += 1
                elif char == 's':
                    if j + 1 < len(opt_chars):
                        set_string = opt_chars[j + 1:]
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                        set_string = parts[i]
                    j += 1
                elif char == 'u':
                    utc_mode = True
                    j += 1
                else:
                    j += 1
            i += 1
            continue
        if part.startswith('+'):
            format_string = part[1:]
        i += 1
    if show_help:
        help_text = (
            'Write-Output "Usage: date [OPTION]... [+FORMAT]\n'
            '  or:  date [-u|--utc|--universal] [MMDDhhmm[[CC]YY][.ss]]\n'
            'Display the current time in the given FORMAT, or set the system date.\n\n'
            'Mandatory arguments to long options are mandatory for short options too.\n'
            '  -d, --date=STRING          display time described by STRING, not now\n'
            '  -f, --file=DATEFILE        like --date; process each line of DATEFILE\n'
            '  -I[FMT], --iso-8601[=FMT]  output date/time in ISO 8601 format.\n'
            '                               FMT=date for date only (the default),\n'
            '                               hours, minutes, seconds, or ns\n'
            '                               for date and time to the indicated precision.\n'
            '  -R, --rfc-email            output date and time in RFC 5322 format.\n'
            '                               Example: Mon, 14 Aug 2006 02:34:56 -0600\n'
            '  -r, --reference=FILE       display the last modification time of FILE\n'
            '  -s, --set=STRING           set time described by STRING\n'
            '  -u, --utc, --universal     print or set Coordinated Universal Time (UTC)\n'
            '      --help                 display this help and exit\n'
            '      --version              output version information and exit\n\n'
            'FORMAT controls the output.  Interpreted sequences are:\n\n'
            '  %%   a literal %\n'
            '  %a   locale abbreviated weekday name (e.g., Sun)\n'
            '  %A   locale full weekday name (e.g., Sunday)\n'
            '  %b   locale abbreviated month name (e.g., Jan)\n'
            '  %B   locale full month name (e.g., January)\n'
            '  %c   locale date and time (e.g., Thu Mar  3 23:05:25 2005)\n'
            '  %C   century; like %Y but omit last two digits (e.g., 20)\n'
            '  %d   day of month (e.g., 01)\n'
            '  %D   date; same as %m/%d/%y\n'
            '  %e   day of month, space padded; same as %_d\n'
            '  %F   full date; same as %Y-%m-%d\n'
            '  %H   hour (00..23)\n'
            '  %I   hour (01..12)\n'
            '  %j   day of year (001..366)\n'
            '  %k   hour, space padded ( 0..23); same as %_H\n'
            '  %l   hour, space padded ( 1..12); same as %_I\n'
            '  %m   month (01..12)\n'
            '  %M   minute (00..59)\n'
            '  %n   a newline\n'
            '  %N   nanoseconds (000000000..999999999)\n'
            '  %p   locale equivalent of either AM or PM; blank if not known\n'
            '  %P   like %p, but lower case\n'
            '  %r   locale 12-hour clock time (e.g., 11:11:04 PM)\n'
            '  %R   24-hour hour and minute; same as %H:%M\n'
            '  %s   seconds since 1970-01-01 00:00:00 UTC\n'
            '  %S   second (00..60)\n'
            '  %t   a tab\n'
            '  %T   time; same as %H:%M:%S\n'
            '  %u   day of week (1..7); 1 is Monday\n'
            '  %U   week number of year, with Sunday as first day of week (00..53)\n'
            '  %V   ISO week number, with Monday as first day of week (01..53)\n'
            '  %w   day of week (0..6); 0 is Sunday\n'
            '  %W   week number of year, with Monday as first day of week (00..53)\n'
            '  %x   locale date representation (e.g., 12/31/99)\n'
            '  %X   locale time representation (e.g., 23:13:48)\n'
            '  %y   last two digits of year (00..99)\n'
            '  %Y   year\n'
            '  %z   +hhmm numeric time zone (e.g., -0400)\n'
            '  %Z   alphabetic time zone abbreviation (e.g., EDT)\n\n'
            'By default, date pads numeric fields with zeroes.\n'
            'After any flags comes an optional field width, as a decimal number;\n'
            'then an optional modifier, which is either E to use the locale\n'
            'alternate representations if available, or O to use the locale\n'
            'alternate numeric symbols if available."'
        )
        return help_text
    if show_version:
        return 'Write-Output "date (GNU coreutils) 8.32"'
    if set_string:
        ps_date = _parse_date_string(set_string)
        if utc_mode:
            return f'Set-Date -Date "{ps_date}" -Adjust'
        else:
            return f'Set-Date -Date "{ps_date}" -Adjust'
    if reference_file:
        escaped_path = reference_file.replace('"', '`"')
        return f'(Get-Item "{escaped_path}").LastWriteTime'
    if file_path:
        escaped_path = file_path.replace('"', '`"')
        return (
            f'Get-Content "{escaped_path}" | ForEach-Object {{ '
            f'Get-Date -Date $_ }}'
        )
    ps_cmd = 'Get-Date'
    params: List[str] = []
    if date_string:
        parsed_date = _parse_date_string(date_string)
        params.append(f'-Date "{parsed_date}"')
    if utc_mode:
        params.append('-AsUTC')
    if format_string:
        ps_format = _convert_format_string(format_string)
        params.append(f'-Format "{ps_format}"')
    elif iso_format:
        if iso_format == 'h':
            params.append('-Format "yyyy-MM-ddTHH"')
        elif iso_format == 'm':
            params.append('-Format "yyyy-MM-ddTHH:mm"')
        elif iso_format == 's':
            params.append('-Format "yyyy-MM-ddTHH:mm:ss"')
        else:
            params.append('-Format "yyyy-MM-dd"')
    elif rfc_email:
        params.append('-Format "r"')
    if params:
        ps_cmd += ' ' + ' '.join(params)
    return ps_cmd
def _parse_date_string(date_str: str) -> str:
    date_str_lower = date_str.lower()
    if date_str_lower in ('now', 'today'):
        return date_str
    if date_str_lower == 'yesterday':
        return (date_str)
    if date_str_lower == 'tomorrow':
        return (date_str)
    relative_pattern = re.compile(
        r'^(\d+)\s+(second|minute|hour|day|week|month|year)s?\s+ago$',
        re.IGNORECASE
    )
    match = relative_pattern.match(date_str)
    if match:
        return date_str
    offset_pattern = re.compile(
        r'^([+-]\d+)\s+(second|minute|hour|day|week|month|year)s?$',
        re.IGNORECASE
    )
    match = offset_pattern.match(date_str)
    if match:
        return date_str
    return date_str
def _convert_format_string(fmt: str) -> str:
    format_mapping = {
        '%Y': 'yyyy',
        '%y': 'yy',
        '%m': 'MM',
        '%d': 'dd',
        '%H': 'HH',
        '%I': 'hh',
        '%M': 'mm',
        '%S': 'ss',
        '%p': 'tt',
        '%A': 'dddd',
        '%a': 'ddd',
        '%B': 'MMMM',
        '%b': 'MMM',
        '%j': 'ddd',
        '%U': 'ww',
        '%W': 'ww',
        '%w': 'ddd',
        '%u': 'ddd',
        '%Z': 'zzz',
        '%z': 'zzz',
        '%n': '\n',
        '%t': '\t',
        '%%': '%',
    }
    composite_formats = {
        '%D': 'MM/dd/yy',
        '%F': 'yyyy-MM-dd',
        '%R': 'HH:mm',
        '%T': 'HH:mm:ss',
        '%r': 'hh:mm:ss tt',
        '%c': 'ddd MMM dd HH:mm:ss yyyy',
        '%x': 'MM/dd/yyyy',
        '%X': 'HH:mm:ss',
    }
    result = fmt
    for bash_fmt, ps_fmt in composite_formats.items():
        result = result.replace(bash_fmt, ps_fmt)
    for bash_fmt, ps_fmt in format_mapping.items():
        result = result.replace(bash_fmt, ps_fmt)
    result = re.sub(r'%([a-zA-Z])', r'\1', result)
    return result
def _convert_df(cmd: str) -> str:
    if not cmd or not cmd.strip():
        return 'Get-Volume'
    parts = _parse_command_line(cmd)
    if not parts:
        return 'Get-Volume'
    if parts[0] in ('df', '/bin/df', '/usr/bin/df'):
        parts = parts[1:]
    if not parts:
        return 'Get-Volume'
    show_all = False
    block_size: Optional[str] = None
    human_readable = False
    si_units = False
    inodes = False
    local_only = False
    no_sync = False
    portability = False
    sync_before = False
    show_total = False
    print_type = False
    show_help = False
    show_version = False
    fs_types: List[str] = []
    exclude_types: List[str] = []
    output_fields: Optional[str] = None
    paths: List[str] = []
    i = 0
    while i < len(parts):
        part = parts[i]
        if part == '--':
            paths.extend(parts[i + 1:])
            break
        if part.startswith('/') and len(part) >= 2:
            if len(part) == 2 and part[1].isalpha():
                part = '-' + part[1:]
            elif len(part) > 2 and part[1].isalpha():
                sub_part = part[1:]
                known_long_opts = {
                    'all', 'help', 'version', 'human-readable', 'si',
                    'inodes', 'local', 'no-sync', 'portability',
                    'sync', 'total', 'print-type', 'type',
                    'exclude-type', 'output', 'block-size'
                }
                if '=' in sub_part:
                    opt_name = sub_part.split('=', 1)[0]
                    if opt_name in known_long_opts or opt_name in ('type', 'exclude-type', 'block-size', 'output'):
                        part = '--' + sub_part
                elif sub_part in known_long_opts:
                    part = '--' + sub_part
                elif all(c.isalpha() and c.islower() for c in sub_part) and len(sub_part) <= 3:
                    part = '-' + sub_part
        if part.startswith('--'):
            long_opt = part[2:]
            if long_opt == 'help':
                show_help = True
                i += 1
                continue
            if long_opt == 'version':
                show_version = True
                i += 1
                continue
            if long_opt == 'all':
                show_all = True
                i += 1
                continue
            if long_opt == 'human-readable':
                human_readable = True
                i += 1
                continue
            if long_opt == 'si':
                si_units = True
                i += 1
                continue
            if long_opt == 'inodes':
                inodes = True
                i += 1
                continue
            if long_opt == 'local':
                local_only = True
                i += 1
                continue
            if long_opt == 'no-sync':
                no_sync = True
                i += 1
                continue
            if long_opt == 'portability':
                portability = True
                i += 1
                continue
            if long_opt == 'sync':
                sync_before = True
                i += 1
                continue
            if long_opt == 'total':
                show_total = True
                i += 1
                continue
            if long_opt == 'print-type':
                print_type = True
                i += 1
                continue
            if long_opt.startswith('block-size='):
                block_size = long_opt.split('=', 1)[1]
                i += 1
                continue
            if long_opt.startswith('type='):
                fs_types.append(long_opt.split('=', 1)[1])
                i += 1
                continue
            if long_opt.startswith('exclude-type='):
                exclude_types.append(long_opt.split('=', 1)[1])
                i += 1
                continue
            if long_opt == 'output':
                output_fields = 'all'
                i += 1
                continue
            elif long_opt.startswith('output='):
                output_fields = long_opt.split('=', 1)[1]
                i += 1
                continue
            i += 1
            continue
        if part.startswith('-') and len(part) > 1:
            opt_chars = part[1:]
            j = 0
            while j < len(opt_chars):
                char = opt_chars[j]
                if char == 'a':
                    show_all = True
                    j += 1
                elif char == 'B':
                    if j + 1 < len(opt_chars):
                        block_size = opt_chars[j + 1:]
                        break
                    elif i + 1 < len(parts):
                        i += 1
                        block_size = parts[i]
                    j += 1
                elif char == 'h':
                    human_readable = True
                    j += 1
                elif char == 'H':
                    si_units = True
                    j += 1
                elif char == 'i':
                    inodes = True
                    j += 1
                elif char == 'k':
                    block_size = '1K'
                    j += 1
                elif char == 'l':
                    local_only = True
                    j += 1
                elif char == 'P':
                    portability = True
                    j += 1
                elif char == 't':
                    if j + 1 < len(opt_chars):
                        fs_types.append(opt_chars[j + 1:])
                        break
                    elif i + 1 < len(parts):
                        i += 1
                        fs_types.append(parts[i])
                    j += 1
                elif char == 'T':
                    print_type = True
                    j += 1
                elif char == 'v':
                    j += 1
                elif char == 'x':
                    if j + 1 < len(opt_chars):
                        exclude_types.append(opt_chars[j + 1:])
                        break
                    elif i + 1 < len(parts):
                        i += 1
                        exclude_types.append(parts[i])
                    j += 1
                else:
                    j += 1
            i += 1
            continue
        paths.append(part)
        i += 1
    return _build_df_powershell_command(
        show_all, block_size, human_readable, si_units, inodes,
        local_only, no_sync, portability, sync_before, show_total,
        print_type, show_help, show_version, fs_types, exclude_types,
        output_fields, paths
    )
def _build_df_powershell_command(
    show_all: bool,
    block_size: Optional[str],
    human_readable: bool,
    si_units: bool,
    inodes: bool,
    local_only: bool,
    no_sync: bool,
    portability: bool,
    sync_before: bool,
    show_total: bool,
    print_type: bool,
    show_help: bool,
    show_version: bool,
    fs_types: List[str],
    exclude_types: List[str],
    output_fields: Optional[str],
    paths: List[str]
) -> str:
    if show_help:
        return ('Write-Output "df - Report file system disk space usage\n'
                'Usage: df [OPTION]... [FILE]...\n'
                'Options:\n'
                '  -a, --all             include pseudo, duplicate, inaccessible file systems\n'
                '  -B, --block-size=SIZE scale sizes by SIZE before printing\n'
                '  -h, --human-readable  print sizes in powers of 1024\n'
                '  -H, --si              print sizes in powers of 1000\n'
                '  -i, --inodes          list inode information instead of block usage\n'
                '  -k                    like --block-size=1K\n'
                '  -l, --local           limit listing to local file systems\n'
                '  -P, --portability     use the POSIX output format\n'
                '  -t, --type=TYPE       limit listing to file systems of type TYPE\n'
                '  -T, --print-type      print file system type\n'
                '  -x, --exclude-type=TYPE  limit listing to file systems not of type TYPE\n'
                '      --total           produce a grand total\n'
                '      --help            display this help\n'
                '      --version         output version information"')
    if show_version:
        return 'Write-Output "df (GNU coreutils) 8.32"'
    base_cmd = 'Get-Volume'
    filters: List[str] = []
    if local_only:
        filters.append('$_.DriveType -eq "Fixed"')
    if paths:
        path_conditions = []
        for path in paths:
            if len(path) == 1 and path.isalpha():
                path_conditions.append(f'$_.DriveLetter -eq "{path.upper()}"')
            elif len(path) == 2 and path[1] == ':' and path[0].isalpha():
                path_conditions.append(f'$_.DriveLetter -eq "{path[0].upper()}"')
            elif path.startswith('/'):
                path_escaped = path.replace("'", "''")
                path_conditions.append(f"$_.Path -like '*{path_escaped}*' -or $_.DriveLetter -eq 'C'")
            else:
                path_escaped = path.replace("'", "''")
                path_conditions.append(f"$_.Path -like '*{path_escaped}*' -or $_.FileSystemLabel -like '*{path_escaped}*'")
        if path_conditions:
            filters.append('(' + ' -or '.join(path_conditions) + ')')
    if fs_types:
        type_conditions = []
        for fs_type in fs_types:
            fs_type_escaped = fs_type.replace("'", "''")
            type_conditions.append(f"$_.FileSystemType -like '*{fs_type_escaped}*'")
        if type_conditions:
            filters.append('(' + ' -or '.join(type_conditions) + ')')
    exclude_conditions = []
    if exclude_types:
        for ex_type in exclude_types:
            ex_type_escaped = ex_type.replace("'", "''")
            exclude_conditions.append(f"$_.FileSystemType -notlike '*{ex_type_escaped}*'")
    all_conditions = filters + exclude_conditions
    if all_conditions:
        base_cmd += ' | Where-Object { ' + ' -and '.join(all_conditions) + ' }'
    if output_fields or print_type or inodes:
        select_fields = []
        if output_fields:
            if output_fields == 'all':
                select_fields = ['DriveLetter', 'FileSystemType', 'FileSystemLabel',
                                'Size', 'SizeRemaining', 'DriveType']
            else:
                field_mapping = {
                    'source': 'Path',
                    'fstype': 'FileSystemType',
                    'size': 'Size',
                    'used': 'SizeUsed',
                    'avail': 'SizeRemaining',
                    'pcent': 'SizeRemainingPercent',
                    'target': 'Path',
                    'file': 'FileSystemLabel',
                }
                for field in output_fields.split(','):
                    field = field.strip()
                    if field in field_mapping:
                        select_fields.append(field_mapping[field])
        if print_type and 'FileSystemType' not in select_fields:
            select_fields.append('FileSystemType')
        if inodes:
            if 'FileSystemLabel' not in select_fields:
                select_fields.append('FileSystemLabel')
        if select_fields:
            base_cmd += ' | Select-Object ' + ', '.join(select_fields)
    if show_total:
        base_cmd += (' | ForEach-Object { $_; $total += $_.Size; '
                    '$used += ($_.Size - $_.SizeRemaining) } '
                    '-Begin { $total = 0; $used = 0 } '
                    '-End { [PSCustomObject]@{ DriveLetter = "total"; '
                    'Size = $total; SizeUsed = $used; '
                    'SizeRemaining = $total - $used } }')
    if human_readable or si_units:
        base_cmd += ' | Format-Table -AutoSize'
    if portability:
        base_cmd += (' | Format-Table -Property DriveLetter, FileSystemType, '
                    'Size, SizeRemaining, @{Name="Capacity"; '
                    'Expression={[math]::Round(($_.Size - $_.SizeRemaining) / '
                    '$_.Size * 100, 2)}} -AutoSize')
    return base_cmd
def _convert_diff(cmd: str) -> str:
    if not cmd or not cmd.strip():
        return 'Compare-Object'
    parts = _parse_command_line(cmd)
    if not parts:
        return 'Compare-Object'
    if parts[0] in ('diff', '/bin/diff', '/usr/bin/diff'):
        parts = parts[1:]
    if not parts:
        return 'Compare-Object'
    ignore_case = False
    ignore_all_space = False
    ignore_space_change = False
    ignore_blank_lines = False
    unified = None
    context = None
    brief = False
    report_identical = False
    side_by_side = False
    left_column = False
    suppress_common = False
    recursive = False
    new_file = False
    text = False
    minimal = False
    show_help = False
    show_version = False
    from_file: Optional[str] = None
    to_file: Optional[str] = None
    files: List[str] = []
    i = 0
    while i < len(parts):
        part = parts[i]
        if part == '--':
            files.extend(parts[i + 1:])
            break
        if part.startswith('/') and len(part) >= 2:
            if len(part) == 2 and part[1].isalpha():
                part = '-' + part[1:]
            elif len(part) > 2 and part[1].isalpha():
                part = '--' + part[1:]
        if part.startswith('--'):
            long_opt = part[2:]
            if long_opt == 'help':
                show_help = True
                i += 1
                continue
            if long_opt == 'version':
                show_version = True
                i += 1
                continue
            if long_opt == 'ignore-case':
                ignore_case = True
                i += 1
                continue
            if long_opt == 'ignore-all-space':
                ignore_all_space = True
                i += 1
                continue
            if long_opt == 'ignore-space-change':
                ignore_space_change = True
                i += 1
                continue
            if long_opt == 'ignore-blank-lines':
                ignore_blank_lines = True
                i += 1
                continue
            if long_opt == 'brief':
                brief = True
                i += 1
                continue
            if long_opt == 'report-identical-files':
                report_identical = True
                i += 1
                continue
            if long_opt == 'side-by-side':
                side_by_side = True
                i += 1
                continue
            if long_opt == 'left-column':
                left_column = True
                i += 1
                continue
            if long_opt == 'suppress-common-lines':
                suppress_common = True
                i += 1
                continue
            if long_opt == 'recursive':
                recursive = True
                i += 1
                continue
            if long_opt == 'new-file':
                new_file = True
                i += 1
                continue
            if long_opt == 'text':
                text = True
                i += 1
                continue
            if long_opt == 'minimal':
                minimal = True
                i += 1
                continue
            if long_opt.startswith('from-file='):
                from_file = long_opt.split('=', 1)[1]
                i += 1
                continue
            if long_opt.startswith('to-file='):
                to_file = long_opt.split('=', 1)[1]
                i += 1
                continue
            if '=' in long_opt:
                opt_name, opt_value = long_opt.split('=', 1)
                if opt_name == 'unified':
                    unified = int(opt_value) if opt_value.isdigit() else 3
                elif opt_name == 'context':
                    context = int(opt_value) if opt_value.isdigit() else 3
                i += 1
                continue
            if long_opt == 'unified':
                unified = 3
                i += 1
                continue
            if long_opt == 'context':
                context = 3
                i += 1
                continue
            i += 1
            continue
        if part.startswith('-') and len(part) > 1:
            opt_chars = part[1:]
            j = 0
            while j < len(opt_chars):
                char = opt_chars[j]
                if char == 'i':
                    ignore_case = True
                    j += 1
                elif char == 'w':
                    ignore_all_space = True
                    j += 1
                elif char == 'b':
                    ignore_space_change = True
                    j += 1
                elif char == 'B':
                    ignore_blank_lines = True
                    j += 1
                elif char == 'u':
                    if j + 1 < len(opt_chars) and opt_chars[j + 1:].isdigit():
                        unified = int(opt_chars[j + 1:])
                        break
                    elif i + 1 < len(parts) and parts[i + 1].isdigit():
                        i += 1
                        unified = int(parts[i])
                    else:
                        unified = 3
                    j += 1
                elif char == 'c':
                    if j + 1 < len(opt_chars) and opt_chars[j + 1:].isdigit():
                        context = int(opt_chars[j + 1:])
                        break
                    elif i + 1 < len(parts) and parts[i + 1].isdigit():
                        i += 1
                        context = int(parts[i])
                    else:
                        context = 3
                    j += 1
                elif char == 'U':
                    if j + 1 < len(opt_chars) and opt_chars[j + 1:].isdigit():
                        unified = int(opt_chars[j + 1:])
                        break
                    elif i + 1 < len(parts) and parts[i + 1].isdigit():
                        i += 1
                        unified = int(parts[i])
                    else:
                        unified = 3
                    j += 1
                elif char == 'C':
                    if j + 1 < len(opt_chars) and opt_chars[j + 1:].isdigit():
                        context = int(opt_chars[j + 1:])
                        break
                    elif i + 1 < len(parts) and parts[i + 1].isdigit():
                        i += 1
                        context = int(parts[i])
                    else:
                        context = 3
                    j += 1
                elif char == 'q':
                    brief = True
                    j += 1
                elif char == 's':
                    report_identical = True
                    j += 1
                elif char == 'y':
                    side_by_side = True
                    j += 1
                elif char == 'r':
                    recursive = True
                    j += 1
                elif char == 'N':
                    new_file = True
                    j += 1
                elif char == 'a':
                    text = True
                    j += 1
                elif char == 'd':
                    minimal = True
                    j += 1
                else:
                    j += 1
            i += 1
            continue
        files.append(part)
        i += 1
    return _build_diff_powershell_command(
        ignore_case, ignore_all_space, ignore_space_change, ignore_blank_lines,
        unified, context, brief, report_identical, side_by_side, left_column,
        suppress_common, recursive, new_file, text, minimal, show_help,
        show_version, from_file, to_file, files
    )
def _build_diff_powershell_command(
    ignore_case: bool,
    ignore_all_space: bool,
    ignore_space_change: bool,
    ignore_blank_lines: bool,
    unified: Optional[int],
    context: Optional[int],
    brief: bool,
    report_identical: bool,
    side_by_side: bool,
    left_column: bool,
    suppress_common: bool,
    recursive: bool,
    new_file: bool,
    text: bool,
    minimal: bool,
    show_help: bool,
    show_version: bool,
    from_file: Optional[str],
    to_file: Optional[str],
    files: List[str]
) -> str:
    if show_help:
        return ('Write-Output "diff - compare files line by line\n'
                'Usage: diff [OPTION]... FILES\n'
                'Options:\n'
                '  -i, --ignore-case           Ignore case differences\n'
                '  -w, --ignore-all-space      Ignore all white space\n'
                '  -b, --ignore-space-change   Ignore changes in amount of white space\n'
                '  -B, --ignore-blank-lines    Ignore changes where lines are all blank\n'
                '  -u, -U NUM, --unified[=NUM] Output NUM lines of unified context\n'
                '  -c, -C NUM, --context[=NUM] Output NUM lines of copied context\n'
                '  -q, --brief                 Report only when files differ\n'
                '  -s, --report-identical-files  Report when two files are the same\n'
                '  -y, --side-by-side          Output in two columns\n'
                '  -r, --recursive             Recursively compare subdirectories\n'
                '  -N, --new-file              Treat absent files as empty\n'
                '  -a, --text                  Treat all files as text\n'
                '  -d, --minimal               Try hard to find a smaller set of changes\n'
                '      --help                  Display help\n'
                '      --version               Output version information"')
    if show_version:
        return 'Write-Output "diff (GNU diffutils) 3.8"'
    notes: List[str] = []
    if unified is not None:
        notes.append(f'# NOTE: Unified diff format (-u {unified}) not directly supported in PowerShell')
    if context is not None:
        notes.append(f'# NOTE: Context diff format (-c {context}) not directly supported in PowerShell')
    if ignore_all_space:
        notes.append('# NOTE: --ignore-all-space not directly supported in PowerShell Compare-Object')
    if ignore_space_change:
        notes.append('# NOTE: --ignore-space-change not directly supported in PowerShell Compare-Object')
    if ignore_blank_lines:
        notes.append('# NOTE: --ignore-blank-lines not directly supported in PowerShell Compare-Object')
    if side_by_side:
        notes.append('# NOTE: --side-by-side not directly supported in PowerShell')
    if left_column:
        notes.append('# NOTE: --left-column not directly supported in PowerShell')
    if suppress_common:
        notes.append('# NOTE: --suppress-common-lines not directly supported in PowerShell')
    if recursive:
        notes.append('# NOTE: Recursive directory comparison not directly supported in PowerShell')
    if new_file:
        notes.append('# NOTE: --new-file not directly supported in PowerShell')
    if text:
        notes.append('# NOTE: --text option is default behavior in PowerShell')
    if minimal:
        notes.append('# NOTE: --minimal not directly supported in PowerShell')
    if from_file is not None:
        notes.append(f'# NOTE: --from-file={from_file} not directly supported in PowerShell')
    if to_file is not None:
        notes.append(f'# NOTE: --to-file={to_file} not directly supported in PowerShell')
    file1: Optional[str] = None
    file2: Optional[str] = None
    if len(files) >= 2:
        file1 = files[0]
        file2 = files[1]
    elif len(files) == 1:
        file1 = files[0]
    if file1 and ' ' in file1 and not (file1.startswith('"') or file1.startswith("'")):
        file1 = f'"{file1}"'
    if file2 and ' ' in file2 and not (file2.startswith('"') or file2.startswith("'")):
        file2 = f'"{file2}"'
    if file1 and file2:
        base_cmd = f'Compare-Object (Get-Content {file1}) (Get-Content {file2})'
    elif file1:
        base_cmd = f'Compare-Object (Get-Content {file1}) $input'
    else:
        base_cmd = 'Compare-Object'
    options: List[str] = []
    if ignore_case:
        options.append('-CaseSensitive:$false')
    if options:
        base_cmd += ' ' + ' '.join(options)
    if brief:
        if report_identical:
            base_cmd = f'if ({base_cmd}) {{ "Files differ" }} else {{ "Files are identical" }}'
        else:
            base_cmd = f'if ({base_cmd}) {{ "Files differ" }}'
    elif report_identical:
        base_cmd = f'if (-not ({base_cmd})) {{ "Files are identical" }} else {{ $result = {base_cmd}; $result }}'
    else:
        base_cmd += ' | Format-Table -AutoSize'
    if notes:
        return '; '.join(notes) + '; ' + base_cmd
    return base_cmd
if __name__ == "__main__":
    test_cases = [
        "diff file1.txt file2.txt",
        "diff -i file1.txt file2.txt",
        "diff --ignore-case file1.txt file2.txt",
        "diff -w file1.txt file2.txt",
        "diff -b file1.txt file2.txt",
        "diff -B file1.txt file2.txt",
        "diff -u file1.txt file2.txt",
        "diff -u5 file1.txt file2.txt",
        "diff -U 5 file1.txt file2.txt",
        "diff -c file1.txt file2.txt",
        "diff -q file1.txt file2.txt",
        "diff -s file1.txt file2.txt",
        "diff -q -s file1.txt file2.txt",
        "diff -y file1.txt file2.txt",
        "diff -r dir1 dir2",
        "diff -N file1.txt file2.txt",
        "diff -a file1.txt file2.txt",
        "diff -d file1.txt file2.txt",
        "diff /i file1.txt file2.txt",
        "diff /ignore-case file1.txt file2.txt",
        "diff --help",
        "diff --version",
        "diff",
        "diff -u -i file1.txt file2.txt",
        "diff --unified=10 file1.txt file2.txt",
        "diff --from-file=dir1 file2.txt",
        "diff --to-file=dir2 file1.txt",
    ]
    for test in test_cases:
        result = _convert_diff(test)
        print(f"Input:  {test}")
        print(f"Output: {result}")
        print()
def _convert_dig(cmd: str) -> str:
    if not cmd or not cmd.strip():
        return 'Write-Output "usage: dig [@server] [-b address] [-c class] [-f filename] [-k filename] [-m] [-p port#] [-q name] [-t type] [-x addr] [-y [hmac:]name:key] [[-4] | [-6]] [name] [type] [class] [queryopt...]"'
    parts = _parse_command_line(cmd)
    if not parts:
        return 'Write-Output "usage: dig [@server] [-b address] [-c class] [-f filename] [-k filename] [-m] [-p port#] [-q name] [-t type] [-x addr] [-y [hmac:]name:key] [[-4] | [-6]] [name] [type] [class] [queryopt...]"'
    if parts[0] in ('dig', '/usr/bin/dig', '/bin/dig'):
        parts = parts[1:]
    if not parts:
        return 'Write-Output "usage: dig [@server] [-b address] [-c class] [-f filename] [-k filename] [-m] [-p port#] [-q name] [-t type] [-x addr] [-y [hmac:]name:key] [[-4] | [-6]] [name] [type] [class] [queryopt...]"'
    options: Dict[str, Any] = {
        'server': None,
        'query_type': None,
        'query_class': None,
        'port': None,
        'source': None,
        'reverse': None,
        'filename': None,
        'keyfile': None,
        'tsig': None,
        'ipv4': False,
        'ipv6': False,
        'short': False,
        'trace': False,
        'recurse': True,
        'tcp': False,
        'time': None,
        'tries': None,
        'dnssec': False,
        'noall': False,
        'answer': False,
        'authority': False,
        'additional': False,
        'comments': True,
        'stats': True,
        'question': True,
        'help': False,
        'version': False,
    }
    target: Optional[str] = None
    VALID_QUERY_TYPES = {
        'A', 'AAAA', 'AFSDB', 'APL', 'CAA', 'CDNSKEY', 'CDS', 'CERT', 'CNAME',
        'CSYNC', 'DHCID', 'DLV', 'DNAME', 'DNSKEY', 'DS', 'EUI48', 'EUI64',
        'HINFO', 'HIP', 'HTTPS', 'IPSECKEY', 'KEY', 'KX', 'LOC', 'MX', 'NAPTR',
        'NS', 'NSEC', 'NSEC3', 'NSEC3PARAM', 'OPENPGPKEY', 'PTR', 'RP', 'RRSIG',
        'SIG', 'SMIMEA', 'SOA', 'SRV', 'SSHFP', 'SVCB', 'TA', 'TKEY', 'TLSA',
        'TSIG', 'TXT', 'URI', 'ZONEMD', 'ANY', 'AXFR', 'IXFR', 'OPT'
    }
    VALID_QUERY_CLASSES = {'IN', 'CS', 'CH', 'HS', 'ANY'}
    LONG_VALUE_OPTS = {'t', 'q', 'c', 'p', 'b', 'f', 'k', 'x', 'y'}
    i = 0
    while i < len(parts):
        part = parts[i]
        if part == '--':
            i += 1
            if i < len(parts):
                target = parts[i]
            break
        if part.startswith('/') and len(part) >= 2:
            opt_part = part[1:]
            if '=' in opt_part:
                opt_name = opt_part.split('=', 1)[0]
                if opt_name in LONG_VALUE_OPTS:
                    part = '-' + opt_part
                else:
                    part = '+' + opt_part
            elif opt_part in LONG_VALUE_OPTS:
                if i + 1 < len(parts) and not parts[i + 1].startswith('-') and not parts[i + 1].startswith('/'):
                    part = '-' + opt_part
                else:
                    part = '-' + opt_part
            elif len(opt_part) == 1 and opt_part in '46hvm':
                part = '-' + opt_part
            else:
                part = '+' + opt_part
        if part.startswith('@'):
            options['server'] = part[1:]
            i += 1
            continue
        if part.startswith('+'):
            opt_str = part[1:]
            if '=' in opt_str:
                opt_name, opt_value = opt_str.split('=', 1)
                if opt_name == 'time':
                    options['time'] = opt_value
                elif opt_name == 'timeout':
                    options['time'] = opt_value
                elif opt_name == 'tries':
                    options['tries'] = opt_value
                elif opt_name == 'retry':
                    options['tries'] = opt_value
                elif opt_name == 'port':
                    options['port'] = opt_value
                elif opt_name == 'type':
                    options['query_type'] = opt_value.upper()
                elif opt_name == 'class':
                    options['query_class'] = opt_value.upper()
                i += 1
                continue
            if opt_str.startswith('no'):
                opt_name = opt_str[2:]
                if opt_name == 'all':
                    options['noall'] = True
                    options['answer'] = False
                    options['authority'] = False
                    options['additional'] = False
                    options['comments'] = False
                    options['stats'] = False
                    options['question'] = False
                elif opt_name == 'short':
                    options['short'] = False
                elif opt_name == 'trace':
                    options['trace'] = False
                elif opt_name == 'recurse':
                    options['recurse'] = False
                elif opt_name == 'tcp':
                    options['tcp'] = False
                elif opt_name == 'dnssec':
                    options['dnssec'] = False
                elif opt_name == 'comments':
                    options['comments'] = False
                elif opt_name == 'stats':
                    options['stats'] = False
                elif opt_name == 'question':
                    options['question'] = False
                elif opt_name == 'answer':
                    options['answer'] = False
                elif opt_name == 'authority':
                    options['authority'] = False
                elif opt_name == 'additional':
                    options['additional'] = False
            else:
                if opt_str == 'short':
                    options['short'] = True
                elif opt_str == 'trace':
                    options['trace'] = True
                elif opt_str == 'recurse':
                    options['recurse'] = True
                elif opt_str == 'tcp':
                    options['tcp'] = True
                elif opt_str == 'dnssec':
                    options['dnssec'] = True
                elif opt_str == 'comments':
                    options['comments'] = True
                elif opt_str == 'stats':
                    options['stats'] = True
                elif opt_str == 'question':
                    options['question'] = True
                elif opt_str == 'answer':
                    options['answer'] = True
                elif opt_str == 'authority':
                    options['authority'] = True
                elif opt_str == 'additional':
                    options['additional'] = True
                elif opt_str == 'all':
                    options['noall'] = False
                    options['answer'] = True
                    options['authority'] = True
                    options['additional'] = True
                    options['comments'] = True
                    options['stats'] = True
                    options['question'] = True
            i += 1
            continue
        if (part.startswith('-') or part.startswith('--')) and '=' in part:
            if part.startswith('--'):
                opt_name, opt_value = part[2:].split('=', 1)
            else:
                opt_name, opt_value = part[1:].split('=', 1)
            if opt_name in ('t', 'type'):
                options['query_type'] = opt_value.upper()
                i += 1
                continue
            elif opt_name in ('q', 'query'):
                options['query_type'] = opt_value.upper()
                i += 1
                continue
            elif opt_name in ('c', 'class'):
                options['query_class'] = opt_value.upper()
                i += 1
                continue
            elif opt_name == 'p':
                options['port'] = opt_value
                i += 1
                continue
            elif opt_name == 'b':
                options['source'] = opt_value
                i += 1
                continue
            elif opt_name == 'f':
                options['filename'] = opt_value
                i += 1
                continue
            elif opt_name == 'k':
                options['keyfile'] = opt_value
                i += 1
                continue
            elif opt_name == 'x':
                options['reverse'] = opt_value
                i += 1
                continue
            elif opt_name == 'y':
                options['tsig'] = opt_value
                i += 1
                continue
        if part.startswith('--'):
            long_opt = part[2:]
            if long_opt == 'help':
                options['help'] = True
                i += 1
                continue
            elif long_opt == 'version':
                options['version'] = True
                i += 1
                continue
            elif long_opt in ('t', 'type'):
                if i + 1 < len(parts):
                    i += 1
                    options['query_type'] = parts[i].upper()
                i += 1
                continue
            elif long_opt in ('q', 'query'):
                if i + 1 < len(parts):
                    i += 1
                    options['query_type'] = parts[i].upper()
                i += 1
                continue
            elif long_opt in ('c', 'class'):
                if i + 1 < len(parts):
                    i += 1
                    options['query_class'] = parts[i].upper()
                i += 1
                continue
            elif long_opt == 'p':
                if i + 1 < len(parts):
                    i += 1
                    options['port'] = parts[i]
                i += 1
                continue
            elif long_opt == 'b':
                if i + 1 < len(parts):
                    i += 1
                    options['source'] = parts[i]
                i += 1
                continue
            elif long_opt == 'f':
                if i + 1 < len(parts):
                    i += 1
                    options['filename'] = parts[i]
                i += 1
                continue
            elif long_opt == 'k':
                if i + 1 < len(parts):
                    i += 1
                    options['keyfile'] = parts[i]
                i += 1
                continue
            elif long_opt == 'x':
                if i + 1 < len(parts):
                    i += 1
                    options['reverse'] = parts[i]
                i += 1
                continue
            elif long_opt == 'y':
                if i + 1 < len(parts):
                    i += 1
                    options['tsig'] = parts[i]
                i += 1
                continue
            elif long_opt == '4':
                options['ipv4'] = True
                i += 1
                continue
            elif long_opt == '6':
                options['ipv6'] = True
                i += 1
                continue
            i += 1
            continue
        if part.startswith('-') and len(part) > 1:
            opt_chars = part[1:]
            j = 0
            while j < len(opt_chars):
                char = opt_chars[j]
                if char == 'h':
                    options['help'] = True
                    j += 1
                elif char == 'v':
                    options['version'] = True
                    j += 1
                elif char == '4':
                    options['ipv4'] = True
                    j += 1
                elif char == '6':
                    options['ipv6'] = True
                    j += 1
                elif char == 'm':
                    j += 1
                elif char in ('t', 'q'):
                    if j + 1 < len(opt_chars):
                        options['query_type'] = opt_chars[j + 1:].upper()
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                        options['query_type'] = parts[i].upper()
                    j += 1
                elif char == 'c':
                    if j + 1 < len(opt_chars):
                        options['query_class'] = opt_chars[j + 1:].upper()
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                        options['query_class'] = parts[i].upper()
                    j += 1
                elif char == 'p':
                    if j + 1 < len(opt_chars):
                        options['port'] = opt_chars[j + 1:]
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                        options['port'] = parts[i]
                    j += 1
                elif char == 'b':
                    if j + 1 < len(opt_chars):
                        options['source'] = opt_chars[j + 1:]
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                        options['source'] = parts[i]
                    j += 1
                elif char == 'f':
                    if j + 1 < len(opt_chars):
                        options['filename'] = opt_chars[j + 1:]
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                        options['filename'] = parts[i]
                    j += 1
                elif char == 'k':
                    if j + 1 < len(opt_chars):
                        options['keyfile'] = opt_chars[j + 1:]
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                        options['keyfile'] = parts[i]
                    j += 1
                elif char == 'x':
                    if j + 1 < len(opt_chars):
                        options['reverse'] = opt_chars[j + 1:]
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                        options['reverse'] = parts[i]
                    j += 1
                elif char == 'y':
                    if j + 1 < len(opt_chars):
                        options['tsig'] = opt_chars[j + 1:]
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                        options['tsig'] = parts[i]
                    j += 1
                else:
                    j += 1
            i += 1
            continue
        if target is None:
            target = part
            i += 1
        else:
            if options['query_type'] is None and part.upper() in VALID_QUERY_TYPES:
                options['query_type'] = part.upper()
            elif options['query_class'] is None and part.upper() in VALID_QUERY_CLASSES:
                options['query_class'] = part.upper()
            i += 1
    if options['help']:
        return (
            'Write-Output "dig - DNS lookup utility\n'
            'Usage: dig [@server] [-b address] [-c class] [-f filename] [-k filename]\n'
            '           [-m] [-p port#] [-q name] [-t type] [-x addr] [-y [hmac:]name:key]\n'
            '           [[-4] | [-6]] [name] [type] [class] [queryopt...]\n\n'
            'Options:\n'
            '  @server             Query this server\n'
            '  -b address          Source address to query from\n'
            '  -c class            Query class (IN, CH, HS, etc.)\n'
            '  -f filename         Batch mode: read queries from file\n'
            '  -k filename         TSIG key file\n'
            '  -p port             Query port (default: 53)\n'
            '  -q name             Query name\n'
            '  -t type             Query type (A, MX, NS, SOA, TXT, etc.)\n'
            '  -x addr             Reverse lookup\n'
            '  -y [hmac:]name:key  TSIG key\n'
            '  -4                  Use IPv4 only\n'
            '  '
            '  -6                  Use IPv6 only\n'
            '  -h                  Show help\n'
            '  -v                  Show version\n\n'
            'Query options:\n'
            '  +short              Short output\n'
            '  +trace              Trace delegation path\n'
            '  +[no]recurse        Recursive query\n'
            '  +[no]tcp            Use TCP\n'
            '  +time=N             Query timeout\n'
            '  +tries=N            Number of retries\n'
            '  +[no]dnssec         Request DNSSEC records\n'
            '  +[no]all            Set/clear all display flags\n'
            '  +[no]answer         Display answer section\n'
            '  +[no]authority      Display authority section\n'
            '  +[no]additional     Display additional section\n'
            '  +[no]comments       Display comments\n'
            '  +[no]stats          Display statistics\n'
            '  +[no]question       Display question section"'
        )
    if options['version']:
        return 'Write-Output "DiG 9.16.1-Ubuntu"'
    if options['filename']:
        filename_escaped = options['filename'].replace('"', '`"')
        return f'# Batch mode: Get-Content "{filename_escaped}" | ForEach-Object {{ Resolve-DnsName $_ }}'
    ps_args: List[str] = []
    notes: List[str] = []
    if options['reverse']:
        addr = options['reverse']
        try:
            if '.' in addr and ':' not in addr:
                parts = addr.split('.')
                parts.reverse()
                ptr_name = '.'.join(parts) + '.in-addr.arpa'
                target = ptr_name
                options['query_type'] = 'PTR'
            elif ':' in addr:
                full_addr = _expand_ipv6(addr)
                if full_addr:
                    nibbles = list(full_addr.replace(':', ''))
                    nibbles.reverse()
                    ptr_name = '.'.join(nibbles) + '.ip6.arpa'
                    target = ptr_name
                    options['query_type'] = 'PTR'
                else:
                    target = addr
            else:
                target = addr
        except Exception:
            target = addr
    if target is None:
        return 'Write-Output "usage: dig [@server] [-b address] [-c class] [-f filename] [-k filename] [-m] [-p port#] [-q name] [-t type] [-x addr] [-y [hmac:]name:key] [[-4] | [-6]] [name] [type] [class] [queryopt...]"'
    ps_args.append(target)
    if options['server']:
        ps_args.append(f'-Server {options["server"]}')
    if options['query_type']:
        if options['query_type'] in VALID_QUERY_TYPES:
            ps_args.append(f'-Type {options["query_type"]}')
        else:
            ps_args.append(f'-Type {options["query_type"]}')
    if options['port']:
        notes.append(f'# NOTE: Port option (-p {options["port"]}) not directly supported in Resolve-DnsName')
    if options['tcp']:
        notes.append('# NOTE: TCP mode (+tcp) not directly supported in Resolve-DnsName')
    if not options['recurse']:
        notes.append('# NOTE: Non-recursive queries (+norecurse) not directly supported')
    if options['dnssec']:
        notes.append('# NOTE: DNSSEC (+dnssec) not directly supported in Resolve-DnsName')
    if options['trace']:
        notes.append('# NOTE: Trace (+trace) not directly supported in Resolve-DnsName')
    if options['source']:
        notes.append(f'# NOTE: Source address (-b {options["source"]}) not directly supported')
    if options['tsig']:
        notes.append('# NOTE: TSIG authentication (-y) not directly supported')
    if options['keyfile']:
        notes.append('# NOTE: TSIG key file (-k) not directly supported')
    if options['time']:
        notes.append(f'# NOTE: Timeout (+time={options["time"]}) not directly supported')
    if options['tries']:
        notes.append(f'# NOTE: Retry count (+tries={options["tries"]}) not directly supported')
    base_cmd = 'Resolve-DnsName ' + ' '.join(ps_args)
    if options['short']:
        if options['query_type'] == 'MX':
            base_cmd += ' | Select-Object -ExpandProperty NameExchange'
        elif options['query_type'] == 'NS':
            base_cmd += ' | Select-Object -ExpandProperty NameHost'
        elif options['query_type'] == 'CNAME':
            base_cmd += ' | Select-Object -ExpandProperty NameHost'
        elif options['query_type'] == 'PTR':
            base_cmd += ' | Select-Object -ExpandProperty NameHost'
        elif options['query_type'] == 'SOA':
            base_cmd += ' | Select-Object -ExpandProperty PrimaryServer'
        elif options['query_type'] == 'TXT':
            base_cmd += ' | Select-Object -ExpandProperty Strings'
        else:
            base_cmd += ' | Select-Object -ExpandProperty IPAddress'
    elif options['noall']:
        if options['answer'] and not (options['authority'] or options['additional']):
            base_cmd += ' | Select-Object IPAddress, NameHost, NameExchange, PrimaryServer, Strings'
        elif options['authority']:
            notes.append('# NOTE: Authority section filtering (+authority) not directly supported')
        elif options['additional']:
            notes.append('# NOTE: Additional section filtering (+additional) not directly supported')
        else:
            base_cmd = f'# +noall suppresses all output: Resolve-DnsName {target}' + (f' -Type {options["query_type"]}' if options['query_type'] else '')
    if not options['comments']:
        notes.append('# NOTE: Comment suppression (+nocomments) not directly supported')
    if not options['stats']:
        notes.append('# NOTE: Statistics suppression (+nostats) not directly supported')
    if notes:
        return '; '.join(notes + [base_cmd])
    return base_cmd
def _expand_ipv6(addr: str) -> Optional[str]:
    try:
        if '::' in addr:
            parts = addr.split('::')
            if len(parts) != 2:
                return None
            left = parts[0].split(':') if parts[0] else []
            right = parts[1].split(':') if parts[1] else []
            missing = 8 - len(left) - len(right)
            if missing < 0:
                return None
            full = left + ['0'] * missing + right
        else:
            full = addr.split(':')
        if len(full) != 8:
            return None
        expanded = ':'.join(p.zfill(4) for p in full)
        return expanded
    except Exception:
        return None
if __name__ == "__main__":
    test_cases = [
        "dig google.com",
        "dig 8.8.8.8",
        "dig @8.8.8.8 google.com",
        "dig @ns1.example.com example.com",
        "dig -t MX google.com",
        "dig -t A google.com",
        "dig -t NS google.com",
        "dig -t SOA google.com",
        "dig -t TXT google.com",
        "dig -t CNAME google.com",
        "dig -t AAAA google.com",
        "dig -t PTR google.com",
        "dig -t ANY google.com",
        "dig -q MX google.com",
        "dig --type=MX google.com",
        "dig -tMX google.com",
        "dig google.com MX",
        "dig google.com A",
        "dig -c IN google.com",
        "dig -c CH google.com",
        "dig --class=IN google.com",
        "dig google.com A IN",
        "dig -x 192.168.1.1",
        "dig -x 8.8.8.8",
        "dig -x2001:db8::1",
        "dig -p 53 google.com",
        "dig -p53 google.com",
        "dig --port=53 google.com",
        "dig -b 192.168.1.1 google.com",
        "dig -b192.168.1.1 google.com",
        "dig +short google.com",
        "dig +trace google.com",
        "dig +recurse google.com",
        "dig +norecurse google.com",
        "dig +tcp google.com",
        "dig +notcp google.com",
        "dig +dnssec google.com",
        "dig +nodnssec google.com",
        "dig +time=5 google.com",
        "dig +timeout=5 google.com",
        "dig +tries=3 google.com",
        "dig +retry=3 google.com",
        "dig +noall google.com",
        "dig +noall +answer google.com",
        "dig +noall +authority google.com",
        "dig +noall +additional google.com",
        "dig +nocomments google.com",
        "dig +nostats google.com",
        "dig +noquestion google.com",
        "dig +short +noall +answer google.com",
        "dig -4 google.com",
        "dig -6 google.com",
        "dig --4 google.com",
        "dig --6 google.com",
        "dig -f queries.txt",
        "dig -fqueries.txt",
        "dig -y hmac-sha256:keyname:secret google.com",
        "dig -k keyfile google.com",
        "dig @8.8.8.8 -t MX +short google.com",
        "dig @8.8.8.8 -p 53 -t A +norecurse google.com",
        "dig -x 192.168.1.1 +short",
        "dig /t MX google.com",
        "dig /x 192.168.1.1",
        "dig /p 53 google.com",
        "dig @8.8.8.8 /t A google.com",
        "dig /short google.com",
        "dig /trace google.com",
        "dig /4 google.com",
        "dig /help",
        "dig -h",
        "dig --help",
        "dig -v",
        "dig --version",
        "",
        "dig",
    ]
    for test in test_cases:
        result = _convert_dig(test)
        print(f"Input:  {test}")
        print(f"Output: {result}")
        print()
def _convert_dirname(cmd: str) -> str:
    if not cmd or not cmd.strip():
        return 'Write-Output "dirname: missing operand"'
    parts = _parse_command_line(cmd)
    if not parts:
        return 'Write-Output "dirname: missing operand"'
    if parts[0] in ('dirname', '/bin/dirname', '/usr/bin/dirname'):
        parts = parts[1:]
    if not parts:
        return 'Write-Output "dirname: missing operand"'
    known_long_options = {'help', 'version', 'zero'}
    zero_terminated = False
    show_help = False
    show_version = False
    i = 0
    while i < len(parts):
        part = parts[i]
        if part == '--':
            i += 1
            break
        if part.startswith('/') and len(part) >= 2:
            if len(part) == 2 and part[1].isalpha():
                part = '-' + part[1:]
            elif len(part) > 2 and part[1].isalpha():
                potential_opt = part[1:]
                if potential_opt in known_long_options or any(
                    opt.startswith(potential_opt) for opt in known_long_options
                ):
                    part = '--' + potential_opt
        if part.startswith('--'):
            long_opt = part[2:]
            if long_opt == 'help':
                show_help = True
                i += 1
                continue
            elif long_opt == 'version':
                show_version = True
                i += 1
                continue
            elif long_opt == 'zero':
                zero_terminated = True
                i += 1
                continue
            break
        if part.startswith('-') and len(part) > 1:
            opt_chars = part[1:]
            j = 0
            while j < len(opt_chars):
                char = opt_chars[j]
                if char == 'z':
                    zero_terminated = True
                    j += 1
                elif char == '-':
                    j += 1
                    i += 1
                    break
                else:
                    j += 1
            i += 1
            continue
        break
    if show_help:
        help_text = (
            'Write-Output "Usage: dirname [OPTION] NAME...\n'
            'Output each NAME with its last non-slash component and trailing slashes\n'
            'removed; if NAME contains no /\'s, output \'.\' (meaning the current directory).\n\n'
            '  -z, --zero                 end each output line with NUL, not newline\n'
            '      --help                 display this help and exit\n'
            '      --version              output version information and exit"'
        )
        return help_text
    if show_version:
        return 'Write-Output "dirname (GNU coreutils) 8.32"'
    file_paths = parts[i:]
    if not file_paths:
        return 'Write-Output "dirname: missing operand"'
    commands: List[str] = []
    for file_path in file_paths:
        if ' ' in file_path and not (file_path.startswith('"') or file_path.startswith("'")):
            quoted_path = f'"{file_path}"'
        else:
            quoted_path = file_path
        ps_cmd = f'Split-Path -Parent {quoted_path}'
        if zero_terminated:
            ps_cmd = f'Write-Host -NoNewline ({ps_cmd}); Write-Host -NoNewline "`0"'
        commands.append(ps_cmd)
    if len(commands) == 1:
        return commands[0]
    return '; '.join(commands)
def _parse_size(size_str: str) -> int:
    size_str = size_str.strip()
    if not size_str:
        return 0
    multiplier = 1
    if size_str.startswith('-'):
        multiplier = -1
        size_str = size_str[1:]
    elif size_str.startswith('+'):
        size_str = size_str[1:]
    match = re.match(r'^(\d+(?:\.\d+)?)\s*([KMGTPEZYRQ]|[KMGTPEZY]i?B)?$', size_str, re.IGNORECASE)
    if not match:
        try:
            return int(size_str) * multiplier
        except ValueError:
            return 0
    num = float(match.group(1))
    suffix = match.group(2).upper() if match.group(2) else ''
    suffix_multipliers = {
        '': 1,
        'K': 1024,
        'KB': 1000,
        'KIB': 1024,
        'M': 1024 ** 2,
        'MB': 1000 ** 2,
        'MIB': 1024 ** 2,
        'G': 1024 ** 3,
        'GB': 1000 ** 3,
        'GIB': 1024 ** 3,
        'T': 1024 ** 4,
        'TB': 1000 ** 4,
        'TIB': 1024 ** 4,
        'P': 1024 ** 5,
        'PB': 1000 ** 5,
        'PIB': 1024 ** 5,
        'E': 1024 ** 6,
        'EB': 1000 ** 6,
        'EIB': 1024 ** 6,
        'Z': 1024 ** 7,
        'ZB': 1000 ** 7,
        'ZIB': 1024 ** 7,
        'Y': 1024 ** 8,
        'YB': 1000 ** 8,
        'YIB': 1024 ** 8,
        'R': 1024 ** 9,
        'RB': 1000 ** 9,
        'RIB': 1024 ** 9,
        'Q': 1024 ** 10,
        'QB': 1000 ** 10,
        'QIB': 1024 ** 10,
    }
    return int(num * suffix_multipliers.get(suffix, 1)) * multiplier
def _convert_du(cmd: str) -> str:
    if not cmd or not cmd.strip():
        return 'Get-ChildItem -Recurse | Measure-Object -Property Length -Sum'
    parts = _parse_command_line(cmd)
    if not parts:
        return 'Get-ChildItem -Recurse | Measure-Object -Property Length -Sum'
    if parts[0] in ('du', '/bin/du', '/usr/bin/du'):
        parts = parts[1:]
    if not parts:
        return 'Get-ChildItem -Recurse | Measure-Object -Property Length -Sum'
    all_files = False
    bytes_only = False
    total = False
    dereference_args = False
    max_depth: Optional[int] = None
    human_readable = False
    si_units = False
    block_size: Optional[int] = None
    dereference = False
    count_links = False
    no_dereference = False
    separate_dirs = False
    summarize = False
    threshold: Optional[int] = None
    apparent_size = False
    inodes = False
    show_time = False
    time_word: Optional[str] = None
    time_style: Optional[str] = None
    exclude_from: Optional[str] = None
    exclude_pattern: Optional[str] = None
    one_file_system = False
    files0_from: Optional[str] = None
    null_terminated = False
    show_help = False
    show_version = False
    paths: List[str] = []
    i = 0
    while i < len(parts):
        part = parts[i]
        if part == '--':
            paths.extend(parts[i + 1:])
            break
        if part.startswith('/') and len(part) >= 2 and not part.startswith('//'):
            if len(part) == 2 and part[1].isalpha():
                part = '-' + part[1:]
            elif len(part) > 2 and part[1].isalpha():
                known_long_opts = ('max-depth', 'exclude', 'exclude-from', 'block-size',
                                   'threshold', 'time', 'time-style', 'files0-from',
                                   'all', 'bytes', 'total', 'dereference-args',
                                   'human-readable', 'si', 'dereference', 'count-links',
                                   'no-dereference', 'separate-dirs', 'summarize',
                                   'apparent-size', 'inodes', 'one-file-system', 'null',
                                   'help', 'version')
                part_body = part[1:]
                if '=' in part_body or any(part_body.startswith(opt) or part_body.startswith(opt.replace('-', '')) for opt in known_long_opts):
                    part = '--' + part[1:]
        if part.startswith('--'):
            long_opt = part[2:]
            if '=' in long_opt:
                opt_name, opt_value = long_opt.split('=', 1)
                if opt_name in ('max-depth', 'd'):
                    max_depth = int(opt_value) if opt_value.isdigit() else None
                elif opt_name == 'block-size':
                    block_size = _parse_size(opt_value)
                elif opt_name == 'threshold':
                    threshold = _parse_size(opt_value)
                elif opt_name == 'time':
                    show_time = True
                    time_word = opt_value if opt_value else None
                elif opt_name == 'time-style':
                    time_style = opt_value
                elif opt_name == 'exclude':
                    exclude_pattern = opt_value
                elif opt_name == 'exclude-from':
                    exclude_from = opt_value
                elif opt_name == 'files0-from':
                    files0_from = opt_value
            else:
                if long_opt == 'all' or long_opt == 'a':
                    all_files = True
                elif long_opt == 'bytes' or long_opt == 'b':
                    bytes_only = True
                    apparent_size = True
                    block_size = 1
                elif long_opt == 'total' or long_opt == 'c':
                    total = True
                elif long_opt == 'dereference-args' or long_opt == 'D':
                    dereference_args = True
                elif long_opt == 'human-readable' or long_opt == 'h':
                    human_readable = True
                elif long_opt == 'si':
                    human_readable = True
                    si_units = True
                elif long_opt == 'dereference' or long_opt == 'L':
                    dereference = True
                elif long_opt == 'count-links' or long_opt == 'l':
                    count_links = True
                elif long_opt == 'no-dereference' or long_opt == 'P':
                    no_dereference = True
                elif long_opt == 'separate-dirs' or long_opt == 'S':
                    separate_dirs = True
                elif long_opt == 'summarize' or long_opt == 's':
                    summarize = True
                elif long_opt == 'apparent-size':
                    apparent_size = True
                elif long_opt == 'inodes':
                    inodes = True
                elif long_opt == 'time':
                    show_time = True
                elif long_opt == 'one-file-system' or long_opt == 'x':
                    one_file_system = True
                elif long_opt == 'null' or long_opt == '0':
                    null_terminated = True
                elif long_opt == 'block-size':
                    if i + 1 < len(parts):
                        i += 1
                        block_size = _parse_size(parts[i])
                elif long_opt == 'max-depth':
                    if i + 1 < len(parts):
                        i += 1
                        max_depth = int(parts[i]) if parts[i].isdigit() else None
                elif long_opt == 'threshold':
                    if i + 1 < len(parts):
                        i += 1
                        threshold = _parse_size(parts[i])
                elif long_opt == 'exclude':
                    if i + 1 < len(parts):
                        i += 1
                        exclude_pattern = parts[i]
                elif long_opt == 'exclude-from':
                    if i + 1 < len(parts):
                        i += 1
                        exclude_from = parts[i]
                elif long_opt == 'files0-from':
                    if i + 1 < len(parts):
                        i += 1
                        files0_from = parts[i]
                elif long_opt == 'help':
                    show_help = True
                elif long_opt == 'version':
                    show_version = True
            i += 1
            continue
        if part.startswith('-') and len(part) > 1:
            opt_chars = part[1:]
            j = 0
            while j < len(opt_chars):
                char = opt_chars[j]
                if char == 'a':
                    all_files = True
                    j += 1
                elif char == 'b':
                    bytes_only = True
                    apparent_size = True
                    block_size = 1
                    j += 1
                elif char == 'c':
                    total = True
                    j += 1
                elif char == 'D':
                    dereference_args = True
                    j += 1
                elif char == 'd':
                    if j + 1 < len(opt_chars):
                        max_depth = int(opt_chars[j + 1:]) if opt_chars[j + 1:].isdigit() else None
                        break
                    elif i + 1 < len(parts):
                        i += 1
                        max_depth = int(parts[i]) if parts[i].isdigit() else None
                    j += 1
                elif char == 'H':
                    dereference_args = True
                    j += 1
                elif char == 'h':
                    human_readable = True
                    j += 1
                elif char == 'k':
                    block_size = 1024
                    j += 1
                elif char == 'L':
                    dereference = True
                    j += 1
                elif char == 'l':
                    count_links = True
                    j += 1
                elif char == 'm':
                    block_size = 1024 * 1024
                    j += 1
                elif char == 'P':
                    no_dereference = True
                    j += 1
                elif char == 'S':
                    separate_dirs = True
                    j += 1
                elif char == 's':
                    summarize = True
                    j += 1
                elif char == 't':
                    if j + 1 < len(opt_chars):
                        threshold = _parse_size(opt_chars[j + 1:])
                        break
                    elif i + 1 < len(parts):
                        i += 1
                        threshold = _parse_size(parts[i])
                    j += 1
                elif char == 'X':
                    if j + 1 < len(opt_chars):
                        exclude_from = opt_chars[j + 1:]
                        break
                    elif i + 1 < len(parts):
                        i += 1
                        exclude_from = parts[i]
                    j += 1
                elif char == 'x':
                    one_file_system = True
                    j += 1
                elif char == '0':
                    null_terminated = True
                    j += 1
                elif char == 'B':
                    if j + 1 < len(opt_chars):
                        block_size = _parse_size(opt_chars[j + 1:])
                        break
                    elif i + 1 < len(parts):
                        i += 1
                        block_size = _parse_size(parts[i])
                    j += 1
                else:
                    j += 1
            i += 1
            continue
        paths.append(part)
        i += 1
    return _build_du_powershell_command(
        all_files, bytes_only, total, dereference_args, max_depth,
        human_readable, si_units, block_size, dereference, count_links,
        no_dereference, separate_dirs, summarize, threshold, apparent_size,
        inodes, show_time, time_word, time_style, exclude_from, exclude_pattern,
        one_file_system, files0_from, null_terminated, show_help, show_version,
        paths
    )
def _build_du_powershell_command(
    all_files: bool,
    bytes_only: bool,
    total: bool,
    dereference_args: bool,
    max_depth: Optional[int],
    human_readable: bool,
    si_units: bool,
    block_size: Optional[int],
    dereference: bool,
    count_links: bool,
    no_dereference: bool,
    separate_dirs: bool,
    summarize: bool,
    threshold: Optional[int],
    apparent_size: bool,
    inodes: bool,
    show_time: bool,
    time_word: Optional[str],
    time_style: Optional[str],
    exclude_from: Optional[str],
    exclude_pattern: Optional[str],
    one_file_system: bool,
    files0_from: Optional[str],
    null_terminated: bool,
    show_help: bool,
    show_version: bool,
    paths: List[str]
) -> str:
    if show_help:
        return ('Write-Output "du - Estimate file space usage\n'
                'Usage: du [OPTION]... [FILE]...\n'
                'Options:\n'
                '  -a, --all                  write counts for all files\n'
                '  -b, --bytes                equivalent to --apparent-size --block-size=1\n'
                '  -c, --total                produce a grand total\n'
                '  -D, --dereference-args     dereference only symlinks on command line\n'
                '  -d, --max-depth=N          print total for directory only if N or fewer levels below\n'
                '  -h, --human-readable       print sizes in human readable format\n'
                '  -H                         equivalent to --dereference-args\n'
                '  -k                         like --block-size=1K\n'
                '  -L, --dereference          dereference all symbolic links\n'
                '  -l, --count-links          count sizes many times if hard linked\n'
                '  -m                         like --block-size=1M\n'
                '  -P, --no-dereference       don\'t follow any symbolic links\n'
                '  -S, --separate-dirs        for directories do not include size of subdirectories\n'
                '  -s, --summarize            display only a total for each argument\n'
                '  -t, --threshold=SIZE       exclude entries smaller/greater than SIZE\n'
                '  -B, --block-size=SIZE      scale sizes by SIZE before printing\n'
                '      --apparent-size        print apparent sizes\n'
                '      --inodes               list inode usage instead of block usage\n'
                '      --time                 show time of last modification\n'
                '      --time=WORD            show time as WORD (atime, ctime, etc.)\n'
                '      --time-style=STYLE     show times using STYLE\n'
                '  -X, --exclude-from=FILE    exclude files matching patterns in FILE\n'
                '      --exclude=PATTERN      exclude files matching PATTERN\n'
                '  -x, --one-file-system      skip directories on different file systems\n'
                '      --files0-from=F        read NUL-terminated file names from F\n'
                '  -0, --null                 end each output line with NUL\n'
                '      --help                 display this help and exit\n'
                '      --version              output version information and exit"')
    if show_version:
        return 'Write-Output "du (GNU coreutils) 8.32"'
    if not paths:
        paths = ['.']
    quoted_paths = []
    for p in paths:
        if ' ' in p and not (p.startswith('"') or p.startswith("'")):
            quoted_paths.append(f'"{p}"')
        else:
            quoted_paths.append(p)
    path_str = quoted_paths[0] if len(quoted_paths) == 1 else ', '.join(quoted_paths)
    commands = []
    notes = []
    if dereference_args:
        notes.append('# NOTE: --dereference-args not directly supported in PowerShell')
    if dereference:
        notes.append('# NOTE: --dereference not directly supported in PowerShell')
    if no_dereference:
        notes.append('# NOTE: --no-dereference is default behavior in PowerShell')
    if count_links:
        notes.append('# NOTE: --count-links not directly supported in PowerShell')
    if separate_dirs:
        notes.append('# NOTE: --separate-dirs not directly supported in PowerShell')
    if apparent_size:
        notes.append('# NOTE: --apparent-size is default behavior in PowerShell')
    if inodes:
        notes.append('# NOTE: --inodes not directly supported in PowerShell')
    if show_time:
        notes.append('# NOTE: --time not directly supported in PowerShell')
    if time_style:
        notes.append('# NOTE: --time-style not directly supported in PowerShell')
    if exclude_from:
        notes.append('# NOTE: --exclude-from not directly supported in PowerShell')
    if exclude_pattern:
        notes.append('# NOTE: --exclude not directly supported in PowerShell')
    if one_file_system:
        notes.append('# NOTE: --one-file-system not directly supported in PowerShell')
    if files0_from:
        notes.append('# NOTE: --files0-from not directly supported in PowerShell')
    if null_terminated:
        notes.append('# NOTE: --null not directly supported in PowerShell')
    if max_depth is not None:
        if max_depth == 0:
            summarize = True
        else:
            depth = max_depth
            if human_readable:
                cmd = (
                    f'Get-ChildItem -Path {path_str} -Directory | '
                    f'ForEach-Object {{ '
                    f'$size = (Get-ChildItem -Path $_.FullName -Recurse -Depth {depth} -File | '
                    f'Measure-Object -Property Length -Sum).Sum; '
                    f'[PSCustomObject]@{{"Path"=$_.FullName;"Size"=$size}} }} | '
                    f'ForEach-Object {{ "{{0:N1}} {{1}}B`t{{2}}" -f '
                    f'$(if($_.Size -ge 1TB){{$_.Size/1TB;"T"}}elseif($_.Size -ge 1GB){{$_.Size/1GB;"G"}}elseif($_.Size -ge 1MB){{$_.Size/1MB;"M"}}elseif($_.Size -ge 1KB){{$_.Size/1KB;"K"}}else{{$_.Size;""}}), $_.Path }}'
                )
            else:
                divisor = block_size if block_size else 1
                cmd = (
                    f'Get-ChildItem -Path {path_str} -Directory | '
                    f'ForEach-Object {{ '
                    f'$size = (Get-ChildItem -Path $_.FullName -Recurse -Depth {depth} -File | '
                    f'Measure-Object -Property Length -Sum).Sum; '
                    f'[PSCustomObject]@{{"Path"=$_.FullName;"Size"=[math]::Round($size / {divisor})}} }} | '
                    f'Select-Object Size, Path'
                )
            commands.append(cmd)
            if total:
                if human_readable:
                    total_cmd = (
                        f'$total = (Get-ChildItem -Path {path_str} -Recurse -File | '
                        f'Measure-Object -Property Length -Sum).Sum; '
                        f'"{{0:N1}} {{1}}B`tTotal" -f '
                        f'$(if($total -ge 1TB){{$total/1TB;"T"}}elseif($total -ge 1GB){{$total/1GB;"G"}}elseif($total -ge 1MB){{$total/1MB;"M"}}elseif($total -ge 1KB){{$total/1KB;"K"}}else{{$total;""}})'
                    )
                else:
                    divisor = block_size if block_size else 1
                    total_cmd = (
                        f'$total = (Get-ChildItem -Path {path_str} -Recurse -File | '
                        f'Measure-Object -Property Length -Sum).Sum; '
                        f'Write-Output "$([math]::Round($total / {divisor}))`tTotal"'
                    )
                commands.append(total_cmd)
            if notes:
                commands.extend(notes)
            return '; '.join(commands)
    if summarize:
        if human_readable:
            base = 1000 if si_units else 1024
            units = ['B', 'K', 'M', 'G', 'T', 'P', 'E']
            cmd = (
                f'$size = (Get-ChildItem -Path {path_str} -Recurse -File | '
                f'Measure-Object -Property Length -Sum).Sum; '
                f'$unit = 0; while ($size -ge {base} -and $unit -lt {len(units) - 1}) '
                f'{{ $size = $size / {base}; $unit++ }}; '
                f'"{{0:N1}}{{1}}`t{paths[0]}" -f $size, $units[$unit]'
            )
        elif block_size:
            cmd = (
                f'(Get-ChildItem -Path {path_str} -Recurse -File | '
                f'Measure-Object -Property Length -Sum).Sum / {block_size}'
            )
        else:
            cmd = (
                f'(Get-ChildItem -Path {path_str} -Recurse -File | '
                f'Measure-Object -Property Length -Sum).Sum'
            )
        if threshold is not None:
            notes.append(f'# NOTE: --threshold={threshold} filtering applied after calculation')
        commands.append(cmd)
        if notes:
            commands.extend(notes)
        return '; '.join(commands)
    if all_files:
        if human_readable:
            cmd = (
                f'Get-ChildItem -Path {path_str} -Recurse | '
                f'Select-Object FullName, Length | '
                f'ForEach-Object {{ '
                f'$size = if($_.Length){{$_.Length}}else{{0}}; '
                f'"{{0:N1}} {{1}}B`t{{2}}" -f '
                f'$(if($size -ge 1TB){{$size/1TB;"T"}}elseif($size -ge 1GB){{$size/1GB;"G"}}elseif($size -ge 1MB){{$size/1MB;"M"}}elseif($size -ge 1KB){{$size/1KB;"K"}}else{{$size;""}}), $_.FullName }}'
            )
        elif block_size:
            cmd = (
                f'Get-ChildItem -Path {path_str} -Recurse | '
                f'Select-Object FullName, @{{Name="Size";Expression='
                f'{{[math]::Round($_.Length / {block_size})}}}} | '
                f'Select-Object Size, FullName'
            )
        else:
            cmd = (
                f'Get-ChildItem -Path {path_str} -Recurse | '
                f'Select-Object FullName, Length'
            )
        commands.append(cmd)
        if notes:
            commands.extend(notes)
        return '; '.join(commands)
    if human_readable:
        base = 1000 if si_units else 1024
        units = ['B', 'K', 'M', 'G', 'T', 'P', 'E']
        if len(paths) == 1:
            cmd = (
                f'Get-ChildItem -Path {path_str} -Recurse -Directory | '
                f'ForEach-Object {{ '
                f'$dirSize = (Get-ChildItem -Path $_.FullName -Recurse -File | '
                f'Measure-Object -Property Length -Sum).Sum; '
                f'$size = $dirSize; $unit = 0; '
                f'while ($size -ge {base} -and $unit -lt {len(units) - 1}) '
                f'{{ $size = $size / {base}; $unit++ }}; '
                f'"{{0:N1}}{{1}}`t{{2}}" -f $size, $units[$unit], $_.FullName }}'
            )
            commands.append(cmd)
            main_cmd = (
                f'$mainSize = (Get-ChildItem -Path {path_str} -Recurse -File | '
                f'Measure-Object -Property Length -Sum).Sum; '
                f'$size = $mainSize; $unit = 0; '
                f'while ($size -ge {base} -and $unit -lt {len(units) - 1}) '
                f'{{ $size = $size / {base}; $unit++ }}; '
                f'"{{0:N1}}{{1}}`t{paths[0]}" -f $size, $units[$unit]'
            )
            commands.append(main_cmd)
        else:
            for p in quoted_paths:
                cmd = (
                    f'$size = (Get-ChildItem -Path {p} -Recurse -File | '
                    f'Measure-Object -Property Length -Sum).Sum; '
                    f'$unit = 0; while ($size -ge {base} -and $unit -lt {len(units) - 1}) '
                    f'{{ $size = $size / {base}; $unit++ }}; '
                    f'"{{0:N1}}{{1}}`t{p}" -f $size, $units[$unit]'
                )
                commands.append(cmd)
    elif block_size:
        if len(paths) == 1:
            cmd = (
                f'Get-ChildItem -Path {path_str} -Recurse -Directory | '
                f'ForEach-Object {{ '
                f'$size = (Get-ChildItem -Path $_.FullName -Recurse -File | '
                f'Measure-Object -Property Length -Sum).Sum; '
                f'[PSCustomObject]@{{"Size"=[math]::Round($size / {block_size}); "Path"=$_.FullName}} }} | '
                f'Select-Object Size, Path'
            )
            commands.append(cmd)
            main_cmd = (
                f'$mainSize = (Get-ChildItem -Path {path_str} -Recurse -File | '
                f'Measure-Object -Property Length -Sum).Sum; '
                f'[math]::Round($mainSize / {block_size})'
            )
            commands.append(main_cmd)
        else:
            for p in quoted_paths:
                cmd = (
                    f'$size = (Get-ChildItem -Path {p} -Recurse -File | '
                    f'Measure-Object -Property Length -Sum).Sum / {block_size}'
                )
                commands.append(cmd)
    else:
        if len(paths) == 1:
            cmd = (
                f'Get-ChildItem -Path {path_str} -Recurse -Directory | '
                f'ForEach-Object {{ '
                f'$size = (Get-ChildItem -Path $_.FullName -Recurse -File | '
                f'Measure-Object -Property Length -Sum).Sum; '
                f'[PSCustomObject]@{{"Size"=$size; "Path"=$_.FullName}} }} | '
                f'Select-Object Size, Path'
            )
            commands.append(cmd)
            main_cmd = (
                f'(Get-ChildItem -Path {path_str} -Recurse -File | '
                f'Measure-Object -Property Length -Sum).Sum'
            )
            commands.append(main_cmd)
        else:
            for p in quoted_paths:
                cmd = (
                    f'(Get-ChildItem -Path {p} -Recurse -File | '
                    f'Measure-Object -Property Length -Sum).Sum'
                )
                commands.append(cmd)
    if total:
        if human_readable:
            base = 1000 if si_units else 1024
            units = ['B', 'K', 'M', 'G', 'T', 'P', 'E']
            total_cmd = (
                f'$total = 0; '
                f'foreach ($p in @({path_str})) {{ '
                f'$total += (Get-ChildItem -Path $p -Recurse -File | '
                f'Measure-Object -Property Length -Sum).Sum }}; '
                f'$size = $total; $unit = 0; '
                f'while ($size -ge {base} -and $unit -lt {len(units) - 1}) '
                f'{{ $size = $size / {base}; $unit++ }}; '
                f'"{{0:N1}}{{1}}`tTotal" -f $size, $units[$unit]'
            )
        elif block_size:
            total_cmd = (
                f'$total = 0; '
                f'foreach ($p in @({path_str})) {{ '
                f'$total += (Get-ChildItem -Path $p -Recurse -File | '
                f'Measure-Object -Property Length -Sum).Sum }}; '
                f'[math]::Round($total / {block_size})'
            )
        else:
            total_cmd = (
                f'$total = 0; '
                f'foreach ($p in @({path_str})) {{ '
                f'$total += (Get-ChildItem -Path $p -Recurse -File | '
                f'Measure-Object -Property Length -Sum).Sum }}; '
                f'$total'
            )
        commands.append(total_cmd)
    if notes:
        commands.extend(notes)
    return '; '.join(commands)
if __name__ == "__main__":
    test_cases = [
        "du /home",
        "du -h /home",
        "du -s /home",
        "du -sh /home",
        "du -a /home",
        "du --max-depth=1 /home",
        "du -k /home",
        "du -m /home",
        "du -c /home /var",
        "du -hc /home",
        "du --si /home",
        "du -b /home",
        "du --bytes /home",
        "du -d 2 /home",
        "du -t 1M /home",
        "du -B 512 /home",
        "du --block-size=1K /home",
        "du --summarize /home",
        "du --all /home",
        "du /h /home",
        "du /s /home",
        "du /max-depth=1 /home",
        "du -L /home",
        "du -P /home",
        "du -S /home",
        "du -x /home",
        "du --help",
        "du --version",
    ]
    for test in test_cases:
        result = _convert_du(test)
        print(f"Input:  {test}")
        print(f"Output: {result}")
        print()
def _convert_env(cmd: str) -> str:
    if not cmd or not cmd.strip():
        return 'Get-ChildItem Env:'
    parts = _parse_command_line(cmd)
    if not parts:
        return 'Get-ChildItem Env:'
    if parts[0] in ('env', '/bin/env', '/usr/bin/env'):
        parts = parts[1:]
    if not parts:
        return 'Get-ChildItem Env:'
    ignore_environment = False
    unset_vars: List[str] = []
    chdir_path: Optional[str] = None
    split_string: Optional[str] = None
    show_help = False
    show_version = False
    env_assignments: List[Tuple[str, str]] = []
    command_parts: List[str] = []
    i = 0
    while i < len(parts):
        part = parts[i]
        if part == '--':
            i += 1
            while i < len(parts):
                remaining = parts[i]
                if '=' in remaining and not remaining.startswith('-') and not remaining.startswith('/'):
                    name, value = remaining.split('=', 1)
                    if name and not name[0].isdigit():
                        env_assignments.append((name, value))
                    else:
                        command_parts.append(remaining)
                else:
                    command_parts.append(remaining)
                i += 1
            break
        if part.startswith('/') and len(part) >= 2:
            if len(part) == 2 and part[1].isalpha():
                part = '-' + part[1:]
            elif len(part) > 2 and part[1].isalpha():
                part = '--' + part[1:]
        if part.startswith('--'):
            long_opt = part[2:]
            if '=' in long_opt:
                opt_name, opt_value = long_opt.split('=', 1)
                if opt_name == 'unset':
                    unset_vars.append(opt_value)
                elif opt_name == 'chdir':
                    chdir_path = opt_value
                elif opt_name == 'split-string':
                    split_string = opt_value
                i += 1
                continue
            if long_opt == 'help':
                show_help = True
                i += 1
                continue
            elif long_opt == 'version':
                show_version = True
                i += 1
                continue
            elif long_opt == 'ignore-environment':
                ignore_environment = True
                i += 1
                continue
            elif long_opt == 'unset':
                if i + 1 < len(parts):
                    i += 1
                    unset_vars.append(parts[i])
                i += 1
                continue
            elif long_opt == 'chdir':
                if i + 1 < len(parts):
                    i += 1
                    chdir_path = parts[i]
                i += 1
                continue
            elif long_opt == 'split-string':
                if i + 1 < len(parts):
                    i += 1
                    split_string = parts[i]
                i += 1
                continue
            i += 1
            continue
        if part.startswith('-') and len(part) > 1:
            opt_chars = part[1:]
            j = 0
            while j < len(opt_chars):
                char = opt_chars[j]
                if char == 'i':
                    ignore_environment = True
                    j += 1
                elif char == 'u':
                    if j + 1 < len(opt_chars):
                        unset_vars.append(opt_chars[j + 1:])
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                        unset_vars.append(parts[i])
                    j += 1
                elif char == 'C':
                    if j + 1 < len(opt_chars):
                        chdir_path = opt_chars[j + 1:]
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                        chdir_path = parts[i]
                    j += 1
                elif char == 'S':
                    if j + 1 < len(opt_chars):
                        split_string = opt_chars[j + 1:]
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                        split_string = parts[i]
                    j += 1
                elif char == '-':
                    j += 1
                    i += 1
                    while i < len(parts):
                        remaining = parts[i]
                        if '=' in remaining and not remaining.startswith('-') and not remaining.startswith('/'):
                            name, value = remaining.split('=', 1)
                            if name and not name[0].isdigit():
                                env_assignments.append((name, value))
                            else:
                                command_parts.append(remaining)
                        else:
                            command_parts.append(remaining)
                        i += 1
                    break
                else:
                    j += 1
            i += 1
            continue
        if '=' in part and not part.startswith('-') and not part.startswith('/'):
            name, value = part.split('=', 1)
            if name and (name[0].isalpha() or name[0] == '_'):
                env_assignments.append((name, value))
                i += 1
                continue
        command_parts.append(part)
        i += 1
    if show_help:
        return (
            'Write-Output "Usage: env [OPTION]... [-] [NAME=VALUE]... [COMMAND [ARG]...]\n'
            'Run COMMAND in the modified environment.\n'
            '\n'
            '  -i, --ignore-environment   start with an empty environment\n'
            '  -u, --unset=NAME           remove variable from the environment\n'
            '  -C, --chdir=DIR            change working directory to DIR\n'
            '  -S, --split-string=S       process and split S into separate arguments;\n'
            '                               used to pass multiple arguments on shebang lines\n'
            '      --help     display this help and exit\n'
            '      --version  output version information and exit\n'
            '\n'
            'A mere - implies -i.  If no COMMAND, print the resulting environment."'
        )
    if show_version:
        return 'Write-Output "env (GNU coreutils) 8.32"'
    ps_commands: List[str] = []
    if ignore_environment:
        ps_commands.append('Get-ChildItem Env: | Remove-Item')
    for var in unset_vars:
        ps_commands.append(f'Remove-Item Env:{var}')
    for name, value in env_assignments:
        escaped_value = value.replace('"', '`"')
        ps_commands.append(f'$env:{name} = "{escaped_value}"')
    if chdir_path:
        if ' ' in chdir_path and not (chdir_path.startswith('"') or chdir_path.startswith("'")):
            chdir_path = f'"{chdir_path}"'
        ps_commands.append(f'Push-Location {chdir_path}')
    if command_parts:
        if split_string:
            split_parts = split_string.split()
            if split_parts:
                command_parts = split_parts + command_parts
        command_str = ' '.join(command_parts)
        ps_commands.append(command_str)
        if chdir_path:
            ps_commands.append('Pop-Location')
    else:
        ps_commands.append('Get-ChildItem Env:')
        if chdir_path:
            ps_commands.append('Pop-Location')
    return '; '.join(ps_commands)
def _convert_exit(cmd: str) -> str:
    if not cmd or not cmd.strip():
        return 'exit'
    parts = _parse_command_line(cmd)
    if not parts:
        return 'exit'
    if parts[0] in ('exit', '/bin/exit', '/usr/bin/exit'):
        parts = parts[1:]
    if not parts:
        return 'exit'
    exit_code: Optional[str] = None
    i = 0
    while i < len(parts):
        part = parts[i]
        if part.startswith('/') and len(part) >= 2:
            if len(part) == 2 and part[1].isalpha():
                part = '-' + part[1:]
            elif len(part) > 2 and part[1].isalpha():
                part = '--' + part[1:]
        if part == '--':
            remaining = parts[i + 1:]
            if remaining:
                exit_code = remaining[0]
            break
        if part.startswith('--'):
            i += 1
            continue
        if part.startswith('-') and len(part) > 1:
            opt_chars = part[1:]
            for char in opt_chars:
                pass
            i += 1
            continue
        if exit_code is None:
            exit_code = part
            break
        i += 1
    if exit_code is not None:
        return f'exit {exit_code}'
    else:
        return 'exit'
def _convert_fold(cmd: str) -> str:
    if not cmd or not cmd.strip():
        return 'Get-Content - | ForEach-Object { $_ -replace ".{80}", "$&\\n" }'
    parts = _parse_command_line(cmd)
    if not parts:
        return 'Get-Content - | ForEach-Object { $_ -replace ".{80}", "$&\\n" }'
    if parts[0] in ('fold', '/bin/fold', '/usr/bin/fold'):
        parts = parts[1:]
    if not parts:
        return 'Get-Content - | ForEach-Object { $_ -replace ".{80}", "$&\\n" }'
    use_bytes = False
    use_chars = False
    break_at_spaces = False
    width: Optional[int] = 80
    show_help = False
    show_version = False
    files: List[str] = []
    i = 0
    while i < len(parts):
        part = parts[i]
        if part == '--':
            files.extend(parts[i + 1:])
            break
        if part.startswith('/') and len(part) >= 2:
            if len(part) == 2 and part[1].isalpha():
                part = '-' + part[1:]
            elif len(part) > 2 and part[1].isalpha():
                part = '--' + part[1:]
        if part.startswith('--'):
            long_opt = part[2:]
            if long_opt == 'help':
                show_help = True
                i += 1
                continue
            if long_opt == 'version':
                show_version = True
                i += 1
                continue
            if long_opt == 'bytes':
                use_bytes = True
                i += 1
                continue
            if long_opt == 'characters':
                use_chars = True
                i += 1
                continue
            if long_opt == 'spaces':
                break_at_spaces = True
                i += 1
                continue
            if long_opt.startswith('width='):
                width_str = long_opt[6:]
                try:
                    width = int(width_str)
                except ValueError:
                    width = 80
                i += 1
                continue
            i += 1
            continue
        if part.startswith('-') and len(part) > 1:
            opt_chars = part[1:]
            j = 0
            while j < len(opt_chars):
                char = opt_chars[j]
                if char == 'b':
                    use_bytes = True
                    j += 1
                elif char == 'c':
                    use_chars = True
                    j += 1
                elif char == 's':
                    break_at_spaces = True
                    j += 1
                elif char == 'w':
                    if j + 1 < len(opt_chars):
                        width_str = opt_chars[j + 1:]
                        try:
                            width = int(width_str)
                        except ValueError:
                            width = 80
                        break
                    elif i + 1 < len(parts):
                        i += 1
                        try:
                            width = int(parts[i])
                        except ValueError:
                            width = 80
                    j += 1
                else:
                    j += 1
            i += 1
            continue
        files.append(part)
        i += 1
    return _build_fold_powershell_command(
        use_bytes, use_chars, break_at_spaces, width,
        show_help, show_version, files
    )
def _build_fold_powershell_command(
    use_bytes: bool,
    use_chars: bool,
    break_at_spaces: bool,
    width: Optional[int],
    show_help: bool,
    show_version: bool,
    files: List[str]
) -> str:
    if show_help:
        return ('Write-Output "fold - wrap each input line to fit in specified width\\n'
                'Usage: fold [OPTION]... [FILE]...\\n'
                'Options:\\n'
                '  -b, --bytes         count bytes rather than columns\\n'
                '  -c, --characters    count characters rather than columns\\n'
                '  -s, --spaces        break at spaces\\n'
                '  -w, --width=WIDTH   use WIDTH columns instead of 80\\n'
                '      --help          display this help and exit\\n'
                '      --version       output version information and exit"')
    if show_version:
        return 'Write-Output "fold (GNU coreutils) 8.32"'
    if width is None:
        width = 80
    if not files:
        input_cmd = '$input'
    elif len(files) == 1:
        file = files[0]
        if file == '-':
            input_cmd = '$input'
        else:
            if ' ' in file and not (file.startswith('"') or file.startswith("'")):
                file = f'"{file}"'
            input_cmd = f'Get-Content {file}'
    else:
        quoted_files = []
        for f in files:
            if ' ' in f and not (f.startswith('"') or f.startswith("'")):
                quoted_files.append(f'"{f}"')
            else:
                quoted_files.append(f)
        files_str = ','.join(quoted_files)
        input_cmd = f'Get-Content {files_str}'
    if use_bytes:
        if 'Get-Content' in input_cmd:
            input_cmd = input_cmd.replace('Get-Content', 'Get-Content -Encoding Byte')
        note = '  # NOTE: -b byte mode: processing as byte array'
    else:
        note = ''
    if break_at_spaces:
        if use_bytes:
            fold_logic = (
                f'ForEach-Object {{ '
                f'$bytes = $_; '
                f'for ($i = 0; $i -lt $bytes.Count; $i += {width}) {{ '
                f'$end = [Math]::Min($i + {width}, $bytes.Count); '
                f'$chunk = $bytes[$i..($end-1)]; '
                f'[System.Text.Encoding]::UTF8.GetString($chunk) '
                f'}} '
                f'}}'
            )
        else:
            fold_logic = (
                f'ForEach-Object {{ '
                f'$line = $_; '
                f'while ($line.Length -gt {width}) {{ '
                f'$breakAt = $line.Substring(0, {width}).LastIndexOf(" "); '
                f'if ($breakAt -le 0) {{ $breakAt = {width} }} '
                f'$line.Substring(0, $breakAt); '
                f'$line = $line.Substring($breakAt).TrimStart() '
                f'}}; '
                f'$line '
                f'}}'
            )
    else:
        if use_bytes:
            fold_logic = (
                f'ForEach-Object {{ '
                f'$bytes = @($_); '
                f'for ($i = 0; $i -lt $bytes.Count; $i += {width}) {{ '
                f'$end = [Math]::Min($i + {width}, $bytes.Count); '
                f'$chunk = $bytes[$i..($end-1)]; '
                f'[System.Text.Encoding]::UTF8.GetString($chunk) '
                f'}} '
                f'}}'
            )
        else:
            fold_logic = (
                f'ForEach-Object {{ '
                f'$line = $_; '
                f'while ($line.Length -gt 0) {{ '
                f'$line.Substring(0, [Math]::Min({width}, $line.Length)); '
                f'$line = $line.Substring([Math]::Min({width}, $line.Length)) '
                f'}} '
                f'}}'
            )
    return f'{input_cmd} | {fold_logic}{note}'
if __name__ == "__main__":
    test_cases = [
        "fold file.txt",
        "fold -w 40 file.txt",
        "fold -s file.txt",
        "fold -b -w 50 file.txt",
        "fold -c -w 30 file.txt",
        "fold -w 40 -s file.txt",
        "fold --width=60 file.txt",
        "fold --bytes file.txt",
        "fold --characters file.txt",
        "fold --spaces file.txt",
        "fold /w 60 file.txt",
        "fold /s /w 50 file.txt",
        "fold file1.txt file2.txt",
        "fold -",
        "fold --help",
        "fold --version",
    ]
    for test in test_cases:
        result = _convert_fold(test)
        print(f"Input:  {test}")
        print(f"Output: {result}")
        print()
def _convert_groups(cmd: str) -> str:
    if not cmd or not cmd.strip():
        return '[System.Security.Principal.WindowsIdentity]::GetCurrent().Groups | ForEach-Object { $_.Translate([System.Security.Principal.NTAccount]).Value }'
    parts = _parse_command_line(cmd)
    if not parts:
        return '[System.Security.Principal.WindowsIdentity]::GetCurrent().Groups | ForEach-Object { $_.Translate([System.Security.Principal.NTAccount]).Value }'
    if parts[0] in ('groups', '/bin/groups', '/usr/bin/groups'):
        parts = parts[1:]
    if not parts:
        return '[System.Security.Principal.WindowsIdentity]::GetCurrent().Groups | ForEach-Object { $_.Translate([System.Security.Principal.NTAccount]).Value }'
    show_help = False
    show_version = False
    usernames: List[str] = []
    i = 0
    while i < len(parts):
        part = parts[i]
        if part == '--':
            i += 1
            while i < len(parts):
                usernames.append(parts[i])
                i += 1
            break
        if part.startswith('/') and len(part) >= 2:
            if len(part) == 2 and part[1].isalpha():
                part = '-' + part[1:]
            elif len(part) > 2 and part[1].isalpha():
                part = '--' + part[1:]
        if part.startswith('--'):
            long_opt = part[2:]
            if long_opt == 'help':
                show_help = True
                i += 1
                continue
            elif long_opt == 'version':
                show_version = True
                i += 1
                continue
            i += 1
            continue
        if part.startswith('-') and len(part) > 1:
            opt_chars = part[1:]
            for char in opt_chars:
                if char == 'h':
                    show_help = True
                elif char == 'v':
                    show_version = True
            i += 1
            continue
        usernames.append(part)
        i += 1
    if show_help:
        return (
            'Write-Output "Usage: groups [OPTION]... [USERNAME]...\n'
            'Print group memberships for each USERNAME or, if no USERNAME is specified, for the current process.\n\n'
            '  --help     display this help and exit\n'
            '  --version  output version information and exit"'
        )
    if show_version:
        return 'Write-Output "groups (GNU coreutils) 8.32"'
    ps_commands: List[str] = []
    if usernames:
        for username in usernames:
            ps_commands.append(f'Write-Output "Groups for user: {username}"')
            ps_commands.append(f'net user {username}')
    else:
        ps_commands.append(
            '[System.Security.Principal.WindowsIdentity]::GetCurrent().Groups | '
            'ForEach-Object { $_.Translate([System.Security.Principal.NTAccount]).Value }'
        )
    return '; '.join(ps_commands)
def _convert_gunzip(cmd: str) -> str:
    if not cmd or not cmd.strip():
        return 'Write-Output "gunzip: compressed data not read from a terminal. Use -f to force decompression."'
    parts = _parse_command_line(cmd)
    if not parts:
        return 'Write-Output "gunzip: compressed data not read from a terminal. Use -f to force decompression."'
    if parts[0] in ('gunzip', '/bin/gunzip', '/usr/bin/gunzip', 'gzexe'):
        parts = parts[1:]
    if not parts:
        return 'Write-Output "gunzip: compressed data not read from a terminal. Use -f to force decompression."'
    to_stdout = False
    decompress = True
    force = False
    keep = False
    list_contents = False
    show_license = False
    no_name = False
    save_name = False
    quiet = False
    recursive = False
    suffix: Optional[str] = None
    test_integrity = False
    verbose = False
    show_version = False
    show_help = False
    files: List[str] = []
    VALID_SHORT_OPTS = 'cdfhklLnNqrS:tvV'
    VALID_LONG_OPTS = {
        'stdout', 'to-stdout', 'decompress', 'uncompress', 'force', 'help',
        'keep', 'list', 'license', 'no-name', 'name', 'quiet', 'recursive',
        'suffix', 'test', 'verbose', 'version', 'fast', 'best'
    }
    i = 0
    while i < len(parts):
        part = parts[i]
        if part == '--':
            i += 1
            break
        if part.startswith('/') and len(part) >= 2:
            opt_part = part[1:]
            if len(opt_part) == 1 and opt_part in VALID_SHORT_OPTS:
                part = '-' + opt_part
            elif opt_part in VALID_LONG_OPTS:
                part = '--' + opt_part
            elif '=' in opt_part:
                opt_name = opt_part.split('=', 1)[0]
                if opt_name in VALID_LONG_OPTS:
                    part = '--' + opt_part
            elif opt_part.startswith('suffix='):
                part = '--' + opt_part
        if part.startswith('--'):
            long_opt = part[2:]
            if '=' in long_opt:
                opt_name, opt_value = long_opt.split('=', 1)
                if opt_name == 'suffix':
                    suffix = opt_value
                i += 1
                continue
            if long_opt == 'help':
                show_help = True
                i += 1
                continue
            elif long_opt == 'version':
                show_version = True
                i += 1
                continue
            elif long_opt in ('stdout', 'to-stdout'):
                to_stdout = True
                i += 1
                continue
            elif long_opt in ('decompress', 'uncompress'):
                decompress = True
                i += 1
                continue
            elif long_opt == 'force':
                force = True
                i += 1
                continue
            elif long_opt == 'keep':
                keep = True
                i += 1
                continue
            elif long_opt == 'list':
                list_contents = True
                i += 1
                continue
            elif long_opt == 'license':
                show_license = True
                i += 1
                continue
            elif long_opt == 'no-name':
                no_name = True
                i += 1
                continue
            elif long_opt == 'name':
                save_name = True
                i += 1
                continue
            elif long_opt in ('quiet', 'silent'):
                quiet = True
                i += 1
                continue
            elif long_opt == 'recursive':
                recursive = True
                i += 1
                continue
            elif long_opt == 'suffix':
                if i + 1 < len(parts):
                    i += 1
                    suffix = parts[i]
                i += 1
                continue
            elif long_opt == 'test':
                test_integrity = True
                i += 1
                continue
            elif long_opt == 'verbose':
                verbose = True
                i += 1
                continue
            elif long_opt == 'fast':
                i += 1
                continue
            elif long_opt == 'best':
                i += 1
                continue
            i += 1
            continue
        if part.startswith('-') and len(part) > 1:
            opt_chars = part[1:]
            j = 0
            while j < len(opt_chars):
                char = opt_chars[j]
                if char == 'c':
                    to_stdout = True
                    j += 1
                elif char == 'd':
                    decompress = True
                    j += 1
                elif char == 'f':
                    force = True
                    j += 1
                elif char == 'h':
                    show_help = True
                    j += 1
                elif char == 'k':
                    keep = True
                    j += 1
                elif char == 'l':
                    list_contents = True
                    j += 1
                elif char == 'L':
                    show_license = True
                    j += 1
                elif char == 'n':
                    no_name = True
                    j += 1
                elif char == 'N':
                    save_name = True
                    j += 1
                elif char == 'q':
                    quiet = True
                    j += 1
                elif char == 'r':
                    recursive = True
                    j += 1
                elif char == 'S':
                    if j + 1 < len(opt_chars):
                        suffix = opt_chars[j + 1:]
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                        suffix = parts[i]
                    j += 1
                elif char == 't':
                    test_integrity = True
                    j += 1
                elif char == 'v':
                    verbose = True
                    j += 1
                elif char == 'V':
                    show_version = True
                    j += 1
                elif char == '-':
                    j += 1
                    i += 1
                    break
                elif char in '123456789':
                    j += 1
                else:
                    j += 1
            i += 1
            continue
        files.append(part)
        i += 1
    while i < len(parts):
        files.append(parts[i])
        i += 1
    if show_help:
        return (
            'Write-Output "Usage: gunzip [OPTION]... [FILE]...\n'
            'Uncompress FILEs (by default, in place).\n'
            '\n'
            'Mandatory arguments to long options are mandatory for short options too.\n'
            '\n'
            '  -c, --stdout      write on standard output, keep original files unchanged\n'
            '  -d, --decompress  decompress\n'
            '  -f, --force       force overwrite of output file and compress links\n'
            '  -h, --help        give this help\n'
            '  -k, --keep        keep (don\'t delete) input files\n'
            '  -l, --list        list compressed file contents\n'
            '  -L, --license     display software license\n'
            '  -n, --no-name     do not save or restore the original name and timestamp\n'
            '  -N, --name        save or restore the original name and timestamp\n'
            '  -q, --quiet       suppress all warnings\n'
            '  -r, --recursive   operate recursively on directories\n'
            '  -S, --suffix=SUF  use suffix SUF on compressed files\n'
            '  -t, --test        test compressed file integrity\n'
            '  -v, --verbose     verbose mode\n'
            '  -V, --version     display version number and copyright"'
        )
    if show_version:
        return 'Write-Output "gunzip (gzip) 1.10"'
    if show_license:
        return 'Write-Output "Copyright (C) 2007, 2011-2018 Free Software Foundation, Inc.\nThis is free software. You may redistribute copies of it under the terms of the GNU General Public License <https://www.gnu.org/licenses/gpl.html>."'
    if not files:
        if to_stdout:
            return '$input | ForEach-Object { $bytes = [System.Text.Encoding]::UTF8.GetBytes($_); $ms = New-Object System.IO.MemoryStream(,$bytes); $gz = New-Object System.IO.Compression.GzipStream($ms, [System.IO.Compression.CompressionMode]::Decompress); $reader = New-Object System.IO.StreamReader($gz); $reader.ReadToEnd() }'
        return 'Write-Output "gunzip: compressed data not read from a terminal. Use -f to force decompression."'
    return _build_gunzip_powershell_command(
        files, to_stdout, force, keep, list_contents,
        no_name, save_name, quiet, recursive, suffix,
        test_integrity, verbose
    )
def _build_gunzip_powershell_command(
    files: List[str],
    to_stdout: bool,
    force: bool,
    keep: bool,
    list_contents: bool,
    no_name: bool,
    save_name: bool,
    quiet: bool,
    recursive: bool,
    suffix: Optional[str],
    test_integrity: bool,
    verbose: bool
) -> str:
    commands: List[str] = []
    file_suffix = suffix if suffix else '.gz'
    for file_path in files:
        quoted_file = f'"{file_path}"' if ' ' in file_path and not (file_path.startswith('"') or file_path.startswith("'")) else file_path
        if recursive:
            find_cmd = f'Get-ChildItem -Path {quoted_file} -Recurse -Filter "*{file_suffix}"'
            if list_contents:
                cmd = (
                    f'{find_cmd} | ForEach-Object {{ '
                    f'Write-Output "$($_.Name):"; '
                    f'$bytes = [System.IO.File]::ReadAllBytes($_.FullName); '
                    f'$ms = New-Object System.IO.MemoryStream(,$bytes); '
                    f'$gz = New-Object System.IO.Compression.GzipStream($ms, [System.IO.Compression.CompressionMode]::Decompress); '
                    f'$info = New-Object PSObject -Property @{{ '
                    f'CompressedSize = $_.Length; '
                    f'Name = $_.BaseName '
                    f'}}; '
                    f'$info '
                    f'}}'
                )
            elif test_integrity:
                cmd = (
                    f'{find_cmd} | ForEach-Object {{ '
                    f'try {{ '
                    f'$bytes = [System.IO.File]::ReadAllBytes($_.FullName); '
                    f'$ms = New-Object System.IO.MemoryStream(,$bytes); '
                    f'$gz = New-Object System.IO.Compression.GzipStream($ms, [System.IO.Compression.CompressionMode]::Decompress); '
                    f'$buffer = New-Object byte[] 1024; '
                    f'while ($gz.Read($buffer, 0, 1024) -gt 0) {{ }}; '
                    f'Write-Output "$($_.Name): OK" '
                    f'}} catch {{ '
                    f'Write-Error "$($_.Name): FAILED - $($_.Exception.Message)" '
                    f'}} '
                    f'}}'
                )
            elif to_stdout:
                cmd = (
                    f'{find_cmd} | ForEach-Object {{ '
                    f'$bytes = [System.IO.File]::ReadAllBytes($_.FullName); '
                    f'$ms = New-Object System.IO.MemoryStream(,$bytes); '
                    f'$gz = New-Object System.IO.Compression.GzipStream($ms, [System.IO.Compression.CompressionMode]::Decompress); '
                    f'$reader = New-Object System.IO.StreamReader($gz); '
                    f'$reader.ReadToEnd() '
                    f'}}'
                )
            else:
                decompress_cmd = (
                    f'{find_cmd} | ForEach-Object {{ '
                    f'$inFile = $_.FullName; '
                    f'$outFile = $inFile -replace "\\{file_suffix}$", ""; '
                    f'if ((Test-Path $outFile) -and -not {"$true" if force else "$false"}) {{ '
                    f'Write-Error "File exists: $outFile"; return '
                    f'}}; '
                    f'try {{ '
                    f'$bytes = [System.IO.File]::ReadAllBytes($inFile); '
                    f'$ms = New-Object System.IO.MemoryStream(,$bytes); '
                    f'$gz = New-Object System.IO.Compression.GzipStream($ms, [System.IO.Compression.CompressionMode]::Decompress); '
                    f'$outMs = New-Object System.IO.MemoryStream; '
                    f'$gz.CopyTo($outMs); '
                    f'[System.IO.File]::WriteAllBytes($outFile, $outMs.ToArray()); '
                    f'{"Remove-Item $inFile;" if not keep else ""} '
                    f'{"Write-Output \"Decompressed: $outFile\";" if verbose else ""} '
                    f'}} catch {{ '
                    f'Write-Error "Failed to decompress $inFile: $($_.Exception.Message)" '
                    f'}} '
                    f'}}'
                )
                cmd = decompress_cmd
            commands.append(cmd)
        else:
            if list_contents:
                cmd = (
                    f'$file = Get-Item {quoted_file}; '
                    f'$bytes = [System.IO.File]::ReadAllBytes($file.FullName); '
                    f'$ms = New-Object System.IO.MemoryStream(,$bytes); '
                    f'$gz = New-Object System.IO.Compression.GzipStream($ms, [System.IO.Compression.CompressionMode]::Decompress); '
                    f'$outMs = New-Object System.IO.MemoryStream; '
                    f'try {{ $gz.CopyTo($outMs); $uncompressedSize = $outMs.Length }} catch {{ $uncompressedSize = "Unknown" }}; '
                    f'[PSCustomObject]@{{ '
                    f'Compressed = $file.Length; '
                    f'Uncompressed = $uncompressedSize; '
                    f'Ratio = if ($uncompressedSize -gt 0) {{ "{{0:N1}}%" -f (100 * (1 - $file.Length / $uncompressedSize)) }} else {{ "N/A" }}; '
                    f'Name = $file.Name '
                    f'}} | Format-Table -AutoSize'
                )
                commands.append(cmd)
            elif test_integrity:
                cmd = (
                    f'try {{ '
                    f'$file = Get-Item {quoted_file}; '
                    f'$bytes = [System.IO.File]::ReadAllBytes($file.FullName); '
                    f'$ms = New-Object System.IO.MemoryStream(,$bytes); '
                    f'$gz = New-Object System.IO.Compression.GzipStream($ms, [System.IO.Compression.CompressionMode]::Decompress); '
                    f'$buffer = New-Object byte[] 8192; '
                    f'while ($gz.Read($buffer, 0, 8192) -gt 0) {{ }}; '
                    f'{"Write-Output \"$file_path: OK\";" if not quiet else ""} '
                    f'}} catch {{ '
                    f'Write-Error "{file_path}: FAILED" '
                    f'}}'
                )
                commands.append(cmd)
            elif to_stdout:
                cmd = (
                    f'$bytes = [System.IO.File]::ReadAllBytes({quoted_file}); '
                    f'$ms = New-Object System.IO.MemoryStream(,$bytes); '
                    f'$gz = New-Object System.IO.Compression.GzipStream($ms, [System.IO.Compression.CompressionMode]::Decompress); '
                    f'$reader = New-Object System.IO.StreamReader($gz); '
                    f'$reader.ReadToEnd()'
                )
                commands.append(cmd)
            else:
                if file_path.endswith(file_suffix):
                    output_file = file_path[:-len(file_suffix)]
                else:
                    output_file = file_path + '.out'
                quoted_output = f'"{output_file}"' if ' ' in output_file and not (output_file.startswith('"') or output_file.startswith("'")) else output_file
                cmd_parts = []
                if not force:
                    cmd_parts.append(
                        f'if (Test-Path {quoted_output}) {{ '
                        f'Write-Error "Output file already exists: {output_file}. Use -f to force."; return '
                        f'}}'
                    )
                decompress_logic = (
                    f'$bytes = [System.IO.File]::ReadAllBytes({quoted_file}); '
                    f'$ms = New-Object System.IO.MemoryStream(,$bytes); '
                    f'$gz = New-Object System.IO.Compression.GzipStream($ms, [System.IO.Compression.CompressionMode]::Decompress); '
                    f'$outMs = New-Object System.IO.MemoryStream; '
                    f'$gz.CopyTo($outMs); '
                    f'[System.IO.File]::WriteAllBytes({quoted_output}, $outMs.ToArray())'
                )
                cmd_parts.append(decompress_logic)
                if not keep:
                    cmd_parts.append(f'Remove-Item {quoted_file}')
                if verbose:
                    cmd_parts.append(f'Write-Output "Decompressed: {file_path} -> {output_file}"')
                cmd = '; '.join(cmd_parts)
                commands.append(cmd)
    if len(commands) == 1:
        return commands[0]
    return '; '.join(commands)
def _convert_gzip(cmd: str) -> str:
    if not cmd or not cmd.strip():
        return 'Write-Output "gzip: missing operand"'
    parts = _parse_command_line(cmd)
    if not parts:
        return 'Write-Output "gzip: missing operand"'
    if parts[0] in ('gzip', '/bin/gzip', '/usr/bin/gzip'):
        parts = parts[1:]
    if not parts:
        return 'Write-Output "gzip: missing operand"'
    options: Dict[str, Any] = {
        'ascii': False,
        'stdout': False,
        'decompress': False,
        'force': False,
        'keep': False,
        'list': False,
        'license': False,
        'no_name': False,
        'name': True,
        'quiet': False,
        'recursive': False,
        'suffix': '.gz',
        'test': False,
        'verbose': False,
        'show_version': False,
        'show_help': False,
        'compression_level': None,
    }
    files: List[str] = []
    i = 0
    while i < len(parts):
        part = parts[i]
        if part == '--':
            files.extend(parts[i + 1:])
            break
        if part.startswith('/') and len(part) >= 2:
            if len(part) == 2 and part[1].isalpha():
                part = '-' + part[1:]
            elif len(part) > 2 and part[1].isalpha():
                part = '--' + part[1:]
        if part.startswith('--'):
            long_opt = part[2:]
            if '=' in long_opt:
                opt_name, opt_value = long_opt.split('=', 1)
                if opt_name in ('suffix', 'S'):
                    options['suffix'] = opt_value
                i += 1
                continue
            if long_opt == 'help':
                options['show_help'] = True
                i += 1
                continue
            elif long_opt == 'version':
                options['show_version'] = True
                i += 1
                continue
            elif long_opt in ('stdout', 'to-stdout'):
                options['stdout'] = True
                i += 1
                continue
            elif long_opt in ('decompress', 'uncompress'):
                options['decompress'] = True
                i += 1
                continue
            elif long_opt == 'force':
                options['force'] = True
                i += 1
                continue
            elif long_opt == 'keep':
                options['keep'] = True
                i += 1
                continue
            elif long_opt == 'list':
                options['list'] = True
                i += 1
                continue
            elif long_opt == 'license':
                options['license'] = True
                i += 1
                continue
            elif long_opt == 'no-name':
                options['no_name'] = True
                options['name'] = False
                i += 1
                continue
            elif long_opt == 'name':
                options['name'] = True
                options['no_name'] = False
                i += 1
                continue
            elif long_opt == 'quiet':
                options['quiet'] = True
                i += 1
                continue
            elif long_opt == 'recursive':
                options['recursive'] = True
                i += 1
                continue
            elif long_opt == 'suffix':
                if i + 1 < len(parts):
                    i += 1
                    options['suffix'] = parts[i]
                i += 1
                continue
            elif long_opt == 'test':
                options['test'] = True
                i += 1
                continue
            elif long_opt == 'verbose':
                options['verbose'] = True
                i += 1
                continue
            elif long_opt == 'ascii':
                options['ascii'] = True
                i += 1
                continue
            elif long_opt == 'fast':
                options['compression_level'] = 1
                i += 1
                continue
            elif long_opt == 'best':
                options['compression_level'] = 9
                i += 1
                continue
            i += 1
            continue
        if part.startswith('-') and len(part) > 1:
            opt_chars = part[1:]
            j = 0
            while j < len(opt_chars):
                char = opt_chars[j]
                if char == 'a':
                    options['ascii'] = True
                    j += 1
                elif char == 'c':
                    options['stdout'] = True
                    j += 1
                elif char == 'd':
                    options['decompress'] = True
                    j += 1
                elif char == 'f':
                    options['force'] = True
                    j += 1
                elif char == 'h':
                    options['show_help'] = True
                    j += 1
                elif char == 'k':
                    options['keep'] = True
                    j += 1
                elif char == 'l':
                    options['list'] = True
                    j += 1
                elif char == 'L':
                    options['license'] = True
                    j += 1
                elif char == 'n':
                    options['no_name'] = True
                    options['name'] = False
                    j += 1
                elif char == 'N':
                    options['name'] = True
                    options['no_name'] = False
                    j += 1
                elif char == 'q':
                    options['quiet'] = True
                    j += 1
                elif char == 'r':
                    options['recursive'] = True
                    j += 1
                elif char == 'S':
                    if j + 1 < len(opt_chars):
                        options['suffix'] = opt_chars[j + 1:]
                        break
                    elif i + 1 < len(parts):
                        i += 1
                        options['suffix'] = parts[i]
                    j += 1
                elif char == 't':
                    options['test'] = True
                    j += 1
                elif char == 'v':
                    options['verbose'] = True
                    j += 1
                elif char == 'V':
                    options['show_version'] = True
                    j += 1
                elif char.isdigit() and char in '123456789':
                    options['compression_level'] = int(char)
                    j += 1
                else:
                    j += 1
            i += 1
            continue
        files.append(part)
        i += 1
    return _build_gzip_powershell_command(options, files)
def _build_gzip_powershell_command(options: Dict[str, Any], files: List[str]) -> str:
    if options.get('show_help'):
        return (
            'Write-Output "Usage: gzip [OPTION]... [FILE]...\n'
            'Compress or uncompress FILEs (by default, compress FILES in-place).\n'
            '\n'
            'Mandatory arguments to long options are mandatory for short options too.\n'
            '\n'
            '  -a, --ascii       ASCII text mode: convert end-of-lines using local conventions\n'
            '  -c, --stdout      write on standard output, keep original files unchanged\n'
            '  -d, --decompress  decompress\n'
            '  -f, --force       force overwrite of output file and compress links\n'
            '  -h, --help        give this help\n'
            '  -k, --keep        keep (don\'t delete) input files\n'
            '  -l, --list        list compressed file contents\n'
            '  -L, --license     display software license\n'
            '  -n, --no-name     do not save or restore the original name and timestamp\n'
            '  -N, --name        save or restore the original name and timestamp\n'
            '  -q, --quiet       suppress all warnings\n'
            '  -r, --recursive   operate recursively on directories\n'
            '  -S, --suffix=SUF  use suffix SUF instead of .gz\n'
            '  -t, --test        test compressed file integrity\n'
            '  -v, --verbose     verbose mode\n'
            '  -V, --version     display version number and exit\n'
            '  -1, --fast        compress faster\n'
            '  -9, --best        compress better"'
        )
    if options.get('show_version'):
        return 'Write-Output "gzip 1.12"'
    if options.get('license'):
        return (
            'Write-Output "Copyright (C) 2024 Free Software Foundation, Inc.\n'
            'Copyright (C) 1993 Jean-loup Gailly.\n'
            'This is free software.  You may redistribute copies of it under the terms of\n'
            'the GNU General Public License <https://www.gnu.org/licenses/gpl.html>.\n'
            'There is NO WARRANTY, to the extent permitted by law."'
        )
    if not files:
        if options.get('decompress'):
            return '$input | ForEach-Object { $src = $_; $fs = [System.IO.FileStream]::new($src, [System.IO.FileMode]::Open); $gs = [System.IO.Compression.GZipStream]::new($fs, [System.IO.Compression.CompressionMode]::Decompress); $dest = $src -replace "\\.gz$", ""; $out = [System.IO.FileStream]::new($dest, [System.IO.FileMode]::Create); $gs.CopyTo($out); $gs.Dispose(); $fs.Dispose(); $out.Dispose() }'
        elif options.get('list'):
            return '$input | ForEach-Object { $file = $_; $fs = [System.IO.FileStream]::new($file, [System.IO.FileMode]::Open); $gs = [System.IO.Compression.GZipStream]::new($fs, [System.IO.Compression.CompressionMode]::Decompress); $temp = [System.IO.MemoryStream]::new(); try { $gs.CopyTo($temp) } catch {}; Write-Output ("{0,9} {1,11} {2}" -f $fs.Length, $temp.Length, $file); $gs.Dispose(); $fs.Dispose(); $temp.Dispose() }'
        elif options.get('test'):
            return '$input | ForEach-Object { $file = $_; try { $fs = [System.IO.FileStream]::new($file, [System.IO.FileMode]::Open); $gs = [System.IO.Compression.GZipStream]::new($fs, [System.IO.Compression.CompressionMode]::Decompress); $ms = [System.IO.MemoryStream]::new(); $gs.CopyTo($ms); $gs.Dispose(); $fs.Dispose(); $ms.Dispose(); Write-Output "$file: OK" } catch { Write-Error "$file: FAILED" } }'
        else:
            return '$input | ForEach-Object { $src = $_; $fs = [System.IO.FileStream]::new($src, [System.IO.FileMode]::Open); $gs = [System.IO.Compression.GZipStream]::new($fs, [System.IO.Compression.CompressionMode]::Compress); $dest = "$src.gz"; $out = [System.IO.FileStream]::new($dest, [System.IO.FileMode]::Create); $fs.CopyTo($gs); $gs.Dispose(); $fs.Dispose(); $out.Dispose(); Remove-Item $src }'
    if options.get('recursive'):
        return _build_recursive_command(files, options)
    commands = []
    for file_path in files:
        quoted_file = file_path
        if ' ' in file_path and not (file_path.startswith('"') or file_path.startswith("'")):
            quoted_file = f'"{file_path}"'
        cmd = _build_single_file_command(quoted_file, options)
        commands.append(cmd)
    if len(commands) == 1:
        return commands[0]
    return '; '.join(commands)
def _build_single_file_command(file_path: str, options: Dict[str, Any]) -> str:
    decompress = options.get('decompress', False)
    to_stdout = options.get('stdout', False)
    keep = options.get('keep', False)
    list_mode = options.get('list', False)
    test_mode = options.get('test', False)
    verbose = options.get('verbose', False)
    suffix = options.get('suffix', '.gz')
    compression_level = options.get('compression_level')
    if compression_level is not None:
        if compression_level >= 6:
            level_param = '[System.IO.Compression.CompressionLevel]::Optimal'
        else:
            level_param = '[System.IO.Compression.CompressionLevel]::Fastest'
    else:
        level_param = '[System.IO.Compression.CompressionLevel]::Optimal'
    if list_mode:
        return (
            f'$file = {file_path}; '
            f'$fs = [System.IO.FileStream]::new($file, [System.IO.FileMode]::Open); '
            f'$gs = [System.IO.Compression.GZipStream]::new($fs, [System.IO.Compression.CompressionMode]::Decompress); '
            f'$temp = [System.IO.MemoryStream]::new(); '
            f'try {{ $gs.CopyTo($temp) }} catch {{}}; '
            f'$compressed = $fs.Length; '
            f'$uncompressed = $temp.Length; '
            f'$ratio = if ($uncompressed -gt 0) {{ [int]((1 - $compressed/$uncompressed) * 100) }} else {{ 0 }}; '
            f'Write-Output "compressed uncompressed  ratio uncompressed_name"; '
            f'Write-Output ("{{0,9}} {{1,11}} {{2,5}}% {{3}}" -f $compressed, $uncompressed, $ratio, $file); '
            f'$gs.Dispose(); $fs.Dispose(); $temp.Dispose()'
        )
    if test_mode:
        return (
            f'$file = {file_path}; '
            f'try {{ '
            f'$fs = [System.IO.FileStream]::new($file, [System.IO.FileMode]::Open); '
            f'$gs = [System.IO.Compression.GZipStream]::new($fs, [System.IO.Compression.CompressionMode]::Decompress); '
            f'$ms = [System.IO.MemoryStream]::new(); '
            f'$gs.CopyTo($ms); '
            f'$gs.Dispose(); $fs.Dispose(); $ms.Dispose(); '
            f'Write-Output "$file: OK" '
            f'}} catch {{ Write-Error "$file: FAILED" }}'
        )
    if decompress:
        dest_var = f'$dest = ({file_path}) -replace "\\{suffix}$", ""'
        if to_stdout:
            return (
                f'$src = {file_path}; '
                f'$fs = [System.IO.FileStream]::new($src, [System.IO.FileMode]::Open); '
                f'$gs = [System.IO.Compression.GZipStream]::new($fs, [System.IO.Compression.CompressionMode]::Decompress); '
                f'$ms = [System.IO.MemoryStream]::new(); '
                f'$gs.CopyTo($ms); '
                f'$gs.Dispose(); $fs.Dispose(); '
                f'$bytes = $ms.ToArray(); '
                f'$ms.Dispose(); '
                f'[System.Text.Encoding]::UTF8.GetString($bytes)'
            )
        else:
            cmd_parts = [
                f'$src = {file_path}',
                f'$dest = ($src) -replace "\\{suffix}$", ""',
                f'$fs = [System.IO.FileStream]::new($src, [System.IO.FileMode]::Open)',
                f'$gs = [System.IO.Compression.GZipStream]::new($fs, [System.IO.Compression.CompressionMode]::Decompress)',
                f'$out = [System.IO.FileStream]::new($dest, [System.IO.FileMode]::Create)',
                f'$gs.CopyTo($out)',
                f'$gs.Dispose(); $fs.Dispose(); $out.Dispose()',
            ]
            if verbose:
                cmd_parts.append(f'Write-Output "{file_path}: decompressed"')
            if not keep:
                cmd_parts.append('Remove-Item $src')
            return '; '.join(cmd_parts)
    if to_stdout:
        return (
            f'$src = {file_path}; '
            f'$fs = [System.IO.FileStream]::new($src, [System.IO.FileMode]::Open); '
            f'$gs = [System.IO.Compression.GZipStream]::new($fs, {level_param}); '
            f'$ms = [System.IO.MemoryStream]::new(); '
            f'$fs.CopyTo($gs); '
            f'$gs.Dispose(); $fs.Dispose(); '
            f'$ms.ToArray()'
        )
    else:
        cmd_parts = [
            f'$src = {file_path}',
            f'$dest = "$src{suffix}"',
            f'$fs = [System.IO.FileStream]::new($src, [System.IO.FileMode]::Open)',
            f'$gs = [System.IO.Compression.GZipStream]::new($fs, {level_param})',
            f'$out = [System.IO.FileStream]::new($dest, [System.IO.FileMode]::Create)',
            f'$fs.CopyTo($gs)',
            f'$gs.Dispose(); $fs.Dispose(); $out.Dispose()',
        ]
        if verbose:
            cmd_parts.append(
                f'$percent = [int]((1 - (Get-Item $dest).Length / (Get-Item $src).Length) * 100); '
                f'Write-Output ("{{0,-20}} {{1,7}}%" -f $src, $percent)'
            )
        if not keep:
            cmd_parts.append('Remove-Item $src')
        return '; '.join(cmd_parts)
def _build_recursive_command(files: List[str], options: Dict[str, Any]) -> str:
    decompress = options.get('decompress', False)
    keep = options.get('keep', False)
    suffix = options.get('suffix', '.gz')
    compression_level = options.get('compression_level')
    if compression_level is not None:
        if compression_level >= 6:
            level_param = '[System.IO.Compression.CompressionLevel]::Optimal'
        else:
            level_param = '[System.IO.Compression.CompressionLevel]::Fastest'
    else:
        level_param = '[System.IO.Compression.CompressionLevel]::Optimal'
    commands = []
    if not files:
        files = ['.']
    for file_path in files:
        quoted_file = file_path
        if ' ' in file_path and not (file_path.startswith('"') or file_path.startswith("'")):
            quoted_file = f'"{file_path}"'
        if decompress:
            cmd = (
                f'Get-ChildItem -Path {quoted_file} -File -Recurse -Filter "*{suffix}" | ForEach-Object {{ '
                f'$src = $_.FullName; '
                f'$dest = ($src) -replace "\\{suffix}$", ""; '
                f'$fs = [System.IO.FileStream]::new($src, [System.IO.FileMode]::Open); '
                f'$gs = [System.IO.Compression.GZipStream]::new($fs, [System.IO.Compression.CompressionMode]::Decompress); '
                f'$out = [System.IO.FileStream]::new($dest, [System.IO.FileMode]::Create); '
                f'$gs.CopyTo($out); '
                f'$gs.Dispose(); $fs.Dispose(); $out.Dispose(); '
            )
            if not keep:
                cmd += 'Remove-Item $src; '
            cmd += '}'
        else:
            cmd = (
                f'Get-ChildItem -Path {quoted_file} -File -Recurse | Where-Object {{ $_.Extension -ne "{suffix}" }} | ForEach-Object {{ '
                f'$src = $_.FullName; '
                f'$fs = [System.IO.FileStream]::new($src, [System.IO.FileMode]::Open); '
                f'$gs = [System.IO.Compression.GZipStream]::new($fs, {level_param}); '
                f'$dest = "$src{suffix}"; '
                f'$out = [System.IO.FileStream]::new($dest, [System.IO.FileMode]::Create); '
                f'$fs.CopyTo($gs); '
                f'$gs.Dispose(); $fs.Dispose(); $out.Dispose(); '
            )
            if not keep:
                cmd += 'Remove-Item $src; '
            cmd += '}'
        commands.append(cmd)
    if len(commands) == 1:
        return commands[0]
    return '; '.join(commands)
if __name__ == "__main__":
    test_cases = [
        "gzip file.txt",
        "gzip -c file.txt",
        "gzip -d file.txt.gz",
        "gzip -k file.txt",
        "gzip -l file.txt.gz",
        "gzip -t file.txt.gz",
        "gzip -v file.txt",
        "gzip -9 file.txt",
        "gzip --fast file.txt",
        "gzip --best file.txt",
        "gzip -r dir/",
        "gzip -S .gz2 file.txt",
        "gzip --help",
        "gzip --version",
        "gzip -f file.txt",
        "gzip -q file.txt",
        "gzip -n file.txt",
        "gzip -N file.txt",
        "gzip /c file.txt",
        "gzip /d file.txt.gz",
        "gzip -cd file.txt.gz",
        "gzip -kv file.txt",
    ]
    for test in test_cases:
        result = _convert_gzip(test)
        print(f"Input:  {test}")
        print(f"Output: {result}")
        print()
def _parse_byte_suffix(value: str) -> int:
    negative = value.startswith('-')
    if negative:
        value = value[1:]
    match = re.match(r'^(\d+(?:\.\d+)?)\s*([a-zA-Z]*)$', value)
    if not match:
        try:
            return -int(value) if negative else int(value)
        except ValueError:
            return 0
    num_str, suffix = match.groups()
    num = float(num_str)
    multipliers = {
        'b': 512,
        'kB': 1000,
        'KB': 1000,
        'K': 1024,
        'k': 1024,
        'MB': 1000 * 1000,
        'M': 1024 * 1024,
        'GB': 1000 * 1000 * 1000,
        'G': 1024 * 1024 * 1024,
        'TB': 1000 * 1000 * 1000 * 1000,
        'T': 1024 * 1024 * 1024 * 1024,
        'PB': 1000 * 1000 * 1000 * 1000 * 1000,
        'P': 1024 * 1024 * 1024 * 1024 * 1024,
        'EB': 1000 * 1000 * 1000 * 1000 * 1000 * 1000,
        'E': 1024 * 1024 * 1024 * 1024 * 1024 * 1024,
        'ZB': 1000 * 1000 * 1000 * 1000 * 1000 * 1000 * 1000,
        'Z': 1024 * 1024 * 1024 * 1024 * 1024 * 1024 * 1024,
        'YB': 1000 * 1000 * 1000 * 1000 * 1000 * 1000 * 1000 * 1000,
        'Y': 1024 * 1024 * 1024 * 1024 * 1024 * 1024 * 1024 * 1024,
        'KiB': 1024,
        'MiB': 1024 * 1024,
        'GiB': 1024 * 1024 * 1024,
        'TiB': 1024 * 1024 * 1024 * 1024,
        'PiB': 1024 * 1024 * 1024 * 1024 * 1024,
        'EiB': 1024 * 1024 * 1024 * 1024 * 1024 * 1024,
        'ZiB': 1024 * 1024 * 1024 * 1024 * 1024 * 1024 * 1024,
        'YiB': 1024 * 1024 * 1024 * 1024 * 1024 * 1024 * 1024 * 1024,
    }
    multiplier = multipliers.get(suffix, 1)
    result = int(num * multiplier)
    return -result if negative else result
def _convert_head(cmd: str) -> str:
    parts = cmd.split()
    num_lines = 10
    file_path = None
    i = 1
    while i < len(parts):
        part = parts[i]
        if part.startswith('-n'):
            if len(part) > 2:
                num_lines = int(part[2:])
            elif i + 1 < len(parts):
                num_lines = int(parts[i + 1])
                i += 1
        elif part.startswith('-') and part[1:].isdigit():
            num_lines = int(part[1:])
        elif not part.startswith('-'):
            file_path = part
        i += 1
    if file_path:
        return f'Get-Content {file_path} | Select-Object -First {num_lines}'
    else:
        return f'Select-Object -First {num_lines}'
def _build_head_powershell_command(
    byte_count: Optional[int],
    line_count: Optional[int],
    quiet: bool,
    verbose: bool,
    zero_terminated: bool,
    show_help: bool,
    show_version: bool,
    files: List[str]
) -> str:
    if show_help:
        return ('Write-Output "head - Output the first part of files\n'
                'Usage: head [OPTION]... [FILE]...\n'
                'Options:\n'
                '  -c, --bytes=NUM     Print first NUM bytes\n'
                '  -n, --lines=NUM     Print first NUM lines (default: 10)\n'
                '  -q, --quiet         Never print headers\n'
                '  -v, --verbose       Always print headers\n'
                '  -z, --zero-terminated  Line delimiter is NUL\n'
                '      --help          Display help\n'
                '      --version       Output version"')
    if show_version:
        return 'Write-Output "head (GNU coreutils) 8.32"'
    if not files:
        if byte_count is not None:
            if byte_count < 0:
                return f'$input -Raw | ForEach-Object {{ $_.Substring(0, [Math]::Max(0, $_.Length + {byte_count})) }}'
            else:
                return f'$input -Raw | ForEach-Object {{ $_.Substring(0, [Math]::Min({byte_count}, $_.Length)) }}'
        else:
            if line_count is None:
                line_count = 10
            if line_count < 0:
                return f'$lines = $input; $lines[0..([Math]::Max(0, $lines.Count + {line_count} - 1))]'
            else:
                return f'$input -Head {line_count}'
    quoted_files = []
    for f in files:
        if ' ' in f and not (f.startswith('"') or f.startswith("'")):
            quoted_files.append(f'"{f}"')
        else:
            quoted_files.append(f)
    file_list = ','.join(quoted_files)
    multi_file = len(files) > 1 and not quiet
    if byte_count is not None:
        if len(files) == 1:
            if byte_count < 0:
                return f'$content = Get-Content {file_list} -Raw; $content.Substring(0, [Math]::Max(0, $content.Length + {byte_count}))'
            else:
                return f'$content = Get-Content {file_list} -Raw; $content.Substring(0, [Math]::Min({byte_count}, $content.Length))'
        else:
            commands = []
            for j, f in enumerate(quoted_files):
                if verbose or (not quiet and len(files) > 1):
                    commands.append(f'Write-Output "==> {files[j]} <=="')
                if byte_count < 0:
                    commands.append(f'$content = Get-Content {f} -Raw; $content.Substring(0, [Math]::Max(0, $content.Length + {byte_count}))')
                else:
                    commands.append(f'$content = Get-Content {f} -Raw; $content.Substring(0, [Math]::Min({byte_count}, $content.Length))')
            return '; '.join(commands)
    else:
        if line_count is None:
            line_count = 10
        if len(files) == 1:
            if line_count < 0:
                return f'$lines = Get-Content {file_list}; $lines[0..([Math]::Max(0, $lines.Count + {line_count} - 1))]'
            else:
                return f'Get-Content {file_list} -Head {line_count}'
        else:
            commands = []
            for j, f in enumerate(quoted_files):
                if verbose or (not quiet and len(files) > 1):
                    commands.append(f'Write-Output "==> {files[j]} <=="')
                if line_count < 0:
                    commands.append(f'$lines = Get-Content {f}; $lines[0..([Math]::Max(0, $lines.Count + {line_count} - 1))]')
                else:
                    commands.append(f'Get-Content {f} -Head {line_count}')
            return '; '.join(commands)
def _convert_history(cmd: str) -> str:
    if not cmd or not cmd.strip():
        return 'Get-History'
    parts = _parse_command_line(cmd)
    if not parts:
        return 'Get-History'
    if parts[0] in ('history', '/bin/history', '/usr/bin/history'):
        parts = parts[1:]
    if not parts:
        return 'Get-History'
    flags: Set[str] = set()
    long_flags: Set[str] = set()
    option_values: dict = {}
    positional_args: List[str] = []
    i = 0
    while i < len(parts):
        part = parts[i]
        if part == '--':
            positional_args.extend(parts[i + 1:])
            break
        if part.startswith('/') and len(part) >= 2:
            if len(part) == 2 and part[1].isalpha():
                part = '-' + part[1:]
            elif len(part) > 2 and part[1].isalpha():
                part = '--' + part[1:]
        if part.startswith('--'):
            long_opt = part[2:]
            if '=' in long_opt:
                opt_name, opt_value = long_opt.split('=', 1)
                long_flags.add(opt_name)
                option_values[opt_name] = opt_value
            else:
                long_flags.add(long_opt)
            i += 1
            continue
        if part.startswith('-') and len(part) > 1:
            opt_chars = part[1:]
            if len(opt_chars) == 1 and opt_chars in 'dpsanrw' and i + 1 < len(parts):
                flags.add(opt_chars)
                i += 1
                if i < len(parts):
                    option_values[opt_chars] = parts[i]
            else:
                for char in opt_chars:
                    flags.add(char)
            i += 1
            continue
        positional_args.append(part)
        i += 1
    if 'c' in flags:
        return 'Clear-History'
    if 'd' in flags:
        offset = option_values.get('d')
        if offset:
            return f'Clear-History -Id {offset}'
        else:
            return 'Clear-History'
    if 'w' in flags:
        filename = option_values.get('w')
        if filename:
            return f'Get-History | Export-Clixml {filename}'
        else:
            return 'Get-History | Export-Clixml (Get-PSReadlineOption).HistorySavePath'
    if 'a' in flags:
        filename = option_values.get('a')
        if filename:
            return f'Get-History | Export-Clixml -Append {filename}'
        else:
            return 'Get-History | Export-Clixml -Append (Get-PSReadlineOption).HistorySavePath'
    if 'r' in flags:
        filename = option_values.get('r')
        if filename:
            return f'Import-Clixml {filename} | Add-History'
        else:
            return 'Import-Clixml (Get-PSReadlineOption).HistorySavePath | Add-History'
    if 'n' in flags:
        return 'Get-History'
    if 'p' in flags:
        return '# History expansion (-p) is not supported in PowerShell'
    if 's' in flags:
        entry = option_values.get('s')
        if entry:
            return f'Add-History -CommandLine "{entry}"'
        elif positional_args:
            return f'Add-History -CommandLine "{" ".join(positional_args)}"'
        else:
            return 'Add-History'
    if positional_args:
        first_arg = positional_args[0]
        try:
            count = int(first_arg)
            if count > 0:
                return f'Get-History -Count {count}'
        except ValueError:
            pass
        return 'Get-History'
    return 'Get-History'
def _convert_host(cmd: str) -> str:
    if not cmd or not cmd.strip():
        return 'Write-Output "usage: host [-aCdlnrsTwv] [-c class] [-N ndots] [-R number] [-t type] [-W time] [-m flag] [-p port] hostname [server]"'
    parts = _parse_command_line(cmd)
    if not parts:
        return 'Write-Output "usage: host [-aCdlnrsTwv] [-c class] [-N ndots] [-R number] [-t type] [-W time] [-m flag] [-p port] hostname [server]"'
    if parts[0] in ('host', '/usr/bin/host', '/bin/host'):
        parts = parts[1:]
    if not parts:
        return 'Write-Output "usage: host [-aCdlnrsTwv] [-c class] [-N ndots] [-R number] [-t type] [-W time] [-m flag] [-p port] hostname [server]"'
    options: Dict[str, Any] = {
        'all': False,
        'soa_check': False,
        'class': None,
        'ndots': None,
        'recurse': True,
        'retries': None,
        'query_type': None,
        'timeout': None,
        'tcp': False,
        'verbose': False,
        'list_zone': False,
        'no_search': False,
        'use_search': False,
        'port': None,
        'ipv4': False,
        'ipv6': False,
        'help': False,
        'version': False,
    }
    target: Optional[str] = None
    server: Optional[str] = None
    VALID_QUERY_TYPES = {
        'A', 'AAAA', 'AFSDB', 'APL', 'CAA', 'CDNSKEY', 'CDS', 'CERT', 'CNAME',
        'CSYNC', 'DHCID', 'DLV', 'DNAME', 'DNSKEY', 'DS', 'EUI48', 'EUI64',
        'HINFO', 'HIP', 'HTTPS', 'IPSECKEY', 'KEY', 'KX', 'LOC', 'MX', 'NAPTR',
        'NS', 'NSEC', 'NSEC3', 'NSEC3PARAM', 'OPENPGPKEY', 'PTR', 'RP', 'RRSIG',
        'SIG', 'SMIMEA', 'SOA', 'SRV', 'SSHFP', 'SVCB', 'TA', 'TKEY', 'TLSA',
        'TSIG', 'TXT', 'URI', 'ZONEMD', 'ANY', 'AXFR', 'IXFR', 'OPT'
    }
    LONG_BOOL_OPTS = {
        'all', 'soa-check', 'C', 'recurse', 'r', 'tcp', 'T', 'verbose', 'v', 'd',
        'list-zone', 'l', 'no-search', 'n', 'use-search', 'N', 'ipv4', '4',
        'ipv6', '6', 'help', 'h', 'version', 'V'
    }
    LONG_VALUE_OPTS = {
        'class', 'c', 'ndots', 'N', 'retries', 'R', 'type', 't', 'wait', 'W',
        'port', 'p'
    }
    i = 0
    while i < len(parts):
        part = parts[i]
        if part == '--':
            i += 1
            if i < len(parts):
                target = parts[i]
                i += 1
            if i < len(parts):
                server = parts[i]
            break
        if part.startswith('/') and len(part) >= 2:
            opt_part = part[1:]
            if '=' in opt_part:
                opt_name = opt_part.split('=', 1)[0]
                if opt_name in LONG_VALUE_OPTS:
                    part = '-' + opt_part
                elif opt_name in LONG_BOOL_OPTS:
                    part = '-' + opt_part
            elif opt_part in LONG_BOOL_OPTS:
                part = '-' + opt_part
            elif opt_part in LONG_VALUE_OPTS:
                if i + 1 < len(parts) and not parts[i + 1].startswith('-') and not parts[i + 1].startswith('/'):
                    part = '-' + opt_part
                else:
                    part = '-' + opt_part
            elif len(opt_part) == 1 and opt_part.isalpha():
                part = '-' + opt_part
        if (part.startswith('-') or part.startswith('--')) and '=' in part:
            if part.startswith('--'):
                opt_name, opt_value = part[2:].split('=', 1)
            else:
                opt_name, opt_value = part[1:].split('=', 1)
            if opt_name in ('type', 't'):
                options['query_type'] = opt_value.upper()
                i += 1
                continue
            elif opt_name in ('class', 'c'):
                options['class'] = opt_value.upper()
                i += 1
                continue
            elif opt_name in ('retries', 'R'):
                options['retries'] = opt_value
                i += 1
                continue
            elif opt_name in ('wait', 'W'):
                options['timeout'] = opt_value
                i += 1
                continue
            elif opt_name in ('port', 'p'):
                options['port'] = opt_value
                i += 1
                continue
            elif opt_name in ('ndots', 'N'):
                options['ndots'] = opt_value
                i += 1
                continue
        if part.startswith('--'):
            long_opt = part[2:]
            if long_opt in ('help', 'h'):
                options['help'] = True
                i += 1
                continue
            elif long_opt in ('version', 'V'):
                options['version'] = True
                i += 1
                continue
            elif long_opt == 'all':
                options['all'] = True
                i += 1
                continue
            elif long_opt in ('soa-check', 'C'):
                options['soa_check'] = True
                i += 1
                continue
            elif long_opt == 'recurse':
                options['recurse'] = True
                i += 1
                continue
            elif long_opt == 'tcp':
                options['tcp'] = True
                i += 1
                continue
            elif long_opt in ('verbose', 'v', 'd'):
                options['verbose'] = True
                i += 1
                continue
            elif long_opt in ('list-zone', 'l'):
                options['list_zone'] = True
                i += 1
                continue
            elif long_opt == 'no-search':
                options['no_search'] = True
                i += 1
                continue
            elif long_opt == 'use-search':
                options['use_search'] = True
                i += 1
                continue
            elif long_opt in ('ipv4', '4'):
                options['ipv4'] = True
                i += 1
                continue
            elif long_opt in ('ipv6', '6'):
                options['ipv6'] = True
                i += 1
                continue
            elif long_opt in ('type', 't'):
                if i + 1 < len(parts):
                    i += 1
                    options['query_type'] = parts[i].upper()
                i += 1
                continue
            elif long_opt in ('class', 'c'):
                if i + 1 < len(parts):
                    i += 1
                    options['class'] = parts[i].upper()
                i += 1
                continue
            elif long_opt in ('retries', 'R'):
                if i + 1 < len(parts):
                    i += 1
                    options['retries'] = parts[i]
                i += 1
                continue
            elif long_opt in ('wait', 'W'):
                if i + 1 < len(parts):
                    i += 1
                    options['timeout'] = parts[i]
                i += 1
                continue
            elif long_opt in ('port', 'p'):
                if i + 1 < len(parts):
                    i += 1
                    options['port'] = parts[i]
                i += 1
                continue
            elif long_opt in ('ndots', 'N'):
                if i + 1 < len(parts):
                    i += 1
                    options['ndots'] = parts[i]
                i += 1
                continue
            i += 1
            continue
        if part.startswith('-') and len(part) > 1:
            opt_chars = part[1:]
            if opt_chars in ('all', 'recurse', 'tcp', 'verbose', 'list-zone',
                           'no-search', 'use-search', 'ipv4', 'ipv6',
                           'soa-check', 'version'):
                if opt_chars == 'all':
                    options['all'] = True
                elif opt_chars == 'recurse':
                    options['recurse'] = True
                elif opt_chars == 'tcp':
                    options['tcp'] = True
                elif opt_chars in ('verbose', 'v', 'd'):
                    options['verbose'] = True
                elif opt_chars == 'list-zone':
                    options['list_zone'] = True
                elif opt_chars == 'no-search':
                    options['no_search'] = True
                elif opt_chars == 'use-search':
                    options['use_search'] = True
                elif opt_chars == 'ipv4':
                    options['ipv4'] = True
                elif opt_chars == 'ipv6':
                    options['ipv6'] = True
                elif opt_chars == 'soa-check':
                    options['soa_check'] = True
                elif opt_chars == 'version':
                    options['version'] = True
                i += 1
                continue
            j = 0
            while j < len(opt_chars):
                char = opt_chars[j]
                if char == 'a':
                    options['all'] = True
                    j += 1
                elif char == 'C':
                    options['soa_check'] = True
                    j += 1
                elif char == 'c':
                    if j + 1 < len(opt_chars):
                        options['class'] = opt_chars[j + 1:].upper()
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                        options['class'] = parts[i].upper()
                    j += 1
                elif char == 'd':
                    options['verbose'] = True
                    j += 1
                elif char == 'l':
                    options['list_zone'] = True
                    j += 1
                elif char == 'N':
                    if j + 1 < len(opt_chars):
                        val = opt_chars[j + 1:]
                        if val.isdigit():
                            options['ndots'] = val
                        else:
                            options['use_search'] = True
                        j = len(opt_chars)
                    elif i + 1 < len(parts) and parts[i + 1].isdigit():
                        i += 1
                        options['ndots'] = parts[i]
                    else:
                        options['use_search'] = True
                    j += 1
                elif char == 'n':
                    options['no_search'] = True
                    j += 1
                elif char == 'p':
                    if j + 1 < len(opt_chars):
                        options['port'] = opt_chars[j + 1:]
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                        options['port'] = parts[i]
                    j += 1
                elif char == 'r':
                    options['recurse'] = False
                    j += 1
                elif char == 'R':
                    if j + 1 < len(opt_chars):
                        options['retries'] = opt_chars[j + 1:]
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                        options['retries'] = parts[i]
                    j += 1
                elif char == 's':
                    j += 1
                elif char == 't':
                    if j + 1 < len(opt_chars):
                        options['query_type'] = opt_chars[j + 1:].upper()
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                        options['query_type'] = parts[i].upper()
                    j += 1
                elif char == 'T':
                    options['tcp'] = True
                    j += 1
                elif char == 'v':
                    options['verbose'] = True
                    j += 1
                elif char == 'w':
                    j += 1
                elif char == 'W':
                    if j + 1 < len(opt_chars):
                        options['timeout'] = opt_chars[j + 1:]
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                        options['timeout'] = parts[i]
                    j += 1
                elif char == '4':
                    options['ipv4'] = True
                    j += 1
                elif char == '6':
                    options['ipv6'] = True
                    j += 1
                elif char == 'h':
                    options['help'] = True
                    j += 1
                elif char == 'V':
                    options['version'] = True
                    j += 1
                else:
                    j += 1
            i += 1
            continue
        if target is None:
            target = part
            i += 1
        elif server is None:
            server = part
            i += 1
        else:
            i += 1
    if options['help']:
        return (
            'Write-Output "host - DNS lookup utility\n'
            'Usage: host [-aCdlnrsTwv] [-c class] [-N ndots] [-R number] [-t type] [-W time] [-m flag] [-p port] hostname [server]\n'
            'Options:\n'
            '  -a              Query for all records (equivalent to -v -t ANY)\n'
            '  -C              Check SOA records\n'
            '  -c class        Query class (IN, CH, HS, etc.)\n'
            '  -d, -v          Verbose output\n'
            '  -l              List zone (AXFR)\n'
            '  -n              Do not use search list\n'
            '  -N ndots        Set number of dots for search\n'
            '  -p port         Use specific port\n'
            '  -r              Do not use recursion\n'
            '  -R number       Set number of retries\n'
            '  -t type         Query type (A, MX, NS, SOA, TXT, etc.)\n'
            '  -T              Use TCP\n'
            '  -W time         Set timeout in seconds\n'
            '  -4              Use IPv4 only\n'
            '  -6              Use IPv6 only\n'
            '  -h, --help      Show help\n'
            '  -V, --version   Show version"'
        )
    if options['version']:
        return 'Write-Output "host (bind-utils)"'
    if target is None:
        return 'Write-Output "usage: host [-aCdlnrsTwv] [-c class] [-N ndots] [-R number] [-t type] [-W time] [-m flag] [-p port] hostname [server]"'
    ps_args: List[str] = []
    ps_args.append(target)
    if server:
        ps_args.append(f'-Server {server}')
    if options['query_type']:
        query_type = options['query_type']
        if query_type in VALID_QUERY_TYPES:
            ps_args.append(f'-Type {query_type}')
        else:
            ps_args.append(f'-Type {query_type}')
    elif options['all']:
        ps_args.append('-Type ANY')
    elif options['soa_check']:
        ps_args.append('-Type SOA')
    cmd_str = 'Resolve-DnsName ' + ' '.join(ps_args)
    return cmd_str
if __name__ == "__main__":
    test_cases = [
        "host google.com",
        "host 8.8.8.8",
        "host google.com 8.8.8.8",
        "host -t MX google.com",
        "host -t A google.com",
        "host -t NS google.com",
        "host -t SOA google.com",
        "host -t TXT google.com",
        "host -t AAAA google.com",
        "host -t ANY google.com",
        "host --type=MX google.com",
        "host --type MX google.com",
        "host -tMX google.com",
        "host -a google.com",
        "host --all google.com",
        "host -C google.com",
        "host --soa-check google.com",
        "host -c IN google.com",
        "host -cIN google.com",
        "host --class IN google.com",
        "host --class=IN google.com",
        "host -v google.com",
        "host -d google.com",
        "host --verbose google.com",
        "host -r google.com",
        "host --recurse google.com",
        "host -T google.com",
        "host --tcp google.com",
        "host -l google.com",
        "host --list-zone google.com",
        "host -n google.com",
        "host --no-search google.com",
        "host -N google.com",
        "host --use-search google.com",
        "host -R 3 google.com",
        "host -R3 google.com",
        "host --retries 3 google.com",
        "host --retries=3 google.com",
        "host -W 5 google.com",
        "host -W5 google.com",
        "host --wait 5 google.com",
        "host --wait=5 google.com",
        "host -p 53 google.com",
        "host -p53 google.com",
        "host --port 53 google.com",
        "host --port=53 google.com",
        "host -4 google.com",
        "host --ipv4 google.com",
        "host -6 google.com",
        "host --ipv6 google.com",
        "host -N 2 google.com",
        "host --ndots 2 google.com",
        "host -h",
        "host --help",
        "host -V",
        "host --version",
        "host /t MX google.com",
        "host /a google.com",
        "host /v google.com",
        "host /help",
        "host /version",
        "host -t MX -T google.com",
        "host -v -t A google.com 8.8.8.8",
        "host -4 -t A google.com",
        "",
        "host",
    ]
    for test in test_cases:
        result = _convert_host(test)
        print(f"Input:  {test}")
        print(f"Output: {result}")
        print()
def _convert_hostname(cmd: str) -> str:
    if not cmd or not cmd.strip():
        return '[System.Net.Dns]::GetHostName()'
    parts = _parse_command_line(cmd)
    if not parts:
        return '[System.Net.Dns]::GetHostName()'
    if parts[0] in ('hostname', '/bin/hostname', '/usr/bin/hostname'):
        parts = parts[1:]
    if not parts:
        return '[System.Net.Dns]::GetHostName()'
    show_alias = False
    show_domain = False
    show_fqdn = False
    show_ip = False
    show_node = False
    show_short = False
    show_version = False
    show_help = False
    show_verbose = False
    show_nis = False
    file_name: Optional[str] = None
    new_hostname: Optional[str] = None
    i = 0
    while i < len(parts):
        part = parts[i]
        if part == '--':
            if i + 1 < len(parts):
                new_hostname = parts[i + 1]
            break
        if part.startswith('/') and len(part) >= 2:
            if len(part) == 2 and part[1].isalpha():
                part = '-' + part[1:]
            elif len(part) > 2 and part[1].isalpha():
                part = '--' + part[1:]
        if part.startswith('--'):
            long_opt = part[2:]
            if long_opt == 'help':
                show_help = True
                i += 1
                continue
            if long_opt == 'version':
                show_version = True
                i += 1
                continue
            if long_opt == 'alias':
                show_alias = True
                i += 1
                continue
            if long_opt == 'domain':
                show_domain = True
                i += 1
                continue
            if long_opt in ('fqdn', 'long'):
                show_fqdn = True
                i += 1
                continue
            if long_opt == 'ip-address':
                show_ip = True
                i += 1
                continue
            if long_opt == 'node':
                show_node = True
                i += 1
                continue
            if long_opt == 'short':
                show_short = True
                i += 1
                continue
            if long_opt == 'verbose':
                show_verbose = True
                i += 1
                continue
            if long_opt in ('yp', 'nis'):
                show_nis = True
                i += 1
                continue
            if long_opt.startswith('file='):
                file_name = long_opt.split('=', 1)[1]
                i += 1
                continue
            elif long_opt == 'file':
                if i + 1 < len(parts):
                    i += 1
                    file_name = parts[i]
                i += 1
                continue
            i += 1
            continue
        if part.startswith('-') and len(part) > 1:
            opt_chars = part[1:]
            j = 0
            while j < len(opt_chars):
                char = opt_chars[j]
                if char == 'a':
                    show_alias = True
                    j += 1
                elif char == 'd':
                    show_domain = True
                    j += 1
                elif char == 'f':
                    show_fqdn = True
                    j += 1
                elif char == 'F':
                    if j + 1 < len(opt_chars):
                        file_name = opt_chars[j + 1:]
                        break
                    elif i + 1 < len(parts):
                        i += 1
                        file_name = parts[i]
                    j += 1
                elif char == 'h':
                    show_help = True
                    j += 1
                elif char == 'i':
                    show_ip = True
                    j += 1
                elif char == 'n':
                    show_node = True
                    j += 1
                elif char == 's':
                    show_short = True
                    j += 1
                elif char == 'V':
                    show_version = True
                    j += 1
                elif char == 'v':
                    show_verbose = True
                    j += 1
                elif char == 'y':
                    show_nis = True
                    j += 1
                else:
                    j += 1
            i += 1
            continue
        new_hostname = part
        i += 1
    return _build_hostname_powershell_command(
        show_alias, show_domain, show_fqdn, show_ip, show_node,
        show_short, show_version, show_help, show_verbose, show_nis,
        file_name, new_hostname
    )
def _build_hostname_powershell_command(
    show_alias: bool,
    show_domain: bool,
    show_fqdn: bool,
    show_ip: bool,
    show_node: bool,
    show_short: bool,
    show_version: bool,
    show_help: bool,
    show_verbose: bool,
    show_nis: bool,
    file_name: Optional[str],
    new_hostname: Optional[str]
) -> str:
    if show_help:
        return ('Write-Output "hostname - show or set the system\'s host name\n'
                'Usage: hostname [OPTION]... [NAME]\n'
                'Options:\n'
                '  -a, --alias            Display the alias name of the host\n'
                '  -d, --domain           Display the name of the DNS domain\n'
                '  -f, --fqdn, --long     Display the FQDN (Fully Qualified Domain Name)\n'
                '  -F, --file FILE        Read the new host name from FILE\n'
                '  -h, --help             Print this help and exit\n'
                '  -i, --ip-address       Display the IP address(es) of the host\n'
                '  -n, --node             Display the DECnet node name\n'
                '  -s, --short            Display the short host name\n'
                '  -V, --version          Print version and exit\n'
                '  -v, --verbose          Be verbose\n'
                '  -y, --yp, --nis        Display the NIS domain name\n'
                '  NAME                   Set the hostname to NAME (requires admin)"')
    if show_version:
        return 'Write-Output "hostname (net-tools) 2.10"'
    if file_name:
        file_name_escaped = file_name.replace("'", "''")
        if new_hostname:
            new_hostname_escaped = new_hostname.replace("'", "''")
            return f'Rename-Computer -NewName "{new_hostname_escaped}" -Restart'
        return (f'$newHostname = (Get-Content -Path "{file_name_escaped}" -TotalCount 1).Trim(); '
                f'Rename-Computer -NewName $newHostname -Restart')
    if new_hostname:
        new_hostname_escaped = new_hostname.replace("'", "''")
        return f'Rename-Computer -NewName "{new_hostname_escaped}" -Restart'
    if show_fqdn:
        return '[System.Net.Dns]::GetHostByName($env:COMPUTERNAME).HostName'
    if show_domain:
        return '(Get-WmiObject -Class Win32_ComputerSystem).Domain'
    if show_ip:
        return '[System.Net.Dns]::GetHostAddresses($env:COMPUTERNAME) | ForEach-Object { $_.IPAddressToString }'
    if show_short:
        return '$env:COMPUTERNAME'
    if show_alias:
        return '[System.Net.Dns]::GetHostName()'
    if show_node:
        return '$env:COMPUTERNAME'
    if show_nis:
        return '(Get-WmiObject -Class Win32_ComputerSystem).Domain'
    return '[System.Net.Dns]::GetHostName()'
def _convert_id(cmd: str) -> str:
    if not cmd or not cmd.strip():
        return _build_default_id_command()
    parts = _parse_command_line(cmd)
    if not parts:
        return _build_default_id_command()
    if parts[0] in ('id', '/bin/id', '/usr/bin/id'):
        parts = parts[1:]
    if not parts:
        return _build_default_id_command()
    show_group = False
    show_groups = False
    show_user = False
    use_name = False
    use_real = False
    use_zero_delim = False
    show_help = False
    show_version = False
    target_user: Optional[str] = None
    i = 0
    while i < len(parts):
        part = parts[i]
        if part == '--':
            if i + 1 < len(parts):
                target_user = parts[i + 1]
            break
        if part.startswith('/') and len(part) >= 2 and part[1].isalpha():
            if len(part) == 2:
                part = '-' + part[1:]
            else:
                sub_part = part[1:]
                if '=' in sub_part:
                    part = '--' + sub_part
                elif sub_part in ('group', 'groups', 'name', 'real', 'user', 'zero', 'help', 'version'):
                    part = '--' + sub_part
                else:
                    part = '-' + sub_part
        if part.startswith('--'):
            long_opt = part[2:]
            if long_opt == 'help':
                show_help = True
                i += 1
                continue
            elif long_opt == 'version':
                show_version = True
                i += 1
                continue
            elif long_opt == 'group':
                show_group = True
                i += 1
                continue
            elif long_opt == 'groups':
                show_groups = True
                i += 1
                continue
            elif long_opt == 'name':
                use_name = True
                i += 1
                continue
            elif long_opt == 'real':
                use_real = True
                i += 1
                continue
            elif long_opt == 'user':
                show_user = True
                i += 1
                continue
            elif long_opt == 'zero':
                use_zero_delim = True
                i += 1
                continue
            i += 1
            continue
        if part.startswith('-') and len(part) > 1:
            opt_chars = part[1:]
            for char in opt_chars:
                if char == 'a':
                    pass
                elif char == 'g':
                    show_group = True
                elif char == 'G':
                    show_groups = True
                elif char == 'n':
                    use_name = True
                elif char == 'r':
                    use_real = True
                elif char == 'u':
                    show_user = True
                elif char == 'z':
                    use_zero_delim = True
            i += 1
            continue
        target_user = part
        i += 1
    if show_help:
        return (
            'Write-Output "Usage: id [OPTION]... [USER]...\n'
            'Print user and group information for the specified USER,\n'
            ' or (when USER omitted) for the current user.\n\n'
            '  -a             ignore, for compatibility with other versions\n'
            '  -g, --group    print only the effective group ID\n'
            '  -G, --groups   print all group IDs\n'
            '  -n, --name     print a name instead of a number, for -ugG\n'
            '  -r, --real     print the real ID instead of the effective ID, for -ugG\n'
            '  -u, --user     print only the effective user ID\n'
            '  -z, --zero     delimit entries with NUL characters, not whitespace\n'
            '      --help     display this help and exit\n'
            '      --version  output version information and exit"'
        )
    if show_version:
        return 'Write-Output "id (GNU coreutils) 8.32"'
    return _build_id_powershell_command(
        show_group, show_groups, show_user, use_name, use_real,
        use_zero_delim, target_user
    )
def _build_default_id_command() -> str:
    return (
        '$currentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent(); '
        'Write-Output "uid=$($currentUser.User.Value)($($currentUser.Name)) '
        'gid=$($currentUser.Groups[0].Value)($($currentUser.Groups[0].Translate([System.Security.Principal.NTAccount]).Value)) '
        'groups=$($currentUser.Groups | ForEach-Object { \"$($_.Value)($($_.Translate([System.Security.Principal.NTAccount]).Value))\" } | Join-String -Separator \", \")"'
    )
def _build_id_powershell_command(
    show_group: bool,
    show_groups: bool,
    show_user: bool,
    use_name: bool,
    use_real: bool,
    use_zero_delim: bool,
    target_user: Optional[str]
) -> str:
    delim = '\\0' if use_zero_delim else '\\n'
    if not any([show_group, show_groups, show_user]):
        if target_user:
            return (
                f'$targetUser = New-Object System.Security.Principal.NTAccount("{target_user}"); '
                '$userSid = $targetUser.Translate([System.Security.Principal.SecurityIdentifier]); '
                'Write-Output "uid=$($userSid.Value)($target_user)"'
            )
        return _build_default_id_command()
    if show_user:
        if use_name:
            if target_user:
                return f'Write-Output "{target_user}"'
            return '$env:USERNAME'
        else:
            if target_user:
                return (
                    f'(New-Object System.Security.Principal.NTAccount("{target_user}")).Translate([System.Security.Principal.SecurityIdentifier]).Value'
                )
            return '[System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value'
    if show_group:
        if use_name:
            if target_user:
                return (
                    f'$user = (New-Object System.Security.Principal.NTAccount("{target_user}")).Translate([System.Security.Principal.SecurityIdentifier]); '
                    '$groupSid = ([System.Security.Principal.WindowsIdentity]::GetUserGroups($user) | Select-Object -First 1); '
                    '$groupSid.Translate([System.Security.Principal.NTAccount]).Value.Split("\\")[1]'
                )
            return (
                '$currentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent(); '
                '$currentUser.Groups[0].Translate([System.Security.Principal.NTAccount]).Value.Split("\\")[1]'
            )
        else:
            if target_user:
                return (
                    f'$user = (New-Object System.Security.Principal.NTAccount("{target_user}")).Translate([System.Security.Principal.SecurityIdentifier]); '
                    '([System.Security.Principal.WindowsIdentity]::GetUserGroups($user) | Select-Object -First 1).Value'
                )
            return (
                '$currentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent(); '
                '$currentUser.Groups[0].Value'
            )
    if show_groups:
        if use_name:
            if target_user:
                return (
                    f'$user = (New-Object System.Security.Principal.NTAccount("{target_user}")).Translate([System.Security.Principal.SecurityIdentifier]); '
                    f'[System.Security.Principal.WindowsIdentity]::GetUserGroups($user) | ForEach-Object {{ $_.Translate([System.Security.Principal.NTAccount]).Value.Split("\\")[1] }} | Join-String -Separator "{delim}"'
                )
            return (
                '[System.Security.Principal.WindowsIdentity]::GetCurrent().Groups | '
                f'ForEach-Object {{ $_.Translate([System.Security.Principal.NTAccount]).Value.Split("\\")[1] }} | Join-String -Separator "{delim}"'
            )
        else:
            if target_user:
                return (
                    f'$user = (New-Object System.Security.Principal.NTAccount("{target_user}")).Translate([System.Security.Principal.SecurityIdentifier]); '
                    f'[System.Security.Principal.WindowsIdentity]::GetUserGroups($user) | ForEach-Object {{ $_.Value }} | Join-String -Separator "{delim}"'
                )
            return (
                '[System.Security.Principal.WindowsIdentity]::GetCurrent().Groups | '
                f'ForEach-Object {{ $_.Value }} | Join-String -Separator "{delim}"'
            )
    return _build_default_id_command()
def _convert_ifconfig(cmd: str) -> str:
    if not cmd or not cmd.strip():
        return _build_default_display_command()
    parts = _parse_command_line(cmd)
    if not parts:
        return _build_default_display_command()
    if parts[0] in ('ifconfig', '/sbin/ifconfig', '/usr/sbin/ifconfig', '/bin/ifconfig'):
        parts = parts[1:]
    if not parts:
        return _build_default_display_command()
    show_all = False
    show_short = False
    verbose = False
    i = 0
    while i < len(parts):
        part = parts[i]
        if part.startswith('/') and len(part) >= 2:
            if len(part) == 2 and part[1].isalpha():
                part = '-' + part[1:]
            elif len(part) > 2 and part[1].isalpha():
                part = '--' + part[1:]
        if part == '-a' or part == '--all':
            show_all = True
            i += 1
            continue
        elif part == '-s':
            show_short = True
            i += 1
            continue
        elif part == '-v':
            verbose = True
            i += 1
            continue
        elif part.startswith('-'):
            i += 1
            continue
        else:
            break
        i += 1
    if i >= len(parts):
        if show_short:
            return _build_short_list_command(show_all)
        return _build_display_all_command(show_all)
    interface = parts[i]
    i += 1
    if i >= len(parts):
        return _build_interface_display_command(interface)
    return _parse_interface_config(interface, parts[i:])
def _build_default_display_command() -> str:
    return (
        'Get-NetAdapter | Where-Object { $_.Status -eq "Up" } | '
        'Get-NetIPAddress | '
        'Select-Object InterfaceAlias, IPAddress, AddressFamily, PrefixLength'
    )
def _build_display_all_command(show_all: bool) -> str:
    if show_all:
        return (
            'Get-NetAdapter | '
            'Get-NetIPAddress | '
            'Select-Object InterfaceAlias, IPAddress, AddressFamily, PrefixLength'
        )
    else:
        return (
            'Get-NetAdapter | Where-Object { $_.Status -eq "Up" } | '
            'Get-NetIPAddress | '
            'Select-Object InterfaceAlias, IPAddress, AddressFamily, PrefixLength'
        )
def _build_short_list_command(show_all: bool) -> str:
    if show_all:
        return (
            'Get-NetAdapter | '
            'Select-Object Name, MtuSize, '
            '@{Name="RX-OK"; Expression={$_.ReceivedPackets}}, '
            '@{Name="RX-ERR"; Expression={$_.ReceivedPacketErrors}}, '
            '@{Name="TX-OK"; Expression={$_.SentPackets}}, '
            '@{Name="TX-ERR"; Expression={$_.OutboundPacketErrors}}, '
            'Status'
        )
    else:
        return (
            'Get-NetAdapter | Where-Object { $_.Status -eq "Up" } | '
            'Select-Object Name, MtuSize, '
            '@{Name="RX-OK"; Expression={$_.ReceivedPackets}}, '
            '@{Name="RX-ERR"; Expression={$_.ReceivedPacketErrors}}, '
            '@{Name="TX-OK"; Expression={$_.SentPackets}}, '
            '@{Name="TX-ERR"; Expression={$_.OutboundPacketErrors}}, '
            'Status'
        )
def _build_interface_display_command(interface: str) -> str:
    interface_escaped = interface.replace('"', '`"')
    return (
        f'Get-NetAdapter -Name "{interface_escaped}" | '
        f'Get-NetIPAddress | '
        f'Select-Object InterfaceAlias, IPAddress, AddressFamily, PrefixLength'
    )
def _parse_interface_config(interface: str, args: List[str]) -> str:
    if not args:
        return _build_interface_display_command(interface)
    if len(args) == 1:
        arg = args[0].lower()
        if arg == 'up':
            return _build_interface_up_command(interface)
        elif arg == 'down':
            return _build_interface_down_command(interface)
    config = {
        'ip_address': None,
        'prefix_length': None,
        'netmask': None,
        'broadcast': None,
        'mtu': None,
        'mac_address': None,
        'arp': None,
        'promisc': None,
        'allmulti': None,
        'pointopoint': None,
        'pointopoint_addr': None,
        'multicast': False,
        'txqueuelen': None,
        'add_addresses': [],
        'del_addresses': [],
        'new_name': None,
    }
    i = 0
    while i < len(args):
        arg = args[i]
        arg_lower = arg.lower()
        if arg_lower in ('inet', 'inet6', 'ax25', 'ddp', 'ipx', 'netrom'):
            i += 1
            continue
        if arg_lower == 'up':
            i += 1
            continue
        elif arg_lower == 'down':
            i += 1
            continue
        if arg_lower == 'arp':
            config['arp'] = True
            i += 1
            continue
        elif arg_lower == '-arp':
            config['arp'] = False
            i += 1
            continue
        if arg_lower == 'promisc':
            config['promisc'] = True
            i += 1
            continue
        elif arg_lower == '-promisc':
            config['promisc'] = False
            i += 1
            continue
        if arg_lower == 'allmulti':
            config['allmulti'] = True
            i += 1
            continue
        elif arg_lower == '-allmulti':
            config['allmulti'] = False
            i += 1
            continue
        if arg_lower == 'multicast':
            config['multicast'] = True
            i += 1
            continue
        if arg_lower == 'pointopoint':
            config['pointopoint'] = True
            if i + 1 < len(args) and not args[i + 1].startswith('-'):
                i += 1
                config['pointopoint_addr'] = args[i]
            i += 1
            continue
        elif arg_lower == '-pointopoint':
            config['pointopoint'] = False
            i += 1
            continue
        if arg_lower == 'netmask':
            if i + 1 < len(args):
                i += 1
                config['netmask'] = args[i]
                config['prefix_length'] = _netmask_to_prefix(args[i])
            i += 1
            continue
        if arg_lower == 'broadcast':
            if i + 1 < len(args):
                i += 1
                config['broadcast'] = args[i]
            i += 1
            continue
        if arg_lower == 'mtu':
            if i + 1 < len(args):
                i += 1
                config['mtu'] = args[i]
            i += 1
            continue
        if arg_lower == 'txqueuelen':
            if i + 1 < len(args):
                i += 1
                config['txqueuelen'] = args[i]
            i += 1
            continue
        if arg_lower == 'hw':
            if i + 2 < len(args):
                i += 1
                hw_class = args[i]
                i += 1
                hw_addr = args[i]
                if hw_class.lower() == 'ether':
                    config['mac_address'] = hw_addr
            i += 1
            continue
        if arg_lower == 'add':
            if i + 1 < len(args):
                i += 1
                config['add_addresses'].append(args[i])
            i += 1
            continue
        if arg_lower == 'del':
            if i + 1 < len(args):
                i += 1
                config['del_addresses'].append(args[i])
            i += 1
            continue
        if arg_lower == 'name':
            if i + 1 < len(args):
                i += 1
                config['new_name'] = args[i]
            i += 1
            continue
        if arg and arg[0].isdigit() and config['ip_address'] is None:
            config['ip_address'] = arg
            if '/' in arg:
                addr, prefix = arg.rsplit('/', 1)
                config['ip_address'] = addr
                config['prefix_length'] = prefix
            i += 1
            continue
        i += 1
    return _build_config_command(interface, config)
def _build_interface_up_command(interface: str) -> str:
    interface_escaped = interface.replace('"', '`"')
    return f'Enable-NetAdapter -Name "{interface_escaped}"'
def _build_interface_down_command(interface: str) -> str:
    interface_escaped = interface.replace('"', '`"')
    return f'Disable-NetAdapter -Name "{interface_escaped}"'
def _netmask_to_prefix(netmask: str) -> Optional[int]:
    try:
        parts = netmask.split('.')
        if len(parts) == 4:
            binary = ''
            for part in parts:
                binary += bin(int(part))[2:].zfill(8)
            return binary.count('1')
    except (ValueError, IndexError):
        pass
    return None
def _build_config_command(interface: str, config: Dict[str, Any]) -> str:
    interface_escaped = interface.replace('"', '`"')
    commands = []
    if config['ip_address']:
        prefix = config['prefix_length'] if config['prefix_length'] else '24'
        ip_escaped = config['ip_address'].replace('"', '`"')
        commands.append(
            f'New-NetIPAddress -InterfaceAlias "{interface_escaped}" '
            f'-IPAddress "{ip_escaped}" -PrefixLength {prefix}'
        )
    for addr in config['add_addresses']:
        if '/' in addr:
            ip, prefix = addr.rsplit('/', 1)
        else:
            ip = addr
            prefix = '24'
        ip_escaped = ip.replace('"', '`"')
        commands.append(
            f'New-NetIPAddress -InterfaceAlias "{interface_escaped}" '
            f'-IPAddress "{ip_escaped}" -PrefixLength {prefix}'
        )
    for addr in config['del_addresses']:
        if '/' in addr:
            ip = addr.rsplit('/', 1)[0]
        else:
            ip = addr
        ip_escaped = ip.replace('"', '`"')
        commands.append(
            f'Remove-NetIPAddress -InterfaceAlias "{interface_escaped}" '
            f'-IPAddress "{ip_escaped}" -Confirm:$false'
        )
    if config['mtu']:
        commands.append(
            f'Set-NetAdapter -Name "{interface_escaped}" -MtuSize {config["mtu"]}'
        )
    if config['mac_address']:
        mac = config['mac_address'].replace(':', '-')
        commands.append(
            f'Set-NetAdapter -Name "{interface_escaped}" -MacAddress "{mac}"'
        )
    if config['arp'] is not None:
        if config['arp']:
            commands.append(
                f'Set-NetIPInterface -InterfaceAlias "{interface_escaped}" -AddressFamily IPv4 '
                f'-NeighborDiscoverySupported Enabled'
            )
        else:
            commands.append(
                f'Set-NetIPInterface -InterfaceAlias "{interface_escaped}" -AddressFamily IPv4 '
                f'-NeighborDiscoverySupported Disabled'
            )
    if config['promisc'] is not None:
        if config['promisc']:
            commands.append(
                f'Set-NetAdapter -Name "{interface_escaped}" -PromiscuousMode Enabled'
            )
        else:
            commands.append(
                f'Set-NetAdapter -Name "{interface_escaped}" -PromiscuousMode Disabled'
            )
    if config['new_name']:
        new_name_escaped = config['new_name'].replace('"', '`"')
        commands.append(
            f'Rename-NetAdapter -Name "{interface_escaped}" -NewName "{new_name_escaped}"'
        )
    if not commands:
        return _build_interface_display_command(interface)
    return '; '.join(commands)
def _convert_ip(cmd: str) -> str:
    if not cmd or not cmd.strip():
        return 'Get-NetIPAddress | Format-Table -AutoSize'
    parts = _parse_command_line(cmd)
    if not parts:
        return 'Get-NetIPAddress | Format-Table -AutoSize'
    if parts[0] in ('ip', '/bin/ip', '/usr/bin/ip', '/sbin/ip', '/usr/sbin/ip'):
        parts = parts[1:]
    if not parts:
        return 'Get-NetIPAddress | Format-Table -AutoSize'
    show_version = False
    show_help = False
    human_readable = False
    batch_file: Optional[str] = None
    force_batch = False
    statistics = 0
    details = False
    loops: Optional[int] = None
    family: Optional[str] = None
    oneline = False
    resolve = False
    netns: Optional[str] = None
    numeric = False
    use_all = False
    color: Optional[str] = None
    timestamp = False
    tshort = False
    rcvbuf: Optional[int] = None
    iec = False
    brief = False
    use_json = False
    pretty = False
    echo = False
    obj: Optional[str] = None
    command: Optional[str] = None
    obj_args: List[str] = []
    i = 0
    while i < len(parts):
        part = parts[i]
        if part == '--':
            obj_args.extend(parts[i + 1:])
            break
        if part.startswith('/') and len(part) >= 2:
            if len(part) == 2:
                part = '-' + part[1:]
            else:
                sub_part = part[1:]
                known_long_opts = {
                    'Version', 'version', 'human', 'human-readable', 'batch', 'force',
                    'stats', 'statistics', 'details', 'loops', 'family',
                    'oneline', 'resolve', 'netns', 'Numeric', 'all', 'color',
                    'timestamp', 'tshort', 'rcvbuf', 'iec', 'brief', 'json',
                    'pretty', 'echo', 'help'
                }
                if '=' in sub_part:
                    part = '--' + sub_part
                elif sub_part in known_long_opts:
                    part = '--' + sub_part
                else:
                    part = '-' + sub_part
        if part.startswith('--'):
            long_opt = part[2:]
            if '=' in long_opt:
                opt_name, opt_value = long_opt.split('=', 1)
                if opt_name == 'family':
                    family = opt_value
                elif opt_name == 'loops':
                    loops = int(opt_value) if opt_value.isdigit() else 10
                elif opt_name == 'netns':
                    netns = opt_value
                elif opt_name == 'rcvbuf':
                    rcvbuf = int(opt_value) if opt_value.isdigit() else None
                elif opt_name == 'batch':
                    batch_file = opt_value
                elif opt_name == 'color':
                    color = opt_value if opt_value else 'always'
                i += 1
                continue
            if long_opt in ('Version', 'version'):
                show_version = True
                i += 1
                continue
            elif long_opt == 'help':
                show_help = True
                i += 1
                continue
            elif long_opt in ('human', 'human-readable'):
                human_readable = True
                i += 1
                continue
            elif long_opt == 'batch':
                if i + 1 < len(parts):
                    i += 1
                    batch_file = parts[i]
                i += 1
                continue
            elif long_opt == 'force':
                force_batch = True
                i += 1
                continue
            elif long_opt in ('stats', 'statistics'):
                statistics += 1
                i += 1
                continue
            elif long_opt == 'details':
                details = True
                i += 1
                continue
            elif long_opt == 'loops':
                if i + 1 < len(parts):
                    i += 1
                    loops = int(parts[i]) if parts[i].isdigit() else 10
                i += 1
                continue
            elif long_opt == 'family':
                if i + 1 < len(parts):
                    i += 1
                    family = parts[i]
                i += 1
                continue
            elif long_opt == 'oneline':
                oneline = True
                i += 1
                continue
            elif long_opt == 'resolve':
                resolve = True
                i += 1
                continue
            elif long_opt == 'netns':
                if i + 1 < len(parts):
                    i += 1
                    netns = parts[i]
                i += 1
                continue
            elif long_opt == 'Numeric':
                numeric = True
                i += 1
                continue
            elif long_opt == 'all':
                use_all = True
                i += 1
                continue
            elif long_opt == 'color':
                color = 'always'
                i += 1
                continue
            elif long_opt == 'timestamp':
                timestamp = True
                i += 1
                continue
            elif long_opt == 'tshort':
                tshort = True
                i += 1
                continue
            elif long_opt == 'rcvbuf':
                if i + 1 < len(parts):
                    i += 1
                    rcvbuf = int(parts[i]) if parts[i].isdigit() else None
                i += 1
                continue
            elif long_opt == 'iec':
                iec = True
                i += 1
                continue
            elif long_opt == 'brief':
                brief = True
                i += 1
                continue
            elif long_opt == 'json':
                use_json = True
                i += 1
                continue
            elif long_opt == 'pretty':
                pretty = True
                i += 1
                continue
            elif long_opt == 'echo':
                echo = True
                i += 1
                continue
            i += 1
            continue
        if part.startswith('-') and len(part) > 1:
            opt_chars = part[1:]
            if opt_chars == 'br':
                brief = True
                i += 1
                continue
            elif opt_chars == 'ts':
                tshort = True
                i += 1
                continue
            elif opt_chars == 'iec':
                iec = True
                i += 1
                continue
            elif opt_chars in ('human', 'human-readable'):
                human_readable = True
                i += 1
                continue
            elif opt_chars in ('stats', 'statistics'):
                statistics += 1
                i += 1
                continue
            elif opt_chars == 'details':
                details = True
                i += 1
                continue
            elif opt_chars == 'oneline':
                oneline = True
                i += 1
                continue
            elif opt_chars == 'resolve':
                resolve = True
                i += 1
                continue
            elif opt_chars == 'Numeric':
                numeric = True
                i += 1
                continue
            elif opt_chars == 'brief':
                brief = True
                i += 1
                continue
            elif opt_chars == 'json':
                use_json = True
                i += 1
                continue
            elif opt_chars == 'pretty':
                pretty = True
                i += 1
                continue
            elif opt_chars == 'echo':
                echo = True
                i += 1
                continue
            elif opt_chars == 'version':
                show_version = True
                i += 1
                continue
            elif opt_chars == 'help':
                show_help = True
                i += 1
                continue
            else:
                j = 0
                while j < len(opt_chars):
                    char = opt_chars[j]
                    if char == 'V':
                        show_version = True
                        j += 1
                    elif char == 'h':
                        human_readable = True
                        j += 1
                    elif char == 's':
                        statistics += 1
                        j += 1
                    elif char == 'd':
                        details = True
                        j += 1
                    elif char == 'l':
                        if j + 1 < len(opt_chars):
                            val = opt_chars[j + 1:]
                            if val.isdigit():
                                loops = int(val)
                                break
                        elif i + 1 < len(parts) and parts[i + 1].isdigit():
                            i += 1
                            loops = int(parts[i])
                        j += 1
                    elif char == 'f':
                        if j + 1 < len(opt_chars):
                            val = opt_chars[j + 1:]
                            family = val
                            break
                        elif i + 1 < len(parts):
                            i += 1
                            family = parts[i]
                        j += 1
                    elif char == '4':
                        family = 'inet'
                        j += 1
                    elif char == '6':
                        family = 'inet6'
                        j += 1
                    elif char == 'B':
                        family = 'bridge'
                        j += 1
                    elif char == 'M':
                        family = 'mpls'
                        j += 1
                    elif char == '0':
                        family = 'link'
                        j += 1
                    elif char == 'o':
                        oneline = True
                        j += 1
                    elif char == 'r':
                        resolve = True
                        j += 1
                    elif char == 'n':
                        if j + 1 < len(opt_chars):
                            val = opt_chars[j + 1:]
                            netns = val
                            break
                        elif i + 1 < len(parts) and not parts[i + 1].startswith('-'):
                            i += 1
                            netns = parts[i]
                        j += 1
                    elif char == 'N':
                        numeric = True
                        j += 1
                    elif char == 'a':
                        use_all = True
                        j += 1
                    elif char == 'c':
                        color = 'always'
                        j += 1
                    elif char == 't':
                        timestamp = True
                        j += 1
                    elif char == 'b':
                        if j + 1 < len(opt_chars):
                            val = opt_chars[j + 1:]
                            batch_file = val
                            break
                        elif i + 1 < len(parts):
                            i += 1
                            batch_file = parts[i]
                        j += 1
                    elif char == 'j':
                        use_json = True
                        j += 1
                    elif char == 'p':
                        pretty = True
                        j += 1
                    else:
                        j += 1
                i += 1
                continue
        if obj is None:
            if part.lower() == 'help':
                show_help = True
                i += 1
                continue
            obj = part
            i += 1
            continue
        if command is None:
            command = part
            i += 1
            continue
        obj_args.append(part)
        i += 1
    if show_help:
        return (
            'Write-Output "ip - show / manipulate routing, network devices, interfaces and tunnels\\n\\n'
            'Usage: ip [ OPTIONS ] OBJECT { COMMAND | help }\\n\\n'
            'Options:\\n'
            '  -V, -Version          Print version\\n'
            '  -h, -human-readable   Output human readable values\\n'
            '  -s, -statistics       Output more information\\n'
            '  -d, -details          Output more detailed information\\n'
            '  -f, -family           Protocol family (inet, inet6, bridge, link)\\n'
            '  -4                    IPv4 only\\n'
            '  -6                    IPv6 only\\n'
            '  -o, -oneline          Output each record on single line\\n'
            '  -r, -resolve          Use system name resolver\\n'
            '  -N, -Numeric          Print numbers directly\\n'
            '  -a, -all              Execute over all objects\\n'
            '  -br, -brief           Brief output\\n'
            '  -j, -json             JSON output\\n'
            '  -p, -pretty           Pretty print JSON\\n\\n'
            'Objects:\\n'
            '  address (addr, a)     Protocol address on device\\n'
            '  link                  Network device\\n'
            '  route (r)             Routing table entry\\n'
            '  neighbour (neigh)     ARP/NDISC cache entries\\n'
            '  tunnel                Tunnel over IP\\n'
            '  netns                 Network namespaces\\n'
            '  monitor               Watch for netlink messages\\n'
            '  rule                  Routing policy database rules\\n'
            '  maddress (maddr)      Multicast address"'
        )
    if show_version:
        return 'Write-Output "ip utility, iproute2-5.15.0"'
    if batch_file:
        batch_file_escaped = batch_file.replace('"', '`"')
        if force_batch:
            return f'# Batch mode with force: Get-Content "{batch_file_escaped}" | ForEach-Object {{ Invoke-Expression $_ -ErrorAction Continue }}'
        return f'# Batch mode: Get-Content "{batch_file_escaped}" | ForEach-Object {{ Invoke-Expression $_ }}'
    return _build_ip_powershell_command(
        obj, command, obj_args, family, statistics, details,
        brief, human_readable, use_json, pretty, resolve,
        numeric, oneline, timestamp, tshort, netns, use_all,
        color, iec, echo, loops, rcvbuf
    )
def _build_ip_powershell_command(
    obj: Optional[str],
    command: Optional[str],
    obj_args: List[str],
    family: Optional[str],
    statistics: int,
    details: bool,
    brief: bool,
    human_readable: bool,
    use_json: bool,
    pretty: bool,
    resolve: bool,
    numeric: bool,
    oneline: bool,
    timestamp: bool,
    tshort: bool,
    netns: Optional[str],
    use_all: bool,
    color: Optional[str],
    iec: bool,
    echo: bool,
    loops: Optional[int],
    rcvbuf: Optional[int]
) -> str:
    notes: List[str] = []
    if netns:
        notes.append(f'# NOTE: Network namespace (-n {netns}) not directly supported in PowerShell')
    if use_json:
        notes.append('# NOTE: JSON output (-j) not directly supported, using Format-List as alternative')
    if color:
        notes.append('# NOTE: Color output (-c) not directly supported in PowerShell')
    if timestamp or tshort:
        notes.append('# NOTE: Timestamp (-t/-ts) not directly supported')
    if echo:
        notes.append('# NOTE: Echo (-echo) not directly supported')
    if loops is not None:
        notes.append(f'# NOTE: Loops option (-l {loops}) not applicable in PowerShell')
    if rcvbuf is not None:
        notes.append(f'# NOTE: Receive buffer size (-rc {rcvbuf}) not applicable in PowerShell')
    if iec:
        notes.append('# NOTE: IEC units (-iec) not directly supported')
    if oneline:
        notes.append('# NOTE: Oneline output (-o) not directly supported')
    family_param = ''
    if family == 'inet':
        family_param = ' -AddressFamily IPv4'
    elif family == 'inet6':
        family_param = ' -AddressFamily IPv6'
    elif family == 'bridge':
        notes.append('# NOTE: Bridge family (-B) not directly supported')
    elif family == 'mpls':
        notes.append('# NOTE: MPLS family (-M) not directly supported')
    elif family == 'link':
        notes.append('# NOTE: Link family (-0) not directly supported')
    obj_normalized = ''
    if obj:
        obj_lower = obj.lower()
        if obj_lower in ('address', 'addr', 'a'):
            obj_normalized = 'address'
        elif obj_lower in ('link', 'l'):
            obj_normalized = 'link'
        elif obj_lower in ('route', 'r', 'ro'):
            obj_normalized = 'route'
        elif obj_lower in ('neighbour', 'neighbor', 'neigh', 'n'):
            obj_normalized = 'neighbour'
        elif obj_lower in ('tunnel', 'tunl', 'tun'):
            obj_normalized = 'tunnel'
        elif obj_lower == 'netns':
            obj_normalized = 'netns'
        elif obj_lower in ('maddress', 'maddr'):
            obj_normalized = 'maddress'
        elif obj_lower == 'monitor':
            obj_normalized = 'monitor'
        elif obj_lower == 'rule':
            obj_normalized = 'rule'
        elif obj_lower in ('addrlabel', 'label'):
            obj_normalized = 'addrlabel'
        else:
            obj_normalized = obj_lower
    cmd_normalized = ''
    if command:
        cmd_lower = command.lower()
        if cmd_lower in ('show', 'sh', 'list', 'lst', 'l'):
            cmd_normalized = 'show'
        elif cmd_lower in ('add', 'a'):
            cmd_normalized = 'add'
        elif cmd_lower in ('delete', 'del', 'd'):
            cmd_normalized = 'delete'
        elif cmd_lower in ('set', 's'):
            cmd_normalized = 'set'
        elif cmd_lower in ('flush', 'f'):
            cmd_normalized = 'flush'
        elif cmd_lower == 'help':
            cmd_normalized = 'help'
        elif cmd_lower in ('change', 'chg', 'c'):
            cmd_normalized = 'change'
        elif cmd_lower in ('replace', 'repl'):
            cmd_normalized = 'replace'
        else:
            cmd_normalized = cmd_lower
    if obj_normalized == 'address':
        return _build_address_command(
            cmd_normalized, obj_args, family_param, statistics,
            details, brief, human_readable, use_all, notes
        )
    elif obj_normalized == 'link':
        return _build_link_command(
            cmd_normalized, obj_args, family_param, statistics,
            details, brief, human_readable, use_all, notes
        )
    elif obj_normalized == 'route':
        return _build_route_command(
            cmd_normalized, obj_args, family_param, statistics,
            details, brief, human_readable, resolve, numeric, notes
        )
    elif obj_normalized == 'neighbour':
        return _build_neighbour_command(
            cmd_normalized, obj_args, family_param, statistics,
            details, brief, notes
        )
    elif obj_normalized == 'tunnel':
        return _build_tunnel_command(
            cmd_normalized, obj_args, family_param, notes
        )
    elif obj_normalized == 'netns':
        notes.append('# NOTE: Network namespaces not directly supported in PowerShell')
        return '; '.join(notes) if notes else '# Network namespaces not supported'
    elif obj_normalized == 'maddress':
        return _build_maddress_command(
            cmd_normalized, obj_args, family_param, notes
        )
    elif obj_normalized == 'monitor':
        notes.append('# NOTE: Monitor mode uses Register-ObjectEvent for continuous monitoring')
        return '; '.join(notes) if notes else 'Register-ObjectEvent -SourceIdentifier NetEvent'
    elif obj_normalized == 'rule':
        return _build_rule_command(
            cmd_normalized, obj_args, family_param, notes
        )
    elif obj_normalized == 'addrlabel':
        notes.append('# NOTE: Address labels not directly supported in PowerShell')
        return '; '.join(notes) if notes else '# Address labels not supported'
    if obj is None:
        return f'Get-NetIPAddress{family_param} | Format-Table -AutoSize'
    notes.append(f'# NOTE: Unknown or unsupported object: {obj}')
    return '; '.join(notes) if notes else f'# Unknown ip object: {obj}'
def _build_address_command(
    command: str,
    obj_args: List[str],
    family_param: str,
    statistics: int,
    details: bool,
    brief: bool,
    human_readable: bool,
    use_all: bool,
    notes: List[str]
) -> str:
    device: Optional[str] = None
    ip_with_prefix: Optional[str] = None
    label: Optional[str] = None
    scope: Optional[str] = None
    i = 0
    while i < len(obj_args):
        arg = obj_args[i]
        arg_lower = arg.lower()
        if arg_lower in ('dev', 'device') and i + 1 < len(obj_args):
            device = obj_args[i + 1]
            i += 2
        elif arg_lower == 'label' and i + 1 < len(obj_args):
            label = obj_args[i + 1]
            i += 2
        elif arg_lower == 'scope' and i + 1 < len(obj_args):
            scope = obj_args[i + 1]
            i += 2
        elif arg_lower == 'global':
            scope = 'global'
            i += 1
        elif arg_lower == 'link':
            scope = 'link'
            i += 1
        elif arg_lower == 'host':
            scope = 'host'
            i += 1
        elif arg.startswith('dev:'):
            device = arg[4:]
            i += 1
        elif not arg.startswith('-') and not ip_with_prefix:
            ip_with_prefix = arg
            i += 1
        else:
            i += 1
    if command == 'add':
        if not ip_with_prefix:
            return '# Error: ip addr add requires an IP address with prefix (e.g., 192.168.1.1/24)'
        if '/' in ip_with_prefix:
            ip_addr, prefix = ip_with_prefix.rsplit('/', 1)
            try:
                prefix_len = int(prefix)
            except ValueError:
                prefix_len = 24
        else:
            ip_addr = ip_with_prefix
            prefix_len = 24
        if not device:
            return f'# Error: ip addr add requires a device (use "dev <interface>")'
        device_escaped = device.replace('"', '`"')
        return f'New-NetIPAddress -IPAddress {ip_addr} -PrefixLength {prefix_len} -InterfaceAlias "{device_escaped}"'
    elif command == 'delete':
        if not ip_with_prefix:
            return '# Error: ip addr del requires an IP address with prefix'
        if '/' in ip_with_prefix:
            ip_addr, prefix = ip_with_prefix.rsplit('/', 1)
            try:
                prefix_len = int(prefix)
            except ValueError:
                prefix_len = None
        else:
            ip_addr = ip_with_prefix
            prefix_len = None
        if device:
            device_escaped = device.replace('"', '`"')
            if prefix_len:
                return f'Remove-NetIPAddress -IPAddress {ip_addr} -PrefixLength {prefix_len} -InterfaceAlias "{device_escaped}" -Confirm:$false'
            return f'Remove-NetIPAddress -IPAddress {ip_addr} -InterfaceAlias "{device_escaped}" -Confirm:$false'
        else:
            if prefix_len:
                return f'Remove-NetIPAddress -IPAddress {ip_addr} -PrefixLength {prefix_len} -Confirm:$false'
            return f'Remove-NetIPAddress -IPAddress {ip_addr} -Confirm:$false'
    elif command == 'flush':
        if device:
            device_escaped = device.replace('"', '`"')
            return f'Get-NetIPAddress -InterfaceAlias "{device_escaped}"{family_param} | Remove-NetIPAddress -Confirm:$false'
        return f'Get-NetIPAddress{family_param} | Remove-NetIPAddress -Confirm:$false'
    base_cmd = f'Get-NetIPAddress{family_param}'
    if device:
        device_escaped = device.replace('"', '`"')
        base_cmd += f' -InterfaceAlias "{device_escaped}"'
    if scope:
        notes.append(f'# NOTE: Scope filter ({scope}) not directly supported in PowerShell')
    if brief:
        base_cmd += ' | Select-Object InterfaceAlias, IPAddress, PrefixLength'
    elif statistics > 0:
        base_cmd = base_cmd.replace('Get-NetIPAddress', 'Get-NetIPAddress') + '; Get-NetAdapterStatistics'
    elif details:
        base_cmd += ' | Format-List'
    else:
        base_cmd += ' | Format-Table -AutoSize'
    if notes:
        return '; '.join(notes + [base_cmd])
    return base_cmd
def _build_link_command(
    command: str,
    obj_args: List[str],
    family_param: str,
    statistics: int,
    details: bool,
    brief: bool,
    human_readable: bool,
    use_all: bool,
    notes: List[str]
) -> str:
    device: Optional[str] = None
    mtu: Optional[int] = None
    state: Optional[str] = None
    name: Optional[str] = None
    new_name: Optional[str] = None
    i = 0
    while i < len(obj_args):
        arg = obj_args[i]
        arg_lower = arg.lower()
        if arg_lower in ('dev', 'device') and i + 1 < len(obj_args):
            device = obj_args[i + 1]
            i += 2
        elif arg_lower == 'mtu' and i + 1 < len(obj_args):
            try:
                mtu = int(obj_args[i + 1])
            except ValueError:
                pass
            i += 2
        elif arg_lower == 'name' and i + 1 < len(obj_args):
            name = obj_args[i + 1]
            i += 2
        elif arg_lower in ('up', 'down'):
            state = arg_lower
            i += 1
        elif arg_lower == 'set':
            i += 1
        else:
            if not device and not arg.startswith('-') and not state:
                device = arg
            i += 1
    if command == 'set' or state:
        if not device:
            return '# Error: ip link set requires a device'
        device_escaped = device.replace('"', '`"')
        if state == 'up':
            return f'Enable-NetAdapter -Name "{device_escaped}"'
        elif state == 'down':
            return f'Disable-NetAdapter -Name "{device_escaped}" -Confirm:$false'
        if mtu:
            return f'Set-NetAdapterAdvancedProperty -Name "{device_escaped}" -RegistryKeyword "MTU" -RegistryValue {mtu}'
        return f'# ip link set dev {device_escaped}' + (f' mtu {mtu}' if mtu else '') + (f' {state}' if state else '')
    elif command == 'add':
        if name:
            name_escaped = name.replace('"', '`"')
            return f'# Creating virtual interface "{name_escaped}" requires additional configuration'
        return '# ip link add requires a name'
    elif command == 'delete':
        if device:
            device_escaped = device.replace('"', '`"')
            return f'Remove-NetAdapter -Name "{device_escaped}" -Confirm:$false'
        return '# ip link del requires a device'
    if statistics > 0:
        base_cmd = 'Get-NetAdapterStatistics'
        if device:
            device_escaped = device.replace('"', '`"')
            base_cmd += f' -Name "{device_escaped}"'
    else:
        base_cmd = 'Get-NetAdapter'
        if device:
            device_escaped = device.replace('"', '`"')
            base_cmd += f' -Name "{device_escaped}"'
    if details:
        base_cmd += ' | Format-List'
    else:
        base_cmd += ' | Format-Table -AutoSize'
    if notes:
        return '; '.join(notes + [base_cmd])
    return base_cmd
def _build_route_command(
    command: str,
    obj_args: List[str],
    family_param: str,
    statistics: int,
    details: bool,
    brief: bool,
    human_readable: bool,
    resolve: bool,
    numeric: bool,
    notes: List[str]
) -> str:
    destination: Optional[str] = None
    gateway: Optional[str] = None
    device: Optional[str] = None
    src: Optional[str] = None
    metric: Optional[int] = None
    table: Optional[str] = None
    i = 0
    while i < len(obj_args):
        arg = obj_args[i]
        arg_lower = arg.lower()
        if arg_lower in ('via', 'gw') and i + 1 < len(obj_args):
            gateway = obj_args[i + 1]
            i += 2
        elif arg_lower in ('dev', 'device') and i + 1 < len(obj_args):
            device = obj_args[i + 1]
            i += 2
        elif arg_lower == 'src' and i + 1 < len(obj_args):
            src = obj_args[i + 1]
            i += 2
        elif arg_lower == 'metric' and i + 1 < len(obj_args):
            try:
                metric = int(obj_args[i + 1])
            except ValueError:
                pass
            i += 2
        elif arg_lower == 'table' and i + 1 < len(obj_args):
            table = obj_args[i + 1]
            i += 2
        elif arg_lower == 'default':
            destination = '0.0.0.0/0'
            i += 1
        elif arg_lower in ('show', 'list', 'add', 'del', 'delete', 'flush'):
            i += 1
        elif not arg.startswith('-') and not destination:
            destination = arg
            i += 1
        else:
            i += 1
    if command == 'add':
        if not destination:
            return '# Error: ip route add requires a destination'
        ps_cmd = f'New-NetRoute -DestinationPrefix "{destination}"'
        if gateway:
            ps_cmd += f' -NextHop "{gateway}"'
        if device:
            device_escaped = device.replace('"', '`"')
            ps_cmd += f' -InterfaceAlias "{device_escaped}"'
        if metric is not None:
            ps_cmd += f' -RouteMetric {metric}'
        return ps_cmd
    elif command == 'delete':
        if not destination:
            return '# Error: ip route del requires a destination'
        ps_cmd = f'Remove-NetRoute -DestinationPrefix "{destination}" -Confirm:$false'
        if gateway:
            ps_cmd += f' -NextHop "{gateway}"'
        return ps_cmd
    elif command == 'flush':
        if destination:
            return f'Remove-NetRoute -DestinationPrefix "{destination}" -Confirm:$false'
        return 'Get-NetRoute | Remove-NetRoute -Confirm:$false'
    base_cmd = 'Get-NetRoute'
    if destination:
        base_cmd += f' -DestinationPrefix "{destination}"'
    if details:
        base_cmd += ' | Format-List'
    else:
        base_cmd += ' | Format-Table -AutoSize'
    if table:
        notes.append(f'# NOTE: Route table filter (table {table}) may require additional filtering')
    if notes:
        return '; '.join(notes + [base_cmd])
    return base_cmd
def _build_neighbour_command(
    command: str,
    obj_args: List[str],
    family_param: str,
    statistics: int,
    details: bool,
    brief: bool,
    notes: List[str]
) -> str:
    ip_addr: Optional[str] = None
    device: Optional[str] = None
    lladdr: Optional[str] = None
    state_filter: Optional[str] = None
    i = 0
    while i < len(obj_args):
        arg = obj_args[i]
        arg_lower = arg.lower()
        if arg_lower in ('dev', 'device') and i + 1 < len(obj_args):
            device = obj_args[i + 1]
            i += 2
        elif arg_lower == 'lladdr' and i + 1 < len(obj_args):
            lladdr = obj_args[i + 1]
            i += 2
        elif arg_lower == 'nud' and i + 1 < len(obj_args):
            state_filter = obj_args[i + 1]
            i += 2
        elif arg_lower in ('show', 'list', 'add', 'del', 'delete', 'flush'):
            i += 1
        elif not arg.startswith('-') and not ip_addr:
            ip_addr = arg
            i += 1
        else:
            i += 1
    if command == 'add':
        if not ip_addr:
            return '# Error: ip neigh add requires an IP address'
        if not lladdr:
            return '# Error: ip neigh add requires a link-layer address (lladdr)'
        device_part = f' -InterfaceAlias "{device.replace("\"", '`"')}"' if device else ''
        return f'New-NetNeighbor -IPAddress "{ip_addr}" -LinkLayerAddress "{lladdr}"{device_part}'
    elif command == 'delete':
        if not ip_addr:
            return '# Error: ip neigh del requires an IP address'
        device_part = f' -InterfaceAlias "{device.replace("\"", '`"')}"' if device else ''
        return f'Remove-NetNeighbor -IPAddress "{ip_addr}"{device_part} -Confirm:$false'
    elif command == 'flush':
        if device:
            device_escaped = device.replace('"', '`"')
            return f'Get-NetNeighbor -InterfaceAlias "{device_escaped}" | Remove-NetNeighbor -Confirm:$false'
        return 'Get-NetNeighbor | Remove-NetNeighbor -Confirm:$false'
    base_cmd = 'Get-NetNeighbor'
    if device:
        device_escaped = device.replace('"', '`"')
        base_cmd += f' -InterfaceAlias "{device_escaped}"'
    if ip_addr:
        base_cmd += f' | Where-Object {{ $_.IPAddress -eq "{ip_addr}" }}'
    if details:
        base_cmd += ' | Format-List'
    else:
        base_cmd += ' | Format-Table -AutoSize'
    if state_filter:
        notes.append(f'# NOTE: State filter (nud {state_filter}) may require additional filtering')
    if notes:
        return '; '.join(notes + [base_cmd])
    return base_cmd
def _build_tunnel_command(
    command: str,
    obj_args: List[str],
    family_param: str,
    notes: List[str]
) -> str:
    tunnel_name: Optional[str] = None
    mode: Optional[str] = None
    remote: Optional[str] = None
    local: Optional[str] = None
    i = 0
    while i < len(obj_args):
        arg = obj_args[i]
        arg_lower = arg.lower()
        if arg_lower in ('add', 'del', 'delete', 'show', 'list', 'change', 'prl', '6rd'):
            i += 1
        elif arg_lower == 'mode' and i + 1 < len(obj_args):
            mode = obj_args[i + 1]
            i += 2
        elif arg_lower == 'remote' and i + 1 < len(obj_args):
            remote = obj_args[i + 1]
            i += 2
        elif arg_lower == 'local' and i + 1 < len(obj_args):
            local = obj_args[i + 1]
            i += 2
        elif not arg.startswith('-') and not tunnel_name:
            tunnel_name = arg
            i += 1
        else:
            i += 1
    notes.append('# NOTE: Tunnel configuration requires additional setup in PowerShell')
    if command == 'add':
        if tunnel_name:
            tunnel_escaped = tunnel_name.replace('"', '`"')
            return f'New-NetIPInterface -InterfaceAlias "{tunnel_escaped}" # NOTE: GRE/IP tunnel creation requires additional configuration (mode={mode}, remote={remote}, local={local})'
        return '# ip tunnel add requires a tunnel name'
    elif command == 'delete':
        if tunnel_name:
            tunnel_escaped = tunnel_name.replace('"', '`"')
            return f'Remove-NetIPInterface -InterfaceAlias "{tunnel_escaped}" -Confirm:$false'
        return '# ip tunnel del requires a tunnel name'
    return 'Get-NetIPInterface | Where-Object { $_.ConnectionState -eq "Tunneled" } | Format-Table -AutoSize'
def _build_maddress_command(
    command: str,
    obj_args: List[str],
    family_param: str,
    notes: List[str]
) -> str:
    notes.append('# NOTE: Multicast address management uses Get-NetMulticastGroup or Get-NetIPInterface')
    device: Optional[str] = None
    i = 0
    while i < len(obj_args):
        arg = obj_args[i]
        arg_lower = arg.lower()
        if arg_lower in ('dev', 'device') and i + 1 < len(obj_args):
            device = obj_args[i + 1]
            i += 2
        elif arg_lower in ('add', 'del', 'delete', 'show', 'list'):
            i += 1
        else:
            i += 1
    if command == 'add':
        return '; '.join(notes) if notes else '# Multicast add not directly supported'
    elif command == 'delete':
        return '; '.join(notes) if notes else '# Multicast delete not directly supported'
    base_cmd = 'Get-NetMulticastGroup' if not device else f'Get-NetMulticastGroup | Where-Object {{ $_.InterfaceAlias -eq "{device.replace("\"", '`"')}" }}'
    base_cmd += ' | Format-Table -AutoSize'
    if notes:
        return '; '.join(notes + [base_cmd])
    return base_cmd
def _build_rule_command(
    command: str,
    obj_args: List[str],
    family_param: str,
    notes: List[str]
) -> str:
    notes.append('# NOTE: Policy routing rules use Get-NetRoute with additional filtering')
    if command == 'add':
        return '; '.join(notes) if notes else '# ip rule add not directly supported'
    elif command == 'delete':
        return '; '.join(notes) if notes else '# ip rule del not directly supported'
    base_cmd = 'Get-NetRoute | Format-Table -AutoSize'
    if notes:
        return '; '.join(notes + [base_cmd])
    return base_cmd
if __name__ == "__main__":
    test_cases = [
        "ip addr",
        "ip addr show",
        "ip link",
        "ip link show",
        "ip route",
        "ip route show",
        "ip neigh",
        "ip neigh show",
        "ip -4 addr",
        "ip -6 addr",
        "ip -s link",
        "ip -h addr",
        "ip -d link",
        "ip -br addr",
        "ip -json addr",
        "ip -pretty addr",
        "ip addr add 192.168.1.10/24 dev eth0",
        "ip addr del 192.168.1.10/24 dev eth0",
        "ip addr flush dev eth0",
        "ip link set eth0 up",
        "ip link set eth0 down",
        "ip link set dev eth0 mtu 1500",
        "ip link del eth0",
        "ip route add default via 192.168.1.1",
        "ip route add 10.0.0.0/8 via 192.168.1.1",
        "ip route del default",
        "ip route flush",
        "ip neigh add 192.168.1.1 lladdr 00:11:22:33:44:55 dev eth0",
        "ip neigh del 192.168.1.1 dev eth0",
        "ip neigh flush dev eth0",
        "ip tunnel add tun0 mode gre remote 10.0.0.1 local 10.0.0.2",
        "ip tunnel del tun0",
        "ip help",
        "ip -V",
        "ip --version",
        "ip /4 addr",
        "ip /6 addr",
        "ip /s link",
        "ip --family inet addr",
        "ip --statistics link",
        "ip --details link",
        "ip --brief addr",
        "ip --json addr",
        "ip --pretty addr",
    ]
    for test in test_cases:
        result = _convert_ip(test)
        print(f"Input:  {test}")
        print(f"Output: {result}")
        print()
def _convert_slash_to_dash(arg: str) -> str:
    if not arg.startswith('/') or len(arg) < 2:
        return arg
    if arg[1].isalpha() or arg[1].isdigit():
        if len(arg) == 2:
            return '-' + arg[1:]
        else:
            return '--' + arg[1:]
    return arg
def _parse_format(format_str: str) -> List[Tuple[int, int]]:
    specs = []
    items = format_str.replace(',', ' ').split()
    for item in items:
        item = item.strip()
        if not item:
            continue
        if item == '0':
            specs.append((0, 0))
        elif '.' in item:
            parts = item.split('.', 1)
            try:
                file_num = int(parts[0])
                field_num = int(parts[1])
                if file_num in (1, 2):
                    specs.append((file_num, field_num))
            except ValueError:
                pass
    return specs
def _build_join_powershell_command(
    file1: str,
    file2: str,
    field1: int,
    field2: int,
    delimiter: Optional[str],
    unpairable1: bool,
    unpairable2: bool,
    suppress_joined: bool,
    empty_string: Optional[str],
    ignore_case: bool,
    format_specs: Optional[List[Tuple[int, int]]],
    check_order: bool,
    nocheck_order: bool,
    header: bool,
    zero_terminated: bool
) -> str:
    notes: List[str] = []
    if check_order:
        notes.append('# NOTE: --check-order not directly supported in PowerShell')
    if nocheck_order:
        notes.append('# NOTE: --nocheck-order not directly supported in PowerShell')
    if zero_terminated:
        notes.append('# NOTE: -z (zero-terminated) not directly supported in PowerShell')
    def quote_file(f: str) -> str:
        if f == '-':
            return '$input'
        if ' ' in f and not (f.startswith('"') or f.startswith("'")):
            return f'"{f}"'
        return f
    if delimiter is None:
        split_delim = '\\s+'
        join_delim = ' '
    else:
        escaped = delimiter.replace('\\\\', '\\\\\\\\').replace('.', '\\.').replace('*', '\\*')
        escaped = escaped.replace('+', '\\+').replace('?', '\\?').replace('[', '\\[')
        escaped = escaped.replace(']', '\\]').replace('^', '\\^').replace('$', '\\$')
        split_delim = escaped
        join_delim = delimiter
    ps_join_delim = join_delim.replace('"', '`"').replace('$', '`$')
    ps_empty = empty_string.replace('"', '`"').replace('$', '`$') if empty_string else ''
    join_type = 'inner'
    if suppress_joined:
        if unpairable1 and unpairable2:
            join_type = 'full_anti'
        elif unpairable1:
            join_type = 'left_anti'
        elif unpairable2:
            join_type = 'right_anti'
    else:
        if unpairable1 and unpairable2:
            join_type = 'full_outer'
        elif unpairable1:
            join_type = 'left_outer'
        elif unpairable2:
            join_type = 'right_outer'
    script_lines: List[str] = []
    if file1 == '-':
        script_lines.append('$lines1 = @($input)')
    else:
        script_lines.append(f'$lines1 = Get-Content {quote_file(file1)}')
    if file2 == '-':
        script_lines.append('$lines2 = @($input)')
    else:
        script_lines.append(f'$lines2 = Get-Content {quote_file(file2)}')
    if header:
        script_lines.append('if ($lines1.Count -gt 0) { $header1 = $lines1[0]; $lines1 = $lines1[1..($lines1.Count-1)] }')
        script_lines.append('if ($lines2.Count -gt 0) { $header2 = $lines2[0]; $lines2 = $lines2[1..($lines2.Count-1)] }')
        script_lines.append('Write-Output $header1')
        script_lines.append('Write-Output $header2')
    field_idx1 = field1 - 1
    field_idx2 = field2 - 1
    if delimiter is None:
        split_func1 = f"$_.Split()[$field_idx1]"
        split_func2 = f"$_.Split()[$field_idx2]"
    else:
        split_func1 = f"$_.Split('{delimiter}')[$field_idx1]"
        split_func2 = f"$_.Split('{delimiter}')[$field_idx2]"
    if ignore_case:
        compare_op = '-eq'
        compare_transform = '.ToLower()'
    else:
        compare_op = '-eq'
        compare_transform = ''
    script_lines.append('$joined = @{}')
    script_lines.append('$unpaired1 = @()')
    script_lines.append('$unpaired2 = @()')
    script_lines.append('$index2 = @{}')
    script_lines.append('foreach ($line2 in $lines2) {')
    if delimiter is None:
        script_lines.append(f'    $fields2 = $line2.Split()')
    else:
        script_lines.append(f'    $fields2 = $line2.Split("{delimiter}")')
    script_lines.append(f'    if ($fields2.Count -gt {field_idx2}) {{')
    if ignore_case:
        script_lines.append(f'        $key = $fields2[{field_idx2}].ToLower()')
    else:
        script_lines.append(f'        $key = $fields2[{field_idx2}]')
    script_lines.append('        if (-not $index2.ContainsKey($key)) { $index2[$key] = @() }')
    script_lines.append('        $index2[$key] += $line2')
    script_lines.append('    }')
    script_lines.append('}')
    script_lines.append('foreach ($line1 in $lines1) {')
    if delimiter is None:
        script_lines.append(f'    $fields1 = $line1.Split()')
    else:
        script_lines.append(f'    $fields1 = $line1.Split("{delimiter}")')
    script_lines.append(f'    if ($fields1.Count -gt {field_idx1}) {{')
    if ignore_case:
        script_lines.append(f'        $key = $fields1[{field_idx1}].ToLower()')
    else:
        script_lines.append(f'        $key = $fields1[{field_idx1}]')
    script_lines.append('        if ($index2.ContainsKey($key)) {')
    if format_specs:
        format_parts = []
        for file_num, field_num in format_specs:
            if file_num == 0:
                format_parts.append('$key')
            elif file_num == 1:
                format_parts.append(f'$fields1[{field_num - 1}]')
            else:
                format_parts.append(f'$f2.Split("{delimiter}")[{field_num - 1}]' if delimiter else f'$f2.Split()[{field_num - 1}]')
        output_expr = f'"{ps_join_delim}".join([{", ".join(format_parts)}])'
    else:
        if delimiter is None:
            output_expr = f'"$key " + (($fields1[0..($fields1.Count-1)] | Where-Object {{ $_ -ne $key }}) -join " ") + " " + (($f2.Split() | Where-Object {{ $_ -ne $key }}) -join " ")'
        else:
            output_expr = f'"$key{ps_join_delim}" + (($fields1 | Where-Object {{ $_ -ne $key }}) -join "{ps_join_delim}") + "{ps_join_delim}" + (($f2.Split("{delimiter}") | Where-Object {{ $_ -ne $key }}) -join "{ps_join_delim}")'
    if empty_string:
        output_expr = output_expr.replace('$fields1[', f'($fields1[').replace(']', f'] ?? "{ps_empty}")')
    if not suppress_joined:
        script_lines.append(f'            foreach ($f2 in $index2[$key]) {{')
        script_lines.append(f'                Write-Output ({output_expr})')
        script_lines.append('            }')
    script_lines.append('        } else {')
    if join_type in ('left_outer', 'full_outer'):
        script_lines.append('            Write-Output $line1')
    elif join_type == 'left_anti':
        script_lines.append('            Write-Output $line1')
    script_lines.append('        }')
    script_lines.append('    }')
    script_lines.append('}')
    if join_type in ('right_outer', 'full_outer', 'right_anti', 'full_anti'):
        script_lines.append('$keys1 = @{}')
        script_lines.append('foreach ($line1 in $lines1) {')
        if delimiter is None:
            script_lines.append(f'    $fields1 = $line1.Split()')
        else:
            script_lines.append(f'    $fields1 = $line1.Split("{delimiter}")')
        script_lines.append(f'    if ($fields1.Count -gt {field_idx1}) {{')
        if ignore_case:
            script_lines.append(f'        $keys1[$fields1[{field_idx1}].ToLower()] = $true')
        else:
            script_lines.append(f'        $keys1[$fields1[{field_idx1}]] = $true')
        script_lines.append('    }')
        script_lines.append('}')
        script_lines.append('foreach ($line2 in $lines2) {')
        if delimiter is None:
            script_lines.append(f'    $fields2 = $line2.Split()')
        else:
            script_lines.append(f'    $fields2 = $line2.Split("{delimiter}")')
        script_lines.append(f'    if ($fields2.Count -gt {field_idx2}) {{')
        if ignore_case:
            script_lines.append(f'        $key = $fields2[{field_idx2}].ToLower()')
        else:
            script_lines.append(f'        $key = $fields2[{field_idx2}]')
        script_lines.append('        if (-not $keys1.ContainsKey($key)) {')
        script_lines.append('            Write-Output $line2')
        script_lines.append('        }')
        script_lines.append('    }')
        script_lines.append('}')
    cmd = '; '.join(script_lines)
    if notes:
        cmd += '  ' + ' '.join(notes)
    return cmd
def _convert_join(cmd: str) -> str:
    if not cmd or not cmd.strip():
        return 'Write-Error "join: missing operand"'
    parts = _parse_command_line(cmd)
    if not parts:
        return 'Write-Error "join: missing operand"'
    if parts[0] in ('join', '/bin/join', '/usr/bin/join'):
        parts = parts[1:]
    if not parts:
        return 'Write-Error "join: missing operand"'
    field1 = 1
    field2 = 1
    delimiter: Optional[str] = None
    unpairable1 = False
    unpairable2 = False
    suppress_joined = False
    empty_string: Optional[str] = None
    ignore_case = False
    format_specs: Optional[List[Tuple[int, int]]] = None
    check_order = False
    nocheck_order = False
    header = False
    zero_terminated = False
    show_help = False
    show_version = False
    files: List[str] = []
    i = 0
    while i < len(parts):
        part = parts[i]
        part = _convert_slash_to_dash(part)
        if part == '--':
            files.extend(parts[i + 1:])
            break
        if part.startswith('--'):
            long_opt = part[2:]
            if long_opt == 'help':
                show_help = True
                i += 1
                continue
            if long_opt == 'version':
                show_version = True
                i += 1
                continue
            if long_opt == 'ignore-case':
                ignore_case = True
                i += 1
                continue
            if long_opt == 'check-order':
                check_order = True
                i += 1
                continue
            if long_opt == 'nocheck-order':
                nocheck_order = True
                i += 1
                continue
            if long_opt == 'header':
                header = True
                i += 1
                continue
            if long_opt == 'zero-terminated':
                zero_terminated = True
                i += 1
                continue
            i += 1
            continue
        if part.startswith('-') and len(part) > 1:
            opt_char = part[1]
            if opt_char == 'a':
                if len(part) > 2:
                    filenum = part[2:]
                elif i + 1 < len(parts):
                    i += 1
                    filenum = parts[i]
                else:
                    return 'Write-Error "join: option requires an argument -- \'a\'"'
                if filenum == '1':
                    unpairable1 = True
                elif filenum == '2':
                    unpairable2 = True
                i += 1
                continue
            elif opt_char == 'e':
                if len(part) > 2:
                    empty_string = part[2:]
                elif i + 1 < len(parts):
                    i += 1
                    empty_string = parts[i]
                else:
                    return 'Write-Error "join: option requires an argument -- \'e\'"'
                i += 1
                continue
            elif opt_char == 'i':
                ignore_case = True
                i += 1
                continue
            elif opt_char == 'j':
                if len(part) > 2:
                    field_val = part[2:]
                elif i + 1 < len(parts):
                    i += 1
                    field_val = parts[i]
                else:
                    return 'Write-Error "join: option requires an argument -- \'j\'"'
                try:
                    field_num = int(field_val)
                    field1 = field_num
                    field2 = field_num
                except ValueError:
                    return 'Write-Error "join: invalid field number"'
                i += 1
                continue
            elif opt_char == 'o':
                if len(part) > 2:
                    format_str = part[2:]
                elif i + 1 < len(parts):
                    i += 1
                    format_str = parts[i]
                else:
                    return 'Write-Error "join: option requires an argument -- \'o\'"'
                if format_str == 'auto':
                    format_specs = None
                else:
                    format_specs = _parse_format(format_str)
                i += 1
                continue
            elif opt_char == 't':
                if len(part) > 2:
                    delimiter = part[2:]
                elif i + 1 < len(parts):
                    i += 1
                    delimiter = parts[i]
                else:
                    return 'Write-Error "join: option requires an argument -- \'t\'"'
                i += 1
                continue
            elif opt_char == 'v':
                if len(part) > 2:
                    filenum = part[2:]
                elif i + 1 < len(parts):
                    i += 1
                    filenum = parts[i]
                else:
                    return 'Write-Error "join: option requires an argument -- \'v\'"'
                suppress_joined = True
                if filenum == '1':
                    unpairable1 = True
                elif filenum == '2':
                    unpairable2 = True
                i += 1
                continue
            elif opt_char == '1':
                if len(part) > 2:
                    field_val = part[2:]
                elif i + 1 < len(parts):
                    i += 1
                    field_val = parts[i]
                else:
                    return 'Write-Error "join: option requires an argument -- \'1\'"'
                try:
                    field1 = int(field_val)
                except ValueError:
                    return 'Write-Error "join: invalid field number"'
                i += 1
                continue
            elif opt_char == '2':
                if len(part) > 2:
                    field_val = part[2:]
                elif i + 1 < len(parts):
                    i += 1
                    field_val = parts[i]
                else:
                    return 'Write-Error "join: option requires an argument -- \'2\'"'
                try:
                    field2 = int(field_val)
                except ValueError:
                    return 'Write-Error "join: invalid field number"'
                i += 1
                continue
            elif opt_char == 'z':
                zero_terminated = True
                i += 1
                continue
            i += 1
            continue
        files.append(part)
        i += 1
    if show_help:
        return (
            'Write-Output "join - join lines of two files on a common field\n'
            'Usage: join [OPTION]... FILE1 FILE2\n'
            'For each pair of input lines with identical join fields, write a line to\n'
            'standard output. The default join field is the first, delimited by blanks.\n'
            'When FILE1 or FILE2 (not both) is -, read standard input.\n\n'
            '  -a FILENUM        also print unpairable lines from file FILENUM, where\n'
            '                     FILENUM is 1 or 2, corresponding to FILE1 or FILE2\n'
            '  -e STRING         replace missing input fields with STRING\n'
            '  -i, --ignore-case ignore differences in case when comparing fields\n'
            '  -j FIELD          equivalent to \'-1 FIELD -2 FIELD\'\n'
            '  -o FORMAT         obey FORMAT while constructing output line\n'
            '  -t CHAR           use CHAR as input and output field separator\n'
            '  -v FILENUM        like -a FILENUM, but suppress joined output lines\n'
            '  -1 FIELD          join on this FIELD of file 1\n'
            '  -2 FIELD          join on this FIELD of file 2\n'
            '      --check-order check that the input is correctly sorted\n'
            '      --nocheck-order do not check that the input is correctly sorted\n'
            '      --header      treat the first line in each file as field headers\n'
            '  -z, --zero-terminated line delimiter is NUL, not newline\n'
            '      --help        display this help and exit\n'
            '      --version     output version information and exit"'
        )
    if show_version:
        return 'Write-Output "join (GNU coreutils) 8.32"'
    if len(files) < 2:
        return 'Write-Error "join: missing operand"'
    if len(files) > 2:
        return 'Write-Error "join: extra operand"'
    file1, file2 = files[0], files[1]
    return _build_join_powershell_command(
        file1, file2, field1, field2, delimiter,
        unpairable1, unpairable2, suppress_joined,
        empty_string, ignore_case, format_specs,
        check_order, nocheck_order, header, zero_terminated
    )
if __name__ == "__main__":
    test_cases = [
        "join file1.txt file2.txt",
        "join -t ',' file1.txt file2.txt",
        "join -1 2 -2 3 file1.txt file2.txt",
        "join -j 2 file1.txt file2.txt",
        "join -a 1 file1.txt file2.txt",
        "join -a 2 file1.txt file2.txt",
        "join -a 1 -a 2 file1.txt file2.txt",
        "join -v 1 file1.txt file2.txt",
        "join -i file1.txt file2.txt",
        "join -e 'NULL' -a 1 file1.txt file2.txt",
        "join -o '1.1,1.2,2.2' file1.txt file2.txt",
        "join --header file1.txt file2.txt",
        "join /t ',' file1.txt file2.txt",
        "join /1 2 /2 3 file1.txt file2.txt",
        "join --ignore-case file1.txt file2.txt",
        "join --help",
        "join --version",
    ]
    for test in test_cases:
        result = _convert_join(test)
        print(f"Input:  {test}")
        print(f"Output: {result}")
        print()
def _convert_slash_to_dash(arg: str) -> str:
    if not arg.startswith('/') or len(arg) < 2:
        return arg
    if arg[1].isalpha():
        if len(arg) == 2:
            return '-' + arg[1:]
        else:
            return '--' + arg[1:]
    return arg
def _is_simple_filter(filter_str: str) -> bool:
    if (filter_str.startswith('"') and filter_str.endswith('"')) or \
       (filter_str.startswith("'") and filter_str.endswith("'")):
        filter_str = filter_str[1:-1]
    if filter_str == '.':
        return True
    if re.match(r'^\.[a-zA-Z_][a-zA-Z0-9_]*(\.[a-zA-Z_][a-zA-Z0-9_]*)*$', filter_str):
        return True
    if re.match(r'^\.\[\d+\]$', filter_str):
        return True
    if filter_str == '.[]':
        return True
    if re.match(r'^\.[a-zA-Z_][a-zA-Z0-9_]*\[\d+\]$', filter_str):
        return True
    if re.match(r'^\.[a-zA-Z_][a-zA-Z0-9_]*\[\]$', filter_str):
        return True
    return False
def _convert_filter_to_powershell(filter_str: str) -> str:
    if (filter_str.startswith('"') and filter_str.endswith('"')) or \
       (filter_str.startswith("'") and filter_str.endswith("'")):
        filter_str = filter_str[1:-1]
    if filter_str == '.':
        return '$_'
    match = re.match(r'^\.([a-zA-Z_][a-zA-Z0-9_]*)(\.[a-zA-Z_][a-zA-Z0-9_]*)*$', filter_str)
    if match:
        parts = filter_str[1:].split('.')
        return '$_.' + '.'.join(parts)
    match = re.match(r'^\.\[(\d+)\]$', filter_str)
    if match:
        idx = int(match.group(1))
        return f'$_[{idx}]'
    if filter_str == '.[]':
        return '$_'
    match = re.match(r'^\.([a-zA-Z_][a-zA-Z0-9_]*)\[(\d+)\]$', filter_str)
    if match:
        prop = match.group(1)
        idx = int(match.group(2))
        return f'$_.{prop}[{idx}]'
    match = re.match(r'^\.([a-zA-Z_][a-zA-Z0-9_]*)\[\]$', filter_str)
    if match:
        prop = match.group(1)
        return f'$_.{prop}'
    return '$_'
def _build_jq_powershell_command(
    filter_str: str,
    files: List[str],
    options: Dict[str, Any]
) -> str:
    if options.get('show_help'):
        return (
            'Write-Output "jq - Command-line JSON processor\n'
            'Usage: jq [OPTIONS...] FILTER [FILES...]\n'
            'Options:\n'
            '  -n, --null-input       Use `null` as the single input value\n'
            '  -R, --raw-input        Read each line as string instead of JSON\n'
            '  -s, --slurp            Read all inputs into an array\n'
            '  -c, --compact-output   Compact output (no pretty-printing)\n'
            '  -r, --raw-output       Output raw strings, not JSON texts\n'
            '  -j, --join-output      Like -r but without newlines between outputs\n'
            '  -a, --ascii-output     Output ASCII only (escape Unicode)\n'
            '  -S, --sort-keys        Sort object keys\n'
            '  -C, --color-output     Colorize JSON output\n'
            '  -M, --monochrome-output  Disable color output\n'
            '  --arg name value       Pass variable $name with string value\n'
            '  --argjson name value   Pass variable $name with JSON value\n'
            '  --slurpfile name file  Pass variable $name with JSON contents of file\n'
            '  --rawfile name file    Pass variable $name with raw contents of file\n'
            '  --argfile name file    Deprecated; use --slurpfile instead\n'
            '  -f file                Read filter from file\n'
            '  -L directory           Prepend directory to search list\n'
            '  -e, --exit-status      Set exit status based on output\n'
            '  -V, --version          Show version\n'
            '      --help             Show this help"'
        )
    if options.get('show_version'):
        return 'Write-Output "jq-1.7"'
    if not filter_str:
        return 'Write-Error "jq: error: no filter specified"'
    if files:
        quoted_files = []
        for f in files:
            if ' ' in f and not (f.startswith('"') or f.startswith("'")):
                quoted_files.append(f'"{f}"')
            else:
                quoted_files.append(f)
        if len(files) == 1:
            input_cmd = f'Get-Content {quoted_files[0]} -Raw'
        else:
            file_list = ','.join(quoted_files)
            input_cmd = f'Get-Content {file_list} -Raw'
    else:
        if options.get('slurp'):
            input_cmd = '$input'
        else:
            input_cmd = '$input'
    if options.get('null_input'):
        input_cmd = '$null'
    elif options.get('raw_input'):
        input_cmd = f'{input_cmd} | ForEach-Object {{ $_ }}'
    else:
        input_cmd = f'{input_cmd} | ConvertFrom-Json -Depth 100'
    use_native_jq = not _is_simple_filter(filter_str)
    if use_native_jq:
        notes = []
        jq_args = []
        if options.get('compact_output'):
            jq_args.append('-c')
        if options.get('raw_output'):
            jq_args.append('-r')
        if options.get('sort_keys'):
            jq_args.append('-S')
        if options.get('null_input'):
            jq_args.append('-n')
        if options.get('raw_input'):
            jq_args.append('-R')
        if options.get('slurp'):
            jq_args.append('-s')
        if options.get('ascii_output'):
            jq_args.append('-a')
        if options.get('join_output'):
            jq_args.append('-j')
        for name, value in options.get('args', []):
            escaped_value = value.replace('"', '`"').replace('$', '`$')
            jq_args.append(f'--arg {name} "{escaped_value}"')
        for name, value in options.get('argjson', []):
            jq_args.append(f'--argjson {name} {value}')
        jq_args_str = ' '.join(jq_args)
        escaped_filter = filter_str.replace('"', '`"').replace('$', '`$')
        if files:
            files_str = ' '.join(quoted_files)
            if jq_args_str:
                result = f'jq {jq_args_str} "{escaped_filter}" {files_str}'
            else:
                result = f'jq "{escaped_filter}" {files_str}'
        else:
            if options.get('null_input'):
                if jq_args_str:
                    result = f'jq {jq_args_str} "{escaped_filter}"'
                else:
                    result = f'jq "{escaped_filter}"'
            else:
                if jq_args_str:
                    result = f'$input | jq {jq_args_str} "{escaped_filter}"'
                else:
                    result = f'$input | jq "{escaped_filter}"'
        if notes:
            result += '  # ' + '; '.join(notes)
        return result
    else:
        ps_expr = _convert_filter_to_powershell(filter_str)
        if options.get('slurp'):
            if ps_expr == '$_':
                pipeline = input_cmd
            else:
                pipeline = f'{input_cmd} | ForEach-Object {{ {ps_expr} }}'
        else:
            if ps_expr == '$_':
                pipeline = input_cmd
            else:
                pipeline = f'{input_cmd} | ForEach-Object {{ {ps_expr} }}'
        if options.get('raw_output'):
            if options.get('compact_output'):
                result = pipeline
            else:
                result = pipeline
        elif options.get('join_output'):
            result = f'{pipeline} | ForEach-Object {{ Write-Host -NoNewline $_ }}'
        else:
            depth = 100
            if options.get('compact_output'):
                result = f'{pipeline} | ConvertTo-Json -Depth {depth} -Compress'
            else:
                result = f'{pipeline} | ConvertTo-Json -Depth {depth}'
        if options.get('sort_keys'):
            pass
        return result
def _convert_jq(cmd: str) -> str:
    if not cmd or not cmd.strip():
        return 'Write-Output "jq - Command-line JSON processor\nUsage: jq [OPTIONS...] FILTER [FILES...]"'
    parts = _parse_command_line(cmd)
    if not parts:
        return 'Write-Output "jq - Command-line JSON processor\nUsage: jq [OPTIONS...] FILTER [FILES...]"'
    if parts[0] in ('jq', '/bin/jq', '/usr/bin/jq'):
        parts = parts[1:]
    if not parts:
        return 'Write-Output "jq - Command-line JSON processor\nUsage: jq [OPTIONS...] FILTER [FILES...]"'
    options: Dict[str, Any] = {
        'null_input': False,
        'raw_input': False,
        'slurp': False,
        'compact_output': False,
        'raw_output': False,
        'join_output': False,
        'ascii_output': False,
        'sort_keys': False,
        'color_output': False,
        'monochrome_output': False,
        'exit_status': False,
        'show_help': False,
        'show_version': False,
        'args': [],
        'argjson': [],
        'filter_file': None,
    }
    filter_str = ''
    files: List[str] = []
    i = 0
    while i < len(parts):
        part = parts[i]
        if part == '--':
            if i + 1 < len(parts):
                filter_str = parts[i + 1]
                files = parts[i + 2:]
            break
        part = _convert_slash_to_dash(part)
        if part.startswith('--'):
            long_opt = part[2:]
            if long_opt == 'help':
                options['show_help'] = True
                i += 1
                continue
            if long_opt == 'version':
                options['show_version'] = True
                i += 1
                continue
            if long_opt == 'null-input':
                options['null_input'] = True
                i += 1
                continue
            if long_opt == 'raw-input':
                options['raw_input'] = True
                i += 1
                continue
            if long_opt == 'slurp':
                options['slurp'] = True
                i += 1
                continue
            if long_opt == 'compact-output':
                options['compact_output'] = True
                i += 1
                continue
            if long_opt == 'raw-output':
                options['raw_output'] = True
                i += 1
                continue
            if long_opt == 'join-output':
                options['join_output'] = True
                i += 1
                continue
            if long_opt == 'ascii-output':
                options['ascii_output'] = True
                i += 1
                continue
            if long_opt == 'sort-keys':
                options['sort_keys'] = True
                i += 1
                continue
            if long_opt == 'color-output':
                options['color_output'] = True
                i += 1
                continue
            if long_opt == 'monochrome-output':
                options['monochrome_output'] = True
                i += 1
                continue
            if long_opt == 'exit-status':
                options['exit_status'] = True
                i += 1
                continue
            if '=' in long_opt:
                opt_name, opt_value = long_opt.split('=', 1)
                if opt_name == 'arg' and i + 1 < len(parts):
                    var_name = opt_value
                    i += 1
                    if i < len(parts):
                        var_value = parts[i]
                        options['args'].append((var_name, var_value))
                elif opt_name == 'argjson' and i + 1 < len(parts):
                    var_name = opt_value
                    i += 1
                    if i < len(parts):
                        var_value = parts[i]
                        options['argjson'].append((var_name, var_value))
                i += 1
                continue
            if long_opt == 'arg' and i + 2 < len(parts):
                var_name = parts[i + 1]
                var_value = parts[i + 2]
                options['args'].append((var_name, var_value))
                i += 3
                continue
            if long_opt == 'argjson' and i + 2 < len(parts):
                var_name = parts[i + 1]
                var_value = parts[i + 2]
                options['argjson'].append((var_name, var_value))
                i += 3
                continue
            i += 1
            continue
        if part.startswith('-') and len(part) > 1:
            opt_chars = part[1:]
            j = 0
            while j < len(opt_chars):
                char = opt_chars[j]
                if char == 'n':
                    options['null_input'] = True
                    j += 1
                elif char == 'R':
                    options['raw_input'] = True
                    j += 1
                elif char == 's':
                    options['slurp'] = True
                    j += 1
                elif char == 'c':
                    options['compact_output'] = True
                    j += 1
                elif char == 'r':
                    options['raw_output'] = True
                    j += 1
                elif char == 'j':
                    options['join_output'] = True
                    j += 1
                elif char == 'a':
                    options['ascii_output'] = True
                    j += 1
                elif char == 'S':
                    options['sort_keys'] = True
                    j += 1
                elif char == 'C':
                    options['color_output'] = True
                    j += 1
                elif char == 'M':
                    options['monochrome_output'] = True
                    j += 1
                elif char == 'e':
                    options['exit_status'] = True
                    j += 1
                elif char == 'V':
                    options['show_version'] = True
                    j += 1
                elif char == 'f':
                    if j + 1 < len(opt_chars):
                        options['filter_file'] = opt_chars[j + 1:]
                        break
                    elif i + 1 < len(parts):
                        i += 1
                        options['filter_file'] = parts[i]
                    j += 1
                else:
                    j += 1
            i += 1
            continue
        if not filter_str and not options.get('filter_file'):
            filter_str = part
        else:
            files.append(part)
        i += 1
    if options.get('filter_file'):
        filter_file = options['filter_file']
        if ' ' in filter_file and not (filter_file.startswith('"') or filter_file.startswith("'")):
            filter_file = f'"{filter_file}"'
        filter_str = f"(Get-Content {filter_file} -Raw)"
    return _build_jq_powershell_command(filter_str, files, options)
if __name__ == "__main__":
    test_cases = [
        "jq '.' file.json",
        "jq '.name' file.json",
        "jq -r '.name' file.json",
        "jq -c '.items' file.json",
        "jq --slurp '.' files*.json",
        "jq /r '.name' file.json",
        "jq -n '$ENV.PATH'",
        "jq -R '.' text.txt",
        "jq -s '.' files*.json",
        "jq --arg foo bar '. + {foo: $foo}' file.json",
        "jq --help",
        "jq --version",
        "jq '.items[0]' file.json",
        "jq '.items[]' file.json",
        "jq '.foo.bar' file.json",
        "jq -r -c '.name' file.json",
        "jq -S '.items' file.json",
    ]
    for test in test_cases:
        result = _convert_jq(test)
        print(f"Input:  {test}")
        print(f"Output: {result}")
        print()
def _convert_ln_s(cmd: str) -> str:
    if not cmd or not cmd.strip():
        return 'Write-Output "ln: missing file operand"'
    parts = _parse_command_line(cmd)
    if not parts:
        return 'Write-Output "ln: missing file operand"'
    if parts[0] in ('ln', '/bin/ln', '/usr/bin/ln'):
        parts = parts[1:]
    if not parts:
        return 'Write-Output "ln: missing file operand"'
    backup = False
    backup_suffix = '~'
    force = False
    interactive = False
    logical = False
    no_dereference = False
    relative = False
    symbolic = False
    target_directory: Optional[str] = None
    no_target_directory = False
    verbose = False
    show_help = False
    show_version = False
    i = 0
    while i < len(parts):
        part = parts[i]
        if part == '--':
            i += 1
            break
        if part.startswith('/') and len(part) >= 2 and not part.startswith('//'):
            if len(part) == 2 and part[1].isalpha():
                part = '-' + part[1:]
            elif len(part) > 2 and part[1].isalpha():
                if '/' not in part[1:] and '\\' not in part[1:]:
                    part = '--' + part[1:]
        if part.startswith('--'):
            long_opt = part[2:]
            if '=' in long_opt:
                opt_name, opt_value = long_opt.split('=', 1)
                if opt_name == 'backup':
                    backup = True
                elif opt_name == 'suffix':
                    backup_suffix = opt_value
                elif opt_name == 'target-directory':
                    target_directory = opt_value
                i += 1
                continue
            if long_opt == 'help':
                show_help = True
                i += 1
                continue
            elif long_opt == 'version':
                show_version = True
                i += 1
                continue
            elif long_opt == 'backup':
                backup = True
                i += 1
                continue
            elif long_opt == 'directory':
                i += 1
                continue
            elif long_opt == 'force':
                force = True
                i += 1
                continue
            elif long_opt == 'interactive':
                interactive = True
                i += 1
                continue
            elif long_opt == 'logical':
                logical = True
                i += 1
                continue
            elif long_opt == 'no-dereference':
                no_dereference = True
                i += 1
                continue
            elif long_opt == 'relative':
                relative = True
                i += 1
                continue
            elif long_opt == 'symbolic':
                symbolic = True
                i += 1
                continue
            elif long_opt == 'suffix':
                if i + 1 < len(parts):
                    i += 1
                    backup_suffix = parts[i]
                i += 1
                continue
            elif long_opt == 'target-directory':
                if i + 1 < len(parts):
                    i += 1
                    target_directory = parts[i]
                i += 1
                continue
            elif long_opt == 'no-target-directory':
                no_target_directory = True
                i += 1
                continue
            elif long_opt == 'verbose':
                verbose = True
                i += 1
                continue
            i += 1
            continue
        if part.startswith('-') and len(part) > 1:
            opt_chars = part[1:]
            j = 0
            while j < len(opt_chars):
                char = opt_chars[j]
                if char == 'b':
                    backup = True
                    j += 1
                elif char == 'd' or char == 'F':
                    j += 1
                elif char == 'f':
                    force = True
                    j += 1
                elif char == 'i':
                    interactive = True
                    j += 1
                elif char == 'L':
                    logical = True
                    j += 1
                elif char == 'n':
                    no_dereference = True
                    j += 1
                elif char == 'r':
                    relative = True
                    j += 1
                elif char == 's':
                    symbolic = True
                    j += 1
                elif char == 'S':
                    if j + 1 < len(opt_chars):
                        backup_suffix = opt_chars[j + 1:]
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                        backup_suffix = parts[i]
                        j += 1
                    else:
                        j += 1
                elif char == 't':
                    if j + 1 < len(opt_chars):
                        target_directory = opt_chars[j + 1:]
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                        target_directory = parts[i]
                        j += 1
                    else:
                        j += 1
                elif char == 'T':
                    no_target_directory = True
                    j += 1
                elif char == 'v':
                    verbose = True
                    j += 1
                elif char == '-':
                    j += 1
                    i += 1
                    break
                else:
                    j += 1
            i += 1
            continue
        break
    if show_help:
        return (
            'Write-Output "Usage: ln [OPTION]... [-T] TARGET LINK_NAME\n'
            '  or:  ln [OPTION]... TARGET\n'
            '  or:  ln [OPTION]... TARGET... DIRECTORY\n'
            '  or:  ln [OPTION]... -t DIRECTORY TARGET...\n'
            'Create a link to TARGET with the name LINK_NAME.\n'
            'Create hard links by default, symbolic links with --symbolic.\n'
            '\n'
            'Mandatory arguments to long options are mandatory for short options too.\n'
            '  -b, --backup             make a backup of each existing destination file\n'
            '  -d, -F, --directory      allow the superuser to attempt to hard link\n'
            '                             directories (note: will probably fail due to\n'
            '                             system restrictions, even for the superuser)\n'
            '  -f, --force              remove existing destination files\n'
            '  -i, --interactive        prompt whether to remove destinations\n'
            '  -L, --logical            dereference TARGETs that are symbolic links\n'
            '  -n, --no-dereference     treat LINK_NAME as a normal file if\n'
            '                             it is a symbolic link to a directory\n'
            '  -r, --relative           create symbolic links relative to link location\n'
            '  -s, --symbolic           make symbolic links instead of hard links\n'
            '  -S, --suffix=SUFFIX      override the usual backup suffix (~)\n'
            '  -t, --target-directory=DIRECTORY  specify the DIRECTORY in which to create\n'
            '                                    the links\n'
            '  -T, --no-target-directory  treat LINK_NAME as a normal file always\n'
            '  -v, --verbose            print name of each linked file\n'
            '      --help     display this help and exit\n'
            '      --version  output version information and exit"'
        )
    if show_version:
        return 'Write-Output "ln (GNU coreutils) 8.32"'
    remaining = parts[i:]
    if not remaining:
        return 'Write-Output "ln: missing file operand"'
    target: Optional[str] = None
    link_name: Optional[str] = None
    if target_directory:
        if len(remaining) == 1:
            target = remaining[0]
            target_basename = os.path.basename(target.rstrip('/\\'))
            link_name = f"{target_directory.rstrip('/\\')}/{target_basename}"
        else:
            target = remaining[0]
            target_basename = os.path.basename(target.rstrip('/\\'))
            link_name = f"{target_directory.rstrip('/\\')}/{target_basename}"
    elif len(remaining) == 1:
        target = remaining[0]
        link_name = os.path.basename(target.rstrip('/\\'))
    elif len(remaining) >= 2:
        if not no_target_directory and len(remaining) > 2:
            target = remaining[0]
            link_dir = remaining[-1]
            target_basename = os.path.basename(target.rstrip('/\\'))
            link_name = f"{link_dir.rstrip('/\\')}/{target_basename}"
        else:
            target = remaining[0]
            link_name = remaining[1]
    if not target:
        return 'Write-Output "ln: missing file operand"'
    if not link_name:
        link_name = target
    return _build_ln_s_powershell_command(
        target, link_name, backup, backup_suffix, force,
        interactive, logical, no_dereference, relative, verbose
    )
def _build_ln_s_powershell_command(
    target: str,
    link_name: str,
    backup: bool,
    backup_suffix: str,
    force: bool,
    interactive: bool,
    logical: bool,
    no_dereference: bool,
    relative: bool,
    verbose: bool
) -> str:
    quoted_target = target
    if ' ' in target and not (target.startswith('"') or target.startswith("'")):
        quoted_target = f'"{target}"'
    quoted_link_name = link_name
    if ' ' in link_name and not (link_name.startswith('"') or link_name.startswith("'")):
        quoted_link_name = f'"{link_name}"'
    commands = []
    if backup:
        backup_cmd = (
            f'if (Test-Path {quoted_link_name}) {{ '
            f'Rename-Item -Path {quoted_link_name} -NewName "{link_name}{backup_suffix}" '
            f'}}'
        )
        commands.append(backup_cmd)
    if force:
        commands.append(f'Remove-Item -Path {quoted_link_name} -ErrorAction SilentlyContinue')
    if interactive and not force:
        interactive_cmd = (
            f'if (Test-Path {quoted_link_name}) {{ '
            f'$response = Read-Host "ln: replace \'{link_name}\'? (y/n)"; '
            f'if ($response -eq "y" -or $response -eq "Y") {{ '
            f'Remove-Item -Path {quoted_link_name} -ErrorAction SilentlyContinue '
            f'}} else {{ return }} '
            f'}}'
        )
        commands.append(interactive_cmd)
    if relative:
        new_item_cmd = (
            f'New-Item -ItemType SymbolicLink -Path {quoted_link_name} '
            f'-Target (Resolve-Path -Relative -Path {quoted_target})'
        )
    else:
        new_item_cmd = (
            f'New-Item -ItemType SymbolicLink -Path {quoted_link_name} '
            f'-Target {quoted_target}'
        )
    commands.append(new_item_cmd)
    if verbose:
        commands.append(f'Write-Output "{link_name}" -> "{target}"')
    return '; '.join(commands)
def _convert_ln(cmd: str) -> str:
    if not cmd or not cmd.strip():
        return 'Write-Output "ln: missing file operand"'
    parts = _parse_command_line(cmd)
    if not parts:
        return 'Write-Output "ln: missing file operand"'
    if parts[0] in ('ln', '/bin/ln', '/usr/bin/ln'):
        parts = parts[1:]
    if not parts:
        return 'Write-Output "ln: missing file operand"'
    symbolic = False
    force = False
    interactive = False
    verbose = False
    backup = False
    suffix = '~'
    target_directory: Optional[str] = None
    no_target_directory = False
    logical = False
    physical = False
    relative = False
    no_dereference = False
    allow_directory = False
    show_help = False
    show_version = False
    i = 0
    while i < len(parts):
        part = parts[i]
        if part == '--':
            i += 1
            break
        VALID_SHORT_OPTS = 'bdFf iL nPrsStTv'
        VALID_LONG_OPTS = {
            'backup', 'directory', 'force', 'interactive', 'logical',
            'no-dereference', 'physical', 'relative', 'symbolic', 'suffix',
            'target-directory', 'no-target-directory', 'verbose', 'help', 'version'
        }
        if part.startswith('/') and len(part) >= 2:
            opt_part = part[1:]
            if len(opt_part) == 1 and opt_part in VALID_SHORT_OPTS:
                part = '-' + opt_part
            elif opt_part in VALID_LONG_OPTS:
                part = '--' + opt_part
            elif '=' in opt_part:
                opt_name = opt_part.split('=', 1)[0]
                if opt_name in VALID_LONG_OPTS:
                    part = '--' + opt_part
        if part.startswith('--'):
            long_opt = part[2:]
            if '=' in long_opt:
                opt_name, opt_value = long_opt.split('=', 1)
                if opt_name == 'suffix':
                    suffix = opt_value
                elif opt_name == 'target-directory':
                    target_directory = opt_value
                i += 1
                continue
            if long_opt == 'help':
                show_help = True
                i += 1
                continue
            elif long_opt == 'version':
                show_version = True
                i += 1
                continue
            elif long_opt == 'symbolic':
                symbolic = True
                i += 1
                continue
            elif long_opt == 'force':
                force = True
                i += 1
                continue
            elif long_opt == 'interactive':
                interactive = True
                i += 1
                continue
            elif long_opt == 'verbose':
                verbose = True
                i += 1
                continue
            elif long_opt == 'backup':
                backup = True
                i += 1
                continue
            elif long_opt == 'directory':
                allow_directory = True
                i += 1
                continue
            elif long_opt == 'logical':
                logical = True
                i += 1
                continue
            elif long_opt == 'physical':
                physical = True
                i += 1
                continue
            elif long_opt == 'relative':
                relative = True
                i += 1
                continue
            elif long_opt == 'no-dereference':
                no_dereference = True
                i += 1
                continue
            elif long_opt == 'no-target-directory':
                no_target_directory = True
                i += 1
                continue
            elif long_opt == 'target-directory':
                if i + 1 < len(parts):
                    i += 1
                    target_directory = parts[i]
                i += 1
                continue
            elif long_opt == 'suffix':
                if i + 1 < len(parts):
                    i += 1
                    suffix = parts[i]
                i += 1
                continue
            i += 1
            continue
        if part.startswith('-') and len(part) > 1:
            opt_chars = part[1:]
            j = 0
            while j < len(opt_chars):
                char = opt_chars[j]
                if char == 's':
                    symbolic = True
                    j += 1
                elif char == 'f':
                    force = True
                    j += 1
                elif char == 'i':
                    interactive = True
                    j += 1
                elif char == 'v':
                    verbose = True
                    j += 1
                elif char == 'b':
                    backup = True
                    j += 1
                elif char == 'd' or char == 'F':
                    allow_directory = True
                    j += 1
                elif char == 'L':
                    logical = True
                    j += 1
                elif char == 'P':
                    physical = True
                    j += 1
                elif char == 'r':
                    relative = True
                    j += 1
                elif char == 'n':
                    no_dereference = True
                    j += 1
                elif char == 'T':
                    no_target_directory = True
                    j += 1
                elif char == 'S':
                    if j + 1 < len(opt_chars):
                        suffix = opt_chars[j + 1:]
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                        suffix = parts[i]
                    j += 1
                elif char == 't':
                    if j + 1 < len(opt_chars):
                        target_directory = opt_chars[j + 1:]
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                        target_directory = parts[i]
                    j += 1
                elif char == '-':
                    j += 1
                    i += 1
                    break
                else:
                    j += 1
            i += 1
            continue
        break
    if show_help:
        return (
            'Write-Output "Usage: ln [OPTION]... [-T] TARGET LINK_NAME\n'
            '  or:  ln [OPTION]... TARGET\n'
            '  or:  ln [OPTION]... TARGET... DIRECTORY\n'
            '  or:  ln [OPTION]... -t DIRECTORY TARGET...\n'
            'Create a link to the specified TARGET(s) with the specified LINK_NAME.\n'
            '\n'
            'Mandatory arguments to long options are mandatory for short options too.\n'
            '  -b, --backup                  make a backup of each existing destination file\n'
            '  -d, -F, --directory           allow the superuser to attempt to hard link directories\n'
            '  -f, --force                   remove existing destination files\n'
            '  -i, --interactive             prompt whether to remove destinations\n'
            '  -L, --logical                 dereference TARGETs that are symbolic links\n'
            '  -n, --no-dereference          treat LINK_NAME as a normal file if it is a symlink to a directory\n'
            '  -P, --physical                make hard links directly to symbolic links\n'
            '  -r, --relative                create symbolic links relative to link location\n'
            '  -s, --symbolic                make symbolic links instead of hard links\n'
            '  -S, --suffix=SUFFIX           override the usual backup suffix\n'
            '  -t, --target-directory=DIRECTORY  specify the DIRECTORY in which to create the links\n'
            '  -T, --no-target-directory     treat LINK_NAME as a normal file always\n'
            '  -v, --verbose                 print name of each linked file\n'
            '      --help     display this help and exit\n'
            '      --version  output version information and exit"'
        )
    if show_version:
        return 'Write-Output "ln (GNU coreutils) 8.32"'
    remaining = parts[i:]
    if not remaining:
        return 'Write-Output "ln: missing file operand"'
    item_type = 'SymbolicLink' if symbolic else 'HardLink'
    commands = []
    if target_directory:
        for target in remaining:
            target_name = target.replace('\\', '/').split('/')[-1]
            if not target_name:
                target_name = target
            link_path = f"{target_directory.rstrip('/\\')}/{target_name}"
            cmd_parts = []
            if backup:
                backup_name = f"{link_path}{suffix}"
                cmd_parts.append(f'if (Test-Path "{link_path}") {{ Rename-Item -Path "{link_path}" -NewName "{backup_name}" }}')
            if force:
                cmd_parts.append(f'Remove-Item -Path "{link_path}" -Force -ErrorAction SilentlyContinue')
            if interactive and not force:
                cmd_parts.append(
                    f'if (Test-Path "{link_path}") {{ '
                    f'$response = Read-Host "ln: replace \'{link_path}\'? "; '
                    f'if ($response -eq "y" -or $response -eq "yes") {{ '
                    f'Remove-Item -Path "{link_path}" -Force '
                    f'}} else {{ continue }} '
                    f'}}'
                )
            cmd_parts.append(f'New-Item -ItemType {item_type} -Path "{link_path}" -Target "{target}"')
            if verbose:
                cmd_parts.append(f'Write-Output "{link_path}" -> "{target}"')
            commands.append('; '.join(cmd_parts))
    elif len(remaining) == 1:
        target = remaining[0]
        target_name = target.replace('\\', '/').split('/')[-1]
        if not target_name:
            target_name = target
        link_path = target_name
        cmd_parts = []
        if backup:
            backup_name = f"{link_path}{suffix}"
            cmd_parts.append(f'if (Test-Path "{link_path}") {{ Rename-Item -Path "{link_path}" -NewName "{backup_name}" }}')
        if force:
            cmd_parts.append(f'Remove-Item -Path "{link_path}" -Force -ErrorAction SilentlyContinue')
        if interactive and not force:
            cmd_parts.append(
                f'if (Test-Path "{link_path}") {{ '
                f'$response = Read-Host "ln: replace \'{link_path}\'? "; '
                f'if ($response -eq "y" -or $response -eq "yes") {{ '
                f'Remove-Item -Path "{link_path}" -Force '
                f'}} else {{ continue }} '
                f'}}'
            )
        cmd_parts.append(f'New-Item -ItemType {item_type} -Path "{link_path}" -Target "{target}"')
        if verbose:
            cmd_parts.append(f'Write-Output "{link_path}" -> "{target}"')
        commands.append('; '.join(cmd_parts))
    elif len(remaining) == 2:
        target, link_path = remaining
        cmd_parts = []
        if backup:
            backup_name = f"{link_path}{suffix}"
            cmd_parts.append(f'if (Test-Path "{link_path}") {{ Rename-Item -Path "{link_path}" -NewName "{backup_name}" }}')
        if force:
            cmd_parts.append(f'Remove-Item -Path "{link_path}" -Force -ErrorAction SilentlyContinue')
        if interactive and not force:
            cmd_parts.append(
                f'if (Test-Path "{link_path}") {{ '
                f'$response = Read-Host "ln: replace \'{link_path}\'? "; '
                f'if ($response -eq "y" -or $response -eq "yes") {{ '
                f'Remove-Item -Path "{link_path}" -Force '
                f'}} else {{ continue }} '
                f'}}'
            )
        cmd_parts.append(f'New-Item -ItemType {item_type} -Path "{link_path}" -Target "{target}"')
        if verbose:
            cmd_parts.append(f'Write-Output "{link_path}" -> "{target}"')
        commands.append('; '.join(cmd_parts))
    else:
        *targets, link_dir = remaining
        for target in targets:
            target_name = target.replace('\\', '/').split('/')[-1]
            if not target_name:
                target_name = target
            link_path = f"{link_dir.rstrip('/\\')}/{target_name}"
            cmd_parts = []
            if backup:
                backup_name = f"{link_path}{suffix}"
                cmd_parts.append(f'if (Test-Path "{link_path}") {{ Rename-Item -Path "{link_path}" -NewName "{backup_name}" }}')
            if force:
                cmd_parts.append(f'Remove-Item -Path "{link_path}" -Force -ErrorAction SilentlyContinue')
            if interactive and not force:
                cmd_parts.append(
                    f'if (Test-Path "{link_path}") {{ '
                    f'$response = Read-Host "ln: replace \'{link_path}\'? "; '
                    f'if ($response -eq "y" -or $response -eq "yes") {{ '
                    f'Remove-Item -Path "{link_path}" -Force '
                    f'}} else {{ continue }} '
                    f'}}'
                )
            cmd_parts.append(f'New-Item -ItemType {item_type} -Path "{link_path}" -Target "{target}"')
            if verbose:
                cmd_parts.append(f'Write-Output "{link_path}" -> "{target}"')
            commands.append('; '.join(cmd_parts))
    if len(commands) == 1:
        return commands[0]
    return '; '.join(commands)
def _convert_md5sum(cmd: str) -> str:
    if not cmd or not cmd.strip():
        return '$input | ForEach-Object { (Get-FileHash -Algorithm MD5 -Path $_).Hash.ToLower() + "  $_" }'
    parts = _parse_command_line(cmd)
    if not parts:
        return '$input | ForEach-Object { (Get-FileHash -Algorithm MD5 -Path $_).Hash.ToLower() + "  $_" }'
    if parts[0] in ('md5sum', '/bin/md5sum', '/usr/bin/md5sum'):
        parts = parts[1:]
    if not parts:
        return '$input | ForEach-Object { (Get-FileHash -Algorithm MD5 -Path $_).Hash.ToLower() + "  $_" }'
    options: Dict[str, Any] = {
        'binary': False,
        'check': False,
        'text': False,
        'quiet': False,
        'status': False,
        'warn': False,
        'strict': False,
        'show_help': False,
        'show_version': False,
    }
    files: List[str] = []
    i = 0
    while i < len(parts):
        part = parts[i]
        if part == '--':
            files.extend(parts[i + 1:])
            break
        if part.startswith('/') and len(part) >= 2:
            if len(part) == 2 and part[1].isalpha():
                part = '-' + part[1:]
            elif len(part) > 2 and part[1].isalpha():
                part = '--' + part[1:]
        if part.startswith('--'):
            long_opt = part[2:]
            if long_opt == 'help':
                options['show_help'] = True
                i += 1
                continue
            elif long_opt == 'version':
                options['show_version'] = True
                i += 1
                continue
            elif long_opt == 'binary':
                options['binary'] = True
                i += 1
                continue
            elif long_opt == 'check':
                options['check'] = True
                i += 1
                continue
            elif long_opt == 'text':
                options['text'] = True
                i += 1
                continue
            elif long_opt == 'quiet':
                options['quiet'] = True
                i += 1
                continue
            elif long_opt == 'status':
                options['status'] = True
                i += 1
                continue
            elif long_opt == 'warn':
                options['warn'] = True
                i += 1
                continue
            elif long_opt == 'strict':
                options['strict'] = True
                i += 1
                continue
            i += 1
            continue
        if part.startswith('-') and len(part) > 1:
            opt_chars = part[1:]
            j = 0
            while j < len(opt_chars):
                char = opt_chars[j]
                if char == 'b':
                    options['binary'] = True
                    j += 1
                elif char == 'c':
                    options['check'] = True
                    j += 1
                elif char == 't':
                    options['text'] = True
                    j += 1
                elif char == 'w':
                    options['warn'] = True
                    j += 1
                elif char == 'q':
                    options['quiet'] = True
                    j += 1
                else:
                    j += 1
            i += 1
            continue
        files.append(part)
        i += 1
    return _build_md5sum_powershell_command(options, files)
def _build_md5sum_powershell_command(options: Dict[str, Any], files: List[str]) -> str:
    if options.get('show_help'):
        return (
            'Write-Output "Usage: md5sum [OPTION]... [FILE]...\n'
            'Print or check MD5 (128-bit) checksums.\n\n'
            '  -b, --binary         read in binary mode\n'
            '  -c, --check          read MD5 sums from the FILEs and check them\n'
            '  -t, --text           read in text mode (default)\n'
            '      --quiet          don\'t print OK for each successfully verified file\n'
            '      --status         don\'t output anything, status code shows success\n'
            '  -w, --warn           warn about improperly formatted checksum lines\n'
            '      --strict         with --check, exit non-zero for improperly formatted lines\n'
            '      --help           display this help and exit\n'
            '      --version        output version information and exit"'
        )
    if options.get('show_version'):
        return 'Write-Output "md5sum (GNU coreutils) 8.32"'
    check_mode = options.get('check', False)
    quiet = options.get('quiet', False)
    status = options.get('status', False)
    warn = options.get('warn', False)
    strict = options.get('strict', False)
    if check_mode:
        if not files:
            return '# Error: No checksum file specified for -c/--check mode'
        checksum_file = files[0]
        if ' ' in checksum_file and not (checksum_file.startswith('"') or checksum_file.startswith("'")):
            checksum_file = f'"{checksum_file}"'
        notes = []
        if quiet:
            notes.append('quiet mode')
        if status:
            notes.append('status only')
        if warn:
            notes.append('warn on format errors')
        if strict:
            notes.append('strict mode')
        note_str = ', '.join(notes) if notes else 'verify checksums'
        return f'# Check MD5 checksums ({note_str}): Parse {checksum_file} and compare with Get-FileHash -Algorithm MD5'
    if not files:
        return '$input | ForEach-Object { (Get-FileHash -Algorithm MD5 -Path $_).Hash.ToLower() + "  $_" }'
    commands = []
    for file_path in files:
        if file_path == '-':
            commands.append('$input | ForEach-Object { (Get-FileHash -Algorithm MD5 -Path $_).Hash.ToLower() + "  $_" }')
            continue
        quoted_file = file_path
        if ' ' in file_path and not (file_path.startswith('"') or file_path.startswith("'")):
            quoted_file = f'"{file_path}"'
        cmd = f'(Get-FileHash -Algorithm MD5 -Path {quoted_file}).Hash.ToLower() + "  {file_path}"'
        commands.append(cmd)
    if len(commands) == 1:
        return commands[0]
    return '; '.join(commands)
if __name__ == "__main__":
    test_cases = [
        "md5sum file.txt",
        "md5sum -c checksum.md5",
        "md5sum --check checksums.txt",
        "md5sum file1.txt file2.txt",
        "md5sum --quiet -c checksum.md5",
        "md5sum --status -c checksum.md5",
        "md5sum -b file.txt",
        "md5sum -t file.txt",
        "md5sum -w -c checksum.md5",
        "md5sum --strict --check checksum.md5",
        "md5sum",
        "md5sum -",
        "md5sum --help",
        "md5sum --version",
        "md5sum /b file.txt",
        "md5sum /c checksum.md5",
        "md5sum /t /b file.txt",
        "md5sum -bw file.bin",
        "md5sum 'file with spaces.txt'",
        'md5sum "another file.txt"',
    ]
    for test in test_cases:
        result = _convert_md5sum(test)
        print(f"Input:  {test}")
        print(f"Output: {result}")
        print()
def _convert_mktemp(cmd: str) -> str:
    if not cmd or not cmd.strip():
        return 'New-TemporaryFile | Select-Object -ExpandProperty FullName'
    parts = _parse_command_line(cmd)
    if not parts:
        return 'New-TemporaryFile | Select-Object -ExpandProperty FullName'
    if parts[0] in ('mktemp', '/bin/mktemp', '/usr/bin/mktemp'):
        parts = parts[1:]
    if not parts:
        return 'New-TemporaryFile | Select-Object -ExpandProperty FullName'
    create_directory = False
    dry_run = False
    quiet = False
    suffix: Optional[str] = None
    tmpdir: Optional[str] = None
    use_tmpdir = False
    template: Optional[str] = None
    i = 0
    while i < len(parts):
        part = parts[i]
        if part == '--':
            if i + 1 < len(parts):
                template = parts[i + 1]
            break
        if part.startswith('/') and len(part) >= 2 and part[1].isalpha():
            if len(part) == 2:
                part = '-' + part[1:]
            else:
                sub_part = part[1:]
                if '=' in sub_part:
                    part = '--' + sub_part
                elif sub_part in ('directory', 'dry-run', 'quiet', 'suffix', 'tmpdir', 'help', 'version'):
                    part = '--' + sub_part
                else:
                    part = '-' + sub_part
        if part.startswith('--'):
            long_opt = part[2:]
            if '=' in long_opt:
                opt_name, opt_value = long_opt.split('=', 1)
                if opt_name == 'suffix':
                    suffix = opt_value
                elif opt_name == 'tmpdir':
                    tmpdir = opt_value
                    use_tmpdir = True
                i += 1
                continue
            if long_opt == 'directory':
                create_directory = True
                i += 1
                continue
            elif long_opt == 'dry-run':
                dry_run = True
                i += 1
                continue
            elif long_opt == 'quiet':
                quiet = True
                i += 1
                continue
            elif long_opt == 'tmpdir':
                use_tmpdir = True
                i += 1
                continue
            elif long_opt == 'help':
                return _get_help_text()
            elif long_opt == 'version':
                return 'Write-Output "mktemp (GNU coreutils) 8.32"'
            i += 1
            continue
        if part.startswith('-') and len(part) > 1:
            opt_chars = part[1:]
            j = 0
            while j < len(opt_chars):
                char = opt_chars[j]
                if char == 'd':
                    create_directory = True
                    j += 1
                elif char == 'u':
                    dry_run = True
                    j += 1
                elif char == 'q':
                    quiet = True
                    j += 1
                elif char == 't':
                    use_tmpdir = True
                    j += 1
                elif char == 'p':
                    if j + 1 < len(opt_chars):
                        tmpdir = opt_chars[j + 1:]
                        use_tmpdir = True
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                        tmpdir = parts[i]
                        use_tmpdir = True
                    j += 1
                else:
                    j += 1
            i += 1
            continue
        template = part
        i += 1
    return _build_powershell_command(
        create_directory=create_directory,
        dry_run=dry_run,
        quiet=quiet,
        suffix=suffix,
        tmpdir=tmpdir,
        use_tmpdir=use_tmpdir,
        template=template
    )
def _build_powershell_command(
    create_directory: bool = False,
    dry_run: bool = False,
    quiet: bool = False,
    suffix: Optional[str] = None,
    tmpdir: Optional[str] = None,
    use_tmpdir: bool = False,
    template: Optional[str] = None
) -> str:
    if tmpdir:
        base_dir = tmpdir
    elif use_tmpdir:
        base_dir = '$env:TEMP'
    else:
        base_dir = None
    if template:
        if 'XXX' in template:
            if '/' in template or '\\' in template:
                template_dir = template.rsplit('/', 1)[0] if '/' in template else template.rsplit('\\', 1)[0]
                template_name = template.rsplit('/', 1)[1] if '/' in template else template.rsplit('\\', 1)[1]
                if template.startswith('/'):
                    base_dir = template_dir
                elif base_dir:
                    base_dir = f"(Join-Path {base_dir} '{template_dir}')"
                else:
                    base_dir = f"(Join-Path ([System.IO.Path]::GetTempPath()) '{template_dir}')"
            else:
                template_name = template
                if not base_dir:
                    base_dir = '[System.IO.Path]::GetTempPath()'
        else:
            template_name = template
            if not base_dir:
                base_dir = '[System.IO.Path]::GetTempPath()'
    else:
        template_name = None
        if not base_dir:
            base_dir = '[System.IO.Path]::GetTempPath()'
    if suffix and template_name:
        template_name = template_name + suffix
    if create_directory:
        if dry_run:
            if template_name and 'XXX' in template_name:
                return f"Write-Output (Join-Path {base_dir} '{template_name}'.Replace('X', (Get-Random -Maximum 16).ToString('x')))"
            elif template_name:
                return f"Write-Output (Join-Path {base_dir} '{template_name}')"
            else:
                return f"Write-Output (Join-Path {base_dir} ([System.IO.Path]::GetRandomFileName()))"
        else:
            if template_name and 'XXX' in template_name:
                ps_cmd = f.strip()
                return ps_cmd
            elif template_name:
                return f"(New-Item -ItemType Directory -Path {base_dir} -Name '{template_name}'{' -ErrorAction SilentlyContinue' if quiet else ''}).FullName"
            else:
                return f"(New-Item -ItemType Directory -Path {base_dir} -Name ([System.IO.Path]::GetRandomFileName()){' -ErrorAction SilentlyContinue' if quiet else ''}).FullName"
    else:
        if dry_run:
            if template_name and 'XXX' in template_name:
                return f"Write-Output (Join-Path {base_dir} '{template_name}'.Replace('X', (Get-Random -Maximum 16).ToString('x')))"
            elif template_name:
                return f"Write-Output (Join-Path {base_dir} '{template_name}')"
            else:
                return f"Write-Output (Join-Path {base_dir} ([System.IO.Path]::GetRandomFileName()))"
        else:
            if template_name and 'XXX' in template_name:
                ps_cmd = f.strip()
                return ps_cmd
            elif template_name:
                return f"(New-Item -ItemType File -Path {base_dir} -Name '{template_name}'{' -ErrorAction SilentlyContinue' if quiet else ''}).FullName"
            else:
                return f"New-TemporaryFile{' -ErrorAction SilentlyContinue' if quiet else ''} | Select-Object -ExpandProperty FullName"
def _get_help_text() -> str:
    help_text = (
        'Write-Output "Usage: mktemp [OPTION]... [TEMPLATE]\n'
        'Create a temporary file or directory, safely, and print its name.\n'
        'TEMPLATE must contain at least 3 consecutive \'X\'s in last component.\n'
        'If TEMPLATE is not specified, use tmp.XXXXXXXXXX, and --tmpdir is implied.\n'
        'Files are created u+rw, and directories u+rwx, minus umask restrictions.\n\n'
        '  -d, --directory     create a directory, not a file\n'
        '  -u, --dry-run       do not create anything; merely print a name (unsafe)\n'
        '  -q, --quiet         suppress diagnostics about file/dir-creation failure\n'
        '      --suffix=SUFF   append SUFF to TEMPLATE; SUFF must not contain a slash.\n'
        '                        This option is implied if TEMPLATE does not end in X\n'
        '  -p DIR, --tmpdir[=DIR]  interpret TEMPLATE relative to DIR; if DIR is not\n'
        '                        specified, use $TMPDIR if set, else /tmp.  With\n'
        '                        this option, TEMPLATE must not be an absolute name;\n'
        '                        unlike with -t, TEMPLATE may contain slashes, but\n'
        '                        mktemp creates only the final component\n'
        '  -t                  interpret TEMPLATE as a single file name component,\n'
        '                        relative to a directory: $TMPDIR, if set; else the\n'
        '                        directory specified via -p; else /tmp [deprecated]\n'
        '      --help     display this help and exit\n'
        '      --version  output version information and exit\n\n'
        'GNU coreutils online help: <https://www.gnu.org/software/coreutils/>\n'
        'Report any translation bugs to <https://translationproject.org/team/>\n'
        'Full documentation <https://www.gnu.org/software/coreutils/mktemp>\n'
        'or available locally via: info \'(coreutils) mktemp invocation\'"'
    )
    return help_text
def _convert_nc(cmd: str) -> str:
    if not cmd or not cmd.strip():
        return (
            'Write-Output "usage: nc [-46CDdFhklNnrStUuvZz] [-I length] [-i interval] [-O length] '
            '[-P proxy_username] [-p source_port] [-q seconds] [-s source] [-T toskeyword] '
            '[-V rtable] [-w timeout] [-X proxy_protocol] [-x proxy_address[:port]] '
            '[destination] [port]"'
        )
    parts = _parse_command_line(cmd)
    if not parts:
        return (
            'Write-Output "usage: nc [-46CDdFhklNnrStUuvZz] [-I length] [-i interval] [-O length] '
            '[-P proxy_username] [-p source_port] [-q seconds] [-s source] [-T toskeyword] '
            '[-V rtable] [-w timeout] [-X proxy_protocol] [-x proxy_address[:port]] '
            '[destination] [port]"'
        )
    if parts[0] in ('nc', '/usr/bin/nc', '/bin/nc', 'netcat', '/usr/bin/netcat'):
        parts = parts[1:]
    if not parts:
        return (
            'Write-Output "usage: nc [-46CDdFhklNnrStUuvZz] [-I length] [-i interval] [-O length] '
            '[-P proxy_username] [-p source_port] [-q seconds] [-s source] [-T toskeyword] '
            '[-V rtable] [-w timeout] [-X proxy_protocol] [-x proxy_address[:port]] '
            '[destination] [port]"'
        )
    options: Dict[str, Any] = {
        'ipv4': False,
        'ipv6': False,
        'crlf': False,
        'debug': False,
        'detach': False,
        'help': False,
        'keepalive': False,
        'listen': False,
        'nodns': False,
        'noshutdown': False,
        'recvonly': False,
        'sendonly': False,
        'telnet': False,
        'udp': False,
        'verbose': False,
        'version': False,
        'zeroio': False,
        'scan': False,
        'interval': None,
        'source_addr': None,
        'source_port': None,
        'timeout': None,
        'proxy_user': None,
        'proxy_protocol': None,
        'proxy_addr': None,
        'exec_cmd': None,
        'output_file': None,
        'hex_dump': None,
    }
    positional_args: List[str] = []
    VALID_SHORT_OPTS = '46CDdFhIikLNnO:P:p:q:s:T:UuV:vW:w:X:x:Zz'
    i = 0
    while i < len(parts):
        part = parts[i]
        if part == '--':
            i += 1
            positional_args.extend(parts[i:])
            break
        if part.startswith('/') and len(part) >= 2:
            opt_part = part[1:]
            valid_single_opts = '46CDdFhiklLNnOPpqrStTtUuvVWwXxZz'
            if len(opt_part) == 1 and opt_part in valid_single_opts:
                part = '-' + opt_part
            elif opt_part in ('help', 'version', 'ipv4', 'ipv6', 'crlf', 'debug',
                              'detach', 'listen', 'nodns', 'udp', 'verbose',
                              'zero', 'keepalive', 'telnet', 'recv-only', 'send-only'):
                part = '--' + opt_part
            elif '=' in opt_part:
                opt_name = opt_part.split('=', 1)[0]
                if opt_name in ('interval', 'source', 'port', 'timeout', 'exec', 'output'):
                    part = '--' + opt_part
            elif all(c in valid_single_opts for c in opt_part):
                part = '-' + opt_part
        if part.startswith('--'):
            long_opt = part[2:]
            if '=' in long_opt:
                opt_name, opt_value = long_opt.split('=', 1)
                if opt_name == 'interval':
                    options['interval'] = opt_value
                elif opt_name == 'source':
                    options['source_addr'] = opt_value
                elif opt_name == 'port':
                    options['source_port'] = opt_value
                elif opt_name == 'timeout':
                    options['timeout'] = opt_value
                elif opt_name == 'exec':
                    options['exec_cmd'] = opt_value
                elif opt_name == 'output':
                    options['output_file'] = opt_value
                i += 1
                continue
            if long_opt == 'help':
                options['help'] = True
                i += 1
                continue
            elif long_opt == 'version':
                options['version'] = True
                i += 1
                continue
            elif long_opt == 'ipv4':
                options['ipv4'] = True
                i += 1
                continue
            elif long_opt == 'ipv6':
                options['ipv6'] = True
                i += 1
                continue
            elif long_opt == 'crlf':
                options['crlf'] = True
                i += 1
                continue
            elif long_opt == 'debug':
                options['debug'] = True
                i += 1
                continue
            elif long_opt == 'listen':
                options['listen'] = True
                i += 1
                continue
            elif long_opt == 'nodns':
                options['nodns'] = True
                i += 1
                continue
            elif long_opt == 'udp':
                options['udp'] = True
                i += 1
                continue
            elif long_opt == 'verbose':
                options['verbose'] = True
                i += 1
                continue
            elif long_opt == 'zero':
                options['zeroio'] = True
                options['scan'] = True
                i += 1
                continue
            elif long_opt == 'keepalive':
                options['keepalive'] = True
                i += 1
                continue
            elif long_opt == 'telnet':
                options['telnet'] = True
                i += 1
                continue
            elif long_opt == 'recv-only':
                options['recvonly'] = True
                i += 1
                continue
            elif long_opt == 'send-only':
                options['sendonly'] = True
                i += 1
                continue
            elif long_opt == 'interval':
                if i + 1 < len(parts):
                    i += 1
                    options['interval'] = parts[i]
                i += 1
                continue
            elif long_opt == 'source':
                if i + 1 < len(parts):
                    i += 1
                    options['source_addr'] = parts[i]
                i += 1
                continue
            elif long_opt == 'port':
                if i + 1 < len(parts):
                    i += 1
                    options['source_port'] = parts[i]
                i += 1
                continue
            elif long_opt == 'timeout':
                if i + 1 < len(parts):
                    i += 1
                    options['timeout'] = parts[i]
                i += 1
                continue
            elif long_opt == 'exec':
                if i + 1 < len(parts):
                    i += 1
                    options['exec_cmd'] = parts[i]
                i += 1
                continue
            elif long_opt == 'output':
                if i + 1 < len(parts):
                    i += 1
                    options['output_file'] = parts[i]
                i += 1
                continue
            i += 1
            continue
        if part.startswith('-') and len(part) > 1:
            opt_chars = part[1:]
            j = 0
            while j < len(opt_chars):
                char = opt_chars[j]
                if char == '4':
                    options['ipv4'] = True
                    j += 1
                elif char == '6':
                    options['ipv6'] = True
                    j += 1
                elif char == 'C':
                    options['crlf'] = True
                    j += 1
                elif char == 'D':
                    options['debug'] = True
                    j += 1
                elif char == 'd':
                    options['detach'] = True
                    j += 1
                elif char == 'F':
                    if j + 1 < len(opt_chars):
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                    j += 1
                elif char == 'h':
                    options['help'] = True
                    j += 1
                elif char == 'I':
                    if j + 1 < len(opt_chars):
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                    j += 1
                elif char == 'i':
                    if j + 1 < len(opt_chars):
                        options['interval'] = opt_chars[j + 1:]
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                        options['interval'] = parts[i]
                    j += 1
                elif char == 'k':
                    options['keepalive'] = True
                    j += 1
                elif char == 'L':
                    options['listen'] = True
                    j += 1
                elif char == 'l':
                    options['listen'] = True
                    j += 1
                elif char == 'N':
                    options['noshutdown'] = True
                    j += 1
                elif char == 'n':
                    options['nodns'] = True
                    j += 1
                elif char == 'O':
                    if j + 1 < len(opt_chars):
                        options['hex_dump'] = opt_chars[j + 1:]
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                        options['hex_dump'] = parts[i]
                    j += 1
                elif char == 'o':
                    if j + 1 < len(opt_chars):
                        options['output_file'] = opt_chars[j + 1:]
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                        options['output_file'] = parts[i]
                    j += 1
                elif char == 'P':
                    if j + 1 < len(opt_chars):
                        options['proxy_user'] = opt_chars[j + 1:]
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                        options['proxy_user'] = parts[i]
                    j += 1
                elif char == 'p':
                    if j + 1 < len(opt_chars):
                        options['source_port'] = opt_chars[j + 1:]
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                        options['source_port'] = parts[i]
                    j += 1
                elif char == 'q':
                    if j + 1 < len(opt_chars):
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                    j += 1
                elif char == 'r':
                    options['recvonly'] = True
                    j += 1
                elif char == 'S':
                    j += 1
                elif char == 's':
                    if j + 1 < len(opt_chars):
                        options['source_addr'] = opt_chars[j + 1:]
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                        options['source_addr'] = parts[i]
                    j += 1
                elif char == 'T':
                    if j + 1 < len(opt_chars):
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                    j += 1
                elif char == 't':
                    options['telnet'] = True
                    j += 1
                elif char == 'U':
                    j += 1
                elif char == 'u':
                    options['udp'] = True
                    j += 1
                elif char == 'V':
                    if j + 1 < len(opt_chars):
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                    j += 1
                elif char == 'v':
                    options['verbose'] = True
                    j += 1
                elif char == 'W':
                    if j + 1 < len(opt_chars):
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                    j += 1
                elif char == 'w':
                    if j + 1 < len(opt_chars):
                        options['timeout'] = opt_chars[j + 1:]
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                        options['timeout'] = parts[i]
                    j += 1
                elif char == 'X':
                    if j + 1 < len(opt_chars):
                        options['proxy_protocol'] = opt_chars[j + 1:]
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                        options['proxy_protocol'] = parts[i]
                    j += 1
                elif char == 'x':
                    if j + 1 < len(opt_chars):
                        options['proxy_addr'] = opt_chars[j + 1:]
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                        options['proxy_addr'] = parts[i]
                    j += 1
                elif char == 'Z':
                    j += 1
                elif char == 'z':
                    options['zeroio'] = True
                    options['scan'] = True
                    j += 1
                else:
                    j += 1
            i += 1
            continue
        positional_args.append(part)
        i += 1
    if options['help']:
        return (
            'Write-Output "usage: nc [-46CDdFhklNnrStUuvZz] [-I length] [-i interval] [-O length] '
            '[-P proxy_username] [-p source_port] [-q seconds] [-s source] [-T toskeyword] '
            '[-V rtable] [-w timeout] [-X proxy_protocol] [-x proxy_address[:port]] '
            '[destination] [port]\n'
            'Options:\n'
            '  -4, --ipv4           Use IPv4 only\n'
            '  -6, --ipv6           Use IPv6 only\n'
            '  -C, --crlf           Use CRLF for EOL sequence\n'
            '  -D, --debug          Enable debugging on the socket\n'
            '  -d, --detach         Detach from stdin\n'
            '  -h, --help           Display help\n'
            '  -i interval          Delay interval for lines sent\n'
            '  -k, --keepalive      Keep listening for more connections\n'
            '  -l, --listen         Listen mode\n'
            '  -n, --nodns          Do not resolve DNS\n'
            '  -p port              Specify source port\n'
            '  -s source            Specify source address\n'
            '  -t, --telnet         Answer TELNET negotiation\n'
            '  -u, --udp            Use UDP instead of TCP\n'
            '  -v, --verbose        Verbose output\n'
            '  -w timeout           Connection timeout\n'
            '  -z, --zero           Zero-I/O mode (scanning)"'
        )
    if options['version']:
        return 'Write-Output "nc: netcat (The netcat tool)"'
    if options['listen']:
        return _build_listen_command(options, positional_args)
    elif options['scan'] or options['zeroio']:
        return _build_scan_command(options, positional_args)
    else:
        return _build_connect_command(options, positional_args)
def _build_connect_command(options: Dict[str, Any], args: List[str]) -> str:
    if len(args) < 1:
        return 'Write-Error "nc: missing host operand"'
    if len(args) < 2:
        return 'Write-Error "nc: missing port operand"'
    host = args[0]
    port = args[1]
    if options['udp']:
        return (
            f'Write-Output "UDP connection to {host}:{port}..."; '
            f'$udpClient = New-Object System.Net.Sockets.UdpClient; '
            f'$udpClient.Connect("{host}", {port}); '
            f'$bytes = [System.Text.Encoding]::ASCII.GetBytes("test"); '
            f'$udpClient.Send($bytes, $bytes.Length) | Out-Null; '
            f'$udpClient.Close()'
        )
    cmd_parts = ['Test-NetConnection']
    cmd_parts.append(f'-ComputerName {host}')
    cmd_parts.append(f'-Port {port}')
    if options['verbose']:
        cmd_parts.append('-InformationLevel Detailed')
    if options['timeout']:
        try:
            timeout_val = int(options['timeout'])
            if timeout_val > 0:
                cmd_parts.append(f'-TimeoutSeconds {timeout_val}')
        except ValueError:
            pass
    if options['zeroio'] or options['scan']:
        cmd_parts.append('-WarningAction SilentlyContinue')
    return ' '.join(cmd_parts)
def _build_scan_command(options: Dict[str, Any], args: List[str]) -> str:
    if len(args) < 1:
        return 'Write-Error "nc: missing host operand"'
    host = args[0]
    if len(args) < 2:
        ports = "22,80,443,3389"
    else:
        ports = args[1]
    if '-' in ports:
        start_port, end_port = ports.split('-', 1)
        return (
            f'{start_port}..{end_port} | ForEach-Object {{ '
            f'$result = Test-NetConnection -ComputerName {host} -Port $_ -WarningAction SilentlyContinue; '
            f'if ($result.TcpTestSucceeded) {{ '
            f'Write-Output "{host} $_ open" '
            f'}} else {{ '
            f'Write-Output "{host} $_ closed" '
            f'}}'
            f'}}'
        )
    else:
        if ',' in ports:
            port_list = ports.split(',')
            return (
                f'@({",".join(port_list)}) | ForEach-Object {{ '
                f'$result = Test-NetConnection -ComputerName {host} -Port $_ -WarningAction SilentlyContinue; '
                f'if ($result.TcpTestSucceeded) {{ '
                f'Write-Output "{host} $_ open" '
                f'}} else {{ '
                f'Write-Output "{host} $_ closed" '
                f'}}'
                f'}}'
            )
        else:
            if options['verbose']:
                return f'Test-NetConnection -ComputerName {host} -Port {ports} -InformationLevel Detailed'
            else:
                return (
                    f'$result = Test-NetConnection -ComputerName {host} -Port {ports} -WarningAction SilentlyContinue; '
                    f'if ($result.TcpTestSucceeded) {{ '
                    f'Write-Output "{host} {ports} open" '
                    f'}} else {{ '
                    f'Write-Output "{host} {ports} closed" '
                    f'}}'
                )
def _build_listen_command(options: Dict[str, Any], args: List[str]) -> str:
    port = None
    if args:
        port = args[0]
    elif options['source_port']:
        port = options['source_port']
    if not port:
        return 'Write-Error "nc: missing port operand for listen mode"'
    if options['udp']:
        return (
            f'Write-Output "Listening on UDP port {port}... (Press Ctrl+C to stop)"; '
            f'$udpClient = New-Object System.Net.Sockets.UdpClient {port}; '
            f'$remoteEP = New-Object System.Net.IPEndPoint ([System.Net.IPAddress]::Any), {port}; '
            f'try {{ '
            f'while ($true) {{ '
            f'$data = $udpClient.Receive([ref]$remoteEP); '
            f'$text = [System.Text.Encoding]::ASCII.GetString($data); '
            f'Write-Output "$($remoteEP.Address):$($remoteEP.Port) - $text" '
            f'}}'
            f'}} finally {{ '
            f'$udpClient.Close() '
            f'}}'
        )
    return (
        f'Write-Output "Listening on TCP port {port}... (Press Ctrl+C to stop)"; '
        f'$listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Any, {port}); '
        f'$listener.Start(); '
        f'try {{ '
        f'$client = $listener.AcceptTcpClient(); '
        f'Write-Output "Connection from $($client.Client.RemoteEndPoint)"; '
        f'$stream = $client.GetStream(); '
        f'$reader = [System.IO.StreamReader]::new($stream); '
        f'while ($client.Connected) {{ '
        f'if ($stream.DataAvailable) {{ '
        f'$data = $reader.ReadLine(); '
        f'if ($data -ne $null) {{ Write-Output $data }} '
        f'}} '
        f'}}'
        f'}} finally {{ '
        f'$listener.Stop() '
        f'}}'
    )
if __name__ == "__main__":
    test_cases = [
        "nc google.com 80",
        "nc 192.168.1.1 22",
        "nc -z google.com 80",
        "nc -zv 192.168.1.1 22",
        "nc -z 192.168.1.1 1-1000",
        "nc -z 192.168.1.1 22,80,443",
        "nc -l 8080",
        "nc -l -p 8080",
        "nc -lk 8080",
        "nc -u 192.168.1.1 53",
        "nc -ul 53",
        "nc -v google.com 80",
        "nc -n 192.168.1.1 22",
        "nc -w 5 google.com 80",
        "nc -s 10.0.0.1 google.com 80",
        "nc -p 12345 google.com 80",
        "nc /z google.com 80",
        "nc /zv 192.168.1.1 22",
        "nc /l 8080",
        "nc /u /l 53",
        "nc --help",
        "nc -h",
        "nc --version",
        "",
        "nc",
        "nc google.com",
    ]
    for test in test_cases:
        result = _convert_nc(test)
        print(f"Input:  {test}")
        print(f"Output: {result}")
        print()
def _convert_netstat(cmd: str) -> str:
    if not cmd or not cmd.strip():
        return 'Get-NetTCPConnection'
    parts = _parse_command_line(cmd)
    if not parts:
        return 'Get-NetTCPConnection'
    if parts[0] in ('netstat', '/bin/netstat', '/usr/bin/netstat', '/usr/sbin/netstat'):
        parts = parts[1:]
    if not parts:
        return 'Get-NetTCPConnection'
    show_all = False
    show_tcp = False
    show_udp = False
    show_listening = False
    numeric = False
    show_programs = False
    show_route = False
    show_interfaces = False
    show_statistics = False
    continuous = False
    extend = False
    show_groups = False
    verbose = False
    show_raw = False
    show_unix = False
    numeric_hosts = False
    numeric_ports = False
    numeric_users = False
    show_help = False
    show_version = False
    i = 0
    while i < len(parts):
        part = parts[i]
        if part == '--':
            break
        if part.startswith('/') and len(part) >= 2 and part[1].isalpha():
            if len(part) == 2:
                part = '-' + part[1:]
            else:
                sub_part = part[1:]
                known_long_opts = {
                    'all', 'tcp', 'udp', 'listening', 'numeric', 'programs',
                    'route', 'interfaces', 'statistics', 'continuous', 'extend',
                    'groups', 'verbose', 'raw', 'unix', 'numeric-hosts',
                    'numeric-ports', 'numeric-users', 'help', 'version'
                }
                if '=' in sub_part:
                    part = '--' + sub_part
                elif sub_part in known_long_opts:
                    part = '--' + sub_part
                else:
                    part = '-' + sub_part
        if part.startswith('--'):
            long_opt = part[2:]
            if long_opt == 'help':
                show_help = True
                i += 1
                continue
            elif long_opt == 'version':
                show_version = True
                i += 1
                continue
            elif long_opt == 'all':
                show_all = True
                i += 1
                continue
            elif long_opt == 'tcp':
                show_tcp = True
                i += 1
                continue
            elif long_opt == 'udp':
                show_udp = True
                i += 1
                continue
            elif long_opt == 'listening':
                show_listening = True
                i += 1
                continue
            elif long_opt == 'numeric':
                numeric = True
                i += 1
                continue
            elif long_opt == 'programs':
                show_programs = True
                i += 1
                continue
            elif long_opt == 'route':
                show_route = True
                i += 1
                continue
            elif long_opt == 'interfaces':
                show_interfaces = True
                i += 1
                continue
            elif long_opt == 'statistics':
                show_statistics = True
                i += 1
                continue
            elif long_opt == 'continuous':
                continuous = True
                i += 1
                continue
            elif long_opt == 'extend':
                extend = True
                i += 1
                continue
            elif long_opt == 'groups':
                show_groups = True
                i += 1
                continue
            elif long_opt == 'verbose':
                verbose = True
                i += 1
                continue
            elif long_opt == 'raw':
                show_raw = True
                i += 1
                continue
            elif long_opt == 'unix':
                show_unix = True
                i += 1
                continue
            elif long_opt == 'numeric-hosts':
                numeric_hosts = True
                i += 1
                continue
            elif long_opt == 'numeric-ports':
                numeric_ports = True
                i += 1
                continue
            elif long_opt == 'numeric-users':
                numeric_users = True
                i += 1
                continue
            i += 1
            continue
        if part.startswith('-') and len(part) > 1:
            opt_chars = part[1:]
            for char in opt_chars:
                if char == 'a':
                    show_all = True
                elif char == 't':
                    show_tcp = True
                elif char == 'u':
                    show_udp = True
                elif char == 'l':
                    show_listening = True
                elif char == 'n':
                    numeric = True
                elif char == 'p':
                    show_programs = True
                elif char == 'r':
                    show_route = True
                elif char == 'i':
                    show_interfaces = True
                elif char == 's':
                    show_statistics = True
                elif char == 'c':
                    continuous = True
                elif char == 'e':
                    extend = True
                elif char == 'g':
                    show_groups = True
                elif char == 'v':
                    verbose = True
                elif char == 'w':
                    show_raw = True
                elif char == 'x':
                    show_unix = True
                elif char == 'h':
                    show_help = True
                elif char == 'V':
                    show_version = True
            i += 1
            continue
        i += 1
    return _build_netstat_powershell_command(
        show_all, show_tcp, show_udp, show_listening, numeric,
        show_programs, show_route, show_interfaces, show_statistics,
        continuous, extend, show_groups, verbose, show_raw, show_unix,
        numeric_hosts, numeric_ports, numeric_users, show_help, show_version
    )
def _build_netstat_powershell_command(
    show_all: bool,
    show_tcp: bool,
    show_udp: bool,
    show_listening: bool,
    numeric: bool,
    show_programs: bool,
    show_route: bool,
    show_interfaces: bool,
    show_statistics: bool,
    continuous: bool,
    extend: bool,
    show_groups: bool,
    verbose: bool,
    show_raw: bool,
    show_unix: bool,
    numeric_hosts: bool,
    numeric_ports: bool,
    numeric_users: bool,
    show_help: bool,
    show_version: bool
) -> str:
    if show_help:
        return (
            'Write-Output "netstat - Network statistics\n'
            'Usage: netstat [OPTION]...\n'
            'Options:\n'
            '  -a, --all           show both listening and non-listening sockets\n'
            '  -t, --tcp           display TCP connections\n'
            '  -u, --udp           display UDP connections\n'
            '  -l, --listening     show only listening sockets\n'
            '  -n, --numeric       show numerical addresses\n'
            '  -p, --programs      show PID/program name\n'
            '  -r, --route         display routing table\n'
            '  -i, --interfaces    display network interface statistics\n'
            '  -s, --statistics    display network statistics\n'
            '  -e, --extend        display extended information\n'
            '  -g, --groups        display multicast group membership\n'
            '  -c, --continuous    continuous listing\n'
            '  -v, --verbose       verbose output\n'
            '  -w, --raw           display raw sockets\n'
            '  -x, --unix          display Unix domain sockets\n'
            '      --numeric-hosts don\'t resolve hostnames\n'
            '      --numeric-ports don\'t resolve port names\n'
            '      --numeric-users don\'t resolve user names\n'
            '  -h, --help          display this help\n'
            '  -V, --version       display version information"'
        )
    if show_version:
        return 'Write-Output "netstat (net-tools) 2.10"'
    notes: List[str] = []
    if continuous:
        notes.append('# NOTE: Continuous listing (-c) not directly supported in PowerShell')
    if show_unix:
        notes.append('# NOTE: Unix domain sockets (-x) not applicable on Windows')
    if show_raw:
        notes.append('# NOTE: Raw sockets (-w) not directly supported in PowerShell')
    if show_groups:
        notes.append('# NOTE: Multicast group membership (-g) use: Get-NetMulticastSession or Get-NetIPInterface')
    if numeric_users:
        notes.append('# NOTE: User name resolution not applicable for network connections in PowerShell')
    if show_route:
        base_cmd = 'Get-NetRoute'
        if verbose:
            base_cmd += ' | Format-List'
        elif show_statistics:
            base_cmd += ' | Format-Table -AutoSize'
        if notes:
            return '; '.join(notes + [base_cmd])
        return base_cmd
    if show_interfaces:
        base_cmd = 'Get-NetAdapterStatistics'
        if show_statistics or extend:
            base_cmd += ' | Format-List'
        else:
            base_cmd += ' | Format-Table -AutoSize'
        if notes:
            return '; '.join(notes + [base_cmd])
        return base_cmd
    if show_statistics and not show_interfaces and not show_route:
        base_cmd = 'Get-NetAdapterStatistics | Format-List'
        if notes:
            return '; '.join(notes + [base_cmd])
        return base_cmd
    if show_udp and not show_tcp:
        notes.append('# NOTE: UDP connections not directly supported; Use Get-NetUDPEndpoint for UDP endpoints')
        base_cmd = 'Get-NetUDPEndpoint'
        if numeric or numeric_hosts or numeric_ports:
            base_cmd += ' | Select-Object LocalAddress, LocalPort'
        if notes:
            return '; '.join(notes + [base_cmd])
        return base_cmd
    base_cmd = 'Get-NetTCPConnection'
    filters: List[str] = []
    if show_listening and not show_all:
        filters.append('$_.State -eq "Listen"')
    elif show_all:
        filters.append('($_.State -eq "Listen" -or $_.State -eq "Established")')
    if filters:
        base_cmd += ' | Where-Object { ' + ' -and '.join(filters) + ' }'
    if numeric or numeric_hosts or numeric_ports:
        select_fields = ['LocalAddress', 'LocalPort', 'RemoteAddress', 'RemotePort', 'State']
        base_cmd += ' | Select-Object ' + ', '.join(select_fields)
    if show_programs:
        if numeric or numeric_hosts or numeric_ports:
            base_cmd = base_cmd.replace(
                ' | Select-Object LocalAddress, LocalPort, RemoteAddress, RemotePort, State',
                ' | Select-Object LocalAddress, LocalPort, RemoteAddress, RemotePort, State, OwningProcess, '
                '@{Name="ProcessName";Expression={(Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue).ProcessName}}'
            )
        else:
            base_cmd += ' | Select-Object *, OwningProcess, @{Name="ProcessName";Expression={(Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue).ProcessName}}'
    if extend:
        if 'Select-Object' not in base_cmd:
            base_cmd += ' | Format-List'
        else:
            base_cmd = base_cmd.replace(' | Select-Object', ' | Format-List')
    if verbose and 'Format-List' not in base_cmd:
        base_cmd += ' | Format-List'
    if notes:
        return '; '.join(notes + [base_cmd])
    return base_cmd
if __name__ == "__main__":
    test_cases = [
        "netstat",
        "netstat -a",
        "netstat -t",
        "netstat -u",
        "netstat -l",
        "netstat -n",
        "netstat -p",
        "netstat -r",
        "netstat -i",
        "netstat -s",
        "netstat -an",
        "netstat -at",
        "netstat -au",
        "netstat -lt",
        "netstat -ln",
        "netstat -ap",
        "netstat -e",
        "netstat -g",
        "netstat -v",
        "netstat -c",
        "netstat /a",
        "netstat /n",
        "netstat /r",
        "netstat --tcp",
        "netstat --udp",
        "netstat --all",
        "netstat --listening",
        "netstat --numeric",
        "netstat --route",
        "netstat --interfaces",
        "netstat --statistics",
        "netstat --help",
        "netstat --version",
        "netstat -tu",
        "netstat -antp",
        "netstat -anp",
        "netstat -rn",
    ]
    for test in test_cases:
        result = _convert_netstat(test)
        print(f"Input:  {test}")
        print(f"Output: {result}")
        print()
def _convert_nslookup(cmd: str) -> str:
    if not cmd or not cmd.strip():
        return 'Write-Output "usage: nslookup [-option] [name | -] [server]"'
    parts = _parse_command_line(cmd)
    if not parts:
        return 'Write-Output "usage: nslookup [-option] [name | -] [server]"'
    if parts[0] in ('nslookup', '/usr/bin/nslookup', '/bin/nslookup'):
        parts = parts[1:]
    if not parts:
        return 'Write-Output "usage: nslookup [-option] [name | -] [server]"'
    options: Dict[str, Any] = {
        'query_type': None,
        'debug': False,
        'timeout': None,
        'retry': None,
        'port': None,
        'query_class': None,
        'recurse': True,
        'vc': False,
        'domain': None,
        'search': None,
        'defname': None,
        'all': False,
        'help': False,
        'version': False,
    }
    target: Optional[str] = None
    server: Optional[str] = None
    VALID_QUERY_TYPES = {
        'A', 'AAAA', 'AFSDB', 'ATMA', 'CNAME', 'HINFO', 'ISDN', 'KEY',
        'MB', 'MD', 'MF', 'MG', 'MINFO', 'MR', 'MX', 'NS', 'NXT', 'PTR',
        'PX', 'RP', 'RT', 'SIG', 'SOA', 'SRV', 'TXT', 'WKS', 'X25', 'ANY'
    }
    VALID_QUERY_CLASSES = {'IN', 'CS', 'CH', 'HS', 'ANY'}
    LONG_BOOL_OPTS = {
        'help', 'h', 'version', 'V', 'all', 'debug', 'd',
        'recurse', 'rec', 'norecurse', 'norec',
        'vc', 'novc', 'search', 'srch', 'nosearch', 'nosrch',
        'defname', 'def', 'nodefname', 'nodef'
    }
    LONG_VALUE_OPTS = {
        'type', 'query', 'q', 'querytype', 'timeout', 'retry', 'port',
        'class', 'cl', 'queryclass', 'domain'
    }
    i = 0
    while i < len(parts):
        part = parts[i]
        if part == '--':
            i += 1
            if i < len(parts):
                target = parts[i]
                i += 1
            if i < len(parts):
                server = parts[i]
            break
        if part.startswith('/') and len(part) >= 2:
            opt_part = part[1:]
            if '=' in opt_part:
                opt_name = opt_part.split('=', 1)[0]
                if opt_name in LONG_VALUE_OPTS:
                    part = '-' + opt_part
                elif opt_name in LONG_BOOL_OPTS:
                    part = '-' + opt_part
            elif opt_part in LONG_BOOL_OPTS:
                part = '-' + opt_part
            elif opt_part in LONG_VALUE_OPTS:
                if i + 1 < len(parts) and not parts[i + 1].startswith('-') and not parts[i + 1].startswith('/'):
                    part = '-' + opt_part
                else:
                    part = '-' + opt_part
        if (part.startswith('-') or part.startswith('--')) and '=' in part:
            if part.startswith('--'):
                opt_name, opt_value = part[2:].split('=', 1)
            else:
                opt_name, opt_value = part[1:].split('=', 1)
            if opt_name in ('type', 'query', 'q', 'querytype'):
                options['query_type'] = opt_value.upper()
                i += 1
                continue
            elif opt_name == 'timeout':
                options['timeout'] = opt_value
                i += 1
                continue
            elif opt_name == 'retry':
                options['retry'] = opt_value
                i += 1
                continue
            elif opt_name == 'port':
                options['port'] = opt_value
                i += 1
                continue
            elif opt_name in ('class', 'cl', 'queryclass'):
                options['query_class'] = opt_value.upper()
                i += 1
                continue
            elif opt_name == 'domain':
                options['domain'] = opt_value
                i += 1
                continue
        if part.startswith('--'):
            long_opt = part[2:]
            if long_opt in ('help', 'h'):
                options['help'] = True
                i += 1
                continue
            elif long_opt in ('version', 'V'):
                options['version'] = True
                i += 1
                continue
            elif long_opt == 'all':
                options['all'] = True
                i += 1
                continue
            elif long_opt in ('debug', 'd'):
                options['debug'] = True
                i += 1
                continue
            elif long_opt in ('recurse', 'rec'):
                options['recurse'] = True
                i += 1
                continue
            elif long_opt in ('norecurse', 'norec'):
                options['recurse'] = False
                i += 1
                continue
            elif long_opt == 'vc':
                options['vc'] = True
                i += 1
                continue
            elif long_opt == 'novc':
                options['vc'] = False
                i += 1
                continue
            elif long_opt in ('search', 'srch'):
                options['search'] = True
                i += 1
                continue
            elif long_opt in ('nosearch', 'nosrch'):
                options['search'] = False
                i += 1
                continue
            elif long_opt in ('defname', 'def'):
                options['defname'] = True
                i += 1
                continue
            elif long_opt in ('nodefname', 'nodef'):
                options['defname'] = False
                i += 1
                continue
            elif long_opt in ('type', 'query', 'querytype'):
                if i + 1 < len(parts):
                    i += 1
                    options['query_type'] = parts[i].upper()
                i += 1
                continue
            elif long_opt == 'q':
                if i + 1 < len(parts):
                    i += 1
                    options['query_type'] = parts[i].upper()
                i += 1
                continue
            elif long_opt == 'timeout':
                if i + 1 < len(parts):
                    i += 1
                    options['timeout'] = parts[i]
                i += 1
                continue
            elif long_opt == 'retry':
                if i + 1 < len(parts):
                    i += 1
                    options['retry'] = parts[i]
                i += 1
                continue
            elif long_opt == 'port':
                if i + 1 < len(parts):
                    i += 1
                    options['port'] = parts[i]
                i += 1
                continue
            elif long_opt in ('class', 'cl', 'queryclass'):
                if i + 1 < len(parts):
                    i += 1
                    options['query_class'] = parts[i].upper()
                i += 1
                continue
            elif long_opt == 'domain':
                if i + 1 < len(parts):
                    i += 1
                    options['domain'] = parts[i]
                i += 1
                continue
            i += 1
            continue
        if part.startswith('-') and len(part) > 1:
            opt_chars = part[1:]
            if opt_chars in ('vc', 'novc', 'all', 'debug', 'recurse', 'norecurse',
                           'rec', 'norec', 'search', 'srch', 'nosearch', 'nosrch',
                           'defname', 'def', 'nodefname', 'nodef', 'version'):
                if opt_chars == 'vc':
                    options['vc'] = True
                elif opt_chars == 'novc':
                    options['vc'] = False
                elif opt_chars == 'all':
                    options['all'] = True
                elif opt_chars in ('debug', 'd'):
                    options['debug'] = True
                elif opt_chars in ('recurse', 'rec'):
                    options['recurse'] = True
                elif opt_chars in ('norecurse', 'norec'):
                    options['recurse'] = False
                elif opt_chars in ('search', 'srch'):
                    options['search'] = True
                elif opt_chars in ('nosearch', 'nosrch'):
                    options['search'] = False
                elif opt_chars in ('defname', 'def'):
                    options['defname'] = True
                elif opt_chars in ('nodefname', 'nodef'):
                    options['defname'] = False
                elif opt_chars == 'version':
                    options['version'] = True
                i += 1
                continue
            if opt_chars == 'cl':
                if i + 1 < len(parts):
                    i += 1
                    options['query_class'] = parts[i].upper()
                i += 1
                continue
            j = 0
            while j < len(opt_chars):
                char = opt_chars[j]
                if char == 'h':
                    options['help'] = True
                    j += 1
                elif char == 'V':
                    options['version'] = True
                    j += 1
                elif char == 'd':
                    options['debug'] = True
                    j += 1
                elif char in ('t', 'q'):
                    if j + 1 < len(opt_chars):
                        options['query_type'] = opt_chars[j + 1:].upper()
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                        options['query_type'] = parts[i].upper()
                    j += 1
                elif char == 'c':
                    if j + 1 < len(opt_chars):
                        options['query_class'] = opt_chars[j + 1:].upper()
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                        options['query_class'] = parts[i].upper()
                    j += 1
                elif char == 'p':
                    if j + 1 < len(opt_chars):
                        options['port'] = opt_chars[j + 1:]
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                        options['port'] = parts[i]
                    j += 1
                elif char == 'l':
                    j += 1
                else:
                    j += 1
            i += 1
            continue
        if target is None:
            target = part
            i += 1
        elif server is None:
            server = part
            i += 1
        else:
            i += 1
    if options['help']:
        return (
            'Write-Output "nslookup - query DNS servers\n'
            'Usage: nslookup [option] [host-to-find] | [server]\n'
            'Options:\n'
            '  -type=TYPE, -query=TYPE, -q=TYPE  query type (A, MX, NS, SOA, TXT, etc.)\n'
            '  -debug, -d                        enable debug mode\n'
            '  -timeout=SECONDS                  set timeout\n'
            '  -retry=NUM                        set number of retries\n'
            '  -port=PORT                        specify DNS port\n'
            '  -class=CLASS, -cl=CLASS           query class (IN, CH, HS, etc.)\n'
            '  -norecurse                        disable recursive queries\n'
            '  -vc                               use TCP instead of UDP\n'
            '  -domain=DOMAIN                    set default domain\n'
            '  -search                           use search list\n'
            '  -nosearch                         don\'t use search list\n'
            '  -all                              print options and current server\n'
            '  -help, -h                         show help\n'
            '  -version, -V                      show version"'
        )
    if options['version']:
        return 'Write-Output "nslookup (bundled with Windows)"'
    if options['all']:
        return (
            'Write-Output "Default Server:  (system default)\n'
            'Address:  (system default)\n\n'
            'Set options:\n'
            '  nodebug\n'
            '  defname\n'
            '  search\n'
            '  recurse\n'
            '  timeout = 2\n'
            '  retry = 1\n'
            '  port = 53\n'
            '  querytype = A\n'
            '  class = IN\n'
            '  novc\n'
            '  noignore"'
        )
    if target is None:
        return 'Write-Output "usage: nslookup [-option] [name | -] [server]"'
    ps_args: List[str] = []
    ps_args.append(target)
    if server:
        ps_args.append(f'-Server {server}')
    if options['query_type']:
        if options['query_type'] in VALID_QUERY_TYPES:
            ps_args.append(f'-Type {options["query_type"]}')
        else:
            ps_args.append(f'-Type {options["query_type"]}')
    if options['debug']:
        ps_args.append('-DnsOnly')
    cmd_str = 'Resolve-DnsName ' + ' '.join(ps_args)
    return cmd_str
if __name__ == "__main__":
    test_cases = [
        "nslookup google.com",
        "nslookup 8.8.8.8",
        "nslookup google.com 8.8.8.8",
        "nslookup -type=MX google.com",
        "nslookup -query=NS google.com",
        "nslookup -q=A google.com",
        "nslookup -q A google.com",
        "nslookup -t MX google.com",
        "nslookup -tMX google.com",
        "nslookup --type=AAAA google.com",
        "nslookup --query=SOA google.com",
        "nslookup --type TXT google.com",
        "nslookup --type TXT google.com",
        "nslookup -type=TXT google.com",
        "nslookup -debug google.com",
        "nslookup -d google.com",
        "nslookup --debug google.com",
        "nslookup -timeout=5 google.com",
        "nslookup --timeout 10 google.com",
        "nslookup -retry=3 google.com",
        "nslookup --retry 2 google.com",
        "nslookup -port=53 google.com",
        "nslookup --port 53 google.com",
        "nslookup -p 53 google.com",
        "nslookup -p53 google.com",
        "nslookup -class=IN google.com",
        "nslookup -cl IN google.com",
        "nslookup -c IN google.com",
        "nslookup -cIN google.com",
        "nslookup --class IN google.com",
        "nslookup -norecurse google.com",
        "nslookup --norecurse google.com",
        "nslookup -recurse google.com",
        "nslookup -vc google.com",
        "nslookup --vc google.com",
        "nslookup -novc google.com",
        "nslookup --novc google.com",
        "nslookup -domain=example.com host",
        "nslookup --domain example.com host",
        "nslookup -search google.com",
        "nslookup --search google.com",
        "nslookup -nosearch google.com",
        "nslookup --nosearch google.com",
        "nslookup -defname google.com",
        "nslookup --defname google.com",
        "nslookup -nodefname google.com",
        "nslookup --nodefname google.com",
        "nslookup -all",
        "nslookup --all",
        "nslookup -help",
        "nslookup -h",
        "nslookup --help",
        "nslookup -version",
        "nslookup -V",
        "nslookup --version",
        "nslookup /type=MX google.com",
        "nslookup /q=A google.com",
        "nslookup /debug google.com",
        "nslookup /help",
        "nslookup /all",
        "nslookup /vc google.com",
        "nslookup /novc google.com",
        "nslookup -type=MX -timeout=5 google.com",
        "nslookup -q=A -debug google.com 8.8.8.8",
        "",
        "nslookup",
    ]
    for test in test_cases:
        result = _convert_nslookup(test)
        print(f"Input:  {test}")
        print(f"Output: {result}")
        print()
def _convert_paste(cmd: str) -> str:
    if not cmd or not cmd.strip():
        return '$input'
    parts = _parse_command_line(cmd)
    if not parts:
        return '$input'
    if parts[0] in ('paste', '/bin/paste', '/usr/bin/paste'):
        parts = parts[1:]
    if not parts:
        return '$input'
    delimiters: Optional[str] = None
    serial = False
    zero_terminated = False
    show_help = False
    show_version = False
    files: List[str] = []
    i = 0
    while i < len(parts):
        part = parts[i]
        if part == '--':
            files.extend(parts[i + 1:])
            break
        if part.startswith('/') and len(part) >= 2 and part[1].isalpha():
            sub_part = part[1:]
            if len(part) == 2:
                part = '-' + part[1:]
            elif '=' in sub_part:
                part = '--' + sub_part
            elif sub_part in ('delimiters', 'serial', 'zero-terminated', 'help', 'version'):
                part = '--' + sub_part
            elif all(c.isalpha() for c in sub_part) and len(sub_part) <= 3:
                part = '-' + sub_part
        if part.startswith('--'):
            long_opt = part[2:]
            if long_opt == 'help':
                show_help = True
                i += 1
                continue
            if long_opt == 'version':
                show_version = True
                i += 1
                continue
            if long_opt == 'serial':
                serial = True
                i += 1
                continue
            if long_opt == 'zero-terminated':
                zero_terminated = True
                i += 1
                continue
            if long_opt.startswith('delimiters='):
                delimiters = long_opt.split('=', 1)[1]
                i += 1
                continue
            elif long_opt == 'delimiters':
                if i + 1 < len(parts) and not parts[i + 1].startswith('-'):
                    i += 1
                    delimiters = parts[i]
                i += 1
                continue
            i += 1
            continue
        if part.startswith('-') and len(part) > 1:
            opt_chars = part[1:]
            j = 0
            while j < len(opt_chars):
                char = opt_chars[j]
                if char == 'd':
                    if j + 1 < len(opt_chars):
                        remaining = opt_chars[j + 1:]
                        if remaining and all(c in 'sz' for c in remaining):
                            for c in remaining:
                                if c == 's':
                                    serial = True
                                elif c == 'z':
                                    zero_terminated = True
                            if i + 1 < len(parts) and not parts[i + 1].startswith('-'):
                                i += 1
                                delimiters = parts[i]
                            break
                        else:
                            delimiters = remaining
                            break
                    elif i + 1 < len(parts):
                        i += 1
                        delimiters = parts[i]
                    j += 1
                elif char == 's':
                    serial = True
                    j += 1
                elif char == 'z':
                    zero_terminated = True
                    j += 1
                else:
                    j += 1
            i += 1
            continue
        files.append(part)
        i += 1
    return _build_paste_powershell_command(
        delimiters, serial, zero_terminated, show_help, show_version, files
    )
def _build_paste_powershell_command(
    delimiters: Optional[str],
    serial: bool,
    zero_terminated: bool,
    show_help: bool,
    show_version: bool,
    files: List[str]
) -> str:
    if show_help:
        return ('Write-Output "paste - Merge lines of files\n'
                'Usage: paste [OPTION]... [FILE]...\n'
                'Write lines consisting of sequentially corresponding lines from each FILE,\n'
                'separated by TABs, to standard output.\n'
                'With no FILE, or when FILE is -, read standard input.\n\n'
                'Mandatory arguments to long options are mandatory for short options too.\n'
                '  -d, --delimiters=LIST   reuse characters from LIST instead of TABs\n'
                '  -s, --serial            paste one file at a time instead of in parallel\n'
                '  -z, --zero-terminated   line delimiter is NUL, not newline\n'
                '      --help              display this help and exit\n'
                '      --version           output version information and exit"')
    if show_version:
        return 'Write-Output "paste (GNU coreutils) 8.32"'
    notes: List[str] = []
    if zero_terminated:
        notes.append('# NOTE: -z (zero-terminated) not directly supported in PowerShell')
    delimiter = delimiters if delimiters is not None else '\t'
    escaped_delimiter = delimiter.replace('"', '`"').replace('$', '`$').replace('`', '``')
    if ' ' in escaped_delimiter or '"' in escaped_delimiter or '$' in escaped_delimiter or '`' in escaped_delimiter:
        delimiter_str = f'"{escaped_delimiter}"'
    elif escaped_delimiter == '\t':
        delimiter_str = '"`t"'
    elif escaped_delimiter == '\n':
        delimiter_str = '"`n"'
    elif escaped_delimiter == '\r\n':
        delimiter_str = '"`r`n"'
    else:
        delimiter_str = f'"{escaped_delimiter}"'
    if serial:
        if not files:
            cmd = f'$input | Join-String -Separator {delimiter_str}'
        elif len(files) == 1:
            file_quoted = f'"{files[0]}"' if ' ' in files[0] and not (files[0].startswith('"') or files[0].startswith("'")) else files[0]
            cmd = f'Get-Content {file_quoted} | Join-String -Separator {delimiter_str}'
        else:
            commands: List[str] = []
            for f in files:
                file_quoted = f'"{f}"' if ' ' in f and not (f.startswith('"') or f.startswith("'")) else f
                commands.append(f'Get-Content {file_quoted} | Join-String -Separator {delimiter_str}')
            cmd = '; '.join(commands)
    else:
        if not files:
            cmd = f'$input | ForEach-Object {{ $lines = @($_); $lines -join {delimiter_str} }}'
        elif len(files) == 1:
            file_quoted = f'"{files[0]}"' if ' ' in files[0] and not (files[0].startswith('"') or files[0].startswith("'")) else files[0]
            cmd = f'Get-Content {file_quoted}'
        else:
            quoted_files: List[str] = []
            for f in files:
                if ' ' in f and not (f.startswith('"') or f.startswith("'")):
                    quoted_files.append(f'"{f}"')
                else:
                    quoted_files.append(f)
            file_list = ', '.join(quoted_files)
            num_files = len(files)
            cmd = (
                f'$files = {file_list}; '
                f'$contents = $files | ForEach-Object {{ Get-Content $_ }}; '
                f'$maxLines = ($contents | Measure-Object -Maximum -Property Count).Maximum; '
                f'for ($i = 0; $i -lt $maxLines; $i++) {{ '
                f'$lineParts = @(); '
                f'foreach ($content in $contents) {{ '
                f'if ($i -lt $content.Count) {{ $lineParts += $content[$i] }} '
                f'else {{ $lineParts += "" }} '
                f'}}; '
                f'$lineParts -join {delimiter_str} '
                f'}}'
            )
    if notes:
        cmd += '  ' + ' '.join(notes)
    return cmd
if __name__ == "__main__":
    test_cases = [
        "paste file1.txt file2.txt",
        "paste -d ',' file1.txt file2.txt",
        "paste -s file.txt",
        "paste --serial file.txt",
        "paste -d ':' -s file.txt",
        "paste --delimiters=':' file1.txt file2.txt",
        "paste /d ',' file1.txt file2.txt",
        "paste /s file.txt",
        "paste -z file.txt",
        "paste --help",
        "paste --version",
        "paste",
        "paste -",
        "paste file1.txt",
        "paste -d '|' -s file1.txt file2.txt",
        "paste -ds ',' file.txt",
        "paste -sd ',' file.txt",
        "paste /d ',' /s file.txt",
        "paste --delimiters ',' file1.txt file2.txt",
        "paste -d'|' file.txt",
        "paste /serial file.txt",
    ]
    for test in test_cases:
        result = _convert_paste(test)
        print(f"Input:  {test}")
        print(f"Output: {result}")
        print()
def _convert_ping(cmd: str) -> str:
    if not cmd or not cmd.strip():
        return 'Write-Output "usage: ping [-aAbBdDfhLnOqrRUvV] [-c count] [-i interval] [-I interface] [-m mark] [-M pmtudisc_option] [-l preload] [-p pattern] [-Q tos] [-s packetsize] [-S sndbuf] [-t ttl] [-T timestamp_option] [-w deadline] [-W timeout] [hop1 ...] destination"'
    parts = _parse_command_line(cmd)
    if not parts:
        return 'Write-Output "usage: ping [-aAbBdDfhLnOqrRUvV] [-c count] [-i interval] [-I interface] [-m mark] [-M pmtudisc_option] [-l preload] [-p pattern] [-Q tos] [-s packetsize] [-S sndbuf] [-t ttl] [-T timestamp_option] [-w deadline] [-W timeout] [hop1 ...] destination"'
    if parts[0] in ('ping', '/bin/ping', '/usr/bin/ping'):
        parts = parts[1:]
    if not parts:
        return 'Write-Output "usage: ping [-aAbBdDfhLnOqrRUvV] [-c count] [-i interval] [-I interface] [-m mark] [-M pmtudisc_option] [-l preload] [-p pattern] [-Q tos] [-s packetsize] [-S sndbuf] [-t ttl] [-T timestamp_option] [-w deadline] [-W timeout] [hop1 ...] destination"'
    options: Dict[str, Any] = {
        'audible': False,
        'adaptive': False,
        'broadcast': False,
        'debug': False,
        'flood': False,
        'help': False,
        'numeric': False,
        'quiet': False,
        'verbose': False,
        'version': False,
        'count': None,
        'interval': None,
        'interface': None,
        'mark': None,
        'pmtudisc': None,
        'preload': None,
        'pattern': None,
        'tos': None,
        'packetsize': None,
        'sndbuf': None,
        'ttl': None,
        'timestamp_option': None,
        'deadline': None,
        'timeout': None,
        'ipv4': False,
        'ipv6': False,
        'record_route': False,
        'source': None,
        'hop': [],
    }
    destination: Optional[str] = None
    VALID_SHORT_OPTS = 'aAbBdDfhLnOqrRUvVc:i:I:m:M:l:p:Q:s:S:t:T:w:W:46'
    VALID_LONG_OPTS = {
        'help', 'version', 'audible', 'adaptive', 'broadcast', 'debug', 'flood',
        'numeric', 'quiet', 'verbose', 'count', 'interval', 'interface', 'mark',
        'pmtudisc', 'mtu-discovery', 'preload', 'pattern', 'tos', 'packetsize',
        'size', 'sndbuf', 'ttl', 'timestamp', 'timestamp-option', 'deadline',
        'timeout', 'ipv4', 'ipv6', 'record-route', 'source', 'hop'
    }
    i = 0
    while i < len(parts):
        part = parts[i]
        if part == '--':
            i += 1
            if i < len(parts):
                destination = parts[i]
            break
        if part.startswith('/') and len(part) >= 2:
            opt_part = part[1:]
            if len(opt_part) == 1 and opt_part in VALID_SHORT_OPTS:
                part = '-' + opt_part
            elif opt_part in VALID_LONG_OPTS:
                part = '--' + opt_part
            elif '=' in opt_part:
                opt_name = opt_part.split('=', 1)[0]
                if opt_name in VALID_LONG_OPTS:
                    part = '--' + opt_part
            elif all(c in VALID_SHORT_OPTS for c in opt_part):
                part = '-' + opt_part
        if part.startswith('--'):
            long_opt = part[2:]
            if '=' in long_opt:
                opt_name, opt_value = long_opt.split('=', 1)
                if opt_name == 'count':
                    options['count'] = opt_value
                elif opt_name == 'interval':
                    options['interval'] = opt_value
                elif opt_name == 'interface':
                    options['interface'] = opt_value
                elif opt_name == 'mark':
                    options['mark'] = opt_value
                elif opt_name in ('pmtudisc', 'mtu-discovery'):
                    options['pmtudisc'] = opt_value
                elif opt_name == 'preload':
                    options['preload'] = opt_value
                elif opt_name == 'pattern':
                    options['pattern'] = opt_value
                elif opt_name == 'tos':
                    options['tos'] = opt_value
                elif opt_name in ('packetsize', 'size'):
                    options['packetsize'] = opt_value
                elif opt_name == 'sndbuf':
                    options['sndbuf'] = opt_value
                elif opt_name == 'ttl':
                    options['ttl'] = opt_value
                elif opt_name in ('timestamp', 'timestamp-option'):
                    options['timestamp_option'] = opt_value
                elif opt_name == 'deadline':
                    options['deadline'] = opt_value
                elif opt_name == 'timeout':
                    options['timeout'] = opt_value
                elif opt_name == 'source':
                    options['source'] = opt_value
                i += 1
                continue
            if long_opt == 'help':
                options['help'] = True
                i += 1
                continue
            elif long_opt == 'version':
                options['version'] = True
                i += 1
                continue
            elif long_opt == 'audible':
                options['audible'] = True
                i += 1
                continue
            elif long_opt == 'adaptive':
                options['adaptive'] = True
                i += 1
                continue
            elif long_opt == 'broadcast':
                options['broadcast'] = True
                i += 1
                continue
            elif long_opt == 'debug':
                options['debug'] = True
                i += 1
                continue
            elif long_opt == 'flood':
                options['flood'] = True
                i += 1
                continue
            elif long_opt == 'numeric':
                options['numeric'] = True
                i += 1
                continue
            elif long_opt == 'quiet':
                options['quiet'] = True
                i += 1
                continue
            elif long_opt == 'verbose':
                options['verbose'] = True
                i += 1
                continue
            elif long_opt == 'ipv4':
                options['ipv4'] = True
                i += 1
                continue
            elif long_opt == 'ipv6':
                options['ipv6'] = True
                i += 1
                continue
            elif long_opt == 'record-route':
                options['record_route'] = True
                i += 1
                continue
            elif long_opt == 'count':
                if i + 1 < len(parts):
                    i += 1
                    options['count'] = parts[i]
                i += 1
                continue
            elif long_opt == 'interval':
                if i + 1 < len(parts):
                    i += 1
                    options['interval'] = parts[i]
                i += 1
                continue
            elif long_opt == 'interface':
                if i + 1 < len(parts):
                    i += 1
                    options['interface'] = parts[i]
                i += 1
                continue
            elif long_opt == 'mark':
                if i + 1 < len(parts):
                    i += 1
                    options['mark'] = parts[i]
                i += 1
                continue
            elif long_opt in ('pmtudisc', 'mtu-discovery'):
                if i + 1 < len(parts):
                    i += 1
                    options['pmtudisc'] = parts[i]
                i += 1
                continue
            elif long_opt == 'preload':
                if i + 1 < len(parts):
                    i += 1
                    options['preload'] = parts[i]
                i += 1
                continue
            elif long_opt == 'pattern':
                if i + 1 < len(parts):
                    i += 1
                    options['pattern'] = parts[i]
                i += 1
                continue
            elif long_opt == 'tos':
                if i + 1 < len(parts):
                    i += 1
                    options['tos'] = parts[i]
                i += 1
                continue
            elif long_opt in ('packetsize', 'size'):
                if i + 1 < len(parts):
                    i += 1
                    options['packetsize'] = parts[i]
                i += 1
                continue
            elif long_opt == 'sndbuf':
                if i + 1 < len(parts):
                    i += 1
                    options['sndbuf'] = parts[i]
                i += 1
                continue
            elif long_opt == 'ttl':
                if i + 1 < len(parts):
                    i += 1
                    options['ttl'] = parts[i]
                i += 1
                continue
            elif long_opt in ('timestamp', 'timestamp-option'):
                if i + 1 < len(parts):
                    i += 1
                    options['timestamp_option'] = parts[i]
                i += 1
                continue
            elif long_opt == 'deadline':
                if i + 1 < len(parts):
                    i += 1
                    options['deadline'] = parts[i]
                i += 1
                continue
            elif long_opt == 'timeout':
                if i + 1 < len(parts):
                    i += 1
                    options['timeout'] = parts[i]
                i += 1
                continue
            elif long_opt == 'source':
                if i + 1 < len(parts):
                    i += 1
                    options['source'] = parts[i]
                i += 1
                continue
            i += 1
            continue
        if part.startswith('-') and len(part) > 1:
            opt_chars = part[1:]
            j = 0
            while j < len(opt_chars):
                char = opt_chars[j]
                if char == 'a':
                    options['audible'] = True
                    j += 1
                elif char == 'A':
                    options['adaptive'] = True
                    j += 1
                elif char == 'b':
                    options['broadcast'] = True
                    j += 1
                elif char == 'B':
                    j += 1
                elif char == 'd':
                    options['debug'] = True
                    j += 1
                elif char == 'D':
                    j += 1
                elif char == 'f':
                    options['flood'] = True
                    j += 1
                elif char == 'h':
                    options['help'] = True
                    j += 1
                elif char == 'L':
                    j += 1
                elif char == 'n':
                    if j + 1 < len(opt_chars) and opt_chars[j + 1:].isdigit():
                        options['count'] = opt_chars[j + 1:]
                        j = len(opt_chars)
                    elif j + 1 < len(opt_chars):
                        options['numeric'] = True
                        j += 1
                    elif i + 1 < len(parts) and parts[i + 1].isdigit():
                        i += 1
                        options['count'] = parts[i]
                        j += 1
                    else:
                        options['numeric'] = True
                        j += 1
                elif char == 'O':
                    j += 1
                elif char == 'q':
                    options['quiet'] = True
                    j += 1
                elif char == 'r':
                    j += 1
                elif char == 'R':
                    options['record_route'] = True
                    j += 1
                elif char == 'U':
                    j += 1
                elif char == 'v':
                    options['verbose'] = True
                    j += 1
                elif char == 'V':
                    options['version'] = True
                    j += 1
                elif char == '4':
                    options['ipv4'] = True
                    j += 1
                elif char == '6':
                    options['ipv6'] = True
                    j += 1
                elif char == 'c':
                    if j + 1 < len(opt_chars):
                        val = opt_chars[j + 1:]
                        num_end = 0
                        while num_end < len(val) and (val[num_end].isdigit() or val[num_end] == '.'):
                            num_end += 1
                        if num_end > 0:
                            options['count'] = val[:num_end]
                            j = j + 1 + num_end
                        else:
                            j += 1
                    elif i + 1 < len(parts):
                        i += 1
                        options['count'] = parts[i]
                        j += 1
                    else:
                        j += 1
                elif char == 'i':
                    if j + 1 < len(opt_chars):
                        options['interval'] = opt_chars[j + 1:]
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                        options['interval'] = parts[i]
                    j += 1
                elif char == 'I':
                    if j + 1 < len(opt_chars):
                        options['interface'] = opt_chars[j + 1:]
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                        options['interface'] = parts[i]
                    j += 1
                elif char == 'm':
                    if j + 1 < len(opt_chars):
                        options['mark'] = opt_chars[j + 1:]
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                        options['mark'] = parts[i]
                    j += 1
                elif char == 'M':
                    if j + 1 < len(opt_chars):
                        options['pmtudisc'] = opt_chars[j + 1:]
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                        options['pmtudisc'] = parts[i]
                    j += 1
                elif char == 'l':
                    if j + 1 < len(opt_chars):
                        options['preload'] = opt_chars[j + 1:]
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                        options['preload'] = parts[i]
                    j += 1
                elif char == 'p':
                    if j + 1 < len(opt_chars):
                        options['pattern'] = opt_chars[j + 1:]
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                        options['pattern'] = parts[i]
                    j += 1
                elif char == 'Q':
                    if j + 1 < len(opt_chars):
                        options['tos'] = opt_chars[j + 1:]
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                        options['tos'] = parts[i]
                    j += 1
                elif char == 's':
                    if j + 1 < len(opt_chars):
                        options['packetsize'] = opt_chars[j + 1:]
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                        options['packetsize'] = parts[i]
                    j += 1
                elif char == 'S':
                    if j + 1 < len(opt_chars):
                        val = opt_chars[j + 1:]
                        if '.' in val or ':' in val:
                            options['source'] = val
                        else:
                            options['sndbuf'] = val
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                        val = parts[i]
                        if '.' in val or ':' in val:
                            options['source'] = val
                        else:
                            options['sndbuf'] = val
                    j += 1
                elif char == 't':
                    if j + 1 < len(opt_chars):
                        options['ttl'] = opt_chars[j + 1:]
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                        options['ttl'] = parts[i]
                    j += 1
                elif char == 'T':
                    if j + 1 < len(opt_chars):
                        options['timestamp_option'] = opt_chars[j + 1:]
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                        options['timestamp_option'] = parts[i]
                    j += 1
                elif char == 'w':
                    if j + 1 < len(opt_chars):
                        options['deadline'] = opt_chars[j + 1:]
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                        options['deadline'] = parts[i]
                    j += 1
                elif char == 'W':
                    if j + 1 < len(opt_chars):
                        options['timeout'] = opt_chars[j + 1:]
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                        options['timeout'] = parts[i]
                    j += 1
                else:
                    j += 1
            i += 1
            continue
        if destination is None:
            destination = part
            i += 1
        else:
            options['hop'].append(part)
            i += 1
    if options['help']:
        return (
            'Write-Output "usage: ping [-aAbBdDfhLnOqrRUvV] [-c count] [-i interval] [-I interface] [-m mark] [-M pmtudisc_option] [-l preload] [-p pattern] [-Q tos] [-s packetsize] [-S sndbuf] [-t ttl] [-T timestamp_option] [-w deadline] [-W timeout] [hop1 ...] destination"'
        )
    if options['version']:
        return 'ping -V'
    if destination is None:
        return 'Write-Output "usage: ping [-aAbBdDfhLnOqrRUvV] [-c count] [-i interval] [-I interface] [-m mark] [-M pmtudisc_option] [-l preload] [-p pattern] [-Q tos] [-s packetsize] [-S sndbuf] [-t ttl] [-T timestamp_option] [-w deadline] [-W timeout] [hop1 ...] destination"'
    ping_args = []
    if options['ipv4']:
        ping_args.append('-4')
    if options['ipv6']:
        ping_args.append('-6')
    if options['count']:
        ping_args.append('-n')
        ping_args.append(options['count'])
    if options['packetsize']:
        ping_args.append('-l')
        ping_args.append(options['packetsize'])
    if options['ttl']:
        ping_args.append('-i')
        ping_args.append(options['ttl'])
    if options['deadline']:
        try:
            deadline_ms = int(float(options['deadline']) * 1000)
            ping_args.append('-w')
            ping_args.append(str(deadline_ms))
        except ValueError:
            pass
    if options['timeout']:
        try:
            timeout_ms = int(float(options['timeout']) * 1000)
            ping_args.append('-w')
            ping_args.append(str(timeout_ms))
        except ValueError:
            pass
    if options['pmtudisc'] == 'do':
        ping_args.append('-f')
    if options['record_route']:
        ping_args.append('-r')
    if options['source']:
        ping_args.append('-S')
        ping_args.append(options['source'])
    if options['quiet']:
        pass
    ping_args.append(destination)
    cmd_str = 'ping ' + ' '.join(ping_args)
    return cmd_str
if __name__ == "__main__":
    test_cases = [
        "ping google.com",
        "ping 8.8.8.8",
        "ping -c 4 google.com",
        "ping -c4 google.com",
        "ping --count 4 google.com",
        "ping --count=4 google.com",
        "ping -n 4 google.com",
        "ping -s 1024 google.com",
        "ping -s1024 google.com",
        "ping --packetsize 1024 google.com",
        "ping --size=1024 google.com",
        "ping -t 64 google.com",
        "ping -t64 google.com",
        "ping --ttl 64 google.com",
        "ping -W 5 google.com",
        "ping -w 10 google.com",
        "ping --timeout 5 google.com",
        "ping --deadline 10 google.com",
        "ping -i 0.5 google.com",
        "ping -i0.5 google.com",
        "ping --interval 1 google.com",
        "ping -4 google.com",
        "ping -6 google.com",
        "ping --ipv4 google.com",
        "ping --ipv6 google.com",
        "ping -S 192.168.1.1 google.com",
        "ping --source 192.168.1.1 google.com",
        "ping -M do google.com",
        "ping --pmtudisc do google.com",
        "ping -R google.com",
        "ping --record-route google.com",
        "ping -c 4 -s 1024 -t 64 google.com",
        "ping -i 0.5 -W 5 8.8.8.8",
        "ping /c 4 google.com",
        "ping /n 4 google.com",
        "ping /4 /c 4 google.com",
        "ping /s 1024 google.com",
        "ping -h",
        "ping --help",
        "ping -V",
        "ping --version",
        "",
        "ping",
    ]
    for test in test_cases:
        result = _convert_ping(test)
        print(f"Input:  {test}")
        print(f"Output: {result}")
        print()
def _convert_readlink(cmd: str) -> str:
    if not cmd or not cmd.strip():
        return 'Write-Error "readlink: missing operand"'
    parts = _parse_command_line(cmd)
    if not parts:
        return 'Write-Error "readlink: missing operand"'
    if parts[0] in ('readlink', '/bin/readlink', '/usr/bin/readlink'):
        parts = parts[1:]
    if not parts:
        return 'Write-Error "readlink: missing operand"'
    known_long_options = {
        'help', 'version', 'canonicalize', 'canonicalize-existing',
        'canonicalize-missing', 'no-newline', 'quiet', 'silent', 'verbose'
    }
    canonicalize = False
    canonicalize_existing = False
    canonicalize_missing = False
    no_newline = False
    quiet = False
    verbose = False
    show_help = False
    show_version = False
    i = 0
    while i < len(parts):
        part = parts[i]
        original_part = part
        if part == '--':
            i += 1
            break
        if part.startswith('/') and len(part) >= 2:
            if len(part) == 2 and part[1].isalpha():
                part = '-' + part[1:]
            elif len(part) > 2 and part[1].isalpha():
                potential_opt = part[1:]
                if potential_opt in known_long_options or any(
                    opt.startswith(potential_opt) for opt in known_long_options
                ):
                    part = '--' + potential_opt
        if part.startswith('--'):
            long_opt = part[2:]
            if long_opt == 'help':
                show_help = True
                i += 1
                continue
            elif long_opt == 'version':
                show_version = True
                i += 1
                continue
            elif long_opt == 'canonicalize':
                canonicalize = True
                i += 1
                continue
            elif long_opt == 'canonicalize-existing':
                canonicalize_existing = True
                i += 1
                continue
            elif long_opt == 'canonicalize-missing':
                canonicalize_missing = True
                i += 1
                continue
            elif long_opt == 'no-newline':
                no_newline = True
                i += 1
                continue
            elif long_opt in ('quiet', 'silent'):
                quiet = True
                i += 1
                continue
            elif long_opt == 'verbose':
                verbose = True
                i += 1
                continue
            break
        if part.startswith('-') and len(part) > 1:
            opt_chars = part[1:]
            j = 0
            while j < len(opt_chars):
                char = opt_chars[j]
                if char == 'f':
                    canonicalize = True
                    j += 1
                elif char == 'e':
                    canonicalize_existing = True
                    j += 1
                elif char == 'm':
                    canonicalize_missing = True
                    j += 1
                elif char == 'n':
                    no_newline = True
                    j += 1
                elif char in ('q', 's'):
                    quiet = True
                    j += 1
                elif char == 'v':
                    verbose = True
                    j += 1
                elif char == '-':
                    j += 1
                    i += 1
                    break
                else:
                    j += 1
            i += 1
            continue
        break
    if show_help:
        return (
            'Write-Output "Usage: readlink [OPTION]... FILE...\n'
            'Print value of a symbolic link or canonical file name\n\n'
            '  -f, --canonicalize            canonicalize by following every symlink in\n'
            '                                every component of the given name recursively;\n'
            '                                all but the last component must exist\n'
            '  -e, --canonicalize-existing   canonicalize by following every symlink in\n'
            '                                every component of the given name recursively;\n'
            '                                all components must exist\n'
            '  -m, --canonicalize-missing    canonicalize by following every symlink in\n'
            '                                every component of the given name recursively;\n'
            '                                without requirements on components existence\n'
            '  -n, --no-newline              do not output the trailing delimiter\n'
            '  -q, --quiet,\n'
            '  -s, --silent                  suppress most error messages\n'
            '  -v, --verbose                 report error messages\n'
            '      --help     display this help and exit\n'
            '      --version  output version information and exit"'
        )
    if show_version:
        return 'Write-Output "readlink (GNU coreutils) 8.32"'
    file_paths = parts[i:]
    if not file_paths:
        return 'Write-Error "readlink: missing operand"'
    commands = []
    for file_path in file_paths:
        if ' ' in file_path and not (file_path.startswith('"') or file_path.startswith("'")):
            quoted_path = f'"{file_path}"'
        else:
            quoted_path = file_path
        if canonicalize or canonicalize_existing:
            ps_cmd = f'Resolve-Path -Path {quoted_path}'
            if quiet:
                ps_cmd = f'Resolve-Path -Path {quoted_path} -ErrorAction SilentlyContinue'
            ps_cmd += ' | Select-Object -ExpandProperty Path'
        elif canonicalize_missing:
            ps_cmd = f'$ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath({quoted_path})'
        else:
            error_action = 'SilentlyContinue' if quiet else 'Continue'
            ps_cmd = f'(Get-Item {quoted_path} -ErrorAction {error_action}).Target'
        if no_newline:
            ps_cmd = f'Write-Host -NoNewline ({ps_cmd})'
        commands.append(ps_cmd)
    if len(commands) == 1:
        return commands[0]
    return '; '.join(commands)
def _convert_realpath(cmd: str) -> str:
    if not cmd or not cmd.strip():
        return 'Write-Output "realpath: missing operand"'
    parts = _parse_command_line(cmd)
    if not parts:
        return 'Write-Output "realpath: missing operand"'
    if parts[0] in ('realpath', '/bin/realpath', '/usr/bin/realpath'):
        parts = parts[1:]
    if not parts:
        return 'Write-Output "realpath: missing operand"'
    canonicalize_existing = False
    canonicalize_missing = False
    logical = False
    physical = False
    strip_symlinks = False
    quiet = False
    zero_terminated = False
    relative_to: Optional[str] = None
    relative_base: Optional[str] = None
    show_help = False
    show_version = False
    i = 0
    while i < len(parts):
        part = parts[i]
        if part == '--':
            i += 1
            break
        if part.startswith('/') and len(part) >= 2:
            if len(part) == 2 and part[1].isalpha():
                part = '-' + part[1:]
            elif len(part) > 2 and part[1].isalpha():
                sub_part = part[1:]
                if '=' in sub_part:
                    part = '--' + sub_part
                elif sub_part in ('canonicalize-existing', 'canonicalize-missing', 'logical',
                                  'physical', 'strip', 'no-symlinks', 'quiet', 'zero',
                                  'relative-to', 'relative-base', 'help', 'version'):
                    part = '--' + sub_part
                else:
                    part = '-' + sub_part
        if part.startswith('--'):
            long_opt = part[2:]
            if '=' in long_opt:
                opt_name, opt_value = long_opt.split('=', 1)
                if opt_name == 'relative-to':
                    relative_to = opt_value
                elif opt_name == 'relative-base':
                    relative_base = opt_value
                i += 1
                continue
            if long_opt == 'help':
                show_help = True
                i += 1
                continue
            elif long_opt == 'version':
                show_version = True
                i += 1
                continue
            elif long_opt == 'canonicalize-existing':
                canonicalize_existing = True
                i += 1
                continue
            elif long_opt == 'canonicalize-missing':
                canonicalize_missing = True
                i += 1
                continue
            elif long_opt == 'logical':
                logical = True
                i += 1
                continue
            elif long_opt == 'physical':
                physical = True
                i += 1
                continue
            elif long_opt in ('strip', 'no-symlinks'):
                strip_symlinks = True
                i += 1
                continue
            elif long_opt == 'quiet':
                quiet = True
                i += 1
                continue
            elif long_opt == 'zero':
                zero_terminated = True
                i += 1
                continue
            elif long_opt == 'relative-to':
                if i + 1 < len(parts):
                    i += 1
                    relative_to = parts[i]
                i += 1
                continue
            elif long_opt == 'relative-base':
                if i + 1 < len(parts):
                    i += 1
                    relative_base = parts[i]
                i += 1
                continue
            i += 1
            continue
        if part.startswith('-') and len(part) > 1:
            opt_chars = part[1:]
            for char in opt_chars:
                if char == 'e':
                    canonicalize_existing = True
                elif char == 'm':
                    canonicalize_missing = True
                elif char == 'L':
                    logical = True
                elif char == 'P':
                    physical = True
                elif char == 's':
                    strip_symlinks = True
                elif char == 'q':
                    quiet = True
                elif char == 'z':
                    zero_terminated = True
            i += 1
            continue
        break
    if show_help:
        help_text = (
            'Write-Output "Usage: realpath [OPTION]... FILE...\n'
            'Print the resolved absolute file name.\n\n'
            '  -e, --canonicalize-existing  all components must exist\n'
            '  -m, --canonicalize-missing   no components need to exist\n'
            '  -L, --logical                resolve symlinks as encountered (default)\n'
            '  -P, --physical               resolve symlinks before processing components\n'
            '  -s, --strip, --no-symlinks   do not expand symlinks\n'
            '  -q, --quiet                  suppress most error messages\n'
            '  -z, --zero                   end each output line with NUL, not newline\n'
            '      --relative-to=DIR        print resolved path relative to DIR\n'
            '      --relative-base=DIR      print absolute paths unless path is under DIR\n'
            '      --help                   display this help and exit\n'
            '      --version                output version information and exit"'
        )
        return help_text
    if show_version:
        return 'Write-Output "realpath (GNU coreutils) 8.32"'
    file_paths = parts[i:]
    if not file_paths:
        return 'Write-Output "realpath: missing operand"'
    commands: List[str] = []
    for file_path in file_paths:
        if ' ' in file_path and not (file_path.startswith('"') or file_path.startswith("'")):
            quoted_path = f'"{file_path}"'
        else:
            quoted_path = file_path
        if canonicalize_missing:
            ps_cmd = f'[System.IO.Path]::GetFullPath({quoted_path})'
        elif relative_to:
            if ' ' in relative_to and not (relative_to.startswith('"') or relative_to.startswith("'")):
                quoted_relative_to = f'"{relative_to}"'
            else:
                quoted_relative_to = relative_to
            ps_cmd = (
                f'$base = Resolve-Path -Path {quoted_relative_to} -ErrorAction SilentlyContinue | '
                f'Select-Object -ExpandProperty Path; '
                f'$target = Resolve-Path -Path {quoted_path} -ErrorAction SilentlyContinue | '
                f'Select-Object -ExpandProperty Path; '
                f'if ($base -and $target) {{ '
                f'[System.Uri]::UnescapeDataString(([System.Uri]::new($base)).MakeRelativeUri('
                f'([System.Uri]::new($target))).ToString()) '
                f'}} else {{ '
                f'Write-Error "Cannot resolve path" '
                f'}}'
            )
        elif relative_base:
            if ' ' in relative_base and not (relative_base.startswith('"') or relative_base.startswith("'")):
                quoted_relative_base = f'"{relative_base}"'
            else:
                quoted_relative_base = relative_base
            ps_cmd = (
                f'$base = Resolve-Path -Path {quoted_relative_base} -ErrorAction SilentlyContinue | '
                f'Select-Object -ExpandProperty Path; '
                f'$target = Resolve-Path -Path {quoted_path} -ErrorAction SilentlyContinue | '
                f'Select-Object -ExpandProperty Path; '
                f'if ($base -and $target -and $target.StartsWith($base)) {{ '
                f'[System.Uri]::UnescapeDataString(([System.Uri]::new($base)).MakeRelativeUri('
                f'([System.Uri]::new($target))).ToString()) '
                f'}} else {{ '
                f'$target '
                f'}}'
            )
        elif physical or strip_symlinks:
            ps_cmd = f'[System.IO.Path]::GetFullPath({quoted_path})'
        else:
            error_action = 'SilentlyContinue' if quiet else 'Stop'
            ps_cmd = (
                f'(Resolve-Path -Path {quoted_path} -ErrorAction {error_action} | '
                f'Select-Object -ExpandProperty Path)'
            )
        if zero_terminated:
            ps_cmd = f'Write-Host -NoNewline ({ps_cmd}); Write-Host -NoNewline "`0"'
        commands.append(ps_cmd)
    if len(commands) == 1:
        return commands[0]
    return '; '.join(commands)
def _convert_route(cmd: str) -> str:
    if not cmd or not cmd.strip():
        return 'Get-NetRoute'
    parts = _parse_command_line(cmd)
    if not parts:
        return 'Get-NetRoute'
    if parts[0] in ('route', '/sbin/route', '/usr/sbin/route', '/bin/route'):
        parts = parts[1:]
    if not parts:
        return 'Get-NetRoute'
    options: Dict[str, Any] = {
        'numeric': False,
        'verbose': False,
        'netstat_format': False,
        'extended': False,
        'fib': True,
        'cache': False,
        'family': None,
        'help': False,
        'version': False,
    }
    action: Optional[str] = None
    target: Optional[str] = None
    target_type: Optional[str] = None
    netmask: Optional[str] = None
    gateway: Optional[str] = None
    metric: Optional[str] = None
    mss: Optional[str] = None
    window: Optional[str] = None
    irtt: Optional[str] = None
    reject: bool = False
    device: Optional[str] = None
    i = 0
    while i < len(parts):
        part = parts[i]
        if part == '--':
            i += 1
            while i < len(parts):
                remaining = parts[i]
                if target is None:
                    target = remaining
                i += 1
            break
        if part in ('-net', '-host'):
            target_type = part[1:]
            i += 1
            continue
        if part.startswith('/') and len(part) >= 2:
            opt_part = part[1:]
            if len(opt_part) == 1:
                part = '-' + opt_part
            elif opt_part in ('help', 'version', 'inet', 'inet6'):
                part = '--' + opt_part
            elif opt_part in ('net', 'host'):
                part = '-' + opt_part
            elif all(c in 'CFvnNee46A' for c in opt_part):
                part = '-' + opt_part
            else:
                part = '-' + opt_part
        if part.startswith('--'):
            long_opt = part[2:]
            if long_opt == 'help':
                options['help'] = True
                i += 1
                continue
            elif long_opt == 'version':
                options['version'] = True
                i += 1
                continue
            elif long_opt == 'inet':
                options['family'] = 'inet'
                i += 1
                continue
            elif long_opt == 'inet6':
                options['family'] = 'inet6'
                i += 1
                continue
            i += 1
            continue
        if part.startswith('-') and len(part) > 1:
            opt_chars = part[1:]
            j = 0
            while j < len(opt_chars):
                char = opt_chars[j]
                if char == 'n':
                    options['numeric'] = True
                    j += 1
                elif char == 'v':
                    options['verbose'] = True
                    j += 1
                elif char == 'e':
                    if options['netstat_format']:
                        options['extended'] = True
                    options['netstat_format'] = True
                    j += 1
                elif char == 'F':
                    options['fib'] = True
                    options['cache'] = False
                    j += 1
                elif char == 'C':
                    options['cache'] = True
                    options['fib'] = False
                    j += 1
                elif char == '4':
                    options['family'] = 'inet'
                    j += 1
                elif char == '6':
                    options['family'] = 'inet6'
                    j += 1
                elif char == 'A':
                    if j + 1 < len(opt_chars):
                        family_val = opt_chars[j + 1:]
                        if family_val in ('inet', 'inet6'):
                            options['family'] = family_val
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                        family_val = parts[i]
                        if family_val in ('inet', 'inet6'):
                            options['family'] = family_val
                    j += 1
                elif char == 'V':
                    options['version'] = True
                    j += 1
                elif char == 'h':
                    if j == 0 and len(opt_chars) == 1:
                        options['help'] = True
                    j += 1
                elif char == 'N':
                    options['family'] = 'inet6'
                    j += 1
                else:
                    j += 1
            i += 1
            continue
        if part in ('add', 'del', 'delete', 'flush'):
            action = 'add' if part == 'add' else 'del'
            i += 1
            continue
        if part == 'netmask':
            if i + 1 < len(parts):
                i += 1
                netmask = parts[i]
            i += 1
            continue
        if part == 'gw' or part == 'gateway':
            if i + 1 < len(parts):
                i += 1
                gateway = parts[i]
            i += 1
            continue
        if part == 'metric':
            if i + 1 < len(parts):
                i += 1
                metric = parts[i]
            i += 1
            continue
        if part == 'mss':
            if i + 1 < len(parts):
                i += 1
                mss = parts[i]
            i += 1
            continue
        if part == 'window':
            if i + 1 < len(parts):
                i += 1
                window = parts[i]
            i += 1
            continue
        if part == 'irtt':
            if i + 1 < len(parts):
                i += 1
                irtt = parts[i]
            i += 1
            continue
        if part == 'reject':
            reject = True
            i += 1
            continue
        if part in ('mod', 'dyn', 'reinstate'):
            i += 1
            continue
        if part == 'dev':
            if i + 1 < len(parts):
                i += 1
                device = parts[i]
            i += 1
            continue
        if target is None:
            target = part
        elif device is None:
            device = part
        i += 1
    if options['help']:
        return (
            'Write-Output "route - show / manipulate the IP routing table\n'
            'Usage: route [-CFvnNee] [-A family |-4|-6]\n'
            '       route [-v] [-A family |-4|-6] add [-net|-host] target [options]\n'
            '       route [-v] [-A family |-4|-6] del [-net|-host] target [options]\n'
            'Options:\n'
            '  -n, --numeric      show numerical addresses\n'
            '  -v, --verbose      verbose operation\n'
            '  -e, --extend       use netstat-format display\n'
            '  -ee                very long listing\n'
            '  -F, --fib          operate on FIB routing table (default)\n'
            '  -C, --cache        operate on routing cache\n'
            '  -A family          use specified address family (inet, inet6)\n'
            '  -4                 use IPv4\n'
            '  -6                 use IPv6\n'
            '  -V, --version      display version\n'
            '  -h, --help         display this help\n'
            'Route modifiers:\n'
            '  -net               target is a network\n'
            '  -host              target is a host\n'
            '  netmask Nm         netmask for route\n'
            '  gw Gw              gateway address\n'
            '  metric N           set metric to N\n'
            '  mss M              set MTU to M bytes\n'
            '  window W           set TCP window size\n'
            '  irtt I             set initial RTT to I ms\n'
            '  reject             install blocking route\n'
            '  dev If             force route via device"'
        )
    if options['version']:
        return 'Write-Output "net-tools 2.10"'
    return _build_route_powershell_command(
        action, target, target_type, netmask, gateway, metric,
        mss, window, irtt, reject, device, options
    )
def _build_route_powershell_command(
    action: Optional[str],
    target: Optional[str],
    target_type: Optional[str],
    netmask: Optional[str],
    gateway: Optional[str],
    metric: Optional[str],
    mss: Optional[str],
    window: Optional[str],
    irtt: Optional[str],
    reject: bool,
    device: Optional[str],
    options: Dict[str, Any]
) -> str:
    if action is None:
        base_cmd = 'Get-NetRoute'
        filters: List[str] = []
        if options['family'] == 'inet':
            filters.append('$_.AddressFamily -eq "IPv4"')
        elif options['family'] == 'inet6':
            filters.append('$_.AddressFamily -eq "IPv6"')
        if filters:
            base_cmd += ' | Where-Object { ' + ' -and '.join(filters) + ' }'
        if options['numeric']:
            base_cmd += ' | Select-Object DestinationPrefix, NextHop, InterfaceAlias, RouteMetric, State'
        elif options['netstat_format']:
            if options['extended']:
                base_cmd += ' | Format-List'
            else:
                base_cmd += ' | Format-Table -AutoSize'
        elif options['verbose']:
            base_cmd += ' | Format-List'
        return base_cmd
    if action == 'add':
        if target is None:
            return 'Write-Error "Target destination is required for add operation"'
        dest_prefix = _build_destination_prefix(target, netmask, target_type)
        cmd_parts: List[str] = ['New-NetRoute']
        cmd_parts.append(f'-DestinationPrefix "{dest_prefix}"')
        if gateway:
            cmd_parts.append(f'-NextHop "{gateway}"')
        if metric:
            cmd_parts.append(f'-RouteMetric {metric}')
        if device:
            cmd_parts.append(f'-InterfaceAlias "{device}"')
        if options['family'] == 'inet':
            cmd_parts.append('-AddressFamily IPv4')
        elif options['family'] == 'inet6':
            cmd_parts.append('-AddressFamily IPv6')
        notes: List[str] = []
        if mss:
            notes.append(f'# NOTE: MSS ({mss}) not directly supported in PowerShell route')
        if window:
            notes.append(f'# NOTE: TCP window size ({window}) not directly supported')
        if irtt:
            notes.append(f'# NOTE: Initial RTT ({irtt}) not directly supported')
        if reject:
            notes.append('# NOTE: Reject route not directly supported in PowerShell')
        result = ' '.join(cmd_parts)
        if notes:
            return '; '.join(notes + [result])
        return result
    if action == 'del':
        if target is None:
            return 'Write-Error "Target destination is required for delete operation"'
        dest_prefix = _build_destination_prefix(target, netmask, target_type)
        cmd_parts = ['Remove-NetRoute']
        cmd_parts.append(f'-DestinationPrefix "{dest_prefix}"')
        if gateway:
            cmd_parts.append(f'-NextHop "{gateway}"')
        if device:
            cmd_parts.append(f'-InterfaceAlias "{device}"')
        if options['family'] == 'inet':
            cmd_parts.append('-AddressFamily IPv4')
        elif options['family'] == 'inet6':
            cmd_parts.append('-AddressFamily IPv6')
        cmd_parts.append('-Confirm:$false')
        return ' '.join(cmd_parts)
    return 'Get-NetRoute'
def _build_destination_prefix(
    target: str,
    netmask: Optional[str],
    target_type: Optional[str]
) -> str:
    if target == 'default':
        if netmask:
            prefix_len = _netmask_to_prefix_len(netmask)
            return f"0.0.0.0/{prefix_len}"
        return "0.0.0.0/0"
    if '/' in target:
        return target
    if netmask:
        prefix_len = _netmask_to_prefix_len(netmask)
    elif target_type == 'host':
        prefix_len = 32
    elif target_type == 'net':
        prefix_len = 24
    else:
        if '.' in target and len(target.split('.')) == 4:
            try:
                parts = target.split('.')
                if all(0 <= int(p) <= 255 for p in parts):
                    prefix_len = 32
                else:
                    prefix_len = 24
            except ValueError:
                prefix_len = 24
        else:
            prefix_len = 24
    return f"{target}/{prefix_len}"
def _netmask_to_prefix_len(netmask: str) -> int:
    try:
        parts = netmask.split('.')
        if len(parts) == 4:
            binary = ''
            for part in parts:
                binary += bin(int(part))[2:].zfill(8)
            return binary.count('1')
    except (ValueError, IndexError):
        pass
    return 24
if __name__ == "__main__":
    test_cases = [
        "route",
        "route -n",
        "route -e",
        "route -ee",
        "route -v",
        "route -4",
        "route -6",
        "route -A inet",
        "route -A inet6",
        "route add -net 192.168.1.0 netmask 255.255.255.0 gw 192.168.1.1",
        "route add -host 192.168.1.100 gw 192.168.1.1",
        "route add default gw 192.168.1.1",
        "route add -net 10.0.0.0 netmask 255.0.0.0 gw 10.0.0.1 metric 100",
        "route add -net 172.16.0.0/16 gw 172.16.0.1",
        "route add -net 192.168.0.0 netmask 255.255.0.0 dev eth0",
        "route del -net 192.168.1.0 netmask 255.255.255.0",
        "route del default",
        "route del -host 192.168.1.100",
        "route /n",
        "route /4",
        "route /n /4",
        "route add /net 192.168.2.0 netmask 255.255.255.0 gw 192.168.2.1",
        "route -h",
        "route --help",
        "route -V",
        "route --version",
        "",
    ]
    for test in test_cases:
        result = _convert_route(test)
        print(f"Input:  {test}")
        print(f"Output: {result}")
        print()
def _convert_rsync(cmd: str) -> str:
    if not cmd or not cmd.strip():
        return 'Write-Output "rsync: missing operand"'
    parts = _parse_command_line(cmd)
    if not parts:
        return 'Write-Output "rsync: missing operand"'
    if parts[0] in ('rsync', '/usr/bin/rsync', '/bin/rsync'):
        parts = parts[1:]
    if not parts:
        return 'Write-Output "rsync: missing operand"'
    options: Dict[str, Any] = {
        'archive': False,
        'recursive': False,
        'links': False,
        'perms': False,
        'times': False,
        'group': False,
        'owner': False,
        'devices': False,
        'specials': False,
        'verbose': False,
        'quiet': False,
        'dry_run': False,
        'delete': False,
        'delete_before': False,
        'delete_during': False,
        'delete_after': False,
        'delete_excluded': False,
        'compress': False,
        'update': False,
        'existing': False,
        'whole_file': False,
        'backup': False,
        'backup_dir': None,
        'suffix': None,
        'compare_dest': None,
        'copy_dest': None,
        'link_dest': None,
        'max_size': None,
        'min_size': None,
        'bwlimit': None,
        'timeout': None,
        'contimeout': None,
        'port': None,
        'rsh': None,
        'rsync_path': None,
        'stats': False,
        'itemize': False,
        'human_readable': False,
        'numeric_ids': False,
        'partial': False,
        'partial_dir': None,
        'temp_dir': None,
        'fake_super': False,
        'super': False,
        'inplace': False,
        'append': False,
        'append_verify': False,
        'checksum': False,
        'size_only': False,
        'ignore_times': False,
        'modify_window': None,
        'cvs_exclude': False,
        'from0': False,
        'protect_args': False,
        'address': None,
        'blocking_io': None,
        'omit_dir_times': False,
        'omit_link_times': False,
        'fuzzy': False,
        'copy_dirlinks': False,
        'keep_dirlinks': False,
        'copy_unsafe_links': False,
        'safe_links': False,
        'munge_links': False,
        'ignore_errors': False,
        'force': False,
        'delay_updates': False,
        'prune_empty_dirs': False,
        'list_only': False,
        'ignore_existing': False,
        'remove_source_files': False,
        'one_file_system': False,
        'show_help': False,
        'show_version': False,
        'relative': False,
        'dirs': False,
        'hard_links': False,
        'acls': False,
        'xattrs': False,
        'atimes': False,
        'crtimes': False,
        'copy_links': False,
        'progress': False,
        'sparse': False,
        'executability': False,
        'inc_recursive': True,
        'no_implied_dirs': False,
        'trust_sender': False,
        'delete_missing_args': False,
        '8_bit_output': False,
        'chmod': None,
        'usermap': None,
        'groupmap': None,
        'chown': None,
        'compress_level': None,
        'skip_compress': None,
        'out_format': None,
        'iconv': None,
        'checksum_seed': None,
        'write_batch': None,
        'only_write_batch': None,
        'read_batch': None,
        'protocol': None,
        'stop_at': None,
        'time_limit': None,
        'outbuf': None,
        'sockopts': None,
        'copy_as': None,
        'block_size': None,
        'remote_option': None,
    }
    exclude_patterns: List[str] = []
    exclude_from_files: List[str] = []
    include_patterns: List[str] = []
    include_from_files: List[str] = []
    filters: List[str] = []
    files_from: Optional[str] = None
    log_file: Optional[str] = None
    log_format: Optional[str] = None
    password_file: Optional[str] = None
    paths: List[str] = []
    VALID_SHORT_OPTS = 'avzqhnoOpPtiIbHuglrRWCxXcSsTkyYJKmneE'
    VALID_LONG_OPTS = {
        'archive', 'recursive', 'links', 'perms', 'times', 'group', 'owner',
        'devices', 'specials', 'verbose', 'quiet', 'dry-run', 'delete',
        'delete-before', 'delete-during', 'delete-after', 'delete-excluded',
        'compress', 'update', 'existing', 'whole-file', 'backup', 'backup-dir',
        'suffix', 'compare-dest', 'copy-dest', 'link-dest', 'max-size', 'min-size',
        'bwlimit', 'timeout', 'contimeout', 'port', 'rsh', 'rsync-path', 'stats',
        'itemize-changes', 'human-readable', 'numeric-ids', 'partial', 'partial-dir',
        'temp-dir', 'fake-super', 'super', 'no-super', 'inplace', 'append',
        'append-verify', 'checksum', 'size-only', 'ignore-times', 'modify-window',
        'cvs-exclude', 'filter', 'files-from', 'from0', 'protect-args',
        'no-protect-args', 'address', 'sockopts', 'outbuf', 'blocking-io',
        'no-blocking-io', 'omit-dir-times', 'omit-link-times', 'fuzzy',
        'copy-dirlinks', 'keep-dirlinks', 'copy-unsafe-links', 'safe-links',
        'munge-links', 'ignore-errors', 'force', 'delay-updates', 'prune-empty-dirs',
        'log-file', 'log-format', 'password-file', 'list-only', 'ignore-existing',
        'remove-source-files', 'one-file-system', 'help', 'version', 'progress',
        'no-inc-recursive', 'inc-recursive', 'relative', 'no-relative',
        'dirs', 'no-dirs', 'links', 'no-links', 'copy-links', 'copy-unsafe-links',
        'safe-links', 'munge-links', 'hard-links', 'no-hard-links',
        'acls', 'no-acls', 'xattrs', 'no-xattrs', 'atimes', 'no-atimes',
        'crtimes', 'no-crtimes', 'omit-dir-times', 'no-omit-dir-times',
        'omit-link-times', 'no-omit-link-times', 'checksum', 'no-checksum',
        'ignore-times', 'size-only', 'modify-window', 'temp-dir', 'fuzzy',
        'compare-dest', 'copy-dest', 'link-dest', 'compress', 'no-compress',
        'compress-level', 'skip-compress', 'cvs-exclude', 'include', 'include-from',
        'exclude', 'exclude-from', 'delete', 'delete-before', 'delete-during',
        'delete-after', 'delete-excluded', 'delete-missing-args', 'ignore-errors',
        'force', 'delay-updates', 'prune-empty-dirs', 'numeric-ids', 'usermap',
        'groupmap', 'chown', 'max-size', 'min-size', 'bwlimit', 'stop-at',
        'time-limit', 'outbuf', 'block-size', 'rsh', 'rsync-path', 'temp-dir',
        'compress-level', 'skip-compress', 'stats', '8-bit-output', 'human-readable',
        'progress', 'itemize-changes', 'remote-option', 'out-format', 'log-file',
        'log-format', 'password-file', 'list-only', 'bwlimit', 'stop-after',
        'stop-at', 'time-limit', 'outbuf', 'write-batch', 'only-write-batch',
        'read-batch', 'protocol', 'iconv', 'checksum-seed', 'server', 'sender',
        'no-implied-dirs', 'trust-sender', 'copy-as', 'address', 'port', 'sockopts',
        'blocking-io', 'no-blocking-io', 'stats', '8-bit-output', 'human-readable',
        'progress', 'itemize-changes', 'remote-option', 'out-format', 'log-file',
        'log-format', 'password-file', 'list-only', 'help', 'version',
    }
    i = 0
    while i < len(parts):
        part = parts[i]
        if part == '--':
            i += 1
            paths.extend(parts[i:])
            break
        if part.startswith('/') and len(part) >= 2:
            opt_part = part[1:]
            if len(opt_part) == 1 and opt_part in VALID_SHORT_OPTS:
                part = '-' + opt_part
            elif opt_part in VALID_LONG_OPTS:
                part = '--' + opt_part
            elif '=' in opt_part:
                opt_name = opt_part.split('=', 1)[0]
                if opt_name in VALID_LONG_OPTS:
                    part = '--' + opt_part
            elif all(c in VALID_SHORT_OPTS for c in opt_part):
                part = '-' + opt_part
        if part.startswith('--'):
            long_opt = part[2:]
            if '=' in long_opt:
                opt_name, opt_value = long_opt.split('=', 1)
                if opt_name == 'exclude':
                    exclude_patterns.append(opt_value)
                elif opt_name == 'exclude-from':
                    exclude_from_files.append(opt_value)
                elif opt_name == 'include':
                    include_patterns.append(opt_value)
                elif opt_name == 'include-from':
                    include_from_files.append(opt_value)
                elif opt_name == 'filter':
                    filters.append(opt_value)
                elif opt_name == 'files-from':
                    files_from = opt_value
                elif opt_name == 'backup-dir':
                    options['backup_dir'] = opt_value
                elif opt_name == 'suffix':
                    options['suffix'] = opt_value
                elif opt_name == 'compare-dest':
                    options['compare_dest'] = opt_value
                elif opt_name == 'copy-dest':
                    options['copy_dest'] = opt_value
                elif opt_name == 'link-dest':
                    options['link_dest'] = opt_value
                elif opt_name == 'max-size':
                    options['max_size'] = opt_value
                elif opt_name == 'min-size':
                    options['min_size'] = opt_value
                elif opt_name == 'bwlimit':
                    options['bwlimit'] = opt_value
                elif opt_name == 'timeout':
                    options['timeout'] = opt_value
                elif opt_name == 'contimeout':
                    options['contimeout'] = opt_value
                elif opt_name == 'port':
                    options['port'] = opt_value
                elif opt_name == 'rsh':
                    options['rsh'] = opt_value
                elif opt_name == 'rsync-path':
                    options['rsync_path'] = opt_value
                elif opt_name == 'partial-dir':
                    options['partial_dir'] = opt_value
                elif opt_name == 'temp-dir':
                    options['temp_dir'] = opt_value
                elif opt_name == 'modify-window':
                    options['modify_window'] = opt_value
                elif opt_name == 'address':
                    options['address'] = opt_value
                elif opt_name == 'sockopts':
                    options['sockopts'] = opt_value
                elif opt_name == 'outbuf':
                    options['outbuf'] = opt_value
                elif opt_name == 'log-file':
                    log_file = opt_value
                elif opt_name == 'log-format':
                    log_format = opt_value
                elif opt_name == 'password-file':
                    password_file = opt_value
                elif opt_name == 'compress-level':
                    options['compress_level'] = opt_value
                elif opt_name == 'skip-compress':
                    options['skip_compress'] = opt_value
                elif opt_name == 'usermap':
                    options['usermap'] = opt_value
                elif opt_name == 'groupmap':
                    options['groupmap'] = opt_value
                elif opt_name == 'chown':
                    options['chown'] = opt_value
                elif opt_name == 'stop-at':
                    options['stop_at'] = opt_value
                elif opt_name == 'time-limit':
                    options['time_limit'] = opt_value
                elif opt_name == 'block-size':
                    options['block_size'] = opt_value
                elif opt_name == 'out-format':
                    options['out_format'] = opt_value
                elif opt_name == 'remote-option':
                    options['remote_option'] = opt_value
                elif opt_name == 'iconv':
                    options['iconv'] = opt_value
                elif opt_name == 'checksum-seed':
                    options['checksum_seed'] = opt_value
                elif opt_name == 'write-batch':
                    options['write_batch'] = opt_value
                elif opt_name == 'only-write-batch':
                    options['only_write_batch'] = opt_value
                elif opt_name == 'read-batch':
                    options['read_batch'] = opt_value
                elif opt_name == 'protocol':
                    options['protocol'] = opt_value
                elif opt_name == 'copy-as':
                    options['copy_as'] = opt_value
                i += 1
                continue
            if long_opt == 'help':
                options['show_help'] = True
                i += 1
                continue
            elif long_opt == 'version':
                options['show_version'] = True
                i += 1
                continue
            elif long_opt == 'archive':
                options['archive'] = True
                i += 1
                continue
            elif long_opt == 'recursive':
                options['recursive'] = True
                i += 1
                continue
            elif long_opt == 'links':
                options['links'] = True
                i += 1
                continue
            elif long_opt == 'no-links':
                options['links'] = False
                i += 1
                continue
            elif long_opt == 'copy-links':
                options['copy_links'] = True
                i += 1
                continue
            elif long_opt == 'hard-links':
                options['hard_links'] = True
                i += 1
                continue
            elif long_opt == 'perms':
                options['perms'] = True
                i += 1
                continue
            elif long_opt == 'no-perms':
                options['perms'] = False
                i += 1
                continue
            elif long_opt == 'times':
                options['times'] = True
                i += 1
                continue
            elif long_opt == 'no-times':
                options['times'] = False
                i += 1
                continue
            elif long_opt == 'atimes':
                options['atimes'] = True
                i += 1
                continue
            elif long_opt == 'crtimes':
                options['crtimes'] = True
                i += 1
                continue
            elif long_opt == 'group':
                options['group'] = True
                i += 1
                continue
            elif long_opt == 'no-group':
                options['group'] = False
                i += 1
                continue
            elif long_opt == 'owner':
                options['owner'] = True
                i += 1
                continue
            elif long_opt == 'no-owner':
                options['owner'] = False
                i += 1
                continue
            elif long_opt == 'devices':
                options['devices'] = True
                i += 1
                continue
            elif long_opt == 'specials':
                options['specials'] = True
                i += 1
                continue
            elif long_opt == 'verbose':
                options['verbose'] = True
                i += 1
                continue
            elif long_opt == 'quiet':
                options['quiet'] = True
                i += 1
                continue
            elif long_opt == 'dry-run':
                options['dry_run'] = True
                i += 1
                continue
            elif long_opt == 'delete':
                options['delete'] = True
                i += 1
                continue
            elif long_opt == 'delete-before':
                options['delete_before'] = True
                i += 1
                continue
            elif long_opt == 'delete-during':
                options['delete_during'] = True
                i += 1
                continue
            elif long_opt == 'delete-after':
                options['delete_after'] = True
                i += 1
                continue
            elif long_opt == 'delete-excluded':
                options['delete_excluded'] = True
                i += 1
                continue
            elif long_opt == 'compress':
                options['compress'] = True
                i += 1
                continue
            elif long_opt == 'no-compress':
                options['compress'] = False
                i += 1
                continue
            elif long_opt == 'update':
                options['update'] = True
                i += 1
                continue
            elif long_opt == 'existing':
                options['existing'] = True
                i += 1
                continue
            elif long_opt == 'whole-file':
                options['whole_file'] = True
                i += 1
                continue
            elif long_opt == 'backup':
                options['backup'] = True
                i += 1
                continue
            elif long_opt == 'stats':
                options['stats'] = True
                i += 1
                continue
            elif long_opt == 'itemize-changes':
                options['itemize'] = True
                i += 1
                continue
            elif long_opt == 'human-readable':
                options['human_readable'] = True
                i += 1
                continue
            elif long_opt == 'numeric-ids':
                options['numeric_ids'] = True
                i += 1
                continue
            elif long_opt == 'partial':
                options['partial'] = True
                i += 1
                continue
            elif long_opt == 'fake-super':
                options['fake_super'] = True
                i += 1
                continue
            elif long_opt == 'super':
                options['super'] = True
                i += 1
                continue
            elif long_opt == 'no-super':
                options['super'] = False
                i += 1
                continue
            elif long_opt == 'inplace':
                options['inplace'] = True
                i += 1
                continue
            elif long_opt == 'append':
                options['append'] = True
                i += 1
                continue
            elif long_opt == 'append-verify':
                options['append_verify'] = True
                i += 1
                continue
            elif long_opt == 'checksum':
                options['checksum'] = True
                i += 1
                continue
            elif long_opt == 'no-checksum':
                options['checksum'] = False
                i += 1
                continue
            elif long_opt == 'size-only':
                options['size_only'] = True
                i += 1
                continue
            elif long_opt == 'ignore-times':
                options['ignore_times'] = True
                i += 1
                continue
            elif long_opt == 'cvs-exclude':
                options['cvs_exclude'] = True
                i += 1
                continue
            elif long_opt == 'from0':
                options['from0'] = True
                i += 1
                continue
            elif long_opt == 'protect-args':
                options['protect_args'] = True
                i += 1
                continue
            elif long_opt == 'no-protect-args':
                options['protect_args'] = False
                i += 1
                continue
            elif long_opt == 'blocking-io':
                options['blocking_io'] = True
                i += 1
                continue
            elif long_opt == 'no-blocking-io':
                options['blocking_io'] = False
                i += 1
                continue
            elif long_opt == 'omit-dir-times':
                options['omit_dir_times'] = True
                i += 1
                continue
            elif long_opt == 'no-omit-dir-times':
                options['omit_dir_times'] = False
                i += 1
                continue
            elif long_opt == 'omit-link-times':
                options['omit_link_times'] = True
                i += 1
                continue
            elif long_opt == 'no-omit-link-times':
                options['omit_link_times'] = False
                i += 1
                continue
            elif long_opt == 'fuzzy':
                options['fuzzy'] = True
                i += 1
                continue
            elif long_opt == 'copy-dirlinks':
                options['copy_dirlinks'] = True
                i += 1
                continue
            elif long_opt == 'keep-dirlinks':
                options['keep_dirlinks'] = True
                i += 1
                continue
            elif long_opt == 'copy-unsafe-links':
                options['copy_unsafe_links'] = True
                i += 1
                continue
            elif long_opt == 'safe-links':
                options['safe_links'] = True
                i += 1
                continue
            elif long_opt == 'munge-links':
                options['munge_links'] = True
                i += 1
                continue
            elif long_opt == 'ignore-errors':
                options['ignore_errors'] = True
                i += 1
                continue
            elif long_opt == 'force':
                options['force'] = True
                i += 1
                continue
            elif long_opt == 'delay-updates':
                options['delay_updates'] = True
                i += 1
                continue
            elif long_opt == 'prune-empty-dirs':
                options['prune_empty_dirs'] = True
                i += 1
                continue
            elif long_opt == 'list-only':
                options['list_only'] = True
                i += 1
                continue
            elif long_opt == 'ignore-existing':
                options['ignore_existing'] = True
                i += 1
                continue
            elif long_opt == 'remove-source-files':
                options['remove_source_files'] = True
                i += 1
                continue
            elif long_opt == 'one-file-system':
                options['one_file_system'] = True
                i += 1
                continue
            elif long_opt == 'progress':
                options['progress'] = True
                i += 1
                continue
            elif long_opt == '8-bit-output':
                options['8_bit_output'] = True
                i += 1
                continue
            elif long_opt == 'relative':
                options['relative'] = True
                i += 1
                continue
            elif long_opt == 'no-relative':
                options['relative'] = False
                i += 1
                continue
            elif long_opt == 'dirs':
                options['dirs'] = True
                i += 1
                continue
            elif long_opt == 'no-dirs':
                options['dirs'] = False
                i += 1
                continue
            elif long_opt == 'inc-recursive':
                options['inc_recursive'] = True
                i += 1
                continue
            elif long_opt == 'no-inc-recursive':
                options['inc_recursive'] = False
                i += 1
                continue
            elif long_opt == 'no-implied-dirs':
                options['no_implied_dirs'] = True
                i += 1
                continue
            elif long_opt == 'trust-sender':
                options['trust_sender'] = True
                i += 1
                continue
            elif long_opt == 'acls':
                options['acls'] = True
                i += 1
                continue
            elif long_opt == 'no-acls':
                options['acls'] = False
                i += 1
                continue
            elif long_opt == 'xattrs':
                options['xattrs'] = True
                i += 1
                continue
            elif long_opt == 'no-xattrs':
                options['xattrs'] = False
                i += 1
                continue
            elif long_opt == 'delete-missing-args':
                options['delete_missing_args'] = True
                i += 1
                continue
            if long_opt == 'exclude':
                if i + 1 < len(parts):
                    i += 1
                    exclude_patterns.append(parts[i])
                i += 1
                continue
            elif long_opt == 'exclude-from':
                if i + 1 < len(parts):
                    i += 1
                    exclude_from_files.append(parts[i])
                i += 1
                continue
            elif long_opt == 'include':
                if i + 1 < len(parts):
                    i += 1
                    include_patterns.append(parts[i])
                i += 1
                continue
            elif long_opt == 'include-from':
                if i + 1 < len(parts):
                    i += 1
                    include_from_files.append(parts[i])
                i += 1
                continue
            elif long_opt == 'filter':
                if i + 1 < len(parts):
                    i += 1
                    filters.append(parts[i])
                i += 1
                continue
            elif long_opt == 'files-from':
                if i + 1 < len(parts):
                    i += 1
                    files_from = parts[i]
                i += 1
                continue
            elif long_opt == 'backup-dir':
                if i + 1 < len(parts):
                    i += 1
                    options['backup_dir'] = parts[i]
                i += 1
                continue
            elif long_opt == 'suffix':
                if i + 1 < len(parts):
                    i += 1
                    options['suffix'] = parts[i]
                i += 1
                continue
            elif long_opt == 'compare-dest':
                if i + 1 < len(parts):
                    i += 1
                    options['compare_dest'] = parts[i]
                i += 1
                continue
            elif long_opt == 'copy-dest':
                if i + 1 < len(parts):
                    i += 1
                    options['copy_dest'] = parts[i]
                i += 1
                continue
            elif long_opt == 'link-dest':
                if i + 1 < len(parts):
                    i += 1
                    options['link_dest'] = parts[i]
                i += 1
                continue
            elif long_opt == 'max-size':
                if i + 1 < len(parts):
                    i += 1
                    options['max_size'] = parts[i]
                i += 1
                continue
            elif long_opt == 'min-size':
                if i + 1 < len(parts):
                    i += 1
                    options['min_size'] = parts[i]
                i += 1
                continue
            elif long_opt == 'bwlimit':
                if i + 1 < len(parts):
                    i += 1
                    options['bwlimit'] = parts[i]
                i += 1
                continue
            elif long_opt == 'timeout':
                if i + 1 < len(parts):
                    i += 1
                    options['timeout'] = parts[i]
                i += 1
                continue
            elif long_opt == 'contimeout':
                if i + 1 < len(parts):
                    i += 1
                    options['contimeout'] = parts[i]
                i += 1
                continue
            elif long_opt == 'port':
                if i + 1 < len(parts):
                    i += 1
                    options['port'] = parts[i]
                i += 1
                continue
            elif long_opt == 'rsh':
                if i + 1 < len(parts):
                    i += 1
                    options['rsh'] = parts[i]
                i += 1
                continue
            elif long_opt == 'rsync-path':
                if i + 1 < len(parts):
                    i += 1
                    options['rsync_path'] = parts[i]
                i += 1
                continue
            elif long_opt == 'partial-dir':
                if i + 1 < len(parts):
                    i += 1
                    options['partial_dir'] = parts[i]
                i += 1
                continue
            elif long_opt == 'temp-dir':
                if i + 1 < len(parts):
                    i += 1
                    options['temp_dir'] = parts[i]
                i += 1
                continue
            elif long_opt == 'modify-window':
                if i + 1 < len(parts):
                    i += 1
                    options['modify_window'] = parts[i]
                i += 1
                continue
            elif long_opt == 'address':
                if i + 1 < len(parts):
                    i += 1
                    options['address'] = parts[i]
                i += 1
                continue
            elif long_opt == 'sockopts':
                if i + 1 < len(parts):
                    i += 1
                    options['sockopts'] = parts[i]
                i += 1
                continue
            elif long_opt == 'log-file':
                if i + 1 < len(parts):
                    i += 1
                    log_file = parts[i]
                i += 1
                continue
            elif long_opt == 'log-format':
                if i + 1 < len(parts):
                    i += 1
                    log_format = parts[i]
                i += 1
                continue
            elif long_opt == 'password-file':
                if i + 1 < len(parts):
                    i += 1
                    password_file = parts[i]
                i += 1
                continue
            i += 1
            continue
        if part.startswith('-') and len(part) > 1:
            opt_chars = part[1:]
            j = 0
            while j < len(opt_chars):
                char = opt_chars[j]
                if char == 'a':
                    options['archive'] = True
                    j += 1
                elif char == 'v':
                    options['verbose'] = True
                    j += 1
                elif char == 'z':
                    options['compress'] = True
                    j += 1
                elif char == 'q':
                    options['quiet'] = True
                    j += 1
                elif char == 'n':
                    options['dry_run'] = True
                    j += 1
                elif char == 'r':
                    options['recursive'] = True
                    j += 1
                elif char == 'R':
                    options['relative'] = True
                    j += 1
                elif char == 'l':
                    options['links'] = True
                    j += 1
                elif char == 'L':
                    options['copy_links'] = True
                    j += 1
                elif char == 'p':
                    options['perms'] = True
                    j += 1
                elif char == 't':
                    options['times'] = True
                    j += 1
                elif char == 'g':
                    options['group'] = True
                    j += 1
                elif char == 'o':
                    options['owner'] = True
                    j += 1
                elif char == 'D':
                    options['devices'] = True
                    options['specials'] = True
                    j += 1
                elif char == 'H':
                    options['hard_links'] = True
                    j += 1
                elif char == 'A':
                    options['acls'] = True
                    j += 1
                elif char == 'X':
                    options['xattrs'] = True
                    j += 1
                elif char == 'u':
                    options['update'] = True
                    j += 1
                elif char == 'c':
                    options['checksum'] = True
                    j += 1
                elif char == 'h':
                    options['human_readable'] = True
                    j += 1
                elif char == 'i':
                    options['itemize'] = True
                    j += 1
                elif char == 'I':
                    options['ignore_times'] = True
                    j += 1
                elif char == 'b':
                    options['backup'] = True
                    j += 1
                elif char == 's':
                    options['protect_args'] = True
                    j += 1
                elif char == 'O':
                    options['omit_dir_times'] = True
                    j += 1
                elif char == 'J':
                    options['omit_link_times'] = True
                    j += 1
                elif char == 'k':
                    options['copy_dirlinks'] = True
                    j += 1
                elif char == 'K':
                    options['keep_dirlinks'] = True
                    j += 1
                elif char == 'y':
                    options['fuzzy'] = True
                    j += 1
                elif char == 'm':
                    options['prune_empty_dirs'] = True
                    j += 1
                elif char == 'd':
                    options['dirs'] = True
                    j += 1
                elif char == 'W':
                    options['whole_file'] = True
                    j += 1
                elif char == 'x':
                    options['one_file_system'] = True
                    j += 1
                elif char == 'C':
                    options['cvs_exclude'] = True
                    j += 1
                elif char == '0':
                    options['from0'] = True
                    j += 1
                elif char == 'T':
                    if j + 1 < len(opt_chars):
                        options['temp_dir'] = opt_chars[j + 1:]
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                        options['temp_dir'] = parts[i]
                    j += 1
                elif char == 'e':
                    if j + 1 < len(opt_chars):
                        options['rsh'] = opt_chars[j + 1:]
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                        options['rsh'] = parts[i]
                    j += 1
                elif char == 'f':
                    if j + 1 < len(opt_chars):
                        filters.append(opt_chars[j + 1:])
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                        filters.append(parts[i])
                    j += 1
                elif char == 'P':
                    options['partial'] = True
                    options['progress'] = True
                    j += 1
                elif char == 'S':
                    options['sparse'] = True
                    j += 1
                elif char == 'E':
                    options['executability'] = True
                    j += 1
                elif char == 'X':
                    options['xattrs'] = True
                    j += 1
                elif char == '-':
                    j += 1
                    i += 1
                    paths.extend(parts[i:])
                    break
                else:
                    j += 1
            i += 1
            continue
        paths.append(part)
        i += 1
    if options['show_help']:
        return (
            'Write-Output "Usage: rsync [OPTION]... SRC [SRC]... DEST\n'
            '  or:  rsync [OPTION]... SRC [SRC]... [USER@]HOST:DEST\n'
            '  or:  rsync [OPTION]... SRC [SRC]... [USER@]HOST::DEST\n'
            '  or:  rsync [OPTION]... SRC [SRC]... rsync://[USER@]HOST[:PORT]/DEST\n'
            '  or:  rsync [OPTION]... [USER@]HOST:SRC [DEST]\n'
            '  or:  rsync [OPTION]... [USER@]HOST::SRC [DEST]\n'
            '  or:  rsync [OPTION]... rsync://[USER@]HOST[:PORT]/SRC [DEST]\n'
            '\n'
            'rsync is a file transfer program capable of efficient remote updates\n'
            'via a fast differencing algorithm.\n'
            '\n'
            'Options:\n'
            '  -v, --verbose               increase verbosity\n'
            '  -q, --quiet                 suppress non-error messages\n'
            '      --no-motd               suppress daemon-mode MOTD\n'
            '  -c, --checksum              skip based on checksum, not mod-time & size\n'
            '  -a, --archive               archive mode; equals -rlptgoD (no -H,-A,-X)\n'
            '      --no-OPTION             turn off an implied OPTION (e.g., --no-D)\n'
            '  -r, --recursive             recurse into directories\n'
            '  -R, --relative              use relative path names\n'
            '      --no-implied-dirs       don\'t send implied dirs with --relative\n'
            '  -b, --backup                make backups (see --suffix & --backup-dir)\n'
            '      --backup-dir=DIR        make backups into hierarchy based in DIR\n'
            '      --suffix=SUFFIX         backup suffix (default ~ w/o --backup-dir)\n'
            '  -u, --update                skip files that are newer on the receiver\n'
            '      --inplace               update destination files in-place\n'
            '      --append                append data onto shorter files\n'
            '      --append-verify         --append w/ old data in file checksum\n'
            '  -d, --dirs                  transfer directories without recursing\n'
            '  -l, --links                 copy symlinks as symlinks\n'
            '  -L, --copy-links            transform symlink into referent file/dir\n'
            '      --copy-unsafe-links     only "unsafe" symlinks are transformed\n'
            '      --safe-links            ignore symlinks that point outside the tree\n'
            '      --munge-links           munge symlinks to make them safe\n'
            '  -k, --copy-dirlinks         transform symlink to dir into referent dir\n'
            '  -K, --keep-dirlinks         treat symlinked dir on receiver as dir\n'
            '  -H, --hard-links            preserve hard links\n'
            '  -p, --perms                 preserve permissions\n'
            '      --executability         preserve executability\n'
            '      --chmod=CHMOD           affect file and/or directory permissions\n'
            '  -A, --acls                  preserve ACLs (implies -p)\n'
            '  -X, --xattrs                preserve extended attributes\n'
            '  -o, --owner                 preserve owner (super-user only)\n'
            '  -g, --group                 preserve group\n'
            '      --devices               preserve device files (super-user only)\n'
            '      --specials              preserve special files\n'
            '  -D                          same as --devices --specials\n'
            '  -t, --times                 preserve modification times\n'
            '  -O, --omit-dir-times        omit directories from --times\n'
            '  -J, --omit-link-times       omit symlinks from --times\n'
            '      --super                 receiver attempts super-user activities\n'
            '      --fake-super            store/recover privileged attrs using xattrs\n'
            '  -S, --sparse                handle sparse files efficiently\n'
            '      --preallocate           allocate dest files before writing\n'
            '  -n, --dry-run               perform a trial run with no changes made\n'
            '  -W, --whole-file            copy files whole (w/o delta-xfer algorithm)\n'
            '  -x, --one-file-system       don\'t cross filesystem boundaries\n'
            '  -B, --block-size=SIZE       force a fixed checksum block-size\n'
            '  -e, --rsh=COMMAND           specify the remote shell to use\n'
            '      --rsync-path=PROGRAM    specify the rsync to run on remote machine\n'
            '      --existing              skip creating new files on receiver\n'
            '      --ignore-existing       skip updating files that exist on receiver\n'
            '      --remove-source-files   sender removes synchronized files\n'
            '      --del                   an alias for --delete-during\n'
            '      --delete                delete extraneous files from dest dirs\n'
            '      --delete-before         receiver deletes before xfer, not during\n'
            '      --delete-during         receiver deletes during the transfer\n'
            '      --delete-after          receiver deletes after transfer, not during\n'
            '      --delete-excluded       also delete excluded files from dest dirs\n'
            '      --ignore-errors         delete even if there are I/O errors\n'
            '      --force                 force deletion of dirs even if not empty\n'
            '      --max-delete=NUM        don\'t delete more than NUM files\n'
            '      --max-size=SIZE         don\'t transfer any file larger than SIZE\n'
            '      --min-size=SIZE         don\'t transfer any file smaller than SIZE\n'
            '      --partial               keep partially transferred files\n'
            '      --partial-dir=DIR       put a partially transferred file into DIR\n'
            '      --delay-updates         put all updated files into place at end\n'
            '  -m, --prune-empty-dirs      prune empty directory chains from file-list\n'
            '      --numeric-ids           don\'t map uid/gid values by user/group name\n'
            '      --usermap=STRING        custom username mapping\n'
            '      --groupmap=STRING       custom groupname mapping\n'
            '      --chown=USER:GROUP      simple username/groupname mapping\n'
            '      --timeout=SECONDS       set I/O timeout in seconds\n'
            '      --contimeout=SECONDS    set daemon connection timeout in seconds\n'
            '  -I, --ignore-times          don\'t skip files that match size and time\n'
            '      --size-only             skip files that match in size\n'
            '      --modify-window=NUM     compare mod-times with reduced accuracy\n'
            '  -T, --temp-dir=DIR          create temporary files in directory DIR\n'
            '  -y, --fuzzy                 find similar file for basis if no dest file\n'
            '      --compare-dest=DIR      also compare received files relative to DIR\n'
            '      --copy-dest=DIR         ... and include copies of unchanged files\n'
            '      --link-dest=DIR         hardlink to files in DIR when unchanged\n'
            '  -z, --compress              compress file data during the transfer\n'
            '      --compress-level=NUM    explicitly set compression level\n'
            '      --skip-compress=LIST    skip compressing files with suffix in LIST\n'
            '  -C, --cvs-exclude           auto-ignore files in the same way CVS does\n'
            '  -f, --filter=RULE           add a file-filtering RULE\n'
            '  -F                          same as --filter=\'dir-merge /.rsync-filter\'\n'
            '                              repeated: --filter=\'- .rsync-filter\'\n'
            '      --exclude=PATTERN       exclude files matching PATTERN\n'
            '      --exclude-from=FILE     read exclude patterns from FILE\n'
            '      --include=PATTERN       don\'t exclude files matching PATTERN\n'
            '      --include-from=FILE     read include patterns from FILE\n'
            '      --files-from=FILE       read list of source-file names from FILE\n'
            '  -0, --from0                 all *from/filter files are delimited by 0s\n'
            '  -s, --protect-args          no space-splitting; wildcard chars only\n'
            '      --address=ADDRESS       bind address for outgoing socket to daemon\n'
            '      --port=PORT             specify double-colon alternate port number\n'
            '      --sockopts=OPTIONS      specify custom TCP options\n'
            '      --blocking-io           use blocking I/O for the remote shell\n'
            '      --stats                 give some file-transfer stats\n'
            '  -8, --8-bit-output          leave high-bit chars unescaped in output\n'
            '  -h, --human-readable        output numbers in a human-readable format\n'
            '      --progress              show progress during transfer\n'
            '  -P                          same as --partial --progress\n'
            '  -i, --itemize-changes       output a change-summary for all updates\n'
            '      --out-format=FORMAT     output updates using the specified FORMAT\n'
            '      --log-file=FILE         log what we\'re doing to the specified FILE\n'
            '      --log-file-format=FMT   log updates using the specified FMT\n'
            '      --password-file=FILE    read daemon-access password from FILE\n'
            '      --list-only             list the files instead of copying them\n'
            '      --bwlimit=RATE          limit socket I/O bandwidth\n'
            '      --outbuf=N|L|B          set out buffering to None, Line, or Block\n'
            '      --write-batch=FILE      write a batched update to FILE\n'
            '      --only-write-batch=FILE like --write-batch but w/o updating dest\n'
            '      --read-batch=FILE       read a batched update from FILE\n'
            '      --protocol=NUM          force an older protocol version to be used\n'
            '      --iconv=CONVERT_SPEC    request charset conversion of filenames\n'
            '      --checksum-seed=NUM     set block/file checksum seed (advanced)\n'
            '  -4, --ipv4                  prefer IPv4\n'
            '  -6, --ipv6                  prefer IPv6\n'
            '      --version               print version number\n'
            '(-h) --help                  show this help (-h is --help only if used alone)\n'
            '\n'
            'Use "rsync --daemon --help" to see the daemon-mode command-line options.\n'
            'See rsync(1) manpage for more details."'
        )
    if options['show_version']:
        return 'Write-Output "rsync  version 3.2.7  protocol version 31"'
    rsync_args = []
    if options['archive']:
        rsync_args.append('-a')
    else:
        if options['recursive']:
            rsync_args.append('-r')
        if options['links']:
            rsync_args.append('-l')
        if options['perms']:
            rsync_args.append('-p')
        if options['times']:
            rsync_args.append('-t')
        if options['group']:
            rsync_args.append('-g')
        if options['owner']:
            rsync_args.append('-o')
        if options['devices'] and options['specials']:
            rsync_args.append('-D')
    if options['verbose']:
        rsync_args.append('-v')
    if options['quiet']:
        rsync_args.append('-q')
    if options['dry_run']:
        rsync_args.append('-n')
    if options['compress']:
        rsync_args.append('-z')
    if options['checksum']:
        rsync_args.append('-c')
    if options['update']:
        rsync_args.append('-u')
    if options['human_readable']:
        rsync_args.append('-h')
    if options['itemize']:
        rsync_args.append('-i')
    if options['backup']:
        rsync_args.append('-b')
    if options['whole_file']:
        rsync_args.append('-W')
    if options['ignore_times']:
        rsync_args.append('-I')
    if options['cvs_exclude']:
        rsync_args.append('-C')
    if options['from0']:
        rsync_args.append('-0')
    if options['protect_args']:
        rsync_args.append('-s')
    if options['omit_dir_times']:
        rsync_args.append('-O')
    if options['omit_link_times']:
        rsync_args.append('-J')
    if options['copy_dirlinks']:
        rsync_args.append('-k')
    if options['keep_dirlinks']:
        rsync_args.append('-K')
    if options['fuzzy']:
        rsync_args.append('-y')
    if options['prune_empty_dirs']:
        rsync_args.append('-m')
    if options['one_file_system']:
        rsync_args.append('-x')
    if options['relative']:
        rsync_args.append('-R')
    if options['dirs']:
        rsync_args.append('-d')
    if options['hard_links']:
        rsync_args.append('-H')
    if options['acls']:
        rsync_args.append('-A')
    if options['xattrs']:
        rsync_args.append('-X')
    if options['copy_links']:
        rsync_args.append('-L')
    if options['existing']:
        rsync_args.append('--existing')
    if options['ignore_existing']:
        rsync_args.append('--ignore-existing')
    if options['remove_source_files']:
        rsync_args.append('--remove-source-files')
    if options['delete']:
        rsync_args.append('--delete')
    if options['delete_before']:
        rsync_args.append('--delete-before')
    if options['delete_during']:
        rsync_args.append('--delete-during')
    if options['delete_after']:
        rsync_args.append('--delete-after')
    if options['delete_excluded']:
        rsync_args.append('--delete-excluded')
    if options['stats']:
        rsync_args.append('--stats')
    if options['numeric_ids']:
        rsync_args.append('--numeric-ids')
    if options['partial']:
        rsync_args.append('--partial')
    if options['progress']:
        rsync_args.append('--progress')
    if options['inplace']:
        rsync_args.append('--inplace')
    if options['append']:
        rsync_args.append('--append')
    if options['append_verify']:
        rsync_args.append('--append-verify')
    if options['size_only']:
        rsync_args.append('--size-only')
    if options['fake_super']:
        rsync_args.append('--fake-super')
    if options['super']:
        rsync_args.append('--super')
    if options['copy_unsafe_links']:
        rsync_args.append('--copy-unsafe-links')
    if options['safe_links']:
        rsync_args.append('--safe-links')
    if options['munge_links']:
        rsync_args.append('--munge-links')
    if options['ignore_errors']:
        rsync_args.append('--ignore-errors')
    if options['force']:
        rsync_args.append('--force')
    if options['delay_updates']:
        rsync_args.append('--delay-updates')
    if options['list_only']:
        rsync_args.append('--list-only')
    if options.get('backup_dir'):
        rsync_args.append(f'--backup-dir={options["backup_dir"]}')
    if options.get('suffix'):
        rsync_args.append(f'--suffix={options["suffix"]}')
    if options.get('compare_dest'):
        rsync_args.append(f'--compare-dest={options["compare_dest"]}')
    if options.get('copy_dest'):
        rsync_args.append(f'--copy-dest={options["copy_dest"]}')
    if options.get('link_dest'):
        rsync_args.append(f'--link-dest={options["link_dest"]}')
    if options.get('max_size'):
        rsync_args.append(f'--max-size={options["max_size"]}')
    if options.get('min_size'):
        rsync_args.append(f'--min-size={options["min_size"]}')
    if options.get('bwlimit'):
        rsync_args.append(f'--bwlimit={options["bwlimit"]}')
    if options.get('timeout'):
        rsync_args.append(f'--timeout={options["timeout"]}')
    if options.get('contimeout'):
        rsync_args.append(f'--contimeout={options["contimeout"]}')
    if options.get('port'):
        rsync_args.append(f'--port={options["port"]}')
    if options.get('rsh'):
        rsh = options['rsh']
        if ' ' in rsh and not (rsh.startswith('"') or rsh.startswith("'")):
            rsh = f'"{rsh}"'
        rsync_args.append(f'--rsh={rsh}')
    if options.get('rsync_path'):
        rsync_args.append(f'--rsync-path={options["rsync_path"]}')
    if options.get('partial_dir'):
        rsync_args.append(f'--partial-dir={options["partial_dir"]}')
    if options.get('temp_dir'):
        rsync_args.append(f'--temp-dir={options["temp_dir"]}')
    if options.get('modify_window'):
        rsync_args.append(f'--modify-window={options["modify_window"]}')
    if options.get('address'):
        rsync_args.append(f'--address={options["address"]}')
    if options.get('sockopts'):
        rsync_args.append(f'--sockopts={options["sockopts"]}')
    if options.get('outbuf'):
        rsync_args.append(f'--outbuf={options["outbuf"]}')
    if options.get('usermap'):
        rsync_args.append(f'--usermap={options["usermap"]}')
    if options.get('groupmap'):
        rsync_args.append(f'--groupmap={options["groupmap"]}')
    if options.get('chown'):
        rsync_args.append(f'--chown={options["chown"]}')
    if options.get('stop_at'):
        rsync_args.append(f'--stop-at={options["stop_at"]}')
    if options.get('time_limit'):
        rsync_args.append(f'--time-limit={options["time_limit"]}')
    if options.get('block_size'):
        rsync_args.append(f'--block-size={options["block_size"]}')
    if options.get('out_format'):
        rsync_args.append(f'--out-format={options["out_format"]}')
    if options.get('remote_option'):
        rsync_args.append(f'--remote-option={options["remote_option"]}')
    if options.get('iconv'):
        rsync_args.append(f'--iconv={options["iconv"]}')
    if options.get('checksum_seed'):
        rsync_args.append(f'--checksum-seed={options["checksum_seed"]}')
    if options.get('write_batch'):
        rsync_args.append(f'--write-batch={options["write_batch"]}')
    if options.get('only_write_batch'):
        rsync_args.append(f'--only-write-batch={options["only_write_batch"]}')
    if options.get('read_batch'):
        rsync_args.append(f'--read-batch={options["read_batch"]}')
    if options.get('protocol'):
        rsync_args.append(f'--protocol={options["protocol"]}')
    if options.get('copy_as'):
        rsync_args.append(f'--copy-as={options["copy_as"]}')
    if options.get('compress_level'):
        rsync_args.append(f'--compress-level={options["compress_level"]}')
    if options.get('skip_compress'):
        rsync_args.append(f'--skip-compress={options["skip_compress"]}')
    for f in filters:
        rsync_args.append(f'--filter={f}')
    for pattern in exclude_patterns:
        rsync_args.append(f'--exclude={pattern}')
    for f in exclude_from_files:
        rsync_args.append(f'--exclude-from={f}')
    for pattern in include_patterns:
        rsync_args.append(f'--include={pattern}')
    for f in include_from_files:
        rsync_args.append(f'--include-from={f}')
    if files_from:
        rsync_args.append(f'--files-from={files_from}')
    if log_file:
        rsync_args.append(f'--log-file={log_file}')
    if log_format:
        rsync_args.append(f'--log-format={log_format}')
    if password_file:
        rsync_args.append(f'--password-file={password_file}')
    for path in paths:
        rsync_args.append(path)
    cmd_str = 'rsync ' + ' '.join(rsync_args)
    return cmd_str
if __name__ == "__main__":
    test_cases = [
        "rsync -av source/ dest/",
        "rsync -avz --delete source/ dest/",
        "rsync -av --exclude='*.tmp' source/ dest/",
        "rsync -av --exclude-from=exclude.txt source/ dest/",
        "rsync -av -e 'ssh -p 2222' source/ dest/",
        "rsync -av /e ssh -p 2222 source/ dest/",
        "rsync /av source/ dest/",
        "rsync -av --progress source/ user@host:/path/",
        "rsync -avz --backup --backup-dir=backups source/ dest/",
        "rsync -av --dry-run source/ dest/",
        "rsync -av --include='*.txt' --exclude='*' source/ dest/",
        "rsync -av --filter='- *.log' source/ dest/",
        "rsync -av --bwlimit=1000 source/ dest/",
        "rsync -av --max-size=100M source/ dest/",
        "rsync -av --min-size=1K source/ dest/",
        "rsync -av --partial --progress source/ dest/",
        "rsync -avP source/ dest/",
        "rsync -av --link-dest=../prev dest/",
        "rsync -av --files-from=list.txt source/ dest/",
        "rsync --help",
        "rsync --version",
        "rsync -av --stats source/ dest/",
        "rsync -av --numeric-ids source/ dest/",
        "rsync -av --inplace source/ dest/",
        "rsync -av --append source/ dest/",
        "rsync -av --size-only source/ dest/",
        "rsync -av --ignore-existing source/ dest/",
        "rsync -av --remove-source-files source/ dest/",
        "rsync -av --prune-empty-dirs source/ dest/",
        "rsync -av --delay-updates source/ dest/",
        "rsync -av --temp-dir=/tmp source/ dest/",
        "rsync -av --timeout=300 source/ dest/",
        "rsync -av --port=873 source/ dest/",
        "rsync -av --log-file=rsync.log source/ dest/",
        "rsync -av --password-file=pass.txt source/ dest/",
        "rsync -av --list-only source/",
        "rsync -av --delete --delete-excluded source/ dest/",
        "rsync -av --cvs-exclude source/ dest/",
        "rsync -av --fuzzy source/ dest/",
        "rsync -av --copy-dirlinks source/ dest/",
        "rsync -av --keep-dirlinks source/ dest/",
        "rsync -av --safe-links source/ dest/",
        "rsync -av --ignore-errors source/ dest/",
        "rsync -av --force source/ dest/",
        "rsync -av --one-file-system source/ dest/",
        "rsync -av --existing source/ dest/",
        "rsync -av --update source/ dest/",
        "rsync -av --whole-file source/ dest/",
        "rsync -av --checksum source/ dest/",
        "rsync -av --hard-links source/ dest/",
        "rsync -av --acls --xattrs source/ dest/",
        "rsync -av --fake-super source/ dest/",
        "rsync -av --super source/ dest/",
        "rsync -av --copy-links source/ dest/",
        "rsync -av --copy-unsafe-links source/ dest/",
        "rsync -av --munge-links source/ dest/",
        "rsync -av --append-verify source/ dest/",
        "rsync -av --omit-dir-times source/ dest/",
        "rsync -av --omit-link-times source/ dest/",
        "rsync -av --protect-args source/ dest/",
        "rsync -av --from0 --files-from=list0.txt source/ dest/",
        "rsync -av --relative source/ dest/",
        "rsync -av --no-inc-recursive source/ dest/",
        "rsync -av --dirs source/ dest/",
        "rsync -av --sparse source/ dest/",
        "rsync -av --executability source/ dest/",
        "rsync -av --chmod=Du+rwx source/ dest/",
        "rsync -av --usermap=user1:user2 source/ dest/",
        "rsync -av --groupmap=group1:group2 source/ dest/",
        "rsync -av --chown=user:group source/ dest/",
        "rsync -av --block-size=1024 source/ dest/",
        "rsync -av --compress-level=6 source/ dest/",
        "rsync -av --skip-compress=gz/jpg/mp3 source/ dest/",
        "rsync -av --out-format='%n%L' source/ dest/",
        "rsync -av --log-format='%i %n%L' source/ dest/",
        "rsync -av --iconv=UTF-8 source/ dest/",
        "rsync -av --checksum-seed=1 source/ dest/",
        "rsync -av --write-batch=batch.dat source/ dest/",
        "rsync -av --read-batch=batch.dat dest/",
        "rsync -av --protocol=30 source/ dest/",
        "rsync -av --contimeout=30 source/ dest/",
        "rsync -av --stop-at=yesterday source/ dest/",
        "rsync -av --time-limit=3600 source/ dest/",
        "rsync -av --outbuf=L source/ dest/",
        "rsync -av --sockopts=SO_KEEPALIVE source/ dest/",
        "rsync -av --address=192.168.1.1 source/ dest/",
        "rsync -av --delete-missing-args source/ dest/",
        "rsync -av --no-implied-dirs source/ dest/",
        "rsync -av --trust-sender source/ dest/",
        "rsync -av --copy-as=user source/ dest/",
        "rsync -av --8-bit-output source/ dest/",
    ]
    for test in test_cases:
        result = _convert_rsync(test)
        print(f"Input:  {test}")
        print(f"Output: {result}")
        print()
def _parse_scp_uri(uri: str) -> Tuple[Optional[str], Optional[str], str]:
    if ':' not in uri:
        return (None, None, uri)
    if len(uri) >= 2 and uri[1] == ':' and uri[0].isalpha():
        return (None, None, uri)
    if uri.startswith('['):
        match = re.match(r'^\[([^\]]+)\]:(.*)$', uri)
        if match:
            host, path = match.groups()
            return (None, host, path)
    colon_idx = uri.rfind(':')
    if colon_idx == -1:
        return (None, None, uri)
    before_colon = uri[:colon_idx]
    path = uri[colon_idx + 1:]
    if '@' in before_colon:
        user, host = before_colon.rsplit('@', 1)
        return (user, host, path)
    else:
        return (None, before_colon, path)
def _is_remote_path(uri: str) -> bool:
    if ':' not in uri:
        return False
    if len(uri) >= 2 and uri[1] == ':' and uri[0].isalpha():
        return False
    if uri.startswith('['):
        return True
    before_colon = uri.split(':')[0]
    if '/' in before_colon or '\\' in before_colon:
        return False
    return True
def _convert_scp(cmd: str) -> str:
    if not cmd or not cmd.strip():
        return 'Write-Output "usage: scp [-346BCpqrTv] [-c cipher] [-F ssh_config] [-i identity_file] [-l limit] [-o ssh_option] [-P port] [-S program] source ... target"'
    parts = _parse_command_line(cmd)
    if not parts:
        return 'Write-Output "usage: scp [-346BCpqrTv] [-c cipher] [-F ssh_config] [-i identity_file] [-l limit] [-o ssh_option] [-P port] [-S program] source ... target"'
    if parts[0] in ('scp', '/bin/scp', '/usr/bin/scp'):
        parts = parts[1:]
    if not parts:
        return 'Write-Output "usage: scp [-346BCpqrTv] [-c cipher] [-F ssh_config] [-i identity_file] [-l limit] [-o ssh_option] [-P port] [-S program] source ... target"'
    options: Dict[str, Any] = {
        'ipv4': False,
        'ipv6': False,
        'batch_mode': False,
        'compression': False,
        'preserve': False,
        'quiet': False,
        'recursive': False,
        'verbose': False,
        'archive': False,
        'no_strict_filename': False,
        'cipher': None,
        'ssh_config': None,
        'identity_file': None,
        'bandwidth_limit': None,
        'ssh_options': [],
        'port': None,
        'program': None,
    }
    sources: List[str] = []
    target: Optional[str] = None
    i = 0
    while i < len(parts):
        part = parts[i]
        if part == '--':
            remaining = parts[i + 1:]
            if remaining:
                sources.extend(remaining[:-1])
                if remaining:
                    target = remaining[-1]
            break
        is_path = False
        if part.startswith('/') and len(part) >= 2:
            if len(part) == 2:
                if part[1] not in '346BCpqrTvaFiloPSc':
                    is_path = True
            elif len(part) > 2:
                if '/' in part[1:]:
                    is_path = True
                known_long_opts = ('recurs', 'verbos', 'quiet', 'archiv', 'preserv',
                                   'compress', 'batch', 'ipv', 'ciph', 'ssh', 'ident',
                                   'limit', 'progr', 'port', 'help', 'vers')
                if not any(part[1:].startswith(prefix) for prefix in known_long_opts):
                    is_path = True
            if not is_path:
                if len(part) == 2:
                    part = '-' + part[1:]
                elif len(part) > 2 and part[1].isalpha():
                    part = '--' + part[1:]
        if part.startswith('--'):
            long_opt = part[2:]
            if '=' in long_opt:
                opt_name, opt_value = long_opt.split('=', 1)
                if opt_name == 'cipher':
                    options['cipher'] = opt_value
                elif opt_name == 'ssh-config':
                    options['ssh_config'] = opt_value
                elif opt_name == 'identity-file':
                    options['identity_file'] = opt_value
                elif opt_name == 'port':
                    options['port'] = opt_value
                elif opt_name == 'program':
                    options['program'] = opt_value
                elif opt_name == 'limit':
                    options['bandwidth_limit'] = opt_value
                elif opt_name == 'ssh-option':
                    options['ssh_options'].append(opt_value)
                i += 1
                continue
            if long_opt == 'recursive':
                options['recursive'] = True
                i += 1
                continue
            elif long_opt == 'verbose':
                options['verbose'] = True
                i += 1
                continue
            elif long_opt == 'quiet':
                options['quiet'] = True
                i += 1
                continue
            elif long_opt == 'archive':
                options['archive'] = True
                i += 1
                continue
            elif long_opt == 'preserve':
                options['preserve'] = True
                i += 1
                continue
            elif long_opt == 'compression':
                options['compression'] = True
                i += 1
                continue
            elif long_opt == 'batch-mode':
                options['batch_mode'] = True
                i += 1
                continue
            elif long_opt == 'ipv4':
                options['ipv4'] = True
                i += 1
                continue
            elif long_opt == 'ipv6':
                options['ipv6'] = True
                i += 1
                continue
            elif long_opt == 'cipher':
                if i + 1 < len(parts):
                    i += 1
                    options['cipher'] = parts[i]
                i += 1
                continue
            elif long_opt == 'ssh-config':
                if i + 1 < len(parts):
                    i += 1
                    options['ssh_config'] = parts[i]
                i += 1
                continue
            elif long_opt == 'identity-file':
                if i + 1 < len(parts):
                    i += 1
                    options['identity_file'] = parts[i]
                i += 1
                continue
            elif long_opt == 'port':
                if i + 1 < len(parts):
                    i += 1
                    options['port'] = parts[i]
                i += 1
                continue
            elif long_opt == 'program':
                if i + 1 < len(parts):
                    i += 1
                    options['program'] = parts[i]
                i += 1
                continue
            elif long_opt == 'limit':
                if i + 1 < len(parts):
                    i += 1
                    options['bandwidth_limit'] = parts[i]
                i += 1
                continue
            elif long_opt == 'ssh-option':
                if i + 1 < len(parts):
                    i += 1
                    options['ssh_options'].append(parts[i])
                i += 1
                continue
            elif long_opt == 'help':
                return (
                    'Write-Output "usage: scp [-346BCpqrTv] [-c cipher] [-F ssh_config] [-i identity_file] [-l limit] [-o ssh_option] [-P port] [-S program] source ... target\n'
                    'Options:\n'
                    '  -3            Copies between two remote hosts are transferred through the local host\n'
                    '  -4            Forces scp to use IPv4 addresses only\n'
                    '  -6            Forces scp to use IPv6 addresses only\n'
                    '  -B            Selects batch mode (prevents asking for passwords)\n'
                    '  -C            Compression enable\n'
                    '  -c cipher     Selects the cipher to use\n'
                    '  -F ssh_config Specifies an alternative per-user configuration file\n'
                    '  -i identity   Selects the file from which the identity is read\n'
                    '  -l limit      Limits the used bandwidth\n'
                    '  -o option     Specify options (e.g., StrictHostKeyChecking)\n'
                    '  -P port       Specify port to connect to\n'
                    '  -p            Preserves modification times, access times, and modes\n'
                    '  -q            Quiet mode\n'
                    '  -r            Recursively copy entire directories\n'
                    '  -S program    Name of program to use for the encrypted connection\n'
                    '  -T            Disable strict filename checking\n'
                    '  -v            Verbose mode"'
                )
            elif long_opt == 'version':
                return 'Write-Output "scp: OpenSSH"'
            i += 1
            continue
        if part.startswith('-') and len(part) > 1:
            opt_chars = part[1:]
            j = 0
            while j < len(opt_chars):
                char = opt_chars[j]
                if char == '4':
                    options['ipv4'] = True
                    j += 1
                elif char == '6':
                    options['ipv6'] = True
                    j += 1
                elif char == '3':
                    j += 1
                elif char == 'B':
                    options['batch_mode'] = True
                    j += 1
                elif char == 'C':
                    options['compression'] = True
                    j += 1
                elif char == 'c':
                    if j + 1 < len(opt_chars):
                        options['cipher'] = opt_chars[j + 1:]
                        break
                    elif i + 1 < len(parts):
                        i += 1
                        options['cipher'] = parts[i]
                    j += 1
                elif char == 'F':
                    if j + 1 < len(opt_chars):
                        options['ssh_config'] = opt_chars[j + 1:]
                        break
                    elif i + 1 < len(parts):
                        i += 1
                        options['ssh_config'] = parts[i]
                    j += 1
                elif char == 'i':
                    if j + 1 < len(opt_chars):
                        options['identity_file'] = opt_chars[j + 1:]
                        break
                    elif i + 1 < len(parts):
                        i += 1
                        options['identity_file'] = parts[i]
                    j += 1
                elif char == 'l':
                    if j + 1 < len(opt_chars):
                        options['bandwidth_limit'] = opt_chars[j + 1:]
                        break
                    elif i + 1 < len(parts):
                        i += 1
                        options['bandwidth_limit'] = parts[i]
                    j += 1
                elif char == 'o':
                    if j + 1 < len(opt_chars):
                        options['ssh_options'].append(opt_chars[j + 1:])
                        break
                    elif i + 1 < len(parts):
                        i += 1
                        options['ssh_options'].append(parts[i])
                    j += 1
                elif char == 'P':
                    if j + 1 < len(opt_chars):
                        options['port'] = opt_chars[j + 1:]
                        break
                    elif i + 1 < len(parts):
                        i += 1
                        options['port'] = parts[i]
                    j += 1
                elif char == 'p':
                    options['preserve'] = True
                    j += 1
                elif char == 'q':
                    options['quiet'] = True
                    j += 1
                elif char == 'r':
                    options['recursive'] = True
                    j += 1
                elif char == 'S':
                    if j + 1 < len(opt_chars):
                        options['program'] = opt_chars[j + 1:]
                        break
                    elif i + 1 < len(parts):
                        i += 1
                        options['program'] = parts[i]
                    j += 1
                elif char == 'T':
                    options['no_strict_filename'] = True
                    j += 1
                elif char == 'v':
                    options['verbose'] = True
                    j += 1
                elif char == 'a':
                    options['archive'] = True
                    j += 1
                elif char == '-':
                    j += 1
                    i += 1
                    remaining = parts[i:]
                    if remaining:
                        sources.extend(remaining[:-1])
                        if remaining:
                            target = remaining[-1]
                    break
                else:
                    j += 1
            i += 1
            continue
        if i == len(parts) - 1:
            target = part
        else:
            sources.append(part)
        i += 1
    if target is None and sources:
        target = sources[-1]
        sources = sources[:-1]
    return _build_scp_powershell_command(options, sources, target)
def _build_scp_powershell_command(
    options: Dict[str, Any],
    sources: List[str],
    target: Optional[str]
) -> str:
    if not sources:
        return 'Write-Output "scp: missing file operand"'
    if target is None:
        return 'Write-Output "scp: missing destination file operand"'
    has_remote = False
    for src in sources:
        if _is_remote_path(src):
            has_remote = True
            break
    if _is_remote_path(target):
        has_remote = True
    if has_remote:
        return _build_remote_scp_command(options, sources, target)
    return _build_local_copy_command(options, sources, target)
def _build_remote_scp_command(
    options: Dict[str, Any],
    sources: List[str],
    target: str
) -> str:
    cmd_parts = ['scp']
    if options.get('ipv4'):
        cmd_parts.append('-4')
    if options.get('ipv6'):
        cmd_parts.append('-6')
    if options.get('batch_mode'):
        cmd_parts.append('-B')
    if options.get('compression'):
        cmd_parts.append('-C')
    if options.get('preserve'):
        cmd_parts.append('-p')
    if options.get('quiet'):
        cmd_parts.append('-q')
    if options.get('recursive'):
        cmd_parts.append('-r')
    if options.get('verbose'):
        cmd_parts.append('-v')
    if options.get('archive'):
        cmd_parts.append('-a')
    if options.get('no_strict_filename'):
        cmd_parts.append('-T')
    if options.get('cipher'):
        cmd_parts.extend(['-c', options['cipher']])
    if options.get('ssh_config'):
        cmd_parts.extend(['-F', options['ssh_config']])
    if options.get('identity_file'):
        cmd_parts.extend(['-i', options['identity_file']])
    if options.get('bandwidth_limit'):
        cmd_parts.extend(['-l', options['bandwidth_limit']])
    if options.get('port'):
        cmd_parts.extend(['-P', str(options['port'])])
    if options.get('program'):
        cmd_parts.extend(['-S', options['program']])
    for opt in options.get('ssh_options', []):
        cmd_parts.extend(['-o', opt])
    cmd_parts.extend(sources)
    cmd_parts.append(target)
    return ' '.join(cmd_parts)
def _build_local_copy_command(
    options: Dict[str, Any],
    sources: List[str],
    target: str
) -> str:
    quoted_sources = []
    for src in sources:
        if ' ' in src and not (src.startswith('"') or src.startswith("'")):
            quoted_sources.append(f'"{src}"')
        else:
            quoted_sources.append(src)
    quoted_target = target
    if ' ' in target and not (target.startswith('"') or target.startswith("'")):
        quoted_target = f'"{target}"'
    if len(quoted_sources) == 1:
        source_str = quoted_sources[0]
    else:
        source_str = ', '.join(quoted_sources)
    cmd_parts = [f'Copy-Item -Path {source_str} -Destination {quoted_target}']
    if options.get('recursive'):
        cmd_parts.append('-Recurse')
    if options.get('preserve'):
        pass
    return ' '.join(cmd_parts)
if __name__ == "__main__":
    test_cases = [
        "scp file.txt user@host:/path/",
        "scp -r dir/ user@host:/path/",
        "scp -P 2222 file.txt user@host:/path/",
        "scp -i ~/.ssh/id_rsa file.txt user@host:/path/",
        "scp -p file.txt user@host:/path/",
        "scp -q file.txt user@host:/path/",
        "scp -v file.txt user@host:/path/",
        "scp -C file.txt user@host:/path/",
        "scp -B file.txt user@host:/path/",
        "scp -4 file.txt user@host:/path/",
        "scp -6 file.txt user@host:/path/",
        "scp -a dir/ user@host:/path/",
        "scp -T file.txt user@host:/path/",
        "scp -c aes256 file.txt user@host:/path/",
        "scp -l 1000 file.txt user@host:/path/",
        "scp -o StrictHostKeyChecking=no file.txt user@host:/path/",
        "scp user@host:/path/file.txt ./local/",
        "scp user1@host1:/path/file.txt user2@host2:/path/",
        "scp /r file.txt user@host:/path/",
        "scp /P 2222 file.txt user@host:/path/",
        "scp /i ~/.ssh/id_rsa file.txt user@host:/path/",
        "scp file1.txt file2.txt /dest/",
        "scp -r dir/ /dest/",
        "scp file.txt /dest/",
        "scp",
        "scp file.txt",
        "scp --help",
        "scp --version",
        "scp -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no file.txt user@host:/path/",
    ]
    for test in test_cases:
        result = _convert_scp(test)
        print(f"Input:  {test}")
        print(f"Output: {result}")
        print()
def _convert_slash_to_dash(arg: str) -> str:
    if not arg.startswith('/') or len(arg) < 2:
        return arg
    if arg[1].isalpha():
        if len(arg) == 2:
            return '-' + arg[1:]
        else:
            return '--' + arg[1:]
    return arg
def _parse_numbers(parts: List[str]) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    if not parts:
        return (None, None, None)
    numbers = []
    for part in parts:
        try:
            num = float(part)
            numbers.append(num)
        except ValueError:
            pass
    if len(numbers) == 0:
        return (None, None, None)
    elif len(numbers) == 1:
        return (1.0, 1.0, numbers[0])
    elif len(numbers) == 2:
        return (numbers[0], 1.0, numbers[1])
    else:
        return (numbers[0], numbers[1], numbers[2])
def _convert_seq(cmd: str) -> str:
    if not cmd or not cmd.strip():
        return 'Write-Output "Usage: seq [OPTION]... LAST\n       seq [OPTION]... FIRST LAST\n       seq [OPTION]... FIRST INCREMENT LAST"'
    parts = _parse_command_line(cmd)
    if not parts:
        return 'Write-Output "Usage: seq [OPTION]... LAST\n       seq [OPTION]... FIRST LAST\n       seq [OPTION]... FIRST INCREMENT LAST"'
    if parts[0] in ('seq', '/bin/seq', '/usr/bin/seq'):
        parts = parts[1:]
    if not parts:
        return 'Write-Output "Usage: seq [OPTION]... LAST\n       seq [OPTION]... FIRST LAST\n       seq [OPTION]... FIRST INCREMENT LAST"'
    format_str: Optional[str] = None
    separator: Optional[str] = None
    equal_width = False
    show_help = False
    show_version = False
    number_parts: List[str] = []
    i = 0
    while i < len(parts):
        part = parts[i]
        part = _convert_slash_to_dash(part)
        if part == '--':
            number_parts.extend(parts[i + 1:])
            break
        if part.startswith('--'):
            long_opt = part[2:]
            if long_opt == 'help':
                show_help = True
                i += 1
                continue
            if long_opt == 'version':
                show_version = True
                i += 1
                continue
            if long_opt == 'equal-width':
                equal_width = True
                i += 1
                continue
            if long_opt.startswith('format='):
                format_str = long_opt[7:]
                i += 1
                continue
            if long_opt.startswith('separator='):
                separator = long_opt[10:]
                if (separator.startswith('"') and separator.endswith('"')) or \
                   (separator.startswith("'") and separator.endswith("'")):
                    separator = separator[1:-1]
                i += 1
                continue
            i += 1
            continue
        if part.startswith('-') and len(part) > 1 and not (part[1].isdigit() or part[1] == '.'):
            opt_chars = part[1:]
            j = 0
            while j < len(opt_chars):
                char = opt_chars[j]
                if char == 'f':
                    if j + 1 < len(opt_chars):
                        format_str = opt_chars[j + 1:]
                        break
                    elif i + 1 < len(parts):
                        i += 1
                        format_str = parts[i]
                        if (format_str.startswith('"') and format_str.endswith('"')) or \
                           (format_str.startswith("'") and format_str.endswith("'")):
                            format_str = format_str[1:-1]
                    j += 1
                elif char == 's':
                    if j + 1 < len(opt_chars):
                        separator = opt_chars[j + 1:]
                        if (separator.startswith('"') and separator.endswith('"')) or \
                           (separator.startswith("'") and separator.endswith("'")):
                            separator = separator[1:-1]
                        break
                    elif i + 1 < len(parts):
                        i += 1
                        separator = parts[i]
                        if (separator.startswith('"') and separator.endswith('"')) or \
                           (separator.startswith("'") and separator.endswith("'")):
                            separator = separator[1:-1]
                    j += 1
                elif char == 'w':
                    equal_width = True
                    j += 1
                else:
                    j += 1
            i += 1
            continue
        number_parts.append(part)
        i += 1
    if show_help:
        return (
            'Write-Output "seq - print a sequence of numbers\n'
            'Usage: seq [OPTION]... LAST\n'
            '       seq [OPTION]... FIRST LAST\n'
            '       seq [OPTION]... FIRST INCREMENT LAST\n'
            'Print numbers from FIRST to LAST, in steps of INCREMENT.\n\n'
            'Mandatory arguments to long options are mandatory for short options too.\n'
            '  -f, --format=FORMAT    use printf style floating-point FORMAT\n'
            '  -s, --separator=STRING use STRING to separate numbers (default: \\\\n)\n'
            '  -w, --equal-width      equalize width by padding with leading zeroes\n'
            '      --help             display this help and exit\n'
            '      --version          output version information and exit\n\n'
            'If FIRST or INCREMENT is omitted, it defaults to 1.\n'
            'FIRST, INCREMENT, and LAST are interpreted as floating point values."'
        )
    if show_version:
        return 'Write-Output "seq (GNU coreutils) 8.32"'
    first, increment, last = _parse_numbers(number_parts)
    if last is None:
        return 'Write-Output "seq: missing operand\nTry `seq --help` for more information."'
    reverse = False
    if first > last:
        if increment > 0:
            return 'Write-Output ""'
        reverse = True
    elif first < last and increment < 0:
        return 'Write-Output ""'
    if reverse:
        use_for_loop = increment != -1.0
    else:
        use_for_loop = increment != 1.0
    return _build_seq_powershell_command(
        first, last, increment, format_str, separator,
        equal_width, use_for_loop, reverse
    )
def _build_seq_powershell_command(
    first: float,
    last: float,
    increment: float,
    format_str: Optional[str],
    separator: Optional[str],
    equal_width: bool,
    use_for_loop: bool,
    reverse: bool
) -> str:
    is_integer = all(x == int(x) for x in [first, last, increment])
    ps_format = None
    if format_str:
        ps_format = _convert_printf_format(format_str)
    if use_for_loop:
        if reverse:
            condition = f'$i -ge {last}'
            step = f'$i += {increment}'
        else:
            condition = f'$i -le {last}'
            step = f'$i += {increment}'
        if ps_format:
            body = f'"{ps_format}" -f $i'
        elif equal_width and is_integer:
            max_val = max(abs(int(first)), abs(int(last)))
            width = len(str(max_val))
            body = f'"{{0:D{width}}}" -f [int]$i'
        else:
            body = '$i'
        if separator:
            return f'$(for ($i = {first}; {condition}; {step}) {{ {body} }}) -join "{separator}" | Write-Output'
        else:
            return f'for ($i = {first}; {condition}; {step}) {{ {body} }}'
    else:
        first_int = int(first)
        last_int = int(last)
        if reverse:
            if ps_format:
                body = f'"{ps_format}" -f $_'
            elif equal_width:
                max_val = max(abs(first_int), abs(last_int))
                width = len(str(max_val))
                body = f'"{{0:D{width}}}" -f $_'
            else:
                body = '$_'
            if separator:
                return f'Write-Output ({first_int}..{last_int} | ForEach-Object {{ {body} }}) -join "{separator}"'
            else:
                return f'{first_int}..{last_int} | ForEach-Object {{ {body} }}'
        else:
            if ps_format:
                body = f'"{ps_format}" -f $_'
            elif equal_width:
                max_val = max(abs(first_int), abs(last_int))
                width = len(str(max_val))
                body = f'"{{0:D{width}}}" -f $_'
            else:
                body = '$_'
            if separator:
                return f'Write-Output ({first_int}..{last_int} | ForEach-Object {{ {body} }}) -join "{separator}"'
            else:
                return f'{first_int}..{last_int} | ForEach-Object {{ {body} }}'
def _convert_printf_format(fmt: str) -> str:
    if (fmt.startswith('"') and fmt.endswith('"')) or \
       (fmt.startswith("'") and fmt.endswith("'")):
        fmt = fmt[1:-1]
    match = re.match(r'^%([0-9#+\- ]*)?(\d+)?(?:\.(\d+))?([dfeEgGisoxX])$', fmt)
    if not match:
        return '{0}'
    flags, width, precision, specifier = match.groups()
    flags = flags or ''
    ps_fmt = '{0:'
    if specifier in ('d', 'i', 'o', 'x', 'X'):
        if '0' in flags and width:
            ps_fmt += f'D{width}'
        elif width:
            ps_fmt += f'D{width}'
        else:
            ps_fmt += 'D'
    elif specifier == 'f':
        if precision:
            ps_fmt += f'F{precision}'
        else:
            ps_fmt += 'F'
    elif specifier in ('e', 'E'):
        if precision:
            ps_fmt += f'{specifier}{precision}'
        else:
            ps_fmt += specifier
    elif specifier in ('g', 'G'):
        if precision:
            ps_fmt += f'{specifier}{precision}'
        else:
            ps_fmt += specifier
    else:
        ps_fmt += '0'
    ps_fmt += '}'
    return ps_fmt
def _convert_sha256sum(cmd: str) -> str:
    if not cmd or not cmd.strip():
        return '$input | ForEach-Object { (Get-FileHash -Algorithm SHA256 -Stream ([System.IO.MemoryStream]::new([System.Text.Encoding]::UTF8.GetBytes($_)))).Hash + "  -" }'
    parts = _parse_command_line(cmd)
    if not parts:
        return '$input | ForEach-Object { (Get-FileHash -Algorithm SHA256 -Stream ([System.IO.MemoryStream]::new([System.Text.Encoding]::UTF8.GetBytes($_)))).Hash + "  -" }'
    if parts[0] in ('sha256sum', '/bin/sha256sum', '/usr/bin/sha256sum'):
        parts = parts[1:]
    if not parts:
        return '$input | ForEach-Object { (Get-FileHash -Algorithm SHA256 -Stream ([System.IO.MemoryStream]::new([System.Text.Encoding]::UTF8.GetBytes($_)))).Hash + "  -" }'
    options: Dict[str, Any] = {
        'binary': False,
        'check': False,
        'tag': False,
        'text': True,
        'zero': False,
        'ignore_missing': False,
        'quiet': False,
        'status': False,
        'strict': False,
        'warn': False,
        'show_help': False,
        'show_version': False,
    }
    files: List[str] = []
    i = 0
    while i < len(parts):
        part = parts[i]
        if part == '--':
            files.extend(parts[i + 1:])
            break
        if part.startswith('/') and len(part) >= 2:
            if len(part) == 2 and part[1].isalpha():
                part = '-' + part[1:]
            elif len(part) > 2 and part[1].isalpha():
                part = '--' + part[1:]
        if part.startswith('--'):
            long_opt = part[2:]
            if long_opt == 'help':
                options['show_help'] = True
                i += 1
                continue
            elif long_opt == 'version':
                options['show_version'] = True
                i += 1
                continue
            elif long_opt == 'binary':
                options['binary'] = True
                options['text'] = False
                i += 1
                continue
            elif long_opt == 'check':
                options['check'] = True
                i += 1
                continue
            elif long_opt == 'tag':
                options['tag'] = True
                i += 1
                continue
            elif long_opt == 'text':
                options['text'] = True
                options['binary'] = False
                i += 1
                continue
            elif long_opt == 'zero':
                options['zero'] = True
                i += 1
                continue
            elif long_opt == 'ignore-missing':
                options['ignore_missing'] = True
                i += 1
                continue
            elif long_opt == 'quiet':
                options['quiet'] = True
                i += 1
                continue
            elif long_opt == 'status':
                options['status'] = True
                i += 1
                continue
            elif long_opt == 'strict':
                options['strict'] = True
                i += 1
                continue
            elif long_opt == 'warn':
                options['warn'] = True
                i += 1
                continue
            i += 1
            continue
        if part.startswith('-') and len(part) > 1:
            opt_chars = part[1:]
            for char in opt_chars:
                if char == 'b':
                    options['binary'] = True
                    options['text'] = False
                elif char == 'c':
                    options['check'] = True
                elif char == 't':
                    options['text'] = True
                    options['binary'] = False
                elif char == 'z':
                    options['zero'] = True
                elif char == 'w':
                    options['warn'] = True
            i += 1
            continue
        files.append(part)
        i += 1
    return _build_sha256sum_powershell_command(options, files)
def _build_sha256sum_powershell_command(options: Dict[str, Any], files: List[str]) -> str:
    if options.get('show_help'):
        return (
            'Write-Output "Usage: sha256sum [OPTION]... [FILE]...\n'
            'Print or check SHA256 (256-bit) checksums.\n\n'
            '  -b, --binary         read in binary mode\n'
            '  -c, --check          read SHA256 sums from the FILEs and check them\n'
            '      --tag            create a BSD-style checksum\n'
            '  -t, --text           read in text mode (default)\n'
            '  -z, --zero           end each output line with NUL, not newline\n'
            '      --ignore-missing don\'t fail or report status for missing files\n'
            '      --quiet          don\'t print OK for each successfully verified file\n'
            '      --status         don\'t output anything, status code shows success\n'
            '      --strict         exit non-zero for improperly formatted checksum lines\n'
            '  -w, --warn           warn about improperly formatted checksum lines\n'
            '      --help           display this help and exit\n'
            '      --version        output version information and exit"'
        )
    if options.get('show_version'):
        return 'Write-Output "sha256sum (GNU coreutils) 9.4"'
    check_mode = options.get('check', False)
    tag_mode = options.get('tag', False)
    zero_mode = options.get('zero', False)
    ignore_missing = options.get('ignore_missing', False)
    quiet = options.get('quiet', False)
    status_mode = options.get('status', False)
    strict_mode = options.get('strict', False)
    warn_mode = options.get('warn', False)
    if not files:
        if check_mode:
            return _build_check_command_stdin(options)
        else:
            return '$input | ForEach-Object { (Get-FileHash -Algorithm SHA256 -Stream ([System.IO.MemoryStream]::new([System.Text.Encoding]::UTF8.GetBytes($_)))).Hash + "  -" }'
    commands = []
    for file_path in files:
        if file_path == '-':
            if check_mode:
                commands.append(_build_check_command_stdin(options))
            else:
                commands.append('$input | ForEach-Object { (Get-FileHash -Algorithm SHA256 -Stream ([System.IO.MemoryStream]::new([System.Text.Encoding]::UTF8.GetBytes($_)))).Hash + "  -" }')
            continue
        quoted_file = file_path
        if ' ' in file_path and not (file_path.startswith('"') or file_path.startswith("'")):
            quoted_file = f'"{file_path}"'
        if check_mode:
            cmd = _build_check_command(quoted_file, options)
        elif tag_mode:
            cmd = _build_tag_command(quoted_file, zero_mode)
        else:
            cmd = _build_hash_command(quoted_file, zero_mode)
        commands.append(cmd)
    if len(commands) == 1:
        return commands[0]
    return '; '.join(commands)
def _build_hash_command(file_path: str, zero_mode: bool) -> str:
    if zero_mode:
        return f'(Get-FileHash -Algorithm SHA256 {file_path}).Hash + "  " + (Get-Item {file_path}).Name | Write-Host -NoNewline; Write-Host -NoNewline "`0"'
    else:
        return f'(Get-FileHash -Algorithm SHA256 {file_path}).Hash + "  " + (Get-Item {file_path}).Name'
def _build_tag_command(file_path: str, zero_mode: bool) -> str:
    if zero_mode:
        return f'Write-Output "SHA256 ({file_path}) = $((Get-FileHash -Algorithm SHA256 {file_path}).Hash)" | Write-Host -NoNewline; Write-Host -NoNewline "`0"'
    else:
        return f'Write-Output "SHA256 ({file_path}) = $((Get-FileHash -Algorithm SHA256 {file_path}).Hash)"'
def _build_check_command(checksum_file: str, options: Dict[str, Any]) -> str:
    ignore_missing = options.get('ignore_missing', False)
    quiet = options.get('quiet', False)
    status_mode = options.get('status', False)
    strict_mode = options.get('strict', False)
    warn_mode = options.get('warn', False)
    lines = []
    lines.append(f'$checksumFile = {checksum_file}')
    lines.append('$exitCode = 0')
    lines.append('$hasErrors = $false')
    lines.append('')
    lines.append('foreach ($line in Get-Content $checksumFile) {')
    lines.append('    $line = $line.Trim()')
    lines.append('    if ([string]::IsNullOrWhiteSpace($line)) { continue }')
    lines.append('    ')
    lines.append('    # Parse checksum line: <hash> <mode><filename>')
    lines.append('    # Mode is either " " (text) or "*" (binary)')
    lines.append('    if ($line -match "^([a-fA-F0-9]{64})\\s([ \\*])(.+)$") {')
    lines.append('        $expectedHash = $matches[1].ToUpper()')
    lines.append('        $mode = $matches[2]')
    lines.append('        $file = $matches[3]')
    lines.append('        ')
    lines.append('        if (Test-Path $file) {')
    lines.append('            $actualHash = (Get-FileHash -Algorithm SHA256 $file).Hash')
    lines.append('            if ($actualHash -eq $expectedHash) {')
    if not quiet and not status_mode:
        lines.append('                Write-Output "$file: OK"')
    lines.append('            } else {')
    lines.append('                $hasErrors = $true')
    lines.append('                $exitCode = 1')
    if not status_mode:
        lines.append('                Write-Output "$file: FAILED"')
    lines.append('            }')
    lines.append('        } else {')
    lines.append('            if (-not $ignoreMissing) {')
    lines.append('                $hasErrors = $true')
    lines.append('                $exitCode = 1')
    if not status_mode:
        lines.append('                Write-Output "$file: No such file or directory"')
    lines.append('            }')
    lines.append('        }')
    lines.append('    } else {')
    if strict_mode:
        lines.append('        $exitCode = 1')
    if warn_mode or strict_mode:
        lines.append('        if (-not $status) { Write-Warning "Invalid checksum line: $line" }')
    lines.append('    }')
    lines.append('}')
    lines.append('')
    lines.append('exit $exitCode')
    return '; '.join(lines)
def _build_check_command_stdin(options: Dict[str, Any]) -> str:
    ignore_missing = options.get('ignore_missing', False)
    quiet = options.get('quiet', False)
    status_mode = options.get('status', False)
    strict_mode = options.get('strict', False)
    warn_mode = options.get('warn', False)
    lines = []
    lines.append('$exitCode = 0')
    lines.append('$hasErrors = $false')
    lines.append('$input | ForEach-Object {')
    lines.append('    $line = $_.Trim()')
    lines.append('    if ([string]::IsNullOrWhiteSpace($line)) { return }')
    lines.append('    ')
    lines.append('    # Parse checksum line: <hash> <mode><filename>')
    lines.append('    if ($line -match "^([a-fA-F0-9]{64})\\s([ \\*])(.+)$") {')
    lines.append('        $expectedHash = $matches[1].ToUpper()')
    lines.append('        $file = $matches[3]')
    lines.append('        ')
    lines.append('        if (Test-Path $file) {')
    lines.append('            $actualHash = (Get-FileHash -Algorithm SHA256 $file).Hash')
    lines.append('            if ($actualHash -eq $expectedHash) {')
    if not quiet and not status_mode:
        lines.append('                Write-Output "$file: OK"')
    lines.append('            } else {')
    lines.append('                $hasErrors = $true')
    lines.append('                $exitCode = 1')
    if not status_mode:
        lines.append('                Write-Output "$file: FAILED"')
    lines.append('            }')
    lines.append('        } else {')
    lines.append('            if (-not $ignoreMissing) {')
    lines.append('                $hasErrors = $true')
    lines.append('                $exitCode = 1')
    if not status_mode:
        lines.append('                Write-Output "$file: No such file or directory"')
    lines.append('            }')
    lines.append('        }')
    lines.append('    } else {')
    if strict_mode:
        lines.append('        $exitCode = 1')
    if warn_mode or strict_mode:
        lines.append('        if (-not $status) { Write-Warning "Invalid checksum line: $line" }')
    lines.append('    }')
    lines.append('}')
    lines.append('')
    lines.append('exit $exitCode')
    return '; '.join(lines)
if __name__ == "__main__":
    test_cases = [
        "sha256sum file.txt",
        "sha256sum -b file.bin",
        "sha256sum --binary file.bin",
        "sha256sum -t file.txt",
        "sha256sum --text file.txt",
        "sha256sum -c checksums.txt",
        "sha256sum --check checksums.txt",
        "sha256sum --tag file.txt",
        "sha256sum -z file.txt",
        "sha256sum --zero file.txt",
        "sha256sum file1.txt file2.txt",
        "sha256sum -",
        "sha256sum --help",
        "sha256sum --version",
        "sha256sum -c --quiet checksums.txt",
        "sha256sum -c --status checksums.txt",
        "sha256sum -c --ignore-missing checksums.txt",
        "sha256sum -c --strict checksums.txt",
        "sha256sum -c --warn checksums.txt",
        "sha256sum -cw checksums.txt",
        "sha256sum /b file.bin",
        "sha256sum /c checksums.txt",
        "sha256sum /tag file.txt",
        r"sha256sum file\ with\ spaces.txt",
        'sha256sum "file with spaces.txt"',
    ]
    for test in test_cases:
        result = _convert_sha256sum(test)
        print(f"Input:  {test}")
        print(f"Output: {result}")
        print()
def _convert_sha512sum(cmd: str) -> str:
    if not cmd or not cmd.strip():
        return '$input | ForEach-Object { (Get-FileHash -Algorithm SHA512 -Path $_).Hash.ToLower() + "  $_" }'
    parts = _parse_command_line(cmd)
    if not parts:
        return '$input | ForEach-Object { (Get-FileHash -Algorithm SHA512 -Path $_).Hash.ToLower() + "  $_" }'
    if parts[0] in ('sha512sum', '/bin/sha512sum', '/usr/bin/sha512sum'):
        parts = parts[1:]
    if not parts:
        return '$input | ForEach-Object { (Get-FileHash -Algorithm SHA512 -Path $_).Hash.ToLower() + "  $_" }'
    options: Dict[str, Any] = {
        'binary': False,
        'check': False,
        'text': False,
        'tag': False,
        'zero': False,
        'ignore_missing': False,
        'quiet': False,
        'status': False,
        'warn': False,
        'strict': False,
        'show_help': False,
        'show_version': False,
    }
    files: List[str] = []
    i = 0
    while i < len(parts):
        part = parts[i]
        if part == '--':
            files.extend(parts[i + 1:])
            break
        if part.startswith('/') and len(part) >= 2:
            if len(part) == 2 and part[1].isalpha():
                part = '-' + part[1:]
            elif len(part) > 2 and part[1].isalpha():
                part = '--' + part[1:]
        if part.startswith('--'):
            long_opt = part[2:]
            if long_opt == 'help':
                options['show_help'] = True
                i += 1
                continue
            elif long_opt == 'version':
                options['show_version'] = True
                i += 1
                continue
            elif long_opt == 'binary':
                options['binary'] = True
                i += 1
                continue
            elif long_opt == 'check':
                options['check'] = True
                i += 1
                continue
            elif long_opt == 'text':
                options['text'] = True
                i += 1
                continue
            elif long_opt == 'tag':
                options['tag'] = True
                i += 1
                continue
            elif long_opt == 'zero':
                options['zero'] = True
                i += 1
                continue
            elif long_opt == 'ignore-missing':
                options['ignore_missing'] = True
                i += 1
                continue
            elif long_opt == 'quiet':
                options['quiet'] = True
                i += 1
                continue
            elif long_opt == 'status':
                options['status'] = True
                i += 1
                continue
            elif long_opt == 'warn':
                options['warn'] = True
                i += 1
                continue
            elif long_opt == 'strict':
                options['strict'] = True
                i += 1
                continue
            i += 1
            continue
        if part.startswith('-') and len(part) > 1:
            opt_chars = part[1:]
            j = 0
            while j < len(opt_chars):
                char = opt_chars[j]
                if char == 'b':
                    options['binary'] = True
                    j += 1
                elif char == 'c':
                    options['check'] = True
                    j += 1
                elif char == 't':
                    options['text'] = True
                    j += 1
                elif char == 'z':
                    options['zero'] = True
                    j += 1
                elif char == 'w':
                    options['warn'] = True
                    j += 1
                elif char == 'q':
                    options['quiet'] = True
                    j += 1
                else:
                    j += 1
            i += 1
            continue
        files.append(part)
        i += 1
    return _build_sha512sum_powershell_command(options, files)
def _build_sha512sum_powershell_command(options: Dict[str, Any], files: List[str]) -> str:
    if options.get('show_help'):
        return (
            'Write-Output "Usage: sha512sum [OPTION]... [FILE]...\n'
            'Print or check SHA512 (512-bit) checksums.\n\n'
            '  -b, --binary         read in binary mode\n'
            '  -c, --check          read SHA512 sums from the FILEs and check them\n'
            '      --tag            create a BSD-style checksum\n'
            '  -t, --text           read in text mode (default)\n'
            '  -z, --zero           end each output line with NUL, not newline,\n'
            '                       and disable file name escaping\n'
            '      --ignore-missing  don\'t fail or report status for missing files\n'
            '      --quiet          don\'t print OK for each successfully verified file\n'
            '      --status         don\'t output anything, status code shows success\n'
            '  -w, --warn           warn about improperly formatted checksum lines\n'
            '      --strict         with --check, exit non-zero for improperly formatted lines\n'
            '      --help           display this help and exit\n'
            '      --version        output version information and exit"'
        )
    if options.get('show_version'):
        return 'Write-Output "sha512sum (GNU coreutils) 8.32"'
    check_mode = options.get('check', False)
    quiet = options.get('quiet', False)
    status = options.get('status', False)
    warn = options.get('warn', False)
    strict = options.get('strict', False)
    tag = options.get('tag', False)
    zero = options.get('zero', False)
    ignore_missing = options.get('ignore_missing', False)
    if check_mode:
        if not files:
            return '# Error: No checksum file specified for -c/--check mode'
        checksum_file = files[0]
        if ' ' in checksum_file and not (checksum_file.startswith('"') or checksum_file.startswith("'")):
            checksum_file = f'"{checksum_file}"'
        notes = []
        if quiet:
            notes.append('quiet mode')
        if status:
            notes.append('status only')
        if warn:
            notes.append('warn on format errors')
        if strict:
            notes.append('strict mode')
        if ignore_missing:
            notes.append('ignore missing')
        note_str = ', '.join(notes) if notes else 'verify checksums'
        return f'# Check SHA512 checksums ({note_str}): Parse {checksum_file} and compare with Get-FileHash -Algorithm SHA512'
    if not files:
        return '$input | ForEach-Object { (Get-FileHash -Algorithm SHA512 -Path $_).Hash.ToLower() + "  $_" }'
    commands = []
    for file_path in files:
        if file_path == '-':
            commands.append('$input | ForEach-Object { (Get-FileHash -Algorithm SHA512 -Path $_).Hash.ToLower() + "  $_" }')
            continue
        quoted_file = file_path
        if ' ' in file_path and not (file_path.startswith('"') or file_path.startswith("'")):
            quoted_file = f'"{file_path}"'
        if tag:
            cmd = f'"SHA512 ({file_path}) = " + (Get-FileHash -Algorithm SHA512 -Path {quoted_file}).Hash.ToLower()'
            if zero:
                cmd += ' # Note: -z (zero line ending) not directly supported in PowerShell'
            commands.append(cmd)
        else:
            cmd = f'(Get-FileHash -Algorithm SHA512 -Path {quoted_file}).Hash.ToLower() + "  {file_path}"'
            if zero:
                cmd += ' # Note: -z (zero line ending) not directly supported in PowerShell'
            commands.append(cmd)
    if len(commands) == 1:
        return commands[0]
    return '; '.join(commands)
if __name__ == "__main__":
    test_cases = [
        "sha512sum file.txt",
        "sha512sum -c checksum.sha512",
        "sha512sum --check checksums.txt",
        "sha512sum file1.txt file2.txt",
        "sha512sum --quiet -c checksum.sha512",
        "sha512sum --status -c checksum.sha512",
        "sha512sum -b file.txt",
        "sha512sum -t file.txt",
        "sha512sum -w -c checksum.sha512",
        "sha512sum --strict --check checksum.sha512",
        "sha512sum",
        "sha512sum -",
        "sha512sum --help",
        "sha512sum --version",
        "sha512sum /b file.txt",
        "sha512sum /c checksum.sha512",
        "sha512sum /t /b file.txt",
        "sha512sum -bw file.bin",
        "sha512sum 'file with spaces.txt'",
        'sha512sum "another file.txt"',
        "sha512sum --tag file.txt",
        "sha512sum -z file.txt",
        "sha512sum --zero file.txt",
        "sha512sum --ignore-missing -c checksum.sha512",
        "sha512sum /tag file.txt",
        "sha512sum /zero file.txt",
    ]
    for test in test_cases:
        result = _convert_sha512sum(test)
        print(f"Input:  {test}")
        print(f"Output: {result}")
        print()
def _parse_count(value: str) -> int:
    value = value.strip()
    if not value:
        return 0
    match = re.match(r'^(\d+(?:\.\d+)?)\s*([a-zA-Z]*)$', value)
    if not match:
        try:
            return int(value)
        except ValueError:
            return 0
    num_str, suffix = match.groups()
    num = float(num_str)
    multipliers = {
        'b': 512,
        'kB': 1000,
        'KB': 1000,
        'K': 1024,
        'k': 1024,
        'MB': 1000 * 1000,
        'M': 1024 * 1024,
        'GB': 1000 * 1000 * 1000,
        'G': 1024 * 1024 * 1024,
        'TB': 1000 * 1000 * 1000 * 1000,
        'T': 1024 * 1024 * 1024 * 1024,
        'PB': 1000 * 1000 * 1000 * 1000 * 1000,
        'P': 1024 * 1024 * 1024 * 1024 * 1024,
        'EB': 1000 * 1000 * 1000 * 1000 * 1000 * 1000,
        'E': 1024 * 1024 * 1024 * 1024 * 1024 * 1024,
        'ZB': 1000 * 1000 * 1000 * 1000 * 1000 * 1000 * 1000,
        'Z': 1024 * 1024 * 1024 * 1024 * 1024 * 1024 * 1024,
        'YB': 1000 * 1000 * 1000 * 1000 * 1000 * 1000 * 1000 * 1000,
        'Y': 1024 * 1024 * 1024 * 1024 * 1024 * 1024 * 1024 * 1024,
        'KiB': 1024,
        'MiB': 1024 * 1024,
        'GiB': 1024 * 1024 * 1024,
        'TiB': 1024 * 1024 * 1024 * 1024,
        'PiB': 1024 * 1024 * 1024 * 1024 * 1024,
        'EiB': 1024 * 1024 * 1024 * 1024 * 1024 * 1024,
        'ZiB': 1024 * 1024 * 1024 * 1024 * 1024 * 1024 * 1024,
        'YiB': 1024 * 1024 * 1024 * 1024 * 1024 * 1024 * 1024 * 1024,
    }
    multiplier = multipliers.get(suffix, 1)
    return int(num * multiplier)
def _convert_shuf(cmd: str) -> str:
    if not cmd or not cmd.strip():
        return '$input | Get-Random -Shuffle'
    parts = _parse_command_line(cmd)
    if not parts:
        return '$input | Get-Random -Shuffle'
    if parts[0] in ('shuf', '/bin/shuf', '/usr/bin/shuf'):
        parts = parts[1:]
    if not parts:
        return '$input | Get-Random -Shuffle'
    echo_mode = False
    input_range: Optional[str] = None
    head_count: Optional[int] = None
    output_file: Optional[str] = None
    repeat = False
    zero_terminated = False
    show_help = False
    show_version = False
    files: List[str] = []
    echo_args: List[str] = []
    i = 0
    while i < len(parts):
        part = parts[i]
        if part == '--':
            if echo_mode:
                echo_args.extend(parts[i + 1:])
            else:
                files.extend(parts[i + 1:])
            break
        if part.startswith('/') and len(part) >= 2:
            if len(part) == 2 and part[1].isalpha():
                part = '-' + part[1:]
            elif len(part) > 2 and part[1].isalpha():
                part = '--' + part[1:]
        if part.startswith('--'):
            long_opt = part[2:]
            if long_opt == 'help':
                show_help = True
                i += 1
                continue
            if long_opt == 'version':
                show_version = True
                i += 1
                continue
            if long_opt == 'echo':
                echo_mode = True
                i += 1
                continue
            if long_opt == 'repeat':
                repeat = True
                i += 1
                continue
            if long_opt == 'zero-terminated':
                zero_terminated = True
                i += 1
                continue
            if long_opt.startswith('input-range='):
                input_range = long_opt.split('=', 1)[1]
                i += 1
                continue
            if long_opt.startswith('head-count='):
                head_count = _parse_count(long_opt.split('=', 1)[1])
                i += 1
                continue
            if long_opt.startswith('output='):
                output_file = long_opt.split('=', 1)[1]
                i += 1
                continue
            i += 1
            continue
        if part.startswith('-') and len(part) > 1:
            opt_chars = part[1:]
            j = 0
            while j < len(opt_chars):
                char = opt_chars[j]
                if char == 'e':
                    echo_mode = True
                    j += 1
                elif char == 'i':
                    if j + 1 < len(opt_chars):
                        input_range = opt_chars[j + 1:]
                        break
                    elif i + 1 < len(parts):
                        i += 1
                        input_range = parts[i]
                    j += 1
                elif char == 'n':
                    if j + 1 < len(opt_chars):
                        head_count = _parse_count(opt_chars[j + 1:])
                        break
                    elif i + 1 < len(parts):
                        i += 1
                        head_count = _parse_count(parts[i])
                    j += 1
                elif char == 'o':
                    if j + 1 < len(opt_chars):
                        output_file = opt_chars[j + 1:]
                        break
                    elif i + 1 < len(parts):
                        i += 1
                        output_file = parts[i]
                    j += 1
                elif char == 'r':
                    repeat = True
                    j += 1
                elif char == 'z':
                    zero_terminated = True
                    j += 1
                else:
                    j += 1
            i += 1
            continue
        if echo_mode:
            echo_args.append(part)
        else:
            files.append(part)
        i += 1
    if show_help:
        return (
            'Write-Output "Usage: shuf [OPTION]... [FILE]\n'
            '  or:  shuf -e [OPTION]... [ARG]...\n'
            '  or:  shuf -i LO-HI [OPTION]...\n'
            'Shuffle lines from FILE or standard input randomly.\n\n'
            'Options:\n'
            '  -e, --echo                treat each ARG as an input line\n'
            '  -i, --input-range=LO-HI   treat each number LO through HI as an input line\n'
            '  -n, --head-count=COUNT    output at most COUNT lines\n'
            '  -o, --output=FILE         write result to FILE instead of standard output\n'
            '  -r, --repeat              output lines can be repeated\n'
            '  -z, --zero-terminated     end lines with NUL, not newline\n'
            '      --help     display this help and exit\n'
            '      --version  output version information and exit"'
        )
    if show_version:
        return 'Write-Output "shuf (GNU coreutils) 8.32"'
    return _build_shuf_powershell_command(
        echo_mode, input_range, head_count, output_file,
        repeat, zero_terminated, files, echo_args
    )
def _build_shuf_powershell_command(
    echo_mode: bool,
    input_range: Optional[str],
    head_count: Optional[int],
    output_file: Optional[str],
    repeat: bool,
    zero_terminated: bool,
    files: List[str],
    echo_args: List[str]
) -> str:
    commands: List[str] = []
    if echo_mode:
        if echo_args:
            quoted_args = []
            for arg in echo_args:
                if ' ' in arg and not (arg.startswith('"') or arg.startswith("'")):
                    quoted_args.append(f'"{arg}"')
                else:
                    quoted_args.append(f'"{arg}"')
            input_source = f'@({", ".join(quoted_args)})'
        else:
            input_source = '@()'
    elif input_range:
        range_match = re.match(r'^(\d+)-(\d+)$', input_range)
        if range_match:
            lo = int(range_match.group(1))
            hi = int(range_match.group(2))
            input_source = f'{lo}..{hi}'
        else:
            input_source = '@()'
    elif files:
        if len(files) == 1:
            file_path = files[0]
            if ' ' in file_path and not (file_path.startswith('"') or file_path.startswith("'")):
                file_path = f'"{file_path}"'
            input_source = f'Get-Content {file_path}'
        else:
            quoted_files = []
            for f in files:
                if ' ' in f and not (f.startswith('"') or f.startswith("'")):
                    quoted_files.append(f'"{f}"')
                else:
                    quoted_files.append(f)
            input_source = f'Get-Content {",".join(quoted_files)}'
    else:
        input_source = '$input'
    if repeat:
        if head_count:
            if echo_mode and echo_args:
                shuffle_cmd = f'{input_source} | ForEach-Object {{ $_ }} | Get-Random -Count {head_count}'
            elif input_range:
                shuffle_cmd = f'({input_source} | ForEach-Object {{ $_ }}) | Get-Random -Count {head_count}'
            else:
                shuffle_cmd = f'{input_source} | Get-Random -Count {head_count}'
        else:
            if echo_mode and echo_args:
                shuffle_cmd = f'{input_source} | ForEach-Object {{ $_ }} | Get-Random -Count {len(echo_args)}'
            elif input_range and range_match:
                lo = int(range_match.group(1))
                hi = int(range_match.group(2))
                count = hi - lo + 1
                shuffle_cmd = f'{input_source} | ForEach-Object {{ $_ }} | Get-Random -Count {count}'
            else:
                shuffle_cmd = f'{input_source} | Get-Random -Shuffle'
    else:
        if head_count:
            if input_source.startswith('$input'):
                shuffle_cmd = f'({input_source} | Get-Random -Shuffle) | Select-Object -First {head_count}'
            else:
                shuffle_cmd = f'({input_source} | Get-Random -Shuffle) | Select-Object -First {head_count}'
        else:
            shuffle_cmd = f'{input_source} | Get-Random -Shuffle'
    commands.append(shuffle_cmd)
    if output_file:
        if ' ' in output_file and not (output_file.startswith('"') or output_file.startswith("'")):
            output_file = f'"{output_file}"'
        if zero_terminated:
            commands.append(f'Set-Content {output_file} -NoNewline')
        else:
            commands.append(f'Set-Content {output_file}')
    if zero_terminated and not output_file:
        commands.append('# NOTE: -z (zero-terminated) not fully supported in PowerShell')
    return ' | '.join(commands)
if __name__ == "__main__":
    test_cases = [
        "shuf file.txt",
        "shuf -n 5 file.txt",
        "shuf -e a b c",
        "shuf -i 1-100",
        "shuf -i 1-100 -n 10",
        "shuf -o output.txt file.txt",
        "shuf -r -n 5 -e a b c",
        "shuf --echo foo bar baz",
        "shuf --input-range=1-50",
        "shuf --head-count=20 file.txt",
        "shuf --output=result.txt input.txt",
        "shuf --repeat -n 10 -i 1-5",
        "shuf -z file.txt",
        "shuf /e a b c",
        "shuf /n 3 file.txt",
        "shuf /i 1-10",
    ]
    for test in test_cases:
        result = _convert_shuf(test)
        print(f"Input:  {test}")
        print(f"Output: {result}")
        print()
def _convert_sleep(cmd: str) -> str:
    if not cmd or not cmd.strip():
        return 'Start-Sleep'
    parts = _parse_command_line(cmd)
    if not parts:
        return 'Start-Sleep'
    if parts[0] in ('sleep', '/bin/sleep', '/usr/bin/sleep'):
        parts = parts[1:]
    if not parts:
        return 'Start-Sleep'
    time_specs: List[str] = []
    show_help = False
    show_version = False
    i = 0
    while i < len(parts):
        part = parts[i]
        if part.startswith('/') and len(part) >= 2 and part[1].isalpha():
            if len(part) == 2:
                part = '-' + part[1:]
            else:
                part = '--' + part[1:]
        if part == '--':
            time_specs.extend(parts[i + 1:])
            break
        if part.startswith('--'):
            opt_name = part[2:]
            if opt_name == 'help':
                show_help = True
            elif opt_name == 'version':
                show_version = True
            i += 1
            continue
        if part.startswith('-') and len(part) > 1:
            opt_chars = part[1:]
            for char in opt_chars:
                if char == 'h':
                    show_help = True
                elif char == 'v':
                    show_version = True
            i += 1
            continue
        time_specs.append(part)
        i += 1
    if show_help:
        return (
            'Write-Output "sleep - delay for a specified amount of time\n'
            'Usage: sleep NUMBER[SUFFIX]...\n'
            '       sleep OPTION\n'
            'Pause for NUMBER seconds. SUFFIX may be:\n'
            '  s - seconds (default)\n'
            '  m - minutes\n'
            '  h - hours\n'
            '  d - days\n'
            'Multiple arguments are summed.\n'
            'Options:\n'
            '  --help     Display this help and exit\n'
            '  --version  Output version information and exit"'
        )
    if show_version:
        return 'Write-Output "sleep (GNU coreutils)"'
    total_seconds = _calculate_total_seconds(time_specs)
    if total_seconds is None:
        return 'Start-Sleep'
    if total_seconds < 1:
        milliseconds = int(round(total_seconds * 1000))
        if milliseconds == 0:
            milliseconds = 1
        return f'Start-Sleep -Milliseconds {milliseconds}'
    else:
        if total_seconds == int(total_seconds):
            return f'Start-Sleep -Seconds {int(total_seconds)}'
        else:
            return f'Start-Sleep -Seconds {total_seconds}'
def _calculate_total_seconds(time_specs: List[str]) -> Optional[float]:
    if not time_specs:
        return None
    total = 0.0
    has_valid_spec = False
    time_pattern = re.compile(r'^(\d+\.?\d*)([smhd])?$', re.IGNORECASE)
    ms_pattern = re.compile(r'^(\d+\.?\d*)ms$', re.IGNORECASE)
    for spec in time_specs:
        spec = spec.strip()
        if not spec:
            continue
        ms_match = ms_pattern.match(spec)
        if ms_match:
            value = float(ms_match.group(1))
            total += value / 1000.0
            has_valid_spec = True
            continue
        match = time_pattern.match(spec)
        if match:
            value = float(match.group(1))
            suffix = match.group(2)
            if suffix:
                suffix = suffix.lower()
                if suffix == 's':
                    total += value
                elif suffix == 'm':
                    total += value * 60
                elif suffix == 'h':
                    total += value * 3600
                elif suffix == 'd':
                    total += value * 86400
            else:
                total += value
            has_valid_spec = True
    return total if has_valid_spec else None
def _convert_slash_to_dash(arg: str) -> str:
    if not arg.startswith('/') or len(arg) < 2:
        return arg
    if arg[1].isalpha():
        if len(arg) == 2:
            return '-' + arg[1:]
        else:
            return '--' + arg[1:]
    return arg
def _parse_size(size_str: str) -> int:
    size_str = size_str.strip()
    if not size_str:
        return 0
    match = re.match(r'^(\d+(?:\.\d+)?)\s*([a-zA-Z]*)$', size_str)
    if not match:
        try:
            return int(size_str)
        except ValueError:
            return 0
    num_str, suffix = match.groups()
    num = float(num_str)
    multipliers = {
        '': 1,
        'b': 512,
        'kB': 1000,
        'KB': 1000,
        'K': 1024,
        'k': 1024,
        'MB': 1000 * 1000,
        'M': 1024 * 1024,
        'GB': 1000 * 1000 * 1000,
        'G': 1024 * 1024 * 1024,
        'TB': 1000 * 1000 * 1000 * 1000,
        'T': 1024 * 1024 * 1024 * 1024,
        'PB': 1000 * 1000 * 1000 * 1000 * 1000,
        'P': 1024 * 1024 * 1024 * 1024 * 1024,
        'EB': 1000 * 1000 * 1000 * 1000 * 1000 * 1000,
        'E': 1024 * 1024 * 1024 * 1024 * 1024 * 1024,
        'ZB': 1000 * 1000 * 1000 * 1000 * 1000 * 1000 * 1000,
        'Z': 1024 * 1024 * 1024 * 1024 * 1024 * 1024 * 1024,
        'YB': 1000 * 1000 * 1000 * 1000 * 1000 * 1000 * 1000 * 1000,
        'Y': 1024 * 1024 * 1024 * 1024 * 1024 * 1024 * 1024 * 1024,
        'RB': 1000 ** 9,
        'R': 1024 ** 9,
        'QB': 1000 ** 10,
        'Q': 1024 ** 10,
        'KiB': 1024,
        'MiB': 1024 * 1024,
        'GiB': 1024 * 1024 * 1024,
        'TiB': 1024 * 1024 * 1024 * 1024,
        'PiB': 1024 * 1024 * 1024 * 1024 * 1024,
        'EiB': 1024 * 1024 * 1024 * 1024 * 1024 * 1024,
        'ZiB': 1024 * 1024 * 1024 * 1024 * 1024 * 1024 * 1024,
        'YiB': 1024 * 1024 * 1024 * 1024 * 1024 * 1024 * 1024 * 1024,
    }
    multiplier = multipliers.get(suffix, 1)
    return int(num * multiplier)
def _convert_split(cmd: str) -> str:
    if not cmd or not cmd.strip():
        return 'Write-Output "Usage: split [OPTION]... [FILE [PREFIX]]"'
    parts = _parse_command_line(cmd)
    if not parts:
        return 'Write-Output "Usage: split [OPTION]... [FILE [PREFIX]]"'
    if parts[0] in ('split', '/bin/split', '/usr/bin/split'):
        parts = parts[1:]
    if not parts:
        return 'Write-Output "Usage: split [OPTION]... [FILE [PREFIX]]"'
    suffix_length: Optional[int] = None
    additional_suffix: Optional[str] = None
    bytes_count: Optional[int] = None
    line_bytes: Optional[int] = None
    numeric_suffixes = False
    numeric_suffix_start: Optional[int] = None
    hex_suffixes = False
    hex_suffix_start: Optional[int] = None
    elide_empty_files = False
    filter_cmd: Optional[str] = None
    lines: Optional[int] = None
    chunks: Optional[str] = None
    separator: Optional[str] = None
    unbuffered = False
    verbose = False
    show_help = False
    show_version = False
    file: Optional[str] = None
    prefix: Optional[str] = None
    i = 0
    while i < len(parts):
        part = parts[i]
        part = _convert_slash_to_dash(part)
        if part == '--':
            remaining = parts[i + 1:]
            if len(remaining) >= 1:
                file = remaining[0]
            if len(remaining) >= 2:
                prefix = remaining[1]
            break
        if part.startswith('--'):
            long_opt = part[2:]
            if long_opt == 'help':
                show_help = True
                i += 1
                continue
            if long_opt == 'version':
                show_version = True
                i += 1
                continue
            if long_opt == 'verbose':
                verbose = True
                i += 1
                continue
            if long_opt == 'elide-empty-files':
                elide_empty_files = True
                i += 1
                continue
            if long_opt == 'unbuffered':
                unbuffered = True
                i += 1
                continue
            if long_opt.startswith('numeric-suffixes'):
                numeric_suffixes = True
                if '=' in long_opt:
                    try:
                        numeric_suffix_start = int(long_opt.split('=', 1)[1])
                    except ValueError:
                        pass
                i += 1
                continue
            if long_opt.startswith('hex-suffixes'):
                hex_suffixes = True
                if '=' in long_opt:
                    try:
                        hex_suffix_start = int(long_opt.split('=', 1)[1])
                    except ValueError:
                        pass
                i += 1
                continue
            if '=' in long_opt:
                opt_name, opt_value = long_opt.split('=', 1)
                if opt_name == 'suffix-length':
                    try:
                        suffix_length = int(opt_value)
                    except ValueError:
                        pass
                elif opt_name == 'additional-suffix':
                    additional_suffix = opt_value
                elif opt_name == 'bytes':
                    bytes_count = _parse_size(opt_value)
                    lines = None
                elif opt_name == 'line-bytes':
                    line_bytes = _parse_size(opt_value)
                elif opt_name == 'filter':
                    filter_cmd = opt_value
                elif opt_name == 'lines':
                    try:
                        lines = int(opt_value)
                        bytes_count = None
                    except ValueError:
                        pass
                elif opt_name == 'number':
                    chunks = opt_value
                elif opt_name == 'separator':
                    separator = opt_value
                i += 1
                continue
            i += 1
            continue
        if part.startswith('-') and len(part) > 1:
            opt_chars = part[1:]
            j = 0
            while j < len(opt_chars):
                char = opt_chars[j]
                if char == 'a':
                    if j + 1 < len(opt_chars):
                        try:
                            suffix_length = int(opt_chars[j + 1:])
                        except ValueError:
                            pass
                        break
                    elif i + 1 < len(parts):
                        try:
                            suffix_length = int(parts[i + 1])
                            i += 1
                        except ValueError:
                            pass
                    j += 1
                elif char == 'b':
                    if j + 1 < len(opt_chars):
                        bytes_count = _parse_size(opt_chars[j + 1:])
                        lines = None
                        break
                    elif i + 1 < len(parts):
                        bytes_count = _parse_size(parts[i + 1])
                        lines = None
                        i += 1
                    j += 1
                elif char == 'C':
                    if j + 1 < len(opt_chars):
                        line_bytes = _parse_size(opt_chars[j + 1:])
                        break
                    elif i + 1 < len(parts):
                        line_bytes = _parse_size(parts[i + 1])
                        i += 1
                    j += 1
                elif char == 'd':
                    numeric_suffixes = True
                    j += 1
                elif char == 'e':
                    elide_empty_files = True
                    j += 1
                elif char == 'l':
                    if j + 1 < len(opt_chars):
                        try:
                            lines = int(opt_chars[j + 1:])
                            bytes_count = None
                        except ValueError:
                            pass
                        break
                    elif i + 1 < len(parts):
                        try:
                            lines = int(parts[i + 1])
                            bytes_count = None
                            i += 1
                        except ValueError:
                            pass
                    j += 1
                elif char == 'n':
                    if j + 1 < len(opt_chars):
                        chunks = opt_chars[j + 1:]
                        break
                    elif i + 1 < len(parts):
                        chunks = parts[i + 1]
                        i += 1
                    j += 1
                elif char == 't':
                    if j + 1 < len(opt_chars):
                        separator = opt_chars[j + 1:]
                        break
                    elif i + 1 < len(parts):
                        separator = parts[i + 1]
                        if (separator.startswith('"') and separator.endswith('"')) or \
                           (separator.startswith("'") and separator.endswith("'")):
                            separator = separator[1:-1]
                        i += 1
                    j += 1
                elif char == 'u':
                    unbuffered = True
                    j += 1
                elif char == 'x':
                    hex_suffixes = True
                    j += 1
                else:
                    j += 1
            i += 1
            continue
        if file is None:
            file = part
        elif prefix is None:
            prefix = part
        i += 1
    if show_help:
        return (
            'Write-Output "split - split a file into pieces\\n'
            'Usage: split [OPTION]... [FILE [PREFIX]]\\n'
            'Output pieces of FILE to PREFIXaa, PREFIXab, ...; default size is 1000 lines,\\n'
            'and default PREFIX is `x`.\\n'
            'With no FILE, or when FILE is -, read standard input.\\n\\n'
            'Mandatory arguments to long options are mandatory for short options too.\\n'
            '  -a, --suffix-length=N   generate suffixes of length N (default 2)\\n'
            '      --additional-suffix=SUFFIX  append an additional SUFFIX to file names\\n'
            '  -b, --bytes=SIZE        put SIZE bytes per output file\\n'
            '  -C, --line-bytes=SIZE   put at most SIZE bytes of records per output file\\n'
            '  -d                      use numeric suffixes starting at 0, not alphabetic\\n'
            '      --numeric-suffixes[=FROM]  same as -d, but allow setting the start value\\n'
            '  -x                      use hex suffixes starting at 0, not alphabetic\\n'
            '      --hex-suffixes[=FROM]  same as -x, but allow setting the start value\\n'
            '  -e, --elide-empty-files  do not generate empty output files with `-n`\\n'
            '      --filter=COMMAND    write to shell COMMAND; file name is $FILE\\n'
            '  -l, --lines=NUMBER      put NUMBER lines/records per output file\\n'
            '  -n, --number=CHUNKS     generate CHUNKS output files; see explanation below\\n'
            '  -t, --separator=SEP     use SEP instead of newline as the record separator;\\n'
            '                           `\\0` (zero) specifies the NUL character\\n'
            '  -u, --unbuffered        immediately copy input to output with `-n r/...`\\n'
            '      --verbose           print a diagnostic just before each output file is opened\\n'
            '      --help              display this help and exit\\n'
            '      --version           output version information and exit\\n\\n'
            'The SIZE argument is an integer and optional unit (example: 10K is 10*1024).\\n'
            'Units are K,M,G,T,P,E,Z,Y,R,Q (powers of 1024) or KB,MB,... (powers of 1000).\\n'
            'Binary prefixes can be used, too: KiB=K, MiB=M, and so on.\\n\\n'
            'CHUNKS may be:\\n'
            '  N       split into N files based on size of input\\n'
            '  K/N     output Kth of N to standard output\\n'
            '  l/N     split into N files without splitting lines/records\\n'
            '  l/K/N   output Kth of N to standard output without splitting lines/records\\n'
            '  r/N     like `l` but use round robin distribution\\n'
            '  r/K/N   likewise but only output Kth of N to standard output"'
        )
    if show_version:
        return 'Write-Output "split (GNU coreutils) 8.32"'
    return _build_split_powershell_command(
        suffix_length, additional_suffix, bytes_count, line_bytes,
        numeric_suffixes, numeric_suffix_start, hex_suffixes, hex_suffix_start,
        elide_empty_files, filter_cmd, lines, chunks, separator, unbuffered,
        verbose, file, prefix
    )
def _build_split_powershell_command(
    suffix_length: Optional[int],
    additional_suffix: Optional[str],
    bytes_count: Optional[int],
    line_bytes: Optional[int],
    numeric_suffixes: bool,
    numeric_suffix_start: Optional[int],
    hex_suffixes: bool,
    hex_suffix_start: Optional[int],
    elide_empty_files: bool,
    filter_cmd: Optional[str],
    lines: Optional[int],
    chunks: Optional[str],
    separator: Optional[str],
    unbuffered: bool,
    verbose: bool,
    file: Optional[str],
    prefix: Optional[str]
) -> str:
    if suffix_length is None:
        suffix_length = 2
    if prefix is None:
        prefix = 'x'
    if lines is None and bytes_count is None and chunks is None:
        lines = 1000
    def escape_ps_string(s: str) -> str:
        return s.replace('`', '``').replace('$', '`$').replace('"', '`"')
    escaped_prefix = escape_ps_string(prefix)
    cmds = []
    if verbose:
        cmds.append(f'Write-Verbose "Splitting file with prefix: {escaped_prefix}"')
    if chunks:
        cmds.append(f'# NOTE: CHUNKS mode (-n {chunks}) requires custom implementation')
        chunk_parts = chunks.split('/')
        if len(chunk_parts) == 1:
            try:
                num_chunks = int(chunk_parts[0])
                if file and file != '-':
                    file_quoted = f'"{escape_ps_string(file)}"' if ' ' in file else file
                    cmds.append(
                        f'$content = Get-Content {file_quoted} -Raw; '
                        f'$size = [math]::Ceiling($content.Length / {num_chunks}); '
                        f'$suffix = 0; '
                        f'for ($i = 0; $i -lt $content.Length; $i += $size) {{ '
                        f'$chunk = $content.Substring($i, [math]::Min($size, $content.Length - $i)); '
                        f'$outfile = "{escaped_prefix}" + [Convert]::ToString($suffix, 36).PadLeft({suffix_length}, "0"); '
                        f'$chunk | Set-Content $outfile; $suffix++ }}'
                    )
                else:
                    cmds.append(
                        f'$content = $input -join "`n"; '
                        f'$size = [math]::Ceiling($content.Length / {num_chunks}); '
                        f'$suffix = 0; '
                        f'for ($i = 0; $i -lt $content.Length; $i += $size) {{ '
                        f'$chunk = $content.Substring($i, [math]::Min($size, $content.Length - $i)); '
                        f'$outfile = "{escaped_prefix}" + [Convert]::ToString($suffix, 36).PadLeft({suffix_length}, "0"); '
                        f'$chunk | Set-Content $outfile; $suffix++ }}'
                    )
            except ValueError:
                pass
        elif len(chunk_parts) == 2:
            try:
                k, n = int(chunk_parts[0]), int(chunk_parts[1])
                if file and file != '-':
                    file_quoted = f'"{escape_ps_string(file)}"' if ' ' in file else file
                    cmds.append(
                        f'$lines = Get-Content {file_quoted}; '
                        f'$start = [math]::Floor($lines.Count * {k - 1} / {n}); '
                        f'$end = [math]::Floor($lines.Count * {k} / {n}) - 1; '
                        f'$lines[$start..$end]'
                    )
                else:
                    cmds.append(
                        f'$lines = @($input); '
                        f'$start = [math]::Floor($lines.Count * {k - 1} / {n}); '
                        f'$end = [math]::Floor($lines.Count * {k} / {n}) - 1; '
                        f'$lines[$start..$end]'
                    )
            except ValueError:
                pass
    elif bytes_count is not None:
        if file and file != '-':
            file_quoted = f'"{escape_ps_string(file)}"' if ' ' in file else file
            if numeric_suffixes:
                suffix_fmt = 'numeric'
                start_val = numeric_suffix_start if numeric_suffix_start is not None else 0
            elif hex_suffixes:
                suffix_fmt = 'hex'
                start_val = hex_suffix_start if hex_suffix_start is not None else 0
            else:
                suffix_fmt = 'alpha'
                start_val = 0
            cmd = (
                f'$content = Get-Content {file_quoted} -Raw; '
                f'$bytes = [System.Text.Encoding]::UTF8.GetBytes($content); '
                f'$chunkSize = {bytes_count}; '
                f'$suffix = {start_val}; '
                f'for ($i = 0; $i -lt $bytes.Length; $i += $chunkSize) {{ '
                f'$chunk = $bytes[$i..([math]::Min($i + $chunkSize - 1, $bytes.Length - 1))]; '
            )
            if suffix_fmt == 'numeric':
                cmd += (
                    f'$outfile = "{escaped_prefix}" + $suffix.ToString().PadLeft({suffix_length}, "0")'
                )
            elif suffix_fmt == 'hex':
                cmd += (
                    f'$outfile = "{escaped_prefix}" + $suffix.ToString("X{suffix_length}").PadLeft({suffix_length}, "0")'
                )
            else:
                cmd += (
                    f'$outfile = "{escaped_prefix}"; '
                    f'$s = $suffix; '
                    f'for ($j = 0; $j -lt {suffix_length}; $j++) {{ '
                    f'$outfile = [char](97 + ($s % 26)) + $outfile; $s = [math]::Floor($s / 26) }}'
                )
            if additional_suffix:
                cmd += f' + "{escape_ps_string(additional_suffix)}"'
            if verbose:
                cmd += f'; Write-Output "Creating file: $outfile"'
            cmd += (
                f'; [System.IO.File]::WriteAllBytes($outfile, $chunk); '
                f'$suffix++ }}'
            )
            cmds.append(cmd)
        else:
            cmds.append(
                f'$content = $input -join "`n"; '
                f'$bytes = [System.Text.Encoding]::UTF8.GetBytes($content); '
                f'$chunkSize = {bytes_count}; '
                f'$suffix = 0; '
                f'for ($i = 0; $i -lt $bytes.Length; $i += $chunkSize) {{ '
                f'$chunk = $bytes[$i..([math]::Min($i + $chunkSize - 1, $bytes.Length - 1))]; '
                f'$outfile = "{escaped_prefix}" + $suffix.ToString().PadLeft({suffix_length}, "0"); '
                f'[System.IO.File]::WriteAllBytes($outfile, $chunk); $suffix++ }}'
            )
    elif lines is not None:
        if file and file != '-':
            file_quoted = f'"{escape_ps_string(file)}"' if ' ' in file else file
            if separator == '\\0' or separator == '\0':
                read_cmd = f'Get-Content {file_quoted} -Delimiter "`0"'
            elif separator:
                escaped_sep = escape_ps_string(separator)
                read_cmd = f'Get-Content {file_quoted} -Delimiter "{escaped_sep}"'
            else:
                read_cmd = f'Get-Content {file_quoted}'
            if numeric_suffixes:
                if numeric_suffix_start is not None:
                    suffix_init = f'$suffix = {numeric_suffix_start}'
                else:
                    suffix_init = '$suffix = 0'
                suffix_gen = f'$outfile = "{escaped_prefix}" + $suffix.ToString().PadLeft({suffix_length}, "0")'
            elif hex_suffixes:
                if hex_suffix_start is not None:
                    suffix_init = f'$suffix = {hex_suffix_start}'
                else:
                    suffix_init = '$suffix = 0'
                suffix_gen = f'$outfile = "{escaped_prefix}" + $suffix.ToString("X").PadLeft({suffix_length}, "0")'
            else:
                suffix_init = '$suffix = 0'
                suffix_gen = (
                    f'$outfile = "{escaped_prefix}"; '
                    f'$s = $suffix; '
                    f'for ($j = 0; $j -lt {suffix_length}; $j++) {{ '
                    f'$outfile = [char](97 + ($s % 26)) + $outfile; $s = [math]::Floor($s / 26) }}'
                )
            cmd = (
                f'$lines = {read_cmd}; '
                f'$totalLines = $lines.Count; '
                f'$linesPerFile = {lines}; '
                f'{suffix_init}; '
                f'for ($i = 0; $i -lt $totalLines; $i += $linesPerFile) {{ '
                f'$end = [math]::Min($i + $linesPerFile - 1, $totalLines - 1); '
                f'$chunk = $lines[$i..$end]; '
                f'{suffix_gen}; '
            )
            if additional_suffix:
                cmd += f'$outfile += "{escape_ps_string(additional_suffix)}"; '
            if verbose:
                cmd += f'Write-Output "Creating file: $outfile"; '
            if elide_empty_files:
                cmd += f'if ($chunk.Count -gt 0) {{ $chunk | Set-Content $outfile }}; '
            else:
                cmd += f'$chunk | Set-Content $outfile; '
            cmd += f'$suffix++ }}'
            cmds.append(cmd)
        else:
            cmds.append(
                f'$lines = @($input); '
                f'$totalLines = $lines.Count; '
                f'$linesPerFile = {lines}; '
                f'$suffix = 0; '
                f'for ($i = 0; $i -lt $totalLines; $i += $linesPerFile) {{ '
                f'$end = [math]::Min($i + $linesPerFile - 1, $totalLines - 1); '
                f'$chunk = $lines[$i..$end]; '
                f'$outfile = "{escaped_prefix}" + $suffix.ToString().PadLeft({suffix_length}, "0"); '
                f'$chunk | Set-Content $outfile; $suffix++ }}'
            )
    else:
        if file and file != '-':
            file_quoted = f'"{escape_ps_string(file)}"' if ' ' in file else file
            cmds.append(
                f'$lines = Get-Content {file_quoted}; '
                f'$totalLines = $lines.Count; '
                f'$linesPerFile = 1000; '
                f'$suffix = 0; '
                f'for ($i = 0; $i -lt $totalLines; $i += $linesPerFile) {{ '
                f'$end = [math]::Min($i + $linesPerFile - 1, $totalLines - 1); '
                f'$chunk = $lines[$i..$end]; '
                f'$outfile = "{escaped_prefix}" + $suffix.ToString().PadLeft({suffix_length}, "0"); '
                f'$chunk | Set-Content $outfile; $suffix++ }}'
            )
        else:
            cmds.append(
                f'$lines = @($input); '
                f'$totalLines = $lines.Count; '
                f'$linesPerFile = 1000; '
                f'$suffix = 0; '
                f'for ($i = 0; $i -lt $totalLines; $i += $linesPerFile) {{ '
                f'$end = [math]::Min($i + $linesPerFile - 1, $totalLines - 1); '
                f'$chunk = $lines[$i..$end]; '
                f'$outfile = "{escaped_prefix}" + $suffix.ToString().PadLeft({suffix_length}, "0"); '
                f'$chunk | Set-Content $outfile; $suffix++ }}'
            )
    if filter_cmd:
        cmds.append(f'# NOTE: --filter option not directly supported in PowerShell')
        cmds.append(f'# Filter command would be: {filter_cmd}')
    if unbuffered:
        cmds.append('# NOTE: --unbuffered option not directly supported in PowerShell')
    if line_bytes is not None:
        cmds.append(f'# NOTE: --line-bytes={line_bytes} option requires custom implementation')
    return '; '.join(cmds) if cmds else 'Write-Output "split: no operation specified"'
if __name__ == "__main__":
    test_cases = [
        "split file.txt",
        "split -l 100 file.txt",
        "split -l 100 file.txt output",
        "split -b 1M file.txt",
        "split -b 1024 file.txt part",
        "split -d file.txt",
        "split -d -a 3 file.txt",
        "split --numeric-suffixes=10 file.txt",
        "split -x file.txt",
        "split --hex-suffixes file.txt",
        "split -a 4 -l 50 file.txt prefix",
        "split --additional-suffix=.txt file.txt",
        "split -e -n 5 file.txt",
        "split --verbose -l 100 file.txt",
        "split -t ',' file.txt",
        "split /l 100 file.txt",
        "split /b 1K file.txt",
        "split --lines=200 file.txt",
        "split --bytes=10K file.txt",
        "split -n 4 file.txt",
        "split -n l/2/3 file.txt",
        "split --help",
        "split --version",
    ]
    for test in test_cases:
        result = _convert_split(test)
        print(f"Input:  {test}")
        print(f"Output: {result}")
        print()
def _convert_ssh(cmd: str) -> str:
    if not cmd or not cmd.strip():
        return 'Write-Output "usage: ssh [-46AaCfGgKkMNnqsTtVvXxYy] [-B bind_interface] [-b bind_address] [-c cipher_spec] [-D [bind_address:]port] [-E log_file] [-e escape_char] [-F configfile] [-I pkcs11] [-i identity_file] [-J [user@]host[:port]] [-L address] [-l login_name] [-m mac_spec] [-O ctl_cmd] [-o option] [-p port] [-Q query_option] [-R address] [-S ctl_path] [-W host:port] [-w local_tun[:remote_tun]] destination [command]"'
    parts = _parse_command_line(cmd)
    if not parts:
        return 'Write-Output "usage: ssh [-46AaCfGgKkMNnqsTtVvXxYy] [-B bind_interface] [-b bind_address] [-c cipher_spec] [-D [bind_address:]port] [-E log_file] [-e escape_char] [-F configfile] [-I pkcs11] [-i identity_file] [-J [user@]host[:port]] [-L address] [-l login_name] [-m mac_spec] [-O ctl_cmd] [-o option] [-p port] [-Q query_option] [-R address] [-S ctl_path] [-W host:port] [-w local_tun[:remote_tun]] destination [command]"'
    if parts[0] in ('ssh', '/usr/bin/ssh', '/bin/ssh'):
        parts = parts[1:]
    if not parts:
        return 'Write-Output "usage: ssh [-46AaCfGgKkMNnqsTtVvXxYy] [-B bind_interface] [-b bind_address] [-c cipher_spec] [-D [bind_address:]port] [-E log_file] [-e escape_char] [-F configfile] [-I pkcs11] [-i identity_file] [-J [user@]host[:port]] [-L address] [-l login_name] [-m mac_spec] [-O ctl_cmd] [-o option] [-p port] [-Q query_option] [-R address] [-S ctl_path] [-W host:port] [-w local_tun[:remote_tun]] destination [command]"'
    options: Dict[str, Any] = {
        'ipv4': False,
        'ipv6': False,
        'agent_forwarding': None,
        'batch_mode': False,
        'compression': False,
        'fork_background': False,
        'gateway_ports': False,
        'help': False,
        'quiet': False,
        'subsystem': False,
        'tty': None,
        'verbose': 0,
        'x11_forwarding': None,
        'version': False,
        'port': None,
        'identity_file': None,
        'login_name': None,
        'config_file': None,
        'cipher': None,
        'mac': None,
        'escape_char': None,
        'log_file': None,
        'bind_address': None,
        'bind_interface': None,
        'local_forward': [],
        'remote_forward': [],
        'dynamic_forward': None,
        'proxy_jump': None,
        'ssh_options': [],
        'protocol_version': None,
    }
    destination: Optional[str] = None
    remote_command: List[str] = []
    VALID_SHORT_OPTS = '46AaCfGgKkMNnqsTtVvXxYyBbcDeEfFhiIJlLmOoPpQRrSswW'
    VALID_LONG_OPTS = {
        'help', 'version', 'ipv4', 'ipv6', 'agent-forwarding', 'no-agent-forwarding',
        'batch-mode', 'compression', 'fork-background', 'gateway-ports',
        'quiet', 'subsystem', 'tty', 'no-tty', 'verbose', 'trusted-x11-forwarding',
        'x11-forwarding', 'no-x11-forwarding', 'port', 'identity', 'login', 'config',
        'cipher', 'mac', 'escape', 'log', 'bind', 'interface', 'local-forward',
        'remote-forward', 'dynamic-forward', 'proxy-jump', 'option', 'protocol'
    }
    i = 0
    while i < len(parts):
        part = parts[i]
        if part == '--':
            i += 1
            if i < len(parts):
                destination = parts[i]
                i += 1
            remote_command = parts[i:]
            break
        if part.startswith('/') and len(part) >= 2:
            opt_part = part[1:]
            if len(opt_part) == 1 and opt_part in VALID_SHORT_OPTS:
                part = '-' + opt_part
            elif opt_part in VALID_LONG_OPTS:
                part = '--' + opt_part
            elif '=' in opt_part:
                opt_name = opt_part.split('=', 1)[0]
                if opt_name in VALID_LONG_OPTS:
                    part = '--' + opt_part
            elif all(c in VALID_SHORT_OPTS for c in opt_part):
                part = '-' + opt_part
        if part.startswith('--'):
            long_opt = part[2:]
            if '=' in long_opt:
                opt_name, opt_value = long_opt.split('=', 1)
                if opt_name == 'port':
                    options['port'] = opt_value
                elif opt_name == 'identity':
                    options['identity_file'] = opt_value
                elif opt_name == 'login':
                    options['login_name'] = opt_value
                elif opt_name == 'config':
                    options['config_file'] = opt_value
                elif opt_name == 'cipher':
                    options['cipher'] = opt_value
                elif opt_name == 'mac':
                    options['mac'] = opt_value
                elif opt_name == 'escape':
                    options['escape_char'] = opt_value
                elif opt_name == 'log':
                    options['log_file'] = opt_value
                elif opt_name == 'bind':
                    options['bind_address'] = opt_value
                elif opt_name == 'interface':
                    options['bind_interface'] = opt_value
                elif opt_name == 'option':
                    options['ssh_options'].append(opt_value)
                elif opt_name == 'protocol':
                    options['protocol_version'] = opt_value
                i += 1
                continue
            if long_opt == 'help':
                options['help'] = True
                i += 1
                continue
            elif long_opt == 'version':
                options['version'] = True
                i += 1
                continue
            elif long_opt == 'ipv4':
                options['ipv4'] = True
                i += 1
                continue
            elif long_opt == 'ipv6':
                options['ipv6'] = True
                i += 1
                continue
            elif long_opt == 'agent-forwarding':
                options['agent_forwarding'] = True
                i += 1
                continue
            elif long_opt == 'no-agent-forwarding':
                options['agent_forwarding'] = False
                i += 1
                continue
            elif long_opt == 'batch-mode':
                options['batch_mode'] = True
                i += 1
                continue
            elif long_opt == 'compression':
                options['compression'] = True
                i += 1
                continue
            elif long_opt == 'fork-background':
                options['fork_background'] = True
                i += 1
                continue
            elif long_opt == 'gateway-ports':
                options['gateway_ports'] = True
                i += 1
                continue
            elif long_opt == 'quiet':
                options['quiet'] = True
                i += 1
                continue
            elif long_opt == 'subsystem':
                options['subsystem'] = True
                i += 1
                continue
            elif long_opt == 'tty':
                options['tty'] = True
                i += 1
                continue
            elif long_opt == 'no-tty':
                options['tty'] = False
                i += 1
                continue
            elif long_opt == 'verbose':
                options['verbose'] += 1
                i += 1
                continue
            elif long_opt == 'x11-forwarding':
                options['x11_forwarding'] = 'untrusted'
                i += 1
                continue
            elif long_opt == 'trusted-x11-forwarding':
                options['x11_forwarding'] = 'trusted'
                i += 1
                continue
            elif long_opt == 'no-x11-forwarding':
                options['x11_forwarding'] = False
                i += 1
                continue
            elif long_opt == 'port':
                if i + 1 < len(parts):
                    i += 1
                    options['port'] = parts[i]
                i += 1
                continue
            elif long_opt == 'identity':
                if i + 1 < len(parts):
                    i += 1
                    options['identity_file'] = parts[i]
                i += 1
                continue
            elif long_opt == 'login':
                if i + 1 < len(parts):
                    i += 1
                    options['login_name'] = parts[i]
                i += 1
                continue
            elif long_opt == 'config':
                if i + 1 < len(parts):
                    i += 1
                    options['config_file'] = parts[i]
                i += 1
                continue
            elif long_opt == 'cipher':
                if i + 1 < len(parts):
                    i += 1
                    options['cipher'] = parts[i]
                i += 1
                continue
            elif long_opt == 'mac':
                if i + 1 < len(parts):
                    i += 1
                    options['mac'] = parts[i]
                i += 1
                continue
            elif long_opt == 'escape':
                if i + 1 < len(parts):
                    i += 1
                    options['escape_char'] = parts[i]
                i += 1
                continue
            elif long_opt == 'log':
                if i + 1 < len(parts):
                    i += 1
                    options['log_file'] = parts[i]
                i += 1
                continue
            elif long_opt == 'bind':
                if i + 1 < len(parts):
                    i += 1
                    options['bind_address'] = parts[i]
                i += 1
                continue
            elif long_opt == 'interface':
                if i + 1 < len(parts):
                    i += 1
                    options['bind_interface'] = parts[i]
                i += 1
                continue
            elif long_opt == 'option':
                if i + 1 < len(parts):
                    i += 1
                    options['ssh_options'].append(parts[i])
                i += 1
                continue
            elif long_opt == 'local-forward':
                if i + 1 < len(parts):
                    i += 1
                    local_fwd = parts[i]
                    options['local_forward'].append(local_fwd)
                i += 1
                continue
            elif long_opt == 'remote-forward':
                if i + 1 < len(parts):
                    i += 1
                    remote_fwd = parts[i]
                    options['remote_forward'].append(remote_fwd)
                i += 1
                continue
            elif long_opt == 'dynamic-forward':
                if i + 1 < len(parts):
                    i += 1
                    options['dynamic_forward'] = parts[i]
                i += 1
                continue
            elif long_opt == 'proxy-jump':
                if i + 1 < len(parts):
                    i += 1
                    options['proxy_jump'] = parts[i]
                i += 1
                continue
            elif long_opt == 'protocol':
                if i + 1 < len(parts):
                    i += 1
                    options['protocol_version'] = parts[i]
                i += 1
                continue
            i += 1
            continue
        if part.startswith('-') and len(part) > 1:
            opt_chars = part[1:]
            j = 0
            while j < len(opt_chars):
                char = opt_chars[j]
                if char == '4':
                    options['ipv4'] = True
                    j += 1
                elif char == '6':
                    options['ipv6'] = True
                    j += 1
                elif char == 'A':
                    options['agent_forwarding'] = True
                    j += 1
                elif char == 'a':
                    options['agent_forwarding'] = False
                    j += 1
                elif char == 'C':
                    options['compression'] = True
                    j += 1
                elif char == 'f':
                    options['fork_background'] = True
                    j += 1
                elif char == 'g':
                    options['gateway_ports'] = True
                    j += 1
                elif char == 'G':
                    options['help'] = True
                    j += 1
                elif char == 'h':
                    options['help'] = True
                    j += 1
                elif char == 'K':
                    j += 1
                elif char == 'k':
                    j += 1
                elif char == 'M':
                    j += 1
                elif char == 'N':
                    j += 1
                elif char == 'n':
                    j += 1
                elif char == 'q':
                    options['quiet'] = True
                    j += 1
                elif char == 's':
                    options['subsystem'] = True
                    j += 1
                elif char == 'T':
                    options['tty'] = False
                    j += 1
                elif char == 't':
                    options['tty'] = True
                    j += 1
                elif char == 'V':
                    options['version'] = True
                    j += 1
                elif char == 'v':
                    options['verbose'] += 1
                    j += 1
                elif char == 'X':
                    options['x11_forwarding'] = 'untrusted'
                    j += 1
                elif char == 'x':
                    options['x11_forwarding'] = False
                    j += 1
                elif char == 'Y':
                    options['x11_forwarding'] = 'trusted'
                    j += 1
                elif char == 'y':
                    j += 1
                elif char == '1':
                    options['protocol_version'] = '1'
                    j += 1
                elif char == '2':
                    options['protocol_version'] = '2'
                    j += 1
                elif char == 'B':
                    if j + 1 < len(opt_chars):
                        options['bind_interface'] = opt_chars[j + 1:]
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                        options['bind_interface'] = parts[i]
                    j += 1
                elif char == 'b':
                    if j + 1 < len(opt_chars):
                        options['bind_address'] = opt_chars[j + 1:]
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                        options['bind_address'] = parts[i]
                    j += 1
                elif char == 'c':
                    if j + 1 < len(opt_chars):
                        options['cipher'] = opt_chars[j + 1:]
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                        options['cipher'] = parts[i]
                    j += 1
                elif char == 'D':
                    if j + 1 < len(opt_chars):
                        options['dynamic_forward'] = opt_chars[j + 1:]
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                        options['dynamic_forward'] = parts[i]
                    j += 1
                elif char == 'e':
                    if j + 1 < len(opt_chars):
                        options['escape_char'] = opt_chars[j + 1:]
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                        options['escape_char'] = parts[i]
                    j += 1
                elif char == 'E':
                    if j + 1 < len(opt_chars):
                        options['log_file'] = opt_chars[j + 1:]
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                        options['log_file'] = parts[i]
                    j += 1
                elif char == 'F':
                    if j + 1 < len(opt_chars):
                        options['config_file'] = opt_chars[j + 1:]
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                        options['config_file'] = parts[i]
                    j += 1
                elif char == 'I':
                    if j + 1 < len(opt_chars):
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                    j += 1
                elif char == 'i':
                    if j + 1 < len(opt_chars):
                        options['identity_file'] = opt_chars[j + 1:]
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                        options['identity_file'] = parts[i]
                    j += 1
                elif char == 'J':
                    if j + 1 < len(opt_chars):
                        options['proxy_jump'] = opt_chars[j + 1:]
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                        options['proxy_jump'] = parts[i]
                    j += 1
                elif char == 'L':
                    if j + 1 < len(opt_chars):
                        options['local_forward'].append(opt_chars[j + 1:])
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                        options['local_forward'].append(parts[i])
                    j += 1
                elif char == 'l':
                    if j + 1 < len(opt_chars):
                        options['login_name'] = opt_chars[j + 1:]
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                        options['login_name'] = parts[i]
                    j += 1
                elif char == 'm':
                    if j + 1 < len(opt_chars):
                        options['mac'] = opt_chars[j + 1:]
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                        options['mac'] = parts[i]
                    j += 1
                elif char == 'O':
                    if j + 1 < len(opt_chars):
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                    j += 1
                elif char == 'o':
                    if j + 1 < len(opt_chars):
                        options['ssh_options'].append(opt_chars[j + 1:])
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                        options['ssh_options'].append(parts[i])
                    j += 1
                elif char == 'P':
                    if j + 1 < len(opt_chars):
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                    j += 1
                elif char == 'p':
                    if j + 1 < len(opt_chars):
                        options['port'] = opt_chars[j + 1:]
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                        options['port'] = parts[i]
                    j += 1
                elif char == 'Q':
                    if j + 1 < len(opt_chars):
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                    j += 1
                elif char == 'R':
                    if j + 1 < len(opt_chars):
                        options['remote_forward'].append(opt_chars[j + 1:])
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                        options['remote_forward'].append(parts[i])
                    j += 1
                elif char == 'S':
                    if j + 1 < len(opt_chars):
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                    j += 1
                elif char == 'W':
                    if j + 1 < len(opt_chars):
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                    j += 1
                elif char == 'w':
                    if j + 1 < len(opt_chars):
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                    j += 1
                else:
                    j += 1
            i += 1
            continue
        if destination is None:
            destination = part
            i += 1
        else:
            remote_command = parts[i:]
            break
    if options['help']:
        return (
            'Write-Output "usage: ssh [-46AaCfGgKkMNnqsTtVvXxYy] [-B bind_interface] [-b bind_address] [-c cipher_spec] [-D [bind_address:]port] [-E log_file] [-e escape_char] [-F configfile] [-I pkcs11] [-i identity_file] [-J [user@]host[:port]] [-L address] [-l login_name] [-m mac_spec] [-O ctl_cmd] [-o option] [-p port] [-Q query_option] [-R address] [-S ctl_path] [-W host:port] [-w local_tun[:remote_tun]] destination [command]"'
        )
    if options['version']:
        return 'ssh -V'
    if destination is None:
        return 'Write-Output "usage: ssh [-46AaCfGgKkMNnqsTtVvXxYy] [-B bind_interface] [-b bind_address] [-c cipher_spec] [-D [bind_address:]port] [-E log_file] [-e escape_char] [-F configfile] [-I pkcs11] [-i identity_file] [-J [user@]host[:port]] [-L address] [-l login_name] [-m mac_spec] [-O ctl_cmd] [-o option] [-p port] [-Q query_option] [-R address] [-S ctl_path] [-W host:port] [-w local_tun[:remote_tun]] destination [command]"'
    ssh_args = []
    if options['ipv4']:
        ssh_args.append('-4')
    if options['ipv6']:
        ssh_args.append('-6')
    if options['agent_forwarding'] is True:
        ssh_args.append('-A')
    elif options['agent_forwarding'] is False:
        ssh_args.append('-a')
    if options['compression']:
        ssh_args.append('-C')
    if options['fork_background']:
        ssh_args.append('-f')
    if options['gateway_ports']:
        ssh_args.append('-g')
    if options['quiet']:
        ssh_args.append('-q')
    if options['subsystem']:
        ssh_args.append('-s')
    if options['tty'] is True:
        ssh_args.append('-t')
    elif options['tty'] is False:
        ssh_args.append('-T')
    if options['verbose'] > 0:
        ssh_args.extend(['-v'] * min(options['verbose'], 3))
    if options['x11_forwarding'] == 'trusted':
        ssh_args.append('-Y')
    elif options['x11_forwarding'] == 'untrusted':
        ssh_args.append('-X')
    elif options['x11_forwarding'] is False:
        ssh_args.append('-x')
    if options['protocol_version'] == '1':
        ssh_args.append('-1')
    elif options['protocol_version'] == '2':
        ssh_args.append('-2')
    if options['port']:
        ssh_args.append('-p')
        ssh_args.append(options['port'])
    if options['identity_file']:
        ssh_args.append('-i')
        ssh_args.append(options['identity_file'])
    if options['login_name']:
        ssh_args.append('-l')
        ssh_args.append(options['login_name'])
    if options['config_file']:
        ssh_args.append('-F')
        ssh_args.append(options['config_file'])
    if options['cipher']:
        ssh_args.append('-c')
        ssh_args.append(options['cipher'])
    if options['mac']:
        ssh_args.append('-m')
        ssh_args.append(options['mac'])
    if options['escape_char']:
        ssh_args.append('-e')
        ssh_args.append(options['escape_char'])
    if options['log_file']:
        ssh_args.append('-E')
        ssh_args.append(options['log_file'])
    if options['bind_address']:
        ssh_args.append('-b')
        ssh_args.append(options['bind_address'])
    if options['bind_interface']:
        ssh_args.append('-B')
        ssh_args.append(options['bind_interface'])
    if options['proxy_jump']:
        ssh_args.append('-J')
        ssh_args.append(options['proxy_jump'])
    if options['dynamic_forward']:
        ssh_args.append('-D')
        ssh_args.append(options['dynamic_forward'])
    for fwd in options['local_forward']:
        ssh_args.append('-L')
        ssh_args.append(fwd)
    for fwd in options['remote_forward']:
        ssh_args.append('-R')
        ssh_args.append(fwd)
    for opt in options['ssh_options']:
        ssh_args.append('-o')
        ssh_args.append(opt)
    ssh_args.append(destination)
    if remote_command:
        cmd_str = ' '.join(remote_command)
        if ' ' in cmd_str and not (cmd_str.startswith('"') or cmd_str.startswith("'")):
            cmd_str = f'"{cmd_str}"'
        ssh_args.append(cmd_str)
    cmd_str = 'ssh ' + ' '.join(ssh_args)
    return cmd_str
if __name__ == "__main__":
    test_cases = [
        "ssh user@host",
        "ssh host",
        "ssh -p 2222 user@host",
        "ssh -p2222 user@host",
        "ssh --port 2222 user@host",
        "ssh --port=2222 user@host",
        "ssh -i ~/.ssh/id_rsa user@host",
        "ssh -i~/.ssh/id_rsa user@host",
        "ssh -v -C user@host",
        "ssh -vvv user@host",
        "ssh -4 -C -p 2222 user@host",
        "ssh -X user@host",
        "ssh -Y user@host",
        "ssh -x user@host",
        "ssh user@host 'ls -la'",
        "ssh user@host ls -la",
        "ssh -L 8080:localhost:80 user@host",
        "ssh -R 9090:localhost:3000 user@host",
        "ssh -D 1080 user@host",
        "ssh -l username host",
        "ssh -F /path/to/config user@host",
        "ssh -t user@host",
        "ssh -T user@host",
        "ssh -o StrictHostKeyChecking=no user@host",
        "ssh -oServerAliveInterval=60 user@host",
        "ssh /p 2222 user@host",
        "ssh /v user@host",
        "ssh /4 /C user@host",
        "ssh /i ~/.ssh/id_rsa user@host",
        "ssh /L 8080:localhost:80 user@host",
        "ssh -i ~/.ssh/id_rsa -p 2222 -l admin host.example.com",
        "ssh -A -C -X user@host 'echo hello'",
        "",
        "ssh",
    ]
    for test in test_cases:
        result = _convert_ssh(test)
        print(f"Input:  {test}")
        print(f"Output: {result}")
        print()
def _convert_tail(cmd: str) -> str:
    parts = cmd.split()
    num_lines = 10
    file_path = None
    follow_mode = False
    i = 1
    while i < len(parts):
        part = parts[i]
        if part == '-f':
            follow_mode = True
        elif part.startswith('-n'):
            if len(part) > 2:
                num_lines = int(part[2:])
            elif i + 1 < len(parts):
                num_lines = int(parts[i + 1])
                i += 1
        elif part.startswith('-') and part[1:].isdigit():
            num_lines = int(part[1:])
        elif not part.startswith('-'):
            file_path = part
        i += 1
    if file_path:
        if follow_mode:
            return f'Get-Content {file_path} -Tail {num_lines} -Wait'
        else:
            return f'Get-Content {file_path} -Tail {num_lines}'
    else:
        return f'Select-Object -Last {num_lines}'
def _parse_size(size_str: str) -> int:
    size_str = size_str.strip()
    if not size_str:
        return 0
    multiplier = 1
    if size_str.startswith('-'):
        multiplier = -1
        size_str = size_str[1:]
    match = re.match(r'^(\d+)([KMGTPEZY]?)', size_str, re.IGNORECASE)
    if not match:
        return 0
    num = int(match.group(1))
    suffix = match.group(2).upper()
    suffix_multipliers = {
        '': 1,
        'K': 1024,
        'M': 1024 ** 2,
        'G': 1024 ** 3,
        'T': 1024 ** 4,
        'P': 1024 ** 5,
        'E': 1024 ** 6,
        'Z': 1024 ** 7,
        'Y': 1024 ** 8,
    }
    return num * suffix_multipliers.get(suffix, 1) * multiplier
if __name__ == "__main__":
    test_cases = [
        "tail file.txt",
        "tail -n 20 file.txt",
        "tail -20 file.txt",
        "tail -c 100 file.txt",
        "tail -f file.txt",
        "tail -n 5 /var/log/syslog",
        "tail --lines=50 file.txt",
        "tail /n 15 file.txt",
        "tail -q file.txt",
        "tail -v file.txt",
        "tail file1.txt file2.txt",
        "tail -F log.txt",
        "tail --bytes=1K file.txt",
        "tail -c 1M file.txt",
    ]
    for test in test_cases:
        result = _convert_tail(test)
        print(f"Input:  {test}")
        print(f"Output: {result}")
        print()
def _convert_tar(cmd: str) -> str:
    if not cmd or not cmd.strip():
        return 'Write-Output "tar: You must specify one of the -Acdtrux options"'
    parts = _parse_command_line(cmd)
    if not parts:
        return 'Write-Output "tar: You must specify one of the -Acdtrux options"'
    if parts[0] in ('tar', '/bin/tar', '/usr/bin/tar'):
        parts = parts[1:]
    if not parts:
        return 'Write-Output "tar: You must specify one of the -Acdtrux options"'
    create = False
    extract = False
    list_contents = False
    append = False
    update = False
    diff = False
    catenate = False
    delete = False
    archive_file: Optional[str] = None
    verbose = False
    gzip = False
    bzip2 = False
    xz = False
    directory: Optional[str] = None
    preserve_permissions = False
    numeric_owner = False
    owner: Optional[str] = None
    group: Optional[str] = None
    touch = False
    keep_old_files = False
    keep_newer_files = False
    overwrite = False
    unlink_first = False
    interactive = False
    no_same_owner = False
    no_same_permissions = False
    dereference = False
    hard_dereference = False
    absolute_names = False
    strip_components: Optional[int] = None
    transform: Optional[str] = None
    files_from: Optional[str] = None
    exclude_from: Optional[str] = None
    exclude_patterns: List[str] = []
    exclude_backups = False
    exclude_caches = False
    exclude_caches_all = False
    exclude_caches_under = False
    exclude_tags: List[str] = []
    exclude_ignore: Optional[str] = None
    exclude_ignore_recursive: Optional[str] = None
    anchored: Optional[bool] = None
    ignore_case: Optional[bool] = None
    wildcards: Optional[bool] = None
    wildcards_match_slash: Optional[bool] = None
    show_help = False
    show_version = False
    VALID_SHORT_OPTS = 'AcdefhijkmoprstuvwxzACfTUX'
    VALID_LONG_OPTS = {
        'create', 'extract', 'get', 'list', 'append', 'update', 'diff', 'compare',
        'catenate', 'concatenate', 'delete', 'file', 'verbose', 'gzip', 'gunzip',
        'ungzip', 'bzip2', 'xz', 'directory', 'preserve-permissions', 'same-permissions',
        'numeric-owner', 'owner', 'group', 'touch', 'keep-old-files', 'keep-newer-files',
        'overwrite', 'unlink-first', 'interactive', 'no-same-owner', 'no-same-permissions',
        'dereference', 'hard-dereference', 'absolute-names', 'strip-components',
        'transform', 'xform', 'files-from', 'exclude-from', 'exclude', 'exclude-backups',
        'exclude-caches', 'exclude-caches-all', 'exclude-caches-under', 'exclude-tag',
        'exclude-ignore', 'exclude-ignore-recursive', 'anchored', 'no-anchored',
        'ignore-case', 'no-ignore-case', 'wildcards', 'no-wildcards',
        'wildcards-match-slash', 'no-wildcards-match-slash', 'help', 'version'
    }
    i = 0
    while i < len(parts):
        part = parts[i]
        if part == '--':
            i += 1
            break
        if part.startswith('/') and len(part) >= 2:
            opt_part = part[1:]
            if len(opt_part) == 1 and opt_part in VALID_SHORT_OPTS:
                part = '-' + opt_part
            elif opt_part in VALID_LONG_OPTS:
                part = '--' + opt_part
            elif '=' in opt_part:
                opt_name = opt_part.split('=', 1)[0]
                if opt_name in VALID_LONG_OPTS:
                    part = '--' + opt_part
            elif all(c in VALID_SHORT_OPTS for c in opt_part):
                part = '-' + opt_part
            elif opt_part.startswith('exclude=') or opt_part.startswith('owner=') or \
                 opt_part.startswith('group=') or opt_part.startswith('file=') or \
                 opt_part.startswith('directory=') or opt_part.startswith('strip-components=') or \
                 opt_part.startswith('transform=') or opt_part.startswith('xform=') or \
                 opt_part.startswith('files-from=') or opt_part.startswith('exclude-from=') or \
                 opt_part.startswith('exclude-tag=') or opt_part.startswith('exclude-ignore=') or \
                 opt_part.startswith('exclude-ignore-recursive='):
                part = '--' + opt_part
        if part.startswith('--'):
            long_opt = part[2:]
            if '=' in long_opt:
                opt_name, opt_value = long_opt.split('=', 1)
                if opt_name == 'file':
                    archive_file = opt_value
                elif opt_name == 'directory':
                    directory = opt_value
                elif opt_name == 'owner':
                    owner = opt_value
                elif opt_name == 'group':
                    group = opt_value
                elif opt_name == 'strip-components':
                    try:
                        strip_components = int(opt_value)
                    except ValueError:
                        pass
                elif opt_name == 'transform' or opt_name == 'xform':
                    transform = opt_value
                elif opt_name == 'files-from':
                    files_from = opt_value
                elif opt_name == 'exclude-from':
                    exclude_from = opt_value
                elif opt_name == 'exclude':
                    exclude_patterns.append(opt_value)
                elif opt_name == 'exclude-tag':
                    exclude_tags.append(opt_value)
                elif opt_name == 'exclude-ignore':
                    exclude_ignore = opt_value
                elif opt_name == 'exclude-ignore-recursive':
                    exclude_ignore_recursive = opt_value
                i += 1
                continue
            if long_opt == 'help':
                show_help = True
                i += 1
                continue
            elif long_opt == 'version':
                show_version = True
                i += 1
                continue
            elif long_opt == 'create':
                create = True
                i += 1
                continue
            elif long_opt in ('extract', 'get'):
                extract = True
                i += 1
                continue
            elif long_opt == 'list':
                list_contents = True
                i += 1
                continue
            elif long_opt == 'append':
                append = True
                i += 1
                continue
            elif long_opt == 'update':
                update = True
                i += 1
                continue
            elif long_opt in ('diff', 'compare'):
                diff = True
                i += 1
                continue
            elif long_opt in ('catenate', 'concatenate'):
                catenate = True
                i += 1
                continue
            elif long_opt == 'delete':
                delete = True
                i += 1
                continue
            elif long_opt == 'verbose':
                verbose = True
                i += 1
                continue
            elif long_opt in ('gzip', 'gunzip', 'ungzip'):
                gzip = True
                i += 1
                continue
            elif long_opt == 'bzip2':
                bzip2 = True
                i += 1
                continue
            elif long_opt == 'xz':
                xz = True
                i += 1
                continue
            elif long_opt == 'preserve-permissions' or long_opt == 'same-permissions':
                preserve_permissions = True
                i += 1
                continue
            elif long_opt == 'numeric-owner':
                numeric_owner = True
                i += 1
                continue
            elif long_opt == 'touch':
                touch = True
                i += 1
                continue
            elif long_opt == 'keep-old-files':
                keep_old_files = True
                i += 1
                continue
            elif long_opt == 'keep-newer-files':
                keep_newer_files = True
                i += 1
                continue
            elif long_opt == 'overwrite':
                overwrite = True
                i += 1
                continue
            elif long_opt == 'unlink-first':
                unlink_first = True
                i += 1
                continue
            elif long_opt == 'interactive':
                interactive = True
                i += 1
                continue
            elif long_opt == 'no-same-owner':
                no_same_owner = True
                i += 1
                continue
            elif long_opt == 'no-same-permissions':
                no_same_permissions = True
                i += 1
                continue
            elif long_opt == 'dereference':
                dereference = True
                i += 1
                continue
            elif long_opt == 'hard-dereference':
                hard_dereference = True
                i += 1
                continue
            elif long_opt == 'absolute-names':
                absolute_names = True
                i += 1
                continue
            elif long_opt == 'exclude-backups':
                exclude_backups = True
                i += 1
                continue
            elif long_opt == 'exclude-caches':
                exclude_caches = True
                i += 1
                continue
            elif long_opt == 'exclude-caches-all':
                exclude_caches_all = True
                i += 1
                continue
            elif long_opt == 'exclude-caches-under':
                exclude_caches_under = True
                i += 1
                continue
            elif long_opt == 'anchored':
                anchored = True
                i += 1
                continue
            elif long_opt == 'no-anchored':
                anchored = False
                i += 1
                continue
            elif long_opt == 'ignore-case':
                ignore_case = True
                i += 1
                continue
            elif long_opt == 'no-ignore-case':
                ignore_case = False
                i += 1
                continue
            elif long_opt == 'wildcards':
                wildcards = True
                i += 1
                continue
            elif long_opt == 'no-wildcards':
                wildcards = False
                i += 1
                continue
            elif long_opt == 'wildcards-match-slash':
                wildcards_match_slash = True
                i += 1
                continue
            elif long_opt == 'no-wildcards-match-slash':
                wildcards_match_slash = False
                i += 1
                continue
            elif long_opt == 'file':
                if i + 1 < len(parts):
                    i += 1
                    archive_file = parts[i]
                i += 1
                continue
            elif long_opt == 'directory':
                if i + 1 < len(parts):
                    i += 1
                    directory = parts[i]
                i += 1
                continue
            elif long_opt == 'owner':
                if i + 1 < len(parts):
                    i += 1
                    owner = parts[i]
                i += 1
                continue
            elif long_opt == 'group':
                if i + 1 < len(parts):
                    i += 1
                    group = parts[i]
                i += 1
                continue
            elif long_opt == 'strip-components':
                if i + 1 < len(parts):
                    i += 1
                    try:
                        strip_components = int(parts[i])
                    except ValueError:
                        pass
                i += 1
                continue
            elif long_opt in ('transform', 'xform'):
                if i + 1 < len(parts):
                    i += 1
                    transform = parts[i]
                i += 1
                continue
            elif long_opt == 'files-from':
                if i + 1 < len(parts):
                    i += 1
                    files_from = parts[i]
                i += 1
                continue
            elif long_opt == 'exclude-from':
                if i + 1 < len(parts):
                    i += 1
                    exclude_from = parts[i]
                i += 1
                continue
            elif long_opt == 'exclude':
                if i + 1 < len(parts):
                    i += 1
                    exclude_patterns.append(parts[i])
                i += 1
                continue
            elif long_opt == 'exclude-tag':
                if i + 1 < len(parts):
                    i += 1
                    exclude_tags.append(parts[i])
                i += 1
                continue
            elif long_opt == 'exclude-ignore':
                if i + 1 < len(parts):
                    i += 1
                    exclude_ignore = parts[i]
                i += 1
                continue
            elif long_opt == 'exclude-ignore-recursive':
                if i + 1 < len(parts):
                    i += 1
                    exclude_ignore_recursive = parts[i]
                i += 1
                continue
            i += 1
            continue
        if part.startswith('-') and len(part) > 1:
            opt_chars = part[1:]
            j = 0
            while j < len(opt_chars):
                char = opt_chars[j]
                if char == 'c':
                    create = True
                    j += 1
                elif char == 'x':
                    extract = True
                    j += 1
                elif char == 't':
                    list_contents = True
                    j += 1
                elif char == 'r':
                    append = True
                    j += 1
                elif char == 'u':
                    update = True
                    j += 1
                elif char == 'd':
                    diff = True
                    j += 1
                elif char == 'A':
                    catenate = True
                    j += 1
                elif char == 'v':
                    verbose = True
                    j += 1
                elif char == 'z':
                    gzip = True
                    j += 1
                elif char == 'j':
                    bzip2 = True
                    j += 1
                elif char == 'J':
                    xz = True
                    j += 1
                elif char == 'f':
                    if j + 1 < len(opt_chars):
                        archive_file = opt_chars[j + 1:]
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                        archive_file = parts[i]
                    j += 1
                elif char == 'C':
                    if j + 1 < len(opt_chars):
                        directory = opt_chars[j + 1:]
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                        directory = parts[i]
                    j += 1
                elif char == 'p':
                    preserve_permissions = True
                    j += 1
                elif char == 'm':
                    touch = True
                    j += 1
                elif char == 'k':
                    keep_old_files = True
                    j += 1
                elif char == 'w':
                    interactive = True
                    j += 1
                elif char == 'o':
                    no_same_owner = True
                    j += 1
                elif char == 'h':
                    dereference = True
                    j += 1
                elif char == 'P':
                    absolute_names = True
                    j += 1
                elif char == 'T':
                    if j + 1 < len(opt_chars):
                        files_from = opt_chars[j + 1:]
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                        files_from = parts[i]
                    j += 1
                elif char == 'X':
                    if j + 1 < len(opt_chars):
                        exclude_from = opt_chars[j + 1:]
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                        exclude_from = parts[i]
                    j += 1
                elif char == '-':
                    j += 1
                    i += 1
                    break
                else:
                    j += 1
            i += 1
            continue
        break
    if show_help:
        return (
            'Write-Output "Usage: tar [OPTION]... [FILE]...\n'
            'GNU tar is an archiver that creates and manipulates archive files.\n'
            '\n'
            'Main operation mode:\n'
            '  -c, --create               create a new archive\n'
            '  -r, --append               append files to the end of an archive\n'
            '  -t, --list                 list the contents of an archive\n'
            '  -u, --update               only append files newer than copy in archive\n'
            '  -x, --extract, --get       extract files from an archive\n'
            '  -d, --diff, --compare      find differences between archive and file system\n'
            '  -A, --catenate, --concatenate   append tar files to an archive\n'
            '      --delete               delete from the archive\n'
            '\n'
            'Operation modifiers:\n'
            '  -f, --file=ARCHIVE         use archive file\n'
            '  -C, --directory=DIR        change to directory DIR\n'
            '  -v, --verbose              verbosely list files processed\n'
            '\n'
            'Compression options:\n'
            '  -z, --gzip                 filter through gzip\n'
            '  -j, --bzip2                filter through bzip2\n'
            '  -J, --xz                   filter through xz"'
        )
    if show_version:
        return 'Write-Output "tar (GNU tar) 1.34"'
    remaining = parts[i:]
    tar_args = []
    if create:
        tar_args.append('-c')
    elif extract:
        tar_args.append('-x')
    elif list_contents:
        tar_args.append('-t')
    elif append:
        tar_args.append('-r')
    elif update:
        tar_args.append('-u')
    elif diff:
        tar_args.append('-d')
    elif catenate:
        tar_args.append('-A')
    elif delete:
        tar_args.append('--delete')
    if gzip:
        tar_args.append('-z')
    elif bzip2:
        tar_args.append('-j')
    elif xz:
        tar_args.append('-J')
    if verbose:
        tar_args.append('-v')
    if preserve_permissions:
        tar_args.append('-p')
    if touch:
        tar_args.append('-m')
    if keep_old_files:
        tar_args.append('-k')
    if interactive:
        tar_args.append('-w')
    if no_same_owner:
        tar_args.append('-o')
    if dereference:
        tar_args.append('-h')
    if absolute_names:
        tar_args.append('-P')
    if archive_file:
        tar_args.append('-f')
        tar_args.append(archive_file)
    if directory:
        tar_args.append('-C')
        tar_args.append(directory)
    if remaining:
        tar_args.extend(remaining)
    cmd_str = 'tar ' + ' '.join(tar_args)
    return cmd_str
def _convert_tee(cmd: str) -> str:
    if not cmd or not cmd.strip():
        return 'Tee-Object'
    parts = _parse_command_line(cmd)
    if not parts:
        return 'Tee-Object'
    if parts[0] in ('tee', '/bin/tee', '/usr/bin/tee'):
        parts = parts[1:]
    if not parts:
        return 'Tee-Object'
    append = False
    ignore_interrupts = False
    pipe_mode = False
    output_error_mode: Optional[str] = None
    show_help = False
    show_version = False
    files: List[str] = []
    i = 0
    while i < len(parts):
        part = parts[i]
        if part == '--':
            files.extend(parts[i + 1:])
            break
        if part.startswith('/') and len(part) >= 2 and part[1].isalpha():
            sub_part = part[1:]
            if len(part) == 2:
                part = '-' + part[1:]
            elif '=' in sub_part:
                part = '--' + sub_part
            elif sub_part in ('append', 'ignore-interrupts', 'help', 'version', 'output-error'):
                part = '--' + sub_part
            elif all(c.isalpha() and c.islower() for c in sub_part) and len(sub_part) <= 3:
                part = '-' + sub_part
        if part.startswith('--'):
            long_opt = part[2:]
            if long_opt == 'help':
                show_help = True
                i += 1
                continue
            if long_opt == 'version':
                show_version = True
                i += 1
                continue
            if long_opt == 'append':
                append = True
                i += 1
                continue
            if long_opt == 'ignore-interrupts':
                ignore_interrupts = True
                i += 1
                continue
            if long_opt.startswith('output-error='):
                output_error_mode = long_opt.split('=', 1)[1]
                i += 1
                continue
            elif long_opt == 'output-error':
                if i + 1 < len(parts) and not parts[i + 1].startswith('-'):
                    i += 1
                    output_error_mode = parts[i]
                i += 1
                continue
            i += 1
            continue
        if part.startswith('-') and len(part) > 1:
            opt_chars = part[1:]
            j = 0
            while j < len(opt_chars):
                char = opt_chars[j]
                if char == 'a':
                    append = True
                    j += 1
                elif char == 'i':
                    ignore_interrupts = True
                    j += 1
                elif char == 'p':
                    pipe_mode = True
                    j += 1
                else:
                    j += 1
            i += 1
            continue
        files.append(part)
        i += 1
    return _build_tee_powershell_command(
        append, ignore_interrupts, pipe_mode, output_error_mode,
        show_help, show_version, files
    )
def _build_tee_powershell_command(
    append: bool,
    ignore_interrupts: bool,
    pipe_mode: bool,
    output_error_mode: Optional[str],
    show_help: bool,
    show_version: bool,
    files: List[str]
) -> str:
    if show_help:
        return ('Write-Output "tee - Read from standard input and write to standard output and files\n'
                'Usage: tee [OPTION]... [FILE]...\n'
                'Options:\n'
                '  -a, --append              Append to the given FILEs, do not overwrite\n'
                '  -i, --ignore-interrupts   Ignore interrupt signals\n'
                '  -p                        Operate in a more appropriate MODE with pipes\n'
                '      --output-error[=MODE] Set behavior on write error\n'
                '      --help                Display this help and exit\n'
                '      --version             Output version information and exit\n'
                '\n'
                'MODE determines behavior with write errors on the outputs:\n'
                '  warn         Diagnose errors writing to any output\n'
                '  warn-nopipe  Diagnose errors writing to any output not a pipe\n'
                '  exit         Exit on error writing to any output\n'
                '  exit-nopipe  Exit on error writing to any output not a pipe"')
    if show_version:
        return 'Write-Output "tee (GNU coreutils) 8.32"'
    notes: List[str] = []
    if ignore_interrupts:
        notes.append('# NOTE: -i (ignore-interrupts) not directly supported in PowerShell')
    if pipe_mode:
        notes.append('# NOTE: -p (pipe mode) not directly supported in PowerShell')
    if output_error_mode:
        notes.append(f'# NOTE: --output-error={output_error_mode} not directly supported in PowerShell')
    if not files:
        return '$input'
    quoted_files: List[str] = []
    for f in files:
        if ' ' in f and not (f.startswith('"') or f.startswith("'")):
            quoted_files.append(f'"{f}"')
        else:
            quoted_files.append(f)
    if len(quoted_files) == 1:
        append_flag = ' -Append' if append else ''
        cmd = f'Tee-Object -FilePath {quoted_files[0]}{append_flag}'
    else:
        commands: List[str] = []
        for idx, f in enumerate(quoted_files):
            append_flag = ' -Append' if append else ''
            commands.append(f'Tee-Object -FilePath {f}{append_flag}')
        cmd = '$input | ' + ' | '.join(commands)
    if notes:
        cmd += '  ' + ' '.join(notes)
    return cmd
if __name__ == "__main__":
    test_cases = [
        "tee output.txt",
        "tee -a output.txt",
        "tee --append output.txt",
        "tee file1.txt file2.txt",
        "tee -a file1.txt file2.txt",
        "tee -i file.txt",
        "tee -p file.txt",
        "tee --ignore-interrupts file.txt",
        "tee --output-error=warn file.txt",
        "tee --help",
        "tee --version",
        "tee /a output.txt",
        "tee /append output.txt",
        "tee",
        "tee -a",
    ]
    for test in test_cases:
        result = _convert_tee(test)
        print(f"Input:  {test}")
        print(f"Output: {result}")
        print()
def _convert_time(cmd: str) -> str:
    if not cmd or not cmd.strip():
        return 'Measure-Command { }'
    parts = _parse_command_line(cmd)
    if not parts:
        return 'Measure-Command { }'
    if parts[0] in ('time', '/usr/bin/time', '/bin/time'):
        parts = parts[1:]
    if not parts:
        return 'Measure-Command { }'
    portability = False
    format_string: Optional[str] = None
    output_file: Optional[str] = None
    append_mode = False
    verbose = False
    quiet = False
    show_help = False
    show_version = False
    command_parts: List[str] = []
    i = 0
    while i < len(parts):
        part = parts[i]
        if part == '--':
            command_parts.extend(parts[i + 1:])
            break
        if part.startswith('/') and len(part) >= 2 and part[1].isalpha():
            if len(part) == 2:
                part = '-' + part[1:]
            elif len(part) > 2:
                sub_part = part[1:]
                if '=' in sub_part:
                    part = '--' + sub_part
                elif sub_part in ('portability', 'format', 'output', 'append',
                                  'verbose', 'quiet', 'help', 'version'):
                    part = '--' + sub_part
                elif all(c.isalpha() and c.islower() for c in sub_part) and len(sub_part) <= 3:
                    part = '-' + sub_part
        if part.startswith('--'):
            long_opt = part[2:]
            if '=' in long_opt:
                opt_name, opt_value = long_opt.split('=', 1)
                if opt_name == 'format':
                    format_string = opt_value
                elif opt_name == 'output':
                    output_file = opt_value
                i += 1
                continue
            if long_opt == 'help':
                show_help = True
                i += 1
                continue
            elif long_opt == 'version':
                show_version = True
                i += 1
                continue
            elif long_opt == 'portability':
                portability = True
                i += 1
                continue
            elif long_opt == 'append':
                append_mode = True
                i += 1
                continue
            elif long_opt == 'verbose':
                verbose = True
                i += 1
                continue
            elif long_opt == 'quiet':
                quiet = True
                i += 1
                continue
            elif long_opt == 'format':
                if i + 1 < len(parts):
                    i += 1
                    format_string = parts[i]
                i += 1
                continue
            elif long_opt == 'output':
                if i + 1 < len(parts):
                    i += 1
                    output_file = parts[i]
                i += 1
                continue
            i += 1
            continue
        if part.startswith('-') and len(part) > 1:
            opt_chars = part[1:]
            j = 0
            while j < len(opt_chars):
                char = opt_chars[j]
                if char == 'p':
                    portability = True
                    j += 1
                elif char == 'a':
                    append_mode = True
                    j += 1
                elif char == 'v':
                    verbose = True
                    j += 1
                elif char == 'q':
                    quiet = True
                    j += 1
                elif char == 'V':
                    show_version = True
                    j += 1
                elif char == 'f':
                    if j + 1 < len(opt_chars):
                        format_string = opt_chars[j + 1:]
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                        format_string = parts[i]
                    j += 1
                elif char == 'o':
                    if j + 1 < len(opt_chars):
                        output_file = opt_chars[j + 1:]
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                        output_file = parts[i]
                    j += 1
                else:
                    j += 1
            i += 1
            continue
        command_parts.append(part)
        i += 1
    if show_help:
        return (
            'Write-Output "Usage: time [OPTION...] COMMAND [ARGUMENTS...]\n'
            'Run COMMAND, then print resource usage statistics.\n\n'
            'Options:\n'
            '  -f FORMAT, --format=FORMAT   use FORMAT as the output format\n'
            '  -p, --portability            use POSIX output format\n'
            '  -o FILE, --output=FILE       write resource usage to FILE\n'
            '  -a, --append                 append (instead of overwrite) the output\n'
            '  -v, --verbose                give very verbose output\n'
            '  -q, --quiet                  don\'t report abnormal program termination\n'
            '      --help                   display this help and exit\n'
            '  -V, --version                output version information and exit\n\n'
            'FORMAT is a printf-like string with specifiers like:\n'
            '  %E  elapsed real time, %e  elapsed real time in seconds\n'
            '  %U  user CPU time, %S  system CPU time, %P  percentage of CPU\n'
            '  %M  maximum resident set size, %t  average resident set size\n'
            '  %I  filesystem inputs, %O  filesystem outputs, etc."'
        )
    if show_version:
        return 'Write-Output "time (GNU time) 1.9"'
    if command_parts:
        command_str = ' '.join(command_parts)
    else:
        command_str = ''
    base_cmd = f'Measure-Command {{ {command_str} }}'
    output_redirect = ''
    if output_file:
        escaped_file = output_file.replace("'", "''")
        if append_mode:
            output_redirect = f' | ForEach-Object {{ $formatted = $_; $formatted | Out-String | Add-Content -Path "{escaped_file}" -NoNewline; $formatted }}'
        else:
            output_redirect = f' | ForEach-Object {{ $formatted = $_; $formatted | Out-String | Set-Content -Path "{escaped_file}" -NoNewline; $formatted }}'
    if format_string:
        ps_format = _convert_format_string(format_string)
        if output_redirect:
            return f'{base_cmd}{output_redirect}'
        else:
            return f'{base_cmd} | Select-Object @{ps_format}'
    elif portability:
        if output_redirect:
            return f'{base_cmd}{output_redirect}'
        else:
            return (
                f'{base_cmd} | Select-Object '
                f'@{{Name="real"; Expression={{$_.TotalSeconds}}}}, '
                f'@{{Name="user"; Expression={{$_.UserProcessorTime.TotalSeconds}}}}, '
                f'@{{Name="sys"; Expression={{$_.SystemProcessorTime.TotalSeconds}}}}'
            )
    elif verbose:
        if output_redirect:
            return f'{base_cmd}{output_redirect}'
        else:
            return (
                f'{base_cmd} | Select-Object '
                f'TotalSeconds, '
                f'UserProcessorTime, '
                f'SystemProcessorTime, '
                f'TotalProcessorTime, '
                f'Days, Hours, Minutes, Seconds, Milliseconds'
            )
    else:
        if output_redirect:
            return f'{base_cmd}{output_redirect}'
        else:
            return (
                f'{base_cmd} | Select-Object '
                f'TotalSeconds, '
                f'UserProcessorTime, '
                f'SystemProcessorTime'
            )
def _convert_format_string(fmt: str) -> str:
    format_mapping = {
        '%E': '$_.TotalSeconds',
        '%e': '$_.TotalSeconds',
        '%S': '$_.SystemProcessorTime.TotalSeconds',
        '%U': '$_.UserProcessorTime.TotalSeconds',
        '%P': '($_.TotalProcessorTime.TotalSeconds / $_.TotalSeconds * 100)',
    }
    return (
        'Name="Formatted"; '
        'Expression={'
        '$fmt = "' + fmt.replace('"', '`"') + '"; '
        '$result = $fmt; '
        '$result = $result -replace "%E", [string]::Format("{0:F3}", $_.TotalSeconds); '
        '$result = $result -replace "%e", [string]::Format("{0:F3}", $_.TotalSeconds); '
        '$result = $result -replace "%S", [string]::Format("{0:F3}", $_.SystemProcessorTime.TotalSeconds); '
        '$result = $result -replace "%U", [string]::Format("{0:F3}", $_.UserProcessorTime.TotalSeconds); '
        '$result = $result -replace "%P", [string]::Format("{0:F1}", ($_.TotalProcessorTime.TotalSeconds / [math]::Max($_.TotalSeconds, 0.001) * 100)); '
        '$result = $result -replace "%%", "%"; '
        '$result'
        '}'
    )
def _convert_slash_to_dash(arg: str) -> str:
    if not arg.startswith('/') or len(arg) < 2:
        return arg
    if arg[1].isalpha():
        if len(arg) == 2:
            return '-' + arg[1:]
        else:
            return '--' + arg[1:]
    return arg
def _expand_posix_class(char_class: str) -> str:
    class_map = {
        '[:alnum:]': 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789',
        '[:alpha:]': 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ',
        '[:blank:]': ' \t',
        '[:cntrl:]': ''.join(chr(i) for i in range(32)) + '\x7f',
        '[:digit:]': '0123456789',
        '[:graph:]': ''.join(chr(i) for i in range(33, 127)),
        '[:lower:]': 'abcdefghijklmnopqrstuvwxyz',
        '[:print:]': ''.join(chr(i) for i in range(32, 127)),
        '[:punct:]': '!"#$%&\'()*+,-./:;<=>?@[\\]^_`{|}~',
        '[:space:]': ' \t\n\r\x0b\x0c',
        '[:upper:]': 'ABCDEFGHIJKLMNOPQRSTUVWXYZ',
        '[:xdigit:]': '0123456789abcdefABCDEF',
    }
    return class_map.get(char_class, char_class)
def _expand_ranges(set_str: str) -> str:
    result = []
    i = 0
    while i < len(set_str):
        if i + 2 < len(set_str) and set_str[i:i+2] == '[:':
            end_idx = set_str.find(':]', i + 2)
            if end_idx != -1:
                class_name = set_str[i:end_idx+2]
                expanded = _expand_posix_class(class_name)
                result.append(expanded)
                i = end_idx + 2
                continue
        if set_str[i] == '\\' and i + 1 < len(set_str):
            next_char = set_str[i + 1]
            escape_map = {
                'n': '\n',
                't': '\t',
                'r': '\r',
                '\\': '\\',
                'a': '\x07',
                'b': '\x08',
                'f': '\x0c',
                'v': '\x0b',
            }
            if next_char in escape_map:
                result.append(escape_map[next_char])
            else:
                result.append(next_char)
            i += 2
            continue
        if i + 2 < len(set_str) and set_str[i + 1] == '-':
            start = set_str[i]
            end = set_str[i + 2]
            if (start.islower() and end.islower() and start <= end) or \
               (start.isupper() and end.isupper() and start <= end) or \
               (start.isdigit() and end.isdigit() and start <= end):
                result.append(''.join(chr(c) for c in range(ord(start), ord(end) + 1)))
                i += 3
                continue
        result.append(set_str[i])
        i += 1
    return ''.join(result)
def _parse_tr_sets(set1_str: str, set2_str: Optional[str] = None) -> Tuple[str, Optional[str]]:
    if set1_str.startswith(("'", '"')) and set1_str.endswith(("'", '"')):
        set1_str = set1_str[1:-1]
    if set2_str and set2_str.startswith(("'", '"')) and set2_str.endswith(("'", '"')):
        set2_str = set2_str[1:-1]
    set1 = _expand_ranges(set1_str)
    set2 = _expand_ranges(set2_str) if set2_str else None
    return set1, set2
def _build_tr_powershell_command(
    set1: str,
    set2: Optional[str],
    complement: bool,
    delete_mode: bool,
    squeeze_mode: bool,
    truncate: bool
) -> str:
    def escape_for_char_class(s: str) -> str:
        special_in_class = r'\^]\-'
        result = []
        for c in s:
            if c in special_in_class:
                result.append('\\' + c)
            else:
                result.append(c)
        return ''.join(result)
    def escape_for_replacement(s: str) -> str:
        result = []
        for c in s:
            if c == '"':
                result.append('\"')
            elif c == '$':
                result.append('$$')
            elif c == '\\':
                result.append('\\')
            else:
                result.append(c)
        return ''.join(result)
    truncate_note = ""
    if truncate and set2:
        truncate_note = " # NOTE: -t (truncate) not directly supported"
    if delete_mode:
        escaped_set1 = escape_for_char_class(set1)
        if complement:
            pattern = f"[^{escaped_set1}]"
            return f'$input -creplace "{pattern}", ""{truncate_note}'
        else:
            pattern = f"[{escaped_set1}]"
            return f'$input -creplace "{pattern}", ""{truncate_note}'
    elif squeeze_mode:
        escaped_set1 = escape_for_char_class(set1)
        if set2:
            squeeze_pattern = f"([{escaped_set1}])\\1+"
            if complement:
                squeeze_pattern = f"([^{escaped_set1}])\\1+"
            return f'$input -creplace "{squeeze_pattern}", "$1"{truncate_note}'
        else:
            squeeze_pattern = f"([{escaped_set1}])\\1+"
            if complement:
                squeeze_pattern = f"([^{escaped_set1}])\\1+"
            return f'$input -creplace "{squeeze_pattern}", "$1"{truncate_note}'
    else:
        if not set2:
            return 'Write-Output "tr: missing operand after SET1\nTry `tr --help` for more information."'
        if truncate and len(set1) > len(set2):
            set1 = set1[:len(set2)]
        replacements = []
        for i, c in enumerate(set1):
            if i < len(set2):
                target = set2[i]
            else:
                target = set2[-1] if set2 else ""
            source_escaped = escape_for_char_class(c)
            target_escaped = escape_for_replacement(target)
            replacements.append(f'-creplace "{source_escaped}", "{target_escaped}"')
        if replacements:
            return f'$input {" | ".join(replacements)}{truncate_note}'
        else:
            return f'$input{truncate_note}'
def _convert_unalias(cmd: str) -> str:
    if not cmd or not cmd.strip():
        return "Remove-Item alias:*"
    parts = _parse_command_line(cmd)
    if not parts:
        return "Remove-Item alias:*"
    if parts[0] in ('unalias', '/bin/unalias', '/usr/bin/unalias'):
        parts = parts[1:]
    if not parts:
        return "Remove-Item alias:*"
    remove_all = False
    alias_names: List[str] = []
    i = 0
    while i < len(parts):
        part = parts[i]
        if part == '--':
            alias_names.extend(parts[i + 1:])
            break
        if part.startswith('/') and len(part) >= 2 and part[1].isalpha():
            if len(part) == 2:
                part = '-' + part[1:]
            else:
                part = '--' + part[1:]
        if part.startswith('--'):
            opt_name = part[2:]
            if opt_name == 'all' or opt_name == 'a':
                remove_all = True
            i += 1
            continue
        if part.startswith('-') and len(part) > 1:
            opt_chars = part[1:]
            for char in opt_chars:
                if char == 'a':
                    remove_all = True
            i += 1
            continue
        alias_names.append(part)
        i += 1
    if remove_all:
        return "Remove-Item alias:*"
    if alias_names:
        escaped_names = []
        for name in alias_names:
            escaped_name = name.replace("'", "''")
            escaped_names.append(f"'alias:{escaped_name}'")
        if len(escaped_names) == 1:
            return f"Remove-Item {escaped_names[0]}"
        else:
            return f"Remove-Item {', '.join(escaped_names)}"
    return "Remove-Item alias:*"
def _convert_uname(cmd: str) -> str:
    if not cmd or not cmd.strip():
        return 'Write-Output "Windows"'
    parts = _parse_command_line(cmd)
    if not parts:
        return 'Write-Output "Windows"'
    if parts[0] in ('uname', '/bin/uname', '/usr/bin/uname'):
        parts = parts[1:]
    if not parts:
        return 'Write-Output "Windows"'
    show_all = False
    kernel_name = False
    nodename = False
    kernel_release = False
    kernel_version = False
    machine = False
    processor = False
    hardware_platform = False
    operating_system = False
    show_help = False
    show_version = False
    i = 0
    while i < len(parts):
        part = parts[i]
        if part == '--':
            break
        if part.startswith('/') and len(part) >= 2 and part[1].isalpha():
            if len(part) == 2:
                part = '-' + part[1:]
            else:
                sub_part = part[1:]
                if '=' in sub_part:
                    part = '--' + sub_part
                elif sub_part in ('all', 'kernel-name', 'nodename', 'kernel-release',
                                  'kernel-version', 'machine', 'processor',
                                  'hardware-platform', 'operating-system', 'help', 'version'):
                    part = '--' + sub_part
                else:
                    part = '-' + sub_part
        if part.startswith('--'):
            long_opt = part[2:]
            if long_opt == 'help':
                show_help = True
                i += 1
                continue
            elif long_opt == 'version':
                show_version = True
                i += 1
                continue
            elif long_opt == 'all':
                show_all = True
                i += 1
                continue
            elif long_opt == 'kernel-name':
                kernel_name = True
                i += 1
                continue
            elif long_opt == 'nodename':
                nodename = True
                i += 1
                continue
            elif long_opt == 'kernel-release':
                kernel_release = True
                i += 1
                continue
            elif long_opt == 'kernel-version':
                kernel_version = True
                i += 1
                continue
            elif long_opt == 'machine':
                machine = True
                i += 1
                continue
            elif long_opt == 'processor':
                processor = True
                i += 1
                continue
            elif long_opt == 'hardware-platform':
                hardware_platform = True
                i += 1
                continue
            elif long_opt == 'operating-system':
                operating_system = True
                i += 1
                continue
            i += 1
            continue
        if part.startswith('-') and len(part) > 1:
            opt_chars = part[1:]
            for char in opt_chars:
                if char == 'a':
                    show_all = True
                elif char == 's':
                    kernel_name = True
                elif char == 'n':
                    nodename = True
                elif char == 'r':
                    kernel_release = True
                elif char == 'v':
                    kernel_version = True
                elif char == 'm':
                    machine = True
                elif char == 'p':
                    processor = True
                elif char == 'i':
                    hardware_platform = True
                elif char == 'o':
                    operating_system = True
            i += 1
            continue
        i += 1
    if show_help:
        return (
            'Write-Output "Usage: uname [OPTION]...\n'
            'Print certain system information.  With no OPTION, same as -s.\n\n'
            '  -a, --all                print all information, in the following order,\n'
            '                           except omit -p and -i if unknown:\n'
            '  -s, --kernel-name        print the kernel name\n'
            '  -n, --nodename           print the network node hostname\n'
            '  -r, --kernel-release     print the kernel release\n'
            '  -v, --kernel-version     print the kernel version\n'
            '  -m, --machine            print the machine hardware name\n'
            '  -p, --processor          print the processor type (non-portable)\n'
            '  -i, --hardware-platform  print the hardware platform (non-portable)\n'
            '  -o, --operating-system   print the operating system\n'
            '      --help               display this help and exit\n'
            '      --version            output version information and exit"'
        )
    if show_version:
        return 'Write-Output "uname (GNU coreutils) 8.32"'
    if not any([show_all, kernel_name, nodename, kernel_release, kernel_version,
                machine, processor, hardware_platform, operating_system]):
        kernel_name = True
    if show_all:
        return (
            'Write-Output "Windows $env:COMPUTERNAME '
            '$([System.Environment]::OSVersion.Version.ToString()) '
            '$([System.Environment]::OSVersion.Version.ToString()) '
            '$([System.Runtime.InteropServices.RuntimeInformation]::ProcessArchitecture) '
            'Windows_NT"'
        )
    outputs = []
    if kernel_name:
        outputs.append('"Windows"')
    if nodename:
        outputs.append('$env:COMPUTERNAME')
    if kernel_release:
        outputs.append('[System.Environment]::OSVersion.Version.ToString()')
    if kernel_version:
        outputs.append('[System.Environment]::OSVersion.Version.ToString()')
    if machine:
        outputs.append(
            '$([System.Runtime.InteropServices.RuntimeInformation]::ProcessArchitecture.ToString().ToLower() -replace "x64", "x86_64")'
        )
    if processor:
        outputs.append(
            '$([System.Runtime.InteropServices.RuntimeInformation]::ProcessArchitecture.ToString().ToLower() -replace "x64", "x86_64")'
        )
    if hardware_platform:
        outputs.append(
            '$([System.Runtime.InteropServices.RuntimeInformation]::ProcessArchitecture.ToString().ToLower() -replace "x64", "x86_64")'
        )
    if operating_system:
        outputs.append('"Windows_NT"')
    if len(outputs) == 1:
        return f'Write-Output {outputs[0]}'
    else:
        return f'Write-Output {" ".join(outputs)}'
def _convert_uniq(cmd: str) -> str:
    if not cmd or not cmd.strip():
        return '$input | Select-Object -Unique'
    parts = _parse_command_line(cmd)
    if not parts:
        return '$input | Select-Object -Unique'
    if parts[0] in ('uniq', '/bin/uniq', '/usr/bin/uniq'):
        parts = parts[1:]
    if not parts:
        return '$input | Select-Object -Unique'
    count = False
    repeated = False
    all_duplicates = False
    unique_only = False
    ignore_case = False
    zero_terminated = False
    show_help = False
    show_version = False
    skip_fields: Optional[int] = None
    skip_chars: Optional[int] = None
    check_chars: Optional[int] = None
    files: List[str] = []
    i = 0
    while i < len(parts):
        part = parts[i]
        if part == '--':
            files.extend(parts[i + 1:])
            break
        if part.startswith('/') and len(part) >= 2 and part[1].isalpha():
            sub_part = part[1:]
            if len(part) == 2:
                part = '-' + part[1:]
            elif '=' in sub_part:
                part = '--' + sub_part
            elif sub_part in ('count', 'repeated', 'unique', 'ignore-case',
                              'zero-terminated', 'help', 'version',
                              'skip-fields', 'skip-chars', 'check-chars', 'all-repeated'):
                part = '--' + sub_part
            elif all(c.isalpha() and c.islower() for c in sub_part) and len(sub_part) <= 3:
                part = '-' + sub_part
        if part.startswith('--'):
            long_opt = part[2:]
            if long_opt == 'help':
                show_help = True
                i += 1
                continue
            if long_opt == 'version':
                show_version = True
                i += 1
                continue
            if long_opt == 'count':
                count = True
                i += 1
                continue
            if long_opt == 'repeated':
                repeated = True
                i += 1
                continue
            if long_opt == 'all-repeated':
                all_duplicates = True
                i += 1
                continue
            if long_opt == 'unique':
                unique_only = True
                i += 1
                continue
            if long_opt == 'ignore-case':
                ignore_case = True
                i += 1
                continue
            if long_opt == 'zero-terminated':
                zero_terminated = True
                i += 1
                continue
            if long_opt.startswith('skip-fields='):
                try:
                    skip_fields = int(long_opt.split('=', 1)[1])
                except ValueError:
                    skip_fields = 0
                i += 1
                continue
            elif long_opt == 'skip-fields':
                if i + 1 < len(parts):
                    i += 1
                    try:
                        skip_fields = int(parts[i])
                    except ValueError:
                        skip_fields = 0
                i += 1
                continue
            if long_opt.startswith('skip-chars='):
                try:
                    skip_chars = int(long_opt.split('=', 1)[1])
                except ValueError:
                    skip_chars = 0
                i += 1
                continue
            elif long_opt == 'skip-chars':
                if i + 1 < len(parts):
                    i += 1
                    try:
                        skip_chars = int(parts[i])
                    except ValueError:
                        skip_chars = 0
                i += 1
                continue
            if long_opt.startswith('check-chars='):
                try:
                    check_chars = int(long_opt.split('=', 1)[1])
                except ValueError:
                    check_chars = None
                i += 1
                continue
            elif long_opt == 'check-chars':
                if i + 1 < len(parts):
                    i += 1
                    try:
                        check_chars = int(parts[i])
                    except ValueError:
                        check_chars = None
                i += 1
                continue
            i += 1
            continue
        if part.startswith('-') and len(part) > 1:
            opt_chars = part[1:]
            j = 0
            while j < len(opt_chars):
                char = opt_chars[j]
                if char == 'c':
                    count = True
                    j += 1
                elif char == 'd':
                    repeated = True
                    j += 1
                elif char == 'D':
                    all_duplicates = True
                    j += 1
                elif char == 'u':
                    unique_only = True
                    j += 1
                elif char == 'i':
                    ignore_case = True
                    j += 1
                elif char == 'z':
                    zero_terminated = True
                    j += 1
                elif char == 'f':
                    if j + 1 < len(opt_chars):
                        try:
                            skip_fields = int(opt_chars[j + 1:])
                        except ValueError:
                            skip_fields = 0
                        break
                    elif i + 1 < len(parts):
                        i += 1
                        try:
                            skip_fields = int(parts[i])
                        except ValueError:
                            skip_fields = 0
                    j += 1
                elif char == 's':
                    if j + 1 < len(opt_chars):
                        try:
                            skip_chars = int(opt_chars[j + 1:])
                        except ValueError:
                            skip_chars = 0
                        break
                    elif i + 1 < len(parts):
                        i += 1
                        try:
                            skip_chars = int(parts[i])
                        except ValueError:
                            skip_chars = 0
                    j += 1
                elif char == 'w':
                    if j + 1 < len(opt_chars):
                        try:
                            check_chars = int(opt_chars[j + 1:])
                        except ValueError:
                            check_chars = None
                        break
                    elif i + 1 < len(parts):
                        i += 1
                        try:
                            check_chars = int(parts[i])
                        except ValueError:
                            check_chars = None
                    j += 1
                else:
                    j += 1
            i += 1
            continue
        files.append(part)
        i += 1
    return _build_uniq_powershell_command(
        count, repeated, all_duplicates, unique_only, ignore_case,
        zero_terminated, skip_fields, skip_chars, check_chars,
        show_help, show_version, files
    )
def _build_uniq_powershell_command(
    count: bool,
    repeated: bool,
    all_duplicates: bool,
    unique_only: bool,
    ignore_case: bool,
    zero_terminated: bool,
    skip_fields: Optional[int],
    skip_chars: Optional[int],
    check_chars: Optional[int],
    show_help: bool,
    show_version: bool,
    files: List[str]
) -> str:
    if show_help:
        return ('Write-Output "uniq - Report or omit repeated lines\n'
                'Usage: uniq [OPTION]... [INPUT [OUTPUT]]\n'
                'Filter adjacent matching lines from INPUT (or standard input),\n'
                'writing to OUTPUT (or standard output).\n\n'
                'Options:\n'
                '  -c, --count           Prefix lines by the number of occurrences\n'
                '  -d, --repeated        Only print duplicate lines, one for each group\n'
                '  -D                    Print all duplicate lines\n'
                '  -f, --skip-fields=N   Avoid comparing the first N fields\n'
                '  -i, --ignore-case     Ignore differences in case when comparing\n'
                '  -s, --skip-chars=N    Avoid comparing the first N characters\n'
                '  -u, --unique          Only print unique lines\n'
                '  -w, --check-chars=N   Compare no more than N characters in lines\n'
                '  -z, --zero-terminated  End lines with NUL, not newline\n'
                '      --help            Display this help and exit\n'
                '      --version         Output version information and exit"')
    if show_version:
        return 'Write-Output "uniq (GNU coreutils) 8.32"'
    notes: List[str] = []
    if zero_terminated:
        notes.append('# NOTE: -z (zero-terminated) not directly supported in PowerShell')
    if skip_fields is not None:
        notes.append(f'# NOTE: -f (skip-fields={skip_fields}) not directly supported in PowerShell')
    if skip_chars is not None:
        notes.append(f'# NOTE: -s (skip-chars={skip_chars}) not directly supported in PowerShell')
    if check_chars is not None:
        notes.append(f'# NOTE: -w (check-chars={check_chars}) not directly supported in PowerShell')
    if all_duplicates:
        notes.append('# NOTE: -D (all-duplicates) not directly supported in PowerShell')
    if files:
        file_path = files[0]
        if ' ' in file_path and not (file_path.startswith('"') or file_path.startswith("'")):
            file_path = f'"{file_path}"'
        input_cmd = f'Get-Content {file_path}'
    else:
        input_cmd = '$input'
    if count:
        if ignore_case:
            cmd = f'{input_cmd} | ForEach-Object {{ $_.ToLower() }} | Group-Object | ForEach-Object {{ "$($_.Count) $($_.Name)" }}'
        else:
            cmd = f'{input_cmd} | Group-Object | ForEach-Object {{ "$($_.Count) $($_.Name)" }}'
    elif repeated:
        if ignore_case:
            cmd = f'{input_cmd} | ForEach-Object {{ $_.ToLower() }} | Group-Object | Where-Object {{ $_.Count -gt 1 }} | ForEach-Object {{ $_.Name }}'
        else:
            cmd = f'{input_cmd} | Group-Object | Where-Object {{ $_.Count -gt 1 }} | ForEach-Object {{ $_.Name }}'
    elif unique_only:
        if ignore_case:
            cmd = f'{input_cmd} | ForEach-Object {{ $_.ToLower() }} | Group-Object | Where-Object {{ $_.Count -eq 1 }} | ForEach-Object {{ $_.Name }}'
        else:
            cmd = f'{input_cmd} | Group-Object | Where-Object {{ $_.Count -eq 1 }} | ForEach-Object {{ $_.Name }}'
    else:
        if ignore_case:
            cmd = f'{input_cmd} | ForEach-Object {{ $_.ToLower() }} | Select-Object -Unique'
        else:
            cmd = f'{input_cmd} | Select-Object -Unique'
    if notes:
        cmd += '  ' + ' '.join(notes)
    return cmd
if __name__ == "__main__":
    test_cases = [
        "uniq file.txt",
        "uniq -c file.txt",
        "uniq -d file.txt",
        "uniq -u file.txt",
        "uniq -i file.txt",
        "uniq -D file.txt",
        "uniq -f 2 file.txt",
        "uniq -s 5 file.txt",
        "uniq -w 10 file.txt",
        "uniq --count file.txt",
        "uniq --repeated file.txt",
        "uniq --unique file.txt",
        "uniq --ignore-case file.txt",
        "uniq --skip-fields=2 file.txt",
        "uniq --skip-chars=5 file.txt",
        "uniq --check-chars=10 file.txt",
        "uniq -z file.txt",
        "uniq --help",
        "uniq --version",
        "uniq /c file.txt",
        "uniq /i /c file.txt",
        "uniq",
        "uniq -cd file.txt",
    ]
    for test in test_cases:
        result = _convert_uniq(test)
        print(f"Input:  {test}")
        print(f"Output: {result}")
        print()
def _convert_unzip(cmd: str) -> str:
    if not cmd or not cmd.strip():
        return 'Write-Output "unzip: cannot find or open .zip"'
    parts = _parse_command_line(cmd)
    if not parts:
        return 'Write-Output "unzip: cannot find or open .zip"'
    if parts[0] in ('unzip', '/usr/bin/unzip', '/bin/unzip'):
        parts = parts[1:]
    if not parts:
        return 'Write-Output "unzip: cannot find or open .zip"'
    list_mode = False
    test_mode = False
    quiet = False
    verbose = False
    overwrite = False
    never_overwrite = False
    update_mode = False
    freshen_mode = False
    junk_paths = False
    pipe_mode = False
    stdout_mode = False
    auto_convert = False
    all_text = False
    zipinfo_mode = False
    show_comment = False
    show_help = False
    show_version = False
    password: Optional[str] = None
    dest_dir: Optional[str] = None
    exclude_files: List[str] = []
    include_files: List[str] = []
    VALID_SHORT_OPTS = 'ltoqnuvfjpcaAZz'
    VALID_LONG_OPTS = {
        'list', 'test', 'quiet', 'verbose', 'help', 'version',
        'junk-paths', 'update', 'freshen'
    }
    i = 0
    while i < len(parts):
        part = parts[i]
        if part == '--':
            i += 1
            break
        if part.startswith('/') and len(part) >= 2:
            opt_part = part[1:]
            if len(opt_part) == 1 and opt_part in VALID_SHORT_OPTS:
                part = '-' + opt_part
            elif opt_part in VALID_LONG_OPTS:
                part = '--' + opt_part
            elif '=' in opt_part:
                opt_name = opt_part.split('=', 1)[0]
                if opt_name in VALID_LONG_OPTS:
                    part = '--' + opt_part
            elif all(c in VALID_SHORT_OPTS for c in opt_part):
                part = '-' + opt_part
        if part.startswith('--'):
            long_opt = part[2:]
            if '=' in long_opt:
                opt_name, opt_value = long_opt.split('=', 1)
                if opt_name == 'password':
                    password = opt_value
                i += 1
                continue
            if long_opt == 'help':
                show_help = True
                i += 1
                continue
            elif long_opt == 'version':
                show_version = True
                i += 1
                continue
            elif long_opt == 'list':
                list_mode = True
                i += 1
                continue
            elif long_opt == 'test':
                test_mode = True
                i += 1
                continue
            elif long_opt == 'quiet':
                quiet = True
                i += 1
                continue
            elif long_opt == 'verbose':
                verbose = True
                i += 1
                continue
            elif long_opt == 'junk-paths':
                junk_paths = True
                i += 1
                continue
            elif long_opt == 'update':
                update_mode = True
                i += 1
                continue
            elif long_opt == 'freshen':
                freshen_mode = True
                i += 1
                continue
            elif long_opt == 'password':
                if i + 1 < len(parts):
                    i += 1
                    password = parts[i]
                i += 1
                continue
            elif long_opt == 'directory':
                if i + 1 < len(parts):
                    i += 1
                    dest_dir = parts[i]
                i += 1
                continue
            elif long_opt == 'exclude':
                if i + 1 < len(parts):
                    i += 1
                    exclude_files.append(parts[i])
                i += 1
                continue
            elif long_opt == 'include':
                if i + 1 < len(parts):
                    i += 1
                    include_files.append(parts[i])
                i += 1
                continue
            i += 1
            continue
        if part.startswith('-') and len(part) > 1:
            opt_chars = part[1:]
            j = 0
            skip_outer_increment = False
            while j < len(opt_chars):
                char = opt_chars[j]
                if char == 'l':
                    list_mode = True
                    j += 1
                elif char == 't':
                    test_mode = True
                    j += 1
                elif char == 'q':
                    quiet = True
                    j += 1
                elif char == 'v':
                    verbose = True
                    j += 1
                elif char == 'o':
                    overwrite = True
                    j += 1
                elif char == 'n':
                    never_overwrite = True
                    j += 1
                elif char == 'u':
                    update_mode = True
                    j += 1
                elif char == 'f':
                    freshen_mode = True
                    j += 1
                elif char == 'j':
                    junk_paths = True
                    j += 1
                elif char == 'p':
                    pipe_mode = True
                    j += 1
                elif char == 'c':
                    stdout_mode = True
                    j += 1
                elif char == 'a':
                    if j + 1 < len(opt_chars) and opt_chars[j + 1] == 'a':
                        all_text = True
                        j += 2
                    else:
                        auto_convert = True
                        j += 1
                elif char == 'Z':
                    zipinfo_mode = True
                    j += 1
                elif char == 'z':
                    show_comment = True
                    j += 1
                elif char == 'd':
                    if j + 1 < len(opt_chars):
                        dest_dir = opt_chars[j + 1:]
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                        dest_dir = parts[i]
                    j += 1
                elif char == 'P':
                    if j + 1 < len(opt_chars):
                        password = opt_chars[j + 1:]
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                        password = parts[i]
                    j += 1
                elif char == 'x':
                    if j + 1 < len(opt_chars):
                        exclude_files.append(opt_chars[j + 1:])
                        j = len(opt_chars)
                    else:
                        i += 1
                        while i < len(parts) and not parts[i].startswith('-'):
                            exclude_files.append(parts[i])
                            i += 1
                        skip_outer_increment = True
                    j += 1
                elif char == 'i':
                    if j + 1 < len(opt_chars):
                        include_files.append(opt_chars[j + 1:])
                        j = len(opt_chars)
                    else:
                        i += 1
                        while i < len(parts) and not parts[i].startswith('-'):
                            include_files.append(parts[i])
                            i += 1
                        skip_outer_increment = True
                    j += 1
                elif char == '-':
                    j += 1
                    i += 1
                    skip_outer_increment = True
                    break
                else:
                    j += 1
            if not skip_outer_increment:
                i += 1
            continue
        break
    if show_help:
        return (
            'Write-Output "UnZip 6.00 of 20 April 2009, by Info-ZIP.  Maintained by C. Spieler.  Send bug reports using http://www.info-zip.org/zip.html; see README for details.\n'
            '\n'
            'Usage: unzip [-Z] [-opts[modifiers]] file[.zip] [list] [-x xlist] [-d exdir]\n'
            '  Default action is to extract files in list, except for those in xlist, to exdir;\n'
            '  file[.zip] may be a wildcard.  -Z => ZipInfo mode (see man page).\n'
            '\n'
            '  -p  extract files to pipe, no messages     -l  list files (short format)\n'
            '  -f  freshen existing files, create none    -t  test compressed archive data\n'
            '  -u  update files, create if necessary      -z  display archive comment only\n'
            '  -v  list verbosely/show version info       -T  timestamp archive to latest\n'
            '  -x  exclude files that follow (in xlist)   -d  extract files into exdir\n'
            'modifiers:\n'
            '  -n  never overwrite existing files         -q  quiet mode (-qq => quieter)\n'
            '  -o  overwrite files WITHOUT prompting      -a  auto-convert any text files\n'
            '  -j  junk paths (do not make directories)   -aa treat ALL files as text\n'
            '  -C  match filenames case-insensitively     -L  make (some) names lowercase\n'
            '  -V  retain VMS version numbers             -M  pipe through `more` pager\n'
            '  -O CHARSET  specify a character encoding for DOS, Windows and OS/2 archives\n'
            '  -I CHARSET  specify a character encoding for UNIX and other archives\n'
            'See `unzip -hh` or unzip.txt for more help.  Examples:\n'
            '  unzip data1 -x joe   => extract all files except joe from data1.zip\n'
            '  unzip -p foo | more  => send contents of foo.zip via pipe into program more\n'
            '  unzip -fo foo ReadMe => quietly replace existing ReadMe if archive file newer"'
        )
    if show_version:
        return 'Write-Output "UnZip 6.00 of 20 April 2009, by Info-ZIP."'
    if show_comment:
        return (
            'Add-Type -AssemblyName System.IO.Compression.FileSystem; '
            '$zip = [System.IO.Compression.ZipFile]::OpenRead("archive.zip"); '
            'Write-Output $zip.Comment; '
            '$zip.Dispose()'
        )
    remaining = parts[i:]
    if not remaining:
        return 'Write-Output "unzip: cannot find or open .zip"'
    archive_file = remaining[0]
    specific_files: List[str] = []
    j = 1
    while j < len(remaining):
        part = remaining[j]
        if part == '--':
            j += 1
            while j < len(remaining):
                specific_files.append(remaining[j])
                j += 1
            break
        if part.startswith('/') and len(part) >= 2:
            opt_part = part[1:]
            if opt_part in ('d', 'x', 'i'):
                part = '-' + opt_part
            elif opt_part.startswith('d') and len(opt_part) > 1:
                part = '-' + opt_part
            elif opt_part in ('directory', 'exclude', 'include'):
                part = '--' + opt_part
        if part == '-d' or part == '--directory':
            if j + 1 < len(remaining):
                j += 1
                dest_dir = remaining[j]
            j += 1
            continue
        if part.startswith('-d') and len(part) > 2:
            dest_dir = part[2:]
            j += 1
            continue
        if part == '-x' or part == '--exclude':
            j += 1
            while j < len(remaining) and not remaining[j].startswith('-') and not remaining[j].startswith('/'):
                exclude_files.append(remaining[j])
                j += 1
            continue
        if part == '-i' or part == '--include':
            j += 1
            while j < len(remaining) and not remaining[j].startswith('-') and not remaining[j].startswith('/'):
                include_files.append(remaining[j])
                j += 1
            continue
        if part.startswith('-') or part.startswith('/'):
            j += 1
            continue
        specific_files.append(part)
        j += 1
    def quote_path(path: str) -> str:
        if ' ' in path and not (path.startswith('"') or path.startswith("'")):
            return f'"{path}"'
        return path
    quoted_archive = quote_path(archive_file)
    if dest_dir is None:
        dest_dir = "."
    quoted_dest = quote_path(dest_dir)
    if list_mode:
        if verbose:
            return (
                f'Add-Type -AssemblyName System.IO.Compression.FileSystem; '
                f'$zip = [System.IO.Compression.ZipFile]::OpenRead({quoted_archive}); '
                f'$zip.Entries | Select-Object FullName, Length, CompressedLength, LastWriteTime | '
                f'Format-Table -AutoSize; '
                f'$zip.Dispose()'
            )
        else:
            return (
                f'Add-Type -AssemblyName System.IO.Compression.FileSystem; '
                f'$zip = [System.IO.Compression.ZipFile]::OpenRead({quoted_archive}); '
                f'$zip.Entries | Select-Object FullName, Length, LastWriteTime; '
                f'$zip.Dispose()'
            )
    if test_mode:
        return (
            f'try {{ '
            f'Expand-Archive -Path {quoted_archive} -DestinationPath "$env:TEMP\test_extract" -Force; '
            f'Remove-Item -Path "$env:TEMP\test_extract" -Recurse -Force; '
            f'Write-Output "No errors detected in {archive_file}." '
            f'}} catch {{ Write-Error "Error testing {archive_file}" }}'
        )
    if pipe_mode or stdout_mode:
        if specific_files:
            file_list = ', '.join([f'"{f}"' for f in specific_files])
            return (
                f'Add-Type -AssemblyName System.IO.Compression.FileSystem; '
                f'$zip = [System.IO.Compression.ZipFile]::OpenRead({quoted_archive}); '
                f'@({file_list}) | ForEach-Object {{ '
                f'$entry = $zip.GetEntry($_); '
                f'if ($entry) {{ '
                f'$stream = $entry.Open(); '
                f'$reader = [System.IO.StreamReader]::new($stream); '
                f'$reader.ReadToEnd(); '
                f'$reader.Dispose(); '
                f'$stream.Dispose() '
                f'}} '
                f'}}; '
                f'$zip.Dispose()'
            )
        else:
            return (
                f'Add-Type -AssemblyName System.IO.Compression.FileSystem; '
                f'$zip = [System.IO.Compression.ZipFile]::OpenRead({quoted_archive}); '
                f'$zip.Entries | Where-Object {{ -not $_.FullName.EndsWith("/") }} | ForEach-Object {{ '
                f'$stream = $_.Open(); '
                f'$reader = [System.IO.StreamReader]::new($stream); '
                f'Write-Output "--- $($_.FullName) ---"; '
                f'$reader.ReadToEnd(); '
                f'$reader.Dispose(); '
                f'$stream.Dispose() '
                f'}}; '
                f'$zip.Dispose()'
            )
    if zipinfo_mode:
        return (
            f'Add-Type -AssemblyName System.IO.Compression.FileSystem; '
            f'$zip = [System.IO.Compression.ZipFile]::OpenRead({quoted_archive}); '
            f'Write-Output "Archive: {archive_file}"; '
            f'Write-Output "  Length      Date    Time    Name"; '
            f'Write-Output "---------  ---------- -----   ----"; '
            f'$total = 0; '
            f'$zip.Entries | ForEach-Object {{ '
            f'$total += $_.Length; '
            f'Write-Output ("{{0,9}}  {{1:yyyy-MM-dd HH:mm}}   {{2}}" -f $_.Length, $_.LastWriteTime, $_.FullName) '
            f'}}; '
            f'Write-Output "---------                     -------"; '
            f'Write-Output ("{{0,9}}                     {{1}} files" -f $total, $zip.Entries.Count); '
            f'$zip.Dispose()'
        )
    if specific_files or exclude_files or include_files or junk_paths or update_mode or freshen_mode or never_overwrite:
        cmd_parts = [
            'Add-Type -AssemblyName System.IO.Compression.FileSystem',
            f'$zip = [System.IO.Compression.ZipFile]::OpenRead({quoted_archive})',
        ]
        if specific_files:
            file_list = ', '.join([f'"{f}"' for f in specific_files])
            cmd_parts.append(f'$files = @({file_list})')
            cmd_parts.append('$entries = $zip.Entries | Where-Object {{ $files -contains $_.FullName }}')
        else:
            cmd_parts.append('$entries = $zip.Entries | Where-Object {{ -not $_.FullName.EndsWith("/") }}')
        if include_files:
            for inc in include_files:
                cmd_parts.append(f'$entries = $entries | Where-Object {{ $_.FullName -like "*{inc}*" }}')
        if exclude_files:
            for exc in exclude_files:
                cmd_parts.append(f'$entries = $entries | Where-Object {{ $_.FullName -notlike "*{exc}*" }}')
        cmd_parts.append('$entries | ForEach-Object {')
        if junk_paths:
            cmd_parts.append(f'  $destPath = Join-Path {quoted_dest} ($_.FullName.Split("/")[-1])')
        else:
            cmd_parts.append(f'  $destPath = Join-Path {quoted_dest} $_.FullName')
            cmd_parts.append('  $destDir = Split-Path -Parent $destPath')
            cmd_parts.append('  if (-not (Test-Path $destDir)) { New-Item -ItemType Directory -Path $destDir -Force | Out-Null }')
        if update_mode:
            cmd_parts.append('  if ((Test-Path $destPath) -and ((Get-Item $destPath).LastWriteTime -ge $_.LastWriteTime)) { return }')
        elif freshen_mode:
            cmd_parts.append('  if (-not (Test-Path $destPath)) { return }')
            cmd_parts.append('  if ((Get-Item $destPath).LastWriteTime -ge $_.LastWriteTime) { return }')
        elif never_overwrite:
            cmd_parts.append('  if (Test-Path $destPath) { return }')
        overwrite_flag = '$true' if overwrite else '$false'
        cmd_parts.append(f'  [System.IO.Compression.ZipFileExtensions]::ExtractToFile($_, $destPath, {overwrite_flag})')
        if verbose:
            cmd_parts.append('  Write-Output "  inflating: $destPath"')
        cmd_parts.append('}')
        cmd_parts.append('$zip.Dispose()')
        return '; '.join(cmd_parts)
    if overwrite:
        ps_cmd = f'Expand-Archive -Path {quoted_archive} -DestinationPath {quoted_dest} -Force'
    else:
        ps_cmd = f'Expand-Archive -Path {quoted_archive} -DestinationPath {quoted_dest}'
    return ps_cmd
if __name__ == "__main__":
    test_cases = [
        "unzip archive.zip",
        "unzip archive.zip -d /path/to/dest",
        "unzip -l archive.zip",
        "unzip -t archive.zip",
        "unzip -q archive.zip",
        "unzip -v archive.zip",
        "unzip -o archive.zip",
        "unzip -n archive.zip",
        "unzip -u archive.zip",
        "unzip -f archive.zip",
        "unzip -j archive.zip",
        "unzip archive.zip file1.txt file2.txt",
        "unzip archive.zip -x exclude.txt",
        "unzip -lt archive.zip",
        "unzip --help",
        "unzip --version",
        "unzip /l archive.zip",
        "unzip /o /q archive.zip",
        "unzip -p archive.zip file.txt",
        "unzip -c archive.zip",
    ]
    for test in test_cases:
        result = _convert_unzip(test)
        print(f"Input:  {test}")
        print(f"Output: {result}")
        print()
def _convert_uptime(cmd: str) -> str:
    if not cmd or not cmd.strip():
        return 'Get-Uptime'
    parts = _parse_command_line(cmd)
    if not parts:
        return 'Get-Uptime'
    if parts[0] in ('uptime', '/bin/uptime', '/usr/bin/uptime'):
        parts = parts[1:]
    if not parts:
        return 'Get-Uptime'
    pretty_mode = False
    since_mode = False
    container_mode = False
    raw_mode = False
    show_help = False
    show_version = False
    i = 0
    while i < len(parts):
        part = parts[i]
        if part == '--':
            break
        if part.startswith('/') and len(part) >= 2 and part[1].isalpha():
            if len(part) == 2:
                part = '-' + part[1:]
            else:
                sub_part = part[1:]
                if '=' in sub_part:
                    part = '--' + sub_part
                elif sub_part in ('container', 'pretty', 'help', 'raw', 'since', 'version'):
                    part = '--' + sub_part
                else:
                    part = '-' + sub_part
        if part.startswith('--'):
            long_opt = part[2:]
            if long_opt == 'help':
                show_help = True
                i += 1
                continue
            elif long_opt == 'version':
                show_version = True
                i += 1
                continue
            elif long_opt == 'pretty':
                pretty_mode = True
                i += 1
                continue
            elif long_opt == 'since':
                since_mode = True
                i += 1
                continue
            elif long_opt == 'container':
                container_mode = True
                i += 1
                continue
            elif long_opt == 'raw':
                raw_mode = True
                i += 1
                continue
            i += 1
            continue
        if part.startswith('-') and len(part) > 1:
            opt_chars = part[1:]
            for char in opt_chars:
                if char == 'p':
                    pretty_mode = True
                elif char == 's':
                    since_mode = True
                elif char == 'c':
                    container_mode = True
                elif char == 'r':
                    raw_mode = True
                elif char == 'h':
                    show_help = True
                elif char == 'V':
                    show_version = True
            i += 1
            continue
        i += 1
    if show_help:
        return (
            'Write-Output "Usage: uptime [OPTION]...\n'
            'Display how long the system has been running.\n\n'
            '  -c, --container  show the container uptime instead of system uptime\n'
            '  -p, --pretty     show uptime in pretty format\n'
            '  -h, --help       display this help and exit\n'
            '  -r, --raw        display values in raw format (seconds)\n'
            '  -s, --since      system up since, in yyyy-mm-dd HH:MM:SS format\n'
            '  -V, --version    output version information and exit"'
        )
    if show_version:
        return 'Write-Output "uptime (procps-ng) 3.3.17"'
    if since_mode:
        return '(Get-Date).Add(-(Get-Uptime)) | Get-Date -Format "yyyy-MM-dd HH:mm:ss"'
    if raw_mode:
        return 'Get-Uptime | Select-Object -ExpandProperty TotalSeconds'
    if pretty_mode:
        return (
            '$uptime = Get-Uptime; '
            '$days = $uptime.Days; '
            '$hours = $uptime.Hours; '
            '$minutes = $uptime.Minutes; '
            '$result = @(); '
            'if ($days -gt 0) { $result += "$days day$(if($days -ne 1){\"s\"})" }; '
            'if ($hours -gt 0) { $result += "$hours hour$(if($hours -ne 1){\"s\"})" }; '
            'if ($minutes -gt 0) { $result += "$minutes minute$(if($minutes -ne 1){\"s\"})" }; '
            'Write-Output ($result -join \", \")'
        )
    if container_mode:
        return 'Get-Uptime'
    return 'Get-Uptime'
def _convert_wget(cmd: str) -> str:
    if not cmd or not cmd.strip():
        return 'Write-Output "wget: missing URL"'
    parts = _parse_command_line(cmd)
    if not parts:
        return 'Write-Output "wget: missing URL"'
    if parts[0] in ('wget', '/usr/bin/wget', '/bin/wget'):
        parts = parts[1:]
    if not parts:
        return 'Write-Output "wget: missing URL"'
    options: Dict[str, Any] = {
        'output_document': None,
        'directory_prefix': None,
        'background': False,
        'quiet': False,
        'verbose': False,
        'no_verbose': False,
        'continue': False,
        'timestamping': False,
        'no_clobber': False,
        'timeout': None,
        'tries': None,
        'user_agent': None,
        'headers': [],
        'post_data': None,
        'post_file': None,
        'method': None,
        'http_user': None,
        'http_password': None,
        'ftp_user': None,
        'ftp_password': None,
        'no_check_certificate': False,
        'certificate': None,
        'private_key': None,
        'ca_certificate': None,
        'max_redirect': None,
        'no_proxy': False,
        'proxy': None,
        'recursive': False,
        'level': None,
        'no_directories': False,
        'accept': None,
        'reject': None,
        'mirror': False,
        'spider': False,
        'input_file': None,
        'delete_after': False,
        'server_response': False,
        'save_headers': False,
        'content_disposition': False,
        'trust_server_names': False,
        'limit_rate': None,
        'dns_timeout': None,
        'connect_timeout': None,
        'read_timeout': None,
        'bind_address': None,
        'inet4_only': False,
        'inet6_only': False,
        'retry_connrefused': False,
        'wait': None,
        'wait_retry': None,
        'random_wait': False,
        'user': None,
        'password': None,
        'passive_ftp': False,
        'active_ftp': False,
        'no_glob': False,
        'prefer_family': None,
        'append_output': None,
        'output_file': None,
        'debug': False,
        'help': False,
        'version': False,
    }
    urls: List[str] = []
    VALID_SHORT_OPTS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz'
    VALID_LONG_OPTS = {
        'output-document', 'directory-prefix', 'output', 'background', 'quiet',
        'verbose', 'no-verbose', 'continue', 'timestamping', 'no-clobber',
        'timeout', 'tries', 'user-agent', 'header', 'post-data', 'post-file',
        'method', 'http-user', 'http-password', 'ftp-user', 'ftp-password',
        'no-check-certificate', 'certificate', 'private-key', 'ca-certificate',
        'max-redirect', 'no-proxy', 'proxy', 'recursive', 'level', 'no-directories',
        'accept', 'reject', 'mirror', 'spider', 'input-file', 'delete-after',
        'server-response', 'save-headers', 'content-disposition', 'trust-server-names',
        'limit-rate', 'dns-timeout', 'connect-timeout', 'read-timeout', 'bind-address',
        'inet4-only', 'inet6-only', 'retry-connrefused', 'wait', 'waitretry',
        'random-wait', 'user', 'password', 'passive-ftp', 'active-ftp', 'no-glob',
        'glob', 'prefer-family', 'report-speed', 'progress', 'show-progress',
        'no-show-progress', 'append-output', 'output-file', 'debug', 'help', 'version',
        'execute', 'config', 'force-html', 'base', 'referer', 'save-cookies',
        'load-cookies', 'keep-session-cookies', 'auth-no-challenge', 'secure-protocol',
        'no-http-keep-alive', 'no-cache', 'no-cookies', 'no-dns-cache', 'no-parent',
        'page-requisites', 'strict-comments', 'adjust-extension', 'convert-links',
        'backup-converted', 'backup', 'suffix', 'domains', 'exclude-domains',
        'follow-ftp', 'follow-tags', 'ignore-tags', 'include-directories',
        'exclude-directories', 'follow-tags', 'ignore-tags', 'cut-dirs',
        'default-page', 'http-keep-alive', 'cookies', 'dns-cache', 'parent',
    }
    i = 0
    while i < len(parts):
        part = parts[i]
        if part == '--':
            i += 1
            urls.extend(parts[i:])
            break
        if part.startswith('/') and len(part) >= 2:
            opt_part = part[1:]
            if len(opt_part) == 1 and opt_part in VALID_SHORT_OPTS:
                part = '-' + opt_part
            elif opt_part in VALID_LONG_OPTS:
                part = '--' + opt_part
            elif '=' in opt_part:
                opt_name = opt_part.split('=', 1)[0]
                if opt_name in VALID_LONG_OPTS:
                    part = '--' + opt_part
            elif all(c in VALID_SHORT_OPTS for c in opt_part):
                part = '-' + opt_part
        if part.startswith('--'):
            long_opt = part[2:]
            if '=' in long_opt:
                opt_name, opt_value = long_opt.split('=', 1)
                if opt_name == 'output-document':
                    options['output_document'] = opt_value
                elif opt_name == 'directory-prefix':
                    options['directory_prefix'] = opt_value
                elif opt_name == 'timeout':
                    options['timeout'] = opt_value
                elif opt_name == 'tries':
                    options['tries'] = opt_value
                elif opt_name == 'user-agent':
                    options['user_agent'] = opt_value
                elif opt_name == 'header':
                    options['headers'].append(opt_value)
                elif opt_name == 'post-data':
                    options['post_data'] = opt_value
                elif opt_name == 'post-file':
                    options['post_file'] = opt_value
                elif opt_name == 'method':
                    options['method'] = opt_value
                elif opt_name == 'http-user':
                    options['http_user'] = opt_value
                elif opt_name == 'http-password':
                    options['http_password'] = opt_value
                elif opt_name == 'ftp-user':
                    options['ftp_user'] = opt_value
                elif opt_name == 'ftp-password':
                    options['ftp_password'] = opt_value
                elif opt_name == 'certificate':
                    options['certificate'] = opt_value
                elif opt_name == 'private-key':
                    options['private_key'] = opt_value
                elif opt_name == 'ca-certificate':
                    options['ca_certificate'] = opt_value
                elif opt_name == 'max-redirect':
                    options['max_redirect'] = opt_value
                elif opt_name == 'level':
                    options['level'] = opt_value
                elif opt_name == 'accept':
                    options['accept'] = opt_value
                elif opt_name == 'reject':
                    options['reject'] = opt_value
                elif opt_name == 'input-file':
                    options['input_file'] = opt_value
                elif opt_name == 'limit-rate':
                    options['limit_rate'] = opt_value
                elif opt_name == 'dns-timeout':
                    options['dns_timeout'] = opt_value
                elif opt_name == 'connect-timeout':
                    options['connect_timeout'] = opt_value
                elif opt_name == 'read-timeout':
                    options['read_timeout'] = opt_value
                elif opt_name == 'bind-address':
                    options['bind_address'] = opt_value
                elif opt_name == 'wait':
                    options['wait'] = opt_value
                elif opt_name == 'waitretry':
                    options['wait_retry'] = opt_value
                elif opt_name == 'user':
                    options['user'] = opt_value
                elif opt_name == 'password':
                    options['password'] = opt_value
                elif opt_name == 'prefer-family':
                    options['prefer_family'] = opt_value
                elif opt_name == 'append-output':
                    options['append_output'] = opt_value
                elif opt_name == 'output-file':
                    options['output_file'] = opt_value
                elif opt_name == 'execute':
                    if 'http_proxy' in opt_value or 'use_proxy' in opt_value:
                        if 'use_proxy=yes' in opt_value:
                            options['proxy'] = True
                        elif '=' in opt_value:
                            key, val = opt_value.split('=', 1)
                            if key == 'http_proxy':
                                options['proxy'] = val
                i += 1
                continue
            if long_opt == 'help':
                options['help'] = True
                i += 1
                continue
            elif long_opt == 'version':
                options['version'] = True
                i += 1
                continue
            elif long_opt == 'background':
                options['background'] = True
                i += 1
                continue
            elif long_opt == 'quiet':
                options['quiet'] = True
                i += 1
                continue
            elif long_opt == 'verbose':
                options['verbose'] = True
                i += 1
                continue
            elif long_opt == 'no-verbose':
                options['no_verbose'] = True
                i += 1
                continue
            elif long_opt == 'continue':
                options['continue'] = True
                i += 1
                continue
            elif long_opt == 'timestamping':
                options['timestamping'] = True
                i += 1
                continue
            elif long_opt == 'no-clobber':
                options['no_clobber'] = True
                i += 1
                continue
            elif long_opt == 'no-check-certificate':
                options['no_check_certificate'] = True
                i += 1
                continue
            elif long_opt == 'no-proxy':
                options['no_proxy'] = True
                i += 1
                continue
            elif long_opt == 'recursive':
                options['recursive'] = True
                i += 1
                continue
            elif long_opt == 'no-directories':
                options['no_directories'] = True
                i += 1
                continue
            elif long_opt == 'mirror':
                options['mirror'] = True
                i += 1
                continue
            elif long_opt == 'spider':
                options['spider'] = True
                i += 1
                continue
            elif long_opt == 'delete-after':
                options['delete_after'] = True
                i += 1
                continue
            elif long_opt == 'server-response':
                options['server_response'] = True
                i += 1
                continue
            elif long_opt == 'save-headers':
                options['save_headers'] = True
                i += 1
                continue
            elif long_opt == 'content-disposition':
                options['content_disposition'] = True
                i += 1
                continue
            elif long_opt == 'trust-server-names':
                options['trust_server_names'] = True
                i += 1
                continue
            elif long_opt == 'inet4-only':
                options['inet4_only'] = True
                i += 1
                continue
            elif long_opt == 'inet6-only':
                options['inet6_only'] = True
                i += 1
                continue
            elif long_opt == 'retry-connrefused':
                options['retry_connrefused'] = True
                i += 1
                continue
            elif long_opt == 'random-wait':
                options['random_wait'] = True
                i += 1
                continue
            elif long_opt == 'passive-ftp':
                options['passive_ftp'] = True
                i += 1
                continue
            elif long_opt == 'active-ftp':
                options['active_ftp'] = True
                i += 1
                continue
            elif long_opt == 'no-glob':
                options['no_glob'] = True
                i += 1
                continue
            elif long_opt == 'debug':
                options['debug'] = True
                i += 1
                continue
            elif long_opt == 'output-document':
                if i + 1 < len(parts):
                    i += 1
                    options['output_document'] = parts[i]
                i += 1
                continue
            elif long_opt == 'directory-prefix':
                if i + 1 < len(parts):
                    i += 1
                    options['directory_prefix'] = parts[i]
                i += 1
                continue
            elif long_opt == 'timeout':
                if i + 1 < len(parts):
                    i += 1
                    options['timeout'] = parts[i]
                i += 1
                continue
            elif long_opt == 'tries':
                if i + 1 < len(parts):
                    i += 1
                    options['tries'] = parts[i]
                i += 1
                continue
            elif long_opt == 'user-agent':
                if i + 1 < len(parts):
                    i += 1
                    options['user_agent'] = parts[i]
                i += 1
                continue
            elif long_opt == 'header':
                if i + 1 < len(parts):
                    i += 1
                    options['headers'].append(parts[i])
                i += 1
                continue
            elif long_opt == 'post-data':
                if i + 1 < len(parts):
                    i += 1
                    options['post_data'] = parts[i]
                i += 1
                continue
            elif long_opt == 'post-file':
                if i + 1 < len(parts):
                    i += 1
                    options['post_file'] = parts[i]
                i += 1
                continue
            elif long_opt == 'method':
                if i + 1 < len(parts):
                    i += 1
                    options['method'] = parts[i]
                i += 1
                continue
            elif long_opt == 'http-user':
                if i + 1 < len(parts):
                    i += 1
                    options['http_user'] = parts[i]
                i += 1
                continue
            elif long_opt == 'http-password':
                if i + 1 < len(parts):
                    i += 1
                    options['http_password'] = parts[i]
                i += 1
                continue
            elif long_opt == 'ftp-user':
                if i + 1 < len(parts):
                    i += 1
                    options['ftp_user'] = parts[i]
                i += 1
                continue
            elif long_opt == 'ftp-password':
                if i + 1 < len(parts):
                    i += 1
                    options['ftp_password'] = parts[i]
                i += 1
                continue
            elif long_opt == 'certificate':
                if i + 1 < len(parts):
                    i += 1
                    options['certificate'] = parts[i]
                i += 1
                continue
            elif long_opt == 'private-key':
                if i + 1 < len(parts):
                    i += 1
                    options['private_key'] = parts[i]
                i += 1
                continue
            elif long_opt == 'ca-certificate':
                if i + 1 < len(parts):
                    i += 1
                    options['ca_certificate'] = parts[i]
                i += 1
                continue
            elif long_opt == 'max-redirect':
                if i + 1 < len(parts):
                    i += 1
                    options['max_redirect'] = parts[i]
                i += 1
                continue
            elif long_opt == 'level':
                if i + 1 < len(parts):
                    i += 1
                    options['level'] = parts[i]
                i += 1
                continue
            elif long_opt == 'accept':
                if i + 1 < len(parts):
                    i += 1
                    options['accept'] = parts[i]
                i += 1
                continue
            elif long_opt == 'reject':
                if i + 1 < len(parts):
                    i += 1
                    options['reject'] = parts[i]
                i += 1
                continue
            elif long_opt == 'input-file':
                if i + 1 < len(parts):
                    i += 1
                    options['input_file'] = parts[i]
                i += 1
                continue
            elif long_opt == 'limit-rate':
                if i + 1 < len(parts):
                    i += 1
                    options['limit_rate'] = parts[i]
                i += 1
                continue
            elif long_opt == 'dns-timeout':
                if i + 1 < len(parts):
                    i += 1
                    options['dns_timeout'] = parts[i]
                i += 1
                continue
            elif long_opt == 'connect-timeout':
                if i + 1 < len(parts):
                    i += 1
                    options['connect_timeout'] = parts[i]
                i += 1
                continue
            elif long_opt == 'read-timeout':
                if i + 1 < len(parts):
                    i += 1
                    options['read_timeout'] = parts[i]
                i += 1
                continue
            elif long_opt == 'bind-address':
                if i + 1 < len(parts):
                    i += 1
                    options['bind_address'] = parts[i]
                i += 1
                continue
            elif long_opt == 'wait':
                if i + 1 < len(parts):
                    i += 1
                    options['wait'] = parts[i]
                i += 1
                continue
            elif long_opt == 'waitretry':
                if i + 1 < len(parts):
                    i += 1
                    options['wait_retry'] = parts[i]
                i += 1
                continue
            elif long_opt == 'user':
                if i + 1 < len(parts):
                    i += 1
                    options['user'] = parts[i]
                i += 1
                continue
            elif long_opt == 'password':
                if i + 1 < len(parts):
                    i += 1
                    options['password'] = parts[i]
                i += 1
                continue
            elif long_opt == 'prefer-family':
                if i + 1 < len(parts):
                    i += 1
                    options['prefer_family'] = parts[i]
                i += 1
                continue
            elif long_opt == 'append-output':
                if i + 1 < len(parts):
                    i += 1
                    options['append_output'] = parts[i]
                i += 1
                continue
            elif long_opt == 'output-file':
                if i + 1 < len(parts):
                    i += 1
                    options['output_file'] = parts[i]
                i += 1
                continue
            i += 1
            continue
        if part.startswith('-') and len(part) > 1:
            opt_chars = part[1:]
            j = 0
            while j < len(opt_chars):
                char = opt_chars[j]
                if char == 'O':
                    if j + 1 < len(opt_chars):
                        options['output_document'] = opt_chars[j + 1:]
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                        options['output_document'] = parts[i]
                    j += 1
                elif char == 'P':
                    if j + 1 < len(opt_chars):
                        options['directory_prefix'] = opt_chars[j + 1:]
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                        options['directory_prefix'] = parts[i]
                    j += 1
                elif char == 'b':
                    options['background'] = True
                    j += 1
                elif char == 'q':
                    options['quiet'] = True
                    j += 1
                elif char == 'v':
                    options['verbose'] = True
                    j += 1
                elif char == 'c':
                    options['continue'] = True
                    j += 1
                elif char == 'N':
                    options['timestamping'] = True
                    j += 1
                elif char == 'n':
                    if j + 1 < len(opt_chars) and opt_chars[j + 1] == 'c':
                        options['no_clobber'] = True
                        j += 2
                    else:
                        j += 1
                elif char == 'S':
                    options['server_response'] = True
                    j += 1
                elif char == 's':
                    j += 1
                elif char == 'T':
                    if j + 1 < len(opt_chars):
                        options['timeout'] = opt_chars[j + 1:]
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                        options['timeout'] = parts[i]
                    j += 1
                elif char == 't':
                    if j + 1 < len(opt_chars):
                        options['tries'] = opt_chars[j + 1:]
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                        options['tries'] = parts[i]
                    j += 1
                elif char == 'U':
                    if j + 1 < len(opt_chars):
                        options['user_agent'] = opt_chars[j + 1:]
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                        options['user_agent'] = parts[i]
                    j += 1
                elif char == 'r':
                    options['recursive'] = True
                    j += 1
                elif char == 'l':
                    if j + 1 < len(opt_chars):
                        options['level'] = opt_chars[j + 1:]
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                        options['level'] = parts[i]
                    j += 1
                elif char == 'A':
                    if j + 1 < len(opt_chars):
                        options['accept'] = opt_chars[j + 1:]
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                        options['accept'] = parts[i]
                    j += 1
                elif char == 'R':
                    if j + 1 < len(opt_chars):
                        options['reject'] = opt_chars[j + 1:]
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                        options['reject'] = parts[i]
                    j += 1
                elif char == 'm':
                    options['mirror'] = True
                    j += 1
                elif char == 'i':
                    if j + 1 < len(opt_chars):
                        options['input_file'] = opt_chars[j + 1:]
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                        options['input_file'] = parts[i]
                    j += 1
                elif char == 'o':
                    if j + 1 < len(opt_chars):
                        options['output_file'] = opt_chars[j + 1:]
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                        options['output_file'] = parts[i]
                    j += 1
                elif char == 'a':
                    if j + 1 < len(opt_chars):
                        options['append_output'] = opt_chars[j + 1:]
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                        options['append_output'] = parts[i]
                    j += 1
                elif char == 'd':
                    options['debug'] = True
                    j += 1
                elif char == '4':
                    options['inet4_only'] = True
                    j += 1
                elif char == '6':
                    options['inet6_only'] = True
                    j += 1
                elif char == 'w':
                    if j + 1 < len(opt_chars):
                        options['wait'] = opt_chars[j + 1:]
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                        options['wait'] = parts[i]
                    j += 1
                elif char == 'F':
                    j += 1
                elif char == 'B':
                    if j + 1 < len(opt_chars):
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                    j += 1
                elif char == 'e':
                    if j + 1 < len(opt_chars):
                        exec_val = opt_chars[j + 1:]
                        if 'http_proxy' in exec_val or 'use_proxy' in exec_val:
                            if 'use_proxy=yes' in exec_val:
                                options['proxy'] = True
                            elif '=' in exec_val:
                                key, val = exec_val.split('=', 1)
                                if key == 'http_proxy':
                                    options['proxy'] = val
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                        exec_val = parts[i]
                        if 'http_proxy' in exec_val or 'use_proxy' in exec_val:
                            if 'use_proxy=yes' in exec_val:
                                options['proxy'] = True
                            elif '=' in exec_val:
                                key, val = exec_val.split('=', 1)
                                if key == 'http_proxy':
                                    options['proxy'] = val
                    j += 1
                elif char == 'H':
                    j += 1
                elif char == 'D':
                    if j + 1 < len(opt_chars):
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                    j += 1
                elif char == 'I':
                    if j + 1 < len(opt_chars):
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                    j += 1
                elif char == 'X':
                    if j + 1 < len(opt_chars):
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                    j += 1
                elif char == 'Y':
                    if j + 1 < len(opt_chars):
                        j = len(opt_chars)
                    elif i + 1 < len(parts):
                        i += 1
                    j += 1
                elif char == 'K':
                    j += 1
                elif char == 'E':
                    j += 1
                elif char == 'k':
                    j += 1
                elif char == 'p':
                    j += 1
                elif char == 'L':
                    j += 1
                elif char == 'np':
                    j += 1
                elif char == '-':
                    j += 1
                    i += 1
                    urls.extend(parts[i:])
                    break
                else:
                    j += 1
            i += 1
            continue
        urls.append(part)
        i += 1
    if options['help']:
        return (
            'Write-Output "GNU Wget 1.21.1, a non-interactive network retriever.\n'
            'Usage: wget [OPTION]... [URL]...\n\n'
            'Mandatory arguments to long options are mandatory for short options too.\n\n'
            'Startup:\n'
            '  -V,  --version           display the version of Wget and exit.\n'
            '  -h,  --help              print this help.\n'
            '  -b,  --background        go to background after startup.\n'
            '  -e,  --execute=COMMAND   execute a `.wgetrc\'-style command.\n\n'
            'Logging and input file:\n'
            '  -o,  --output-file=FILE    log messages to FILE.\n'
            '  -a,  --append-output=FILE  append messages to FILE.\n'
            '  -d,  --debug               print lots of debugging information.\n'
            '  -q,  --quiet               quiet (no output).\n'
            '  -v,  --verbose             be verbose (this is the default).\n'
            '  -nv, --no-verbose          turn off verboseness, without being quiet.\n'
            '  -i,  --input-file=FILE     download URLs found in local or external FILE.\n\n'
            'Download:\n'
            '  -O,  --output-document=FILE      write documents to FILE.\n'
            '  -nc, --no-clobber                skip downloads that would download to existing files.\n'
            '  -c,  --continue                  resume getting a partially-downloaded file.\n'
            '  -N,  --timestamping              don\'t re-retrieve files unless newer than local.\n'
            '  -S,  --server-response           print server response.\n'
            '  -T,  --timeout=SECONDS           set all timeout values to SECONDS.\n'
            '  -t,  --tries=NUMBER              set number of retries to NUMBER (0 unlimits).\n'
            '  -w,  --wait=SECONDS              wait SECONDS between retrievals.\n'
            '       --user=USER                 set both ftp and http user to USER.\n'
            '       --password=PASS             set both ftp and http password to PASS.\n\n'
            'Directories:\n'
            '  -nd, --no-directories            don\'t create directories.\n'
            '  -P,  --directory-prefix=PREFIX   save files to PREFIX/...\n\n'
            'HTTP options:\n'
            '       --http-user=USER            set http user to USER.\n'
            '       --http-password=PASS        set http password to PASS.\n'
            '       --no-cache                  disallow server-cached data.\n'
            '       --no-cookies                don\'t use cookies.\n'
            '       --user-agent=AGENT          identify as AGENT instead of Wget/VERSION.\n'
            '       --header=STRING             insert STRING among the headers.\n'
            '       --post-data=STRING          use the POST method; send STRING as the data.\n'
            '       --post-file=FILE            use the POST method; send contents of FILE.\n'
            '       --method=HTTPMethod         use method \\"HTTPMethod\\" in the request.\n\n'
            'HTTPS (SSL/TLS) options:\n'
            '       --no-check-certificate      don\'t validate the server\'s certificate.\n'
            '       --certificate=FILE          client certificate file.\n'
            '       --private-key=FILE          private key file.\n'
            '       --ca-certificate=FILE       file with the bundle of CAs.\n\n'
            'Recursive download:\n'
            '  -r,  --recursive                 specify recursive download.\n'
            '  -l,  --level=NUMBER             maximum recursion depth (inf or 0 for infinite).\n'
            '  -A,  --accept=LIST              comma-separated list of accepted extensions.\n'
            '  -R,  --reject=LIST              comma-separated list of rejected extensions.\n'
            '  -m,  --mirror                   shortcut for -N -r -l inf --no-remove-listing."'
        )
    if options['version']:
        return 'Write-Output "GNU Wget 1.21.1 built on linux-gnu."'
    if not urls and not options['input_file']:
        return 'Write-Output "wget: missing URL"'
    return _build_wget_powershell_command(options, urls)
def _build_wget_powershell_command(options: Dict[str, Any], urls: List[str]) -> str:
    if not urls:
        if options['input_file']:
            return f'# wget with input file: {options["input_file"]}\nGet-Content "{options["input_file"]}" | ForEach-Object {{ Invoke-WebRequest -Uri $_ -OutFile (Split-Path $_ -Leaf) }}'
        return 'Write-Output "wget: missing URL"'
    if len(urls) > 1 or options['recursive'] or options['mirror']:
        return _build_multi_url_command(options, urls)
    url = urls[0]
    output_file = options['output_document']
    if not output_file:
        parsed = urlparse(url)
        output_file = parsed.path.split('/')[-1] if parsed.path else 'index.html'
        if not output_file:
            output_file = 'index.html'
    if options['directory_prefix']:
        output_file = f"{options['directory_prefix'].rstrip('/')}/{output_file}"
    cmd_parts = ['Invoke-WebRequest']
    cmd_parts.append(f'-Uri "{url}"')
    cmd_parts.append(f'-OutFile "{output_file}"')
    if options['method']:
        cmd_parts.append(f'-Method {options["method"]}')
    if options['post_data']:
        cmd_parts.append(f'-Body "{options["post_data"]}"')
    elif options['post_file']:
        cmd_parts.append(f'-Body (Get-Content "{options["post_file"]}" -Raw)')
    if options['headers']:
        headers_dict = {}
        for header in options['headers']:
            if ':' in header:
                key, value = header.split(':', 1)
                headers_dict[key.strip()] = value.strip()
        if headers_dict:
            headers_str = '; '.join([f'"{k}"="{v}"' for k, v in headers_dict.items()])
            cmd_parts.append(f'-Headers @{{{headers_str}}}')
    if options['user_agent']:
        cmd_parts.append(f'-UserAgent "{options["user_agent"]}"')
    if options['http_user'] and options['http_password']:
        cmd_parts.append(f'-Credential (New-Object System.Management.Automation.PSCredential ("{options["http_user"]}", (ConvertTo-SecureString "{options["http_password"]}" -AsPlainText -Force)))')
    elif options['user'] and options['password']:
        cmd_parts.append(f'-Credential (New-Object System.Management.Automation.PSCredential ("{options["user"]}", (ConvertTo-SecureString "{options["password"]}" -AsPlainText -Force)))')
    if options['timeout']:
        try:
            timeout_sec = int(options['timeout'])
            cmd_parts.append(f'-TimeoutSec {timeout_sec}')
        except ValueError:
            pass
    if options['no_check_certificate']:
        cmd_parts.append('-SkipCertificateCheck')
    if options['max_redirect'] is not None:
        try:
            max_redir = int(options['max_redirect'])
            if max_redir == 0:
                cmd_parts.append('-MaximumRedirection 0')
            else:
                cmd_parts.append(f'-MaximumRedirection {max_redir}')
        except ValueError:
            pass
    base_cmd = ' '.join(cmd_parts)
    if options['quiet']:
        base_cmd += ' | Out-Null'
    if options['continue']:
        base_cmd = f'# Note: Resume download may require additional handling\n{base_cmd}'
    if options['background']:
        base_cmd = f'Start-Job -ScriptBlock {{ {base_cmd} }}'
    return base_cmd
def _build_multi_url_command(options: Dict[str, Any], urls: List[str]) -> str:
    lines = ['# wget multi-URL download script']
    urls_str = ', '.join([f'"{url}"' for url in urls])
    lines.append(f'$urls = @({urls_str})')
    lines.append('')
    if options['directory_prefix']:
        lines.append(f'$outputDir = "{options["directory_prefix"]}"')
        lines.append('if (!(Test-Path $outputDir)) { New-Item -ItemType Directory -Path $outputDir -Force | Out-Null }')
    else:
        lines.append('$outputDir = "."')
    lines.append('')
    lines.append('foreach ($url in $urls) {')
    lines.append('    $fileName = Split-Path $url -Leaf')
    lines.append('    if ([string]::IsNullOrEmpty($fileName)) { $fileName = "index.html" }')
    lines.append('    $outFile = Join-Path $outputDir $fileName')
    lines.append('    ')
    lines.append('    try {')
    iw_params = ['        Invoke-WebRequest -Uri $url -OutFile $outFile']
    if options['user_agent']:
        iw_params.append(f' -UserAgent "{options["user_agent"]}"')
    if options['timeout']:
        try:
            timeout_sec = int(options['timeout'])
            iw_params.append(f' -TimeoutSec {timeout_sec}')
        except ValueError:
            pass
    if options['no_check_certificate']:
        iw_params.append(' -SkipCertificateCheck')
    if options['method']:
        iw_params.append(f' -Method {options["method"]}')
    if options['quiet']:
        iw_params.append(' | Out-Null')
    lines.append(''.join(iw_params))
    lines.append('    } catch {')
    lines.append('        Write-Error "Failed to download: $url"')
    lines.append('    }')
    lines.append('}')
    return "\n".join(lines)
if __name__ == "__main__":
    test_cases = [
        "wget http://example.com/file.txt",
        "wget https://example.com/file.zip",
        "wget ftp://example.com/file.txt",
        "wget -O output.txt http://example.com/file.txt",
        "wget --output-document=output.txt http://example.com/file.txt",
        "wget -P /tmp http://example.com/file.txt",
        "wget --directory-prefix=/tmp http://example.com/file.txt",
        "wget -q http://example.com/file.txt",
        "wget --quiet http://example.com/file.txt",
        "wget -v http://example.com/file.txt",
        "wget --verbose http://example.com/file.txt",
        "wget -c http://example.com/file.txt",
        "wget --continue http://example.com/file.txt",
        "wget -N http://example.com/file.txt",
        "wget --timestamping http://example.com/file.txt",
        "wget -nc http://example.com/file.txt",
        "wget --no-clobber http://example.com/file.txt",
        "wget -T 30 http://example.com/file.txt",
        "wget --timeout=30 http://example.com/file.txt",
        "wget -t 5 http://example.com/file.txt",
        "wget --tries=5 http://example.com/file.txt",
        "wget -U Mozilla http://example.com/file.txt",
        "wget --user-agent=Mozilla http://example.com/file.txt",
        'wget --header="X-Custom: value" http://example.com/file.txt',
        'wget --post-data="name=value" http://example.com/form',
        'wget --post-file=data.txt http://example.com/form',
        "wget --method=POST http://example.com/api",
        "wget --http-user=user --http-password=pass http://example.com/file.txt",
        "wget --user=user --password=pass http://example.com/file.txt",
        "wget --ftp-user=user --ftp-password=pass ftp://example.com/file.txt",
        "wget --no-check-certificate https://example.com/file.txt",
        "wget --certificate=cert.pem https://example.com/file.txt",
        "wget --private-key=key.pem https://example.com/file.txt",
        "wget --ca-certificate=ca.pem https://example.com/file.txt",
        "wget --max-redirect=5 http://example.com/file.txt",
        "wget --no-proxy http://example.com/file.txt",
        "wget -e use_proxy=yes -e http_proxy=proxy:8080 http://example.com/file.txt",
        "wget -r http://example.com/",
        "wget --recursive http://example.com/",
        "wget -r -l 2 http://example.com/",
        "wget --recursive --level=2 http://example.com/",
        "wget -nd http://example.com/",
        "wget --no-directories http://example.com/",
        "wget -A '*.txt' http://example.com/",
        "wget --accept='*.txt' http://example.com/",
        "wget -R '*.jpg' http://example.com/",
        "wget --reject='*.jpg' http://example.com/",
        "wget -m http://example.com/",
        "wget --mirror http://example.com/",
        "wget --spider http://example.com/",
        "wget -i urls.txt",
        "wget --input-file=urls.txt",
        "wget --delete-after http://example.com/",
        "wget -S http://example.com/",
        "wget --server-response http://example.com/",
        "wget --save-headers http://example.com/",
        "wget --content-disposition http://example.com/",
        "wget --trust-server-names http://example.com/",
        "wget --limit-rate=100k http://example.com/",
        "wget --dns-timeout=10 http://example.com/",
        "wget --connect-timeout=10 http://example.com/",
        "wget --read-timeout=10 http://example.com/",
        "wget --bind-address=192.168.1.1 http://example.com/",
        "wget -4 http://example.com/",
        "wget --inet4-only http://example.com/",
        "wget -6 http://example.com/",
        "wget --inet6-only http://example.com/",
        "wget --retry-connrefused http://example.com/",
        "wget -w 5 http://example.com/",
        "wget --wait=5 http://example.com/",
        "wget --waitretry=10 http://example.com/",
        "wget --random-wait http://example.com/",
        "wget --passive-ftp ftp://example.com/file.txt",
        "wget --active-ftp ftp://example.com/file.txt",
        "wget --no-glob ftp://example.com/file.txt",
        "wget --prefer-family=IPv4 http://example.com/",
        "wget -a log.txt http://example.com/",
        "wget --append-output=log.txt http://example.com/",
        "wget -o log.txt http://example.com/",
        "wget --output-file=log.txt http://example.com/",
        "wget -d http://example.com/",
        "wget --debug http://example.com/",
        "wget -b http://example.com/",
        "wget --background http://example.com/",
        "wget --help",
        "wget --version",
        "wget /O output.txt http://example.com/file.txt",
        "wget /q http://example.com/file.txt",
        "wget /c http://example.com/file.txt",
        "wget /T 30 http://example.com/file.txt",
        "wget /t 5 http://example.com/file.txt",
        "wget /r http://example.com/",
        "wget /P /tmp http://example.com/file.txt",
        "wget http://example.com/file1.txt http://example.com/file2.txt",
        "",
        "wget",
    ]
    for test in test_cases:
        result = _convert_wget(test)
        print(f"Input:  {test}")
        print(f"Output: {result}")
        print()
def _convert_whoami(cmd: str) -> str:
    if not cmd or not cmd.strip():
        return '$env:USERNAME'
    parts = _parse_command_line(cmd)
    if not parts:
        return '$env:USERNAME'
    if parts[0] in ('whoami', '/bin/whoami', '/usr/bin/whoami'):
        parts = parts[1:]
    if not parts:
        return '$env:USERNAME'
    show_help = False
    show_version = False
    i = 0
    while i < len(parts):
        part = parts[i]
        if part == '--':
            break
        if part.startswith('/') and len(part) >= 2:
            if len(part) == 2 and part[1].isalpha():
                part = '-' + part[1:]
            elif len(part) > 2 and part[1].isalpha():
                part = '--' + part[1:]
        if part.startswith('--'):
            long_opt = part[2:]
            if long_opt == 'help':
                show_help = True
                i += 1
                continue
            elif long_opt == 'version':
                show_version = True
                i += 1
                continue
            i += 1
            continue
        if part.startswith('-') and len(part) > 1:
            opt_chars = part[1:]
            for char in opt_chars:
                if char == 'h':
                    show_help = True
                elif char == 'v':
                    show_version = True
            i += 1
            continue
        i += 1
    if show_help:
        return (
            'Write-Output "Usage: whoami [OPTION]...\n'
            'Print the user name associated with the current effective user ID.\n'
            'Same as id -un.\n\n'
            '  --help     display this help and exit\n'
            '  --version  output version information and exit"'
        )
    if show_version:
        return 'Write-Output "whoami (GNU coreutils) 8.32"'
    return '$env:USERNAME'
def _convert_xargs(cmd: str) -> str:
    if not cmd or not cmd.strip():
        return '$input | ForEach-Object { echo $_ }'
    parts = _parse_command_line(cmd)
    if not parts:
        return '$input | ForEach-Object { echo $_ }'
    if parts[0] in ('xargs', '/bin/xargs', '/usr/bin/xargs'):
        parts = parts[1:]
    if not parts:
        return '$input | ForEach-Object { echo $_ }'
    options: Dict[str, Any] = {
        'null_terminated': False,
        'arg_file': None,
        'delimiter': None,
        'eof_str': None,
        'replace_str': None,
        'max_lines': None,
        'max_args': None,
        'max_procs': 1,
        'interactive': False,
        'no_run_if_empty': False,
        'max_chars': None,
        'verbose': False,
        'exit_on_size': False,
        'show_limits': False,
        'show_help': False,
        'show_version': False,
    }
    command_parts: List[str] = []
    i = 0
    while i < len(parts):
        part = parts[i]
        if part == '--':
            command_parts = parts[i + 1:]
            break
        if part.startswith('/') and len(part) >= 2:
            if len(part) == 2 and (part[1].isalpha() or part[1].isdigit()):
                part = '-' + part[1:]
            elif len(part) > 2 and part[1].isalpha():
                part = '--' + part[1:]
        if part.startswith('--'):
            long_opt = part[2:]
            if long_opt == 'help':
                options['show_help'] = True
                i += 1
                continue
            if long_opt == 'version':
                options['show_version'] = True
                i += 1
                continue
            if long_opt == 'null':
                options['null_terminated'] = True
                i += 1
                continue
            if long_opt == 'show-limits':
                options['show_limits'] = True
                i += 1
                continue
            if long_opt == 'interactive':
                options['interactive'] = True
                i += 1
                continue
            if long_opt == 'verbose':
                options['verbose'] = True
                i += 1
                continue
            if long_opt == 'exit':
                options['exit_on_size'] = True
                i += 1
                continue
            if long_opt == 'no-run-if-empty':
                options['no_run_if_empty'] = True
                i += 1
                continue
            if long_opt == 'open-tty':
                i += 1
                continue
            if '=' in long_opt:
                opt_name, opt_value = long_opt.split('=', 1)
                if opt_name in ('arg-file', 'a'):
                    options['arg_file'] = opt_value
                elif opt_name in ('delimiter', 'd'):
                    options['delimiter'] = _parse_delimiter(opt_value)
                elif opt_name == 'eof':
                    options['eof_str'] = opt_value
                elif opt_name in ('replace', 'I'):
                    options['replace_str'] = opt_value if opt_value else '{}'
                    if options['max_lines'] is None:
                        options['max_lines'] = 1
                elif opt_name in ('max-lines', 'L'):
                    try:
                        options['max_lines'] = int(opt_value)
                    except ValueError:
                        options['max_lines'] = 1
                elif opt_name in ('max-args', 'n'):
                    try:
                        options['max_args'] = int(opt_value)
                    except ValueError:
                        pass
                elif opt_name in ('max-procs', 'P'):
                    try:
                        options['max_procs'] = int(opt_value)
                    except ValueError:
                        options['max_procs'] = 1
                elif opt_name in ('max-chars', 's'):
                    try:
                        options['max_chars'] = int(opt_value)
                    except ValueError:
                        pass
                elif opt_name == 'process-slot-var':
                    pass
                i += 1
                continue
            i += 1
            continue
        if part.startswith('-') and len(part) > 1:
            opt_chars = part[1:]
            j = 0
            while j < len(opt_chars):
                char = opt_chars[j]
                if char == '0':
                    options['null_terminated'] = True
                    j += 1
                elif char == 'a':
                    if j + 1 < len(opt_chars):
                        options['arg_file'] = opt_chars[j + 1:]
                        break
                    elif i + 1 < len(parts):
                        i += 1
                        options['arg_file'] = parts[i]
                    j += 1
                elif char == 'd':
                    if j + 1 < len(opt_chars):
                        options['delimiter'] = _parse_delimiter(opt_chars[j + 1:])
                        break
                    elif i + 1 < len(parts):
                        i += 1
                        options['delimiter'] = _parse_delimiter(parts[i])
                    j += 1
                elif char == 'E':
                    if j + 1 < len(opt_chars):
                        options['eof_str'] = opt_chars[j + 1:]
                        break
                    elif i + 1 < len(parts):
                        i += 1
                        options['eof_str'] = parts[i]
                    j += 1
                elif char == 'e':
                    if j + 1 < len(opt_chars):
                        options['eof_str'] = opt_chars[j + 1:]
                        break
                    elif i + 1 < len(parts) and not parts[i + 1].startswith('-'):
                        i += 1
                        options['eof_str'] = parts[i]
                    else:
                        options['eof_str'] = None
                    j += 1
                elif char == 'I':
                    if j + 1 < len(opt_chars):
                        options['replace_str'] = opt_chars[j + 1:]
                    elif i + 1 < len(parts):
                        i += 1
                        options['replace_str'] = parts[i]
                    else:
                        options['replace_str'] = '{}'
                    if options['max_lines'] is None:
                        options['max_lines'] = 1
                    options['exit_on_size'] = True
                    j += 1
                elif char == 'i':
                    if j + 1 < len(opt_chars):
                        options['replace_str'] = opt_chars[j + 1:]
                        break
                    else:
                        options['replace_str'] = '{}'
                    if options['max_lines'] is None:
                        options['max_lines'] = 1
                    options['exit_on_size'] = True
                    j += 1
                elif char == 'L':
                    if j + 1 < len(opt_chars):
                        try:
                            options['max_lines'] = int(opt_chars[j + 1:])
                        except ValueError:
                            options['max_lines'] = 1
                        break
                    elif i + 1 < len(parts):
                        i += 1
                        try:
                            options['max_lines'] = int(parts[i])
                        except ValueError:
                            options['max_lines'] = 1
                    j += 1
                elif char == 'l':
                    if j + 1 < len(opt_chars):
                        try:
                            options['max_lines'] = int(opt_chars[j + 1:])
                        except ValueError:
                            options['max_lines'] = 1
                        break
                    else:
                        options['max_lines'] = 1
                    j += 1
                elif char == 'n':
                    if j + 1 < len(opt_chars):
                        try:
                            options['max_args'] = int(opt_chars[j + 1:])
                        except ValueError:
                            pass
                        break
                    elif i + 1 < len(parts):
                        i += 1
                        try:
                            options['max_args'] = int(parts[i])
                        except ValueError:
                            pass
                    j += 1
                elif char == 'P':
                    if j + 1 < len(opt_chars):
                        try:
                            options['max_procs'] = int(opt_chars[j + 1:])
                        except ValueError:
                            options['max_procs'] = 1
                        break
                    elif i + 1 < len(parts):
                        i += 1
                        try:
                            options['max_procs'] = int(parts[i])
                        except ValueError:
                            options['max_procs'] = 1
                    j += 1
                elif char == 'p':
                    options['interactive'] = True
                    j += 1
                elif char == 'r':
                    options['no_run_if_empty'] = True
                    j += 1
                elif char == 's':
                    if j + 1 < len(opt_chars):
                        try:
                            options['max_chars'] = int(opt_chars[j + 1:])
                        except ValueError:
                            pass
                        break
                    elif i + 1 < len(parts):
                        i += 1
                        try:
                            options['max_chars'] = int(parts[i])
                        except ValueError:
                            pass
                    j += 1
                elif char == 't':
                    options['verbose'] = True
                    j += 1
                elif char == 'x':
                    options['exit_on_size'] = True
                    j += 1
                elif char == 'o':
                    j += 1
                else:
                    j += 1
            i += 1
            continue
        command_parts = parts[i:]
        break
    return _build_xargs_powershell_command(options, command_parts)
def _parse_delimiter(delim: str) -> str:
    if not delim:
        return ' '
    escape_map = {
        '\\n': '\n',
        '\\t': '\t',
        '\\r': '\r',
        '\\0': '\0',
        '\\\\': '\\',
    }
    for escape, char in escape_map.items():
        if delim == escape:
            return char
    if delim.startswith('\\0') and len(delim) > 2:
        try:
            return chr(int(delim[2:], 8))
        except ValueError:
            pass
    elif delim.startswith('\\x') and len(delim) > 2:
        try:
            return chr(int(delim[2:], 16))
        except ValueError:
            pass
    return delim[0]
def _build_xargs_powershell_command(options: Dict[str, Any], command_parts: List[str]) -> str:
    if options.get('show_help'):
        return ('Write-Output "xargs - Build and execute command lines from standard input\n'
                'Usage: xargs [OPTION]... [COMMAND [INITIAL-ARGS]]\n'
                'Options:\n'
                '  -0, --null              Input items are null-terminated\n'
                '  -a FILE, --arg-file=FILE  Read items from FILE instead of stdin\n'
                '  -d DELIM, --delimiter=DELIM  Input items terminated by DELIM\n'
                '  -E EOF-STR              Set end-of-file string\n'
                '  -I REPLACE-STR          Replace REPLACE-STR with input items\n'
                '  -L MAX-LINES, --max-lines=MAX-LINES  Use at most MAX-LINES per command\n'
                '  -n MAX-ARGS, --max-args=MAX-ARGS  Use at most MAX-ARGS arguments per command\n'
                '  -P MAX-PROCS, --max-procs=MAX-PROCS  Run up to MAX-PROCS processes in parallel\n'
                '  -p, --interactive       Prompt user before running each command\n'
                '  -r, --no-run-if-empty   Don\'t run command if stdin is empty\n'
                '  -s MAX-CHARS, --max-chars=MAX-CHARS  Limit command line length\n'
                '  -t, --verbose           Print command line before executing\n'
                '  -x, --exit              Exit if size limit is exceeded\n'
                '      --show-limits       Display system limits\n'
                '      --help              Display help\n'
                '      --version           Output version information"')
    if options.get('show_version'):
        return 'Write-Output "xargs (GNU findutils) 4.9.0"'
    if options.get('show_limits'):
        return ('Write-Output "These are the system limits for xargs:\n'
                'Maximum command line length: 2097152 bytes\n'
                'Maximum command line length for exec: 2097152 bytes\n'
                'Maximum number of arguments: 2097152 / sizeof(char*)\n'
                'Maximum length of argument: 131072 bytes"')
    input_source = '$input'
    if options.get('arg_file'):
        arg_file = options['arg_file']
        if ' ' in arg_file and not (arg_file.startswith('"') or arg_file.startswith("'")):
            arg_file = f'"{arg_file}"'
        input_source = f'Get-Content {arg_file}'
    delimiter = options.get('delimiter')
    if options.get('null_terminated'):
        if input_source == '$input':
            input_source = '$input -Split "\\0"'
        else:
            input_source = f'({input_source}) -Split "\\0"'
    elif delimiter and delimiter != '\n':
        delim_str = delimiter.replace('\\', '\\\\').replace('"', '\\"')
        if input_source == '$input':
            input_source = f'$input -Split "{delim_str}"'
        else:
            input_source = f'({input_source}) -Split "{delim_str}"'
    if not command_parts:
        command = 'echo $_'
    else:
        command = _build_command_string(command_parts, options.get('replace_str'))
    notes: List[str] = []
    pipeline_parts: List[str] = [input_source]
    if options.get('no_run_if_empty'):
        pipeline_parts.append('Where-Object { $_ }')
    if options.get('interactive'):
        notes.append('NOTE: -p (interactive) not directly supported in PowerShell')
    if options.get('verbose'):
        notes.append('NOTE: -t (verbose) not directly supported in PowerShell')
    if options.get('max_procs') and options['max_procs'] != 1:
        notes.append(f"NOTE: -P {options['max_procs']} (parallel processes) not directly supported")
    if options.get('max_args'):
        notes.append(f"NOTE: -n {options['max_args']} (max-args) not directly supported")
    if options.get('max_lines') and options['max_lines'] != 1:
        notes.append(f"NOTE: -L {options['max_lines']} (max-lines) not directly supported")
    if options.get('max_chars'):
        notes.append(f"NOTE: -s {options['max_chars']} (max-chars) not directly supported")
    if options.get('exit_on_size') and not options.get('replace_str'):
        notes.append('NOTE: -x (exit-on-size) not directly supported')
    if options.get('eof_str'):
        notes.append(f"NOTE: -E '{options['eof_str']}' (eof-str) not directly supported")
    pipeline_parts.append(f'ForEach-Object {{ {command} }}')
    result = ' | '.join(pipeline_parts)
    if notes:
        result += '  # ' + '; '.join(notes)
    return result
def _build_command_string(command_parts: List[str], replace_str: Optional[str]) -> str:
    if not command_parts:
        return 'echo $_'
    quoted_parts = []
    for part in command_parts:
        if ' ' in part and not (part.startswith('"') or part.startswith("'")):
            quoted_parts.append(f'"{part}"')
        else:
            quoted_parts.append(part)
    command_str = ' '.join(quoted_parts)
    if replace_str:
        command_str = command_str.replace(f'"{replace_str}"', '$_')
        command_str = command_str.replace(f"'{replace_str}'", '$_')
        command_str = command_str.replace(replace_str, '$_')
    else:
        command_str += ' $_'
    return command_str
if __name__ == "__main__":
    test_cases = [
        "xargs",
        "xargs rm",
        "xargs -n 1 echo",
        "xargs -I {} cp {} /dest",
        "xargs -0 rm",
        "xargs -a file.txt cat",
        "xargs -r rm",
        "xargs /n 5 echo",
        "xargs -I {} echo 'Processing: {}'",
        "xargs -d '\\n' cat",
        "xargs -p rm",
        "xargs -t echo",
        "xargs -P 4 gzip",
        "xargs --help",
        "xargs --version",
        "xargs --show-limits",
        "xargs -L 1 echo",
        "xargs -l echo",
        "xargs -s 1000 echo",
        "xargs -E END echo",
        "xargs -i mv {} {}.bak",
    ]
    for test in test_cases:
        result = _convert_xargs(test)
        print(f"Input:  {test}")
        print(f"Output: {result}")
        print()
def _convert_yes(cmd: str) -> str:
    if not cmd or not cmd.strip():
        return 'while ($true) { Write-Output "y" }'
    parts = _parse_command_line(cmd)
    if not parts:
        return 'while ($true) { Write-Output "y" }'
    if parts[0] in ('yes', '/bin/yes', '/usr/bin/yes'):
        parts = parts[1:]
    if not parts:
        return 'while ($true) { Write-Output "y" }'
    strings: List[str] = []
    show_help = False
    show_version = False
    i = 0
    while i < len(parts):
        part = parts[i]
        if part.startswith('/') and len(part) >= 2:
            part = '-' + part[1:]
        if part == '--':
            strings.extend(parts[i + 1:])
            break
        if part.startswith('--'):
            opt_name = part[2:]
            if opt_name == 'help':
                show_help = True
            elif opt_name == 'version':
                show_version = True
            i += 1
            continue
        if part.startswith('-') and len(part) > 1:
            opt_chars = part[1:]
            for char in opt_chars:
                if char == 'h':
                    show_help = True
                elif char == 'v':
                    show_version = True
            i += 1
            continue
        strings.append(part)
        i += 1
    if show_help:
        return (
            'Write-Output "yes - output a string repeatedly until killed\n'
            'Usage: yes [STRING]...\n'
            '  or:  yes OPTION\n'
            'Repeatedly output a line with all specified STRING(s), or `y`.\n\n'
            'Options:\n'
            '  --help     Display this help and exit\n'
            '  --version  Output version information and exit"'
        )
    if show_version:
        return 'Write-Output "yes (GNU coreutils)"'
    if not strings:
        output_string = 'y'
    else:
        output_string = ' '.join(strings)
    output_string = output_string.replace('"', '`"')
    return f'while ($true) {{ Write-Output "{output_string}" }}'
def _convert_zip(cmd: str) -> str:
    if not cmd or not cmd.strip():
        return 'Write-Output "zip: nothing to do!"'
    parts = _parse_command_line(cmd)
    if not parts:
        return 'Write-Output "zip: nothing to do!"'
    if parts[0] in ('zip', '/bin/zip', '/usr/bin/zip'):
        parts = parts[1:]
    if not parts:
        return 'Write-Output "zip: nothing to do!"'
    options: Dict[str, Any] = {
        'compression_level': None,
        'ascii': False,
        'temp_path': None,
        'entry_comments': False,
        'delete': False,
        'no_dir_entries': False,
        'encrypt': False,
        'freshen': False,
        'fix': False,
        'fixfix': False,
        'grow': False,
        'show_help': False,
        'include': [],
        'junk_paths': False,
        'junk_sfx': False,
        'dos_names': False,
        'to_crlf': False,
        'from_crlf': False,
        'license': False,
        'move': False,
        'no_compress_suffixes': [],
        'latest': False,
        'paths': True,
        'password': None,
        'quiet': False,
        'recursive': False,
        'system_hidden': False,
        'after_date': None,
        'test': False,
        'update': False,
        'verbose': False,
        'show_version': False,
        'exclude': [],
        'no_extra': False,
        'symlinks': False,
        'archive_comment': False,
    }
    files: List[str] = []
    archive_file: Optional[str] = None
    i = 0
    while i < len(parts):
        part = parts[i]
        if part == '--':
            files.extend(parts[i + 1:])
            break
        if part.startswith('/') and len(part) >= 2:
            if len(part) == 2 and part[1].isdigit():
                part = '-' + part[1:]
            elif len(part) == 2 and part[1].isalpha():
                part = '-' + part[1:]
            elif len(part) > 2 and part[1].isalpha():
                part = '--' + part[1:]
        if part.startswith('--'):
            long_opt = part[2:]
            if '=' in long_opt:
                opt_name, opt_value = long_opt.split('=', 1)
                if opt_name == 'temp-path':
                    options['temp_path'] = opt_value
                elif opt_name == 'password':
                    options['password'] = opt_value
                elif opt_name == 'after-date':
                    options['after_date'] = opt_value
                elif opt_name == 'include':
                    options['include'].append(opt_value)
                elif opt_name == 'exclude':
                    options['exclude'].append(opt_value)
                i += 1
                continue
            if long_opt == 'help':
                options['show_help'] = True
                i += 1
                continue
            elif long_opt == 'version':
                options['show_version'] = True
                i += 1
                continue
            elif long_opt == 'license':
                options['license'] = True
                i += 1
                continue
            elif long_opt == 'ascii':
                options['ascii'] = True
                i += 1
                continue
            elif long_opt == 'entry-comments':
                options['entry_comments'] = True
                i += 1
                continue
            elif long_opt == 'delete':
                options['delete'] = True
                i += 1
                continue
            elif long_opt == 'no-dir-entries':
                options['no_dir_entries'] = True
                i += 1
                continue
            elif long_opt == 'encrypt':
                options['encrypt'] = True
                i += 1
                continue
            elif long_opt == 'freshen':
                options['freshen'] = True
                i += 1
                continue
            elif long_opt == 'fix':
                options['fix'] = True
                i += 1
                continue
            elif long_opt == 'fixfix':
                options['fixfix'] = True
                i += 1
                continue
            elif long_opt == 'grow':
                options['grow'] = True
                i += 1
                continue
            elif long_opt == 'junk-paths':
                options['junk_paths'] = True
                i += 1
                continue
            elif long_opt == 'junk-sfx':
                options['junk_sfx'] = True
                i += 1
                continue
            elif long_opt == 'DOS-names':
                options['dos_names'] = True
                i += 1
                continue
            elif long_opt == 'to-crlf':
                options['to_crlf'] = True
                i += 1
                continue
            elif long_opt == 'from-crlf':
                options['from_crlf'] = True
                i += 1
                continue
            elif long_opt == 'move':
                options['move'] = True
                i += 1
                continue
            elif long_opt == 'latest':
                options['latest'] = True
                i += 1
                continue
            elif long_opt == 'paths':
                options['paths'] = True
                i += 1
                continue
            elif long_opt == 'quiet':
                options['quiet'] = True
                i += 1
                continue
            elif long_opt == 'recurse-paths':
                options['recursive'] = True
                i += 1
                continue
            elif long_opt == 'system-hidden':
                options['system_hidden'] = True
                i += 1
                continue
            elif long_opt == 'test':
                options['test'] = True
                i += 1
                continue
            elif long_opt == 'update':
                options['update'] = True
                i += 1
                continue
            elif long_opt == 'verbose':
                options['verbose'] = True
                i += 1
                continue
            elif long_opt == 'no-extra':
                options['no_extra'] = True
                i += 1
                continue
            elif long_opt == 'symlinks':
                options['symlinks'] = True
                i += 1
                continue
            elif long_opt == 'archive-comment':
                options['archive_comment'] = True
                i += 1
                continue
            elif long_opt == 'temp-path':
                if i + 1 < len(parts):
                    i += 1
                    options['temp_path'] = parts[i]
                i += 1
                continue
            elif long_opt == 'password':
                if i + 1 < len(parts):
                    i += 1
                    options['password'] = parts[i]
                i += 1
                continue
            elif long_opt == 'after-date':
                if i + 1 < len(parts):
                    i += 1
                    options['after_date'] = parts[i]
                i += 1
                continue
            elif long_opt == 'include':
                if i + 1 < len(parts):
                    i += 1
                    options['include'].append(parts[i])
                i += 1
                continue
            elif long_opt == 'exclude':
                if i + 1 < len(parts):
                    i += 1
                    options['exclude'].append(parts[i])
                i += 1
                continue
            i += 1
            continue
        if part.startswith('-') and len(part) > 1:
            opt_chars = part[1:]
            j = 0
            while j < len(opt_chars):
                char = opt_chars[j]
                if char == '0':
                    options['compression_level'] = 0
                    j += 1
                elif char == '1':
                    options['compression_level'] = 1
                    j += 1
                elif char == '2':
                    options['compression_level'] = 2
                    j += 1
                elif char == '3':
                    options['compression_level'] = 3
                    j += 1
                elif char == '4':
                    options['compression_level'] = 4
                    j += 1
                elif char == '5':
                    options['compression_level'] = 5
                    j += 1
                elif char == '6':
                    options['compression_level'] = 6
                    j += 1
                elif char == '7':
                    options['compression_level'] = 7
                    j += 1
                elif char == '8':
                    options['compression_level'] = 8
                    j += 1
                elif char == '9':
                    options['compression_level'] = 9
                    j += 1
                elif char == 'a':
                    options['ascii'] = True
                    j += 1
                elif char == 'b':
                    if j + 1 < len(opt_chars):
                        options['temp_path'] = opt_chars[j + 1:]
                        break
                    elif i + 1 < len(parts):
                        i += 1
                        options['temp_path'] = parts[i]
                    j += 1
                elif char == 'c':
                    options['entry_comments'] = True
                    j += 1
                elif char == 'd':
                    options['delete'] = True
                    j += 1
                elif char == 'D':
                    options['no_dir_entries'] = True
                    j += 1
                elif char == 'e':
                    options['encrypt'] = True
                    j += 1
                elif char == 'f':
                    options['freshen'] = True
                    j += 1
                elif char == 'F':
                    if j + 1 < len(opt_chars) and opt_chars[j + 1] == 'F':
                        options['fixfix'] = True
                        j += 2
                    else:
                        options['fix'] = True
                        j += 1
                elif char == 'g':
                    options['grow'] = True
                    j += 1
                elif char == 'h':
                    options['show_help'] = True
                    j += 1
                elif char == 'i':
                    i += 1
                    while i < len(parts) and not parts[i].startswith('-') and not parts[i].startswith('/'):
                        options['include'].append(parts[i])
                        i += 1
                    j = len(opt_chars)
                    continue
                elif char == 'j':
                    options['junk_paths'] = True
                    j += 1
                elif char == 'J':
                    options['junk_sfx'] = True
                    j += 1
                elif char == 'k':
                    options['dos_names'] = True
                    j += 1
                elif char == 'l':
                    if j + 1 < len(opt_chars) and opt_chars[j + 1] == 'l':
                        options['from_crlf'] = True
                        j += 2
                    else:
                        options['to_crlf'] = True
                        j += 1
                elif char == 'L':
                    options['license'] = True
                    j += 1
                elif char == 'm':
                    options['move'] = True
                    j += 1
                elif char == 'n':
                    if j + 1 < len(opt_chars):
                        suffixes = opt_chars[j + 1:].split(':')
                        options['no_compress_suffixes'].extend(suffixes)
                        break
                    elif i + 1 < len(parts):
                        i += 1
                        suffixes = parts[i].split(':')
                        options['no_compress_suffixes'].extend(suffixes)
                    j += 1
                elif char == 'o':
                    options['latest'] = True
                    j += 1
                elif char == 'p':
                    options['paths'] = True
                    j += 1
                elif char == 'P':
                    if j + 1 < len(opt_chars):
                        options['password'] = opt_chars[j + 1:]
                        break
                    elif i + 1 < len(parts):
                        i += 1
                        options['password'] = parts[i]
                    j += 1
                elif char == 'q':
                    options['quiet'] = True
                    j += 1
                elif char == 'r':
                    options['recursive'] = True
                    j += 1
                elif char == 'S':
                    options['system_hidden'] = True
                    j += 1
                elif char == 't':
                    if j + 1 < len(opt_chars):
                        options['after_date'] = opt_chars[j + 1:]
                        break
                    elif i + 1 < len(parts):
                        i += 1
                        options['after_date'] = parts[i]
                    j += 1
                elif char == 'T':
                    options['test'] = True
                    j += 1
                elif char == 'u':
                    options['update'] = True
                    j += 1
                elif char == 'v':
                    options['verbose'] = True
                    j += 1
                elif char == 'V':
                    options['show_version'] = True
                    j += 1
                elif char == 'x':
                    i += 1
                    while i < len(parts) and not parts[i].startswith('-') and not parts[i].startswith('/'):
                        options['exclude'].append(parts[i])
                        i += 1
                    j = len(opt_chars)
                    continue
                elif char == 'X':
                    options['no_extra'] = True
                    j += 1
                elif char == 'y':
                    options['symlinks'] = True
                    j += 1
                elif char == 'z':
                    options['archive_comment'] = True
                    j += 1
                else:
                    j += 1
            i += 1
            continue
        if archive_file is None:
            archive_file = part
            i += 1
            continue
        files.append(part)
        i += 1
    return _build_zip_powershell_command(options, archive_file, files)
def _build_zip_powershell_command(options: Dict[str, Any], archive_file: Optional[str], files: List[str]) -> str:
    if options.get('show_help'):
        return (
            'Write-Output "Usage: zip [-options] [-b path] [-t mmddyyyy] [-n suffixes] [zipfile list] [-xi list]\n'
            '  The default action is to add or replace zipfile entries from list, which can include the special name - to compress standard input.\n'
            '  If zipfile and list are omitted, zip compresses stdin to stdout.\n'
            '\n'
            '  -0      store only\n'
            '  -1      compress faster\n'
            '  -9      compress better\n'
            '  -a      convert line endings\n'
            '  -b path use path for temporary files\n'
            '  -c      add one-line comments for each file\n'
            '  -d      delete entries in zipfile\n'
            '  -D      do not add directory entries\n'
            '  -e      encrypt entries\n'
            '  -f      freshen: only changed files\n'
            '  -F      fix zipfile (-FF try harder)\n'
            '  -g      grow (append to) zipfile\n'
            '  -h      show this help\n'
            '  -i      include following names\n'
            '  -j      junk (don\'t record) directory names\n'
            '  -J      junk archive suffix\n'
            '  -k      use 8.3 DOS names\n'
            '  -l      translate LF to CR LF\n'
            '  -ll     translate CR LF to LF\n'
            '  -L      show license\n'
            '  -m      move into zipfile (delete OS files)\n'
            '  -n      don\'t compress these suffixes\n'
            '  -o      set modified time to latest entry\n'
            '  -p      store relative path names\n'
            '  -P      use password to encrypt\n'
            '  -q      quiet operation\n'
            '  -r      recurse into directories\n'
            '  -S      include system and hidden files\n'
            '  -t      do not operate on files modified after date\n'
            '  -T      test archive integrity\n'
            '  -u      update entries\n'
            '  -v      verbose mode\n'
            '  -V      show version\n'
            '  -x      exclude following names\n'
            '  -X      do not save extra file attributes\n'
            '  -y      store symbolic links\n'
            '  -z      add archive comment"'
        )
    if options.get('show_version'):
        return 'Write-Output "Zip 3.0"'
    if options.get('license'):
        return (
            'Write-Output "Copyright (c) 1990-2008 Info-ZIP - Type \"zip -L\" for software license.\n'
            'This is Zip 3.0 (July 5th 2008), by Info-ZIP.\n'
            'Currently maintained by E. Gordon. Please send bug reports to the authors using the web page at www.info-zip.org."'
        )
    if archive_file is None:
        return 'Write-Output "zip: nothing to do! (archive.zip)"'
    quoted_archive = archive_file
    if ' ' in archive_file and not (archive_file.startswith('"') or archive_file.startswith("'")):
        quoted_archive = f'"{archive_file}"'
    if options.get('test'):
        return (
            f'$archive = {quoted_archive}; '
            'try { '
            'Add-Type -AssemblyName System.IO.Compression.FileSystem; '
            '$zip = [System.IO.Compression.ZipFile]::OpenRead($archive); '
            '$zip.Dispose(); '
            'Write-Output "test of $archive OK" '
            '} catch { '
            'Write-Error "test of $archive FAILED" '
            '}'
        )
    if options.get('delete'):
        if not files:
            return 'Write-Output "zip: nothing to delete!"'
        entries_str = ', '.join([f'"{f}"' for f in files])
        return (
            f'$archive = {quoted_archive}; '
            f'$entriesToRemove = @({entries_str}); '
            'Add-Type -AssemblyName System.IO.Compression.FileSystem; '
            '$zip = [System.IO.Compression.ZipFile]::Open($archive, "Update"); '
            'foreach ($entryName in $entriesToRemove) { '
            '$entry = $zip.GetEntry($entryName); '
            'if ($entry) { $entry.Delete() } '
            '}; '
            '$zip.Dispose()'
        )
    if options.get('fix') or options.get('fixfix'):
        return (
            f'$archive = {quoted_archive}; '
            'Write-Output "Archive fixing is not fully supported in PowerShell. Consider using external tools."'
        )
    if not files and not options.get('test'):
        return 'Write-Output "zip: nothing to do!"'
    quoted_files = []
    for f in files:
        if ' ' in f and not (f.startswith('"') or f.startswith("'")):
            quoted_files.append(f'"{f}"')
        else:
            quoted_files.append(f)
    files_str = ', '.join(quoted_files)
    if options.get('junk_paths'):
        compression_level = options.get('compression_level')
        if compression_level is not None and compression_level >= 6:
            level_str = '[System.IO.Compression.CompressionLevel]::Optimal'
        elif compression_level is not None and compression_level > 0:
            level_str = '[System.IO.Compression.CompressionLevel]::Fastest'
        else:
            level_str = '[System.IO.Compression.CompressionLevel]::Optimal'
        cmd_parts = [
            f'$archive = {quoted_archive}',
            f'$files = @({files_str})',
            'Add-Type -AssemblyName System.IO.Compression.FileSystem',
            '$zip = [System.IO.Compression.ZipFile]::Open($archive, "Update")',
            'foreach ($file in $files) {',
            '$entryName = Split-Path $file -Leaf',
            f'[System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile($zip, $file, $entryName, {level_str})',
            '}',
            '$zip.Dispose()',
        ]
        if options.get('move'):
            cmd_parts.append('foreach ($file in $files) { Remove-Item $file }')
        return '; '.join(cmd_parts)
    compression_level = options.get('compression_level')
    if compression_level is not None:
        if compression_level >= 6:
            level_str = '[System.IO.Compression.CompressionLevel]::Optimal'
        elif compression_level > 0:
            level_str = '[System.IO.Compression.CompressionLevel]::Fastest'
        else:
            level_str = '[System.IO.Compression.CompressionLevel]::NoCompression'
        if len(files) == 1 and not options.get('recursive'):
            file_path = quoted_files[0]
            return (
                f'$archive = {quoted_archive}; '
                f'$file = {file_path}; '
                'Add-Type -AssemblyName System.IO.Compression.FileSystem; '
                '$zip = [System.IO.Compression.ZipFile]::Open($archive, "Create"); '
                f'$entryName = Split-Path $file -Leaf; '
                f'[System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile($zip, $file, $entryName, {level_str}); '
                '$zip.Dispose()'
            )
        else:
            return (
                f'$compression = {level_str}; '
                f'$archive = {quoted_archive}; '
                f'$files = @({files_str}); '
                '$tempDir = New-Item -ItemType Directory -Path ([System.IO.Path]::GetTempPath() + [System.Guid]::NewGuid().ToString()); '
                'foreach ($file in $files) { '
                'if (Test-Path $file -PathType Container) { '
                'Copy-Item -Path $file -Destination $tempDir.FullName -Recurse -Container '
                '} else { '
                'Copy-Item -Path $file -Destination $tempDir.FullName '
                '} '
                '}; '
                '[System.IO.Compression.ZipFile]::CreateFromDirectory($tempDir.FullName, $archive, $compression, $false); '
                'Remove-Item $tempDir.FullName -Recurse'
            )
    if options.get('recursive'):
        if len(files) == 1:
            return f'Compress-Archive -Path {quoted_files[0]} -DestinationPath {quoted_archive} -Force'
        else:
            return f'Compress-Archive -Path {files_str} -DestinationPath {quoted_archive} -Force'
    if options.get('update') or options.get('grow'):
        return f'Compress-Archive -Path {files_str} -DestinationPath {quoted_archive} -Update'
    if len(files) == 1:
        return f'Compress-Archive -Path {quoted_files[0]} -DestinationPath {quoted_archive} -Force'
    else:
        return f'Compress-Archive -Path {files_str} -DestinationPath {quoted_archive} -Force'
if __name__ == "__main__":
    test_cases = [
        "zip archive.zip file1.txt file2.txt",
        "zip -r archive.zip dir/",
        "zip -9 archive.zip file.txt",
        "zip -0 archive.zip file.txt",
        "zip -j archive.zip dir/file.txt",
        "zip -d archive.zip file.txt",
        "zip -T archive.zip",
        "zip -h",
        "zip --help",
        "zip -V",
        "zip -L",
        "zip -q archive.zip file.txt",
        "zip -v archive.zip file.txt",
        "zip -u archive.zip file.txt",
        "zip -m archive.zip file.txt",
        "zip -x '*.tmp' archive.zip file.txt",
        "zip -i '*.txt' archive.zip dir/",
        "zip -l archive.zip file.txt",
        "zip -ll archive.zip file.txt",
        "zip -e archive.zip file.txt",
        "zip -P secret archive.zip file.txt",
        "zip /r archive.zip dir/",
        "zip /9 archive.zip file.txt",
        "zip archive.zip",
        "zip",
    ]
    for test in test_cases:
        result = _convert_zip(test)
        print(f"Input:  {test}")
        print(f"Output: {result}")
        print()
_command_map = {
    "ver": _convert_ver,
    "ls": _convert_ls,
    "dir": _convert_dir,
    "cd": _convert_cd,
    "pwd": _convert_pwd,
    "cat": _convert_cat,
    "mkdir": _convert_mkdir,
    "rm": _convert_rm,
    "cp": _convert_cp,
    "mv": _convert_mv,
    "grep": _convert_grep,
    "ps": _convert_ps,
    "man": _convert_man,
    "kill": _convert_kill,
    "echo": _convert_echo,
    "touch": _convert_touch,
    "which": _convert_which,
    "wc": _convert_wc,
    "find": _convert_find,
    "alias": _convert_alias,
    "base64": _convert_base64,
    "basename": _convert_basename,
    "chmod": _convert_chmod,
    "chown": _convert_chown,
    "clear": _convert_clear,
    "curl": _convert_curl,
    "cut": _convert_cut,
    "date": _convert_date,
    "df": _convert_df,
    "diff": _convert_diff,
    "dig": _convert_dig,
    "dirname": _convert_dirname,
    "du": _convert_du,
    "env": _convert_env,
    "exit": _convert_exit,
    "fold": _convert_fold,
    "groups": _convert_groups,
    "gunzip": _convert_gunzip,
    "gzip": _convert_gzip,
    "head": _convert_head,
    "history": _convert_history,
    "host": _convert_host,
    "hostname": _convert_hostname,
    "id": _convert_id,
    "ifconfig": _convert_ifconfig,
    "ip": _convert_ip,
    "join": _convert_join,
    "jq": _convert_jq,
    "ln": _convert_ln,
    "ln_s": _convert_ln_s,
    "md5sum": _convert_md5sum,
    "mktemp": _convert_mktemp,
    "nc": _convert_nc,
    "netstat": _convert_netstat,
    "nslookup": _convert_nslookup,
    "paste": _convert_paste,
    "ping": _convert_ping,
    "readlink": _convert_readlink,
    "realpath": _convert_realpath,
    "route": _convert_route,
    "rsync": _convert_rsync,
    "scp": _convert_scp,
    "seq": _convert_seq,
    "sha256sum": _convert_sha256sum,
    "sha512sum": _convert_sha512sum,
    "shuf": _convert_shuf,
    "sleep": _convert_sleep,
    "split": _convert_split,
    "ssh": _convert_ssh,
    "tail": _convert_tail,
    "tar": _convert_tar,
    "tee": _convert_tee,
    "time": _convert_time,
    "unalias": _convert_unalias,
    "uname": _convert_uname,
    "uniq": _convert_uniq,
    "unzip": _convert_unzip,
    "uptime": _convert_uptime,
    "wget": _convert_wget,
    "whoami": _convert_whoami,
    "xargs": _convert_xargs,
    "yes": _convert_yes,
    "zip": _convert_zip,
}