"""M4 论文库（m4-runbook 4.8；调研 §9 E/F 线范式落地）。

三大件：
1. t_category 树（FastGPT 式：自引用+ancestor_ids 物化路径+环检测+层级上限）；
2. t_ingest_task 状态机（dify 式：queued/parsing/indexing/completed/error
   + chunk 计数 + error 文本 + batch 聚合号）；
3. 单篇入库编排（复用 M1/M2 全部既有零件：corpus_intake 校验/去重 →
   mineru_parser.parse_pdf → ingest.process_doc → BM25 重建）。

设计要点（调研校验）：
- 任务状态落库 + 前端 2s 轮询（五家共同范式，无 WebSocket）；
- 进程内后台任务（open-webui 同款）+ **启动扫描兜底**（uvicorn 重启时把
  超阈值 processing 任务标 failed——open-webui/dify 同款思路，不引 celery）；
- 上传口同步校验大小/扩展名（4xx），解析失败放任务侧；
- 所有表预埋可空 user_id（anything-llm 平滑升级路径，L1 启用时零迁移）。
"""

from __future__ import annotations

import asyncio
import json
import shutil
import threading
import time
from datetime import datetime
from pathlib import Path

from doclens.config import DATA_DIR, PARSED_DIR, settings
from doclens.index.db import connect

MAX_CATEGORY_DEPTH = 3          # FastGPT maxFolderDepth 同款（根=1 层）
STALE_TASK_SECONDS = 3600       # 启动扫描阈值：processing 超 1h 视为中断（open-webui 口径）
UPLOAD_MAX_BYTES = 100 * 1024 * 1024  # MaxKB 口径 100MB

MANIFEST_PATH = DATA_DIR / "corpus_manifest.json"
_INGEST_LOCK = threading.Lock()  # 单机串行化入库（嵌入批/连接池量级），防并发重复建索引


# ---------- 分类树（FastGPT 式） ----------

def _validate_name(name: str) -> str:
    name = (name or "").strip()
    if not name or len(name) > 64:
        raise ValueError("分类名需为 1–64 字符")
    return name


def _subtree_ids(cur, cat_id: int) -> set[int]:
    """子树 ID 集合（S3 M-1 修复：JSON 列用 MEMBER OF 判断成员——IN 对 JSON 数组恒假）。"""
    cur.execute(
        "SELECT id FROM t_category WHERE CAST(%s AS JSON) MEMBER OF (ancestor_ids) OR id=%s",
        (str(cat_id), cat_id),
    )
    return {r[0] for r in cur.fetchall()}


def list_tree(user_id: str | None = None) -> list[dict]:
    """全量分类（树形由前端按 parent_id/ancestor_ids 组装）。"""
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, name, parent_id, ancestor_ids FROM t_category "
                "ORDER BY parent_id IS NOT NULL DESC, name")
            rows = cur.fetchall()
        return [{"id": r[0], "name": r[1], "parent_id": r[2],
                 "ancestor_ids": _maybe_ids(r[3])} for r in rows]
    finally:
        conn.close()


def _maybe_ids(val):
    if isinstance(val, list):
        return val
    if isinstance(val, str) and val.strip():
        try:
            parsed = json.loads(val)
            return parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            return []
    return []


def create_category(name: str, parent_id: int | None, user_id: str | None = None) -> dict:
    name = _validate_name(name)
    conn = connect()
    try:
        with conn.cursor() as cur:
            ancestors: list[int] = []
            depth = 1
            if parent_id is not None:
                cur.execute("SELECT id, name, ancestor_ids FROM t_category WHERE id=%s",
                            (parent_id,))
                row = cur.fetchone()
                if row is None:
                    raise ValueError("父分类不存在")
                parent_ancestors = _maybe_ids(row[2])
                ancestors = parent_ancestors + [parent_id]
                depth = len(ancestors) + 1
                if depth > MAX_CATEGORY_DEPTH:
                    raise ValueError(f"层级超限（最多 {MAX_CATEGORY_DEPTH} 层）")
                # 重名检查（同父下）
                cur.execute(
                    "SELECT COUNT(*) FROM t_category WHERE parent_id=%s AND name=%s",
                    (parent_id, name))
                if cur.fetchone()[0]:
                    raise ValueError("同级下已存在同名分类")
            else:
                cur.execute("SELECT COUNT(*) FROM t_category WHERE parent_id IS NULL AND name=%s",
                            (name,))
                if cur.fetchone()[0]:
                    raise ValueError("顶层已存在同名分类")
            cur.execute(
                "INSERT INTO t_category (name, parent_id, ancestor_ids, user_id) "
                "VALUES (%s,%s,%s,%s)",
                (name, parent_id, json.dumps(ancestors), user_id))
            cat_id = cur.lastrowid
        conn.commit()
        return {"id": cat_id, "name": name, "parent_id": parent_id,
                "ancestor_ids": ancestors}
    finally:
        conn.close()


