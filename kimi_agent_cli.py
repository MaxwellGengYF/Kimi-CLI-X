# API credentials for Kimi Code Console
import agent_utils
from pathlib import Path
from kaos.path import KaosPath
import asyncio
from kimi_utils import print_success, print_error, print_warning, print_info, prompt, clear_context, sync_all,  _create_default_session, print_usage, delete_session_dir, print_debug, get_default_session, fix_error, validate
import os
import sys
import subprocess
LSP_JSON = None
frame = 0
read_agent = False
COMMENT = """Always write ' Start writen by AGENT ' comment before code, Always write ' End writen by AGENT ' comment after code"""
curr_dir = Path(os.curdir)
if not curr_dir.is_absolute():
    curr_dir = curr_dir.absolute()

# Start writen by AGENT
HELP_STR = '''Command line options:
  -c, --clean         - Delete cache file after quit
  --ralph             - Continue work until done (auto-loop)
  --think          - Enable thinking mode
  --plan           - Enable plan mode
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
  /txt            - input multiple line text
  /think:on       - Enable thinking mode
  /think:off      - Disable thinking mode
  /plan:on        - Enable plan mode
  /plan:off       - Disable plan mode
  /script         - Write python script
  /cmd            - Write cmd 
  /cd             - change dir
  /tool:<name>    - Run script from tools/ directory
  /tool:help      - List all available tools
  /md:on          - Enable read AGENTS.md
  /md:off         - Disable read AGENTS.md

Or enter any prompt to send to the agent.
'''
# End writen by AGENT
CLEAN_MODE = None
globals_dict = {}
locals_dict = {}


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
                        help='Enable thinking mode')
    parser.add_argument('-plan', '--plan', action='store_true',
                        help='Enable plan mode')
    parser.add_argument('-no_yolo', '--no_yolo', action='store_true',
                        help='Disable YOLO mode')
    parser.add_argument('-s', '--skill-dir', type=str, nargs='*', default=None,
                        help='Specify custom skill directory(s)')
    args = parser.parse_args()
    if args.no_color:
        agent_utils._colorful_print = False

    CLEAN_MODE = args.clean
    if CLEAN_MODE:
        print_debug('Clean mode ON, delete cache file after quit.')
    else:
        print_debug('Clean mode OFF.')

    if args.ralph:
        agent_utils._ralph_iterations = -1
        print_debug(
            'Ralph loop ON, continue work until done(or running OUT of your TOKEN!!!).')
    else:
        agent_utils._ralph_iterations = 0
        print_debug('Ralph loop OFF.')

    if args.think:
        agent_utils._default_thinking = True
        print_debug('Thinking ON.')
    else:
        agent_utils._default_thinking = False
        print_debug('Thinking OFF.')

    if args.plan:
        agent_utils._default_plan_mode = True
        print_debug('Plan mode ON.')
    else:
        agent_utils._default_plan_mode = False
        print_debug('Plan mode OFF.')

    if args.no_yolo:
        agent_utils._default_yolo = False
        print_debug('YOLO OFF.')
    else:
        agent_utils._default_yolo = True
        print_debug('YOLO ON.')

    # Handle --skill-dir argument
    if args.skill_dir:
        for skill_dir in args.skill_dir:
            skill_dir_path = Path(skill_dir)
            if not skill_dir_path.is_absolute():
                skill_dir_path = curr_dir / skill_dir_path
            # Normalize the path (resolve ., .., and symlinks)
            skill_dir_path = skill_dir_path.resolve()
            if skill_dir_path.exists() and skill_dir_path.is_dir():
                agent_utils._default_skill_dirs.append(KaosPath(skill_dir_path))
                print_debug(f'Skill dir added: {str(skill_dir_path)}')
            else:
                print_warning(f'Skill dir not found: {str(skill_dir_path)}')


def _input(text: str, text_arr: list) -> str:
    if text_arr is None or len(text_arr) == 0:
        return input(text)
    v = text_arr.pop(0)
    return v


