# -*- coding: utf-8 -*-
"""Server-side session manager: creates, tracks, and runs kimix sessions.

Emits opencode-style SSE events that match the protocol specification:
- ID prefixes: ses_, msg_, prt_
- message.part.updated with proper part.type sub-fields
- Tool call lifecycle: pending → running → completed/error
- Reasoning and text use cumulative text + delta pattern
- step-finish carries reason, cost, tokens at part level
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from kimi_agent_sdk import Session

from kimix.server.bus import bus, BusEvent
from kimix.utils import (
    _create_session_async,
    close_session_async,
)

logger = logging.getLogger(__name__)

# ── ID Generators (opencode-style prefixed IDs) ────────────────────

_id_counter_lock = threading.Lock()
_id_counter = 0


def _gen_id(prefix: str) -> str:
    """Generate an opencode-style prefixed ID.

    Format: {prefix}_{hex_timestamp}{random_hex}
    Examples: ses_2325232b2ffe0XLh, msg_dcdae34e30014kj6, prt_dcdae47b2001AnTv
    """
    global _id_counter
    with _id_counter_lock:
        _id_counter += 1
        counter = _id_counter
    ts_hex = format(int(time.time() * 1000), "x")
    cnt_hex = format(counter, "04x")
    # Add some entropy from hash
    raw = f"{ts_hex}{cnt_hex}{os.getpid()}{time.monotonic_ns()}"
    h = hashlib.md5(raw.encode()).hexdigest()[:12]
    return f"{prefix}_{ts_hex}{h}"


def _gen_session_id() -> str:
    return _gen_id("ses")


def _gen_message_id() -> str:
    return _gen_id("msg")


def _gen_part_id() -> str:
    return _gen_id("prt")


def _snapshot_hash() -> str:
    """Generate a snapshot hash for step-start/step-finish."""
    raw = f"{time.time()}{time.monotonic_ns()}{os.getpid()}"
    return hashlib.md5(raw.encode()).hexdigest()[:16]


def _now_ms() -> int:
    """Current timestamp in milliseconds."""
    return int(time.time() * 1000)


# ── Data Models ──────────────────────────────────────────────────


@dataclass
class MessagePart:
    """A part of a message (text, tool call, reasoning, etc.)."""

    id: str = ""
    type: str = "text"  # text | tool | reasoning | step-start | step-finish
    sessionID: str = ""
    messageID: str = ""
    # text / reasoning fields
    text: str = ""
    # tool fields
    tool: str = ""
    callID: str = ""
    state: Dict[str, Any] = field(default_factory=dict)
    # step-start / step-finish fields
    snapshot: str = ""
    reason: str = ""
    cost: float = 0.0
    prompt: Dict[str, Any] = field(default_factory=dict)
    tokens: Dict[str, Any] = field(default_factory=dict)
    # time tracking
    time: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to opencode-compatible dict for SSE emission."""
        d: Dict[str, Any] = {
            "id": self.id,
            "sessionID": self.sessionID,
            "messageID": self.messageID,
            "type": self.type,
        }
        if self.type == "text":
            d["text"] = self.text
            if self.time:
                d["time"] = self.time
        elif self.type == "reasoning":
            d["text"] = self.text
            if self.time:
                d["time"] = self.time
        elif self.type == "tool":
            d["callID"] = self.callID
            d["tool"] = self.tool
            d["state"] = self.state
        elif self.type == "step-start":
            d["snapshot"] = self.snapshot
        elif self.type == "step-finish":
            d["reason"] = self.reason
            d["snapshot"] = self.snapshot
            if self.cost:
                d["cost"] = self.cost
            if self.prompt:
                d["prompt"] = self.prompt
            if self.tokens:
                d["tokens"] = self.tokens
        return d


@dataclass
class MessageInfo:
    """Message metadata."""

    id: str = ""
    role: str = "assistant"  # user | assistant | system
    sessionID: str = ""
    agent: str = ""
    modelID: str = ""
    providerID: str = ""
    mode: str = ""
    time: Dict[str, Any] = field(default_factory=dict)
    parentID: str = ""
    path: Dict[str, str] = field(default_factory=dict)
    cost: float = 0.0
    tokens: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "id": self.id,
            "sessionID": self.sessionID,
            "role": self.role,
        }
        if self.time:
            d["time"] = self.time
        if self.parentID:
            d["parentID"] = self.parentID
        if self.agent:
            d["agent"] = self.agent
        if self.modelID:
            d["modelID"] = self.modelID
        if self.providerID:
            d["providerID"] = self.providerID
        if self.mode:
            d["mode"] = self.mode
        if self.path:
            d["path"] = self.path
        if self.cost:
            d["cost"] = self.cost
        if self.tokens:
            d["tokens"] = self.tokens
        return d


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


