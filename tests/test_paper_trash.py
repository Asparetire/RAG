"""论文删除+回收站单测（m6-trash-runbook §6；monkeypatch DB/Qdrant/BM25，纯逻辑）。

fake 连接：记录执行的 SQL（含参数），按注册的匹配器返回 canned 行——
断言"做了什么 SQL"而非真连库；文件操作落到 tmp_path。
"""

from __future__ import annotations

from pathlib import Path

from doclens import paperlib as pl
from doclens.index import bm25 as bm25_mod
from doclens.index import qdrant_store as qs


# ---------- fakes ----------

class FakeCursor:
    def __init__(self, conn):
        self._conn = conn
        self._rows = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, args=None):
        self._conn.queries.append((" ".join(sql.split()), args))
        self.rowcount = 1  # 变更语句默认成功 1 行（rowcount 消费方：rename/delete 判存在）
        for match, rows in self._conn.results:
            if match(sql, args):
                self._rows = rows
                return
        self._rows = []

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return self._rows


class FakeConn:
    """pymysql 连接替身：queries 记录 + results 按匹配器路由 canned 行。"""

    def __init__(self, results=None):
        self.queries = []
        self.results = list(results or [])
        self.commits = 0

    def cursor(self):
        return FakeCursor(self)

    def commit(self):
        self.commits += 1

    def close(self):
        pass


class FakeQdrant:
    def close(self):
        pass


def _setup_doc(tmp_path: Path, doc_id: str = "aabbccddeeff", *,
               deleted_at=None, task_status="completed"):
    """布景：磁盘资产（pdf+parsed 目录）+ canned 查询行；返回 (conn, pdf, parsed)。"""
    data = tmp_path / "data"
    pdf_dir = data / "pdfs"
    parsed = tmp_path / "parsed" / doc_id
    pdf_dir.mkdir(parents=True, exist_ok=True)
    parsed.mkdir(parents=True)
    (pdf_dir / f"{doc_id}.pdf").write_bytes(b"%PDF-1.4 fake")
    (parsed / "doc.json").write_text("{}", encoding="utf-8")
    conn = FakeConn(results=[
        (lambda sql, a: "FROM t_doc WHERE doc_id" in sql, [(doc_id, deleted_at)]),
        (lambda sql, a: "FROM t_ingest_task" in sql, [(task_status,)]),
    ])
    return conn, pdf_dir / f"{doc_id}.pdf", parsed


# ---------- 用例 1（R1 软删正常路径） ----------

