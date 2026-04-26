# -*- coding: utf-8 -*-
"""Kimix Lark Bot Agent - Main entry point."""

from pathlib import Path
from typing import Optional, Dict, Any
import json
import threading
import traceback
import logging
from datetime import datetime

import lark_oapi as lark

from kimix_lark_bot.config import AgentConfig
from kimix_lark_bot.context import ConversationContext
from kimix_lark_bot.brain import BotBrain
from kimix_lark_bot.process_manager import KimixProcessManager
from kimix_lark_bot.messaging import FeishuMessagingClient
from kimix_lark_bot.handlers import HandlerContext, MessageHandler

logger = logging.getLogger(__name__)

_CONTEXTS_FILE = Path("data/kimix_bot/state/contexts.json")


class FeishuBotAgent:
    CONTEXT_STATE_FILE = _CONTEXTS_FILE

    def __init__(self, config: AgentConfig):
        self.config = config

        # Process management
        self.process_mgr = KimixProcessManager(
            base_port=config.base_port,
            projects=config.projects,
        )

        # Messaging client
        self.messaging = FeishuMessagingClient(default_chat_id=config.default_chat_id)
        self.lark_client: Optional[lark.Client] = None

        # AI brain
        self.brain = BotBrain(config.projects)

        # Conversation contexts
        self._contexts: Dict[str, ConversationContext] = {}
        self._load_contexts()

        # Create handler context
        self._handler_ctx = HandlerContext(
            messaging=self.messaging,
            process_mgr=self.process_mgr,
            brain=self.brain,
            config=self.config,
            agent=self,
        )

        # Initialize handlers
        self._message_handler = MessageHandler(self._handler_ctx)

        logger.info("FeishuBotAgent initialized")

    def _get_context(self, chat_id: str) -> ConversationContext:
        if chat_id not in self._contexts:
            self._contexts[chat_id] = ConversationContext(chat_id=chat_id)
        ctx = self._contexts[chat_id]
        if ctx.is_pending_expired():
            ctx.clear_pending()
        return ctx

    def _load_contexts(self) -> None:
        if not self.CONTEXT_STATE_FILE.exists():
            return
        try:
            with open(self.CONTEXT_STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)

            reset_count = 0
            for item in data:
                chat_id = item.get("chat_id", "")
                if not chat_id:
                    continue
                ctx = ConversationContext.from_dict(item)

                # Validate active_workspace against running processes
                if ctx.active_workspace:
                    procs = {p.path: p for p in self.process_mgr.list_processes()}
                    proc = procs.get(ctx.active_workspace)
                    if not proc or not proc.is_alive:
                        logger.warning("Resetting context for %s: workspace not running", chat_id)
                        ctx.mode = "idle"
                        ctx.active_workspace = None
                        ctx.active_session_id = None
                        reset_count += 1

                self._contexts[chat_id] = ctx

            if self._contexts:
                logger.info("Loaded %s conversation(s)", len(self._contexts))
            if reset_count > 0:
                logger.warning("Reset %s context(s) due to missing connection", reset_count)
        except Exception as exc:
            logger.error("Failed to load contexts: %s", exc, exc_info=True)

    def _save_contexts(self) -> None:
        try:
            self.CONTEXT_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            data = [
                ctx.to_dict()
                for chat_id, ctx in self._contexts.items()
                if ctx.active_workspace or ctx.mode != "idle"
            ]
            with open(self.CONTEXT_STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as exc:
            logger.error("Failed to save contexts: %s", exc, exc_info=True)

    def _handle_message(self, data: lark.im.v1.P2ImMessageReceiveV1) -> None:
        try:
            if not data or not data.event or not data.event.message:
                logger.debug("_handle_message: empty data or message")
                return
            message = data.event.message
            logger.debug("_handle_message: type=%s chat_id=%s msg_id=%s", message.message_type, message.chat_id, message.message_id)
            if message.message_type != "text":
                logger.debug("_handle_message: ignoring non-text message")
                return
            self._message_handler.handle(data)
        except Exception as exc:
            logger.error("Message handling error: %s", exc, exc_info=True)
            traceback.print_exc()

    def _handle_p2p_chat_entered(self, data: lark.im.v1.P2ImChatAccessEventBotP2pChatEnteredV1) -> None:
        try:
            if not data or not data.event:
                return
            chat_id = data.event.chat_id
            if chat_id:
                logger.info("User entered P2P chat: %s", chat_id)
                self.messaging.send_text(chat_id, "你好！我是 Kimix Bot。发送「帮助」查看可用指令。")
        except Exception as exc:
            logger.error("P2P chat entered error: %s", exc, exc_info=True)

    def run(self) -> int:
        print("Kimix Lark Bot v1.0")
        logger.info("Config: %s", self.config.config_path)

        if not self.config.app_id or not self.config.app_secret:
            logger.error("Feishu credentials not configured")
            return 1

        logger.info("App ID: %s...", self.config.app_id[:10])
        if self.config.projects:
            slugs = [p.get("slug", "") for p in self.config.projects]
            logger.info("Projects: %s", ", ".join(slugs))
        else:
            logger.info("No projects configured")

        # Initialize Lark client
        self.lark_client = (
            lark.Client.builder()
            .app_id(self.config.app_id)
            .app_secret(self.config.app_secret)
            .build()
        )
        self.messaging.set_client(self.lark_client)

        # Setup event handlers
        event_handler = (
            lark.EventDispatcherHandler.builder("", "")
            .register_p2_im_message_receive_v1(self._handle_message)
            .register_p2_im_chat_access_event_bot_p2p_chat_entered_v1(
                self._handle_p2p_chat_entered
            )
            .build()
        )

        ws_client = lark.ws.Client(
            self.config.app_id,
            self.config.app_secret,
            event_handler=event_handler,
            log_level=lark.LogLevel.INFO,
        )

        logger.info("Connecting to Feishu (long connection)...")
        logger.info("Send '帮助' in Feishu to see available commands.")

        # Startup notification
        if self.config.admin_chat_id:
            try:
                self.messaging.send_text(self.config.admin_chat_id, "🤖 Kimix Bot 已启动")
            except Exception as exc:
                logger.warning("Startup notification failed: %s", exc)

        exit_code = 0
        shutdown_event = threading.Event()
        ws_error: Optional[Exception] = None

        def _run_ws() -> None:
            nonlocal ws_error
            try:
                logger.debug("WebSocket thread starting...")
                ws_client.start()
            except Exception as exc:
                ws_error = exc
                logger.error("WebSocket client error: %s", exc, exc_info=True)

        ws_thread = threading.Thread(target=_run_ws, daemon=True)
        ws_thread.start()

        # Wait a bit and check if WS thread died immediately
        ws_thread.join(timeout=3.0)
        if not ws_thread.is_alive():
            if ws_error:
                logger.error("WebSocket failed to start: %s", ws_error)
            else:
                logger.error("WebSocket thread exited immediately without error")
            logger.error("Possible causes: invalid app_id/app_secret, network issue, or Feishu app not published")
            return 1

        logger.info("WebSocket client connected")

        heartbeat_counter = 0
        try:
            while not shutdown_event.is_set():
                shutdown_event.wait(1.0)
                heartbeat_counter += 1
                if heartbeat_counter % 30 == 0:
                    logger.info("Bot is running... (heartbeat)")
                if not ws_thread.is_alive():
                    logger.error("WebSocket thread died unexpectedly")
                    break
        except KeyboardInterrupt:
            logger.info("Stopped by user")
        except Exception as exc:
            logger.error("Fatal error: %s", exc, exc_info=True)
            exit_code = 1
        finally:
            logger.info("Shutting down...")
            if hasattr(ws_client, "stop"):
                try:
                    ws_client.stop()
                except Exception as exc:
                    logger.warning("Error stopping ws_client: %s", exc)
            count = self.process_mgr.stop_all()
            logger.info("Stopped %d process(es)", count)
            self._save_contexts()
            if self.config.admin_chat_id:
                try:
                    self.messaging.send_text(self.config.admin_chat_id, "🛑 Kimix Bot 已关闭")
                except Exception:
                    pass

        return exit_code
