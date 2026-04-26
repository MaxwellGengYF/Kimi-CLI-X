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


# ── Feishu card content size limit (bytes, conservative) ─────────
_CARD_CONTENT_MAX_CHARS = 2800


def streaming_progress(
    title: str,
    task_text: str,
    elapsed: int,
    tools: Optional[List[Dict[str, str]]] = None,
    reasoning_snippet: str = "",
    text_snippet: str = "",
    finished: bool = False,
) -> dict:
    """Build a real-time streaming progress card showing tool/reasoning/text status.

    Args:
        title: Card header title.
        task_text: Original task text (truncated for display).
        elapsed: Elapsed seconds.
        tools: List of dicts with keys 'name', 'status', 'title'.
        reasoning_snippet: Latest reasoning text snippet.
        text_snippet: Latest text output snippet (tail).
        finished: Whether the task is done.
    """
    color = "green" if finished else "blue"
    card = _header(title, color)

    # Task summary
    task_display = task_text[:100] + ("..." if len(task_text) > 100 else "")
    _add_text(card, f"**任务:** {task_display}")

    # Tool activity section
    if tools:
        tool_lines = []
        for t in tools[-8:]:  # Show last 8 tools
            status = t.get("status", "")
            name = t.get("title") or t.get("name", "unknown")
            if status == "running":
                tool_lines.append(f"🔄 `{name}`")
            elif status in ("completed", "done"):
                tool_lines.append(f"✅ `{name}`")
            elif status == "error":
                tool_lines.append(f"❌ `{name}`")
            else:
                tool_lines.append(f"⏳ `{name}`")
        _add_text(card, "**工具调用:**\n" + "\n".join(tool_lines))

    # Reasoning snippet
    if reasoning_snippet:
        snippet = reasoning_snippet[-200:]
        if len(reasoning_snippet) > 200:
            snippet = "..." + snippet
        _add_text(card, f"**思考中:**\n{snippet}")

    # Text output snippet (tail)
    if text_snippet:
        snippet = text_snippet[-500:]
        if len(text_snippet) > 500:
            snippet = "..." + snippet
        _add_text(card, f"**输出预览:**\n{snippet}")

    # Status line
    status_text = f"✅ 已完成 ({elapsed}s)" if finished else f"⏳ 运行中 ({elapsed}s)"
    _add_text(card, status_text)

    return card


def paginated_result(
    title: str,
    content: str,
    success: bool = True,
    page_size: int = _CARD_CONTENT_MAX_CHARS,
) -> List[dict]:
    """Split a long result into multiple cards for pagination.

    Returns a list of card dicts. If content fits in one card, returns a single-item list.
    """
    if len(content) <= page_size:
        return [result(title, content, success)]

    pages: List[str] = []
    remaining = content
    while remaining:
        # Try to split at a newline near page_size boundary
        if len(remaining) <= page_size:
            pages.append(remaining)
            break
        cut = remaining[:page_size]
        last_nl = cut.rfind("\n")
        if last_nl > page_size // 2:
            pages.append(remaining[:last_nl])
            remaining = remaining[last_nl + 1:]
        else:
            pages.append(cut)
            remaining = remaining[page_size:]

    cards = []
    total = len(pages)
    for i, page in enumerate(pages):
        page_title = f"{title} ({i + 1}/{total})"
        cards.append(result(page_title, page, success))
    return cards


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
