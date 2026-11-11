"""K7 无依据兜底（m3-runbook §3.4；调研 R6/R13）。

三道防线分工（R11/R13）：
1. judge 上下文充分性判定（默认 ctx_model；Sufficient Context 先例 93% 准确）——主机制；
2. 检索观测（log-only）：**检索分数不进决策（R6）**——dense/BM25/融合分均不可
   跨查询比较，任何全局分数阈值必错；分数只在 trace 里观测；
3. prompt "只依据 Source 作答/无依据明确声明" + self_check——第三道，不作主机制。

保守方向（R13，**先压误拒**）：judge 调用失败/输出解析失败时**默认放行**
（sufficient=True）——误拒（把能答的题判成"库里没有依据"）直接丢掉用户问题，
伤害大于误放（误放还有 prompt 第三道与引用自检兜底）。调参纪律：20 冒烟题
先压误拒 ≤1/16，再提拒答率（拒答/误拒矩阵入报告）。

弃答输出 = REFUSAL_TEXT（固定话术，m3-runbook §3.1）+ 空引用 + trace 标记
（REFUSAL_TEXT 的落盘/输出由 3.5 CLI 决定，本模块只提供常量与决策）。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from openai import AsyncOpenAI

from doclens.config import settings
from doclens.generate.citations import parse_citations
from doclens.generate.context import AssembledContext, to_prompt_parts

REFUSAL_TEXT = "根据现有文档库，未能找到足以回答该问题的依据。"

JUDGE_PROMPT = (
    "你是检索问答系统的上下文充分性判定器。请判断：仅凭给定的 Source 上下文"
    "（不使用任何外部知识）能否回答用户问题。\n"
    "注意：Source 中可能包含表格的文本化表示（markdown 表格、列名/行名清单）或图片的"
    "图注（caption）文字——它们就是对应表格/图片的证据本体，只要其中含有回答问题"
    "所需的信息即视为充分，不要因为'看不到原始图表'而判为不充分。\n"
    '只输出一个 JSON 对象，不要解释、不要代码块围栏：'
    '{"sufficient": true 或 false, "reason": "一句话理由"}'
)

JUDGE_MAX_TOKENS = 200  # 一句话理由足够（judge 输出从紧）


@dataclass
class JudgeVerdict:
    """judge 判定结果。judge_ok=False 表示调用/解析失败（此时 sufficient 恒为 True 放行）。"""

    sufficient: bool
    reason: str
    judge_ok: bool = True


@dataclass
class FallbackDecision:
    """兜底决策：refused=True 时调用方输出 REFUSAL_TEXT + 空引用 + trace 标记。"""

    refused: bool
    reason: str


def _parse_judge_json(raw: str) -> dict | None:
    """宽容解析 judge 输出：裸 JSON / ```json 围栏 / 文本中夹带 JSON 均可。"""
    text = (raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", text).strip()
    obj = None
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.DOTALL)  # 容错：抓首尾大括号之间的 JSON
        if m:
            try:
                obj = json.loads(m.group(0))
            except json.JSONDecodeError:
                return None
    if not isinstance(obj, dict) or not isinstance(obj.get("sufficient"), bool):
        return None
    reason = obj.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        reason = "上下文充分" if obj["sufficient"] else "上下文不充分"
    return {"sufficient": obj["sufficient"], "reason": reason}


async def judge_sufficiency(
    question: str,
    ctx: AssembledContext,
    *,
    model: str | None = None,
    timeout: float = 30.0,
) -> JudgeVerdict:
    """判"所给上下文是否足以回答问题"（默认 settings.ctx_model，纯文本上下文，不带图）。

    失败方向（R13）：任何调用失败/解析失败 → sufficient=True 放行（judge_ok=False），
    理由见模块 docstring。
    """
    model = model or settings.ctx_model
    context_text = to_prompt_parts(ctx)[0]["text"]
    user = f"{JUDGE_PROMPT}\n\n{context_text}"
    try:
        client = AsyncOpenAI(api_key=settings.ark_api_key, base_url=settings.ark_base_url)
        resp = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": user}],
            temperature=0,
            max_tokens=JUDGE_MAX_TOKENS,
            timeout=timeout,
        )
        raw = (getattr(resp.choices[0].message, "content", None) or "").strip()
    except Exception:  # noqa: BLE001 任何异常都走放行（R13 保守方向）
        return JudgeVerdict(sufficient=True, reason="judge 调用失败默认放行", judge_ok=False)
    parsed = _parse_judge_json(raw)
    if parsed is None:
        return JudgeVerdict(sufficient=True, reason="judge 失败默认放行（输出解析失败）",
                            judge_ok=False)
    return JudgeVerdict(sufficient=parsed["sufficient"], reason=parsed["reason"], judge_ok=True)


def decide_fallback(
    question: str,
    ctx: AssembledContext,
    judge: JudgeVerdict | None,
    *,
    force_refuse: bool = False,
) -> FallbackDecision:
    """兜底决策（纯函数，无 IO）。

    - judge.sufficient=False → 拒答；
    - judge None / judge 失败（judge_ok=False）→ 放行（R13 先压误拒）；
    - force_refuse 仅供测试注入。
    - **检索分数不进决策（R6）**：dense/BM25/融合分均不可跨查询比较，全局阈值必错；
      分数只入 trace 观测。question/ctx 保留在签名里供 trace 与未来扩展，当前逻辑只依赖 judge。
    """
    if force_refuse:
        return FallbackDecision(refused=True, reason="force_refuse（测试注入）")
    if judge is None:
        return FallbackDecision(refused=False, reason="无 judge 结果，放行")
    if not judge.sufficient:
        return FallbackDecision(refused=True, reason=judge.reason or "上下文不充分")
    return FallbackDecision(refused=False, reason=judge.reason or "上下文充分，放行")


def self_check(answer: str, ctx: AssembledContext) -> bool:
    """生成后引用自检（R11 第三道，只判不罚）。

    通过条件：答案里至少有一个有效 [n] 引用，**且**引用的 n 全部在 ctx.sources
    范围内（出现任一无效编号即判 False——引用幻觉留给调用方降级处置，如换档
    重试/追加无依据声明；本模块不重写答案）。
    """
    valid = {s.source_n for s in ctx.sources}
    report = parse_citations(answer, valid)
    return bool(report.has_any and report.cited and not report.degraded_sentences)
