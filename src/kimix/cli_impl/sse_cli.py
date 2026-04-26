# -*- coding: utf-8 -*-
"""SSE CLI debugger – connects to `kimix serve` and interactively tests SSE streams."""

from __future__ import annotations

import asyncio
import time

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
    print("[SSE CLI] Commands: /exit /new /abort /status /sessions /messages")

    tool_start_times: dict[str, float] = {}

    while True:
        try:
            text = input("> ")
        except (EOFError, KeyboardInterrupt):
            break

        cmd = text.strip()
        if cmd == "/exit":
            break
        if cmd == "/new":
            session = await client.create_session("SSE CLI debug session")
            print(f"[SSE CLI] New session: {session.id}")
            continue
        if cmd == "/abort":
            ok = await client.abort_session(session.id)
            print(f"[SSE CLI] Abort: {'ok' if ok else 'failed'}")
            continue
        if cmd == "/status":
            status = await client.get_session_status()
            print(f"[SSE CLI] Status: {status}")
            continue
        if cmd == "/sessions":
            sessions = await client.list_sessions()
            for s in sessions:
                print(f"  {s.id}: {s.title}")
            continue
        if cmd == "/messages":
            messages = await client.get_messages(session.id, limit=20)
            for m in messages:
                content = m.text_content[:100] if m.text_content else ""
                print(f"  [{m.role}] {content}...")
            continue
        if not cmd:
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
