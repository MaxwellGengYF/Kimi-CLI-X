# -*- coding: utf-8 -*-
"""Feishu messaging client."""

import json
import time
import threading
import logging
from typing import Optional, Dict, Any
import lark_oapi as lark
from lark_oapi.api.im.v1 import (
    CreateMessageRequest,
    CreateMessageRequestBody,
    PatchMessageRequest,
    PatchMessageRequestBody,
    ReplyMessageRequest,
    ReplyMessageRequestBody,
)

logger = logging.getLogger(__name__)


class _RateLimiter:
    def __init__(self, max_calls: int = 20, period: float = 1.0):
        self._max = max_calls
        self._period = period
        self._tokens = max_calls
        self._last_refill = time.time()
        self._lock = threading.Lock()

    def acquire(self) -> None:
        while True:
            with self._lock:
                now = time.time()
                elapsed = now - self._last_refill
                if elapsed >= self._period:
                    self._tokens = self._max
                    self._last_refill = now
                if self._tokens > 0:
                    self._tokens -= 1
                    return
            time.sleep(0.05)


_rate_limiter = _RateLimiter(max_calls=20, period=1.0)


def _card_to_content(card: dict) -> str:
    return json.dumps(card, ensure_ascii=False)


def _text_fallback(card: dict) -> str:
    header = card.get("header", {}).get("title", {}).get("content", "")
    elements = card.get("elements", [])
    texts = [header] if header else []
    for el in elements:
        if el.get("tag") == "div":
            text = el.get("text", {}).get("content", "")
            if text:
                texts.append(text)
    return "\n".join(texts) or "[卡片消息]"


class FeishuMessagingClient:
    def __init__(self, lark_client: Optional[lark.Client] = None, default_chat_id: Optional[str] = None):
        self.lark_client = lark_client
        self.default_chat_id = default_chat_id

    def set_client(self, lark_client: lark.Client) -> None:
        self.lark_client = lark_client

    def set_default_chat_id(self, chat_id: Optional[str]) -> None:
        self.default_chat_id = chat_id

    def send_text(self, chat_id: str, text: str) -> bool:
        if not self.lark_client:
            logger.warning("(no client) Would send to %s", chat_id)
            return False
        _rate_limiter.acquire()
        try:
            content = json.dumps({"text": text}, ensure_ascii=False)
            request = (
                CreateMessageRequest.builder()
                .receive_id_type("chat_id")
                .request_body(
                    CreateMessageRequestBody.builder()
                    .receive_id(chat_id)
                    .msg_type("text")
                    .content(content)
                    .build()
                )
                .build()
            )
            resp = self.lark_client.im.v1.message.create(request)
            if not resp.success():
                logger.error("Send failed: %s", resp.msg)
                return False
            return True
        except Exception as exc:
            logger.error("Send error: %s", exc, exc_info=True)
            return False

    def reply_text(self, message_id: str, text: str) -> bool:
        if not self.lark_client:
            logger.warning("(no client) Would reply to %s: %s", message_id, text[:80])
            return False
        _rate_limiter.acquire()
        try:
            content = json.dumps({"text": text}, ensure_ascii=False)
            request = (
                ReplyMessageRequest.builder()
                .message_id(message_id)
                .request_body(
                    ReplyMessageRequestBody.builder()
                    .content(content)
                        .msg_type("text")
                        .build()
                )
                .build()
            )
            resp = self.lark_client.im.v1.message.reply(request)
            if not resp.success():
                logger.error("Reply failed: %s", resp.msg)
                return False
            return True
        except Exception as exc:
            logger.error("Reply error: %s", exc, exc_info=True)
            return False

    def send_card(self, chat_id: str, card: dict) -> Optional[str]:
        if not self.lark_client:
            logger.warning("(no client) Would send card to %s", chat_id)
            return None
        _rate_limiter.acquire()
        try:
            content = _card_to_content(card)
            request = (
                CreateMessageRequest.builder()
                .receive_id_type("chat_id")
                .request_body(
                    CreateMessageRequestBody.builder()
                    .receive_id(chat_id)
                    .msg_type("interactive")
                    .content(content)
                    .build()
                )
                .build()
            )
            resp = self.lark_client.im.v1.message.create(request)
            if resp.success() and resp.data and resp.data.message_id:
                return resp.data.message_id
            else:
                logger.error("Card send failed: %s", resp.msg)
                self.send_text(chat_id, _text_fallback(card))
                return None
        except Exception as exc:
            logger.error("Card send error: %s", exc, exc_info=True)
            try:
                self.send_text(chat_id, _text_fallback(card))
            except Exception:
                pass
            return None

    def reply_card(self, message_id: str, card: dict) -> Optional[str]:
        if not self.lark_client:
            logger.warning("(no client) Would reply card to %s", message_id)
            return None
        _rate_limiter.acquire()
        try:
            content = _card_to_content(card)
            request = (
                ReplyMessageRequest.builder()
                .message_id(message_id)
                .request_body(
                    ReplyMessageRequestBody.builder()
                    .content(content)
                    .msg_type("interactive")
                    .build()
                )
                .build()
            )
            resp = self.lark_client.im.v1.message.reply(request)
            if resp.success() and resp.data and resp.data.message_id:
                return resp.data.message_id
            else:
                logger.error("Card reply failed: %s", resp.msg)
                self.reply_text(message_id, _text_fallback(card))
                return None
        except Exception as exc:
            logger.error("Card reply error: %s", exc, exc_info=True)
            try:
                self.reply_text(message_id, _text_fallback(card))
            except Exception:
                pass
            return None

    def update_card(self, message_id: str, card: dict) -> bool:
        if not self.lark_client:
            logger.warning("(no client) Would update card %s", message_id)
            return False
        _rate_limiter.acquire()
        try:
            content = _card_to_content(card)
            request = (
                PatchMessageRequest.builder()
                .message_id(message_id)
                .request_body(
                    PatchMessageRequestBody.builder().content(content).build()
                )
                .build()
            )
            resp = self.lark_client.im.v1.message.patch(request)
            if not resp.success():
                logger.error("Card update failed: %s", resp.msg)
                return False
            return True
        except Exception as exc:
            logger.error("Card update error: %s", exc, exc_info=True)
            return False
