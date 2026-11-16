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
    """pymysql 连接替身：queries 记录 + results 按匹配器路由 canned 行；事务计数。"""

    def __init__(self, results=None):
        self.queries = []
        self.results = list(results or [])
        self.commits = 0
        self.begins = 0
        self.rollbacks = 0

    def cursor(self):
        return FakeCursor(self)

    def begin(self):
        self.begins += 1

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

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
    rebuild_at = []  # 记录重建调用时已执行的 SQL 条数（验顺序用）
    monkeypatch.setattr(bm25_mod, "bm25_rebuild",
                        lambda: rebuild_at.append(len(conn.queries)))

    out = pl.soft_delete_doc(doc_id)

    assert out["ok"] is True and out["removed_points"] == 12
    assert removed["n"] == 12 and rebuild_at, "应摘除 Qdrant 点位并重建 BM25"
    updates = [i for i, (sql, _) in enumerate(conn.queries) if sql.startswith("UPDATE t_doc")]
    assert updates and "deleted_at IS NULL" in conn.queries[updates[0]][0]
    # B-1 修复：语料源按 deleted_at 过滤后，打标必须先于 BM25 重建——
    # 否则重建语料仍含已删文档，BM25 检索面摘除不成立（审查 B-1）。
    assert updates[0] < rebuild_at[0], "打标（使语料过滤生效）必须先于 BM25 重建"
    # 软删不动物理文件
    assert pdf.exists() and parsed.exists()


# ---------- 用例 2（R1 幂等重放：已在垃圾桶 → 重放摘除自愈） ----------

def test_soft_delete_replay_heals(monkeypatch, tmp_path):
    """重复删除 = 重放摘除（自愈部分失败状态），打标 SQL 幂等不重复置值。

    B-1 修复后不能早退跳过摘除：若上次软删在"打标后、摘除前"中断，
    重试必须补齐 Qdrant/BM25 摘除，否则检索面残留。"""
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

    assert out["ok"] is True
    assert touched == {"qdrant": 1, "bm25": 1}, "重复删除应重放摘除（自愈）"
    updates = [sql for sql, _ in conn.queries if sql.startswith("UPDATE t_doc")]
    assert updates and "deleted_at IS NULL" in updates[-1], "打标幂等（WHERE 守卫不重复置值）"


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
                        lambda client, q, c, root, force=False: replayed.append((root, force, len(c.queries))))

    out = pl.restore_doc(doc_id)

    assert out["ok"] is True and out["pdf_ok"] is True
    # 容器冒烟实证：doc_hash 未变时 process_doc 默认增量跳过（零写入）→ 恢复后 Qdrant
    # 点位丢失。恢复必须 force=True 强制重放（嵌入缓存命中，零 API 费用）。
    assert replayed[0][0] == tmp_path / "parsed" / doc_id and replayed[0][1] is True, \
        "恢复必须强制重放（force=True）"
    assert rebuilds, "恢复后应重建 BM25"
    # B-1 修复：语料源按 deleted_at 过滤后，清标记必须先于重放与 BM25 重建——
    # 否则恢复时重建语料仍排除本文档（调研 L61 原定顺序，审查 B-1 修复②）。
    clears = [i for i, (sql, _) in enumerate(conn.queries)
              if sql.startswith("UPDATE t_doc") and "deleted_at=NULL" in sql]
    assert clears, "清标记 SQL 必须执行"
    assert clears[0] < replayed[0][2], "清标记必须先于 process_doc 重放"


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


# ---------- 用例 13（守卫补覆盖：论文不存在/格式非法，审查 m-2 语义区分） ----------

