# API credentials for Kimi Code Console
from pathlib import Path
from kaos.path import KaosPath
import asyncio
from kimi_utils import print_success, print_error, print_warning, print_info, prompt, clear_context, sync_all,  _create_default_session, print_usage, delete_session_dir, print_debug, get_default_session
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
HELP_STR = '''Available commands:
  /file:<path>    - Load a file and execute its content line by line
  <path>          - Same as /file:<path>
  /clear          - Clear the conversation context
  /compact        - Compact context
  /exit           - Exit the program
  /skill          - Load skills
  /help           - Show this help message
  /context        - Print context usage

Or enter any prompt to send to the agent.
'''
# End writen by AGENT


CLEAN_MODE = '-c' in sys.argv or '--clean' in sys.argv
if CLEAN_MODE:
    print_debug('Enable clean mode, delete cache file after quit')
if '-ralph' in sys.argv or '--ralph' in sys.argv:
    kimi_utils._ralph_iterations = -1
    print_debug(
        'Enable ralph loop, continue work until done(or running OUT of your TOKEN!!!). ')

if '--think=false' in sys.argv or '-think=false' in sys.argv:
    kimi_utils._default_thinking = False
    print_debug('disable thinking')
if '--yolo=false' in sys.argv or '-yolo=false' in sys.argv:
    kimi_utils._default_yolo = False
    print_debug('disable yolo')


def _run_cli():
    # Parse command line arguments for clean mode flag

    # Read user input from keyboard asynchronously
    exec_ctx = None
    special_commands = {
        'clear', 'exit', 'help', 'compact', 'context'
    }
    input_str = None
    _create_default_session()
    assert get_default_session()
    while True:
        try:
            input_str = input("\n>>>>>>>>> Enter your prompt or command:\n")
        except KeyboardInterrupt as e:
            print_success('bye.')
            break
        except EOFError as e:
            print_success('bye.')
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
                elif task_split[0] == 'compact':
                    prompt(f"/compact", get_default_session())
                    continue
                elif task_split[0] == 'exit':
                    print_success('bye!')
                    break
                elif task_split[0] == 'context':
                    print_usage()
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
                            f'command format error, should be /file:path')
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
                            print_warning('File not executable')
                    except KeyboardInterrupt as e:
                        raise e
                    except Exception as e:
                        print_error(str(e))
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
