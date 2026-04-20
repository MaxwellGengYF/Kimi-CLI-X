#!/usr/bin/env python3
"""Simple CLI server that hosts a JSON-RPC server with an input_from_client function."""

import argparse
import asyncio

import os
import queue
import sys
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path
import kimix.agent_utils as agent_utils
from kimi_agent_sdk import Session
from kimix.kimi_utils import (
    create_session, close_session as _close_kimi_session, prompt_async,
    clear_context, set_plan_mode, set_ralph_loop,
    close_session_async, _create_session_async,
)
async def clear_context_async(session: Session, force_create: bool = False, resume: bool = False, print_info: bool = True) -> Session:
    """Close the old session, then create a new session and return it."""
    if not force_create and session.status.context_usage < 1e-8:
        return session
    await close_session_async(session)
    return await _create_session_async(session_id=session.id, resume=resume)


from kimix.cli_impl.constants import HELP_STR
from kimix.network.rpc_server import JSONRPCServer


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8888


@dataclass
class SessionEntry:
    client_id: str
    session: Session
    thread: threading.Thread | None = None
    output_queue: queue.Queue[str] | None = None


session_dict: dict[str, SessionEntry] = {}
client_sessions: dict[str, list[str]] = {}


def _generate_session_id() -> str:
    return str(uuid.uuid4())


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
    def _run() -> None:
        async def _inner() -> None:
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
        asyncio.run(_inner())

    thread = threading.Thread(target=_run)
    thread.start()
    session_dict[session_id].thread = thread
    session_dict[session_id].output_queue = output_queue
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


def input_from_client(client_id: int, session_id: str, text: str) -> str:
    """Receive a string from the client, start prompt_async in a background thread, and return confirmation."""
    print(f"[from client {client_id}] session {session_id}: {text}")
    entry = session_dict.get(session_id)
    if entry is None:
        return "error: session not found"
    if entry.client_id != str(client_id):
        return "error: session does not belong to this client"

    existing_thread = entry.thread
    if existing_thread is not None and existing_thread.is_alive():
        return "error: prompt already in progress"

    session = entry.session
    output_queue: queue.Queue[str] = queue.Queue()

    if text.startswith('/'):
        task = text[1:]
        split_idx = task.find(':')
        if split_idx >= 0:
            cmd = task[:split_idx]
            arg = task[split_idx + 1:]
        else:
            cmd = task
            arg = ''
        handler = _command_map.get(cmd, _cmd_unknown)
        new_text = asyncio.run(handler(session_id, session, cmd, arg, output_queue))
        if new_text is None:
            session_dict[session_id].output_queue = output_queue
            return "processing"
        text = new_text
        session = session_dict[session_id].session

    def _run_prompt() -> None:
        try:
            asyncio.run(prompt_async(
                text,
                session=session,
                output_function=output_queue.put,
                info_print=False,
            ))
        except Exception as e:
            output_queue.put(f"[error] {e}")

    thread = threading.Thread(target=_run_prompt)
    thread.start()
    session_dict[session_id] = SessionEntry(
        client_id=str(client_id),
        session=session,
        thread=thread,
        output_queue=output_queue,
    )
    return "processing"


def get_output_from_client(client_id: int, session_id: str) -> list[str]:
    """Get queued output for a session."""
    entry = session_dict.get(session_id)
    if entry is None:
        return ["error: session not found"]
    if entry.client_id != str(client_id):
        return ["error: session does not belong to this client"]
    q = entry.output_queue
    if q is None:
        return []
    outputs = []
    try:
        while True:
            outputs.append(q.get_nowait())
    except queue.Empty:
        pass
    return outputs


def is_session_finished(client_id: int, session_id: str) -> bool:
    """Check whether the prompt thread for a session has finished."""
    entry = session_dict.get(session_id)
    if entry is None:
        return False
    if entry.client_id != str(client_id):
        return False
    thread = entry.thread
    if thread is None:
        return False
    if not thread.is_alive():
        entry.thread = None
        return True
    return False

def open_session(client_id: int) -> str:
    """Open a new session for a client and return the session ID."""
    async def _create() -> Session:
        return await _create_session_async(session_id=str(client_id))

    session = asyncio.run(_create())
    session_id = _generate_session_id()
    session_dict[session_id] = SessionEntry(
        client_id=str(client_id),
        session=session,
        thread=None,
        output_queue=None,
    )
    client_sessions.setdefault(str(client_id), []).append(session_id)
    print(f"[open_session] client {client_id} opened session {session_id}")
    return session_id


def close_session(client_id: int, session_id: str) -> str:
    """Close a session. Only the client that opened the session can close it."""
    entry = session_dict.get(session_id)
    if entry is None:
        return "error: session not found"
    if entry.client_id != str(client_id):
        return "error: session does not belong to this client"

    _close_kimi_session(entry.session)
    del session_dict[session_id]

    sessions = client_sessions.get(str(client_id), [])
    if session_id in sessions:
        sessions.remove(session_id)
    if not sessions:
        client_sessions.pop(str(client_id), None)

    print(f"[close_session] client {client_id} closed session {session_id}")
    return "ok"


def on_client_connect(client_id: int, client_addr: tuple[str, int]) -> None:
    """Track a client connection."""
    print(client_addr)
    if str(client_id) not in client_sessions:
        client_sessions[str(client_id)] = []


def on_client_disconnect(client_id: int) -> None:
    """Close all sessions for a client and clean up tracking dictionaries."""
    sessions = client_sessions.pop(str(client_id), [])
    for session_id in sessions:
        entry = session_dict.pop(session_id, None)
        if entry is not None and entry.session is not None:
            _close_kimi_session(entry.session)

def server_cli() -> None:
    parser = argparse.ArgumentParser(description="Simple JSON-RPC server")
    parser.add_argument("--host", default=DEFAULT_HOST, help="Host to bind to")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Port to bind to")
    args = parser.parse_args()

    server = JSONRPCServer(host=args.host, port=args.port, on_client_connect=on_client_connect, on_client_disconnect=on_client_disconnect)
    server.register_function(input_from_client)
    server.register_function(get_output_from_client)
    server.register_function(is_session_finished)
    server.register_function(open_session)
    server.register_function(close_session)
    print(f"[server] Starting on {args.host}:{args.port}")
    print("[server] Press Ctrl+C to stop")

    try:
        server.start(blocking=True)
    except KeyboardInterrupt:
        print("\n[server] Stopping...")
    finally:
        server.stop()


if __name__ == "__main__":
    server_cli()
