# API credentials for Kimi Code Console
import agent_utils
from pathlib import Path
from kaos.path import KaosPath
import asyncio
from kimi_utils import print_success, print_error, print_warning, print_info, prompt, clear_context, sync_all,  _create_default_session, print_usage, delete_session_dir, print_debug, get_default_session, fix_error, validate, get_todo, clear_todo, make_todo, update_todo_status
import kimi_utils
import os
import sys
import subprocess
LSP_JSON = None
frame = 0

COMMENT = """Always write ' Start writen by AGENT ' comment before code, Always write ' End writen by AGENT ' comment after code"""
curr_dir = Path(os.curdir)
if not curr_dir.is_absolute():
    curr_dir = curr_dir.absolute()

# Start writen by AGENT
HELP_STR = '''Command line options:
  -c, --clean         - Delete cache file after quit
  --ralph             - Continue work until done (auto-loop)
  --think          - Disable thinking mode
  --no_yolo           - Disable YOLO mode
  -s, --skill-dir     - Specify custom skill directory

Available commands:
  /file:<path>    - Load a file and execute its content line by line
  <path>          - Same as /file:<path>
  /clear          - Clear the conversation context
  /exit           - Exit the program
  /skill          - Load skills
  /help           - Show this help message
  /context        - Print context usage
  /validate       - Test if a condition is true
  /fix:<command>  - Run a command and fix errors if any
  /plan           - Make a plan 
  /todo           - Show todo list
  /todo:help      - Show todo commands help
  /txt            - input multiple line text
  /think:on       - Enable thinking mode
  /think:off      - Disable thinking mode

Or enter any prompt to send to the agent.
'''
# End writen by AGENT
CLEAN_MODE = None


def set_arg():
    global CLEAN_MODE
    import argparse
    parser = argparse.ArgumentParser(description='Kimi Agent CLI')
    parser.add_argument('-c', '--clean', action='store_true',
                        help='Delete cache file after quit')
    parser.add_argument('-no_color', '--no_color', action='store_true',
                        help='Disable colorful print')
    parser.add_argument('-ralph', '--ralph', action='store_true',
                        help='Continue work until done (auto-loop)')
    parser.add_argument('-think', '--think', action='store_true',
                        help='Disable thinking mode')
    parser.add_argument('-no_yolo', '--no_yolo', action='store_true',
                        help='Disable YOLO mode')
    parser.add_argument('-s', '--skill-dir', type=str, default=None,
                        help='Specify custom skill directory')
    args = parser.parse_args()
    if args.no_color:
        agent_utils._colorful_print = False

    CLEAN_MODE = args.clean
    if CLEAN_MODE:
        print_debug('Clean mode ON, delete cache file after quit.')
    else:
        print_debug('Clean mode OFF.')

    if args.ralph:
        kimi_utils._ralph_iterations = -1
        print_debug(
            'Ralph loop ON, continue work until done(or running OUT of your TOKEN!!!).')
    else:
        kimi_utils._ralph_iterations = 0
        print_debug('Ralph loop OFF.')

    if args.think:
        kimi_utils._default_thinking = True
        print_debug('Thinking ON.')
    else:
        kimi_utils._default_thinking = False
        print_debug('Thinking OFF.')

    if args.no_yolo:
        kimi_utils._default_yolo = False
        print_debug('YOLO OFF.')
    else:
        kimi_utils._default_yolo = True
        print_debug('YOLO ON.')

    # Handle --skill-dir argument
    if args.skill_dir:
        skill_dir_path = Path(args.skill_dir)
        if not skill_dir_path.is_absolute():
            skill_dir_path = curr_dir / skill_dir_path
        # Normalize the path (resolve ., .., and symlinks)
        skill_dir_path = skill_dir_path.resolve()
        if skill_dir_path.exists() and skill_dir_path.is_dir():
            kimi_utils._default_skill_dir = KaosPath(skill_dir_path)
            print_debug(f'Skill dir set to: {str(skill_dir_path)}')
        else:
            print_warning(f'Skill dir not found: {str(skill_dir_path)}')


def _input(text: str, text_arr: list) -> str:
    if text_arr is None or len(text_arr) == 0:
        return input(text)
    v = text_arr.pop(0)
    return v


def _split_text(txt: str):
    text_arr = []
    current_text = []
    for line in txt.splitlines():
        strip_line = line.strip()
        if len(strip_line) == 0:
            continue
        if strip_line.startswith('/'):
            if current_text:
                text_arr.append('\n'.join(current_text))
                current_text = []
            if len(strip_line) > 1:
                text_arr.append(strip_line)
        else:
            current_text.append(line)
    if current_text:
        text_arr.append('\n'.join(current_text))
    return text_arr


