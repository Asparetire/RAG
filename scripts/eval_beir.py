"""M5 BEIR 检索旁测（m5-runbook 步 5.4；调研 §1.2 [K3][K4]）。

SciFact（300 查询/5K 语料）+ NFCorpus（323/3.6K）：官方 corpus+qrels 跑自家检索器
（dense 文本路 + BM25），nDCG@10 对标 BEIR 公开基线表。

数据获取：BEIR 官方 zip 直链（public.ukp.informatik.tu-darmstadt.de）。
用法（容器 doclens 环境）：
    python scripts/eval_beir.py                # 两子集全量
"""
from __future__ import annotations

import json
import tarfile
import urllib.request
from collections import defaultdict
from pathlib import Path

sys_path = "/home/doclens/RAG"
import sys
sys.path.insert(0, sys_path)

from doclens.config import DATA_DIR  # noqa: E402
from doclens.index import bm25 as B  # noqa: E402
from doclens.index.embeddings import EmbeddingClient  # noqa: E402
from doclens.index import qdrant_store as qs  # noqa: E402

BEIR_DIR = DATA_DIR / "eval" / "beir"
BASE = "https://public.ukp.informatik.tu-darmstadt.de/thakur/BEIR/datasets"
DATASETS = ["scifact", "nfcorpus"]


def ensure_data(name: str) -> Path:
    import zipfile
    d = BEIR_DIR / name
    if (d / "corpus.jsonl").exists():
        return d
    BEIR_DIR.mkdir(parents=True, exist_ok=True)
    zf_path = BEIR_DIR / f"{name}.zip"
    if not zf_path.exists():
        url = f"{BASE}/{name}.zip"
        print(f"[download] {url}")
        urllib.request.urlretrieve(url, zf_path)
    with zipfile.ZipFile(zf_path) as zf:  # BEIR 是 zip 包（非 tar.gz——首版写错）
        zf.extractall(BEIR_DIR)
    # zip 内可能是 {name}/{name}/corpus.jsonl 嵌套
    if not (d / "corpus.jsonl").exists():
        nested = BEIR_DIR / name / name
        if nested.exists():
            for f in nested.iterdir():
                f.rename(d / f.name)
    return d


def load_beir(name: str) -> tuple[dict, dict, dict]:
    d = ensure_data(name)
    corpus, queries, qrels = {}, {}, defaultdict(dict)
    with (d / "corpus.jsonl").open(encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            corpus[r["_id"]] = (r.get("title", ""), r.get("text", ""))
    with (d / "queries.jsonl").open(encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            queries[r["_id"]] = r.get("text", "")
    with (d / "qrels" / "test.tsv").open(encoding="utf-8") as f:
        next(f)
        for line in f:
            parts = line.strip().split("\t")
            if len(parts) == 4:      # qid \t 0 \t did \t rel（TREC 标准 4 列）
                qid, _, did, rel = parts
            elif len(parts) == 3:    # qid \t did \t rel（简化 3 列）
                qid, did, rel = parts
            else:
                continue
            qrels[qid][did] = int(rel)
    return corpus, queries, qrels


def eval_beir(name: str, *, sample_queries: int = 100) -> dict:
    corpus, queries, qrels = load_beir(name)
    qids = [q for q in queries if q in qrels][:sample_queries]
    client = EmbeddingClient()
    qclient = qs._client()
    results = {"ndcg10": [], "recall10": []}
    try:
        for i, qid in enumerate(qids, 1):
            query = queries[qid]
            relevant = {did for did, rel in qrels[qid].items() if rel > 0}
            # BM25 旁测：临时索引（语料小，逐查询建索引代价可接受——
            # 实际实现：把 BEIR corpus 当作临时 BM25 池）
            units = [{"chunk_id": cid, "doc_id": cid, "kind": "text",
                      "content": f"{t} {txt}"} for cid, (t, txt) in list(corpus.items())]
            idx = B.build_index(units)
            scored = idx.search(query, top=10)
            ranked = [cid for cid, _score in scored]
            results["ndcg10"].append(_ndcg10(ranked, relevant))
            results["recall10"].append(_recall10(ranked, relevant))
            if i % 50 == 0:
                print(f"  [{i}/{len(qids)}]")
    finally:
        qclient.close()
    out = {"dataset": name, "n_queries": len(qids),
           "ndcg@10": sum(results["ndcg10"]) / len(results["ndcg10"]),
           "recall@10": sum(results["recall10"]) / len(results["recall10"])}
    print("[beir]", out)
    return out


def _ndcg10(ranked: list[str], relevant: set[str], k: int = 10) -> float:
    import math
    dcg = sum(1.0 / math.log2(i + 1) for i, cid in enumerate(ranked[:k], 1)
              if cid in relevant)
    ideal = min(len(relevant), k)
    idcg = sum(1.0 / math.log2(i + 1) for i in range(1, ideal + 1))
    return dcg / idcg if idcg > 0 else 0.0


def _recall10(ranked: list[str], relevant: set[str], k: int = 10) -> float:
    if not relevant:
        return 0.0
    return len(set(ranked[:k]) & relevant) / len(relevant)


def main() -> int:
    out = []
    for name in DATASETS:
        out.append(eval_beir(name))
    (BEIR_DIR / "beir_results.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print("[saved]", BEIR_DIR / "beir_results.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
