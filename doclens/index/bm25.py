"""BM25 索引（m2-runbook 2.5；K6 rank-bm25 + jieba，D5 既定）。

设计：
- 分词：jieba.lcut 中英通吃 + 小写化（英文靠 jieba 按空格/词边界切，小写归一）；
- 落盘：data/bm25/（**分词语料 pickle** + chunk 元数据 jsonl）——BM25Okapi 对象不可 extend
  （IDF 随语料重算），增量 = 从 t_chunk/t_ctx 源加载语料重建索引（~1500 块秒级，§3.1 增量语义）；
- 检索：get_top_n 风格返回 (chunk_id, score) 降序；查询同分词管线。
"""

from __future__ import annotations

import json
import pickle
from dataclasses import dataclass
from pathlib import Path

import jieba

from doclens.config import DATA_DIR

BM25_DIR = DATA_DIR / "bm25"
CORPUS_PICKLE = BM25_DIR / "corpus.pkl"      # list[list[str]] 分词后的 chunk 语料
META_JSONL = BM25_DIR / "chunks.jsonl"       # 每行 {chunk_id, kind, page, doc_id}（与语料同序）


def tokenize(text: str) -> list[str]:
    """查询/文档统一分词：jieba 切词 → 小写 → 去纯空白 token。"""
    return [t.lower() for t in jieba.lcut(text) if t.strip()]


@dataclass
class Bm25Index:
    chunk_ids: list[str]
    corpus: list[list[str]]
    bm25: object = None  # BM25Okapi（懒构建）

    def build(self) -> "Bm25Index":
        from rank_bm25 import BM25Okapi

        self.bm25 = BM25Okapi(self.corpus) if self.corpus else None
        return self

    def search(self, query: str, top: int = 20) -> list[tuple[str, float]]:
        """返回 (chunk_id, score) 降序 top-n；空索引/空查询返回 []。"""
        if self.bm25 is None or not self.chunk_ids:
            return []
        q = tokenize(query)
        if not q:
            return []
        scores = self.bm25.get_scores(q)
        pairs = sorted(zip(self.chunk_ids, scores), key=lambda x: -x[1])
        return [(cid, float(s)) for cid, s in pairs[:top] if s > 0]


def build_index(units: list[dict]) -> Bm25Index:
    """从单元清单构建索引（units: {chunk_id, content, ...}；kind=image 的空 content 自然退化为弱项）。

    索引范围 = 文本可检索单元（text/table/caption；image 单元无正文不进 BM25，runbook §1 验收口径
    "BM25 索引含全部文本单元"）。
    """
    usable = [u for u in units if u.get("kind") in ("text", "table", "caption") and (u.get("content") or "").strip()]
    idx = Bm25Index(
        chunk_ids=[u["chunk_id"] for u in usable],
        corpus=[tokenize(u["content"]) for u in usable],
    ).build()
    return idx


def save_index(idx: Bm25Index, meta_rows: list[dict] | None = None) -> None:
    """落盘：分词语料 pickle + chunk 元数据 jsonl（同序）。"""
    BM25_DIR.mkdir(parents=True, exist_ok=True)
    with CORPUS_PICKLE.open("wb") as f:
        pickle.dump({"chunk_ids": idx.chunk_ids, "corpus": idx.corpus}, f, protocol=pickle.HIGHEST_PROTOCOL)
    rows = meta_rows if meta_rows is not None else [
        {"chunk_id": cid} for cid in idx.chunk_ids
    ]
    with META_JSONL.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def load_index(rebuild: bool = False) -> Bm25Index:
    """加载落盘索引；rebuild=True 或文件缺失 → 空索引（调用方重建）。

    pickle 信任边界（S4-04 纪律）：corpus.pkl 仅由本脚本 save_index 产出、随 data/ 不入库、
    不接受外部文件——若将来需要外部交换语料，改用 JSON 明文格式。
    """
    if rebuild or not CORPUS_PICKLE.exists():
        return Bm25Index(chunk_ids=[], corpus=[])
    data = pickle.loads(CORPUS_PICKLE.read_bytes())
    return Bm25Index(chunk_ids=data["chunk_ids"], corpus=data["corpus"]).build()


def load_units_from_db(doc_ids: list[str] | None = None) -> list[dict]:
    """从 t_chunk 读文本单元（重建式增量的语料源——单一事实源，§3.1）。"""
    from doclens.index.db import connect

    conn = connect()
    try:
        with conn.cursor() as cur:
            if doc_ids:
                ph = ",".join(["%s"] * len(doc_ids))
                cur.execute(
                    f"SELECT chunk_id, doc_id, kind, content FROM t_chunk "
                    f"WHERE kind IN ('text','table','caption') AND doc_id IN ({ph})",
                    doc_ids,
                )
            else:
                cur.execute(
                    "SELECT chunk_id, doc_id, kind, content FROM t_chunk "
                    "WHERE kind IN ('text','table','caption')"
                )
            return [{"chunk_id": r[0], "doc_id": r[1], "kind": r[2], "content": r[3]}
                    for r in cur.fetchall()]
    finally:
        conn.close()
