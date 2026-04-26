# -*- coding: utf-8 -*-
"""Server-side session manager: creates, tracks, and runs kimix sessions.

Instead of relying on the text-only output_function callback from prompt_async,
this module directly iterates sdk_session.prompt() wire messages to capture
tool calls, tool results, step boundaries, reasoning, and text content —
then emits proper opencode-style SSE events for each.
"""

from __future__ import annotations

import asyncio
import json
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
        """Send a prompt and wait for the full response.

        Directly iterates sdk_session.prompt() wire messages to capture:
        - TextPart / ThinkPart  → text / reasoning events
        - ToolCall              → tool event (status=running)
        - ToolResult            → tool event (status=completed/error)
        - StepBegin             → step-start event
        - StepInterrupted       → step-finish event (reason=tool-calls)
        """
        # Lazy imports of wire message types (avoids import at module level)
        from kimi_cli.wire.types import (
            ApprovalRequest,
            ContentPart,
            StepBegin,
            StepInterrupted,
            TextPart,
            ThinkPart,
            ToolCall,
            ToolCallPart,
            ToolResult,
        )

        entry = self._get_entry(session_id)
        sdk_session = entry.sdk_session
        if sdk_session is None:
            raise ValueError(f"Session {session_id} has no active SDK session")

        self._set_status(entry, "busy")
        entry._cancel_event = None  # will be set by sdk_session internally

        # ── Create user message ──────────────────────────────────
        user_msg_id = self._next_msg_id()
        now = time.time()
        user_msg = MessageWithParts(
            info=MessageInfo(
                id=user_msg_id, role="user", sessionID=session_id,
                agent=agent or "", createdAt=now,
            ),
            parts=[MessagePart(
                id=self._next_part_id(), type="text", text=text,
                sessionID=session_id, messageID=user_msg_id, createdAt=now,
            )],
        )
        entry.messages.append(user_msg)
        bus.emit_type("message.created", sessionID=session_id, info=user_msg.info.to_dict())

        # ── Create assistant message placeholder ─────────────────
        asst_msg_id = self._next_msg_id()
        asst_msg = MessageWithParts(
            info=MessageInfo(
                id=asst_msg_id, role="assistant", sessionID=session_id,
                agent=agent or "", createdAt=time.time(),
            ),
            parts=[],
        )
        entry.messages.append(asst_msg)

        # Helper: emit a part and append to the message
        def _emit_part(part: MessagePart, delta: str = "") -> None:
            asst_msg.parts.append(part)
            bus.emit_type(
                "message.part.updated",
                sessionID=session_id,
                messageID=asst_msg_id,
                part=part.to_dict(),
                delta=delta,
            )

        # ── Emit initial step-start ──────────────────────────────
        _emit_part(MessagePart(
            id=self._next_part_id(), type="step-start",
            sessionID=session_id, messageID=asst_msg_id,
            createdAt=time.time(),
        ))

        # Accumulate text for the current text part
        text_buf: list[str] = []
        text_part_id = self._next_part_id()

        # Track active tool calls:  tool_call_id → part_id
        active_tool_parts: Dict[str, str] = {}

        error_msg: Optional[str] = None
        step_finish_reason = "end_turn"

        try:
            async for wire_msg in sdk_session.prompt(text, merge_wire_messages=True):
                # ── ApprovalRequest: auto-approve in server mode ─
                if isinstance(wire_msg, ApprovalRequest):
                    logger.info(
                        "[SessionManager] Auto-approving: %s (%s)",
                        wire_msg.action, wire_msg.description,
                    )
                    wire_msg.resolve("approve")
                    continue

                # ── StepBegin: new step boundary ─────────────────
                if isinstance(wire_msg, StepBegin):
                    # Flush accumulated text
                    if text_buf:
                        full = "".join(text_buf)
                        _emit_part(MessagePart(
                            id=text_part_id, type="text", text=full,
                            sessionID=session_id, messageID=asst_msg_id,
                            createdAt=time.time(),
                        ), delta="")
                        text_buf.clear()
                        text_part_id = self._next_part_id()

                    # Emit step-finish for previous step (reason=tool-calls)
                    _emit_part(MessagePart(
                        id=self._next_part_id(), type="step-finish",
                        sessionID=session_id, messageID=asst_msg_id,
                        createdAt=time.time(),
                        state={"reason": "tool-calls"},
                    ))
                    # Emit step-start for new step
                    _emit_part(MessagePart(
                        id=self._next_part_id(), type="step-start",
                        sessionID=session_id, messageID=asst_msg_id,
                        createdAt=time.time(),
                    ))
                    continue

                # ── StepInterrupted ──────────────────────────────
                if isinstance(wire_msg, StepInterrupted):
                    step_finish_reason = "tool-calls"
                    continue

                # ── TextPart ─────────────────────────────────────
                if isinstance(wire_msg, TextPart):
                    chunk = wire_msg.text
                    text_buf.append(chunk)
                    full_so_far = "".join(text_buf)
                    _emit_part(MessagePart(
                        id=text_part_id, type="text", text=full_so_far,
                        sessionID=session_id, messageID=asst_msg_id,
                        createdAt=time.time(),
                    ), delta=chunk)
                    continue

                # ── ThinkPart (reasoning) ────────────────────────
                if isinstance(wire_msg, ThinkPart):
                    chunk = wire_msg.think
                    if chunk:
                        _emit_part(MessagePart(
                            id=self._next_part_id(), type="reasoning",
                            text=chunk,
                            sessionID=session_id, messageID=asst_msg_id,
                            createdAt=time.time(),
                        ), delta=chunk)
                    continue

                # ── ToolCall: tool invocation starts ─────────────
                if isinstance(wire_msg, ToolCall):
                    tool_name = wire_msg.function.name if wire_msg.function else "unknown"
                    tool_args = wire_msg.function.arguments if wire_msg.function else ""
                    tool_part_id = self._next_part_id()
                    active_tool_parts[wire_msg.id] = tool_part_id
                    _emit_part(MessagePart(
                        id=tool_part_id, type="tool",
                        tool=tool_name,
                        state={
                            "status": "running",
                            "title": tool_name,
                            "input": tool_args or "",
                            "toolCallId": wire_msg.id,
                        },
                        sessionID=session_id, messageID=asst_msg_id,
                        createdAt=time.time(),
                    ))
                    continue

                # ── ToolCallPart: incremental tool-call arguments ─
                if isinstance(wire_msg, ToolCallPart):
                    # Streaming argument chunk; we don't emit a separate event
                    # for this (the final ToolResult covers it).
                    continue

                # ── ToolResult: tool finished ────────────────────
                if isinstance(wire_msg, ToolResult):
                    tc_id = wire_msg.tool_call_id
                    tool_part_id = active_tool_parts.pop(tc_id, self._next_part_id())
                    rv = wire_msg.return_value
                    is_error = rv.is_error
                    # rv.output is str | list[ContentPart]
                    output = ""
                    if isinstance(rv.output, str):
                        output = rv.output
                    elif isinstance(rv.output, list):
                        # Concatenate text parts, skip non-text
                        parts_text = []
                        for cp in rv.output:
                            if isinstance(cp, TextPart):
                                parts_text.append(cp.text)
                            else:
                                parts_text.append(f"[{type(cp).__name__}]")
                        output = "".join(parts_text)
                    if not output and rv.message:
                        output = rv.message
                    # Use brief display if available
                    brief = rv.brief
                    status = "error" if is_error else "completed"
                    _emit_part(MessagePart(
                        id=tool_part_id, type="tool",
                        tool="",  # name not available in ToolResult
                        state={
                            "status": status,
                            "title": brief or "",
                            "output": output[:4000],
                            "error": rv.message if is_error else "",
                            "toolCallId": tc_id,
                        },
                        sessionID=session_id, messageID=asst_msg_id,
                        createdAt=time.time(),
                    ))
                    continue

                # ── Other ContentPart subtypes (images etc.) ─────
                if isinstance(wire_msg, ContentPart):
                    # Generic content part — serialize best-effort
                    try:
                        raw = wire_msg.model_dump()
                        part_type_str = raw.get("type", "unknown")
                        part_text = json.dumps(raw, ensure_ascii=False)
                        _emit_part(MessagePart(
                            id=self._next_part_id(), type="text",
                            text=f"[{part_type_str}] {part_text}",
                            sessionID=session_id, messageID=asst_msg_id,
                            createdAt=time.time(),
                        ), delta=part_text)
                    except Exception:
                        pass
                    continue

        except asyncio.CancelledError:
            error_msg = "cancelled"
        except Exception as exc:
            error_msg = str(exc)
            logger.error("[SessionManager] Prompt error: %s", exc, exc_info=True)

        # ── Flush remaining text ─────────────────────────────────
        if text_buf:
            final_text = "".join(text_buf)
            _emit_part(MessagePart(
                id=text_part_id, type="text", text=final_text,
                sessionID=session_id, messageID=asst_msg_id,
                createdAt=time.time(),
            ))

        # ── Emit final step-finish ───────────────────────────────
        reason = error_msg or step_finish_reason
        _emit_part(MessagePart(
            id=self._next_part_id(), type="step-finish",
            sessionID=session_id, messageID=asst_msg_id,
            createdAt=time.time(),
            state={"reason": reason},
        ))

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
