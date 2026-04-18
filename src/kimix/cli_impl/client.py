#!/usr/bin/env python3
"""Simple CLI client that connects to the JSON-RPC server and sends input."""

import argparse
import sys

from kimix.network.rpc_client import JSONRPCClient


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8888


def client_cli() -> None:
    parser = argparse.ArgumentParser(description="Simple JSON-RPC client")
    parser.add_argument("--host", default=DEFAULT_HOST, help="Server host")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Server port")
    args = parser.parse_args()

    client = JSONRPCClient(host=args.host, port=args.port)
    if not client.connect():
        print("[client] Failed to connect to server")
        sys.exit(1)
    try:
        while True:
            try:
                text = input("[client] Enter text to send: ")
            except EOFError:
                print("[client] No input provided")
                sys.exit(1)
            if text == 'exit':
                return
            result = client.call("input_from_client", text)
            print(f"[client] Server response: {result}")
    except TimeoutError:
        print("[client] Request timed out")
    except RuntimeError as exc:
        print(f"[client] Server error: {exc}")
    finally:
        client.disconnect()


if __name__ == "__main__":
    client_cli()
