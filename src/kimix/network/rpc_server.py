#!/usr/bin/env python3
"""JSON-RPC Server - JSON-RPC TCP server supporting multiple concurrent clients.

This module provides a JSON-RPC server built on top of TcpGroupServer.
It accepts JSON-RPC 2.0 requests over TCP from multiple clients, dispatches
to registered functions, and returns JSON-RPC 2.0 responses.
"""

import json
import time
from typing import Any, Callable, Optional

from kimix.network.tcp_group_server import TcpGroupServer


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8888


class JSONRPCServer:
    """JSON-RPC server built on top of TcpGroupServer."""

    def __init__(
        self,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        max_workers: int = 10,
        on_client_connect: Optional[Callable[[int, tuple[str, int]], None]] = None,
        on_client_disconnect: Optional[Callable[[int], None]] = None,
    ):
        self._server = TcpGroupServer(host=host, port=port, max_workers=max_workers)
        self._registry: dict[str, Callable[..., Any]] = {}
        self._server.on_raw_data(self._handle_raw_data)
        if on_client_connect is not None:
            self._server.on_client_connect(on_client_connect)
        if on_client_disconnect is not None:
            self._server.on_client_disconnect(on_client_disconnect)

    def register(self, name: str, func: Callable[..., Any]) -> None:
        """Register a function under the given name."""
        self._registry[name] = func

    def register_function(self, func: Callable[..., Any]) -> None:
        """Register a function using its ``__name__``."""
        self._registry[func.__name__] = func

    def _handle_raw_data(self, client_id: int, data: bytes) -> Optional[str]:
        """Parse a JSON-RPC request, invoke the method, and return a response."""
        try:
            request = json.loads(data.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            return json.dumps(
                {
                    "jsonrpc": "2.0",
                    "error": {"code": -32700, "message": f"Parse error: {exc}"},
                }
            )

        if not isinstance(request, dict):
            return json.dumps(
                {
                    "jsonrpc": "2.0",
                    "error": {"code": -32600, "message": "Invalid Request"},
                }
            )

        method_name = request.get("method")
        params = request.get("params", [])

        if not isinstance(method_name, str) or method_name not in self._registry:
            return json.dumps(
                {
                    "jsonrpc": "2.0",
                    "error": {
                        "code": -32601,
                        "message": f"Method not found: {method_name}",
                    },
                }
            )

        func = self._registry[method_name]
        try:
            if isinstance(params, dict):
                result = func(**params)
            elif isinstance(params, list):
                result = func(*params)
            else:
                result = func()
        except TypeError as exc:
            return json.dumps(
                {
                    "jsonrpc": "2.0",
                    "error": {"code": -32602, "message": f"Invalid params: {exc}"},
                }
            )
        except Exception as exc:
            return json.dumps(
                {
                    "jsonrpc": "2.0",
                    "error": {"code": -32603, "message": f"Internal error: {exc}"},
                }
            )

        return json.dumps({"jsonrpc": "2.0", "result": result})

    def start(self, blocking: bool = True) -> None:
        """Start the JSON-RPC server."""
        self._server.start(blocking=blocking)

    def stop(self) -> None:
        """Stop the JSON-RPC server."""
        self._server.stop()

    def get_client_count(self) -> int:
        """Get the number of currently connected clients."""
        return self._server.get_client_count()

    def is_client_connected(self) -> bool:
        """Check if any client is currently connected."""
        return self._server.get_client_count() > 0

    def wait_for_connection(self, timeout: float = 5.0) -> bool:
        """Wait for at least one client to connect."""
        return self._server.wait_for_clients(count=1, timeout=timeout)

    def wait_for_disconnection(self, timeout: float = 5.0) -> bool:
        """Wait for all clients to disconnect."""
        start = time.time()
        while time.time() - start < timeout:
            if self._server.get_client_count() == 0:
                return True
            time.sleep(0.05)
        return False

    def get_client_ids(self) -> list[int]:
        """Get list of currently connected client IDs."""
        return self._server.get_client_ids()

    def disconnect_client(self, client_id: int) -> bool:
        """Disconnect a specific client."""
        return self._server.disconnect_client(client_id)


if __name__ == "__main__":
    def main() -> None:
        def add(a: int, b: int) -> int:
            return a + b

        def subtract(a: int, b: int) -> int:
            return a - b

        def echo(message: str) -> str:
            return message

        def multiply(a: int, b: int) -> int:
            return a * b

        server = JSONRPCServer()
        server.register_function(add)
        server.register_function(subtract)
        server.register_function(echo)
        server.register_function(multiply)
        print(f"[JSONRPCServer] Starting on {DEFAULT_HOST}:{DEFAULT_PORT}")
        server.start(blocking=True)

    main()
