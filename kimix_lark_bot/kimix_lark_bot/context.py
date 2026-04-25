# -*- coding: utf-8 -*-
"""Conversation context and data models."""

from collections import deque
from dataclasses import dataclass, field
from typing import Optional, Dict, Any
from datetime import datetime

_HISTORY_WINDOW = 6

_CONFIRM_WORDS = {"是", "是的", "确认", "确定", "y", "yes", "ok", "好", "行", "可以", "没错", "对", "对的"}
_CANCEL_WORDS = {"否", "不是", "取消", "不", "n", "no", "算了", "别", "不要", "拒绝"}


@dataclass
class ActionPlan:
    action: str
    params: Dict[str, Any] = field(default_factory=dict)
    confirm_required: bool = False
    confirm_summary: str = ""
    reply: str = ""


@dataclass
class PendingConfirmation:
    action: str
    params: Dict[str, Any]
    summary: str
    expires_at: datetime

    def is_expired(self) -> bool:
        return datetime.now() > self.expires_at


@dataclass
class ConversationContext:
    chat_id: str
    history: deque = field(default_factory=lambda: deque(maxlen=_HISTORY_WINDOW))
    mode: str = "idle"
    active_workspace: Optional[str] = None
    pending: Optional[PendingConfirmation] = None
    active_session_id: Optional[str] = None

    def push(self, role: str, text: str) -> None:
        self.history.append({"role": role, "text": text, "ts": datetime.now()})

    def history_text(self) -> str:
        lines = []
        for t in self.history:
            prefix = "User" if t["role"] == "user" else "Bot"
            lines.append(f"{prefix}: {t['text']}")
        return "\n".join(lines)

    def is_pending_expired(self) -> bool:
        return self.pending is not None and self.pending.is_expired()

    def clear_pending(self) -> None:
        self.pending = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chat_id": self.chat_id,
            "mode": self.mode,
            "active_workspace": self.active_workspace,
            "active_session_id": self.active_session_id,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ConversationContext":
        ctx = cls(
            chat_id=data.get("chat_id", ""),
            mode=data.get("mode", "idle"),
            active_workspace=data.get("active_workspace"),
            active_session_id=data.get("active_session_id"),
        )
        return ctx
