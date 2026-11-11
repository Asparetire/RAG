"""E 档块上下文前缀（m2-runbook 2.6；K7 / FR-2.6，Anthropic Contextual Retrieval 思路）。

设计：
- ctx_model（deepseek-v4-flash）读全文+chunk → 生成 50–100 token 语境前缀；
  嵌入与 BM25 **共用**该前缀（M5 消融时拼进两路索引）；
- 结果缓存 t_ctx_prefix（每 chunk 一条，幂等 upsert）；
- M2 只做模块 + 100 块分层抽样试产（text/table/caption 各取比例），全量 M5 按需生成；
- thinking 型模型兼容：非流式响应 content 为空时取 reasoning_content（M0 教训）。
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor

from openai import OpenAI

from doclens.config import settings
from doclens.index.db import connect

CTX_CONCURRENCY = 4
CTX_MAX_TOKENS = 200
CTX_PROMPT_TEMPLATE = (
    "以下是一篇论文中的一个块（chunk），以及它所属的全文标题与章节路径。"
    "请用不超过 100 个 token 的中文语境前缀描述这个块的上下文：它出现在论文的哪个部分、"
    "讨论什么主题、与全文的关系。只输出前缀本身，不要任何解释或引号。\n\n"
    "论文标题: {doc_title}\n章节路径: {heading}\n\n块内容:\n{chunk}"
)

# thinking 型模型兜底：content 为空时取 reasoning_content
def _answer_text(message) -> str:
    text = (getattr(message, "content", None) or "").strip()
    if text:
        return text
    return (getattr(message, "reasoning_content", None) or "").strip()


def _gen_one(client: OpenAI, doc_title: str, chunk: dict) -> str:
    """单块前缀生成（同步；线程池限并发）。"""
    heading = " / ".join(chunk.get("heading_path") or []) or "（无章节路径）"
    prompt = CTX_PROMPT_TEMPLATE.format(
        doc_title=doc_title, heading=heading, chunk=(chunk.get("content") or "")[:3000]
    )
    resp = client.chat.completions.create(
        model=settings.ctx_model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        max_tokens=CTX_MAX_TOKENS,
        timeout=90,
    )
    return _answer_text(resp.choices[0].message)


def _prefix_get_existing(chunk_ids: list[str]) -> set[str]:
    if not chunk_ids:
        return set()
    conn = connect()
    try:
        existing: set[str] = set()
        with conn.cursor() as cur:
            for i in range(0, len(chunk_ids), 500):
                batch = chunk_ids[i:i + 500]
                ph = ",".join(["%s"] * len(batch))
                cur.execute(f"SELECT chunk_id FROM t_ctx_prefix WHERE chunk_id IN ({ph})", batch)
                existing.update(r[0] for r in cur.fetchall())
        return existing
    finally:
        conn.close()


def _prefix_put_many(rows: list[tuple[str, str, str]]) -> None:
    if not rows:
        return
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO t_ctx_prefix (chunk_id, prefix, model) VALUES (%s, %s, %s) "
                "ON DUPLICATE KEY UPDATE prefix=VALUES(prefix), model=VALUES(model)",
                rows,
            )
        conn.commit()
    finally:
        conn.close()


async def generate_prefixes(doc_title: str, chunks: list[dict], *,
                            concurrency: int = CTX_CONCURRENCY) -> dict[str, str]:
    """为 chunks 生成前缀并落缓存（已有缓存且 model 相同的块跳过）。返回 chunk_id→prefix。

    chunks 元素：{chunk_id, content, heading_path}。
    """
    loop = asyncio.get_running_loop()
    client = OpenAI(api_key=settings.ark_api_key, base_url=settings.ark_base_url)
    existing = await loop.run_in_executor(None, _prefix_get_existing, [c["chunk_id"] for c in chunks])
    todo = [c for c in chunks if c["chunk_id"] not in existing]
    done: dict[str, str] = {}
    if todo:
        sem = asyncio.Semaphore(concurrency)

        async def run(c: dict) -> tuple[str, str]:
            async with sem:
                prefix = await loop.run_in_executor(None, _gen_one, client, doc_title, c)
                return c["chunk_id"], prefix

        results = await asyncio.gather(*(run(c) for c in todo))
        rows = [(cid, p, settings.ctx_model) for cid, p in results]
        await loop.run_in_executor(None, _prefix_put_many, rows)
        done.update(rows and {cid: p for cid, p in results})
    return done


def stratified_sample(units: list[dict], n: int = 100) -> list[dict]:
    """分层抽样（runbook §1 E 档试产口径）：text/table/caption 按各自占比分配名额。"""
    by_kind: dict[str, list[dict]] = {}
    for u in units:
        if u.get("kind") in ("text", "table", "caption") and (u.get("content") or "").strip():
            by_kind.setdefault(u["kind"], []).append(u)
    total = sum(len(v) for v in by_kind.values())
    if total <= n:
        return [u for v in by_kind.values() for u in v]
    picked: list[dict] = []
    allocated = {k: max(1, round(len(v) * n / total)) for k, v in by_kind.items()}
    # 修正取整误差：名额总和超过 n 时从最多的组削
    while sum(allocated.values()) > n:
        kmax = max(allocated, key=lambda k: allocated[k])
        allocated[kmax] -= 1
    while sum(allocated.values()) < n:
        kmin = min(allocated, key=lambda k: allocated[k])
        allocated[kmin] += 1
    for k, m in allocated.items():
        v = by_kind[k]
        step = max(1, len(v) // m)
        picked.extend(v[i * step] for i in range(m) if i * step < len(v))
    return picked[:n]
