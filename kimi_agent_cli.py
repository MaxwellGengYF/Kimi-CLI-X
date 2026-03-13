# API credentials for Kimi Code Console
from pathlib import Path
from kaos.path import KaosPath
import asyncio
from kimi_utils import print_success, print_error, print_warning, print_info, prompt, clear_context, compact_context, sync_all, skill, _create_default_session, print_usage
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
kimi_utils.default_work_dir = KaosPath(curr_dir)
work_dir = KaosPath(str(curr_dir))
skills_dir = KaosPath(str(curr_dir)) / '.agents/skills'
if not (asyncio.run(skills_dir.exists())):
    skills_dir = None

exec_ctx = None


def normalize_path(path: str):
    p = Path(path)
    if p.is_absolute():
        p = p.relative_to(curr_dir)
    return str(p).replace('\\', '/')


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


def cli():
    # Read user input from keyboard asynchronously
    global exec_ctx
    special_commands = {
        'clear', 'exit', 'help', 'compact', 'context'
    }
    input_str = None
    _create_default_session(work_dir=work_dir, skills_dir=skills_dir)
    while True:
        try:
            input_str = input("\n>>>>>>>>> Enter your prompt or command:\n")
        except KeyboardInterrupt as e:
            print_success('bye.')
            return
        except EOFError as e:
            print_success('bye.')
            return
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
                    compact_context()
                    continue
                elif task_split[0] == 'exit':
                    print_success('bye!')
                    return
                elif task_split[0] == 'context':
                    print_usage()
                    continue
                elif task_split[0] == 'skill':
                    if len(task_split) < 2:
                        print_error('Command must be /skill:xx')
                        continue
                    skill(task_split[1])
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
                            prompt(prompt_str=input_str)
                    except KeyboardInterrupt as e:
                        print_warning('Keyboard Interrupt.')
        except Exception as e:
            print_error(str(e))
            continue


if __name__ == "__main__":
    cli()