def rename_category(cat_id: int, new_name: str) -> None:
    new_name = _validate_name(new_name)
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE t_category SET name=%s WHERE id=%s", (new_name, cat_id))
            if cur.rowcount == 0:
                raise ValueError("分类不存在")
        conn.commit()
    finally:
        conn.close()


def move_category(cat_id: int, new_parent_id: int | None) -> None:
    """移动分类：环检测（新父不得在自身子树内）+ 层级校验 + ancestor_ids 子树级联更新。"""
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, parent_id, ancestor_ids FROM t_category WHERE id=%s", (cat_id,))
            row = cur.fetchone()
            if row is None:
                raise ValueError("分类不存在")
            old_ancestors = _maybe_ids(row[2])

            new_ancestors: list[int] = []
            if new_parent_id is not None:
                cur.execute("SELECT id, ancestor_ids FROM t_category WHERE id=%s", (new_parent_id,))
                prow = cur.fetchone()
                if prow is None:
                    raise ValueError("目标父分类不存在")
                if new_parent_id == cat_id:
                    raise ValueError("不能移入自身")
                p_anc = _maybe_ids(prow[1])
                if cat_id in p_anc or new_parent_id in old_ancestors:
                    raise ValueError("不能移入自身子树（环路）")
                new_ancestors = p_anc + [new_parent_id]
                if len(new_ancestors) + 1 > MAX_CATEGORY_DEPTH:
                    raise ValueError(f"层级超限（最多 {MAX_CATEGORY_DEPTH} 层）")
            # 子树级联：原 subtree 内所有后代 ancestor_ids 前缀替换
            subtree = _subtree_ids(cur, cat_id) - {cat_id}
            for sid in subtree:
                cur.execute("SELECT ancestor_ids FROM t_category WHERE id=%s", (sid,))
                anc = _maybe_ids(cur.fetchone()[0])
                new_anc = new_ancestors + [cid for cid in anc if cid not in set(old_ancestors) | {cat_id}]
                cur.execute("UPDATE t_category SET ancestor_ids=%s WHERE id=%s",
                            (json.dumps(new_anc), sid))
            cur.execute("UPDATE t_category SET parent_id=%s, ancestor_ids=%s WHERE id=%s",
                        (new_parent_id, json.dumps(new_ancestors), cat_id))
        conn.commit()
    finally:
        conn.close()


def delete_category(cat_id: int) -> None:
    """删除分类：含子树或挂有论文时拒绝（防误删，提示先清理）。"""
    conn = connect()
    try:
        with conn.cursor() as cur:
            if _subtree_ids(cur, cat_id) - {cat_id}:
                raise ValueError("请先删除/移出子分类")
            cur.execute("SELECT COUNT(*) FROM t_doc WHERE category_id=%s", (cat_id,))
            if cur.fetchone()[0]:
                raise ValueError("分类下仍有论文，请先移动论文")
            cur.execute("DELETE FROM t_category WHERE id=%s", (cat_id,))
            if cur.rowcount == 0:
                raise ValueError("分类不存在")
        conn.commit()
    finally:
        conn.close()


def ensure_default_category() -> int:
    """确保"未分类"根节点存在（B 决策点：初始 11 篇全挂这里）。返回其 id。"""
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM t_category WHERE parent_id IS NULL AND name='未分类'")
            row = cur.fetchone()
            if row:
                return row[0]
            cur.execute("INSERT INTO t_category (name, parent_id, ancestor_ids) "
                        "VALUES ('未分类', NULL, '[]')")
            conn.commit()
            return cur.lastrowid
    finally:
        conn.close()


# ---------- 论文列表 ----------

