#!/usr/bin/env python3
"""Simple CLI client that connects to the JSON-RPC server and sends input."""

import argparse
import sys
import time

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
                text = input("> ")
            except EOFError:
                print("[client] No input provided")
                break
            if text == "exit":
                break
            result = client.call("input_from_client", text)
            if result != "processing":
                print(f"[client] Server response: {result}")
                continue
            while True:
                outputs = client.call("get_output_from_client")
                for output in outputs:
                    print(output, end="\n")
                finished = client.call("is_session_finished")
                if finished:
                    break
                time.sleep(1.0)
    except TimeoutError:
        print("[client] Request timed out")
    except RuntimeError as exc:
        print(f"[client] Server error: {exc}")
    finally:
        client.disconnect()


if __name__ == "__main__":
    client_cli()