def test_functions_reject_missing_or_malformed_doc(monkeypatch):
    conn = FakeConn()  # 无路由 → 一切查询返回空
    monkeypatch.setattr(pl, "connect", lambda *a, **k: conn)
    import pytest
    from doclens.paperlib import PaperNotFoundError
    # 格式非法（非 12 位十六进制）→ ValueError"格式非法"（API 422）
    for bad in ("zzz", "AABBCCDDEEFF", "aabbccddeeff0"):
        for fn in (pl.soft_delete_doc, pl.restore_doc, pl.purge_doc):
            with pytest.raises(ValueError, match="格式非法"):
                fn(bad)
    # 格式合法但库中无行 → PaperNotFoundError"论文不存在"（API 404）
    for fn in (pl.soft_delete_doc, pl.restore_doc, pl.purge_doc):
        with pytest.raises(PaperNotFoundError, match="论文不存在"):
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
        if d == "cccc22222222":
            raise RuntimeError("qdrant down")  # m-1：非 ValueError 也不得中断清空
        return {"ok": True}

    monkeypatch.setattr(pl, "purge_doc", _purge)
    monkeypatch.setattr(pl, "list_trash", lambda: [
        {"doc_id": "aaaa00000000", "title": "x", "n_chunks": 1, "category_id": None, "deleted_at": "d1"},
        {"doc_id": "bbbb11111111", "title": "y", "n_chunks": 1, "category_id": None, "deleted_at": "d2"},
        {"doc_id": "cccc22222222", "title": "z", "n_chunks": 1, "category_id": None, "deleted_at": "d3"}])
    client = _client()

    r = client.post("/api/papers/aabbccddeeff/restore")
    assert r.status_code == 422 and "不在垃圾桶" in r.json()["detail"]
    r = client.delete("/api/papers/aabbccddeeff/purge")
    assert r.status_code == 422 and "正在入库" in r.json()["detail"]
    r = client.post("/api/papers/trash/empty")
    assert r.status_code == 200
    assert r.json()["purged"] == 1, "清空逐篇继续：ValueError/RuntimeError 均不拖垮（m-1）"


# ---------- 用例 15（B-1 核心回归：BM25 语料源排除垃圾桶文档——sqlite 真库验证） ----------

def test_load_units_and_build_exclude_trashed(monkeypatch):
    """真跑 SQL 与 build_index：软删（deleted_at 非空）文档的块不得进入 BM25 语料。

    审查 B-1/n-7：此前 17 条测试全部 mock 掉 bm25_rebuild，替身盲区漏过了
    "重建语料仍含已删文档"的缺陷——本用例用 sqlite 内存库跑真 SQL。"""
    import sqlite3

    raw = sqlite3.connect(":memory:")
    import contextlib

    class _SqliteConn:  # pymysql 风格适配：cursor() 支持上下文协议
        def cursor(self):
            return contextlib.nullcontext(raw.cursor())

        def close(self):
            raw.close()

    raw.execute("CREATE TABLE t_chunk (chunk_id TEXT, doc_id TEXT, kind TEXT, content TEXT)")
    raw.execute("CREATE TABLE t_doc (doc_id TEXT, deleted_at TEXT)")
    raw.execute("INSERT INTO t_doc VALUES ('aabbccddeeff', NULL), ('4444aaaa4444', '2026-11-16')")
    raw.execute("INSERT INTO t_chunk VALUES "
                "('aabbccddeeff:0001','aabbccddeeff','text','live quantum'),"
                "('4444aaaa4444:0001','4444aaaa4444','text','deleted secret'),"
                "('aabbccddeeff:0002','aabbccddeeff','image','')")
    from doclens.index import db as db_mod
    monkeypatch.setattr(db_mod, "connect", lambda *a, **k: _SqliteConn())

    units = bm25_mod.load_units_from_db()
    assert [u["doc_id"] for u in units] == ["aabbccddeeff"], "语料源必须排除垃圾桶文档"

    idx = bm25_mod.build_index(units)
    assert "aabbccddeeff:0001" in idx.chunk_ids and "4444aaaa4444:0001" not in idx.chunk_ids
    hits = idx.search("quantum", top=5)
    assert all(cid.split(":")[0] != "4444aaaa4444" for cid, _ in hits)
    raw.close()


# ---------- 用例 16（M-2a：恢复/彻底删除同样拒绝进行中任务） ----------

def test_restore_purge_reject_active_ingest(monkeypatch, tmp_path):
    doc_id = "aabbccddeeff"
    conn, pdf, parsed = _setup_doc(tmp_path, doc_id,
                                   deleted_at="2026-11-16 16:00:00", task_status="parsing")
    monkeypatch.setattr(pl, "connect", lambda *a, **k: conn)
    monkeypatch.setattr(pl, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(pl, "PARSED_DIR", tmp_path / "parsed")
    monkeypatch.setattr(qs, "_client", lambda: FakeQdrant())
    monkeypatch.setattr(qs, "delete_doc_points", lambda client, d: 0)
    monkeypatch.setattr(bm25_mod, "bm25_rebuild", lambda: None)
    import scripts.ingest as ingest_mod
    monkeypatch.setattr(ingest_mod, "process_doc",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("不应重放")))

    import pytest
    with pytest.raises(ValueError, match="正在入库"):
        pl.restore_doc(doc_id)
    with pytest.raises(ValueError, match="正在入库"):
        pl.purge_doc(doc_id)
    assert not any(sql.startswith("DELETE FROM") for sql, _ in conn.queries), \
        "守卫拒绝时不得有任何破坏性动作"


