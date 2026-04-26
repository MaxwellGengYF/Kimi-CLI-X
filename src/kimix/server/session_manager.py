# -*- coding: utf-8 -*-
"""Server-side session manager: creates, tracks, and runs kimix sessions."""

from __future__ import annotations

import asyncio
import logging
import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from kimi_agent_sdk import Session

from kimix.server.bus import bus, BusEvent
from kimix.utils import (
    _create_session_async,
    close_session_async,
    prompt_async as _prompt_async,
)

logger = logging.getLogger(__name__)

# ── Data Models ──────────────────────────────────────────────────


@dataclass
class MessagePart:
    """A part of a message (text, tool call, reasoning, etc.)."""
    id: str = ""
    type: str = "text"   # text | tool | reasoning | step-start | step-finish
    text: str = ""
    tool: str = ""
    state: Dict[str, Any] = field(default_factory=dict)
    sessionID: str = ""
    messageID: str = ""
    createdAt: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "id": self.id,
            "type": self.type,
            "sessionID": self.sessionID,
            "messageID": self.messageID,
            "createdAt": self.createdAt,
        }
        if self.type == "text":
            d["text"] = self.text
        elif self.type == "tool":
            d["tool"] = self.tool
            d["state"] = self.state
        elif self.type == "reasoning":
            d["text"] = self.text
        return d


@dataclass
class MessageInfo:
    """Message metadata."""
    id: str = ""
    role: str = "assistant"  # user | assistant | system
    sessionID: str = ""
    agent: str = ""
    createdAt: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "role": self.role,
            "sessionID": self.sessionID,
            "agent": self.agent,
            "createdAt": self.createdAt,
        }


@dataclass
class MessageWithParts:
    info: MessageInfo = field(default_factory=MessageInfo)
    parts: List[MessagePart] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "info": self.info.to_dict(),
            "parts": [p.to_dict() for p in self.parts],
        }


@dataclass
class SessionInfo:
    """Public session info exposed via API."""
    id: str = ""
    title: Optional[str] = None
    createdAt: float = 0.0
    updatedAt: float = 0.0
    parentID: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "createdAt": self.createdAt,
            "updatedAt": self.updatedAt,
            "parentID": self.parentID,
        }


# Session status
@dataclass
class SessionStatus:
    type: str = "idle"   # idle | busy | error
    time: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {"type": self.type, "time": self.time}


# ── Managed Session Entry ────────────────────────────────────────


@dataclass
class ManagedSession:
    """Internal session entry tracked by the manager."""
    info: SessionInfo
    sdk_session: Optional[Session] = None
    status: SessionStatus = field(default_factory=SessionStatus)
    messages: List[MessageWithParts] = field(default_factory=list)
    _cancel_event: Optional[asyncio.Event] = field(default=None, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)


# ── Session Manager ──────────────────────────────────────────────


