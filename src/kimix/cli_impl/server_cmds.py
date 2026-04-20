from dataclasses import dataclass
from pathlib import Path
import kimix.agent_utils as agent_utils
import threading
import queue
import os
from kimix.cli_impl.constants import HELP_STR
from kimix.kimi_utils import (
    prompt_async,
    close_session_async, _create_session_async,
)
from kimi_agent_sdk import Session
@dataclass
class SessionEntry:
    client_id: str
    session: Session
    thread: threading.Thread | None = None
    task_queue: queue.Queue | None = None
    stop_event: threading.Event | None = None
    output_queue: queue.Queue[str] | None = None
    running: bool = False



session_dict: dict[str, SessionEntry] = {}

async def clear_context_async(session: Session, force_create: bool = False, resume: bool = False, print_info: bool = True) -> Session:
    """Close the old session, then create a new session and return it."""
    if not force_create and session.status.context_usage < 1e-8:
        return session
    await close_session_async(session)
    return await _create_session_async(session_id=session.id, resume=resume)


async def _cmd_help(session_id: str, session: Session, cmd: str, arg: str, output_queue: queue.Queue[str]) -> str | None:
    output_queue.put(HELP_STR)
    return None


async def _cmd_clear(session_id: str, session: Session, cmd: str, arg: str, output_queue: queue.Queue[str]) -> str | None:
    new_session = await clear_context_async(session, force_create=True, resume=False, print_info=False)
    session_dict[session_id].session = new_session
    from kimix.agent_utils import percentage_str
    output_queue.put(f'Context cleared. Usage: {percentage_str(new_session.status.context_usage)}')
    return None


async def _cmd_summarize(session_id: str, session: Session, cmd: str, arg: str, output_queue: queue.Queue[str]) -> str | None:
    try:
        from kimix.summarize import generate_memory, read_memory
        from my_tools.common import _create_temp_file_name
        from kimix.agent_utils import percentage_str
        temp_file = _create_temp_file_name()
        Path(temp_file).unlink(missing_ok=True)
        last_usage = session.status.context_usage
        await prompt_async(generate_memory.substitute(memory_file=temp_file), session=session, output_function=output_queue.put, info_print=False)
        await close_session_async(session)
        new_session = await _create_session_async(session_id=str(session_id))
        await prompt_async(read_memory.substitute(memory_file=temp_file), session=new_session, output_function=output_queue.put, info_print=False)
        new_usage = new_session.status.context_usage
        output_queue.put(f'Compact from {percentage_str(last_usage)} to {percentage_str(new_usage)}')
        session_dict[session_id].session = new_session
    except Exception as e:
        output_queue.put(f"[error] {e}")
    return None


async def _cmd_exit(session_id: str, session: Session, cmd: str, arg: str, output_queue: queue.Queue[str]) -> str | None:
    output_queue.put('bye!')
    return None


async def _cmd_context(session_id: str, session: Session, cmd: str, arg: str, output_queue: queue.Queue[str]) -> str | None:
    from kimix.agent_utils import percentage_str
    output_queue.put(f'Context usage: {percentage_str(session.status.context_usage)}')
    return None


async def _cmd_script(session_id: str, session: Session, cmd: str, arg: str, output_queue: queue.Queue[str]) -> str | None:
    if not arg:
        output_queue.put('[error] Command must be /script:<code>')
        return None
    try:
        exec(arg, {}, {})
        output_queue.put('Done.')
    except Exception as e:
        output_queue.put(f'[error] {e}')
    return None


async def _cmd_cmd(session_id: str, session: Session, cmd: str, arg: str, output_queue: queue.Queue[str]) -> str | None:
    if not arg:
        output_queue.put('[error] Command must be /cmd:<command>')
        return None
    try:
        os.system(arg)
        output_queue.put('Done.')
    except Exception as e:
        output_queue.put(f'[error] {e}')
    return None


async def _cmd_cd(session_id: str, session: Session, cmd: str, arg: str, output_queue: queue.Queue[str]) -> str | None:
    if not arg:
        output_queue.put('[error] Command must be /cd:<path>')
        return None
    try:
        os.chdir(arg)
        agent_utils._default_skill_dirs = []
        new_session = await clear_context_async(session, force_create=True, resume=True, print_info=False)
        session_dict[session_id].session = new_session
        output_queue.put(f'Changed directory to: {Path(".").resolve()}')
    except Exception as e:
        output_queue.put(f'[error] Failed to change directory: {e}')
    return None


async def _cmd_fix(session_id: str, session: Session, cmd: str, arg: str, output_queue: queue.Queue[str]) -> str | None:
    if not arg:
        output_queue.put('[error] Command must be /fix:<command>')
        return None
    from kimix.agent_utils import run_process_with_error
    result = run_process_with_error(arg, ('error',), skip_success=True)
    if result is None:
        output_queue.put('No error.')
        return None
    prompt_str = f'Fix "error" from command {arg}:\n{result}\n'
    try:
        from my_tools.common import _maybe_export_output
        prompt_str = _maybe_export_output(prompt_str)
    except Exception:
        pass
    return prompt_str


async def _cmd_think(session_id: str, session: Session, cmd: str, arg: str, output_queue: queue.Queue[str]) -> str | None:
    value = arg.strip().lower()
    if value == 'on':
        agent_utils._default_thinking = True
        output_queue.put('Thinking mode enabled.')
    elif value == 'off':
        agent_utils._default_thinking = False
        output_queue.put('Thinking mode disabled.')
    else:
        output_queue.put('[error] Command must be /think:on or /think:off')
        return None
    new_session = await clear_context_async(session, force_create=True, resume=True, print_info=False)
    if new_session is not None:
        session_dict[session_id].session = new_session
    return None



async def _cmd_txt(session_id: str, session: Session, cmd: str, arg: str, output_queue: queue.Queue[str]) -> str | None:
    if not arg:
        output_queue.put('[error] Command must be /txt:<text>')
        return None
    return arg


async def _cmd_skill(session_id: str, session: Session, cmd: str, arg: str, output_queue: queue.Queue[str]) -> str | None:
    if not arg:
        output_queue.put('[error] Command must be /skill:<name>')
        return None
    return f'Use skill:{arg}.\n'


async def _cmd_file(session_id: str, session: Session, cmd: str, arg: str, output_queue: queue.Queue[str]) -> str | None:
    if not arg:
        output_queue.put('[error] Command must be /file:<path>')
        return None
    file_path = Path(arg)
    if not file_path.is_absolute():
        file_path = Path(os.getcwd()) / file_path
    if not file_path.is_file():
        output_queue.put(f'[error] file not found: {file_path}')
        return None
    try:
        content = file_path.read_text(encoding='utf-8', errors='replace')
        return content
    except Exception as e:
        output_queue.put(f'[error] {e}')
        return None


async def _cmd_unknown(session_id: str, session: Session, cmd: str, arg: str, output_queue: queue.Queue[str]) -> str | None:
    output_queue.put('Unrecognized command.')
    return None


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
    'txt': _cmd_txt,
    'skill': _cmd_skill,
    'file': _cmd_file
}
