# -*- coding: utf-8 -*-
"""Kimix JSON-RPC / WebSocket client for communicating with kimix server."""

import json
import logging
import threading
import time
from typing import Any, Callable, List, Optional

logger = logging.getLogger(__name__)


class KimixJsonRpcClient:
    """JSON-RPC TCP client for kimix server."""

    def __init__(self, host: str = "127.0.0.1", port: int = 8896):
        self.host = host
        self.port = port
        self._sock: Optional[Any] = None
        self._lock = threading.Lock()
        self._pending_event = threading.Event()
        self._last_response: Any = None
        self._buffer = b""
        self._recv_thread: Optional[threading.Thread] = None
        self._stop_recv = threading.Event()

    def connect(self, timeout: float = 5.0) -> bool:
        import socket
        try:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._sock.settimeout(timeout)
            self._sock.connect((self.host, self.port))
            self._sock.settimeout(None)
            self._stop_recv.clear()
            self._recv_thread = threading.Thread(target=self._recv_loop, daemon=True)
            self._recv_thread.start()
            return True
        except Exception as exc:
            logger.error("[KimixClient] Connect failed: %s", exc)
            self._sock = None
            return False

    def disconnect(self) -> None:
        self._stop_recv.set()
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None
        if self._recv_thread:
            self._recv_thread.join(timeout=2.0)
            self._recv_thread = None

    def is_connected(self) -> bool:
        return self._sock is not None

    def _recv_loop(self) -> None:
        while not self._stop_recv.is_set() and self._sock:
            try:
                data = self._sock.recv(4096)
                if not data:
                    break
                self._buffer += data
                while b"\n" in self._buffer:
                    line, self._buffer = self._buffer.split(b"\n", 1)
                    if line:
                        self._handle_message(line.decode("utf-8", errors="replace"))
            except Exception:
                break
        self._sock = None

    def _handle_message(self, message: str) -> None:
        try:
            response = json.loads(message)
        except json.JSONDecodeError:
            return
        with self._lock:
            self._last_response = response
            self._pending_event.set()

    def call(self, method: str, *args: Any, timeout: float = 10.0) -> Any:
        if not self._sock:
            raise RuntimeError("Not connected")

        with self._lock:
            self._pending_event.clear()

        request = {
            "jsonrpc": "2.0",
            "method": method,
            "params": list(args),
        }
        payload = json.dumps(request) + "\n"
        try:
            self._sock.sendall(payload.encode("utf-8"))
        except Exception as exc:
            raise RuntimeError(f"Send failed: {exc}")

        if not self._pending_event.wait(timeout=timeout):
            raise TimeoutError(f"JSON-RPC call to '{method}' timed out")

        with self._lock:
            response = self._last_response
            self._last_response = None

        if response and "error" in response:
            raise RuntimeError(f"JSON-RPC error: {response['error']['message']}")

        return response.get("result") if response else None


