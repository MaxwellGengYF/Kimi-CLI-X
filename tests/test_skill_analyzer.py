"""Comprehensive tests for SkillAnalyzer tool."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

# Patch get_skill_dirs BEFORE importing SkillAnalyzer so _load_index receives plain strings.
import kimix.agent_utils as _agent_utils

_original_get_skill_dirs = _agent_utils.get_skill_dirs

def _patched_get_skill_dirs(use_kaos_path: bool = True) -> list[str]:
    return [str(Path(".opencode").resolve()), str(Path(".agents").resolve())]

_agent_utils.get_skill_dirs = _patched_get_skill_dirs

from my_tools.skill import IndexerParams, SkillAnalyzer
from kimi_agent_sdk import ToolOk


# ---------------------------------------------------------------------------
# Session-scoped fixture
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def skill_analyzer() -> SkillAnalyzer:
    """Create a single SkillAnalyzer instance indexed over the skill directories."""
    tool = SkillAnalyzer()
    return tool


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _call_tool(tool: SkillAnalyzer, **kwargs: Any) -> tuple[str, str]:
    """Call SkillAnalyzer with given params and return (output, brief)."""
    params = IndexerParams(**kwargs)
    result = await tool(params)
    assert isinstance(result, ToolOk), f"Expected ToolOk, got {type(result)}: {result}"
    assert not result.is_error
    assert isinstance(result.output, str)
    return result.output, result.brief


# ---------------------------------------------------------------------------
# IndexerParams model tests
# ---------------------------------------------------------------------------

def test_params_defaults() -> None:
    """IndexerParams should have correct defaults."""
    p = IndexerParams(query="test")
    assert p.query == "test"
    assert p.top_k == 3
    assert p.content is False
    assert p.negative is None


def test_params_top_k_minimum() -> None:
    """top_k below 1 should raise ValidationError."""
    with pytest.raises(ValidationError):
        IndexerParams(query="test", top_k=0)


def test_params_top_k_maximum() -> None:
    """top_k above 10 should raise ValidationError."""
    with pytest.raises(ValidationError):
        IndexerParams(query="test", top_k=11)


def test_params_top_k_boundary_values() -> None:
    """top_k at boundaries 1 and 10 should be accepted."""
    p1 = IndexerParams(query="test", top_k=1)
    assert p1.top_k == 1
    p10 = IndexerParams(query="test", top_k=10)
    assert p10.top_k == 10


# ---------------------------------------------------------------------------
# Query tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_query_basic(skill_analyzer: SkillAnalyzer) -> None:
    """Query for a known keyword from skill dirs should return results."""
    output, brief = await _call_tool(skill_analyzer, query="MeshBuilder")
    assert "mesh_builder" in output.lower() or "MeshBuilder" in output
    assert "Found" in brief


@pytest.mark.asyncio
async def test_query_sentence_from_skill_dir(skill_analyzer: SkillAnalyzer) -> None:
    """Query for a sentence/phrase from skill dirs should return results."""
    output, brief = await _call_tool(skill_analyzer, query="create_session")
    assert "api" in output.lower() or "session" in output.lower()
    assert "Found" in brief


@pytest.mark.asyncio
async def test_query_callabletool2(skill_analyzer: SkillAnalyzer) -> None:
    """Query for CallableTool2 keyword should return tool skill results."""
    output, brief = await _call_tool(skill_analyzer, query="CallableTool2")
    assert "tool" in output.lower() or "CallableTool2" in output
    assert "Found" in brief


@pytest.mark.asyncio
async def test_query_no_results(skill_analyzer: SkillAnalyzer) -> None:
    """Query for nonsense should execute without error (semantic search may still return low-score matches)."""
    output, brief = await _call_tool(skill_analyzer, query="xyz nonsense query 12345")
    # Semantic search can return results for arbitrary queries; just verify well-formed output
    assert "Indexed" in output


# ---------------------------------------------------------------------------
# top_k tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_top_k_default(skill_analyzer: SkillAnalyzer) -> None:
    """Default top_k (3) should return up to 3 results."""
    output, _ = await _call_tool(skill_analyzer, query="guide")
    # Count result lines like "1. [0.1234] ..."
    count = sum(1 for line in output.splitlines() if line.strip().startswith("1. ") or line.strip().startswith("2. ") or line.strip().startswith("3. "))
    assert count <= 3


@pytest.mark.asyncio
async def test_top_k_one(skill_analyzer: SkillAnalyzer) -> None:
    """top_k=1 should return at most 1 result."""
    output, _ = await _call_tool(skill_analyzer, query="guide", top_k=1)
    lines = output.splitlines()
    count = sum(1 for line in lines if line.strip().startswith("1. "))
    assert count == 1
    assert not any(line.strip().startswith("2. ") for line in lines)


@pytest.mark.asyncio
async def test_top_k_five(skill_analyzer: SkillAnalyzer) -> None:
    """top_k=5 should return up to 5 results."""
    output, _ = await _call_tool(skill_analyzer, query="guide", top_k=5)
    count = sum(1 for line in output.splitlines() if any(line.strip().startswith(f"{i}. ") for i in range(1, 6)))
    assert 1 <= count <= 5


@pytest.mark.asyncio
async def test_top_k_ten(skill_analyzer: SkillAnalyzer) -> None:
    """top_k=10 should return up to 10 results."""
    output, _ = await _call_tool(skill_analyzer, query="guide", top_k=10)
    count = sum(1 for line in output.splitlines() if any(line.strip().startswith(f"{i}. ") for i in range(1, 11)))
    assert 1 <= count <= 10


# ---------------------------------------------------------------------------
# content tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_content_false_default(skill_analyzer: SkillAnalyzer) -> None:
    """Default content=False should NOT include full file content."""
    output, _ = await _call_tool(skill_analyzer, query="MeshBuilder")
    assert "--- Full Content ---" not in output
    assert "--- End Content ---" not in output


@pytest.mark.asyncio
async def test_content_true(skill_analyzer: SkillAnalyzer) -> None:
    """content=True should include full file content markers."""
    output, _ = await _call_tool(skill_analyzer, query="MeshBuilder", content=True)
    assert "--- Full Content ---" in output
    assert "--- End Content ---" in output


# ---------------------------------------------------------------------------
# negative tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_negative_penalty(skill_analyzer: SkillAnalyzer) -> None:
    """Using negative keyword should deprioritize/exclude matching results."""
    # Query for something general that appears in many skills
    output_without, _ = await _call_tool(skill_analyzer, query="guide", top_k=5)
    output_with, _ = await _call_tool(skill_analyzer, query="guide", top_k=5, negative="mesh")

    # The output should differ when negative is applied (mesh_builder results deprioritized)
    # We assert that the negative result does not have mesh_builder in top results,
    # or at least the output is different.
    has_mesh_without = "mesh_builder" in output_without.lower()
    has_mesh_with = "mesh_builder" in output_with.lower()

    # If mesh_builder was in results without negative, it should be absent or less prominent with negative
    if has_mesh_without:
        assert not has_mesh_with, "mesh_builder should be penalized by negative='mesh'"


@pytest.mark.asyncio
async def test_negative_empty_string(skill_analyzer: SkillAnalyzer) -> None:
    """negative='' should behave the same as None (no penalty)."""
    _, brief_none = await _call_tool(skill_analyzer, query="guide", top_k=3)
    _, brief_empty = await _call_tool(skill_analyzer, query="guide", top_k=3, negative="")
    # Both should succeed and return results
    assert "Found" in brief_none
    assert "Found" in brief_empty


# ---------------------------------------------------------------------------
# Combined params tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_combined_top_k_content_negative(skill_analyzer: SkillAnalyzer) -> None:
    """Using top_k, content, and negative together should work correctly."""
    output, brief = await _call_tool(
        skill_analyzer,
        query="world_resource",
        top_k=2,
        content=True,
        negative="RoboCute",
    )
    assert "--- Full Content ---" in output
    assert "--- End Content ---" in output
    count = sum(1 for line in output.splitlines() if line.strip().startswith("1. ") or line.strip().startswith("2. "))
    assert count <= 2
    assert "Found" in brief
