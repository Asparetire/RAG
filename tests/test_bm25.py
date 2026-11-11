"""bm25 单测（m2-runbook 2.5）：中英混合分词/查询命中、落盘往返、重建式增量、空索引防御。"""
from doclens.index import bm25 as B


def make_units():
    return [
        {"chunk_id": "d:0000", "kind": "text", "content": "Evolutionary algorithms optimize multilevel image thresholding efficiently."},
        {"chunk_id": "d:0001", "kind": "text", "content": "演化算法在多阈值图像分割中表现优异，实验验证了收敛性。"},
        {"chunk_id": "d:0002", "kind": "table", "content": "| Method | PSNR | BF | HS | 峰值信噪比对比 |"},
        {"chunk_id": "d:0003", "kind": "caption", "content": "Fig. 1 | Accuracy curve across rounds."},
        {"chunk_id": "d:0004", "kind": "image", "content": ""},  # image 单元不进 BM25
    ]


def test_tokenize_mixed_language():
    toks = B.tokenize("Evolutionary 演化算法 ABC-123")
    assert "evolutionary" in toks and "abc" in toks and "123" in toks
    assert any("演化" in t or "算法" in t for t in toks)
    assert all(t == t.lower() for t in toks)


def test_build_and_search_english_chinese():
    idx = B.build_index(make_units())
    assert idx.bm25 is not None
    assert len(idx.chunk_ids) == 4  # image 单元排除
    # 英文查询命中英文块
    hits = idx.search("multilevel thresholding", top=5)
    assert hits and hits[0][0] == "d:0000"
    # 中文查询命中中文块
    hits_zh = idx.search("演化算法 图像分割 收敛", top=5)
    assert hits_zh and hits_zh[0][0] == "d:0001"
    # 表格 markdown 词命中表格块
    hits_t = idx.search("PSNR 峰值信噪比", top=5)
    assert any(cid == "d:0002" for cid, _ in hits_t)


def test_save_load_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(B, "BM25_DIR", tmp_path)
    monkeypatch.setattr(B, "CORPUS_PICKLE", tmp_path / "corpus.pkl")
    monkeypatch.setattr(B, "META_JSONL", tmp_path / "chunks.jsonl")
    idx = B.build_index(make_units())
    B.save_index(idx, meta_rows=[{"chunk_id": c, "kind": "text"} for c in idx.chunk_ids])
    loaded = B.load_index()
    assert loaded.chunk_ids == idx.chunk_ids
    hits = loaded.search("multilevel thresholding", top=5)
    assert hits and hits[0][0] == "d:0000"


def test_rebuild_style_increment(tmp_path, monkeypatch):
    """重建式增量：语料追加后重建，新文档可命中、IDF 随语料重算（BM25Okapi 不可 extend 的正确替代）。"""
    monkeypatch.setattr(B, "BM25_DIR", tmp_path)
    monkeypatch.setattr(B, "CORPUS_PICKLE", tmp_path / "corpus.pkl")
    monkeypatch.setattr(B, "META_JSONL", tmp_path / "chunks.jsonl")
    B.save_index(B.build_index(make_units()))
    before = B.load_index()
    assert all(cid != "d:0005" for cid in before.chunk_ids)
    # "增量"：语料清单追加一行后整体重建
    units = make_units() + [{"chunk_id": "d:0005", "kind": "text", "content": "Quantum annealing beats genetic algorithms on TSP."}]
    after = B.build_index(units)
    assert after.search("quantum annealing TSP", top=3)[0][0] == "d:0005"


def test_empty_index_and_empty_query_defense():
    empty = B.build_index([])
    assert empty.search("anything") == []
    idx = B.build_index(make_units())
    assert idx.search("   ") == []
