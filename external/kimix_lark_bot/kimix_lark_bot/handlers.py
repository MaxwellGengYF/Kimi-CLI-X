# -*- coding: utf-8 -*-
"""Handlers for Kimix Lark Bot."""

import asyncio
import json
import re
import time
import threading
import logging
import traceback
from typing import Optional, Dict, Any, List
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import lark_oapi as lark

from kimix_lark_bot.context import ActionPlan, ConversationContext, PendingConfirmation
from kimix_lark_bot.card_renderer import (
    result, error, progress, session_status, current_workspace,
    workspace_selection, confirmation, help_card, status_card,
    streaming_progress, paginated_result,
)
from kimix_lark_bot.messaging import FeishuMessagingClient
from kimix_lark_bot.process_manager import KimixProcessManager, extract_path_from_text
from kimix_lark_bot.config import AgentConfig
from kimix_lark_bot.brain import BotBrain

from kimix_lark_bot.kimix_client_x import (
    KimixAsyncClient, EventType, check_health_sync, parse_event,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# OperationTracker
# ---------------------------------------------------------------------------
class OperationTracker:
    """Simple operation tracker with timeouts."""

    def __init__(self):
        self._ops: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._counter = 0

    def start(self, path: str, description: str, timeout: float = 300.0) -> str:
        with self._lock:
            self._counter += 1
            op_id = f"op_{self._counter:04d}"
            self._ops[op_id] = {
                "path": path,
                "description": description,
                "started_at": time.time(),
                "timeout": timeout,
            }
            return op_id

    def finish(self, op_id: str) -> None:
        with self._lock:
            self._ops.pop(op_id, None)

    def is_active(self, op_id: str) -> bool:
        with self._lock:
            op = self._ops.get(op_id)
            if not op:
                return False
            return time.time() - op["started_at"] < op["timeout"]


# ---------------------------------------------------------------------------
# HandlerContext
# ---------------------------------------------------------------------------
class HandlerContext:
    def __init__(
        self,
        messaging: FeishuMessagingClient,
        process_mgr: KimixProcessManager,
        brain: BotBrain,
        config: AgentConfig,
        agent: Optional[Any] = None,
    ):
        self.messaging = messaging
        self.process_mgr = process_mgr
        self.brain = brain
        self.config = config
        self.agent = agent
        self.op_tracker = OperationTracker()

    def get_or_create_context(self, chat_id: str) -> ConversationContext:
        if self.agent:
            return self.agent._get_context(chat_id)
        raise NotImplementedError("Agent reference not set")

    def save_contexts(self) -> None:
        if self.agent:
            self.agent._save_contexts()


# ---------------------------------------------------------------------------
# BaseHandler
# ---------------------------------------------------------------------------
class BaseHandler:
    def __init__(self, ctx: HandlerContext):
        self.ctx = ctx

    def handle(self, *args, **kwargs) -> Any:
        raise NotImplementedError("Subclasses must implement handle()")


# ---------------------------------------------------------------------------
# MessageDeduplicator
# ---------------------------------------------------------------------------
class _MessageDeduplicator:
    def __init__(self, ttl_seconds: int = 300):
        self._seen: dict[str, float] = {}
        self._lock = threading.Lock()
        self._ttl = ttl_seconds

    def is_duplicate(self, message_id: str) -> bool:
        now = time.time()
        with self._lock:
            if len(self._seen) > 500:
                cutoff = now - self._ttl
                self._seen = {k: v for k, v in self._seen.items() if v > cutoff}
            if message_id in self._seen:
                return True
            self._seen[message_id] = now
            return False


_dedup = _MessageDeduplicator()
_executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="msg-handler")


