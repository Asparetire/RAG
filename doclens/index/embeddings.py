"""嵌入客户端 + MySQL 缓存（m2-runbook 2.3；K3 单条并发 + K4 缓存先行）。

端点：ARK /embeddings/multimodal（M0 冒烟已验：coding/v3 放行、2048 维、
data 字典/数组双格式兼容——沿用 smoke_test 已验证的请求结构）。
并发：asyncio + httpx，单条请求、并发 4（K3），指数退避重试 3 次；
DB 读写经 asyncio.to_thread 包裹（PyMySQL 同步库，§3.1 实现注意）。
缓存：t_embed_cache，键 = sha256(model+instruction+dim+content)——
模型/指令/维度全纳入键，换模型不串缓存（严格优于 LangChain 默认键，调研 §3）。
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import struct
from pathlib import Path

import httpx

from doclens.config import (
    CORPUS_IMAGE_INSTRUCTION,
    CORPUS_TEXT_INSTRUCTION,
    settings,
)
from doclens.index.db import connect

CONCURRENCY = 4
RETRIES = 3
BACKOFF_BASE = 2.0   # 指数退避：2s / 4s / 8s
TIMEOUT = 60.0


class EmbedError(RuntimeError):
    """嵌入调用最终失败（重试耗尽）。"""


def cache_key(model: str, instruction: str, dim: int, content: str) -> str:
    """缓存键：模型/指令/维度/内容全纳入（sha256 hex 小写）。"""
    h = hashlib.sha256()
    for part in (model, instruction, str(dim), content):
        h.update(part.encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()


def vec_to_bytes(vec: list[float]) -> bytes:
    """float32 小端打包（2048 维 = 8KB）。"""
    return struct.pack(f"<{len(vec)}f", *vec)


def bytes_to_vec(blob: bytes) -> list[float]:
    return list(struct.unpack(f"<{len(blob) // 4}f", blob))


def _cache_get_many(keys: list[str]) -> dict[str, list[float]]:
    """同步查缓存（to_thread 内执行）；命中返回 key→向量。"""
    if not keys:
        return {}
    conn = connect()
    try:
        found: dict[str, list[float]] = {}
        with conn.cursor() as cur:
            for i in range(0, len(keys), 500):  # IN 分批
                batch = keys[i:i + 500]
                ph = ",".join(["%s"] * len(batch))
                cur.execute(
                    f"SELECT cache_key, vec FROM t_embed_cache WHERE cache_key IN ({ph})", batch
                )
                for k, blob in cur.fetchall():
                    found[k] = bytes_to_vec(blob)
        return found
    finally:
        conn.close()


def _cache_put_many(rows: list[tuple[str, str, str, int, bytes]]) -> None:
    """同步写缓存（to_thread 内执行）；幂等 ON DUPLICATE KEY UPDATE。"""
    if not rows:
        return
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO t_embed_cache (cache_key, model, kind, dim, vec) "
                "VALUES (%s, %s, %s, %s, %s) "
                "ON DUPLICATE KEY UPDATE vec=VALUES(vec), model=VALUES(model)",
                rows,
            )
        conn.commit()
    finally:
        conn.close()


def _extract_embedding(body: dict) -> list[float]:
    """响应双格式兼容（M0 教训：data 可能是 dict 或数组）。"""
    data = body.get("data")
    if isinstance(data, list) and data:
        vec = data[0].get("embedding")
    elif isinstance(data, dict):
        vec = data.get("embedding")
    else:
        vec = None
    if not vec:
        raise EmbedError(f"响应里找不到 embedding 向量，键: {list(body.keys())}")
    return vec


class EmbeddingClient:
    """异步嵌入客户端：embed_texts / embed_image_files（缓存先行，未命中才调 API）。"""

    def __init__(self, *, concurrency: int = CONCURRENCY) -> None:
        self._sem = asyncio.Semaphore(concurrency)
        base = (settings.ark_embed_base_url or settings.ark_base_url).rstrip("/")
        self._url = f"{base}/embeddings/multimodal"
        self._headers = {"Authorization": f"Bearer {settings.ark_api_key}"}

    async def _post_one(self, client: httpx.AsyncClient, item: dict) -> list[float]:
        """单条请求（信号量限并发）+ 指数退避重试。

        可重试：网络错误（httpx.HTTPError）、429/5xx；
        不可重试：其余 4xx（鉴权/参数错误，直接抛出）。
        """
        last: Exception | None = None
        for attempt in range(1, RETRIES + 1):
            try:
                async with self._sem:
                    resp = await client.post(
                        self._url,
                        headers=self._headers,
                        json={"model": settings.embed_model, "input": [item]},
                        timeout=TIMEOUT,
                    )
                if resp.status_code == 200:
                    return _extract_embedding(resp.json())
                if resp.status_code in (429, 500, 502, 503, 504):
                    last = EmbedError(f"HTTP {resp.status_code}: {resp.text[:200]}")
                else:
                    raise EmbedError(f"HTTP {resp.status_code}: {resp.text[:300]}")
            except httpx.HTTPError as exc:  # 网络错误：可重试
                last = exc
            if attempt < RETRIES:
                await asyncio.sleep(BACKOFF_BASE ** attempt)
        raise EmbedError(f"重试 {RETRIES} 次后仍失败：{last}") from last

    async def _embed_batch(self, jobs: list[dict]) -> list[list[float]]:
        """jobs: [{cache_key, item}] → 按序返回向量（缓存命中优先）。"""
        keys = [j["cache_key"] for j in jobs]
        cached = await asyncio.to_thread(_cache_get_many, keys)
        missing = [j for j, k in zip(jobs, keys) if k not in cached]
        fetched: dict[str, list[float]] = {}
        if missing:
            async with httpx.AsyncClient() as client:
                results = await asyncio.gather(
                    *(self._post_one(client, j["item"]) for j in missing),
                    return_exceptions=True,
                )
            rows = []
            for j, r in zip(missing, results):
                if isinstance(r, BaseException):
                    raise EmbedError(f"嵌入失败 [{j['cache_key'][:12]}…]: {r}") from r
                fetched[j["cache_key"]] = r
                rows.append((j["cache_key"], settings.embed_model, j["kind"], len(r),
                             vec_to_bytes(r)))
            await asyncio.to_thread(_cache_put_many, rows)
        return [cached.get(k) or fetched[k] for k in keys]

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """批量文本嵌入（缓存先行）。texts 顺序 = 返回顺序。"""
        jobs = [
            {"cache_key": cache_key(settings.embed_model, CORPUS_TEXT_INSTRUCTION,
                                    settings.embed_dimensions, t),
             "kind": "text",
             "item": {"type": "text", "text": t, "instructions": CORPUS_TEXT_INSTRUCTION}}
            for t in texts
        ]
        return await self._embed_batch(jobs)

    async def embed_image_files(self, paths: list[Path]) -> list[list[float]]:
        """批量图像嵌入（单图单请求 base64 data URL，D3 既定）。"""
        jobs = []
        for p in paths:
            b64 = await asyncio.to_thread(lambda fp: base64.b64encode(Path(fp).read_bytes()).decode(), p)
            data_url = f"data:image/{p.suffix.lstrip('.').lower()};base64,{b64}"
            jobs.append({
                "cache_key": cache_key(settings.embed_model, CORPUS_IMAGE_INSTRUCTION,
                                       settings.embed_dimensions, data_url),
                "kind": "image",
                "item": {"type": "image_url", "image_url": {"url": data_url}},
            })
        return await self._embed_batch(jobs)
