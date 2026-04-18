#!/usr/bin/env python3
"""Simple CLI server that hosts a JSON-RPC server with an input_from_client function."""

import argparse
import sys

from kimix.network.rpc_server import JSONRPCServer


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8888


def input_from_client(text: str) -> str:
    """Receive a string from the client, print it, and return confirmation."""
    print(f"[from client] {text}")
    return f"received: {text}"


def server_cli() -> None:
    parser = argparse.ArgumentParser(description="Simple JSON-RPC server")
    parser.add_argument("--host", default=DEFAULT_HOST, help="Host to bind to")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Port to bind to")
    args = parser.parse_args()

    server = JSONRPCServer(host=args.host, port=args.port)
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