def _run_cli():
    set_arg()
    # Parse command line arguments for clean mode flag

    # Read user input from keyboard asynchronously
    exec_ctx = None
    special_commands = {
        'clear', 'exit', 'help', 'context', 'fix', 'plan', 'txt'
    }
    input_str = None
    _create_default_session()
    assert get_default_session()
    text_arr = []
    while True:
        try:
            input_str = _input(
                "\n>>>>>>>>> Enter your prompt or command:\n", text_arr)
        except KeyboardInterrupt as e:
            print_success('\nbye.')
            break
        except EOFError as e:
            print_success('\nbye.')
            break
        try:
            if len(input_str) == 0:
                continue
            if input_str.lower() in special_commands:
                input_str = '/' + input_str.lower()
            if input_str is not None and input_str[0] == '/':
                task = input_str[1:]
                split_idx = task.strip().find(':')
                if split_idx >= 0:
                    task_split = (task[:split_idx], task[split_idx+1:])
                else:
                    task_split = (task,)
                if task_split[0] == 'help':
                    print(HELP_STR)
                    continue
                elif task_split[0] == 'clear':
                    clear_context()
                    continue
                elif task_split[0] == 'exit':
                    print_success('bye!')
                    break
                elif task_split[0] == 'context':
                    print_usage()
                    continue
                elif task_split[0] == 'fix':
                    if len(task_split) < 2:
                        print_error('Command must be /fix:<command>')
                        continue
                    command_to_fix = task_split[1].strip()
                    if not command_to_fix:
                        print_error('Command must be /fix:<command>')
                        continue
                    fix_error(
                        command_to_fix, session=get_default_session())
                    continue
                elif task_split[0] == 'validate':
                    if len(task_split) < 2:
                        print_error('Command must be /validate:prompt')
                        continue
                    result = validate(
                        task_split[1], get_default_session())
                    print_info(f'Validate result: {result}')
                    continue
                elif task_split[0] == 'think':
                    if len(task_split) < 2:
                        print_error('Command must be /think:on or /think:off')
                        continue
                    value = task_split[1].strip().lower()
                    if value == 'on':
                        kimi_utils._default_thinking = True
                        print_success('Thinking mode enabled.')
                    elif value == 'off':
                        kimi_utils._default_thinking = False
                        print_success('Thinking mode disabled.')
                    else:
                        print_error('Command must be /think:on or /think:off')
                        continue
                    clear_context(True, True)
                    continue
                elif task_split[0] == 'plan':
                    if len(task_split) < 2:
                        print_error('Command must be /plan:plan_script.py')
                        continue
                    script_dst_dir = Path(task_split[1])
                    if script_dst_dir.suffix != '.py':
                        print_error(
                            f'Invalid file extension: {script_dst_dir.suffix}. Expected .py')
                        continue
                    plan_str = _input(
                        ">>>> Enter your plan:\n", text_arr).strip()
                    import my_tools.todo as todo
                    todo.clear_todo_list('default')
                    if len(plan_str) > 0:
                        prompt(f'''
Run tool:SetTodoList to set a todo-list of (do NOT implement, ONLY make list):
{plan_str}
''')
                    todo_list = todo.get_todo_list('default')
                    if todo_list is None:
                        print_error('Make plan failed.')
                    else:
                        data = 'from kimi_utils import prompt\n'
                        for i in todo_list.todos:
                            data += f'prompt({repr(i.title)})\n'
                        script_dst_dir.write_text(data, encoding='utf-8')
                        print_success(
                            f'Make plan success. write to {str(script_dst_dir)}')
                    continue
                elif task_split[0] == 'txt':
                    print('\n>>>> Start input multiple-lines, end with /end')
                    text = ''
                    while True:
                        s = _input('', text_arr)
                        if s.strip() == '/end':
                            break
                        text += s + '\n'
                    for i in _split_text(text):
                        text_arr.append(i)
                    continue
                elif task_split[0] == 'todo':
                    # Parse subcommand and arguments
                    subcommand = task_split[1].strip() if len(
                        task_split) > 1 else ''

                    if not subcommand or subcommand == 'list':
                        # Show current todo list
                        result = get_todo(get_default_session())
                        if not result:
                            print_info('No todo items found.')
                        else:
                            todos = result.todos if hasattr(
                                result, 'todos') else []
                            if not todos:
                                print_info('No todo items found.')
                            else:
                                print_success('Todo list:')
                                for i, todo in enumerate(todos, 1):
                                    status = todo.status if hasattr(
                                        todo, 'status') else todo.get('status', 'pending')
                                    title = todo.title if hasattr(
                                        todo, 'title') else todo.get('title', 'Unknown')
                                    status_icon = {'pending': '⏳', 'in_progress': '🔄', 'done': '✅'}.get(
                                        status, '⏳')
                                    print_info(
                                        f'  {i}. [{status_icon}] {title}')
                        continue
                    elif subcommand == 'clear':
                        clear_todo(get_default_session())
                        print_success('Todo list cleared.')
                        continue
                    elif subcommand.startswith('make ') or subcommand == 'make':
                        subcommand = subcommand[4:]
                        if not make_todo(subcommand.strip(), get_default_session()):
                            print_error('Make todo-list failed.')
                        else:
                            print_success(f'Make todo-list success.')
                        continue

                    elif subcommand.startswith('done ') or subcommand == 'done':
                        # Mark item(s) as done
                        update_todo_status(get_default_session(), subcommand[5:].strip(
                        ) if subcommand.startswith('done ') else '', 'done')
                        continue

                    elif subcommand.startswith('in_progress ') or subcommand == 'in_progress':
                        # Mark item(s) as in_progress
                        update_todo_status(get_default_session(), subcommand[12:].strip(
                        ) if subcommand.startswith('in_progress ') else '', 'in_progress')
                        continue

                    elif subcommand.startswith('pending ') or subcommand == 'pending':
                        # Mark item(s) as pending
                        update_todo_status(get_default_session(), subcommand[8:].strip(
                        ) if subcommand.startswith('pending ') else '', 'pending')
                        continue

                    elif subcommand == 'help':
                        print_info('''Todo commands:
  /todo           - Show current todo list
  /todo:list      - Show current todo list
  /todo:make      - Make a new todo list
  /todo:clear     - Clear all todo items
  /todo:done <n>  - Mark item(s) as done (e.g., /todo:done 1,2 or /todo:done 1-3)
  /todo:in_progress <n> - Mark item(s) as in_progress
  /todo:pending <n>     - Mark item(s) as pending
  /todo:help      - Show this help message''')
                        continue

                    else:
                        print_warning(
                            f'Unknown todo command: {subcommand}. Use /todo:help for usage.')
                        continue
                elif task_split[0] == 'skill':
                    if len(task_split) < 2:
                        print_error('Command must be /skill:xx')
                        continue
                    prompt(f"/skill:{task_split[1]}", get_default_session())
                    continue
                elif task_split[0] == 'file':
                    if len(task_split) != 2:
                        print_error(
                            f'command format error, must be /file:path')
                        continue
                    input_str = task_split[1]
                else:
                    print_warning('Unrecognized command.')
                    continue
            if input_str is not None and len(input_str) > 0:
                # Test if is file path
                try:
                    path = Path(input_str)
                    if not path.is_absolute():
                        path = curr_dir / path
                    if not path.exists():
                        raise Exception()
                    input_str = None
                    try:
                        suffix = path.suffix
                        f = open(path, 'r', encoding='utf-8')
                        s = f.read()
                        f.close()
                        if suffix == '.py':
                            print_info(f'Executing {path.name}', end='\n\n')
                            try:
                                if exec_ctx is None:
                                    exec_ctx = dict()
                                exec(s, exec_ctx)
                            except KeyboardInterrupt as e:
                                raise e
                            except Exception as e:
                                print_error(str(e))
                            finally:
                                sync_all()
                        else:
                            print_warning(
                                'File not executable, consider as prompt.')
                            input_str = s
                    except KeyboardInterrupt as e:
                        raise e
                    except Exception as e:
                        print_error(str(e))
                    if input_str:
                        raise Exception()
                except KeyboardInterrupt as e:
                    print_warning('Keyboard Interrupt.')
                except:
                    try:
                        if (input_str is not None) and len(input_str) > 0:
                            prompt(prompt_str=input_str,
                                   session=get_default_session())
                    except KeyboardInterrupt as e:
                        print_warning('Keyboard Interrupt.')
        except Exception as e:
            print_error(str(e))
            continue


def cli():
    try:
        _run_cli()
    except KeyboardInterrupt as e:
        if CLEAN_MODE:
            delete_session_dir()
    finally:
        if CLEAN_MODE:
            delete_session_dir()


if __name__ == "__main__":
    cli()
