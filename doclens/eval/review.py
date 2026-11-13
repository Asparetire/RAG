"""M5 AI 复审（m5-runbook K6 前奏；judge 校准纪律的第一次实践）。

分工：出题模型（glm）出题 → 复审 judge（ctx_model=deepseek，与出题模型分离防自偏好）
→ pass/uncertain/reject 三桶；uncertain 进"待人工裁决"队列。

复审三判：①题目清晰无歧义 ②ref_answer 与证据原文事实一致 ③有唯一合理解。
"""

from __future__ import annotations

import json
import re

from openai import AsyncOpenAI

from doclens.config import settings

_REVIEW_PROMPT = (
    "你是 RAG 评测题集的质量审查员。下面是一道评测题及其标注的证据原文。\n"
    "请审查三项：\n"
    "1) 题目是否清晰无歧义（能否明确理解在问什么）；\n"
    "2) ref_answer 是否与证据原文事实一致（无编造、无矛盾）；\n"
    "3) 是否有唯一合理解（不是开放式/观点题）。\n\n"
    "只输出一个 JSON 对象："
    '{"verdict": "pass|uncertain|reject", "confidence": 0.0到1.0, "reason": "一句话理由"}\n'
    "- pass：三项都满足；\n"
    "- uncertain：你不确定（如题目涉及证据无法确认的专业细节、或 ref_answer 与证据"
    "部分吻合但无法完全判定）——交人工裁决；\n"
    "- reject：题目有硬伤（歧义/ref_answer 与证据矛盾/开放式问题）。\n"
    "graph 类题的'看图才能答'是预期行为（证据含图表），不作为 reject 理由。"
)


async def review_question(question: str, ref_answer: str, gold_contents: list[str],
                          q_type: str = "text") -> dict:
    """AI 复审一道题（ctx_model；返回 verdict dict）。"""
    evidence = "\n\n".join(f"[证据 {i + 1}]\n{c[:1200]}" for i, c in enumerate(gold_contents))
    prompt = (
        f"{_REVIEW_PROMPT}\n\n"
        f"[题目类型] {q_type}\n"
        f"[题目] {question}\n\n"
        f"[参考答案] {ref_answer}\n\n"
        f"[证据原文]\n{evidence}"
    )
    client = AsyncOpenAI(api_key=settings.ark_api_key, base_url=settings.ark_base_url)
    resp = await client.chat.completions.create(
        model=settings.ctx_model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0, max_tokens=300, timeout=60)
    raw = (resp.choices[0].message.content or "").strip()
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.M)
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", raw, re.S)
        obj = json.loads(m.group(0)) if m else {}
    verdict = obj.get("verdict", "uncertain")
    if verdict not in ("pass", "uncertain", "reject"):
        verdict = "uncertain"
    try:
        conf = max(0.0, min(1.0, float(obj.get("confidence", 0.5))))
    except (TypeError, ValueError):
        conf = 0.5
    return {"verdict": verdict, "confidence": conf,
            "reason": str(obj.get("reason", ""))[:200]}
