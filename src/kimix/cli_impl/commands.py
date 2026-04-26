from typing import Any
import os
from pathlib import Path

import kimix.base as base
from . import constants
from .utils import _input, _split_text
from kimix.base import print_success, print_error, print_warning, print_info, colorful_text, Color
from kimix.utils import (
    prompt, clear_context, get_default_session, fix_error,
    print_usage, execute_plan
)


def _cmd_help(task_split: list[str], text_arr: list[str]) -> tuple[None, bool]:
    print(constants.HELP_STR)
    return None, False


def _cmd_clear(task_split: list[str], text_arr: list[str]) -> tuple[None, bool]:
    clear_context()
    return None, False


def _cmd_summarize(task_split: list[str], text_arr: list[str]) -> tuple[None, bool]:
    from kimix.summarize import summarize
    summarize()
    return None, False


def _cmd_exit(task_split: list[str], text_arr: list[str]) -> tuple[None, bool]:
    print_success('bye!')
    return None, True


def _cmd_context(task_split: list[str], text_arr: list[str]) -> tuple[None, bool]:
    print_usage()
    return None, False


def _cmd_script(task_split: list[str], text_arr: list[str]) -> tuple[None, bool]:
    print('\n>>>> Start input multiple-lines, end with /end')
    text_lines: list[str] = []
    while True:
        s = _input('', text_arr)
        if s.strip() == '/end':
            break
        text_lines.append(s)
    text = '\n'.join(text_lines)
    try:
        exec(text, constants.globals_dict, constants.locals_dict)
        print_success('Done.')
    except Exception as e:
        print_error(str(e))
    return None, False


def _cmd_cmd(task_split: list[str], text_arr: list[str]) -> tuple[None, bool]:
    if len(task_split) < 2:
        print_error('Command must be /cmd:xx yy')
        return None, False
    cmd = ':'.join(task_split[1:])
    try:
        os.system(cmd)
        print_success('Done.')
    except Exception as e:
        print_error(str(e))
    return None, False


def _cmd_cd(task_split: list[str], text_arr: list[str]) -> tuple[None, bool]:
    if len(task_split) < 2:
        print_error('Command must be /cd:PATH')
        return None, False
    path = ':'.join(task_split[1:])
    try:
        os.chdir(path)
        base._default_skill_dirs = []
        if get_default_session():
            clear_context(True, True)
        print_success(f'Changed directory to: {Path(".").resolve()}')
    except Exception as e:
        print_error(f'Failed to change directory: {e}')
    return None, False


def _cmd_fix(task_split: list[str], text_arr: list[str]) -> tuple[None, bool]:
    if len(task_split) < 2:
        print_error('Command must be /fix:<command>')
        return None, False
    command_to_fix = (':'.join(task_split[1:])).strip()
    if not command_to_fix:
        print_error('Command must be /fix:<command>')
        return None, False
    fix_error(command_to_fix, session=get_default_session())
    return None, False


def _cmd_think(task_split: list[str], text_arr: list[str]) -> tuple[None, bool]:
    if len(task_split) < 2:
        print_error('Command must be /think:on or /think:off')
        return None, False
    value = task_split[1].strip().lower()
    if value == 'on':
        base._default_thinking = True
        print_success('Thinking mode enabled.')
    elif value == 'off':
        base._default_thinking = False
        print_success('Thinking mode disabled.')
    else:
        print_error('Command must be /think:on or /think:off')
        return None, False
    if get_default_session():
        clear_context(True, True)
    return None, False


def _cmd_plan(task_split: list[str], text_arr: list[str]) -> tuple[None, bool]:
    if len(task_split) < 2 or (not task_split[1]):
        print(
            f'\n>>>> Make a plan: input multiple-lines, end with {colorful_text('/end', Color.YELLOW)}, cancel with {colorful_text('/cancel', Color.YELLOW)}')
        text: list[str] = []
        while True:
            s = _input('', text_arr)
            if s.strip() == '/end':
                break
            if s.strip() == '/cancel':
                text.clear()
                break
            text.append(s)
        prompt_str = '\n'.join(text)

        def ask_if_use_cache(path: str) -> bool:
            v = input(f'found cache `{path}`, load it and continue? (y/n) ')
            if v.strip().lower() == 'y':
                return True
            return False

        def ask_if_execute(steps: list[str]) -> bool:
            print('Plan steps:\n' + ('\n' + '=' * 40 + '\n').join(steps))
            print_warning('execute the plan? (y/n)')
            return input().strip().lower() == 'y'
        ask_plan = input(
            'Ask after make plan? no for auto accept-all. (y/n)').strip().lower() == 'y'

        if prompt_str.strip():
            execute_plan(prompt_str, ask_if_use_cache,
                         ask_if_execute if ask_plan else None)
        return None, False
    value = task_split[1].strip().lower()
    if value == 'on':
        base._default_plan_mode = True
        print_success('Plan mode enabled.')
    elif value == 'off':
        base._default_plan_mode = False
        print_success('Plan mode disabled.')
    else:
        print_error('Command must be /plan:on or /plan:off')
        return None, False
    if get_default_session():
        clear_context(True, True)
    return None, False


def _cmd_txt(task_split: list[str], text_arr: list[str]) -> tuple[None, bool]:
    print(
        f'\n>>>> Start input multiple-lines, end with {colorful_text('/end', Color.YELLOW)}, cancel with {colorful_text('/cancel', Color.YELLOW)}')
    text: list[str] = []
    while True:
        s = _input('', text_arr)
        if s.strip() == '/end':
            break
        if s.strip() == '/cancel':
            text.clear()
            break
        text.append(s)
    for i in _split_text(text):
        text_arr.append(i)
    return None, False


def _cmd_skill(task_split: list[str], text_arr: list[str]) -> tuple[None, bool]:
    if len(task_split) < 2:
        print_error('Command must be /skill:xx')
        return None, False
    prompt(f"/skill:{task_split[1]}", get_default_session())
    return None, False


def _cmd_file(task_split: list[str], text_arr: list[str]) -> tuple[str | None, bool]:
    if len(task_split) != 2:
        print_error(f'command format error, must be /file:path')
        return None, False
    file_name_str = ':'.join(task_split[1:])
    file_path = Path(file_name_str)
    if not file_path.is_file():
        print_error(f'file not found: {file_path}')
        return None, False
    return file_path.read_text(encoding='utf-8', errors='replace'), False


def _cmd_unknown(task_split: list[str], text_arr: list[str]) -> tuple[None, bool]:
    print_warning('Unrecognized command.')
    return None, False


_command_map = {
    'help': _cmd_help,
    'clear': _cmd_clear,
    'summarize': _cmd_summarize,
    'exit': _cmd_exit,
    'context': _cmd_context,
    'script': _cmd_script,
    'cmd': _cmd_cmd,
    'cd': _cmd_cd,
    'fix': _cmd_fix,
    'think': _cmd_think,
    'plan': _cmd_plan,
    'txt': _cmd_txt,
    'skill': _cmd_skill,
    'file': _cmd_file
}