@dataclass
class SessionStatus:
    type: str = "idle"  # idle | busy | error
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

    # ── Session CRUD ─────────────────────────────────────────────

    async def create_session(self, title: Optional[str] = None) -> SessionInfo:
        session_id = _gen_session_id()
        now = time.time()
        info = SessionInfo(
            id=session_id,
            title=title or f"Session {session_id[:12]}",
            createdAt=now,
            updatedAt=now,
        )
        sdk_session = await _create_session_async(session_id=session_id)
        entry = ManagedSession(info=info, sdk_session=sdk_session)
        with self._lock:
            self._sessions[session_id] = entry

        bus.emit_type(
            "session.created", sessionID=session_id, info=info.to_dict()
        )
        logger.info("[SessionManager] Created session %s", session_id)
        return info

    def get_session(self, session_id: str) -> SessionInfo:
        entry = self._get_entry(session_id)
        return entry.info

    def get_sdk_session(self, session_id: str) -> Optional[Session]:
        entry = self._get_entry(session_id)
        return entry.sdk_session

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

        Emits opencode-compatible SSE events:
        - step-start / step-finish with snapshot, reason, cost, tokens
        - reasoning with cumulative text + delta + time
        - text with cumulative text + delta + time
        - tool with pending → running → completed lifecycle + callID
        """
        # Lazy imports of wire message types
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
        entry._cancel_event = None

        # ── Create user message ──────────────────────────────────
        user_msg_id = _gen_message_id()
        now_ms = _now_ms()
        user_msg = MessageWithParts(
            info=MessageInfo(
                id=user_msg_id,
                role="user",
                sessionID=session_id,
                agent=agent or "",
                time={"created": now_ms},
            ),
            parts=[
                MessagePart(
                    id=_gen_part_id(),
                    type="text",
                    text=text,
                    sessionID=session_id,
                    messageID=user_msg_id,
                )
            ],
        )
        entry.messages.append(user_msg)
        bus.emit_type(
            "message.created",
            sessionID=session_id,
            info=user_msg.info.to_dict(),
        )

        # ── Create assistant message placeholder ─────────────────
        asst_msg_id = _gen_message_id()
        asst_msg = MessageWithParts(
            info=MessageInfo(
                id=asst_msg_id,
                role="assistant",
                sessionID=session_id,
                agent=agent or "",
                time={"created": _now_ms()},
            ),
            parts=[],
        )
        entry.messages.append(asst_msg)

        # ── Event emission helper ────────────────────────────────
        def _emit_part(part: MessagePart, delta: str = "") -> None:
            asst_msg.parts.append(part)
            props: Dict[str, Any] = {"part": part.to_dict()}
            if delta:
                props["delta"] = delta
            bus.emit(BusEvent(type="message.part.updated", properties=props))

        # ── Emit initial step-start ──────────────────────────────
        step_snapshot = _snapshot_hash()
        _emit_part(
            MessagePart(
                id=_gen_part_id(),
                type="step-start",
                sessionID=session_id,
                messageID=asst_msg_id,
                snapshot=step_snapshot,
            )
        )

        # ── Accumulation state ───────────────────────────────────
        # Text: cumulative buffer
        text_buf: List[str] = []
        text_part_id = _gen_part_id()
        text_time_start: Optional[int] = None

        # Reasoning: cumulative buffer
        reasoning_buf: List[str] = []
        reasoning_part_id = _gen_part_id()
        reasoning_time_start: Optional[int] = None

        # Tool tracking: wire_tool_call_id → (part_id, tool_name)
        active_tool_parts: Dict[str, tuple[str, str]] = {}

        # Metrics accumulation
        total_input_tokens = 0
        total_output_tokens = 0
        total_reasoning_tokens = 0
        total_cache_read = 0
        total_cache_write = 0
        total_cost = 0.0

        error_msg: Optional[str] = None
        step_finish_reason = "stop"

        def _flush_reasoning() -> None:
            """Flush accumulated reasoning with time.end."""
            nonlocal reasoning_buf, reasoning_part_id, reasoning_time_start
            if reasoning_buf and reasoning_time_start:
                full = "".join(reasoning_buf)
                _emit_part(
                    MessagePart(
                        id=reasoning_part_id,
                        type="reasoning",
                        text=full,
                        sessionID=session_id,
                        messageID=asst_msg_id,
                        time={"start": reasoning_time_start, "end": _now_ms()},
                    )
                )
            reasoning_buf = []
            reasoning_part_id = _gen_part_id()
            reasoning_time_start = None

        def _flush_text() -> None:
            """Flush accumulated text with time.end."""
            nonlocal text_buf, text_part_id, text_time_start
            if text_buf and text_time_start:
                full = "".join(text_buf)
                _emit_part(
                    MessagePart(
                        id=text_part_id,
                        type="text",
                        text=full,
                        sessionID=session_id,
                        messageID=asst_msg_id,
                        time={"start": text_time_start, "end": _now_ms()},
                    )
                )
            text_buf = []
            text_part_id = _gen_part_id()
            text_time_start = None

        def _emit_step_finish(reason: str) -> None:
            """Emit a step-finish event."""
            nonlocal step_snapshot
            _emit_part(
                MessagePart(
                    id=_gen_part_id(),
                    type="step-finish",
                    sessionID=session_id,
                    messageID=asst_msg_id,
                    reason=reason,
                    snapshot=step_snapshot,
                    cost=total_cost,
                    prompt={"total": total_input_tokens + total_output_tokens},
                    tokens={
                        "input": total_input_tokens,
                        "output": total_output_tokens,
                        "reasoning": total_reasoning_tokens,
                        "cache": {
                            "read": total_cache_read,
                            "write": total_cache_write,
                        },
                    },
                )
            )

        try:
            async for wire_msg in sdk_session.prompt(text, merge_wire_messages=True):
                # ── ApprovalRequest: auto-approve in server mode ─
                if isinstance(wire_msg, ApprovalRequest):
                    logger.info(
                        "[SessionManager] Auto-approving: %s (%s)",
                        wire_msg.action,
                        wire_msg.description,
                    )
                    wire_msg.resolve("approve")
                    continue

                # ── StepBegin: new step boundary ─────────────────
                if isinstance(wire_msg, StepBegin):
                    _flush_reasoning()
                    _flush_text()
                    _emit_step_finish("tool-calls")

                    # Inter-step events
                    asst_msg.info.time["completed"] = _now_ms()
                    bus.emit_type(
                        "message.updated",
                        sessionID=session_id,
                        info=asst_msg.info.to_dict(),
                    )
                    bus.emit_type(
                        "session.status",
                        sessionID=session_id,
                        status={"type": "busy", "time": time.time()},
                    )

                    # New step
                    step_snapshot = _snapshot_hash()
                    _emit_part(
                        MessagePart(
                            id=_gen_part_id(),
                            type="step-start",
                            sessionID=session_id,
                            messageID=asst_msg_id,
                            snapshot=step_snapshot,
                        )
                    )
                    step_finish_reason = "stop"
                    continue

                # ── StepInterrupted ──────────────────────────────
                if isinstance(wire_msg, StepInterrupted):
                    step_finish_reason = "tool-calls"
                    continue

                # ── ThinkPart (reasoning) — cumulative ───────────
                if isinstance(wire_msg, ThinkPart):
                    chunk = wire_msg.think
                    if chunk:
                        if reasoning_time_start is None:
                            reasoning_time_start = _now_ms()
                        reasoning_buf.append(chunk)
                        full_so_far = "".join(reasoning_buf)
                        _emit_part(
                            MessagePart(
                                id=reasoning_part_id,
                                type="reasoning",
                                text=full_so_far,
                                sessionID=session_id,
                                messageID=asst_msg_id,
                                time={"start": reasoning_time_start},
                            ),
                            delta=chunk,
                        )
                    continue

                # ── TextPart — cumulative ────────────────────────
                if isinstance(wire_msg, TextPart):
                    chunk = wire_msg.text
                    if chunk:
                        # Flush reasoning first if we're switching to text
                        if reasoning_buf:
                            _flush_reasoning()

                        if text_time_start is None:
                            text_time_start = _now_ms()
                        text_buf.append(chunk)
                        full_so_far = "".join(text_buf)
                        _emit_part(
                            MessagePart(
                                id=text_part_id,
                                type="text",
                                text=full_so_far,
                                sessionID=session_id,
                                messageID=asst_msg_id,
                                time={"start": text_time_start},
                            ),
                            delta=chunk,
                        )
                    continue

                # ── ToolCall: pending → running ──────────────────
                if isinstance(wire_msg, ToolCall):
                    # Flush reasoning before tool calls
                    if reasoning_buf:
                        _flush_reasoning()

                    tool_name = (
                        wire_msg.function.name if wire_msg.function else "unknown"
                    )
                    tool_args_raw = (
                        wire_msg.function.arguments if wire_msg.function else ""
                    )
                    wire_tc_id = wire_msg.id or _gen_id("toolu")
                    tool_part_id = _gen_part_id()
                    active_tool_parts[wire_tc_id] = (tool_part_id, tool_name)

                    # Phase 1: pending
                    _emit_part(
                        MessagePart(
                            id=tool_part_id,
                            type="tool",
                            tool=tool_name,
                            callID=wire_tc_id,
                            sessionID=session_id,
                            messageID=asst_msg_id,
                            state={
                                "status": "pending",
                                "input": {},
                                "raw": "",
                            },
                        )
                    )

                    # Phase 2: running (parse input args)
                    parsed_input: Any = {}
                    if tool_args_raw:
                        try:
                            parsed_input = json.loads(tool_args_raw)
                        except (json.JSONDecodeError, TypeError):
                            parsed_input = {"raw": str(tool_args_raw)}

                    _emit_part(
                        MessagePart(
                            id=tool_part_id,
                            type="tool",
                            tool=tool_name,
                            callID=wire_tc_id,
                            sessionID=session_id,
                            messageID=asst_msg_id,
                            state={
                                "status": "running",
                                "input": parsed_input,
                                "time": {"start": _now_ms()},
                            },
                        )
                    )
                    continue

                # ── ToolCallPart: streaming argument chunks ──────
                if isinstance(wire_msg, ToolCallPart):
                    # Incremental argument chunk — we already emitted running
                    continue

                # ── ToolResult: completed / error ────────────────
                if isinstance(wire_msg, ToolResult):
                    tc_id = wire_msg.tool_call_id
                    tool_part_id, tool_name = active_tool_parts.pop(
                        tc_id, (_gen_part_id(), "")
                    )
                    rv = wire_msg.return_value
                    is_error = rv.is_error

                    # Extract output text
                    output = ""
                    if isinstance(rv.output, str):
                        output = rv.output
                    elif isinstance(rv.output, list):
                        parts_text = []
                        for cp in rv.output:
                            if isinstance(cp, TextPart):
                                parts_text.append(cp.text)
                            else:
                                parts_text.append(f"[{type(cp).__name__}]")
                        output = "".join(parts_text)
                    if not output and rv.message:
                        output = rv.message

                    status = "error" if is_error else "completed"
                    state: Dict[str, Any] = {
                        "status": status,
                        "input": {},  # input was already sent in running phase
                    }
                    if is_error:
                        state["error"] = rv.message or output[:4000]
                    else:
                        state["output"] = output[:4000]

                    _emit_part(
                        MessagePart(
                            id=tool_part_id,
                            type="tool",
                            tool=tool_name,
                            callID=tc_id,
                            sessionID=session_id,
                            messageID=asst_msg_id,
                            state=state,
                        )
                    )
                    continue

                # ── Other ContentPart subtypes (images etc.) ─────
                if isinstance(wire_msg, ContentPart):
                    try:
                        raw = wire_msg.model_dump()
                        part_type_str = raw.get("type", "unknown")
                        part_text = json.dumps(raw, ensure_ascii=False)
                        if text_time_start is None:
                            text_time_start = _now_ms()
                        text_buf.append(f"[{part_type_str}] {part_text}")
                        full_so_far = "".join(text_buf)
                        _emit_part(
                            MessagePart(
                                id=text_part_id,
                                type="text",
                                text=full_so_far,
                                sessionID=session_id,
                                messageID=asst_msg_id,
                                time={"start": text_time_start},
                            ),
                            delta=part_text,
                        )
                    except Exception:
                        pass
                    continue

        except asyncio.CancelledError:
            error_msg = "cancelled"
        except Exception as exc:
            error_msg = str(exc)
            logger.error(
                "[SessionManager] Prompt error: %s", exc, exc_info=True
            )

        # ── Flush remaining buffers ──────────────────────────────
        _flush_reasoning()
        _flush_text()

        # ── Emit final step-finish ───────────────────────────────
        reason = step_finish_reason
        if error_msg:
            reason = error_msg
        _emit_step_finish(reason)

        # ── Finalize ─────────────────────────────────────────────
        asst_msg.info.time["completed"] = _now_ms()
        entry.info.updatedAt = time.time()
        entry._cancel_event = None

        bus.emit_type(
            "message.updated",
            sessionID=session_id,
            info=asst_msg.info.to_dict(),
        )

        self._set_status(entry, "idle")

        return asst_msg.to_dict()

    # ── Prompt Async (fire-and-forget) ───────────────────────────

    async def prompt_async(
        self,
        session_id: str,
        text: str,
        agent: Optional[str] = None,
    ) -> None:
        """Fire-and-forget: start prompt in background, events via SSE."""

        async def _run() -> None:
            try:
                await self.prompt(session_id, text, agent)
            except Exception as exc:
                logger.error(
                    "[SessionManager] prompt_async error: %s",
                    exc,
                    exc_info=True,
                )
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


# Global singleton
session_manager = SessionManager()