# ---------------------------------------------------------------------------
# MessageHandler
# ---------------------------------------------------------------------------
class MessageHandler(BaseHandler):
    def handle(self, data: lark.im.v1.P2ImMessageReceiveV1) -> None:
        try:
            if not data or not data.event or not data.event.message:
                logger.debug("Empty data or message, skipping")
                return
            message = data.event.message
            if message.message_type != "text":
                logger.debug("Ignoring non-text message: %s", message.message_type)
                return
            try:
                content = json.loads(message.content or "{}")
            except json.JSONDecodeError:
                logger.debug("Invalid JSON content, skipping")
                return

            text = content.get("text", "").strip()
            chat_id = message.chat_id
            message_id = message.message_id

            logger.debug("[Raw] chat_id=%s message_id=%s text=%r", chat_id, message_id, text)

            if _dedup.is_duplicate(message_id):
                logger.debug("Duplicate message %s, skipping", message_id)
                return
            if not text or not chat_id:
                logger.debug("Empty text or chat_id, skipping")
                return

            logger.info("[%s] User: %s", chat_id, text)
            _executor.submit(self._process_message, text, chat_id, message_id)
        except Exception as exc:
            logger.error("Message handler error: %s", exc, exc_info=True)
            traceback.print_exc()

    def _process_message(self, text: str, chat_id: str, message_id: str) -> None:
        text = re.sub(r"@_user_\S+", "", text).strip()
        text = re.sub(r"@\S+", "", text).strip()
        if not text:
            logger.debug("Empty text after filtering mentions, skipping")
            return

        ctx = self.ctx.get_or_create_context(chat_id)
        ctx.push("user", text)
        logger.debug("[%s] Context mode=%s workspace=%s", chat_id, ctx.mode, ctx.active_workspace)

        plan = self._dispatch_message(text, chat_id, message_id, ctx)
        logger.debug("[%s] Plan action=%s params=%s", chat_id, plan.action, plan.params)

        if plan.action not in ("noop", "chat", "clarify"):
            logger.info("[%s] Executing action=%s", chat_id, plan.action)
            executor = PlanExecutor(self.ctx)
            executor.execute(plan, chat_id, message_id, ctx)
        else:
            logger.debug("[%s] No action to execute (action=%s)", chat_id, plan.action)

    def _dispatch_message(self, text: str, chat_id: str, message_id: str, ctx: ConversationContext) -> ActionPlan:
        # Check for pending confirmation reply
        if ctx.pending:
            logger.debug("[%s] Has pending confirmation: %s", chat_id, ctx.pending.summary)
            decision = self.ctx.brain.check_confirmation_reply(text)
            if decision is True:
                logger.info("[%s] User confirmed pending action: %s", chat_id, ctx.pending.action)
                plan = ActionPlan(action=ctx.pending.action, params=ctx.pending.params)
                ctx.clear_pending()
                return plan
            elif decision is False:
                logger.info("[%s] User cancelled pending action", chat_id)
                ctx.clear_pending()
                self.ctx.messaging.reply_card(message_id, result("已取消", "操作已取消。", success=False))
                ctx.push("bot", "已取消")
                return ActionPlan(action="noop")
            else:
                logger.debug("[%s] Unrelated reply to pending, clearing", chat_id)
                ctx.clear_pending()
                self.ctx.messaging.reply_text(message_id, "确认已超时，请重新发起指令。")
                return ActionPlan(action="noop")

        plan = self.ctx.brain.think(text, ctx)
        logger.debug("[%s] Brain think result: action=%s confirm_required=%s", chat_id, plan.action, plan.confirm_required)

        if plan.action in ("chat", "clarify", "noop"):
            reply = plan.reply or "我不太确定你的意思，能再描述一下吗？"
            ctx.push("bot", reply[:200])
            self.ctx.messaging.reply_text(message_id, reply)
            return plan

        if plan.confirm_required:
            logger.info("[%s] Action requires confirmation: %s", chat_id, plan.confirm_summary)
            ctx.pending = self.ctx.brain.build_confirmation(
                plan.action, plan.params, plan.confirm_summary or plan.action, ctx
            )
            card = confirmation(
                action_summary=plan.confirm_summary or plan.action,
                pending_id=f"pending_{chat_id}",
            )
            self.ctx.messaging.reply_card(message_id, card)
            ctx.push("bot", "需要确认: " + (plan.confirm_summary or plan.action))
            return ActionPlan(action="noop")

        return plan


