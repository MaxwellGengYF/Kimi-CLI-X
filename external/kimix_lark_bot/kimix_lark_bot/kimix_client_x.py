# -*- coding: utf-8 -*-
"""Kimix opencode-style HTTP / SSE async client.

Replaces the old KimixJsonRpcClient / KimixWebSocketClient / KimixSessionClient
with an HTTP REST + SSE client that talks to `kimix serve`.

API surface mirrors sail.opencode.client for consistency.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncIterator, Callable, Dict, Iterator, List, Optional

import httpx

logger = logging.getLogger(__name__)


# ── Data Models ───────────────────────────────────────────────────


class MessagePartType(str, Enum):
    TEXT = "text"
    TOOL = "tool"
    REASONING = "reasoning"
    STEP_START = "step-start"
    STEP_FINISH = "step-finish"
    UNKNOWN = "unknown"


@dataclass
class MessagePart:
    type: MessagePartType
    text: Optional[str] = None
    tool_name: Optional[str] = None
    tool_status: Optional[str] = None
    tool_state: Optional[Dict[str, Any]] = None
    reason: Optional[str] = None
    cost: Optional[float] = None
    tokens: Optional[Dict[str, Any]] = None
    raw_data: Optional[Dict[str, Any]] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MessagePart":
        part_type = data.get("type", "text")
        try:
            msg_type = MessagePartType(part_type)
        except ValueError:
            return cls(type=MessagePartType.UNKNOWN, raw_data=data)

        part = cls(type=msg_type)
        if msg_type == MessagePartType.TEXT:
            part.text = data.get("text")
        elif msg_type == MessagePartType.TOOL:
            part.tool_name = data.get("tool")
            state = data.get("state", {})
            part.tool_status = state.get("status")
            part.tool_state = state
        elif msg_type == MessagePartType.REASONING:
            part.text = data.get("text")
        elif msg_type == MessagePartType.STEP_FINISH:
            state = data.get("state", {})
            part.reason = state.get("reason")
            part.cost = data.get("cost")
            part.tokens = data.get("tokens")
        elif msg_type == MessagePartType.UNKNOWN:
            part.raw_data = data
        return part


@dataclass
class Message:
    id: str
    role: str
    parts: List[MessagePart] = field(default_factory=list)
    created_at: Optional[float] = None

    @property
    def text_content(self) -> str:
        return "".join(
            p.text for p in self.parts
            if p.type == MessagePartType.TEXT and p.text
        )

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Message":
        info = data.get("info", {})
        return cls(
            id=info.get("id", ""),
            role=info.get("role", "assistant"),
            parts=[MessagePart.from_dict(p) for p in data.get("parts", [])],
            created_at=info.get("createdAt"),
        )


@dataclass
class Session:
    id: str
    title: Optional[str] = None
    created_at: Optional[float] = None
    updated_at: Optional[float] = None
    parent_id: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Session":
        return cls(
            id=data.get("id", ""),
            title=data.get("title"),
            created_at=data.get("createdAt"),
            updated_at=data.get("updatedAt"),
            parent_id=data.get("parentID"),
        )


@dataclass
class SSEEvent:
    """Parsed Server-Sent Event."""
    event: str = ""
    data: str = ""
    id: Optional[str] = None

    def json(self) -> Any:
        if not self.data:
            return None
        try:
            return json.loads(self.data)
        except json.JSONDecodeError:
            return None

    @property
    def is_reconnect(self) -> bool:
        return self.event == "__reconnected__"


# ── Event Type / Parsed Event ─────────────────────────────────────


class EventType(str, Enum):
    TEXT = "text"
    TEXT_DELTA = "text_delta"
    REASONING = "reasoning"
    TOOL = "tool"
    PERMISSION = "permission"
    STEP_START = "step-start"
    STEP_FINISH = "step-finish"
    SESSION_IDLE = "session_idle"
    RECONNECTED = "reconnected"
    SKIP = "skip"
    UNKNOWN = "unknown"


@dataclass
class ParsedEvent:
    type: EventType = EventType.UNKNOWN
    text: str = ""
    delta: str = ""
    tool_name: str = ""
    tool_status: str = ""
    tool_title: str = ""
    permission_id: str = ""
    finished: bool = False
    cost: float = 0.0
    tokens: Dict[str, Any] = field(default_factory=dict)
    raw: Dict[str, Any] = field(default_factory=dict)

    def is_terminal(self) -> bool:
        if self.type == EventType.SESSION_IDLE:
            return True
        if self.type == EventType.STEP_FINISH:
            return self.text not in ("tool-calls", "tool_calls")
        return False


# ── SSE Event Parser ─────────────────────────────────────────────


def parse_event(event: SSEEvent, session_id: str = "") -> ParsedEvent:
    """Parse a raw SSE event into a structured ParsedEvent.

    Compatible with both opencode native format and kimix format.
    """
    if event.event == "__reconnected__":
        return ParsedEvent(
            type=EventType.RECONNECTED,
            text=f"SSE reconnected (attempt {event.data})",
        )

    data = event.json()
    if not data:
        return ParsedEvent(type=EventType.SKIP)

    event_type: str = data.get("type", "")

    if event_type in ("server.connected", "server.heartbeat"):
        return ParsedEvent(type=EventType.SKIP)

    # Session filtering
    if session_id and not _matches_session(data, session_id):
        return ParsedEvent(type=EventType.SKIP)

    if event_type == "message.part.updated":
        return _parse_part_updated(data)

    if event_type in ("message.updated", "message.created", "session.updated", "session.created"):
        return ParsedEvent(type=EventType.SKIP)

    if event_type == "message.part.delta":
        return _parse_part_delta(data)

    if event_type in ("session.idle", "session.status"):
        return _parse_session_status(data, event_type)

    return ParsedEvent(type=EventType.UNKNOWN, raw=data)


def _parse_part_updated(data: Dict[str, Any]) -> ParsedEvent:
    props = data.get("properties", {})
    part = props.get("part", {})
    delta = props.get("delta", "")
    part_type = part.get("type", "")

    if part_type == "text":
        return ParsedEvent(
            type=EventType.TEXT,
            delta=delta,
            text=part.get("text", ""),
            raw=data,
        )
    if part_type == "tool":
        state = part.get("state", {})
        tool_name = part.get("tool", "unknown")
        status = state.get("status", "")
        title = state.get("title", tool_name)
        return ParsedEvent(
            type=EventType.TOOL,
            tool_name=tool_name,
            tool_status=status,
            tool_title=title,
            raw=data,
        )
    if part_type == "reasoning":
        return ParsedEvent(
            type=EventType.REASONING,
            text=part.get("text", ""),
            delta=delta,
            raw=data,
        )
    if part_type == "step-start":
        return ParsedEvent(type=EventType.STEP_START, raw=data)
    if part_type == "step-finish":
        state = part.get("state", {})
        reason = state.get("reason", "")
        finished = reason not in ("tool-calls", "tool_calls")
        return ParsedEvent(
            type=EventType.STEP_FINISH,
            text=reason,
            finished=finished,
            raw=data,
        )
    return ParsedEvent(type=EventType.SKIP)


def _parse_part_delta(data: Dict[str, Any]) -> ParsedEvent:
    props = data.get("properties", {})
    delta = props.get("delta", "")
    field_name = props.get("field", "")
    if delta and field_name in ("text", "reasoning"):
        return ParsedEvent(
            type=EventType.TEXT_DELTA,
            delta=delta,
            text=delta,
            raw=data,
        )
    return ParsedEvent(type=EventType.SKIP)


def _parse_session_status(data: Dict[str, Any], event_type: str) -> ParsedEvent:
    if event_type == "session.status":
        props = data.get("properties", {})
        status = props.get("status", {})
        status_type = status.get("type", "") if isinstance(status, dict) else ""
        if status_type != "idle":
            return ParsedEvent(type=EventType.SKIP)
    return ParsedEvent(type=EventType.SESSION_IDLE, finished=True, raw=data)


def _matches_session(data: Dict[str, Any], session_id: str) -> bool:
    props = data.get("properties", {})
    sid: Optional[str] = (
        props.get("sessionID")
        or props.get("session_id")
        or data.get("sessionID")
    )
    if not sid:
        info = props.get("info", {}) if props else {}
        sid = info.get("sessionID")
    return not sid or sid == session_id


# ── Sync Helpers ──────────────────────────────────────────────────


def check_health_sync(
    port: int,
    host: str = "127.0.0.1",
    timeout: float = 3.0,
) -> bool:
    """Synchronous health check for process management contexts."""
    try:
        with httpx.Client(timeout=httpx.Timeout(timeout)) as c:
            resp = c.get(f"http://{host}:{port}/global/health")
            return bool(resp.json().get("healthy", False))
    except Exception:
        return False


def abort_session_sync(
    session_id: str,
    port: int,
    host: str = "127.0.0.1",
    timeout: float = 10.0,
) -> bool:
    """Synchronous session abort."""
    try:
        with httpx.Client(timeout=httpx.Timeout(timeout)) as c:
            resp = c.post(f"http://{host}:{port}/session/{session_id}/abort")
            return resp.status_code == 200
    except Exception:
        return False


# ── Async Client ──────────────────────────────────────────────────


class KimixAsyncClient:
    """Async HTTP + SSE client for kimix serve (opencode-style API).

    Drop-in replacement for the old KimixSessionClient.

    Example::

        async with KimixAsyncClient(port=4096) as client:
            sess = await client.create_session("My Task")
            ok = await client.send_prompt_async(sess.id, "write tests")
            async for event in client.stream_events_robust(sess.id):
                parsed = parse_event(event, sess.id)
                if parsed.type == EventType.TEXT:
                    print(parsed.delta, end="", flush=True)
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 4096,
        timeout: float = 30.0,
    ) -> None:
        self.host = host
        self.port = port
        self._base_url = f"http://{host}:{port}"
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(timeout))

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "KimixAsyncClient":
        return self

    async def __aexit__(self, *args: Any) -> bool:
        await self.close()
        return False

    # ── Health ────────────────────────────────────────────────

    async def health_check(self) -> bool:
        try:
            resp = await self._client.get(f"{self._base_url}/global/health")
            data = resp.json()
            return bool(data.get("healthy", False))
        except Exception as exc:
            logger.warning("[KimixClient] health_check: %s: %s", type(exc).__name__, exc)
            return False

    # ── Session CRUD ─────────────────────────────────────────

    async def create_session(self, title: Optional[str] = None) -> Session:
        body = {"title": title} if title else {}
        resp = await self._client.post(f"{self._base_url}/session", json=body)
        resp.raise_for_status()
        return Session.from_dict(resp.json())

    async def get_session(self, session_id: str) -> Session:
        resp = await self._client.get(f"{self._base_url}/session/{session_id}")
        resp.raise_for_status()
        return Session.from_dict(resp.json())

    async def delete_session(self, session_id: str) -> bool:
        resp = await self._client.delete(f"{self._base_url}/session/{session_id}")
        return resp.status_code == 200

    async def list_sessions(self) -> List[Session]:
        resp = await self._client.get(f"{self._base_url}/session")
        resp.raise_for_status()
        return [Session.from_dict(s) for s in resp.json()]

    async def get_messages(self, session_id: str, limit: int = 10) -> List[Message]:
        resp = await self._client.get(
            f"{self._base_url}/session/{session_id}/message",
            params={"limit": limit},
        )
        resp.raise_for_status()
        return [Message.from_dict(m) for m in resp.json()]

    async def get_session_status(self) -> Dict[str, Any]:
        resp = await self._client.get(f"{self._base_url}/session/status")
        resp.raise_for_status()
        return resp.json()

    # ── Messaging ────────────────────────────────────────────

    async def send_prompt_async(
        self,
        session_id: str,
        text: str,
        agent: Optional[str] = None,
    ) -> bool:
        """Fire-and-forget prompt (HTTP 204)."""
        body: Dict[str, Any] = {"parts": [{"type": "text", "text": text}]}
        if agent:
            body["agent"] = agent
        resp = await self._client.post(
            f"{self._base_url}/session/{session_id}/prompt_async", json=body
        )
        return resp.status_code == 204

    async def send_message(
        self,
        session_id: str,
        text: str,
        agent: Optional[str] = None,
        timeout: float = 600.0,
    ) -> Message:
        """Send message and wait for the response (blocking)."""
        body: Dict[str, Any] = {"parts": [{"type": "text", "text": text}]}
        if agent:
            body["agent"] = agent
        resp = await self._client.post(
            f"{self._base_url}/session/{session_id}/message",
            json=body,
            timeout=httpx.Timeout(timeout, read=timeout),
        )
        resp.raise_for_status()
        return Message.from_dict(resp.json())

    async def abort_session(self, session_id: str) -> bool:
        resp = await self._client.post(
            f"{self._base_url}/session/{session_id}/abort"
        )
        return resp.status_code == 200

    # ── SSE Streaming ────────────────────────────────────────

    async def stream_events(
        self,
        session_id: str,
        timeout: float = 14400.0,
    ) -> AsyncIterator[SSEEvent]:
        """Stream SSE events from /event endpoint."""
        url = f"{self._base_url}/event"
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(timeout, connect=10.0, read=timeout)
        ) as stream_client:
            async with stream_client.stream("GET", url) as response:
                response.raise_for_status()
                async for event in _parse_sse_stream(response):
                    yield event

    async def stream_events_robust(
        self,
        session_id: str,
        timeout: float = 14400.0,
        max_reconnects: int = 5,
        reconnect_delay: float = 2.0,
        on_reconnect: Optional[Callable[[int], None]] = None,
    ) -> AsyncIterator[SSEEvent]:
        """SSE stream with auto-reconnect."""
        reconnects = 0
        while reconnects <= max_reconnects:
            try:
                async for event in self.stream_events(session_id, timeout):
                    reconnects = 0
                    yield event
                return
            except (
                httpx.ReadError,
                httpx.RemoteProtocolError,
                httpx.ConnectError,
                httpx.ReadTimeout,
            ) as exc:
                reconnects += 1
                if reconnects > max_reconnects:
                    logger.error("[SSE] Max reconnects reached: %s", exc)
                    raise
                logger.warning("[SSE] Reconnecting (%d/%d): %s", reconnects, max_reconnects, exc)
                if on_reconnect:
                    on_reconnect(reconnects)
                await asyncio.sleep(reconnect_delay * reconnects)
                yield SSEEvent(event="__reconnected__", data=str(reconnects))


# ── SSE Stream Parser (internal) ──────────────────────────────────

async def _parse_sse_stream(
    response: httpx.Response,
) -> AsyncIterator[SSEEvent]:
    """Parse HTTP response body into SSEEvent stream."""
    current = SSEEvent()
    data_lines: List[str] = []

    async for raw_line in response.aiter_lines():
        line = raw_line.rstrip("\r\n")

        if not line:
            if data_lines or current.event:
                current.data = "\n".join(data_lines)
                yield current
                current = SSEEvent()
                data_lines = []
            continue

        if line.startswith(":"):
            continue  # SSE comment / heartbeat

        if ":" in line:
            field_name, _, value = line.partition(":")
            value = value.lstrip(" ")
        else:
            field_name = line
            value = ""

        if field_name == "event":
            current.event = value
        elif field_name == "data":
            data_lines.append(value)
        elif field_name == "id":
            current.id = value

    if data_lines or current.event:
        current.data = "\n".join(data_lines)
        yield current
