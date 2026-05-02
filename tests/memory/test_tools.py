"""Tests for memory tools using CallableTool2 pattern."""

import os

import pytest

from kimix.memory.tools import (
    Remember,
    Recall,
    GetContext,
    Reflect,
    _get_memory_system,
)
from kimix.memory.system import AgentMemorySystem


@pytest.fixture(autouse=True)
def reset_memory_system():
    """Reset global memory system before each test."""
    import kimix.memory.tools as tools_mod
    tools_mod._memory_system = None
    # Remove default memory file if it exists
    if os.path.exists("agent_memory.json"):
        os.unlink("agent_memory.json")
    yield
    tools_mod._memory_system = None
    if os.path.exists("agent_memory.json"):
        os.unlink("agent_memory.json")


class TestRememberTool:
    @pytest.mark.asyncio
    async def test_remember_long_term(self):
        tool = Remember()
        result = await tool(Remember.params(content="test fact", importance=8.0, tier="long_term"))
        assert not result.is_error
        assert "Remembered" in result.output

    @pytest.mark.asyncio
    async def test_remember_short_term(self):
        tool = Remember()
        result = await tool(Remember.params(content="test observation", importance=5.0, tier="short_term"))
        assert not result.is_error
        assert "Perceived" in result.output

    @pytest.mark.asyncio
    async def test_remember_empty_content(self):
        tool = Remember()
        result = await tool(Remember.params(content="", importance=5.0))
        assert not result.is_error
        assert "Remembered" in result.output


class TestRecallTool:
    @pytest.mark.asyncio
    async def test_recall(self):
        tool = Recall()
        # First remember something in long-term
        remember = Remember()
        await remember(Remember.params(content="recall me", tier="long_term"))
        result = await tool(Recall.params(query="recall"))
        assert "recall me" in result.output

    @pytest.mark.asyncio
    async def test_recall_empty(self):
        tool = Recall()
        result = await tool(Recall.params(query="nonexistent"))
        assert result.output == "No memories found."


class TestGetContext:
    @pytest.mark.asyncio
    async def test_get_context(self):
        tool = GetContext()
        remember = Remember()
        await remember(Remember.params(content="python programming", tier="short_term"))
        result = await tool(GetContext.params(query="python"))
        assert "python" in result.output.lower()


class TestReflect:
    @pytest.mark.asyncio
    async def test_reflect(self):
        tool = Reflect()
        remember = Remember()
        await remember(Remember.params(content="test", tier="short_term"))
        result = await tool(Reflect.params())
        assert "Memory System Status Report" in result.output