# ---------------------------------------------------------------------------
# PlanExecutor
# ---------------------------------------------------------------------------
class PlanExecutor(BaseHandler):
    def __init__(self, ctx: HandlerContext):
        super().__init__(ctx)
        self._help = HelpHandler(ctx)
        self._status = StatusHandler(ctx)
        self._start = StartWorkspaceHandler(ctx)
        self._stop = StopWorkspaceHandler(ctx)
        self._switch = SwitchWorkspaceHandler(ctx)
        self._exit = ExitWorkspaceHandler(ctx)
        self._task = TaskHandler(ctx)

        self._registry: Dict[str, Any] = {
            "show_help": self._help.handle,
            "show_status": self._status.handle,
            "switch_workspace": self._switch.handle,
            "start_workspace": self._start.handle,
            "stop_workspace": self._stop.handle,
            "exit_workspace": self._exit.handle,
            "send_task": self._task.handle,
        }

    def execute(self, plan: ActionPlan, chat_id: str, message_id: str, ctx: ConversationContext) -> None:
        handler_fn = self._registry.get(plan.action)
        if handler_fn:
            logger.info("[%s] Executing handler for %s", chat_id, plan.action)
            handler_fn(plan, chat_id, message_id, ctx)
            ctx.push("bot", plan.action)
        else:
            logger.warning("[%s] Unknown action: %s", chat_id, plan.action)
            self.ctx.messaging.reply_text(message_id, f"未知动作: {plan.action}")


# ---------------------------------------------------------------------------
# HelpHandler
# ---------------------------------------------------------------------------
class HelpHandler(BaseHandler):
    def handle(self, plan: ActionPlan, chat_id: str, message_id: str, ctx: ConversationContext) -> None:
        procs = self.ctx.process_mgr.list_processes()
        card = help_card(self.ctx.config.projects, procs)
        self.ctx.messaging.reply_card(message_id, card)
        ctx.push("bot", "显示帮助")


# ---------------------------------------------------------------------------
# StatusHandler
# ---------------------------------------------------------------------------
class StatusHandler(BaseHandler):
    def handle(self, plan: ActionPlan, chat_id: str, message_id: str, ctx: ConversationContext) -> None:
        procs = self.ctx.process_mgr.list_processes()
        card = status_card(procs, active_workspace=ctx.active_workspace)
        self.ctx.messaging.reply_card(message_id, card)
        ctx.push("bot", "显示状态")


