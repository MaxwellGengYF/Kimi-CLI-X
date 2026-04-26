# -*- coding: utf-8 -*-
"""SSE CLI debugger – connects to `kimix serve` and interactively tests SSE streams."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from kimix.base import print_error
from kimix.server.client import KimixAsyncClient, parse_event, EventType


def _fmt_arg(s: str, max_len: int = 120) -> str:
    """Truncate long arguments, keeping head and tail."""
    if len(s) <= max_len:
        return s
    head = max_len // 2
    tail = max_len - head - 3
    return s[:head] + "..." + s[-tail:]


def _fmt_ts(unix_t: float) -> str:
    """Format unix timestamp to HH:MM:SS."""
    if not unix_t:
        return ""
    return time.strftime("%H:%M:%S", time.localtime(unix_t))


async def _sse_cli_main(host: str, port: int) -> None:
    client = KimixAsyncClient(host=host, port=port)
    print(f"[SSE CLI] Connecting to http://{host}:{port}")

    healthy = await client.health_check()
    if not healthy:
        print(f"[SSE CLI] Server not healthy at http://{host}:{port}")
        await client.close()
        return

    session = await client.create_session("SSE CLI debug session")
    print(f"[SSE CLI] Created session: {session.id}")
    print("[SSE CLI] Commands: /exit /new /abort /status /sessions /messages /clear /summarize /fix")

    tool_start_times: dict[str, float] = {}

    async def _cmd_help(task_split: list[str], text_arr: list[str]) -> tuple[None, bool]:
        print("[SSE CLI] Commands: /exit /new /abort /status /sessions /messages /clear /summarize /fix")
        return False

    async def _cmd_new(task_split: list[str], text_arr: list[str]) -> tuple[None, bool]:
        nonlocal session
        session = await client.create_session("SSE CLI debug session")
        print(f"[SSE CLI] New session: {session.id}")
        return False

    async def _cmd_abort(task_split: list[str], text_arr: list[str]) -> tuple[None, bool]:
        ok = await client.abort_session(session.id)
        print(f"[SSE CLI] Abort: {'ok' if ok else 'failed'}")
        return False

    async def _cmd_status(task_split: list[str], text_arr: list[str]) -> tuple[None, bool]:
        status = await client.get_session_status()
        print(f"[SSE CLI] Status: {status}")
        return False

    async def _cmd_sessions(task_split: list[str], text_arr: list[str]) -> tuple[None, bool]:
        sessions = await client.list_sessions()
        for s in sessions:
            print(f"  {s.id}: {s.title}")
        return False

    async def _cmd_messages(task_split: list[str], text_arr: list[str]) -> tuple[None, bool]:
        messages = await client.get_messages(session.id, limit=20)
        for m in messages:
            content = m.text_content[:100] if m.text_content else ""
            print(f"  [{m.role}] {content}...")
        return False

    async def _cmd_clear(task_split: list[str], text_arr: list[str]) -> tuple[None, bool]:
        ok = await client.clear_session(session.id)
        print(f"[SSE CLI] Clear: {'ok' if ok else 'failed'}")
        return False

    async def _cmd_summarize(task_split: list[str], text_arr: list[str]) -> tuple[None, bool]:
        ok = await client.summarize_session(session.id)
        print(f"[SSE CLI] Summarize: {'ok' if ok else 'failed'}")
        return False

    async def _cmd_fix(task_split: list[str], text_arr: list[str]) -> tuple[None, bool]:
        if len(task_split) < 2:
            print_error("Command must be /fix:<command>")
            return False
        command_to_fix = (":".join(task_split[1:])).strip()
        ok = await client.fix_session(session.id, command=command_to_fix)
        print(f"[SSE CLI] Fix: {'ok' if ok else 'failed'}")
        return False
    
    async def _cmd_unknown(task_split: list[str], text_arr: list[str]) -> tuple[None, bool]:
        print(f"[SSE CLI] Unrecognized command: {task_split[0]}")
        return False

    _command_map = {
        "help": _cmd_help,
        "new": _cmd_new,
        "abort": _cmd_abort,
        "status": _cmd_status,
        "sessions": _cmd_sessions,
        "messages": _cmd_messages,
        "clear": _cmd_clear,
        "summarize": _cmd_summarize,
        "fix": _cmd_fix,
    }

    while True:
        try:
            text = input("> ")
        except (EOFError, KeyboardInterrupt):
            break

        cmd = text.strip()
        if not cmd:
            continue

        if cmd.startswith("/"):
            task = cmd[1:]
            split_idx = task.find(":")
            if split_idx >= 0:
                task_split = [task[:split_idx], task[split_idx + 1:]]
            else:
                task_split = [task]
            handler = _command_map.get(task_split[0], _cmd_unknown)
            should_break = await handler(task_split, [])
            if should_break:
                break
            continue

        ok = await client.send_prompt_async(session.id, text)
        if not ok:
            print("[SSE CLI] Failed to send prompt")
            continue

        print("[SSE CLI] Streaming events...")
        async for event in client.stream_events_robust(session.id):
            parsed = parse_event(event, session.id)
            if parsed.type == EventType.SKIP:
                continue
            if parsed.type == EventType.TEXT_DELTA:
                print(parsed.delta, end="", flush=True)
            elif parsed.type == EventType.TEXT:
                print(parsed.delta, end="", flush=True)
            elif parsed.type == EventType.TOOL:
                extra: list[str] = []
                if parsed.tool_input:
                    extra.append(f"input: {_fmt_arg(parsed.tool_input)}")
                if parsed.tool_output:
                    extra.append(f"output: {_fmt_arg(parsed.tool_output)}")
                if parsed.tool_error:
                    extra.append(f"error: {_fmt_arg(parsed.tool_error)}")
                if parsed.tool_call_id:
                    extra.append(f"callId: {parsed.tool_call_id[:8]}")

                ts_info = ""
                if parsed.tool_status == "running" and parsed.tool_call_id:
                    tool_start_times[parsed.tool_call_id] = parsed.created_at or time.time()
                    ts_info = f"  start@{_fmt_ts(parsed.created_at or time.time())}"
                elif parsed.tool_status in ("completed", "error") and parsed.tool_call_id in tool_start_times:
                    start_t = tool_start_times.pop(parsed.tool_call_id, 0)
                    duration = (parsed.created_at or time.time()) - start_t
                    ts_info = f"  took {duration:.1f}s  end@{_fmt_ts(parsed.created_at or time.time())}"
                elif parsed.created_at:
                    ts_info = f"  {_fmt_ts(parsed.created_at)}"

                print(f"\n[TOOL] {parsed.tool_name} status={parsed.tool_status}{ts_info}")
                for line in extra:
                    print(f"       {line}")
            elif parsed.type == EventType.REASONING:
                print(f"\n[REASONING] {parsed.text}")
            elif parsed.type == EventType.STEP_START:
                print("\n[STEP START]")
            elif parsed.type == EventType.STEP_FINISH:
                print(f"\n[STEP FINISH] reason={parsed.text}")
            elif parsed.type == EventType.SESSION_IDLE:
                print("\n[SESSION IDLE]")
            elif parsed.type == EventType.RECONNECTED:
                print(f"\n[RECONNECTED] {parsed.text}")
            elif parsed.type == EventType.UNKNOWN:
                print(f"\n[UNKNOWN] {parsed.raw}")
            if parsed.is_terminal():
                break
        print()  # newline after stream

    await client.close()
    print("[SSE CLI] Bye.")


def run_sse_cli(host: str, port: int) -> None:
    try:
        asyncio.run(_sse_cli_main(host, port))
    except KeyboardInterrupt:
        pass
