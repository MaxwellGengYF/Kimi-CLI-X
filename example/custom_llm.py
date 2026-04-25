"""Simple custom ChatProvider tests (no network)."""
from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path
from typing import Any

import pytest
from kaos.path import KaosPath
from kosong.chat_provider import ChatProvider, StreamedMessage, TokenUsage
from kosong.message import TextPart, ToolCall

from kimi_agent_sdk import Session, ToolResult
from kimix.utils import _create_session_async


class FixedStreamedMessage:
    """StreamedMessage that yields predefined parts."""

    def __init__(self, parts: list[Any]) -> None:
        self._parts = parts
        self._msg_id = "fixed-msg-001"

    def __aiter__(self) -> Any:
        return self._iterate()

    async def _iterate(self) -> Any:
        for part in self._parts:
            yield part

    @property
    def id(self) -> str | None:
        return self._msg_id

    @property
    def usage(self) -> TokenUsage | None:
        return None


class FixedChatProvider:
    """ChatProvider that returns fixed responses."""

    name = "fixed"

    def __init__(self, responses: list[list[Any]]) -> None:
        self._responses = responses
        self._index = 0

    @property
    def model_name(self) -> str:
        return "fixed-model"

    @property
    def thinking_effort(self) -> Any:
        return None

    async def generate(self, system_prompt: str, tools: Any, history: Any) -> StreamedMessage:
        if self._index < len(self._responses):
            parts = self._responses[self._index]
        else:
            parts = [TextPart(text="Done")]
        self._index += 1
        return FixedStreamedMessage(parts)

    def with_thinking(self, effort: Any) -> FixedChatProvider:
        return self


@pytest.mark.asyncio
async def test_custom_llm_fixed_text_response() -> None:
    provider = FixedChatProvider([[TextPart(text="Hello from fixed LLM")]])

    with tempfile.TemporaryDirectory() as tmpdir:
        work_dir = KaosPath.unsafe_from_local_path(Path(tmpdir))
        config_path = Path(tmpdir) / "config.toml"
        config_path.write_text(
            """
[loop_control]
max_steps_per_turn = 5
max_retries_per_step = 1
""",
            encoding="utf-8",
        )

        session = await _create_session_async(
            work_dir=work_dir,
            yolo=True,
            chat_provider=provider,
        )
        try:
            text_parts: list[str] = []
            async for msg in session.prompt("Say hello"):
                if isinstance(msg, TextPart):
                    text_parts.append(msg.text)
            print(text_parts)
            assert "Hello from fixed LLM" in " ".join(text_parts)
        finally:
            await session.close()


@pytest.mark.asyncio
async def test_custom_llm_fixed_tool_call() -> None:
    provider = FixedChatProvider(
        [
            [
                ToolCall(
                    id="call_001",
                    function=ToolCall.FunctionBody(
                        name="fake_tool",
                        arguments='{"arg": "value"}',
                    ),
                )
            ],
            [TextPart(text="Tool call completed")],
        ]
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        work_dir = KaosPath.unsafe_from_local_path(Path(tmpdir))
        config_path = Path(tmpdir) / "config.toml"
        config_path.write_text(
            """
[loop_control]
max_steps_per_turn = 5
max_retries_per_step = 1
""",
            encoding="utf-8",
        )

        session = await _create_session_async(
            work_dir=work_dir,
            yolo=True,
            chat_provider=provider,
        )
        try:
            tool_calls: list[ToolCall] = []
            text_parts: list[str] = []
            async for msg in session.prompt("Call a tool"):
                if isinstance(msg, ToolCall):
                    tool_calls.append(msg)
                elif isinstance(msg, TextPart):
                    text_parts.append(msg.text)
            print(tool_calls)
            assert len(tool_calls) >= 1
            assert tool_calls[0].function.name == "fake_tool"
            assert any("Tool call completed" in t for t in text_parts)
        finally:
            await session.close()


@pytest.mark.asyncio
async def test_custom_llm_read_file() -> None:
    test_file_path = str(Path(__file__).parent / "test_text.txt")
    provider = FixedChatProvider(
        [
            [
                ToolCall(
                    id="call_readfile",
                    function=ToolCall.FunctionBody(
                        name="ReadFile",
                        arguments=json.dumps({"path": test_file_path}),
                    ),
                )
            ],
            [TextPart(text="114514 1919810")],
        ]
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        work_dir = KaosPath.unsafe_from_local_path(Path(tmpdir))
        config_path = Path(tmpdir) / "config.toml"
        config_path.write_text(
            """
[loop_control]
max_steps_per_turn = 5
max_retries_per_step = 1
""",
            encoding="utf-8",
        )

        session = await _create_session_async(
            work_dir=work_dir,
            yolo=True,
            chat_provider=provider,
        )
        try:
            tool_calls: list[ToolCall] = []
            tool_results: list[ToolResult] = []
            text_parts: list[str] = []
            async for msg in session.prompt("Read the test file"):
                if isinstance(msg, ToolCall):
                    tool_calls.append(msg)
                elif isinstance(msg, ToolResult):
                    tool_results.append(msg)
                elif isinstance(msg, TextPart):
                    text_parts.append(msg.text)

            assert len(tool_calls) >= 1
            assert tool_calls[0].function.name == "ReadFile"
            assert len(tool_results) >= 1
            result_output = str(tool_results[0].return_value.output)
            print(result_output)
            assert any("114514" in t and "1919810" in t for t in text_parts)
        finally:
            await session.close()


if __name__ == "__main__":
    asyncio.run(test_custom_llm_fixed_text_response())
    asyncio.run(test_custom_llm_fixed_tool_call())
    asyncio.run(test_custom_llm_read_file())