# ---------------------------------------------------------------------------
# StartWorkspaceHandler
# ---------------------------------------------------------------------------
class StartWorkspaceHandler(BaseHandler):
    def handle(self, plan: ActionPlan, chat_id: str, message_id: str, ctx: ConversationContext) -> None:
        path = plan.params.get("path")
        project_slug = plan.params.get("project")

        if project_slug:
            path = extract_path_from_text(project_slug, self.ctx.config.projects)
        elif path:
            path = extract_path_from_text(path, self.ctx.config.projects)

        if not path:
            logger.info("[%s] No path resolved, showing workspace selection", chat_id)
            projects = self.ctx.config.projects
            state_map = {}
            for proc in self.ctx.process_mgr.list_processes():
                state_map[proc.path] = proc.status.value
            card = workspace_selection(projects, session_states=state_map)
            self.ctx.messaging.reply_card(message_id, card)
            return

        name = Path(path).name
        logger.info("[%s] Starting workspace: %s", chat_id, path)

        op_id = self.ctx.op_tracker.start(path, f"启动 {name}", timeout=30.0)
        prog_card = progress(f"正在启动 {name}", "初始化 Kimix 服务...")
        prog_mid = self.ctx.messaging.reply_card(message_id, prog_card)

        def do_start() -> None:
            stop_event = threading.Event()

            def _poll_progress():
                elapsed = 0
                while not stop_event.wait(3.0):
                    elapsed += 3
                    card = progress(f"正在启动 {name}", f"已等待 {elapsed} 秒，请稍候...")
                    if prog_mid:
                        self.ctx.messaging.update_card(prog_mid, card)

            poll_thread = threading.Thread(target=_poll_progress, daemon=True)
            poll_thread.start()
            try:
                ok, proc, msg = self.ctx.process_mgr.ensure_running(path, chat_id)
            except Exception as exc:
                stop_event.set()
                self.ctx.op_tracker.finish(op_id)
                logger.error("[%s] Exception in start workspace: %s", chat_id, exc, exc_info=True)
                err_card = error("启动异常", str(exc), context_path=path)
                if prog_mid:
                    self.ctx.messaging.update_card(prog_mid, err_card)
                else:
                    self.ctx.messaging.send_card(chat_id, err_card)
                return
            finally:
                stop_event.set()

            self.ctx.op_tracker.finish(op_id)

            if ok:
                ctx.mode = "coding"
                ctx.active_workspace = proc.path
                ctx.clear_pending()
                self.ctx.save_contexts()

                result_card = session_status(
                    path=proc.path,
                    state="running",
                    port=proc.port,
                    pid=proc.pid,
                )
                if prog_mid:
                    self.ctx.messaging.update_card(prog_mid, result_card)
                else:
                    self.ctx.messaging.send_card(chat_id, result_card)

                ws_card = current_workspace(proc.path, mode="coding")
                self.ctx.messaging.send_card(chat_id, ws_card)
                ctx.push("bot", "Kimix 已启动: " + proc.path)
                logger.info("[%s] Workspace started: %s port=%s", chat_id, proc.path, proc.port)
            else:
                logger.error("[%s] Failed to start workspace: %s", chat_id, msg)
                err_card = error("启动失败", msg, context_path=path)
                if prog_mid:
                    self.ctx.messaging.update_card(prog_mid, err_card)
                else:
                    self.ctx.messaging.send_card(chat_id, err_card)

        threading.Thread(target=do_start, daemon=True).start()


# ---------------------------------------------------------------------------
# StopWorkspaceHandler
# ---------------------------------------------------------------------------
class StopWorkspaceHandler(BaseHandler):
    def handle(self, plan: ActionPlan, chat_id: str, message_id: str, ctx: ConversationContext) -> None:
        path = plan.params.get("path")
        if path:
            path = extract_path_from_text(path, self.ctx.config.projects) or path

        if path:
            name = Path(path).name
            logger.info("[%s] Stopping workspace: %s", chat_id, path)
            ok, msg = self.ctx.process_mgr.stop(path)
            if ok and ctx.active_workspace == path:
                ctx.mode = "idle"
                ctx.active_workspace = None
                ctx.active_session_id = None
                ctx.clear_pending()
                self.ctx.save_contexts()
            card = result("已停止" if ok else "停止失败", f"{name} {'已停止。' if ok else msg}", success=ok)
            self.ctx.messaging.reply_card(message_id, card)
            ctx.push("bot", "已停止: " + path)
        else:
            procs = self.ctx.process_mgr.list_processes()
            if not procs:
                self.ctx.messaging.reply_text(message_id, "没有正在运行的会话。")
                return
            logger.info("[%s] Stopping all workspaces (%d)", chat_id, len(procs))
            results = []
            for p in procs:
                ok, msg = self.ctx.process_mgr.stop(p.path)
                results.append(Path(p.path).name + ": " + ("已停止" if ok else msg))
            ctx.mode = "idle"
            ctx.active_workspace = None
            ctx.active_session_id = None
            ctx.clear_pending()
            self.ctx.save_contexts()
            self.ctx.messaging.reply_card(message_id, result("全部停止", "\n".join(results), success=True))
            ctx.push("bot", "全部停止")