def _split_text(lines):
    text_arr = []
    current_text = []
    for line in lines:
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
    exec_ctx = {
        '__name__': '__main__'
    }
    set_arg()
    # Parse command line arguments for clean mode flag

    input_str = None
    _create_default_session(False)
    assert get_default_session()
    text_arr = []

    def _cmd_help(task_split):
        print(HELP_STR)
        return None, False

    def _cmd_clear(task_split):
        clear_context()
        return None, False

    def _cmd_exit(task_split):
        print_success('bye!')
        return None, True

    def _cmd_context(task_split):
        print_usage()
        return None, False

    def _cmd_script(task_split):
        print('\n>>>> Start input multiple-lines, end with /end')
        text = []
        while True:
            s = _input('', text_arr)
            if s.strip() == '/end':
                break
            text.append(s)
        text = '\n'.join(text)
        global globals_dict, locals_dict
        try:
            exec(text, globals_dict, locals_dict)
            print_success('Finished.')
        except Exception as e:
            print_error(str(e))
        return None, False

    def _cmd_cmd(task_split):
        s = _input('>>>> Input cmd:\n', text_arr)
        try:
            os.system(s)
            print_success('Finished.')
        except Exception as e:
            print_error(str(e))
        return None, False

    def _cmd_cd(task_split):
        if len(task_split) < 2:
            print_error('Command must be /cd:PATH')
            return None, False
        path = ':'.join(task_split[1:])
        try:
            os.chdir(path)
            agent_utils._default_skill_dirs = []
            clear_context(True, True)
            print_success(f'Changed directory to: {Path(".").resolve()}')
        except Exception as e:
            print_error(f'Failed to change directory: {e}')
        return None, False

    def _cmd_fix(task_split):
        if len(task_split) < 2:
            print_error('Command must be /fix:<command>')
            return None, False
        command_to_fix = task_split[1].strip()
        if not command_to_fix:
            print_error('Command must be /fix:<command>')
            return None, False
        fix_error(command_to_fix, session=get_default_session())
        return None, False

    def _cmd_validate(task_split):
        if len(task_split) < 2:
            print_error('Command must be /validate:prompt')
            return None, False
        result = validate(task_split[1], get_default_session())
        print_info(f'Validate result: {result}')
        return None, False

    def _cmd_md(task_split):
        global read_agent
        if len(task_split) < 2:
            print_error('Command must be /md:on or /md:off')
            return None, False
        value = task_split[1].strip().lower()
        if value == 'on':
            read_agent = True
            print_success('Read markdown mode enabled.')
        elif value == 'off':
            read_agent = False
            print_success('Read markdown disabled.')
        else:
            print_error('Command must be /think:on or /think:off')
            return None, False
        return None, False

    def _cmd_think(task_split):
        if len(task_split) < 2:
            print_error('Command must be /think:on or /think:off')
            return None, False
        value = task_split[1].strip().lower()
        if value == 'on':
            agent_utils._default_thinking = True
            print_success('Thinking mode enabled.')
        elif value == 'off':
            agent_utils._default_thinking = False
            print_success('Thinking mode disabled.')
        else:
            print_error('Command must be /think:on or /think:off')
            return None, False
        clear_context(True, True)
        return None, False

    def _cmd_plan(task_split):
        if len(task_split) < 2:
            print_error('Command must be /plan:on or /plan:off')
            return None, False
        value = task_split[1].strip().lower()
        if value == 'on':
            agent_utils._default_plan_mode = True
            print_success('Plan mode enabled.')
        elif value == 'off':
            agent_utils._default_plan_mode = False
            print_success('Plan mode disabled.')
        else:
            print_error('Command must be /plan:on or /plan:off')
            return None, False
        clear_context(True, True)
        return None, False

    def _cmd_txt(task_split):
        print('\n>>>> Start input multiple-lines, end with /end')
        text = []
        while True:
            s = _input('', text_arr)
            if s.strip() == '/end':
                break
            text.append(s)
        for i in _split_text(text):
            text_arr.append(i)
        return None, False

    def _cmd_skill(task_split):
        if len(task_split) < 2:
            print_error('Command must be /skill:xx')
            return None, False
        prompt(f"/skill:{task_split[1]}", get_default_session())
        return None, False

    def _cmd_file(task_split):
        if len(task_split) != 2:
            print_error(f'command format error, must be /file:path')
            return None, False
        return task_split[1], False

    def _cmd_tool(task_split):
        tools_dir = Path(__file__).parent / 'tools'

        if len(task_split) < 2:
            print_error('Command must be /tool:<script_name> or /tool:help')
            return None, False

        tool_name = task_split[1].strip()

        # Handle help command
        if tool_name == 'help':
            if not tools_dir.exists():
                print_info('No tools directory found.')
                return None, False

            tool_files = sorted(
                [f for f in tools_dir.iterdir() if f.suffix == '.py'])
            if not tool_files:
                print_info('No tools available in tools/ directory.')
            else:
                print_success('Available tools:')
                for tool_file in tool_files:
                    print_info(f'  - {tool_file.name}')
            return None, False

        # Remove .py extension if present
        if tool_name.endswith('.py'):
            tool_name = tool_name[:-3]

        tool_path = tools_dir / f'{tool_name}.py'

        if not tool_path.exists():
            print_error(f'Tool not found: {tool_name}.py')
            return None, False

        try:
            print_info(f'Running tool: {tool_name}.py')
            # Read and execute the tool script
            with open(tool_path, 'r', encoding='utf-8') as f:
                script_content = f.read()

            # Create a clean execution context
            exec(script_content, {
                '__name__': '__main__',
                '__file__': str(tool_path),
            })
            print_success(f'Tool {tool_name}.py finished.')
        except Exception as e:
            print_error(f'Failed to run tool {tool_name}.py: {e}')
        return None, False

    def _cmd_unknown(task_split):
        print_warning('Unrecognized command.')
        return None, False

    _command_map = {
        'help': _cmd_help,
        'clear': _cmd_clear,
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
        'file': _cmd_file,
        'tool': _cmd_tool,
        'md': _cmd_md
    }

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
            if input_str is not None and input_str[0] == '/':
                task = input_str[1:]
                split_idx = task.strip().find(':')
                if split_idx >= 0:
                    task_split = (task[:split_idx], task[split_idx+1:])
                else:
                    task_split = (task,)
                handler = _command_map.get(task_split[0], _cmd_unknown)
                new_input_str, should_break = handler(task_split)
                if should_break:
                    break
                if new_input_str is not None:
                    input_str = new_input_str
                else:
                    continue
            elif input_str is not None and len(input_str) > 0:
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
                            print_info(
                                f'Executing {path.name}', end='\n\n')
                            try:
                                exec_ctx['__file__'] = path
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
                                   session=get_default_session(),
                                   read_agents_md=read_agent)
                    except KeyboardInterrupt as e:
                        print_warning('Keyboard Interrupt.')
        except Exception as e:
            print_error(str(e))


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
