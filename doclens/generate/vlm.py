"""K5 生成（m3-runbook §3.4；调研 R9/R14）。

模型与思考适配（R9）：
- GLM-5.3-FLASH 为 thinking 型模型且**强制思考不可关闭**（官方文档）——本模块按
  "必有 reasoning_content"设计：**双字段分流**，思考内容只累计进 trace 统计
  （reasoning_chars / reasoning_text_head），**绝不混入答案**；正文只认
  content（非流式 message.content / 流式 delta.content）。
- 不向 5.3 系发送 thinking:disabled 参数（官方明示无效）。
- usage：流式下只有末 chunk 携带，取**最后一个出现 usage 的 chunk**（best-effort：
  GenResult 允许 None，M4 流式上线时若方舟缺 usage 再补 stream_options 开关）。
- TTFT：**正文首 token 口径**（首个 content 分片到达时刻-起始；调研 R9——思考
  阶段不算 TTFT，否则 NFR"首 token<5s"口径失真）。
- max_tokens=2048 默认（R9"从紧"口径：thinking 模型 completion 含思考 token，
  此值留给答案，M4 按需调）；temperature=0 生成稳定优先（引用任务）。

语言跟随（R14）：system prompt 要求与问题相同语言作答，专有名词/术语可留英文。

系统提示词为**固定前缀**（吃上下文缓存：所有请求一致，不拼任何动态内容），
三要素：只依据 Source / 每句行内引用 [n] / 语言跟随。

图片：bytes 由调用方（3.5 CLI）经 image_blobs 传入（本模块不读文件），编码为
data URL 后经 context.to_prompt_parts 拼入多模态 content 数组。
"""

from __future__ import annotations

import base64
import dataclasses
import time
from dataclasses import dataclass

from openai import AsyncOpenAI

from doclens.config import settings
from doclens.generate.context import AssembledContext, to_prompt_parts

# 固定前缀系统提示词（三要素 + 语言跟随；R11/R14）
SYSTEM_PROMPT = (
    "你是文档问答助手。规则："
    "1) 只依据所给 Source 作答，不使用外部知识；"
    "2) 每个答案句子至少引用一个 Source，行内标注形如 [1]，只用你实际引用的编号；"
    "3) 严格用与问题相同的语言作答（专有名词/术语可保留英文）。"
)

REASONING_HEAD_LIMIT = 200  # reasoning_text_head 截断长度（仅 trace 用）


@dataclass
class GenResult:
    """生成结果：answer 供后续引用解析；其余字段全部是 trace 统计。"""

    answer: str
    reasoning_chars: int              # 思考内容字符数（R9：思考只进 trace）
    reasoning_text_head: str          # 思考内容前 ≤200 字符（仅 trace 用）
    usage_tokens: int | None
    prompt_tokens: int | None
    ttft_ms: float | None             # 正文首 token 口径（R9）；非流式为 None
    total_ms: float
    model: str


def _data_url(blob: bytes, path: str) -> str:
    """bytes → data URL（图片 part）。mime 按后缀判：png → image/png，其余按 jpeg。"""
    mime = "image/png" if path.lower().endswith(".png") else "image/jpeg"
    return f"data:{mime};base64," + base64.b64encode(blob).decode("ascii")


def _usage_tokens(usage) -> tuple[int | None, int | None]:
    if usage is None:
        return None, None
    return getattr(usage, "total_tokens", None), getattr(usage, "prompt_tokens", None)


async def generate_answer(
    question: str,
    ctx: AssembledContext,
    *,
    image_blobs: dict[str, bytes] | None = None,
    stream: bool = False,
    max_tokens: int = 2048,
    timeout: float = 120.0,
    on_delta=None,
    model: str | None = None,
) -> GenResult:
    """调 gen_model（glm-5.3-flash）生成带引用的答案。

    question：显式参数优先于 ctx.question（两者不一致时以参为准）；
    image_blobs：image_path → 原图 bytes（读取归调用方；缺文件的图跳过不附）。
    on_delta：M4 流式事件钩子（仅 stream=True 时生效），签名 cb(kind, text)，
      kind ∈ ("reasoning", "content")——reasoning 只进该钩子（R5 双字段分流），
      绝不混入 answer。model：K12 覆盖位（None=settings.gen_model）。
    异常不在此吞——调用方决定重试/降级。
    """
    if question and question != ctx.question:
        ctx = dataclasses.replace(ctx, question=question)
    urls: dict[str, str] = {}
    for img in ctx.images:
        blob = (image_blobs or {}).get(img.image_path)
        if blob:
            urls[img.image_path] = _data_url(blob, img.image_path)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": to_prompt_parts(ctx, image_urls=urls)},
    ]
    model = model or settings.gen_model  # K12 覆盖位（None=默认）
    client = AsyncOpenAI(api_key=settings.ark_api_key, base_url=settings.ark_base_url)
    t0 = time.perf_counter()

    if stream:
        # ---- 流式（R9 双字段分流核心路径）----
        answer_parts: list[str] = []
        reasoning_parts: list[str] = []
        ttft_ms: float | None = None
        usage = None
        stream_obj = await client.chat.completions.create(
            model=model, messages=messages, stream=True,
            max_tokens=max_tokens, temperature=0, timeout=timeout,
        )
        async for chunk in stream_obj:
            u = getattr(chunk, "usage", None)
            if u is not None:
                usage = u  # usage 取最后一个携带它的 chunk（流式末 chunk 才有）
            choices = getattr(chunk, "choices", None) or []
            if not choices:
                continue  # 末尾纯 usage chunk 的 choices 为空
            delta = getattr(choices[0], "delta", None)
            if delta is None:
                continue
            reasoning = getattr(delta, "reasoning_content", None)
            if reasoning:
                # R9 分流：思考内容只累计进 trace，绝不进答案
                reasoning_parts.append(reasoning)
                if on_delta is not None:
                    on_delta("reasoning", reasoning)
            content = getattr(delta, "content", None)
            if content:
                if ttft_ms is None:
                    # 正文首 token 口径（R9）：思考阶段不算 TTFT
                    ttft_ms = (time.perf_counter() - t0) * 1000.0
                answer_parts.append(content)
                if on_delta is not None:
                    on_delta("content", content)
        answer_text = "".join(answer_parts)
        reasoning_text = "".join(reasoning_parts)
        usage_tokens, prompt_tokens = _usage_tokens(usage)
    else:
        # ---- 非流式（M3 主路径）----
        ttft_ms = None
        resp = await client.chat.completions.create(
            model=model, messages=messages,
            max_tokens=max_tokens, temperature=0, timeout=timeout,
        )
        message = resp.choices[0].message
        answer_text = getattr(message, "content", None) or ""
        reasoning_text = getattr(message, "reasoning_content", None) or ""
        usage_tokens, prompt_tokens = _usage_tokens(getattr(resp, "usage", None))

    total_ms = (time.perf_counter() - t0) * 1000.0
    return GenResult(
        answer=answer_text,
        reasoning_chars=len(reasoning_text),
        reasoning_text_head=reasoning_text[:REASONING_HEAD_LIMIT],
        usage_tokens=usage_tokens,
        prompt_tokens=prompt_tokens,
        ttft_ms=ttft_ms,
        total_ms=total_ms,
        model=model,
    )
