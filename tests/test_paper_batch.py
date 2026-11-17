"""批量入库 + 失败处理四件套单测（2026-11-17，调研 specs/research/paper-management-survey.md）。

FakeConn/TestClient 范式（同 test_paper_trash）：断言"做了什么"而非真连库；
线程 spawn 打桩（记录 target/args 不真跑）——worker 行为经模块级函数直测。
"""

from __future__ import annotations

import io

from doclens import paperlib as pl
from doclens.serve import api as api_mod
from fastapi.testclient import TestClient

from tests.test_paper_trash import FakeConn


# ---------- fakes ----------

class _NoThread:
    """threading.Thread 替身：记录 target/args/name，不启动。"""

    last = None

    def __init__(self, target=None, args=(), daemon=False, name=None):
        _NoThread.last = (target, args, name)

    def start(self):
        return None


def _client() -> TestClient:
    from doclens.serve.api import create_app
    return TestClient(create_app(pipeline=lambda *a, **k: None, auth_enabled=False))


def _patch_common(monkeypatch, conn, tmp_path=None):
    """公共打桩：DB 连接（db_mod + paperlib + ablation 三处绑定）、校验放行、
    分类/建任务/解析线程全部打桩。

    S3 M-4：tmp_path 传入时把 api_mod/pl 的 DATA_DIR 重定向到临时目录——
    端点落盘与 R4 清理都在沙盒里，绝不触碰真实 data/pdfs_inbox（否则跑
    测试即删真实超期原件）。"""
    from doclens.eval import ablation as eval_mod
    from doclens.index import db as db_mod
    monkeypatch.setattr(db_mod, "connect", lambda *a, **k: conn)
    monkeypatch.setattr(pl, "connect", lambda *a, **k: conn)
    monkeypatch.setattr(eval_mod, "connect", lambda *a, **k: conn)  # 消启动扫描 10s 真连库超时
    monkeypatch.setattr(pl, "validate_upload",
                        lambda name, size: None if name.lower().endswith(".pdf") else "仅支持 PDF 文件")
    monkeypatch.setattr(pl, "_run_ingest", lambda *a, **k: None)
    monkeypatch.setattr(pl, "ensure_default_category", lambda: 1)
    seq = {"n": 0}

    def fake_create_task(filename, category_id, batch_id, user_id=None):
        seq["n"] += 1
        return 1000 + seq["n"]

    monkeypatch.setattr(pl, "create_task", fake_create_task)
    monkeypatch.setattr("threading.Thread", _NoThread)
    if tmp_path is not None:
        (tmp_path / "pdfs_inbox").mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(api_mod, "DATA_DIR", tmp_path)
        monkeypatch.setattr(pl, "DATA_DIR", tmp_path)


def _pdf_bytes(tag: bytes | str = "A") -> bytes:
    return b"%PDF-1.4 fake-" + (tag if isinstance(tag, bytes) else tag.encode())


def _conn_route_docid(doc_id_rules):
    """FakeConn：按 doc_id 参数路由 deleted_at 查询（rules: (子串, deleted_at|None)）。"""
    conn = FakeConn()

    def fake_execute(self, sql, args=None):
        self._conn.queries.append((" ".join(sql.split()), args))
        self.rowcount = 1
        self._rows = []
        doc_id = args[0] if args else ""
        for sub, deleted_at in doc_id_rules:
            if sub in doc_id:
                self._rows = [(deleted_at,)]
                break

    class FC:
        _conn = conn  # 类属性绑定（fake_execute 里经 self._conn 记录查询）

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def execute(self, sql, args=None):
            fake_execute(self, sql, args)

        def fetchone(self):
            return self._rows[0] if getattr(self, "_rows", []) else None

    conn.cursor = lambda: FC()
    conn.close = lambda: None
    return conn


# ---------- 批量端点 ----------

def _doc_id(tag: bytes) -> str:
    """与后端同口径的 doc_id（sha256 前 12 位）——用于路由 doc_id 查询。"""
    import hashlib
    return hashlib.sha256(_pdf_bytes(tag)).hexdigest()[:12]