def list_papers(user_id: str | None = None) -> list[dict]:
    """论文清单（tree 视图用）：t_doc 左连分类，附解析状态（t_ingest_task 最新一条）。"""
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT d.doc_id, d.title, d.n_chunks, d.category_id, c.name, "
                "(SELECT t.status FROM t_ingest_task t WHERE t.doc_id=d.doc_id "
                " ORDER BY t.id DESC LIMIT 1) AS last_status "
                "FROM t_doc d LEFT JOIN t_category c ON c.id=d.category_id "
                "ORDER BY d.doc_id")
            return [{"doc_id": r[0], "title": r[1] or r[0], "n_chunks": r[2],
                     "category_id": r[3], "category_name": r[4],
                     "status": r[5] or "completed"}
                    for r in cur.fetchall()]
    finally:
        conn.close()


# ---------- 任务状态机 ----------

def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def create_task(filename: str, category_id: int | None, batch_id: str,
                user_id: str | None = None) -> int:
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO t_ingest_task (batch_id, filename, category_id, status, "
                "progress, progress_msg, user_id) VALUES (%s,%s,%s,'queued',0,%s,%s)",
                (batch_id, filename, category_id, "排队中", user_id))
            conn.commit()
            return cur.lastrowid
    finally:
        conn.close()


def update_task(task_id: int, *, status: str | None = None, progress: float | None = None,
                progress_msg: str | None = None, error: str | None = None,
                doc_id: str | None = None, completed_chunks: int | None = None,
                total_chunks: int | None = None) -> None:
    sets, args = [], []
    for col, val in (("status", status), ("progress", progress),
                     ("progress_msg", progress_msg), ("error", error),
                     ("doc_id", doc_id), ("completed_chunks", completed_chunks),
                     ("total_chunks", total_chunks)):
        if val is not None:
            sets.append(f"{col}=%s")
            args.append(val)
    if not sets:
        return
    args.append(task_id)
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(f"UPDATE t_ingest_task SET {', '.join(sets)}, updated_at=CURRENT_TIMESTAMP "
                        f"WHERE id=%s", tuple(args))
        conn.commit()
    finally:
        conn.close()


def get_tasks_by_batch(batch_id: str) -> list[dict]:
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, filename, status, progress, progress_msg, error, doc_id, "
                "completed_chunks, total_chunks FROM t_ingest_task WHERE batch_id=%s "
                "ORDER BY id", (batch_id,))
            return [{"task_id": r[0], "filename": r[1], "status": r[2], "progress": r[3],
                     "progress_msg": r[4], "error": r[5], "doc_id": r[6],
                     "completed_chunks": r[7], "total_chunks": r[8]} for r in cur.fetchall()]
    finally:
        conn.close()


def sweep_stale_tasks() -> int:
    """启动扫描兜底（open-webui/dify 同款）：processing 超阈值标 failed。返回处理数。"""
    conn = connect()
    cutoff = datetime.now().timestamp() - STALE_TASK_SECONDS
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM t_ingest_task WHERE status IN ('queued','parsing','indexing') "
                "AND updated_at < %s", (datetime.fromtimestamp(cutoff),))
            rows = cur.fetchall()
            for (tid,) in rows:
                cur.execute(
                    "UPDATE t_ingest_task SET status='error', error='任务中断（服务重启）', "
                    "updated_at=CURRENT_TIMESTAMP WHERE id=%s", (tid,))
        conn.commit()
        return len(rows)
    finally:
        conn.close()


# ---------- 单篇入库编排（复用 M1/M2 零件） ----------