class SessionManager:
    """Manages all sessions for the kimix serve process."""

    def __init__(self) -> None:
        self._sessions: Dict[str, ManagedSession] = {}
        self._lock = threading.Lock()
        self._part_counter = 0

    def _next_part_id(self) -> str:
        self._part_counter += 1
        return f"part_{self._part_counter:06d}"

    def _next_msg_id(self) -> str:
        return str(uuid.uuid4())

    # ── Session CRUD ─────────────────────────────────────────────

    async def create_session(self, title: Optional[str] = None) -> SessionInfo:
        session_id = str(uuid.uuid4())
        now = time.time()
        info = SessionInfo(
            id=session_id,
            title=title or f"Session {session_id[:8]}",
            createdAt=now,
            updatedAt=now,
        )
        sdk_session = await _create_session_async(session_id=session_id)
        entry = ManagedSession(info=info, sdk_session=sdk_session)
        with self._lock:
            self._sessions[session_id] = entry

        bus.emit_type("session.created", sessionID=session_id, info=info.to_dict())
        logger.info("[SessionManager] Created session %s", session_id)
        return info

    def get_session(self, session_id: str) -> SessionInfo:
        entry = self._get_entry(session_id)
        return entry.info

    def list_sessions(self) -> List[SessionInfo]:
        with self._lock:
            entries = list(self._sessions.values())
        return sorted(
            [e.info for e in entries],
            key=lambda s: s.updatedAt,
            reverse=True,
        )

    async def delete_session(self, session_id: str) -> bool:
        with self._lock:
            entry = self._sessions.pop(session_id, None)
        if entry is None:
            return False
        if entry.sdk_session:
            try:
                await close_session_async(entry.sdk_session)
            except Exception:
                logger.debug("Error closing sdk session", exc_info=True)
        bus.emit_type("session.deleted", sessionID=session_id)
        logger.info("[SessionManager] Deleted session %s", session_id)
        return True

    def get_session_status(self) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            return {
                sid: entry.status.to_dict()
                for sid, entry in self._sessions.items()
            }

    # ── Messages ─────────────────────────────────────────────────

    def get_messages(
        self, session_id: str, limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        entry = self._get_entry(session_id)
        msgs = entry.messages
        if limit and limit > 0:
            msgs = msgs[-limit:]
        return [m.to_dict() for m in msgs]

    # ── Prompt (sync wait) ───────────────────────────────────────

    async def prompt(
        self,
        session_id: str,
        text: str,
        agent: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send a prompt and wait for the full response."""
        entry = self._get_entry(session_id)
        sdk_session = entry.sdk_session
        if sdk_session is None:
            raise ValueError(f"Session {session_id} has no active SDK session")

        self._set_status(entry, "busy")
        cancel_event = asyncio.Event()
        entry._cancel_event = cancel_event

        # Create user message
        user_msg_id = self._next_msg_id()
        now = time.time()
        user_msg = MessageWithParts(
            info=MessageInfo(
                id=user_msg_id,
                role="user",
                sessionID=session_id,
                agent=agent or "",
                createdAt=now,
            ),
            parts=[MessagePart(
                id=self._next_part_id(),
                type="text",
                text=text,
                sessionID=session_id,
                messageID=user_msg_id,
                createdAt=now,
            )],
        )
        entry.messages.append(user_msg)
        bus.emit_type("message.created", sessionID=session_id, info=user_msg.info.to_dict())

        # Create assistant message placeholder
        asst_msg_id = self._next_msg_id()
        asst_msg = MessageWithParts(
            info=MessageInfo(
                id=asst_msg_id,
                role="assistant",
                sessionID=session_id,
                agent=agent or "",
                createdAt=time.time(),
            ),
            parts=[],
        )
        entry.messages.append(asst_msg)

        # Emit step-start
        step_start_part = MessagePart(
            id=self._next_part_id(),
            type="step-start",
            sessionID=session_id,
            messageID=asst_msg_id,
            createdAt=time.time(),
        )
        asst_msg.parts.append(step_start_part)
        bus.emit_type(
            "message.part.updated",
            sessionID=session_id,
            messageID=asst_msg_id,
            part=step_start_part.to_dict(),
            delta="",
        )

        collected_text: list[str] = []
        text_part_id = self._next_part_id()

        def _output_fn(chunk: str, is_think: bool) -> None:
            nonlocal collected_text
            part_type = "reasoning" if is_think else "text"
            if not is_think:
                collected_text.append(chunk)
            part = MessagePart(
                id=text_part_id,
                type=part_type,
                text="".join(collected_text) if not is_think else chunk,
                sessionID=session_id,
                messageID=asst_msg_id,
                createdAt=time.time(),
            )
            bus.emit_type(
                "message.part.updated",
                sessionID=session_id,
                messageID=asst_msg_id,
                part=part.to_dict(),
                delta=chunk,
            )

        error_msg: Optional[str] = None
        try:
            await _prompt_async(
                text,
                session=sdk_session,
                output_function=_output_fn,
                info_print=False,
            )
        except asyncio.CancelledError:
            error_msg = "cancelled"
        except Exception as exc:
            error_msg = str(exc)
            logger.error("[SessionManager] Prompt error: %s", exc, exc_info=True)

        # Finalize text part
        final_text = "".join(collected_text)
        final_part = MessagePart(
            id=text_part_id,
            type="text",
            text=final_text,
            sessionID=session_id,
            messageID=asst_msg_id,
            createdAt=time.time(),
        )
        asst_msg.parts.append(final_part)

        # Emit step-finish
        step_finish_part = MessagePart(
            id=self._next_part_id(),
            type="step-finish",
            sessionID=session_id,
            messageID=asst_msg_id,
            createdAt=time.time(),
        )
        step_finish_part.state = {"reason": error_msg or "end_turn"}
        asst_msg.parts.append(step_finish_part)
        bus.emit_type(
            "message.part.updated",
            sessionID=session_id,
            messageID=asst_msg_id,
            part=step_finish_part.to_dict(),
            delta="",
        )

        entry.info.updatedAt = time.time()
        entry._cancel_event = None
        self._set_status(entry, "idle")

        bus.emit_type(
            "message.updated",
            sessionID=session_id,
            info=asst_msg.info.to_dict(),
        )

        return asst_msg.to_dict()

    # ── Prompt Async (fire-and-forget) ───────────────────────────

    async def prompt_async(
        self,
        session_id: str,
        text: str,
        agent: Optional[str] = None,
    ) -> None:
        """Fire-and-forget: start prompt in background, events via SSE."""
        loop = asyncio.get_event_loop()

        async def _run() -> None:
            try:
                await self.prompt(session_id, text, agent)
            except Exception as exc:
                logger.error("[SessionManager] prompt_async error: %s", exc, exc_info=True)
                try:
                    entry = self._get_entry(session_id)
                    self._set_status(entry, "idle")
                except Exception:
                    pass

        asyncio.ensure_future(_run())

    # ── Abort ────────────────────────────────────────────────────

    def abort_session(self, session_id: str) -> bool:
        entry = self._get_entry(session_id)
        if entry._cancel_event:
            entry._cancel_event.set()
        if entry.sdk_session:
            try:
                entry.sdk_session.cancel()
            except Exception:
                pass
        self._set_status(entry, "idle")
        return True

    # ── Helpers ───────────────────────────────────────────────────

    def _get_entry(self, session_id: str) -> ManagedSession:
        with self._lock:
            entry = self._sessions.get(session_id)
        if entry is None:
            raise KeyError(f"Session not found: {session_id}")
        return entry

    def _set_status(self, entry: ManagedSession, status_type: str) -> None:
        entry.status = SessionStatus(type=status_type, time=time.time())
        bus.emit_type(
            "session.status",
            sessionID=entry.info.id,
            status=entry.status.to_dict(),
        )
        if status_type == "idle":
            bus.emit_type("session.idle", sessionID=entry.info.id)


# Global singleton
session_manager = SessionManager()
