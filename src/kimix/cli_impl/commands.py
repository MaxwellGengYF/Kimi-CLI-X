import os
from pathlib import Path

import kimix.base as base
from . import constants
from .utils import _input, _split_text
from kimix.base import print_success, print_error, print_warning, print_info
from kimix.utils import (
    prompt, clear_context, get_default_session, fix_error, validate,
    print_usage
)


def _cmd_help(task_split, text_arr):
    print(constants.HELP_STR)
    return None, False


def _cmd_clear(task_split, text_arr):
    clear_context()
    return None, False


def _cmd_summarize(task_split, text_arr):
    from kimix.summarize import summarize
    summarize()
    return None, False


def _cmd_exit(task_split, text_arr):
    print_success('bye!')
    return None, True


def _cmd_context(task_split, text_arr):
    print_usage()
    return None, False


def _cmd_script(task_split, text_arr):
    print('\n>>>> Start input multiple-lines, end with /end')
    text = []
    while True:
        s = _input('', text_arr)
        if s.strip() == '/end':
            break
        text.append(s)
    text = '\n'.join(text)
    try:
        exec(text, constants.globals_dict, constants.locals_dict)
        print_success('Done.')
    except Exception as e:
        print_error(str(e))
    return None, False


def _cmd_cmd(task_split, text_arr):
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


def _cmd_cd(task_split, text_arr):
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


def _cmd_fix(task_split, text_arr):
    if len(task_split) < 2:
        print_error('Command must be /fix:<command>')
        return None, False
    command_to_fix = task_split[1].strip()
    if not command_to_fix:
        print_error('Command must be /fix:<command>')
        return None, False
    fix_error(command_to_fix, session=get_default_session())
    return None, False


def _cmd_validate(task_split, text_arr):
    if len(task_split) < 2:
        print_error('Command must be /validate:prompt')
        return None, False
    result = validate(task_split[1], get_default_session())
    print_info(f'Validate result: {result}')
    return None, False


def _cmd_think(task_split, text_arr):
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


def _cmd_plan(task_split, text_arr):
    if len(task_split) < 2:
        print_error('Command must be /plan:on or /plan:off')
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

def _cmd_txt(task_split, text_arr):
    print('\n>>>> Start input multiple-lines, end with /end, or cancel with /cancel')
    text = []
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


def _cmd_skill(task_split, text_arr):
    if len(task_split) < 2:
        print_error('Command must be /skill:xx')
        return None, False
    prompt(f"/skill:{task_split[1]}", get_default_session())
    return None, False


def _cmd_file(task_split, text_arr):
    if len(task_split) != 2:
        print_error(f'command format error, must be /file:path')
        return None, False
    file_name = ':'.join(task_split[1:])
    file_name = Path(file_name)
    if not file_name.is_file():
        print_error(f'file not found: {file_name}')
        return None, False
    return file_name.read_text(encoding='utf-8', errors='replace'), False


def _cmd_unknown(task_split, text_arr):
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
    'validate': _cmd_validate,
    'think': _cmd_think,
    'plan': _cmd_plan,
    'txt': _cmd_txt,
    'skill': _cmd_skill,
    'file': _cmd_file
}