def _run_ingest(task_id: int, pdf_path: Path, category_id: int | None) -> None:
    """后台任务体：校验去重 → MinerU 解析 → 索引入库 → BM25 重建 → 状态落库。

    同步阻塞实现（线程内执行）：MinerU subprocess/嵌入调用都是慢 IO，线程足够；
    _INGEST_LOCK 串行化防并发重复建索引。异常 → status=error + error 文本。
    """
    with _INGEST_LOCK:
        try:
            # 1) 校验 + sha256 去重 + **落 canonical**（S3 B-1：必须显式复制到
            #    data/pdfs/{doc_id}.pdf——PDF 预览与重试链路都依赖它；intake() 是
            #    批处理入口不适用于单篇路径）
            from scripts.corpus_intake import validate_pdf  # 延迟导入防环
            err = validate_pdf(pdf_path)
            if err:
                raise ValueError(err)
            digest = _sha256_of(pdf_path)
            doc_id = digest[:12]
            canonical = DATA_DIR / "pdfs" / f"{doc_id}.pdf"
            canonical.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(pdf_path, canonical)
            update_task(task_id, doc_id=doc_id, status="parsing", progress=0.05,
                        progress_msg="校验通过，开始解析")
            # 去重：t_doc 已有同 doc_id → 直接归档跳过解析
            from doclens.index.db import connect
            conn = connect()
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT COUNT(*) FROM t_doc WHERE doc_id=%s", (doc_id,))
                    exists = cur.fetchone()[0]
            finally:
                conn.close()
            if exists:
                update_task(task_id, status="completed", progress=1.0,
                            progress_msg="与已入库论文内容相同（sha256 重复），已归入分类",
                            completed_chunks=None, total_chunks=None)
                if category_id:
                    assign_category(doc_id, category_id)
                return

            # 2) MinerU 解析（subprocess，含重试/缓存；最耗时一步）
            from doclens.parse.mineru_parser import parse_pdf
            doc = parse_pdf(pdf_path, force=False)
            update_task(task_id, doc_id=doc.doc_id, progress=0.4,
                        progress_msg=f"解析完成（标题：{doc.title or doc_id}）")

            # 3) 索引入库（chunk+embed+Qdrant+MySQL；ingest.process_doc 原样复用）
            update_task(task_id, status="indexing", progress=0.5, progress_msg="分块+嵌入+入库")
            from scripts.ingest import process_doc
            from doclens.index.db import connect
            from doclens.index.embeddings import EmbeddingClient
            from doclens.index import qdrant_store as qs
            client = EmbeddingClient()
            qclient = qs._client()
            conn = connect()
            try:
                qs.ensure_collections(qclient)
                r = process_doc(client, qclient, conn, PARSED_DIR / doc.doc_id, force=False)
            finally:
                conn.close()
                qclient.close()

            # 4) BM25 全量重建（~1500 块秒级）
            from doclens.index import bm25 as B
            units = B.load_units_from_db()
            idx = B.build_index(units)
            B.save_index(idx, meta_rows=[{"chunk_id": u["chunk_id"], "doc_id": u["doc_id"],
                                          "kind": u["kind"]} for u in units])

            # 5) 分类归属 + 完成态
            if category_id:
                assign_category(doc.doc_id, category_id)
            update_task(task_id, status="completed", progress=1.0,
                        progress_msg=f"入库完成 text={r['n_text']} img={r['n_img']}",
                        completed_chunks=r["n_text"], total_chunks=r["n_text"] + r["n_img"])
        except Exception as exc:  # noqa: BLE001 任务侧兜底：错误文本落库（dify 范式）
            # S4 M4-05：error 文本与 SSE error 同口径脱敏（防路径/凭据片段入库回显）
            from doclens.serve.sanitize import sanitize_error
            update_task(task_id, status="error", progress=1.0,
                        error=sanitize_error(exc)[:500], progress_msg="失败")


def _sha256_of(path: Path) -> str:
    import hashlib
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def assign_category(doc_id: str, category_id: int | None) -> None:
    conn = connect()
    try:
        with conn.cursor() as cur:
            if category_id is None:
                cur.execute("UPDATE t_doc SET category_id=NULL WHERE doc_id=%s", (doc_id,))
            else:
                cur.execute("SELECT id FROM t_category WHERE id=%s", (category_id,))
                if cur.fetchone() is None:
                    raise ValueError("目标分类不存在")
                cur.execute("UPDATE t_doc SET category_id=%s WHERE doc_id=%s",
                            (category_id, doc_id))
        conn.commit()
    finally:
        conn.close()


def validate_upload(filename: str, size: int) -> str | None:
    """上传口同步校验（4xx 由 api 层抛）：扩展名+大小。"""
    if not filename.lower().endswith(".pdf"):
        return "仅支持 PDF 文件"
    if size > UPLOAD_MAX_BYTES:
        return "文件超过 100MB 上限"
    if size < 10 * 1024:
        return "文件过小，疑似损坏"
    return None
