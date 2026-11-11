"""检索抽检工具（m2-runbook 2.8 验收；M3 被 hybrid 取代）。

10 条中文查询（清单版本化 scripts/probe_queries.json——data/ 被 gitignore，验收资产需入库，
收官时在 runbook 补记该路径变更）→ B 档稠密检索（text+table+caption）+ BM25 双路，
各打 top-5（回表取正文摘要）供人工判定"基本相关"。
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from doclens.index import qdrant_store as qs
from doclens.index import bm25 as B
from doclens.index.db import connect
from doclens.index.embeddings import EmbeddingClient

QUERY_FILE = Path(__file__).resolve().parent / "probe_queries.json"


def _lookup_contents(chunk_ids: list[str]) -> dict[str, dict]:
    """回表取正文摘要（t_chunk 单一事实源）。"""
    if not chunk_ids:
        return {}
    conn = connect()
    try:
        out: dict[str, dict] = {}
        with conn.cursor() as cur:
            ph = ",".join(["%s"] * len(chunk_ids))
            cur.execute(
                f"SELECT chunk_id, doc_id, kind, page, content FROM t_chunk WHERE chunk_id IN ({ph})",
                chunk_ids,
            )
            for cid, doc_id, kind, page, content in cur.fetchall():
                out[cid] = {"doc_id": doc_id, "kind": kind, "page": page,
                            "preview": " ".join((content or "").split())[:120]}
        return out
    finally:
        conn.close()


def _print_hits(title: str, hits: list[tuple[str, float]], meta: dict[str, dict]) -> None:
    print(f"  [{title}]")
    for i, (cid, score) in enumerate(hits, 1):
        m = meta.get(cid, {})
        print(f"   {i}. ({m.get('kind', '?')}) {score:.3f} {m.get('doc_id', '?')} p{m.get('page', '?')}｜{m.get('preview', '')}")


async def main() -> int:
    spec = json.loads(QUERY_FILE.read_text(encoding="utf-8"))
    queries = spec["queries"]
    print(f"探针 v{spec['version']}：{len(queries)} 条查询（B 档稠密 + BM25）")

    client = EmbeddingClient()
    qclient = qs._client()
    bm25_idx = B.load_index()
    try:
        for q in queries:
            print(f"\nQ: {q}")
            vec = await client.embed_query(q)
            hits = qs.search_tier(qclient, vec, tier="B", top=5)
            meta = _lookup_contents([p.payload["chunk_id"] for p in hits])
            _print_hits("稠密 B 档", [(p.payload["chunk_id"], p.score) for p in hits], meta)
            bm_hits = bm25_idx.search(q, top=5)
            bm_meta = _lookup_contents([cid for cid, _ in bm_hits])
            _print_hits("BM25", bm_hits, bm_meta)
    finally:
        qclient.close()
    print("\n[完成] 请人工判定 top-5 相关性（验收线：基本相关；表格召回一般≠失败，见 runbook 风险表）")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