# ---------- 用例 17（M-1：purge 三条 DELETE 包显式事务） ----------

def test_purge_wraps_db_in_transaction(monkeypatch, tmp_path):
    doc_id = "aabbccddeeff"
    conn, pdf, parsed = _setup_doc(tmp_path, doc_id, deleted_at="2026-11-16 16:00:00")
    monkeypatch.setattr(pl, "connect", lambda *a, **k: conn)
    monkeypatch.setattr(pl, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(pl, "PARSED_DIR", tmp_path / "parsed")
    monkeypatch.setattr(qs, "_client", lambda: FakeQdrant())
    monkeypatch.setattr(qs, "delete_doc_points", lambda client, d: 0)

    pl.purge_doc(doc_id)

    assert conn.begins == 1, "autocommit 下三条 DELETE 必须 conn.begin() 包事务（M-1）"
    assert conn.rollbacks == 0 and conn.commits >= 1


# ---------- 用例 18（M-2b：垃圾桶内文档重复入库 → 任务报错引导恢复） ----------

def test_run_ingest_trash_dedupe_errors_out(monkeypatch, tmp_path):
    doc_id = "aabbccddeeff"
    data = tmp_path / "data"
    (data / "pdfs").mkdir(parents=True)
    src = tmp_path / "upload.pdf"
    src.write_bytes(b"%PDF-1.4 " + b"x" * 11264)  # 过 10KB 校验
    conn = FakeConn(results=[
        (lambda sql, a: "SELECT deleted_at FROM t_doc" in sql, [("2026-11-16 16:00:00",)]),
    ])
    from doclens.index import db as db_mod
    monkeypatch.setattr(pl, "connect", lambda *a, **k: conn)
    monkeypatch.setattr(db_mod, "connect", lambda *a, **k: conn)  # _run_ingest 内部是局部导入
    monkeypatch.setattr(pl, "DATA_DIR", data)
    monkeypatch.setattr(pl, "PARSED_DIR", tmp_path / "parsed")
    recorded = []
    monkeypatch.setattr(pl, "update_task",
                        lambda tid, **kw: recorded.append((kw.get("status"), kw.get("error"))))
    import re as _re
    monkeypatch.setattr("doclens.parse.mineru_parser.parse_pdf",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("垃圾桶内文档不应触发解析")))

    pl._run_ingest(999, src, None)

    assert recorded[-1][0] == "error" and "垃圾桶" in (recorded[-1][1] or ""), \
        "去重命中垃圾桶行 → 任务报错引导恢复，不得静默归档/改分类"


# ---------- 用例 19（M-2c：垃圾桶内文档拒绝 retry） ----------

def test_api_retry_rejects_trashed_doc(monkeypatch, tmp_path):
    conn = FakeConn(results=[
        (lambda sql, a: "FROM t_ingest_task WHERE id" in sql,
         [("old.pdf", 3, "aabbccddeeff")]),
        (lambda sql, a: "SELECT deleted_at FROM t_doc" in sql, [("2026-11-16",)]),
    ])
    from doclens.serve import api as api_mod  # retry 用模块级 connect → patch api 命名空间
    monkeypatch.setattr(api_mod, "connect", lambda *a, **k: conn)
    monkeypatch.setattr(pl, "_run_ingest",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("垃圾桶内文档不应重试")))
    client = _client()
    r = client.post("/api/papers/tasks/9/retry")
    assert r.status_code == 422 and "垃圾桶" in r.json()["detail"]


# ---------- 用例 20（m-2：不存在 404 / 格式非法 422） ----------

def test_api_paper_delete_missing_404_malformed_422(monkeypatch):
    conn = FakeConn()  # 库中无行
    monkeypatch.setattr(pl, "connect", lambda *a, **k: conn)
    client = _client()
    r = client.delete("/api/papers/aabbccddeeff")
    assert r.status_code == 404 and "论文不存在" in r.json()["detail"]
    r = client.delete("/api/papers/zzz")
    assert r.status_code == 422 and "格式非法" in r.json()["detail"]
