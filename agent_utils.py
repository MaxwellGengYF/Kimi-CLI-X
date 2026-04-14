from pathlib import Path
from typing import Callable
import os
from enum import Enum
from typing import Optional
import json
import threading
import sys
from concurrent.futures import ThreadPoolExecutor
_threads = list()


class Color(Enum):
    """ANSI color codes for foreground colors."""
    BLACK = 30
    RED = 31
    GREEN = 32
    YELLOW = 33
    BLUE = 34
    MAGENTA = 35
    CYAN = 36
    WHITE = 37
    BRIGHT_BLACK = 90
    BRIGHT_RED = 91
    BRIGHT_GREEN = 92
    BRIGHT_YELLOW = 93
    BRIGHT_BLUE = 94
    BRIGHT_MAGENTA = 95
    BRIGHT_CYAN = 96
    BRIGHT_WHITE = 97


class BgColor(Enum):
    """ANSI color codes for background colors."""
    BLACK = 40
    RED = 41
    GREEN = 42
    YELLOW = 43
    BLUE = 44
    MAGENTA = 45
    CYAN = 46
    WHITE = 47
    BRIGHT_BLACK = 100
    BRIGHT_RED = 101
    BRIGHT_GREEN = 102
    BRIGHT_YELLOW = 103
    BRIGHT_BLUE = 104
    BRIGHT_MAGENTA = 105
    BRIGHT_CYAN = 106
    BRIGHT_WHITE = 107


class Style(Enum):
    """ANSI style codes."""
    RESET = 0
    BOLD = 1
    DIM = 2
    ITALIC = 3
    UNDERLINE = 4
    BLINK = 5
    REVERSE = 7
    HIDDEN = 8
    STRIKETHROUGH = 9


_colorful_print = True
_print_func = None


def colorful_print(
    text: str,
    fg: Optional[Color] = None,
    bg: Optional[BgColor] = None,
    styles: Optional[list[Style]] = None,
    end: str = "\n"
) -> None:
    if not _colorful_print:
        if _print_func:
            _print_func(text, end)
        else:
            print(text, end=end)
        return
    """
    Print text with optional colors and styles.

    Args:
        text: The text to print
        fg: Foreground color
        bg: Background color
        styles: List of text styles to apply
        end: String to append at the end (default: newline)
    """
    codes = []

    if styles:
        codes.extend(style.value for style in styles)
    if fg:
        codes.append(fg.value)
    if bg:
        codes.append(bg.value)

    if codes:
        text = f"\033[{';'.join(map(str, codes))}m{text}\033[0m"
    if _print_func:
        _print_func(text, end)
    else:
        print(text, end=end)


_quiet = False


def print_success(text: str, end: str = "\n") -> None:
    """Print success message in green."""
    colorful_print(text, fg=Color.BRIGHT_GREEN, styles=[Style.BOLD], end=end)


def print_string(text: str, end: str = "\n") -> None:
    if _print_func:
        _print_func(text, end)
    else:
        print(text, end=end)


def print_error(text: str, end: str = "\n") -> None:
    """Print error message in red."""
    colorful_print(text, fg=Color.BRIGHT_RED, styles=[Style.BOLD], end=end)


def print_warning(text: str, end: str = "\n") -> None:
    """Print warning message in yellow."""
    colorful_print(text, fg=Color.BRIGHT_YELLOW, styles=[Style.BOLD], end=end)


def print_info(text: str, end: str = "\n") -> None:
    """Print info message in blue."""
    colorful_print(text, fg=Color.BRIGHT_MAGENTA, end=end)


def print_debug(text: str, end: str = "\n") -> None:
    if _quiet:
        return
    """Print debug message in cyan."""
    colorful_print(text, fg=Color.BRIGHT_CYAN, end=end)


def _process_lru():
    import time
    """Limit the number of processes to 32 by waiting and removing completed ones."""
    global _threads
    MAX_PROCESSES = 4

    # Remove already completed processes first
    _threads = [p for p in _threads if p.is_alive()]

    # If still over limit, wait for processes to complete
    while len(_threads) >= MAX_PROCESSES:
        # Wait for the first process to complete with a timeout
        time.sleep(0.1)
        # Remove completed processes
        _threads = [p for p in _threads if p.is_alive()]


_commands = {
    'Python': ('code', 'run_in_background'),
    'Run': ('path', 'args', 'timeout', 'run_in_background'),
    'TaskOutput': ('task_id', 'block', 'wait_time'),
    'TaskStop': 'task_id',
    'Rm': 'path',
    'Mkdir': 'path',
    'Ls': 'directory',
    'Glob': ('pattern'),
    'Grep': ('pattern', 'path'),
    'ReadFile': ('path', 'line_offset', 'n_lines'),
    'WriteFile': 'path',
    'StrReplaceFile': 'path',
    'Input': 'text',
    'Wait': 'timeout',
    'SetTodoList': 'todos',
    'cpplint': ('file_path', 'project_root', 'verbose'),
    'FetchURL': 'url',
    'SearchWeb': ('query', 'limit', 'include_content'),
    'spawn': ('prompt', 'thinking'),
    'GrepAnalyzer': ('query', 'directory', 'top_k', 'refresh'),
}
_new_commands = dict()
for k, v in _commands.items():
    _new_commands[k.lower()] = v
_commands = _new_commands