# ---------------------------------------------------------------------------
# SwitchWorkspaceHandler
# ---------------------------------------------------------------------------
class SwitchWorkspaceHandler(BaseHandler):
    def handle(self, plan: ActionPlan, chat_id: str, message_id: str, ctx: ConversationContext) -> None:
        path = plan.params.get("path")
        if not path:
            self.ctx.messaging.reply_text(message_id, "请指定工作区路径")
            return
        name = Path(path).name
        logger.info("[%s] Switching workspace to: %s", chat_id, path)
        ctx.mode = "coding"
        ctx.active_workspace = path
        ctx.clear_pending()
        self.ctx.save_contexts()
        card = result(title=f"🔄 已切换到工作区", content=f"**工作区:** {name}\n**路径:** `{path}`", success=True)
        self.ctx.messaging.reply_card(message_id, card)
        ctx.push("bot", f"已切换到工作区: {name}")


# ---------------------------------------------------------------------------
# ExitWorkspaceHandler
# ---------------------------------------------------------------------------
class ExitWorkspaceHandler(BaseHandler):
    def handle(self, plan: ActionPlan, chat_id: str, message_id: str, ctx: ConversationContext) -> None:
        old = ctx.active_workspace
        logger.info("[%s] Exiting workspace: %s", chat_id, old)
        ctx.mode = "idle"
        ctx.active_workspace = None
        ctx.active_session_id = None
        ctx.clear_pending()
        self.ctx.save_contexts()
        self.ctx.messaging.reply_text(message_id, f"已退出工作区{f' ({Path(old).name})' if old else ''}。")
        ctx.push("bot", "已退出工作区")


# ---------------------------------------------------------------------------
# TaskHandler – async SSE streaming with real-time card updates
# ---------------------------------------------------------------------------

# Minimum interval between card updates (seconds) to respect Feishu rate limits
_CARD_UPDATE_INTERVAL = 2.0


