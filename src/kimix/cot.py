"""Manually Chain-of-Thought (CoT) system.

Wraps an LLM callback with explicit reasoning instructions,
parses structured <thinking>/<answer> output, and supports
self-verification and continuation from prior reasoning.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from typing import Awaitable, Callable, Optional


@dataclass
class CoTResult:
    """Result of a manual CoT prompt."""

    thinking: str
    answer: bool
    quit: bool = False


_COT_SYSTEM = (
    "Think step by step. "
    "Write your current reasoning inside <thinking>...</thinking> tags. "
    "If you need more reasoning, output only <thinking>...</thinking> and the system will prompt you again. "
    "When you are ready, write your final answer inside <answer>...</answer> tags. "
    "If you decide to stop without answering, write <quit/>. "
    "Be concise. No preamble outside the tags."
)

_VERIFY_SUFFIX = (
    "\n\nBefore answering, review your reasoning: identify errors, "
    "omissions, or bad assumptions. Correct them, then finalize."
)

_CONTINUE_PREFIX = (
    "Continue from the prior thinking below. Verify, refine, then answer.\n\n"
    "<thinking>\n{thinking}\n</thinking>"
)


def _build_prompt(
    user_prompt: str,
    existing_thinking: Optional[str] = None,
    self_verify: bool = False,
) -> str:
    parts: list[str] = []
    if existing_thinking is not None:
        parts.append(_CONTINUE_PREFIX.format(thinking=existing_thinking.strip()))
    parts.append(_COT_SYSTEM)
    parts.append(user_prompt.strip())
    prompt = "\n\n".join(parts)
    if self_verify:
        prompt += _VERIFY_SUFFIX
    return prompt


_THINKING_RE = re.compile(r"<thinking>(.*?)</thinking>", re.DOTALL | re.IGNORECASE)
_QUIT_RE = re.compile(r"<quit\s*/?>", re.IGNORECASE)


def _parse_response(text: str) -> CoTResult:
    thinking_match = _THINKING_RE.search(text)
    quit_match = _QUIT_RE.search(text)
    thinking = thinking_match.group(1).strip() if thinking_match else ""
    answer = text.find('<answer>') >= 0 and text.find('</answer>') >= 0
    return CoTResult(thinking=thinking, answer=answer, quit=bool(quit_match))


async def cot_prompt_async(
    prompt_str: str,
    llm_callback: Callable[[str], Awaitable[str]],
    self_verify: bool = True,
    existing_thinking: Optional[str] = None,
    max_iterations: int = 10,
) -> CoTResult:
    """Run manual CoT with an async LLM callback.

    The callback is invoked in a loop until the model produces an
    ``<answer>`` block, emits ``<quit/>``, or ``max_iterations`` is reached.

    Parameters
    ----------
    prompt_str:
        The user prompt.
    llm_callback:
        Async callable that takes a prompt string and returns the raw LLM response.
    self_verify:
        If True, append a self-verification instruction to each prompt.
    existing_thinking:
        If provided, ask the model to continue from this prior thinking.
    max_iterations:
        Maximum number of LLM calls before forcing a return.
    """
    accumulated: list[str] = []
    if existing_thinking is not None:
        accumulated.append(existing_thinking.strip())

    for _ in range(max_iterations):
        prompt = _build_prompt(
            prompt_str,
            "\n\n".join(accumulated) if accumulated else None,
            self_verify,
        )
        raw = await llm_callback(prompt)
        result = _parse_response(raw)

        if result.thinking:
            accumulated.append(result.thinking)

        if result.quit or result.answer:
            return CoTResult(
                thinking="\n\n".join(accumulated),
                answer=result.answer,
                quit=result.quit,
            )

    return CoTResult(thinking="\n\n".join(accumulated), answer="", quit=False)


def cot_prompt(
    prompt_str: str,
    llm_callback: Callable[[str], str],
    self_verify: bool = True,
    existing_thinking: Optional[str] = None,
    max_iterations: int = 10,
) -> CoTResult:
    """Synchronous version of :func:`cot_prompt_async`.

    Parameters
    ----------
    prompt_str:
        The user prompt.
    llm_callback:
        Sync callable that takes a prompt string and returns the raw LLM response.
    self_verify:
        If True, append a self-verification instruction to each prompt.
    existing_thinking:
        If provided, ask the model to continue from this prior thinking.
    max_iterations:
        Maximum number of LLM calls before forcing a return.
    """
    accumulated: list[str] = []
    if existing_thinking is not None:
        accumulated.append(existing_thinking.strip())

    for _ in range(max_iterations):
        prompt = _build_prompt(
            prompt_str,
            "\n\n".join(accumulated) if accumulated else None,
            self_verify,
        )
        raw = llm_callback(prompt)
        result = _parse_response(raw)

        if result.thinking:
            accumulated.append(result.thinking)

        if result.quit or result.answer:
            return CoTResult(
                thinking="\n\n".join(accumulated),
                answer=result.answer,
                quit=result.quit,
            )

    return CoTResult(thinking="\n\n".join(accumulated), answer=False, quit=False)


async def cot_prompt_with_verification_async(
    prompt_str: str,
    llm_callback: Callable[[str], Awaitable[str]],
    existing_thinking: Optional[str] = None,
) -> CoTResult:
    """Two-pass CoT: generate reasoning, then verify and refine.

    First pass runs without self-verify to get initial thinking.
    Second pass feeds the thinking back as ``existing_thinking`` with verification enabled.
    """
    first = await cot_prompt_async(
        prompt_str,
        llm_callback,
        self_verify=False,
        existing_thinking=existing_thinking,
    )
    if not first.thinking:
        return first
    second = await cot_prompt_async(
        prompt_str,
        llm_callback,
        self_verify=True,
        existing_thinking=first.thinking,
    )
    return second


def cot_prompt_with_verification(
    prompt_str: str,
    llm_callback: Callable[[str], str],
    existing_thinking: Optional[str] = None,
) -> CoTResult:
    """Synchronous two-pass CoT with verification."""
    first = cot_prompt(
        prompt_str,
        llm_callback,
        self_verify=False,
        existing_thinking=existing_thinking,
    )
    if not first.thinking:
        return first
    second = cot_prompt(
        prompt_str,
        llm_callback,
        self_verify=True,
        existing_thinking=first.thinking,
    )
    return second
