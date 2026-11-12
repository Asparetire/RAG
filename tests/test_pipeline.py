"""K7 空答案守卫单测（m4-runbook 4.0；2026-11-12 冒烟 A 档 s01 观察项闭环）。

背景：glm-5.3-flash 强制思考可能耗尽 max_tokens——实测 A 档 s01 reasoning 6932
字符、content 空（usage 5297 = prompt 3249 + completion 2048）。守卫语义：
空 → 重试一次（max_tokens 上调一档）→ 仍空 → REFUSAL_TEXT + empty_content=True。
"""

from __future__ import annotations

import asyncio

from doclens.config import settings
from doclens.generate.fallback import REFUSAL_TEXT
from doclens.generate.vlm import GenResult
from doclens.pipeline import _generate_with_guard


def _gen(answer: str) -> GenResult:
    return GenResult(answer=answer, reasoning_chars=0, reasoning_text_head="",
                     usage_tokens=10, prompt_tokens=100, ttft_ms=None,
                     total_ms=1.0, model="test-model")


def test_guard_valid_first_no_retry():
    """首次生成即有效：不重试，empty_content=False。"""
    calls: list[int] = []

    async def gen_fn(max_tokens: int) -> GenResult:
        calls.append(max_tokens)
        return _gen("答案 [1]")

    gen, empty = asyncio.run(_generate_with_guard(gen_fn))
    assert gen.answer == "答案 [1]"
    assert empty is False
    assert calls == [settings.gen_max_tokens]


def test_guard_retry_then_success():
    """首次空（纯空白也算空）→ 重试一次（max_tokens 上调）→ 成功。"""
    calls: list[int] = []
    answers = ["   \n  ", "重试后的答案 [1]"]

    async def gen_fn(max_tokens: int) -> GenResult:
        calls.append(max_tokens)
        return _gen(answers[len(calls) - 1])

    gen, empty = asyncio.run(_generate_with_guard(gen_fn))
    assert gen.answer == "重试后的答案 [1]"
    assert empty is False
    assert calls == [settings.gen_max_tokens, settings.gen_max_tokens_retry]
    assert calls[1] > calls[0]


def test_guard_refuse_after_retry():
    """重试后仍空 → REFUSAL_TEXT + empty_content=True（trace 标记由调用方落）。"""
    calls: list[int] = []

    async def gen_fn(max_tokens: int) -> GenResult:
        calls.append(max_tokens)
        return _gen("")  # 空 content（reasoning 耗尽 max_tokens 的实测形态）

    gen, empty = asyncio.run(_generate_with_guard(gen_fn))
    assert gen.answer == REFUSAL_TEXT
    assert empty is True
    assert len(calls) == 2  # 恰好重试一次，不无限重试


def test_guard_whitespace_only_is_empty():
    """纯空白 content 视同空（.strip() 口径）。"""
    calls: list[int] = []

    async def gen_fn(max_tokens: int) -> GenResult:
        calls.append(max_tokens)
        return _gen("\n\t  " if len(calls) == 1 else "正文")

    gen, empty = asyncio.run(_generate_with_guard(gen_fn))
    assert gen.answer == "正文"
    assert empty is False
    assert len(calls) == 2