def print_agent_json(get_message, output_function: Callable | None = None):
    json_str = None
    try:
        json_str = get_message()
    except Exception as e:
        print_debug('JSON error (possibly because streaming)...')
        return
    js = json.loads(json_str)

    def print_item(item):
        import agent_utils
        if type(item) == str:
            if not (item.find('<choice>') >= 0 and item.find('</choice>') >= 0):
                if _print_func:
                    _print_func(item, '\n')
                else:
                    print(item, end='\n')
        elif item.get("type") == "think" and not _quiet:
            think_content = item.get("think", "")
            if think_content:
                colorful_print(f"[Think] {think_content}",
                               fg=Color.BRIGHT_CYAN, end='\n')
        elif item.get("type") == "text":
            text_content = item.get("text", "")
            if text_content:
                if not (text_content.find('<choice>') >= 0 and text_content.find('</choice>') >= 0):
                    if output_function:
                        output_function(text_content)
                    if _print_func:
                        _print_func(f"\n{text_content}", '\n')
                    else:
                        print(f"\n{text_content}", end='\n')
        # print in kimi-cli
        # elif item.get("type") == "function" and not _quiet:
        #     def to_str(s):
        #         if isinstance(s, str):
        #             return s
        #         try:
        #             return ' '.join(str(x) for x in s)
        #         except TypeError:
        #             return str(s)
        #     text = item.get("function", None)
        #     if text:
        #         name:str = text.get("name")
        #         if name is not None:
        #             args: str = text.get('arguments', '')
        #             if not args.endswith('"}'):
        #                 args += '"}'
        #             elif not args.endswith('}'):
        #                 args += '}'
        #             try:
        #                 args = json.loads(args)
        #             except json.JSONDecodeError as e:
        #                 args = {}  # or handle it appropriately
        #             cmd_args = _commands.get(name.lower())
        #             print_arg = ''
        #             if cmd_args is not None:
        #                 if type(cmd_args) is tuple:
        #                     print_args = []
        #                     for i in cmd_args:
        #                         v = args.get(i)
        #                         if v is not None:
        #                             print_args.append(f'{i}: {to_str(v)}')
        #                     print_arg = ' '.join(print_args)
        #                 else:
        #                     v = args.get(cmd_args)
        #                     if v is not None:
        #                         print_arg = to_str(v)
        #             print_info(f"{name}: {print_arg}")
    if js.get("role") == "assistant":
        content = js.get("content", [])
        if type(content) == str:
            if not (content.find('<choice>') >= 0 and content.find('</choice>') >= 0):
                if _print_func:
                    _print_func(content, '\n')
                else:
                    print(content, end='\n')
            return
        for item in content:
            print_item(item)
    else:
        print_item(js)


def run_thread(function, args: tuple = None):
    assert callable(function)
    global _threads
    # Enforce process limit before creating new one
    _process_lru()

    if args is None:
        args = tuple()
    elif type(args) is not tuple:
        args = (args, )
    thd = threading.Thread(target=function, args=args)
    thd.start()

    _threads.append(thd)
    return thd


def run_script(path):
    import subprocess
    return subprocess.Popen(
        [sys.executable, str(path)], creationflags=subprocess.CREATE_NEW_CONSOLE)


def sync_all():
    global _threads
    for thd in _threads:
        thd.join()
    _threads.clear()


def _run_process_with_log(command: str):
    import subprocess
    print_info(f'Shell: {command}')
    result = subprocess.run(command, shell=True,
                            capture_output=True, text=False)
    # Decode stdout with UTF-8, handle decode errors
    if result.stdout:
        output = result.stdout.decode('utf-8', errors='replace')
    else:
        output = ""
    # Decode stderr with UTF-8, handle decode errors
    if result.stderr:
        stderr = result.stderr.decode('utf-8', errors='replace')
        output += "\n" + stderr
    return output, result.returncode


def _run_process_with_error(command: str, keycode: tuple, skip_success: bool = True):
    result, code = _run_process_with_log(command)
    if skip_success and code == 0:
        return None
    lines = result.splitlines()
    if keycode is None or len(keycode) == 0:
        return result
    for idx in range(len(lines)):
        line = lines[idx]
        lower_line = line.lower()
        for c in keycode:
            if c in lower_line:
                return '\n'.join(lines[idx:])

    return result


def _percentage_str(num: float) -> str:
    return f"{num * 100:.1f}%"


_ralph_iterations = 0
_default_thinking = True
_default_plan_mode = False
_default_yolo = True
_default_agent_file_dir = Path(__file__).parent
_default_agent_file = _default_agent_file_dir / 'agent_worker.yaml'
_default_skill_dirs = []
# The failed-list for tool call that
# tuple: function-name, arguments, output, message
_tool_call_failed_lists: dict[str, list[tuple[str, str, str, str]]] = dict()


def _get_skill_dirs(use_kaos_path=True) -> list:
    if use_kaos_path:
        from kaos.path import KaosPath
    global _default_skill_dirs
    if _default_skill_dirs:
        return _default_skill_dirs

    def _gen():
        result = []
        d = Path(os.curdir) / ".agents/skills"
        if d.exists():
            result.append(d)
        d = Path(os.curdir) / ".config/.agents/skills"
        if d.exists():
            result.append(d)
        d = Path(os.curdir) / ".opencode/skills"
        if d.exists():
            result.append(d)
        return result
    _default_skill_dirs = _gen()
    if _default_skill_dirs:
        for d in _default_skill_dirs:
            print_debug(f'skill dir: {str(d)}')
        if use_kaos_path:
            _default_skill_dirs = [
                KaosPath(d) if type(d) is not KaosPath else d
                for d in _default_skill_dirs
            ]
        return _default_skill_dirs
    return []
