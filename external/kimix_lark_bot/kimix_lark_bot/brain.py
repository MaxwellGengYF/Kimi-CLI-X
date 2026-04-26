# -*- coding: utf-8 -*-
"""Bot brain with deterministic intent recognition."""

from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
import logging

from kimix_lark_bot.context import ActionPlan, ConversationContext, PendingConfirmation
from kimix_lark_bot.process_manager import extract_path_from_text

logger = logging.getLogger(__name__)


_CONFIRM_WORDS = {"是", "是的", "确认", "确定", "y", "yes", "ok", "好", "行", "可以", "没错", "对", "对的"}
_CANCEL_WORDS = {"否", "不是", "取消", "不", "n", "no", "算了", "别", "不要", "拒绝"}

_BRAIN_FALLBACK_ACTIONS = {
    "帮助": ("show_help", {}),
    "help": ("show_help", {}),
    "状态": ("show_status", {}),
    "status": ("show_status", {}),
}


class BotBrain:
    _CONFIRM_TTL = timedelta(minutes=5)

    def __init__(self, projects: List[Dict[str, str]]):
        self.projects = projects

    def think(self, text: str, ctx: ConversationContext) -> ActionPlan:
        plan = self._think_deterministic(text, ctx)
        logger.debug("[Brain] text=%r mode=%s action=%s", text, ctx.mode, plan.action)
        if plan.action != "chat":
            return plan
        return self._create_fallback_plan(text, ctx)

    def _create_fallback_plan(self, text: str, ctx: ConversationContext) -> ActionPlan:
        if ctx.mode == "coding" and ctx.active_workspace:
            return ActionPlan(
                action="send_task",
                params={"task": text, "path": ctx.active_workspace},
            )
        return ActionPlan(
            action="chat",
            reply=(
                "我可以帮你控制 Kimix 开发环境。试试这些指令：\n"
                "• 启动 myproject\n"
                "• 停止 myproject\n"
                "• 查看状态\n"
                "• 帮我写代码...\n\n"
                "或者直接描述你需要做什么。"
            ),
        )

    def build_confirmation(
        self, action: str, params: Dict[str, Any], summary: str, ctx: ConversationContext,
    ) -> PendingConfirmation:
        return PendingConfirmation(
            action=action,
            params=params,
            summary=summary,
            expires_at=datetime.now() + self._CONFIRM_TTL,
        )

    def check_confirmation_reply(self, text: str) -> Optional[bool]:
        t = text.strip().lower()
        if t in _CONFIRM_WORDS:
            logger.debug("[Brain] Confirmation reply: True (%r)", t)
            return True
        if t in _CANCEL_WORDS:
            logger.debug("[Brain] Confirmation reply: False (%r)", t)
            return False
        logger.debug("[Brain] Confirmation reply: None (%r)", t)
        return None

    def _think_deterministic(self, text: str, ctx: ConversationContext) -> ActionPlan:
        t = text.lower().strip()

        # === 状态2：在工作区 ===
        if ctx.mode == "coding" and ctx.active_workspace:
            if t.startswith("!") or t.startswith("！"):
                cmd_text = text.lstrip("!！").strip()
                cmd_lower = cmd_text.lower()

                for kw, (action, params) in _BRAIN_FALLBACK_ACTIONS.items():
                    if cmd_lower == kw:
                        return ActionPlan(action=action, params=params)

                if cmd_lower in ["状态", "status", "s"]:
                    return ActionPlan(action="show_status", params={})

                if any(k in cmd_lower for k in ["退出", "离开", "exit", "quit"]):
                    return ActionPlan(action="exit_workspace", params={})

                if any(k in cmd_lower for k in ["启动", "打开", "开启", "start", "open"]):
                    path = extract_path_from_text(cmd_text, self.projects)
                    return ActionPlan(action="start_workspace", params={"path": path})

                if any(k in cmd_lower for k in ["停止", "关闭", "结束", "stop", "kill"]):
                    path = extract_path_from_text(cmd_text, self.projects)
                    return ActionPlan(
                        action="stop_workspace",
                        params={"path": path},
                        confirm_required=True,
                        confirm_summary=f"停止 {'所有会话' if not path else path}",
                    )

                return ActionPlan(
                    action="chat",
                    reply=f"未知的控制指令: {cmd_text}\n\n可用的控制指令:\n• !状态 / !status / !s - 查看当前状态\n• !启动 <项目> - 启动工作区\n• !停止 - 停止工作区\n• !退出 - 退出当前工作区\n• !帮助 / !help - 显示帮助",
                )

            # 非感叹号开头 -> 直接转发给 Kimix
            return ActionPlan(
                action="send_task", params={"task": text, "path": ctx.active_workspace}
            )

        # === 状态1：不在工作区（idle）===
        for kw, (action, params) in _BRAIN_FALLBACK_ACTIONS.items():
            if t == kw:
                return ActionPlan(action=action, params=params)

        if any(k in t for k in ["start", "启动", "开启", "打开", "open"]):
            path = extract_path_from_text(text, self.projects)
            return ActionPlan(action="start_workspace", params={"path": path})

        if any(k in t for k in ["stop", "停止", "关闭", "结束", "kill"]):
            path = extract_path_from_text(text, self.projects)
            return ActionPlan(
                action="stop_workspace",
                params={"path": path},
                confirm_required=True,
                confirm_summary=f"停止 {'所有会话' if not path else path}",
            )

        if any(k in t for k in ["使用", "进入", "切换到", "切到", "use", "switch to", "enter"]):
            path = extract_path_from_text(text, self.projects)
            if path:
                return ActionPlan(action="switch_workspace", params={"path": path})

        return ActionPlan(action="chat")