class TaskHandler(BaseHandler):
    """Execute a coding task via KimixAsyncClient with SSE streaming.

    Flow:
    1. ensure_running (sync, in thread) to start the kimix server if needed.
    2. Connect via KimixAsyncClient.
    3. Fire prompt_async (non-blocking).
    4. Consume SSE events, updating the Feishu card in real-time.
    5. On completion, send paginated result cards.
    """

    def handle(self, plan: ActionPlan, chat_id: str, message_id: str, ctx: ConversationContext) -> None:
        task_text = plan.params.get("task", "")
        path = plan.params.get("path")

        if not path:
            running = [p for p in self.ctx.process_mgr.list_processes() if p.is_alive]
            if not running:
                self.ctx.messaging.reply_card(
                    message_id,
                    error("未找到会话", "没有正在运行的 Kimix 会话。\n请先启动一个，例如：启动 myproject"),
                )
                return
            if len(running) == 1:
                path = running[0].path
            elif ctx.active_workspace:
                path = ctx.active_workspace
            else:
                names = [Path(p.path).name for p in running]
                self.ctx.messaging.reply_text(
                    message_id, "有多个会话运行中：" + ", ".join(names) + "\n请指定工作区",
                )
                return

        name = Path(path).name
        logger.info("[%s] Task in %s: %s", chat_id, name, task_text[:60])

        op_id = self.ctx.op_tracker.start(path, task_text[:60], timeout=14400.0)
        prog_card = progress(
            title="🚀 任务已提交",
            description=f"正在初始化...\n\n**任务:** {task_text[:100]}{'...' if len(task_text) > 100 else ''}",
        )
        prog_mid = self.ctx.messaging.reply_card(message_id, prog_card)

        def _run_async_task() -> None:
            """Run the async task pipeline in a fresh event loop on this thread."""
            try:
                asyncio.run(
                    self._do_task_async(
                        task_text=task_text,
                        path=path,
                        chat_id=chat_id,
                        ctx=ctx,
                        op_id=op_id,
                        prog_mid=prog_mid,
                    )
                )
            except Exception as exc:
                logger.error("[%s] Async task runner error: %s", chat_id, exc, exc_info=True)
                self.ctx.op_tracker.finish(op_id)
                err_card = error("任务异常", str(exc), context_path=path)
                if prog_mid:
                    self.ctx.messaging.update_card(prog_mid, err_card)
                else:
                    self.ctx.messaging.send_card(chat_id, err_card)

        threading.Thread(target=_run_async_task, daemon=True, name=f"task-{chat_id[:8]}").start()

    # ── Async task core ──────────────────────────────────────────

    async def _do_task_async(
        self,
        task_text: str,
        path: str,
        chat_id: str,
        ctx: ConversationContext,
        op_id: str,
        prog_mid: Optional[str],
    ) -> None:
        # --- Phase 1: ensure kimix server is running (blocking I/O) ---
        loop = asyncio.get_running_loop()
        try:
            ok, proc, start_msg = await loop.run_in_executor(
                None, self.ctx.process_mgr.ensure_running, path, chat_id,
            )
        except Exception as exc:
            self.ctx.op_tracker.finish(op_id)
            logger.error("[%s] Exception ensuring server: %s", chat_id, exc, exc_info=True)
            err_card = error("任务异常", str(exc), context_path=path)
            if prog_mid:
                self.ctx.messaging.update_card(prog_mid, err_card)
            else:
                self.ctx.messaging.send_card(chat_id, err_card)
            return

        if not ok:
            logger.error("[%s] Failed to ensure running: %s", chat_id, start_msg)
            self.ctx.op_tracker.finish(op_id)
            err_card = error("启动失败", start_msg, context_path=path)
            if prog_mid:
                self.ctx.messaging.update_card(prog_mid, err_card)
            return

        ctx.mode = "coding"
        ctx.active_workspace = proc.path
        ctx.clear_pending()
        self.ctx.save_contexts()

        if not task_text:
            self.ctx.op_tracker.finish(op_id)
            card = result("就绪", "Kimix 已就绪，请描述你的任务。", success=True)
            if prog_mid:
                self.ctx.messaging.update_card(prog_mid, card)
            return

        # --- Phase 2: connect & create session ---
        async with KimixAsyncClient(host="127.0.0.1", port=proc.port) as client:
            logger.debug("[%s] Connecting to kimix serve port=%s", chat_id, proc.port)
            if not await client.health_check():
                self.ctx.op_tracker.finish(op_id)
                err_card = error("连接失败", f"无法连接到 Kimix server (port={proc.port})", context_path=path)
                if prog_mid:
                    self.ctx.messaging.update_card(prog_mid, err_card)
                return

            session_id = ctx.active_session_id
            if not session_id:
                logger.debug("[%s] Creating new session", chat_id)
                sess = await client.create_session(title=f"Lark Bot - {Path(path).name}")
                session_id = sess.id
                ctx.active_session_id = session_id
                self.ctx.save_contexts()
                logger.info("[%s] Session created: %s", chat_id, session_id)
            else:
                logger.debug("[%s] Reusing session: %s", chat_id, session_id)

            # --- Phase 3: fire prompt (non-blocking) & stream SSE ---
            await self._stream_task(
                client=client,
                session_id=session_id,
                task_text=task_text,
                chat_id=chat_id,
                path=path,
                ctx=ctx,
                op_id=op_id,
                prog_mid=prog_mid,
            )

    # ── SSE streaming core ───────────────────────────────────────

    async def _stream_task(
        self,
        client: KimixAsyncClient,
        session_id: str,
        task_text: str,
        chat_id: str,
        path: str,
        ctx: ConversationContext,
        op_id: str,
        prog_mid: Optional[str],
    ) -> None:
        start_time = time.time()

        # Mutable state for progress card
        tools: List[Dict[str, str]] = []
        reasoning_text = ""
        output_text = ""
        last_update = 0.0

        def _elapsed() -> int:
            return int(time.time() - start_time)

        def _update_card_throttled(force: bool = False) -> None:
            """Update the Feishu card, throttled to avoid rate limits."""
            nonlocal last_update
            now = time.time()
            if not force and (now - last_update) < _CARD_UPDATE_INTERVAL:
                return
            last_update = now
            if not prog_mid:
                return
            card = streaming_progress(
                title=f"⏳ 执行中 ({_elapsed()}s)",
                task_text=task_text,
                elapsed=_elapsed(),
                tools=tools,
                reasoning_snippet=reasoning_text,
                text_snippet=output_text,
            )
            try:
                self.ctx.messaging.update_card(prog_mid, card)
            except Exception as exc:
                logger.warning("[%s] Card update failed: %s", chat_id, exc)

        try:
            logger.debug("[%s] Sending prompt_async: %s", chat_id, task_text[:80])
            ok = await client.send_prompt_async(session_id, task_text)
            if not ok:
                raise RuntimeError("prompt_async returned non-204")

            # Consume SSE events
            async for raw_event in client.stream_events_robust(session_id):
                parsed = parse_event(raw_event, session_id)

                if parsed.type == EventType.SKIP:
                    continue

                if parsed.type == EventType.TEXT:
                    output_text = parsed.text
                    _update_card_throttled()

                elif parsed.type == EventType.TEXT_DELTA:
                    output_text += parsed.delta
                    _update_card_throttled()

                elif parsed.type == EventType.TOOL:
                    tool_entry = {
                        "name": parsed.tool_name,
                        "status": parsed.tool_status,
                        "title": parsed.tool_title,
                    }
                    # Update existing tool entry or add new one
                    updated = False
                    for i, t in enumerate(tools):
                        if t["name"] == parsed.tool_name and t["status"] not in ("completed", "done"):
                            tools[i] = tool_entry
                            updated = True
                            break
                    if not updated:
                        tools.append(tool_entry)
                    _update_card_throttled()

                elif parsed.type == EventType.REASONING:
                    reasoning_text = parsed.text
                    _update_card_throttled()

                elif parsed.type == EventType.STEP_START:
                    _update_card_throttled()

                elif parsed.type == EventType.STEP_FINISH:
                    if parsed.is_terminal():
                        logger.info("[%s] Task finished (reason=%s)", chat_id, parsed.text)
                        break
                    # Non-terminal step finish (e.g. tool_calls) — continue
                    _update_card_throttled()

                elif parsed.type == EventType.SESSION_IDLE:
                    logger.info("[%s] Session idle", chat_id)
                    break

                elif parsed.type == EventType.RECONNECTED:
                    logger.info("[%s] SSE reconnected", chat_id)

        except Exception as exc:
            self.ctx.op_tracker.finish(op_id)
            logger.error("[%s] SSE streaming error: %s", chat_id, exc, exc_info=True)
            err_card = error("执行异常", str(exc), context_path=path)
            if prog_mid:
                self.ctx.messaging.update_card(prog_mid, err_card)
            else:
                self.ctx.messaging.send_card(chat_id, err_card)
            ctx.push("bot", f"任务出错: {str(exc)[:50]}")
            return

        # --- Task completed ---
        self.ctx.op_tracker.finish(op_id)
        elapsed = _elapsed()
        final_text = output_text or "（任务已完成，无输出）"

        # Send paginated results
        cards = paginated_result(
            title=f"✅ 任务完成 ({elapsed}s)",
            content=final_text,
            success=True,
        )

        # First card: update the progress card in-place
        if prog_mid and cards:
            self.ctx.messaging.update_card(prog_mid, cards[0])
            # Additional pages: send as new messages
            for extra_card in cards[1:]:
                self.ctx.messaging.send_card(chat_id, extra_card)
        else:
            for c in cards:
                self.ctx.messaging.send_card(chat_id, c)

        ctx.push("bot", f"任务完成（{elapsed}s）")
        logger.info("[%s] Task completed in %ss, %d page(s)", chat_id, elapsed, len(cards))