def test_soft_delete_marks_and_evicts(monkeypatch, tmp_path):
    doc_id = "aabbccddeeff"
    conn, pdf, parsed = _setup_doc(tmp_path, doc_id)
    monkeypatch.setattr(pl, "connect", lambda *a, **k: conn)
    monkeypatch.setattr(pl, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(pl, "PARSED_DIR", tmp_path / "parsed")
    removed = {}
    monkeypatch.setattr(qs, "_client", lambda: FakeQdrant())
    monkeypatch.setattr(qs, "delete_doc_points",
                        lambda client, d: removed.update(n=12) or 12)
    rebuilds = []
    monkeypatch.setattr(bm25_mod, "bm25_rebuild", lambda: rebuilds.append(1))

    out = pl.soft_delete_doc(doc_id)

    assert out["ok"] is True and out["removed_points"] == 12
    assert removed["n"] == 12 and rebuilds, "应摘除 Qdrant 点位并重建 BM25"
    # 打标 SQL 最后执行，且幂等条件（deleted_at IS NULL）在 WHERE 里
    updates = [sql for sql, _ in conn.queries if sql.startswith("UPDATE t_doc")]
    assert updates and "deleted_at IS NULL" in updates[-1]
    assert updates[-1] == conn.queries[-1][0], "打标应是最后一步（失败可重放）"
    # 软删不动物理文件
    assert pdf.exists() and parsed.exists()


# ---------- 用例 2（R1 幂等重放：已在垃圾桶 → 不动检索面） ----------

def test_soft_delete_idempotent_replay(monkeypatch, tmp_path):
    doc_id = "aabbccddeeff"
    conn, pdf, parsed = _setup_doc(tmp_path, doc_id, deleted_at="2026-11-16 16:00:00")
    monkeypatch.setattr(pl, "connect", lambda *a, **k: conn)
    touched = {"qdrant": 0, "bm25": 0}
    monkeypatch.setattr(qs, "_client", lambda: FakeQdrant())
    monkeypatch.setattr(qs, "delete_doc_points",
                        lambda client, d: touched.update(qdrant=touched["qdrant"] + 1) or 0)
    monkeypatch.setattr(bm25_mod, "bm25_rebuild",
                        lambda: touched.update(bm25=touched["bm25"] + 1))

    out = pl.soft_delete_doc(doc_id)

    assert out == {"ok": True, "already": True}
    assert touched == {"qdrant": 0, "bm25": 0}, "已在垃圾桶：不应重复摘除检索面"


# ---------- 用例 3（R5 守卫：进行中任务拒绝删除） ----------

def test_soft_delete_rejects_active_ingest(monkeypatch, tmp_path):
    doc_id = "aabbccddeeff"
    conn, pdf, parsed = _setup_doc(tmp_path, doc_id, task_status="parsing")
    monkeypatch.setattr(pl, "connect", lambda *a, **k: conn)
    monkeypatch.setattr(pl, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(pl, "PARSED_DIR", tmp_path / "parsed")
    monkeypatch.setattr(qs, "_client", lambda: FakeQdrant())
    monkeypatch.setattr(qs, "delete_doc_points", lambda client, d: 0)
    monkeypatch.setattr(bm25_mod, "bm25_rebuild", lambda: None)

    import pytest
    with pytest.raises(ValueError, match="正在入库"):
        pl.soft_delete_doc(doc_id)
    # 拒绝时不得打标记
    assert not any(sql.startswith("UPDATE t_doc") for sql, _ in conn.queries)


# ---------- 用例 4（R2 恢复正常路径） ----------

def test_restore_replays_and_clears_flag(monkeypatch, tmp_path):
    doc_id = "aabbccddeeff"
    conn, pdf, parsed = _setup_doc(tmp_path, doc_id, deleted_at="2026-11-16 16:00:00")
    monkeypatch.setattr(pl, "connect", lambda *a, **k: conn)
    monkeypatch.setattr(pl, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(pl, "PARSED_DIR", tmp_path / "parsed")
    monkeypatch.setattr(qs, "_client", lambda: FakeQdrant())
    monkeypatch.setattr(qs, "ensure_collections", lambda c: None)
    rebuilds = []
    monkeypatch.setattr(bm25_mod, "bm25_rebuild", lambda: rebuilds.append(1))
    replayed = []
    import scripts.ingest as ingest_mod
    monkeypatch.setattr(ingest_mod, "process_doc",
                        lambda client, q, c, root, force=False: replayed.append(root))

    out = pl.restore_doc(doc_id)

    assert out["ok"] is True and out["pdf_ok"] is True
    assert replayed == [tmp_path / "parsed" / doc_id], "应重放索引入库（嵌入缓存命中）"
    assert rebuilds, "恢复后应重建 BM25"
    clears = [sql for sql, _ in conn.queries
              if sql.startswith("UPDATE t_doc") and "deleted_at=NULL" in sql]
    assert clears and conn.queries[-1][0] == clears[-1], "清标记应是最后一步（出现即完整）"


# ---------- 用例 5（R2b：未删除的文档拒绝恢复） ----------

def test_restore_rejects_not_deleted(monkeypatch, tmp_path):
    doc_id = "aabbccddeeff"
    conn, pdf, parsed = _setup_doc(tmp_path, doc_id, deleted_at=None)
    monkeypatch.setattr(pl, "connect", lambda *a, **k: conn)
    monkeypatch.setattr(pl, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(pl, "PARSED_DIR", tmp_path / "parsed")
    monkeypatch.setattr(qs, "_client", lambda: FakeQdrant())
    monkeypatch.setattr(qs, "ensure_collections", lambda c: None)
    import scripts.ingest as ingest_mod
    monkeypatch.setattr(ingest_mod, "process_doc", lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("未删除的文档不应触发索引重放")))

    import pytest
    with pytest.raises(ValueError, match="不在垃圾桶"):
        pl.restore_doc(doc_id)


# ---------- 用例 6（R3 彻底删除：清库+删产物+PDF 兜底） ----------

def test_purge_clears_db_moves_pdf_to_backup(monkeypatch, tmp_path):
    doc_id = "aabbccddeeff"
    conn, pdf, parsed = _setup_doc(tmp_path, doc_id, deleted_at="2026-11-16 16:00:00")
    monkeypatch.setattr(pl, "connect", lambda *a, **k: conn)
    monkeypatch.setattr(pl, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(pl, "PARSED_DIR", tmp_path / "parsed")
    purged = []
    monkeypatch.setattr(qs, "_client", lambda: FakeQdrant())
    monkeypatch.setattr(qs, "delete_doc_points", lambda client, d: purged.append(d) or 0)

    out = pl.purge_doc(doc_id)

    assert out["ok"] is True and purged == [doc_id]
    sqls = [sql for sql, _ in conn.queries]
    assert any(sql.startswith("DELETE FROM t_doc WHERE doc_id") for sql in sqls)
    assert any("DELETE FROM t_ctx_prefix" in sql and "LIKE" in sql for sql in sqls)
    assert any("DELETE FROM t_ingest_task WHERE doc_id" in sql for sql in sqls)
    # 解析产物目录删除；PDF 原件移入 trash_files 兜底（唯一不可逆点前的保险）
    assert not parsed.exists()
    backup = tmp_path / "data" / "trash_files" / f"{doc_id}.pdf"
    assert backup.is_file() and not pdf.exists()


# ---------- 用例 7（R3b：未进垃圾桶的文档拒绝物理删除） ----------

def test_purge_rejects_not_trashed(monkeypatch, tmp_path):
    doc_id = "aabbccddeeff"
    conn, pdf, parsed = _setup_doc(tmp_path, doc_id, deleted_at=None)
    monkeypatch.setattr(pl, "connect", lambda *a, **k: conn)
    monkeypatch.setattr(pl, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(pl, "PARSED_DIR", tmp_path / "parsed")
    monkeypatch.setattr(qs, "_client", lambda: FakeQdrant())
    monkeypatch.setattr(qs, "delete_doc_points", lambda client, d: 0)

    import pytest
    with pytest.raises(ValueError, match="不在垃圾桶"):
        pl.purge_doc(doc_id)
    # 拒绝时不得有任何破坏性动作
    assert not any(sql.startswith("DELETE FROM") for sql, _ in conn.queries)
    assert pdf.exists() and parsed.exists()


# ---------- 用例 8（R1 过滤面：论文清单排除垃圾桶） ----------

def test_list_papers_excludes_trashed(monkeypatch):
    conn = FakeConn(results=[(lambda sql, a: "FROM t_doc" in sql, [])])
    monkeypatch.setattr(pl, "connect", lambda *a, **k: conn)

    pl.list_papers()

    sql, _ = conn.queries[0]
    assert "deleted_at IS NULL" in sql, "论文清单必须排除已删除（垃圾桶内）文档"


# ---------- 用例 9（R1 垃圾桶列表：只含已删除文档，按删除时间倒序） ----------

def test_list_trash_returns_deleted_only(monkeypatch):
    conn = FakeConn(results=[(lambda sql, a: "FROM t_doc" in sql, [
        ("aabbccddeeff", "司尔特 2024 年度报告", 844, 23, "2026-11-16 16:00:00"),
    ])])
    monkeypatch.setattr(pl, "connect", lambda *a, **k: conn)

    out = pl.list_trash()

    sql, _ = conn.queries[0]
    assert "deleted_at IS NOT NULL" in sql and "ORDER BY deleted_at DESC" in sql
    assert out == [{"doc_id": "aabbccddeeff", "title": "司尔特 2024 年度报告",
                    "n_chunks": 844, "category_id": 23,
                    "deleted_at": "2026-11-16 16:00:00"}]


# ---------- 用例 10（D5 bm25_rebuild 编排固化：与旧内联三连等价） ----------

def test_bm25_rebuild_orchestration(monkeypatch):
    units = [{"chunk_id": "aabbccddeeff:0001", "doc_id": "aabbccddeeff",
              "kind": "text", "content": "x"}]
    saved = {}
    monkeypatch.setattr(bm25_mod, "load_units_from_db", lambda doc_ids=None: units)
    monkeypatch.setattr(bm25_mod, "build_index", lambda u: ("IDX", u))
    monkeypatch.setattr(bm25_mod, "save_index",
                        lambda idx, meta_rows=None: saved.update(meta=meta_rows))

    out = bm25_mod.bm25_rebuild()

    assert out == {"units": 1}
    assert saved["meta"] == [{"chunk_id": "aabbccddeeff:0001",
                              "doc_id": "aabbccddeeff", "kind": "text"}]


# ---------- 用例 11（R1 过滤面：分类删除判断排除垃圾桶文档） ----------

def test_delete_category_count_excludes_trashed(monkeypatch):
    conn = FakeConn(results=[
        (lambda sql, a: "COUNT(*) FROM t_doc" in sql, [(0,)]),
    ])
    monkeypatch.setattr(pl, "connect", lambda *a, **k: conn)

    pl.delete_category(7)

    counts = [sql for sql, _ in conn.queries
              if sql.startswith("SELECT COUNT(*) FROM t_doc")]
    assert counts and "deleted_at IS NULL" in counts[0], "分类占用计数必须排除垃圾桶文档"


# ---------- 用例 12（API 五端点：路由/状态码/错误映射） ----------

def _client():
    from fastapi.testclient import TestClient
    from doclens.serve.api import create_app
    return TestClient(create_app(pipeline=lambda *a, **k: None, auth_enabled=False))


def test_api_paper_delete_and_trash_flow(monkeypatch):
    calls = []
    monkeypatch.setattr(pl, "soft_delete_doc", lambda d, user_id=None: calls.append(d) or {"ok": True, "removed_points": 3})
    monkeypatch.setattr(pl, "list_trash", lambda: [
        {"doc_id": "aabbccddeeff", "title": "t", "n_chunks": 5,
         "category_id": None, "deleted_at": "2026-11-16 16:00:00"}])
    monkeypatch.setattr(pl, "restore_doc", lambda d: calls.append(("restore", d)) or {"ok": True, "pdf_ok": True})
    monkeypatch.setattr(pl, "purge_doc", lambda d: calls.append(("purge", d)) or {"ok": True})
    client = _client()

    r = client.delete("/api/papers/aabbccddeeff")
    assert r.status_code == 200 and r.json()["ok"] is True
    r = client.get("/api/papers/trash")
    assert r.status_code == 200 and r.json()["papers"][0]["doc_id"] == "aabbccddeeff"
    r = client.post("/api/papers/aabbccddeeff/restore")
    assert r.status_code == 200 and r.json()["ok"] is True
    r = client.delete("/api/papers/aabbccddeeff/purge")
    assert r.status_code == 200
    r = client.post("/api/papers/trash/empty")
    assert r.status_code == 200 and r.json()["purged"] == 1
    assert ("purge", "aabbccddeeff") in calls, "清空垃圾桶应逐篇 purge"


def test_api_paper_delete_valueerror_maps_422(monkeypatch):
    monkeypatch.setattr(pl, "soft_delete_doc",
                        lambda d, user_id=None: (_ for _ in ()).throw(ValueError("该论文正在入库（排队/解析/索引中），请稍后再操作")))
    client = _client()
    r = client.delete("/api/papers/aabbccddeeff")
    assert r.status_code == 422 and "正在入库" in r.json()["detail"]


def test_api_upload_dedupe_trash_message(monkeypatch, tmp_path):
    conn = FakeConn(results=[(lambda sql, a: "FROM t_doc WHERE doc_id" in sql,
                              [("aabbccddeeff", "2026-11-16 16:00:00")])])
    from doclens.index import db as db_mod
    monkeypatch.setattr(db_mod, "connect", lambda *a, **k: conn)
    monkeypatch.setattr(pl, "validate_upload", lambda name, size: None)
    client = _client()
    r = client.post("/api/papers/upload",
                    files={"file": ("x.pdf", b"%PDF-1.4 fake", "application/pdf")})
    assert r.status_code == 409 and "垃圾桶" in r.json()["detail"]


def test_api_docs_excludes_trashed(monkeypatch):
    conn = FakeConn(results=[(lambda sql, a: "FROM t_doc" in sql, [])])
    from doclens.index import db as db_mod
    monkeypatch.setattr(db_mod, "connect", lambda *a, **k: conn)
    client = _client()
    r = client.get("/api/docs")
    assert r.status_code == 200
    sql, _ = conn.queries[0]
    assert "deleted_at IS NULL" in sql, "GET /api/docs 必须排除垃圾桶文档"


# ---------- 用例 13（守卫补覆盖：论文不存在/格式非法） ----------

def test_functions_reject_missing_or_malformed_doc(monkeypatch):
    # 格式非法（非 12 位十六进制）→ 不触库直接"论文不存在"
    conn = FakeConn()  # 无路由 → 一切查询返回空
    monkeypatch.setattr(pl, "connect", lambda *a, **k: conn)
    import pytest
    for bad in ("zzz", "AABBCCDDEEFF", "aabbccddeeff0"):
        with pytest.raises(ValueError, match="论文不存在"):
            pl.soft_delete_doc(bad)
        with pytest.raises(ValueError, match="论文不存在"):
            pl.restore_doc(bad)
        with pytest.raises(ValueError, match="论文不存在"):
            pl.purge_doc(bad)
    # 格式合法但库中无行 → 同样"论文不存在"（三个函数各自分支）
    for fn in (pl.soft_delete_doc, pl.restore_doc, pl.purge_doc):
        with pytest.raises(ValueError, match="论文不存在"):
            fn("aabbccddeeff")
    assert not any(sql.startswith(("DELETE", "UPDATE")) for sql, _ in conn.queries), \
        "不存在的文档不得触发任何写库"


# ---------- 用例 14（API 错误映射与清空部分失败） ----------

def test_api_restore_purge_422_and_empty_partial(monkeypatch):
    monkeypatch.setattr(pl, "restore_doc",
                        lambda d: (_ for _ in ()).throw(ValueError("该论文不在垃圾桶中")))

    def _purge(d):
        if d in ("aabbccddeeff", "aaaa00000000"):
            raise ValueError("正在入库")
        return {"ok": True}

    monkeypatch.setattr(pl, "purge_doc", _purge)
    monkeypatch.setattr(pl, "list_trash", lambda: [
        {"doc_id": "aaaa00000000", "title": "x", "n_chunks": 1, "category_id": None, "deleted_at": "d1"},
        {"doc_id": "bbbb11111111", "title": "y", "n_chunks": 1, "category_id": None, "deleted_at": "d2"}])
    client = _client()

    r = client.post("/api/papers/aabbccddeeff/restore")
    assert r.status_code == 422 and "不在垃圾桶" in r.json()["detail"]
    r = client.delete("/api/papers/aabbccddeeff/purge")
    assert r.status_code == 422 and "正在入库" in r.json()["detail"]
    r = client.post("/api/papers/trash/empty")
    assert r.status_code == 200
    assert r.json()["purged"] == 1, "清空逐篇继续：单篇失败不拖垮"
