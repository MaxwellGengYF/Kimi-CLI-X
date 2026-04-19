#!/usr/bin/env python3
"""Simple CLI server that hosts a JSON-RPC server with an input_from_client function."""

import argparse
import asyncio
import queue
import sys
import threading
from typing import Any

from kimix.kimi_utils import create_session, close_session, prompt_async
from kimix.network.rpc_server import JSONRPCServer


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8888

client_dict: dict[int, dict[str, Any]] = {}


def _get_or_create_session(client_id: int) -> Any:
    """Lazy create session for a client if not already created."""
    info = client_dict.get(client_id)
    if info is None:
        info = {"session": None, "thread": None, "queue": None}
        client_dict[client_id] = info
    if info["session"] is None:
        info["session"] = create_session(session_id=str(client_id))
    return info["session"]


def input_from_client(client_id: int, text: str) -> str:
    """Receive a string from the client, start prompt_async in a background thread, and return confirmation."""
    print(f"[from client {client_id}] {text}")
    if client_id not in client_dict:
        return "error: client not connected"

    session = _get_or_create_session(client_id)
    output_queue: queue.Queue[str] = queue.Queue()

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
    # TODO check if client_dict[client_id].thread already exists, return error if so.
    client_dict[client_id] = {
        "session": session,
        "thread": thread,
        "queue": output_queue,
    }
    return "processing"


def get_output_from_client(client_id: int) -> list[str]:
    """Get queued output for a client."""
    if client_id not in client_dict:
        return ["error: client not connected"]
    info = client_dict[client_id]
    q = info.get("queue")
    if q is None:
        return []
    outputs = []
    try:
        while True:
            outputs.append(q.get_nowait())
    except queue.Empty:
        pass
    return outputs


def is_session_finished(client_id: int) -> bool:
    """Check whether the prompt thread for a client has finished."""
    if client_id not in client_dict:
        return False
    thread = client_dict[client_id].get("thread")
    if thread is None:
        return False
    return not thread.is_alive()


def on_client_connect(client_id: int, client_addr: tuple[str, int]) -> str:
    """Track a client connection; session is created lazily later."""
    print(client_addr)
    if client_id in client_dict:
        return "error: client already connected"
    client_dict[client_id] = {"session": None, "thread": None, "queue": None}
    return "ok"


def on_client_disconnect(client_id: int) -> str:
    """Close a client's session and clean up tracking dictionaries."""
    if client_id not in client_dict:
        return "error: client not found"
    info = client_dict.pop(client_id)
    session = info.get("session")
    if session is not None:
        close_session(session)
    return "ok"


def server_cli() -> None:
    parser = argparse.ArgumentParser(description="Simple JSON-RPC server")
    parser.add_argument("--host", default=DEFAULT_HOST, help="Host to bind to")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Port to bind to")
    args = parser.parse_args()

    server = JSONRPCServer(host=args.host, port=args.port, on_client_connect=on_client_connect, on_client_disconnect=on_client_disconnect)
    server.register_function(input_from_client)
    server.register_function(get_output_from_client)
    server.register_function(is_session_finished)
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
