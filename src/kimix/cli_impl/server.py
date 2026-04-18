#!/usr/bin/env python3
"""Simple CLI server that hosts a JSON-RPC server with an input_from_client function."""

import argparse
import sys
from typing import Any

from kimix.kimi_utils import create_session, close_session
from kimix.network.rpc_server import JSONRPCServer


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8888

client_dict: dict[int, Any] = {}


def input_from_client(text: str) -> str:
    """Receive a string from the client, print it, and return confirmation."""
    print(f"[from client] {text}")
    return f"received: {text}"


def on_client_connect(client_id: int, client_addr: tuple[str, int]) -> str:
    """Create a session for a client and track the mapping."""
    print(client_addr)
    session_id = str(client_id)
    if client_id in client_dict:
        return "error: client already connected"
    session = create_session(session_id=session_id)
    client_dict[client_id] = session
    return "ok"


def on_client_disconnect(client_id: int) -> str:
    """Close a client's session and clean up tracking dictionaries."""
    session = client_dict.pop(client_id, None)
    if session is None:
        return "error: client not found"
    close_session(session)
    return "ok"


def server_cli() -> None:
    parser = argparse.ArgumentParser(description="Simple JSON-RPC server")
    parser.add_argument("--host", default=DEFAULT_HOST, help="Host to bind to")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Port to bind to")
    args = parser.parse_args()

    server = JSONRPCServer(host=args.host, port=args.port, on_client_connect=on_client_connect, on_client_disconnect=on_client_disconnect)
    server.register_function(input_from_client)
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