def test_batch_upload_mixed_actions(monkeypatch, tmp_path):
    """四文件混合：新/已入库重复/垃圾桶重复/非 PDF 后缀 → queued×1 + skip×3。"""
    conn = _conn_route_docid([
        (_doc_id(b"dup0"), None),                      # 与库内重复
        (_doc_id(b"tras"), "2026-11-16 16:00:00"),     # 在垃圾桶
    ])
    _patch_common(monkeypatch, conn, tmp_path)
    client = _client()
    r = client.post("/api/papers/upload-batch", files=[
        ("files", ("new1.pdf", _pdf_bytes("aaaa"), "application/pdf")),
        ("files", ("dup.pdf", _pdf_bytes("dup0"), "application/pdf")),
        ("files", ("tras.pdf", _pdf_bytes("tras"), "application/pdf")),
        ("files", ("bad.txt", b"not a pdf", "text/plain")),
    ])
    assert r.status_code == 200
    data = r.json()
    assert set(data.keys()) == {"batch_id", "results"}
    acts = {x["filename"]: x["action"] for x in data["results"]}
    assert acts["new1.pdf"] == "queued"
    assert acts["dup.pdf"] == "skipped_duplicate"
    assert acts["tras.pdf"] == "skipped_trash"
    trash_detail = [x["detail"] for x in data["results"] if x["filename"] == "tras.pdf"][0]
    assert "恢复" in trash_detail
    assert acts["bad.txt"] == "skipped_invalid"


def test_batch_upload_intra_batch_dedupe(monkeypatch, tmp_path):
    """批内去重：同字节两文件 → 第二个 skipped_duplicate（只建一个任务）。"""
    conn = _conn_route_docid([])  # t_doc 查空（跨库不重复）
    _patch_common(monkeypatch, conn, tmp_path)
    client = _client()
    payload = _pdf_bytes("same")
    r = client.post("/api/papers/upload-batch", files=[
        ("files", ("a.pdf", payload, "application/pdf")),
        ("files", ("b.pdf", payload, "application/pdf")),
    ])
    assert r.status_code == 200
    acts = [x["action"] for x in r.json()["results"]]
    assert acts == ["queued", "skipped_duplicate"], f"results={r.json()!r}"


def test_batch_upload_over_limit(monkeypatch, tmp_path):
    conn = _conn_route_docid([])
    _patch_common(monkeypatch, conn, tmp_path)
    client = _client()
    r = client.post("/api/papers/upload-batch", files=[
        ("files", (f"f{i}.pdf", _pdf_bytes(str(i)), "application/pdf"))
        for i in range(pl.MAX_BATCH_FILES + 1)
    ])
    assert r.status_code == 422 and "单批最多" in r.json()["detail"]


def test_batch_upload_serial_worker(monkeypatch, tmp_path):
    """整批一个 worker 线程串行处理（防并发解析复现 2026-11-16 事故）。"""
    conn = _conn_route_docid([])
    _patch_common(monkeypatch, conn, tmp_path)
    client = _client()
    r = client.post("/api/papers/upload-batch", files=[
        ("files", ("a.pdf", _pdf_bytes("x1"), "application/pdf")),
        ("files", ("b.pdf", _pdf_bytes("x2"), "application/pdf")),
    ])
    assert r.status_code == 200
    target, args, name = _NoThread.last
    assert target is api_mod._run_batch_worker
    assert name.startswith("ingest-batch-")
    staged, cat_id = args
    assert [t for t, _ in staged] == [1001, 1002]
    assert cat_id == 1


def test_run_batch_worker_serial_order(monkeypatch):
    """worker 逐个串行调用 _run_ingest（顺序=入队顺序）。"""
    calls = []
    monkeypatch.setattr(pl, "_run_ingest",
                        lambda task_id, dest, cat: calls.append((task_id, str(dest), cat)))
    staged = [(1, "d1"), (2, "d2"), (3, "d3")]
    api_mod._run_batch_worker(staged, 7)
    assert calls == [(1, "d1", 7), (2, "d2", 7), (3, "d3", 7)]


# ---------- R1 失败可见性 ----------

def test_list_active_tasks_includes_error(monkeypatch):
    """R1：SQL 纳入 24h 内 error 行（失败任务 UI 隐身缺口修复）。"""
    captured = {}

    def fake_connect(*a, **k):
        class C:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def cursor(self):
                return self

            def execute(self, sql, args=None):
                captured["sql"] = " ".join(sql.split())

            def fetchall(self):
                return []

            def close(self):
                pass

        return C()

    monkeypatch.setattr(pl, "connect", fake_connect)
    pl.list_active_tasks()
    assert "status IN ('queued','parsing','indexing')" in captured["sql"]
    assert "status='error'" in captured["sql"] and "INTERVAL 1 DAY" in captured["sql"]
    assert "LIMIT 200" in captured["sql"]  # S4 L-3 有界化


# ---------- S4 安全负向用例（2026-11-17 复查 M-1/M-2/L-1 闭环） ----------

class _StubUpload:
    """UploadFile 替身：可 seek 的内存文件 + size 读取打点（验证不整读）。"""

    def __init__(self, blob: bytes):
        self.file = io.BytesIO(blob)
        self.read_sizes: list[int] = []
        orig_read = self.file.read

        def read(n=-1):
            self.read_sizes.append(n)
            return orig_read(n)

        self.file.read = read


