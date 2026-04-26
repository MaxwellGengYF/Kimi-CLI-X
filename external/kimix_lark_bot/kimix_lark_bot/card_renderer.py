# -*- coding: utf-8 -*-
"""Simple card renderer for Feishu interactive messages."""

from typing import Optional, List, Dict, Any


def _header(title: str, color: str = "blue") -> dict:
    return {
        "header": {
            "template": color,
            "title": {"content": title, "tag": "plain_text"},
        },
        "elements": [],
    }


def _add_text(card: dict, text: str) -> dict:
    card["elements"].append({
        "tag": "div",
        "text": {"content": text, "tag": "lark_md"},
    })
    return card


def result(title: str, content: str, success: bool = True) -> dict:
    card = _header(title, "green" if success else "red")
    _add_text(card, content)
    return card


def error(title: str, error_message: str, context_path: Optional[str] = None) -> dict:
    card = _header(f"❌ {title}", "red")
    _add_text(card, error_message)
    if context_path:
        _add_text(card, f"**路径:** `{context_path}`")
    return card


def progress(title: str, description: str) -> dict:
    card = _header(title, "blue")
    _add_text(card, description)
    return card


def session_status(path: str, state: str, port: int, pid: Optional[int] = None, activities: Optional[List[str]] = None) -> dict:
    from pathlib import Path
    name = Path(path).name
    card = _header(f"🚀 {name}", "green")
    lines = [
        f"**状态:** {state}",
        f"**端口:** {port}",
    ]
    if pid:
        lines.append(f"**PID:** {pid}")
    if activities:
        lines.append(f"\n**最近活动:**")
        for a in activities:
            lines.append(f"• {a}")
    _add_text(card, "\n".join(lines))
    return card


def current_workspace(path: str, mode: str = "coding") -> dict:
    from pathlib import Path
    name = Path(path).name
    card = _header(f"💻 当前工作区: {name}", "blue")
    _add_text(card, f"**路径:** `{path}`\n**模式:** {mode}")
    return card


def workspace_selection(projects: List[Dict[str, str]], session_states: Optional[Dict[str, str]] = None) -> dict:
    card = _header("📂 选择工作区", "blue")
    lines = []
    for p in projects:
        slug = p.get("slug", "")
        label = p.get("label", "")
        path = p.get("path", "")
        state = (session_states or {}).get(path, "stopped")
        icon = "🟢" if state == "running" else "⚪"
        lines.append(f"{icon} **{label or slug}** (`{slug}`) — {state}")
    _add_text(card, "\n".join(lines) if lines else "无配置项目")
    _add_text(card, "发送 `启动 <项目名>` 即可启动对应工作区。")
    return card


def confirmation(action_summary: str, risk_level: str = "normal", can_undo: bool = True, pending_id: Optional[str] = None) -> dict:
    card = _header("⚠️ 需要确认", "orange")
    lines = [f"**操作:** {action_summary}"]
    if risk_level != "normal":
        lines.append(f"**风险等级:** {risk_level}")
    lines.append("回复 **确认** 继续，回复 **取消** 放弃。")
    if can_undo:
        lines.append("*此操作可以在 30 秒内撤销。*")
    _add_text(card, "\n".join(lines))
    return card


def help_card(projects: List[Dict[str, str]], processes: List[Any]) -> dict:
    card = _header("📖 Kimix Bot 帮助", "blue")

    # Build projects section
    project_lines = []
    state_map = {p.path: p for p in processes}
    for p in projects:
        slug = p.get("slug", "")
        label = p.get("label", "")
        path = p.get("path", "")
        proc = state_map.get(path)
        icon = "🟢" if proc and proc.is_alive else "⚪"
        project_lines.append(f"{icon} `{slug}` — {label or path}")

    content = f"""\
我可以帮你控制 Kimix 开发环境。

**基本指令:**
• `启动 <项目名>` — 启动 kimix server
• `停止 <项目名>` — 停止 kimix server
• `状态` — 查看所有进程状态
• `帮助` — 显示此帮助

**在工作区中:**
• 直接输入文字 — 发送给 Kimix 执行
• `!退出` — 退出当前工作区
• `!状态` — 查看当前状态

**已配置项目:**
{"\n".join(project_lines) if project_lines else "（无）"}
"""
    _add_text(card, content)
    return card


def status_card(processes: List[Any], active_workspace: Optional[str] = None) -> dict:
    from pathlib import Path
    card = _header("📊 Kimix 进程状态", "blue")

    if not processes:
        _add_text(card, "当前无 kimix 进程运行。")
        return card

    lines = []
    for proc in processes:
        alive = proc.is_alive
        icon = (
            "🟢" if alive
            else {"stopped": "⚪", "starting": "🟡", "error": "🔴"}.get(
                proc.status.value, "⚪"
            )
        )
        name = Path(proc.path).name
        active_mark = " 👈 当前" if active_workspace == proc.path else ""
        lines.append(f"{icon} **{name}**  port={proc.port}  ws={proc.ws_port or '-'}  pid={proc.pid or '-'}{active_mark}")
        if proc.last_error:
            lines.append(f"   ⚠ {proc.last_error}")

    if active_workspace:
        lines.append(f"\n💻 **当前工作区:** `{Path(active_workspace).name}`")

    _add_text(card, "\n".join(lines))
    return card