class KimixWebSocketClient:
    """WebSocket client for kimix server (bridges to JSON-RPC)."""

    def __init__(self, host: str = "127.0.0.1", ws_port: int = 8897):
        self.uri = f"ws://{host}:{ws_port}"
        self._ws: Optional[Any] = None
        self._lock = threading.Lock()
        self._pending_event = threading.Event()
        self._last_response: Any = None
        self._recv_thread: Optional[threading.Thread] = None
        self._stop_recv = threading.Event()

    def connect(self, timeout: float = 5.0) -> bool:
        try:
            import websockets.sync.client as ws_client
            self._ws = ws_client.connect(self.uri, open_timeout=timeout)
            self._stop_recv.clear()
            self._recv_thread = threading.Thread(target=self._recv_loop, daemon=True)
            self._recv_thread.start()
            return True
        except Exception as exc:
            logger.error("[KimixWSClient] Connect failed: %s", exc)
            self._ws = None
            return False

    def disconnect(self) -> None:
        self._stop_recv.set()
        if self._ws:
            try:
                self._ws.close()
            except Exception:
                pass
            self._ws = None
        if self._recv_thread:
            self._recv_thread.join(timeout=2.0)
            self._recv_thread = None

    def is_connected(self) -> bool:
        return self._ws is not None

    def _recv_loop(self) -> None:
        while not self._stop_recv.is_set() and self._ws:
            try:
                message = self._ws.recv(timeout=1.0)
                if message:
                    self._handle_message(message)
            except Exception:
                continue
        self._ws = None

    def _handle_message(self, message: str) -> None:
        try:
            response = json.loads(message)
        except json.JSONDecodeError:
            return
        with self._lock:
            self._last_response = response
            self._pending_event.set()

    def call(self, method: str, *args: Any, timeout: float = 10.0) -> Any:
        if not self._ws:
            raise RuntimeError("Not connected")

        with self._lock:
            self._pending_event.clear()

        request = {
            "jsonrpc": "2.0",
            "method": method,
            "params": list(args),
        }
        try:
            self._ws.send(json.dumps(request))
        except Exception as exc:
            raise RuntimeError(f"Send failed: {exc}")

        if not self._pending_event.wait(timeout=timeout):
            raise TimeoutError(f"JSON-RPC call to '{method}' timed out")

        with self._lock:
            response = self._last_response
            self._last_response = None

        if response and "error" in response:
            raise RuntimeError(f"JSON-RPC error: {response['error']['message']}")

        return response.get("result") if response else None


class KimixSessionClient:
    """High-level client that manages a kimix session."""

    def __init__(self, host: str = "127.0.0.1", port: int = 8896, ws_port: Optional[int] = None):
        self.host = host
        self.port = port
        self.ws_port = ws_port
        self._rpc: Optional[KimixJsonRpcClient] = None
        self._ws: Optional[KimixWebSocketClient] = None
        self._client_id: Optional[int] = None
        self._session_id: Optional[str] = None
        self._use_ws = ws_port is not None

    def connect(self) -> bool:
        if self._use_ws and self.ws_port:
            self._ws = KimixWebSocketClient(self.host, self.ws_port)
            if not self._ws.connect():
                return False
            self._client_id = 1
            return True
        else:
            self._rpc = KimixJsonRpcClient(self.host, self.port)
            if not self._rpc.connect():
                return False
            self._client_id = 1
            return True

    def disconnect(self) -> None:
        if self._session_id and self._client_id is not None:
            try:
                self.close_session()
            except Exception:
                pass
        if self._rpc:
            self._rpc.disconnect()
            self._rpc = None
        if self._ws:
            self._ws.disconnect()
            self._ws = None

    def open_session(self) -> str:
        client = self._ws or self._rpc
        if not client:
            raise RuntimeError("Not connected")
        result = client.call("open_session")
        if isinstance(result, str):
            self._session_id = result
            return result
        raise RuntimeError(f"Failed to open session: {result}")

    def close_session(self) -> str:
        client = self._ws or self._rpc
        if not client or not self._session_id:
            return "not connected"
        result = client.call("close_session", self._session_id)
        self._session_id = None
        return result

    def send_input(self, text: str) -> str:
        client = self._ws or self._rpc
        if not client or not self._session_id:
            raise RuntimeError("No active session")
        return client.call("input_from_client", self._session_id, text)

    def get_output(self) -> List[str]:
        client = self._ws or self._rpc
        if not client or not self._session_id:
            return []
        result = client.call("get_output_from_client", self._session_id)
        if isinstance(result, list):
            return result
        return []

    def is_finished(self) -> bool:
        client = self._ws or self._rpc
        if not client or not self._session_id:
            return True
        result = client.call("is_session_finished", self._session_id)
        return bool(result)

    def run_task(self, text: str, on_output: Optional[Callable[[str], None]] = None, poll_interval: float = 1.0) -> List[str]:
        """Send input and poll until finished. Returns all outputs."""
        self.send_input(text)
        all_outputs: List[str] = []
        while True:
            outputs = self.get_output()
            for line in outputs:
                all_outputs.append(line)
                if on_output:
                    on_output(line)
            if self.is_finished():
                break
            time.sleep(poll_interval)
        return all_outputs
