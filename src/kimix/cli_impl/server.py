#!/usr/bin/env python3
"""Simple CLI server that hosts a JSON-RPC server with an input_from_client function."""

import argparse
import asyncio

import queue

import threading
import uuid
from pathlib import Path
import kimix.agent_utils as agent_utils
from kimi_agent_sdk import Session
from kimix.kimi_utils import (
    create_session, close_session as _close_kimi_session, prompt_async,
    clear_context, set_plan_mode, set_ralph_loop,
    close_session_async, _create_session_async,
)
from kimix.cli_impl.server_cmds import _command_map, _cmd_unknown, session_dict, SessionEntry
from kimix.network.rpc_server import JSONRPCServer


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8888



client_sessions: dict[str, list[str]] = {}


def _generate_session_id() -> str:
    return str(uuid.uuid4())



# RPC function
def input_from_client(client_id: int, session_id: str, text: str) -> str:
    """Receive a string from the client, enqueue it in the session task queue, and return confirmation."""
    print(f"[from client {client_id}] session {session_id}: {text}")
    entry = session_dict.get(session_id)
    if entry is None:
        return "error: session not found"
    if entry.client_id != str(client_id):
        return "error: session does not belong to this client"
    if entry.task_queue is None:
        return "error: session not initialized"

    output_queue: queue.Queue[str] = queue.Queue()

    def _run_task() -> None:
        try:
            _session = entry.session
            _text = text

            if _text.startswith('/'):
                task = _text[1:]
                split_idx = task.find(':')
                if split_idx >= 0:
                    cmd = task[:split_idx]
                    arg = task[split_idx + 1:]
                else:
                    cmd = task
                    arg = ''
                handler = _command_map.get(cmd, _cmd_unknown)
                new_text = asyncio.run(handler(session_id, _session, cmd, arg, output_queue))
                if new_text is None:
                    return
                _text = new_text
                _session = entry.session

            asyncio.run(prompt_async(
                _text,
                session=_session,
                output_function=output_queue.put,
                info_print=False,
            ))
        except Exception as e:
            output_queue.put(f"[error] {e}")

    entry.task_queue.put((_run_task, output_queue))
    return "processing"


# RPC function
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


# RPC function
def is_session_finished(client_id: int, session_id: str) -> bool:
    """Check whether the current task for a session has finished."""
    entry = session_dict.get(session_id)
    if entry is None:
        return False
    if entry.client_id != str(client_id):
        return False
    if entry.task_queue is None:
        return False
    return not entry.running and entry.task_queue.empty()

# RPC function
def _session_worker(session_id: str, entry: SessionEntry) -> None:
    """Worker thread that processes tasks from the session task queue until stopped."""
    while entry.stop_event is not None and not entry.stop_event.is_set():
        if entry.task_queue is None:
            break
        try:
            task_func, output_queue = entry.task_queue.get(timeout=0.1)
        except queue.Empty:
            continue
        entry.output_queue = output_queue
        entry.running = True
        try:
            task_func()
        except Exception as e:
            output_queue.put(f"[error] {e}")
        entry.running = False

# RPC function
def open_session(client_id: int) -> str:
    """Open a new session for a client and return the session ID."""
    async def _create() -> Session:
        return await _create_session_async(session_id=str(client_id))

    session = asyncio.run(_create())
    session_id = _generate_session_id()
    entry = SessionEntry(
        client_id=str(client_id),
        session=session,
        thread=None,
        task_queue=queue.Queue(),
        stop_event=threading.Event(),
        output_queue=None,
    )
    thread = threading.Thread(target=_session_worker, args=(session_id, entry))
    entry.thread = thread
    thread.start()
    session_dict[session_id] = entry
    client_sessions.setdefault(str(client_id), []).append(session_id)
    print(f"[open_session] client {client_id} opened session {session_id}")
    return session_id

# RPC function
def close_session(client_id: int, session_id: str) -> str:
    """Close a session. Only the client that opened the session can close it."""
    entry = session_dict.get(session_id)
    if entry is None:
        return "error: session not found"
    if entry.client_id != str(client_id):
        return "error: session does not belong to this client"

    if entry.stop_event is not None:
        entry.stop_event.set()
    if entry.thread is not None:
        entry.thread.join(timeout=5.0)

    _close_kimi_session(entry.session)
    del session_dict[session_id]

    sessions = client_sessions.get(str(client_id), [])
    if session_id in sessions:
        sessions.remove(session_id)
    if not sessions:
        client_sessions.pop(str(client_id), None)

    print(f"[close_session] client {client_id} closed session {session_id}")
    return "ok"

# RPC function
def on_client_connect(client_id: int, client_addr: tuple[str, int]) -> None:
    """Track a client connection."""
    print(client_addr)
    if str(client_id) not in client_sessions:
        client_sessions[str(client_id)] = []

# RPC function
def on_client_disconnect(client_id: int) -> None:
    """Close all sessions for a client and clean up tracking dictionaries."""
    sessions = client_sessions.pop(str(client_id), [])
    for session_id in sessions:
        entry = session_dict.pop(session_id, None)
        if entry is not None:
            if entry.stop_event is not None:
                entry.stop_event.set()
            if entry.thread is not None:
                entry.thread.join(timeout=2.0)
            if entry.session is not None:
                _close_kimi_session(entry.session)

def server_cli() -> None:
    parser = argparse.ArgumentParser(description="Simple JSON-RPC server")
    parser.add_argument("--host", default=DEFAULT_HOST, help="Host to bind to")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Port to bind to")
    parser.add_argument("--ws-port", type=int, default=None, help="WebSocket bridge port (optional)")
    args = parser.parse_args()

    server = JSONRPCServer(host=args.host, port=args.port, on_client_connect=on_client_connect, on_client_disconnect=on_client_disconnect)
    server.register_function(input_from_client)
    server.register_function(get_output_from_client)
    server.register_function(is_session_finished)
    server.register_function(open_session)
    server.register_function(close_session)
    print(f"[server] Starting on {args.host}:{args.port}")
    if args.ws_port:
        print(f"[server] WebSocket bridge on ws://{args.host}:{args.ws_port}")
    print("[server] Press Ctrl+C to stop")

    server.start(blocking=False)
    if args.ws_port:
        server.start_websocket_server(args.ws_port, blocking=False)

    try:
        import time
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[server] Stopping...")
    finally:
        if args.ws_port:
            server.stop_websocket_server()
        server.stop()


if __name__ == "__main__":
    server_cli()
