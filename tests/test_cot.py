"""Comprehensive tests for manual Chain-of-Thought (CoT) system."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock

import pytest

from kimix.cot import (
    CoTResult,
    _build_prompt,
    _parse_response,
    cot_prompt,
    cot_prompt_async,
    cot_prompt_with_verification,
    cot_prompt_with_verification_async,
)


class TestBuildPrompt:
    def test_basic_prompt(self) -> None:
        prompt = _build_prompt("What is 2+2?")
        assert "Think step by step" in prompt
        assert "<thinking>" in prompt
        assert "<answer>" in prompt
        assert "What is 2+2?" in prompt

    def test_self_verify_appended(self) -> None:
        prompt = _build_prompt("What is 2+2?", self_verify=True)
        assert "review your reasoning" in prompt
        assert "identify errors" in prompt

    def test_self_verify_false(self) -> None:
        prompt = _build_prompt("What is 2+2?", self_verify=False)
        assert "review your reasoning" not in prompt

    def test_existing_thinking(self) -> None:
        prior = "I think 2+2 = 4"
        prompt = _build_prompt("What is 2+2?", existing_thinking=prior)
        assert "Continue from the prior thinking" in prompt
        assert prior in prompt
        assert "<thinking>" in prompt

    def test_existing_thinking_and_self_verify(self) -> None:
        prior = "Initial thought"
        prompt = _build_prompt("Q", existing_thinking=prior, self_verify=True)
        assert "Continue from the prior thinking" in prompt
        assert "Initial thought" in prompt
        assert "review your reasoning" in prompt

    def test_prompt_strips_whitespace(self) -> None:
        prompt = _build_prompt("  hello  ", self_verify=False)
        assert prompt.endswith("hello")


class TestParseResponse:
    def test_full_tags(self) -> None:
        text = (
            "Some preamble\n"
            "<thinking>Step 1: add. Step 2: conclude.</thinking>\n"
            "<answer>4</answer>\n"
            "postamble"
        )
        result = _parse_response(text)
        assert result.thinking == "Step 1: add. Step 2: conclude."
        assert result.answer == "4"

    def test_missing_thinking(self) -> None:
        text = "<answer>42</answer>"
        result = _parse_response(text)
        assert result.thinking == ""
        assert result.answer == "42"

    def test_missing_answer(self) -> None:
        text = "<thinking>just thinking</thinking>"
        result = _parse_response(text)
        assert result.thinking == "just thinking"
        assert result.answer == ""

    def test_no_tags(self) -> None:
        text = "Plain text response"
        result = _parse_response(text)
        assert result.thinking == ""
        assert result.answer == "Plain text response"

    def test_case_insensitive_tags(self) -> None:
        text = "<THINKING>Upper</THINKING><Answer>Lower</Answer>"
        result = _parse_response(text)
        assert result.thinking == "Upper"
        assert result.answer == "Lower"

    def test_multiline_content(self) -> None:
        text = (
            "<thinking>\nLine 1\nLine 2\n</thinking>\n"
            "<answer>\nResult\n</answer>"
        )
        result = _parse_response(text)
        assert result.thinking == "Line 1\nLine 2"
        assert result.answer == "Result"

    def test_empty_tags(self) -> None:
        text = "<thinking></thinking><answer></answer>"
        result = _parse_response(text)
        assert result.thinking == ""
        assert result.answer == ""

    def test_only_whitespace_in_tags(self) -> None:
        text = "<thinking>   </thinking><answer>   </answer>"
        result = _parse_response(text)
        assert result.thinking == ""
        assert result.answer == ""


class TestCotPromptAsync:
    @pytest.mark.asyncio
    async def test_basic_async(self) -> None:
        async def callback(prompt: str) -> str:
            return (
                f"<thinking>received: {prompt[:20]}...</thinking>"
                f"<answer>done</answer>"
            )

        result = await cot_prompt_async("hello", llm_callback=callback)
        assert isinstance(result, CoTResult)
        assert "received:" in result.thinking
        assert result.answer == "done"

    @pytest.mark.asyncio
    async def test_self_verify_false(self) -> None:
        calls: list[str] = []

        async def callback(prompt: str) -> str:
            calls.append(prompt)
            return "<thinking>t</thinking><answer>a</answer>"

        result = await cot_prompt_async("q", llm_callback=callback, self_verify=False)
        assert "review your reasoning" not in calls[0]
        assert result.thinking == "t"

    @pytest.mark.asyncio
    async def test_self_verify_true(self) -> None:
        calls: list[str] = []

        async def callback(prompt: str) -> str:
            calls.append(prompt)
            return "<thinking>t</thinking><answer>a</answer>"

        await cot_prompt_async("q", llm_callback=callback, self_verify=True)
        assert "review your reasoning" in calls[0]

    @pytest.mark.asyncio
    async def test_existing_thinking_passed(self) -> None:
        async def callback(prompt: str) -> str:
            assert "Continue from the prior thinking" in prompt
            assert "old thought" in prompt
            return "<thinking>new</thinking><answer>new ans</answer>"

        result = await cot_prompt_async(
            "q", llm_callback=callback, existing_thinking="old thought"
        )
        assert result.thinking == "new"
        assert result.answer == "new ans"

    @pytest.mark.asyncio
    async def test_async_mock_callback(self) -> None:
        mock = AsyncMock(return_value="<thinking>t</thinking><answer>a</answer>")
        result = await cot_prompt_async("q", llm_callback=mock)
        mock.assert_awaited_once()
        assert result.thinking == "t"
        assert result.answer == "a"


class TestCotPromptSync:
    def test_basic_sync(self) -> None:
        def callback(prompt: str) -> str:
            return "<thinking>sync t</thinking><answer>sync a</answer>"

        result = cot_prompt("hello", llm_callback=callback)
        assert result.thinking == "sync t"
        assert result.answer == "sync a"

    def test_existing_thinking_sync(self) -> None:
        def callback(prompt: str) -> str:
            assert "Continue from the prior thinking" in prompt
            return "<thinking>t</thinking><answer>a</answer>"

        result = cot_prompt("q", llm_callback=callback, existing_thinking="prior")
        assert result.thinking == "t"

    def test_self_verify_sync(self) -> None:
        calls: list[str] = []

        def callback(prompt: str) -> str:
            calls.append(prompt)
            return "<thinking>t</thinking><answer>a</answer>"

        cot_prompt("q", llm_callback=callback, self_verify=True)
        assert "review your reasoning" in calls[0]


class TestCotPromptWithVerificationAsync:
    @pytest.mark.asyncio
    async def test_two_pass(self) -> None:
        calls: list[str] = []

        async def callback(prompt: str) -> str:
            calls.append(prompt)
            if len(calls) == 1:
                return "<thinking>first</thinking><answer>first ans</answer>"
            return "<thinking>second</thinking><answer>second ans</answer>"

        result = await cot_prompt_with_verification_async("q", llm_callback=callback)
        assert len(calls) == 2
        assert "first" in calls[1]
        assert result.thinking == "second"
        assert result.answer == "second ans"

    @pytest.mark.asyncio
    async def test_short_circuit_on_empty_thinking(self) -> None:
        calls: list[str] = []

        async def callback(prompt: str) -> str:
            calls.append(prompt)
            return "<answer>no thinking</answer>"

        result = await cot_prompt_with_verification_async("q", llm_callback=callback)
        assert len(calls) == 1
        assert result.thinking == ""
        assert result.answer == "no thinking"

    @pytest.mark.asyncio
    async def test_uses_existing_thinking(self) -> None:
        calls: list[str] = []

        async def callback(prompt: str) -> str:
            calls.append(prompt)
            return "<thinking>refined</thinking><answer>ok</answer>"

        result = await cot_prompt_with_verification_async(
            "q", llm_callback=callback, existing_thinking="prior"
        )
        assert "prior" in calls[0]
        assert result.thinking == "refined"


class TestCotPromptWithVerificationSync:
    def test_two_pass_sync(self) -> None:
        calls: list[str] = []

        def callback(prompt: str) -> str:
            calls.append(prompt)
            if len(calls) == 1:
                return "<thinking>init</thinking><answer>init ans</answer>"
            return "<thinking>final</thinking><answer>final ans</answer>"

        result = cot_prompt_with_verification("q", llm_callback=callback)
        assert len(calls) == 2
        assert result.thinking == "final"
        assert result.answer == "final ans"

    def test_short_circuit_sync(self) -> None:
        calls: list[str] = []

        def callback(prompt: str) -> str:
            calls.append(prompt)
            return "plain text no tags"

        result = cot_prompt_with_verification("q", llm_callback=callback)
        assert len(calls) == 1
        assert result.thinking == ""
        assert result.answer == "plain text no tags"


class TestEdgeCases:
    @pytest.mark.asyncio
    async def test_empty_response_async(self) -> None:
        async def callback(prompt: str) -> str:
            return ""

        result = await cot_prompt_async("q", llm_callback=callback)
        assert result.thinking == ""
        assert result.answer == ""

    def test_empty_response_sync(self) -> None:
        def callback(prompt: str) -> str:
            return ""

        result = cot_prompt("q", llm_callback=callback)
        assert result.thinking == ""
        assert result.answer == ""

    @pytest.mark.asyncio
    async def test_multiple_thinking_tags(self) -> None:
        """Only the first occurrence should be captured."""
        async def callback(prompt: str) -> str:
            return (
                "<thinking>first</thinking>"
                "<thinking>second</thinking>"
                "<answer>ans</answer>"
            )

        result = await cot_prompt_async("q", llm_callback=callback)
        assert result.thinking == "first"
        assert result.answer == "ans"

    @pytest.mark.asyncio
    async def test_multiple_answer_tags(self) -> None:
        async def callback(prompt: str) -> str:
            return (
                "<thinking>t</thinking>"
                "<answer>first</answer>"
                "<answer>second</answer>"
            )

        result = await cot_prompt_async("q", llm_callback=callback)
        assert result.thinking == "t"
        assert result.answer == "first"
