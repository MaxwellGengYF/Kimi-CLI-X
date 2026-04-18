#!/usr/bin/env python3
"""JSON-RPC Client CLI - Main entry point for JSON-RPC TCP client.

This module provides a JSON-RPC client built on top of the low-level TCPClient.
It sends JSON-RPC 2.0 requests over TCP and returns the decoded results.
"""

import json
import threading
from typing import Any

from kimix.network.tcp_client import TCPClient


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8888


class JSONRPCClient:
    """JSON-RPC client built on top of TCPClient."""

    def __init__(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT):
        self._client = TCPClient(host=host, port=port)
        self._client.on_message(self._handle_message)
        self._lock = threading.Lock()
        self._pending_event = threading.Event()
        self._last_response: Any = None

    def _handle_message(self, message: str) -> None:
        try:
            response = json.loads(message)
        except json.JSONDecodeError:
            return
        with self._lock:
            self._last_response = response
            self._pending_event.set()

    def connect(self) -> bool:
        """Connect to the JSON-RPC server."""
        return self._client.connect()

    def disconnect(self) -> None:
        """Disconnect from the JSON-RPC server."""
        self._client.disconnect()

    def is_connected(self) -> bool:
        """Check if connected to the server."""
        return self._client.is_connected()

    def call(self, method: str, *args: Any, timeout: float = 5.0) -> Any:
        """Call a remote method and return its result.

        Args:
            method: Name of the remote method.
            *args: Positional arguments for the remote method.
            timeout: Maximum seconds to wait for a response.

        Returns:
            The ``result`` field from the JSON-RPC response.

        Raises:
            TimeoutError: If no response is received within *timeout*.
            RuntimeError: If the server returns a JSON-RPC error.
        """
        with self._lock:
            self._pending_event.clear()

        request = {
            "jsonrpc": "2.0",
            "method": method,
            "params": list(args),
        }
        self._client.send(json.dumps(request))

        if not self._pending_event.wait(timeout=timeout):
            raise TimeoutError(f"JSON-RPC call to '{method}' timed out")

        with self._lock:
            response = self._last_response
            self._last_response = None

        if "error" in response:
            raise RuntimeError(
                f"JSON-RPC error: {response['error']['message']}"
            )

        return response.get("result")


if __name__ == "__main__":
    def main() -> None:
        client = JSONRPCClient()
        if not client.connect():
            print("[JSONRPCClient] Failed to connect")
            return
        try:
            result = client.call("add", 1, 2)
            print(f"[JSONRPCClient] add(1,2) = {result}")
        finally:
            client.disconnect()


    main()