def test_read_upload_capped_oversize_not_read_entirely(monkeypatch):
    """M-2：超过 100MB 的 part 先被 size 预检拒绝，不整读进 RAM。"""
    class _LyingFile:
        def __init__(self):
            self._buf = io.BytesIO(b"x" * 1024)
            self.reads: list[int] = []

        def seek(self, pos, whence=0):
            return self._buf.seek(pos, whence)

        def tell(self):
            return 150 * 1024 * 1024  # 谎报 150MB（实际 1KB）

        def read(self, n=-1):
            self.reads.append(n)
            return self._buf.read(n)

    class LyingStub:
        def __init__(self):
            self.file = _LyingFile()

    stub = LyingStub()
    contents, err = pl.read_upload_capped(stub, "big.pdf")
    assert contents is None and "100MB" in err
    # size 预检拒绝发生在 read 之前——零整读
    assert stub.file.reads == []
    # 对照：正常小文件通过
    small = _StubUpload(b"x" * (20 * 1024))
    ok_contents, ok_err = pl.read_upload_capped(small, "small.pdf")
    assert ok_contents is not None and ok_err is None


def test_safe_basename_sanitizes_malicious_names():
    """L-1：路径分隔符/控制字符/U+202E/超长名净化。"""
    assert "/" not in pl._safe_basename("../../etc/passwd.pdf")
    assert "\\" not in pl._safe_basename("..\\..\\win\\x.pdf")
    assert "\n" not in pl._safe_basename("a\nb.pdf")
    assert "\u202e" not in pl._safe_basename("evil\u202efdp.pdf")
    long = "长" * 300 + ".pdf"
    out = pl._safe_basename(long)
    assert len(out.encode("utf-8")) <= 200 and out.endswith(".pdf")
    assert pl._safe_basename("") == "paper.pdf"
    assert pl._safe_basename("正常论文.pdf") == "正常论文.pdf"


def test_batch_upload_error_detail_sanitized(monkeypatch):
    """M-1：单文件异常的 detail 走 sanitize_error——绝对路径/凭据不回显。"""
    conn = _conn_route_docid([])
    _patch_common(monkeypatch, conn)
    # create_task 抛带绝对路径的异常（模拟 DB/落盘错误的真实形态）
    monkeypatch.setattr(pl, "create_task",
                        lambda *a, **k: (_ for _ in ()).throw(
                            RuntimeError("db error at /home/doclens/RAG/data/pdfs_inbox/x.pdf")))
    client = _client()
    r = client.post("/api/papers/upload-batch", files=[
        ("files", ("a.pdf", _pdf_bytes("z1"), "application/pdf")),
    ])
    assert r.status_code == 200
    detail = r.json()["results"][0]["detail"]
    assert "/home/doclens" not in detail and "RAG" not in detail
    assert "处理失败" in detail


# ---------- S4 安全负向用例结束 ----------

# ---------- R4 inbox 生命周期 ----------

def test_cleanup_inbox_file_only_inbox(monkeypatch, tmp_path):
    """R4：_cleanup_inbox_file 只删 inbox 下文件；canonical（data/pdfs）绝不误删。
    S3 M-4：DATA_DIR 重定向 tmp_path——测试绝不触碰真实 data/pdfs_inbox。"""
    monkeypatch.setattr(pl, "DATA_DIR", tmp_path)
    inbox = tmp_path / "pdfs_inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    in_file = inbox / "_t_cleanup_test.pdf"
    in_file.write_bytes(b"x")
    canonical_dir = tmp_path / "pdfs"
    canonical_dir.mkdir(parents=True, exist_ok=True)
    can_file = canonical_dir / "_t_cleanup_test.pdf"
    can_file.write_bytes(b"x")
    try:
        assert pl._cleanup_inbox_file(in_file) is True
        assert not in_file.exists()
        assert pl._cleanup_inbox_file(can_file) is False
        assert can_file.exists()
    finally:
        for f in (in_file, can_file):
            if f.exists():
                f.unlink()


def test_sweep_old_inbox_files_keeps_new_deletes_old(monkeypatch, tmp_path):
    """R4 启动清理：>days 天的 inbox 原件删除，新文件保留。
    S3 M-4：DATA_DIR 重定向 tmp_path——测试绝不触碰真实 data/pdfs_inbox。"""
    import os
    import time as _t

    monkeypatch.setattr(pl, "DATA_DIR", tmp_path)
    inbox = tmp_path / "pdfs_inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    old = inbox / "_t_old.pdf"
    new = inbox / "_t_new.pdf"
    old.write_bytes(b"old")
    new.write_bytes(b"new")
    old_time = _t.time() - 8 * 86400
    os.utime(old, (old_time, old_time))
    try:
        n = pl.sweep_old_inbox_files(days=7)
        assert n >= 1
        assert not old.exists()
        assert new.exists()
    finally:
        for f in (old, new):
            if f.exists():
                f.unlink()
