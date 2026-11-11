"""LLM 列表式重排（m3-runbook 3.2 / K2，调研 R7/R8/R9/R10）。

职责：
- 融合池候选 → 列表式提示词 → LLM 输出编号序列 → 三级解析链 → chunk_id 有序表；
- 失败降级（R8）：可重试异常重试 1 次（退避 1s）→ 回调用方传入序（=RRF 序）+ degraded=True；
  解析全废（无任何可用编号）同样回原序 + degraded=True；
- 结果缓存 t_rerank_cache（R10）：键 = sha256(model+max_tokens+候选指纹+question)，
  temperature=0 不保证确定（实证），同键必回同一 ranking——可复现 + M5 消融复跑不重复计费。

设计依据（specs/research/m3-retrieval-generation-survey.md 修订号）：
- R7  三级解析链照抄 RankGPT 官方 rank_gpt.py 语义（清洗→去重→越界过滤+缺失补尾），函数注释逐级标来源；
- R8  预算：输入截 30 由调用方负责（融合池 top-50 截 30）；每候选截 300 词（RankGPT
      max_length=300 官方先例）；超时默认 5s + 重试 1 次 → 回 RRF 序 + degraded 标记；
      pro 档级联只重排 flash 已排 top-15（cascade_input 纯函数，编排归 3.5 CLI）；
- R9  glm-5.3-flash 强制思考不可关（官方）——解析只认 message.content，绝不读 reasoning_content
      （思考过程不是答案）；max_tokens 从紧 512 起步（RankGPT 官方 64@5 候选、30 候选放宽，
      思考 token 另占额度——实测调参位）；
- R10 temperature=0 不保证确定性 → 结果缓存兜底（含 degraded 位）。

openai 调用选型：**同步 OpenAI + asyncio.to_thread**（PyMySQL 同款纪律）。
理由：① 项目既有纪律是"同步库一律 to_thread 包裹"（db.py/embeddings.py 先例），
事件循环不被阻塞即可直接复用；② M0 冒烟 smoke_test.test_llm_rerank 已实测同步客户端可用，
AsyncOpenAI 属项目首例、引入第二套客户端配置面收益低；③ 每查询仅 1 次重排调用，线程开销可忽略。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time
from dataclasses import dataclass

from openai import APIConnectionError, APITimeoutError, OpenAI, RateLimitError

from doclens.config import settings
from doclens.index.db import connect

RETRY_BACKOFF_S = 1.0  # R8：重试 1 次、短退避 1s——检索在等它，长退避拖爆延迟预算
CONTENT_WORDS = 300    # R8：每候选正文截 300 词（RankGPT max_length=300 官方先例，按空白切词计）

# R8 可重试异常：超时/网络/限流（APITimeoutError 是 APIConnectionError 子类）。
# 其余（鉴权/参数错等）重试无意义，首次即降级。
_RETRYABLE = (APITimeoutError, APIConnectionError, RateLimitError)


@dataclass
class Candidate:
    """重排候选（hybrid.py 回表产物；heading_path 以 t_chunk 的 JSON 数组为主，str/None 防御兼容）。"""

    chunk_id: str
    doc_id: str
    page: int
    kind: str
    heading_path: list[str] | str | None
    content: str


@dataclass
class RerankOutcome:
    """重排结果（字段即 3.5 trace.rerank 的取数来源，m3-runbook §3.1）。

    fail_reason 只描述**本次调用**的失败；缓存命中不回填历史原因（cache_hit 已可追溯）。
    """

    ranking: list[str]        # 重排后 chunk_id 有序列表；degraded 时 = 调用方传入序（RRF 序）
    degraded: bool            # True = LLM 失败或解析全废，已回原序（R8，降级率入验收）
    model: str                # 实际使用的方舟模型名（flash/pro 档解析后）
    latency_ms: float         # 端到端耗时（缓存读写 + LLM 调用 + 重试）
    usage_tokens: int | None  # LLM total_tokens；缓存命中/调用失败为 None
    cache_hit: bool           # 命中 t_rerank_cache
    fail_reason: str | None   # 降级原因（trace 用）；本次成功为 None


# ---------- 三级解析链（R7：照抄 RankGPT 官方 rank_gpt.py 语义） ----------

def clean_response(text: str) -> list[int]:
    """第一级·清洗：所有非数字字符替换成空格，再按空白切分取整数。

    RankGPT 官方 clean_response() 返回清洗后的字符串、调用侧再 split()；
    此处按 3.2 规格合并为一步直接返回整数列表。天然滤掉解释文字/Markdown 残渣
    （"[2] > [1]"、"Answer: 2, 1" 均只剩数字）。负号处理：RankGPT 用 negative
    正则过滤负数，此处按规格简化为只收非负整数 token（int() 失败的跳过）——
    负号本身属非数字字符，清洗后已被替换为空格，与官方语义一致。
    """
    out: list[int] = []
    for token in re.sub(r"\D", " ", text or "").split():
        try:
            n = int(token)
        except ValueError:
            continue
        if n >= 0:
            out.append(n)
    return out


def remove_duplicate(values: list[int]) -> list[int]:
    """第二级·去重：保留首次出现（RankGPT 官方 remove_duplicate() 语义；set 加速不改序）。"""
    seen: set[int] = set()
    out: list[int] = []
    for v in values:
        if v not in seen:
            seen.add(v)
            out.append(v)
    return out


def receive_permutation(raw_order: list[int], candidates: list[str]) -> list[str]:
    """第三级·落位：1-based 编号 → chunk_id，越界/0/负数丢弃，缺失候选按原序补到尾部。

    RankGPT 官方 receive_permutation() 用候选标注 [1]..[n]（1-based 惯例），先 -1 转
    0-based 再过滤越界；此处直接以 1 <= i <= n 对位 candidates[i-1]，语义相同。
    raw_order 为空（模型没给出任何编号）时全部候选视为"缺失"原序补齐——解析链本身就是兜底。
    注意：本函数不做去重（去重是第二级的职责，调用须走 remove_duplicate 先行）。
    """
    n = len(candidates)
    ordered = [candidates[i - 1] for i in raw_order if 1 <= i <= n]
    seen = set(ordered)
    ordered.extend(c for c in candidates if c not in seen)
    return ordered


def parse_ranking(text: str, chunk_ids: list[str]) -> list[str]:
    """三级串联：清洗→去重→越界过滤+补尾；全废（结果为空）→ 原顺序兜底。"""
    perm = receive_permutation(remove_duplicate(clean_response(text)), chunk_ids)
    return perm if perm else list(chunk_ids)


# ---------- 提示词（列表式，措辞出处见 PROMPT_HEADER 注释） ----------

PROMPT_HEADER = (
    "你是检索重排器。根据与 Query 的相关性对候选块排序。\n"
    "只输出从最相关到最不相关的编号序列，形如 [2,1,...]，不要解释，不要输出任何其他文字。"
)
# 措辞来源：RankGPT 官方 rank_gpt.py system prompt（"rank passages based on their relevancy
# to the query / Output only ... without any other explanation"）的项目中文转写，
# m3-runbook §3.1 既定文案；自由文本编号序列而非 JSON 模式（K2：JSON 格式约束损害推理【20】）。


def truncate_words(text: str, limit: int = CONTENT_WORDS) -> str:
    """按空白切词取前 limit 词（R8：RankGPT max_length=300 先例；中文按空白切词口径同款）。"""
    return " ".join((text or "").split()[:limit])


def _heading_str(heading_path: list[str] | str | None) -> str:
    """heading_path → " / ".join（t_chunk.heading_path 为 JSON 数组；str/None 防御兼容）。"""
    if not heading_path:
        return ""
    if isinstance(heading_path, str):
        return heading_path.strip()
    return " / ".join(str(h).strip() for h in heading_path if str(h).strip())


def build_prompt(question: str, candidates: list[Candidate]) -> str:
    """列表式提示词：header + Query 行 + 候选行 `[i] (doc_id,page,kind) heading_path / 正文前 300 词`。"""
    lines = [PROMPT_HEADER, "", f"Query: {question}", "", "候选块:"]
    for i, c in enumerate(candidates, 1):
        head = f"[{i}] ({c.doc_id},{c.page},{c.kind})"  # 1-based（RankGPT 惯例）
        heading = _heading_str(c.heading_path)
        body = (
            f"{head} {heading} / {truncate_words(c.content)}"
            if heading
            else f"{head} / {truncate_words(c.content)}"
        )
        lines.append(body)
    return "\n".join(lines)


# ---------- 结果缓存 t_rerank_cache（R10；读写模式照 embeddings._cache_get_many/_cache_put_many） ----------

def rerank_cache_key(model: str, max_tokens: int, question: str, candidates: list[Candidate]) -> str:
    """缓存键 = sha256(model + str(max_tokens) + 每候选(chunk_id+正文前300词) + question)。

    候选内容变/模型变/问题变/参数变 → 键变，不串缓存；候选指纹只取前 300 词与提示词
    截断口径一致。\\x00 分隔防拼接歧义（embeddings.cache_key 同款纪律）。
    """
    h = hashlib.sha256()
    parts: list[str] = [model, str(max_tokens)]
    parts.extend(f"{c.chunk_id}\x00{truncate_words(c.content)}" for c in candidates)
    parts.append(question)
    for part in parts:
        h.update(part.encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()


def _cache_get(key: str) -> dict | None:
    """同步读缓存（asyncio.to_thread 内执行）；未命中返回 None。pymysql + try/finally close（embeddings 同款）。"""
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT model, n_candidates, ranking, degraded "
                "FROM t_rerank_cache WHERE cache_key = %s",
                (key,),
            )
            row = cur.fetchone()
    finally:
        conn.close()
    if not row:
        return None
    return {
        "model": row[0],
        "n_candidates": row[1],
        "ranking": json.loads(row[2]),  # JSON 列经 pymysql 返回 str
        "degraded": bool(row[3]),
    }


def _cache_put(key: str, model: str, n_candidates: int, ranking: list[str], degraded: bool) -> None:
    """同步写缓存（asyncio.to_thread 内执行）；幂等 ON DUPLICATE KEY UPDATE（embeddings 同款）。

    degraded 结果同样落缓存（R10：缓存的是"该键的最终结果"——M5 消融复跑口径一致、可复现；
    代价是瞬时故障结果被固定，键内 model/params 可失效重建）。
    """
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO t_rerank_cache (cache_key, model, n_candidates, ranking, degraded) "
                "VALUES (%s, %s, %s, %s, %s) "
                "ON DUPLICATE KEY UPDATE model=VALUES(model), n_candidates=VALUES(n_candidates), "
                "ranking=VALUES(ranking), degraded=VALUES(degraded)",
                (key, model, n_candidates, json.dumps(ranking, ensure_ascii=False), 1 if degraded else 0),
            )
        conn.commit()
    finally:
        conn.close()


# ---------- LLM 调用（R9：只认 content） ----------

def _chat_once(prompt: str, model: str, *, timeout: float, max_tokens: int):
    """单次方舟 chat 调用（同步 OpenAI，asyncio.to_thread 内执行；选型理由见模块 docstring）。

    client 即建即关 + max_retries=0：重试策略收敛到 rerank_candidates（R8 恰好 1 次），
    不与 SDK 内建重试叠乘（否则超时场景总耗时 = (1+SDK重试)×2 次调用，爆 5s 预算）。
    """
    client = OpenAI(api_key=settings.ark_api_key, base_url=settings.ark_base_url, max_retries=0)
    try:
        return client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,           # R10：不保证确定，结果靠缓存固定
            max_tokens=max_tokens,   # 512 起步（RankGPT 64@5 候选、30 候选放宽；R9 思考 token
                                     # 另占额度，max_tokens 从紧——实测调参位）
            timeout=timeout,         # R8：默认 5s（检索在等）
        )
    finally:
        client.close()


def _resolve_model(model_tier: str) -> str:
    """model_tier → 方舟模型名（settings 双档）；未知档位早失败（编程错误，不进降级路径）。"""
    if model_tier == "flash":
        return settings.rerank_model_flash
    if model_tier == "pro":
        return settings.rerank_model_pro
    raise ValueError(f"未知 model_tier: {model_tier!r}（只支持 'flash' / 'pro'）")


async def rerank_candidates(
    question: str,
    candidates: list[Candidate],
    *,
    model_tier: str = "flash",
    timeout: float = 5.0,
    max_tokens: int = 512,
    use_cache: bool = True,
) -> RerankOutcome:
    """重排融合池候选（m3-runbook 3.2 / K2）。

    流程：缓存（R10）→ 未命中调 LLM（R9 解析只认 content）→ 三级解析链（R7）。
    失败降级（R8）：APITimeoutError/APIConnectionError/RateLimitError 重试 1 次（退避 1s），
    再失败 → 回调用方传入序（=RRF 序）+ degraded=True + fail_reason；
    解析"全废"（清洗去重后没有任何落在候选范围内的编号：含无数字与全部越界）→ 同样回原序 + degraded。
    """
    t0 = time.perf_counter()
    model = _resolve_model(model_tier)
    original_ids = [c.chunk_id for c in candidates]

    def _done(**kw) -> RerankOutcome:
        return RerankOutcome(
            latency_ms=round((time.perf_counter() - t0) * 1000, 1), model=model, **kw
        )

    if not candidates:  # 空池：无需调用也不落缓存
        return _done(ranking=[], degraded=False, usage_tokens=None, cache_hit=False, fail_reason=None)

    key = rerank_cache_key(model, max_tokens, question, candidates)
    if use_cache:
        hit = await asyncio.to_thread(_cache_get, key)
        if hit is not None:
            return _done(
                ranking=list(hit["ranking"]), degraded=bool(hit["degraded"]),
                usage_tokens=None, cache_hit=True, fail_reason=None,
            )

    prompt = build_prompt(question, candidates)

    resp = None
    last_exc: Exception | None = None
    for attempt in (1, 2):  # R8：初次 + 重试 1 次
        try:
            resp = await asyncio.to_thread(
                _chat_once, prompt, model, timeout=timeout, max_tokens=max_tokens
            )
            break
        except _RETRYABLE as exc:  # 超时/网络/限流：短退避后重试一次
            last_exc = exc
            if attempt == 1:
                await asyncio.sleep(RETRY_BACKOFF_S)
        except Exception as exc:  # 鉴权/参数错等：重试无意义，直接降级（不掩盖——原因入 fail_reason）
            last_exc = exc
            break

    if resp is None:
        reason = f"{type(last_exc).__name__}: {last_exc}" if last_exc else "LLM 调用失败"
        return _done(
            ranking=original_ids, degraded=True, usage_tokens=None,
            cache_hit=False, fail_reason=reason,
        )

    # R9：解析只认 content——reasoning_content 是思考过程（强制思考模型必有），绝不读
    content = resp.choices[0].message.content or ""
    usage = getattr(resp.usage, "total_tokens", None) if resp.usage is not None else None

    # R7 三级解析链；"全废"判定与 parse_ranking 同链（前两级）：
    # usable 为空 = 模型输出没有任何可用编号（无数字或全部越界）→ 回原序 + degraded。
    raw_ids = remove_duplicate(clean_response(content))
    usable = [i for i in raw_ids if 1 <= i <= len(candidates)]
    ranking = parse_ranking(content, original_ids)
    degraded = not usable

    outcome = _done(
        ranking=ranking, degraded=degraded, usage_tokens=usage, cache_hit=False,
        fail_reason="模型输出无可用编号（解析全废），回原顺序" if degraded else None,
    )
    if use_cache:  # degraded 位也缓存（R10，见 _cache_put 注）
        await asyncio.to_thread(_cache_put, key, model, len(candidates), ranking, degraded)
    return outcome


# ---------- pro 档级联辅助（R8；编排归 3.5 CLI，本模块不做 flash→pro 调度） ----------

def cascade_input(candidates: list[Candidate], top: int = 15) -> list[Candidate]:
    """取 flash 已排序列表前 top 个交 pro 重排（保持原序控预算）；top<=0 返回空。"""
    if top <= 0:
        return []
    return list(candidates[:top])
