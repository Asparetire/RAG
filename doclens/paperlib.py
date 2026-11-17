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
import unicodedata
from datetime import datetime
from pathlib import Path

from doclens.config import DATA_DIR, PARSED_DIR, settings
from doclens.index.db import connect

MAX_CATEGORY_DEPTH = 3          # FastGPT maxFolderDepth 同款（根=1 层）
STALE_TASK_SECONDS = 3600       # 启动扫描阈值：processing 超 1h 视为中断（open-webui 口径）
UPLOAD_MAX_BYTES = 100 * 1024 * 1024  # MaxKB 口径 100MB
MAX_BATCH_FILES = 20            # 批量上传单批上限（任务列表/线程量级保护；2026-11-17 批量入库）

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
            cur.execute("SELECT COUNT(*) FROM t_doc WHERE category_id=%s AND deleted_at IS NULL",
                        (cat_id,))
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


def ensure_default_category_and_assign(doc_id: str) -> int:
    """未指定分类的论文归入"未分类"（4.8 体检：NULL 与未分类节点语义对齐——
    不留 NULL，否则前端点"未分类"标签过滤不到）。"""
    cat_id = ensure_default_category()
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE t_doc SET category_id=%s WHERE doc_id=%s", (cat_id, doc_id))
        conn.commit()
        return cat_id
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
                "WHERE d.deleted_at IS NULL "
                "ORDER BY d.doc_id")
            return [{"doc_id": r[0], "title": r[1] or r[0], "n_chunks": r[2],
                     "category_id": r[3], "category_name": r[4],
                     "status": r[5] or "completed"}
                    for r in cur.fetchall()]
    finally:
        conn.close()


def list_trash() -> list[dict]:
    """垃圾桶清单（m6-trash）：仅已删除文档，按删除时间倒序。"""
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT doc_id, title, n_chunks, category_id, deleted_at "
                "FROM t_doc WHERE deleted_at IS NOT NULL ORDER BY deleted_at DESC")
            return [{"doc_id": r[0], "title": r[1] or r[0], "n_chunks": r[2],
                     "category_id": r[3], "deleted_at": r[4]}
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


def list_active_tasks() -> list[dict]:
    """任务区数据源（4.8 体检增补：上传后论文未进 t_doc 前也要在库里可见——RAGFlow
    范式的"列表顶部显示 uploading/processing 状态机"）。

    R1 失败可见性（2026-11-17，调研 [D4]）：error 任务此前被 SQL 过滤——失败瞬间
    从 UI 消失、重试无从下手。现纳入 24h 内的 error 行；终态不驱动前端轮询
    （PaperLibrary 轮询条件同步改为仅非终态）。
    S4 L-3（2026-11-17 安全复查）：LIMIT 200 有界化（防异常自堆撑大响应体），
    DESC 取最新再回正序展示。"""
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, batch_id, filename, status, progress, progress_msg, error, doc_id "
                "FROM t_ingest_task WHERE status IN ('queued','parsing','indexing') "
                "OR (status='error' AND updated_at > NOW() - INTERVAL 1 DAY) "
                "ORDER BY id DESC LIMIT 200")
            return [{"task_id": r[0], "batch_id": r[1], "filename": r[2], "status": r[3],
                     "progress": r[4], "progress_msg": r[5], "error": r[6], "doc_id": r[7]}
                    for r in reversed(cur.fetchall())]
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


# ---------- 论文删除与回收站（m6-trash；方案 B：软删+检索面移除） ----------

_ACTIVE_TASK_STATUSES = ("queued", "parsing", "indexing")


class PaperNotFoundError(ValueError):
    """doc_id 库中无行——API 层映射 404（格式非法仍是 ValueError → 422，审查 m-2）。"""


def _get_doc_row(doc_id: str):
    """(doc_id, deleted_at) 或 None；格式非法直接抛 ValueError。"""
    import re

    if not re.fullmatch(r"[0-9a-f]{12}", doc_id or ""):
        raise ValueError(f"doc_id 格式非法：{doc_id!r}（应为 12 位十六进制）")
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT doc_id, deleted_at FROM t_doc WHERE doc_id=%s", (doc_id,))
            return cur.fetchone()
    finally:
        conn.close()


def _raise_if_ingesting(doc_id: str) -> None:
    """R5 守卫：最新入库任务进行中 → 拒绝删除/清理（防与入库线程竞争）。"""
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT status FROM t_ingest_task WHERE doc_id=%s ORDER BY id DESC LIMIT 1",
                (doc_id,))
            row = cur.fetchone()
    finally:
        conn.close()
    if row and row[0] in _ACTIVE_TASK_STATUSES:
        raise ValueError("该论文正在入库（排队/解析/索引中），请稍后再操作")


def soft_delete_doc(doc_id: str, user_id: str | None = None) -> dict:
    """删除进垃圾桶（m6-trash D2 + B-1 修复重序）：打 deleted_at 标记 → 摘检索面。

    顺序关键（B-1）：BM25 语料源按 deleted_at 过滤（bm25.load_units_from_db），
    打标必须先于重建——否则重建语料仍含已删文档，检索面摘除不成立。
    Qdrant 摘点与 BM25 重建均幂等，重复删除=重放自愈（部分失败状态可补齐）；
    DB 行与磁盘资产原地保留，垃圾桶期内可随时恢复（paperless-ngx 同款语义）。
    """
    row = _get_doc_row(doc_id)
    if row is None:
        raise PaperNotFoundError("论文不存在")
    with _INGEST_LOCK:
        _raise_if_ingesting(doc_id)
        # 1) 打标（语料过滤生效；WHERE 幂等——重复删除不重复置值）
        conn = connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE t_doc SET deleted_at=CURRENT_TIMESTAMP, deleted_by=%s "
                    "WHERE doc_id=%s AND deleted_at IS NULL",
                    (user_id, doc_id))
        finally:
            conn.close()
        # 2) 摘 Qdrant 点位（幂等）
        from doclens.index import bm25 as B
        from doclens.index import qdrant_store as qs
        qclient = qs._client()
        try:
            removed = qs.delete_doc_points(qclient, doc_id)
        finally:
            qclient.close()
        # 3) BM25 重建（语料源已过滤 → 已删文档自然出局）
        B.bm25_rebuild()
    return {"ok": True, "removed_points": removed}


def restore_doc(doc_id: str) -> dict:
    """从垃圾桶恢复（m6-trash D3 + B-1 修复重序）：清 deleted_at → 重放索引 → BM25 重建。

    顺序与软删对称（B-1）：先清标记使语料过滤放行，再 process_doc(force=True)
    重放（嵌入缓存命中 → 零 API 费用），最后 BM25 重建。恢复窗口内列表先可见、
    检索秒级就绪。进行中任务守卫防与入库线程竞争（审查 M-2）。
    """
    row = _get_doc_row(doc_id)
    if row is None:
        raise PaperNotFoundError("论文不存在")
    if row[1] is None:
        raise ValueError("该论文不在垃圾桶中")
    with _INGEST_LOCK:
        _raise_if_ingesting(doc_id)
        from doclens.index import bm25 as B
        from doclens.index import qdrant_store as qs
        parsed_root = PARSED_DIR / doc_id
        if not (parsed_root / "doc.json").is_file():
            raise ValueError("解析产物缺失，无法恢复——请重新上传原 PDF 入库")
        # 1) 清标记（语料过滤放行；research L61 原定顺序）
        conn = connect()
        try:
            with conn.cursor() as cur:
                cur.execute("UPDATE t_doc SET deleted_at=NULL WHERE doc_id=%s", (doc_id,))
        finally:
            conn.close()
        # 2) 重放索引（force=True：doc_hash 未变时增量语义会零写入 → 点位不回来，
        #    容器冒烟实证；嵌入缓存命中 → 零 API 费用）
        from doclens.index.embeddings import EmbeddingClient
        from scripts.ingest import process_doc
        client = EmbeddingClient()
        qclient = qs._client()
        conn = connect()
        try:
            qs.ensure_collections(qclient)
            process_doc(client, qclient, conn, parsed_root, force=True)
        finally:
            conn.close()
            qclient.close()
        # 3) BM25 重建（语料源已放行 → 本文档自然回位）
        B.bm25_rebuild()
        pdf_ok = (DATA_DIR / "pdfs" / f"{doc_id}.pdf").is_file()
    return {"ok": True, "pdf_ok": pdf_ok}


def purge_doc(doc_id: str) -> dict:
    """彻底删除（m6-trash D4 + 审查 M-1/M-2 修复）：仅限垃圾桶内文档。

    顺序（不可逆点最后）：Qdrant 幂等重放 → DB 三条 DELETE 包显式事务
    （autocommit 下必须 conn.begin()，审查 M-1）→ 删解析产物（失败记日志留孤儿，
    审查 m-5）→ PDF 移 data/trash_files/ 兜底。R5 守卫拒绝进行中任务（审查 M-2）。
    """
    row = _get_doc_row(doc_id)
    if row is None:
        raise PaperNotFoundError("论文不存在")
    if row[1] is None:
        raise ValueError("该论文不在垃圾桶中（须先删除进垃圾桶，再彻底删除）")
    with _INGEST_LOCK:
        _raise_if_ingesting(doc_id)
        from doclens.index import qdrant_store as qs
        qclient = qs._client()
        try:
            qs.delete_doc_points(qclient, doc_id)
        finally:
            qclient.close()
        conn = connect()
        try:
            conn.begin()
            try:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM t_doc WHERE doc_id=%s", (doc_id,))
                    cur.execute("DELETE FROM t_ctx_prefix WHERE chunk_id LIKE %s", (f"{doc_id}:%",))
                    cur.execute("DELETE FROM t_ingest_task WHERE doc_id=%s", (doc_id,))
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        finally:
            conn.close()
        import logging
        try:
            shutil.rmtree(PARSED_DIR / doc_id)
        except OSError as e:
            logging.getLogger(__name__).warning(
                "purge %s：解析产物清理失败（孤儿目录可重试清除）：%s", doc_id, e)
        pdf = DATA_DIR / "pdfs" / f"{doc_id}.pdf"
        if pdf.is_file():
            backup_dir = DATA_DIR / "trash_files"
            backup_dir.mkdir(parents=True, exist_ok=True)
            shutil.move(str(pdf), str(backup_dir / f"{doc_id}.pdf"))
    return {"ok": True}


# ---------- 单篇入库编排（复用 M1/M2 零件） ----------

def _run_ingest(task_id: int, pdf_path: Path, category_id: int | None) -> None:
    """后台任务体：校验去重 → MinerU 解析 → 索引入库 → BM25 重建 → 状态落库。

    同步阻塞实现（线程内执行）：MinerU subprocess/嵌入调用都是慢 IO，线程足够；
    _INGEST_LOCK 串行化防并发重复建索引。异常 → status=error + error 文本。
    线程入口先建独立事件循环（process_doc 内部用 asyncio.run 跑嵌入——宿主线程
    若已有循环会 RuntimeError；M5 QASPER 批量入库实测发现）。
    """
    import asyncio
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        pass  # 无循环（正常线程）
    else:  # 线程带着循环被启动 → 换新循环
        asyncio.set_event_loop(asyncio.new_event_loop())
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
            # S3 体检：retry 时 pdf_path 即 canonical（重试传 canonical 路径）——
            # 同文件不自拷（SameFileError）
            if pdf_path.resolve() != canonical.resolve():
                shutil.copy2(pdf_path, canonical)
            update_task(task_id, doc_id=doc_id, status="parsing", progress=0.05,
                        progress_msg="校验通过，开始解析")
            # 去重：t_doc 已有同 doc_id → 直接归档跳过解析（m6-trash M-2：垃圾桶内
            # 文档不归档不挂分类——报错引导先恢复，防"任务完成"改写垃圾桶内文档分类）
            from doclens.index.db import connect
            conn = connect()
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT deleted_at FROM t_doc WHERE doc_id=%s", (doc_id,))
                    dup = cur.fetchone()
            finally:
                conn.close()
            if dup:
                if dup[0] is not None:
                    raise ValueError("该论文在垃圾桶中，请先恢复后再上传/重试（与已入库论文同内容）")
                update_task(task_id, status="completed", progress=1.0,
                            progress_msg="与已入库论文内容相同（sha256 重复），已归入分类",
                            completed_chunks=None, total_chunks=None)
                if category_id:
                    assign_category(doc_id, category_id)
                _cleanup_inbox_file(pdf_path)
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

            # 4) BM25 全量重建（~1500 块秒级；m6-trash D5：三连抽公共函数）
            from doclens.index import bm25 as B
            B.bm25_rebuild()

            # 5) 分类归属 + 完成态
            if category_id:
                assign_category(doc.doc_id, category_id)
            else:
                # 未指定分类 → 归入"未分类"节点（4.8 体检：NULL 与未分类节点语义对齐）
                ensure_default_category_and_assign(doc.doc_id)
            # 标题兜底（4.8 交互优化）：MinerU 提取失败时从 markdown 一级标题回填
            if not (doc.title or "").strip():
                from doclens.paperlib import backfill_title_from_markdown as _bf
                backfill_title_from_markdown(doc.doc_id)
            update_task(task_id, status="completed", progress=1.0,
                        progress_msg=f"入库完成 text={r['n_text']} img={r['n_img']}",
                        completed_chunks=r["n_text"], total_chunks=r["n_text"] + r["n_img"])
            # R4：消费即清（paperless-ngx [P1]）——成功后清 inbox 原件（canonical 保留）
            _cleanup_inbox_file(pdf_path)
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


def _cleanup_inbox_file(pdf_path: Path) -> bool:
    """R4（对照 paperless-ngx"消费即清"，[P1]）：入库成功后清理 inbox 原件。

    仅删 pdfs_inbox 下的文件——重试等路径传的是 canonical（data/pdfs/），
    绝不能误删 canonical；失败任务保留 inbox 供人工排查。返回是否删除。
    """
    try:
        p = Path(pdf_path)
        if p.resolve().parent == (DATA_DIR / "pdfs_inbox").resolve() and p.is_file():
            p.unlink()
            return True
    except OSError:
        pass
    return False


def sweep_old_inbox_files(days: int = 7) -> int:
    """R4 启动清理：inbox 里超过 days 天的遗留原件删除（重试链路用的是 canonical，
    inbox 原件成败皆不再回看——2026-11-16 b056 实证只写不清、永久堆积）。
    返回删除数。"""
    inbox = DATA_DIR / "pdfs_inbox"
    if not inbox.is_dir():
        return 0
    cutoff = time.time() - days * 86400
    n = 0
    for p in inbox.iterdir():
        try:
            if p.is_file() and p.stat().st_mtime < cutoff:
                p.unlink()
                n += 1
        except OSError:
            continue
    return n


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


def rename_paper(doc_id: str, title: str) -> None:
    """论文重命名（用户 UI 操作；S4 约定：标题长度校验+入库参数化）。"""
    title = (title or "").strip()
    if not title or len(title) > 256:
        raise ValueError("标题需为 1–256 字符")
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM t_doc WHERE doc_id=%s", (doc_id,))
            if cur.fetchone()[0] == 0:
                raise ValueError("论文不存在")
            cur.execute("UPDATE t_doc SET title=%s WHERE doc_id=%s", (title, doc_id))
        conn.commit()
    finally:
        conn.close()


def backfill_title_from_markdown(doc_id: str) -> str | None:
    """解析完成后 title 为空 → 从 parsed markdown 的一级标题回填（QASPER 12 篇
    空标题的泛化解；提取失败返回 None——调用方保留 doc_id 回退显示）。"""
    md = PARSED_DIR / doc_id / "markdown.md"
    if not md.exists():
        return None
    best = ""
    for line in md.read_text(encoding="utf-8").splitlines()[:15]:
        s = line.strip()
        if s.startswith("# ") and len(s) > len(best):
            best = s[2:].strip()
    if not best or len(best) > 256:
        return None
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE t_doc SET title=%s WHERE doc_id=%s AND (title IS NULL OR title='')",
                        (best, doc_id))
        conn.commit()
        return best
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


def read_upload_capped(upload_file, filename: str) -> tuple[bytes | None, str | None]:
    """S4 M-2（2026-11-17 批量上传安全复查，M4-02 记池项闭环）：先取 size 校验上限
    再读内容——防"先整读后校验"（>100MB 的 part 先全量进 RAM 再被拒 → OOM 面）。

    upload_file.file 为 Starlette SpooledTemporaryFile，可 seek。返回
    (contents, None) 或 (None, 错误文案)。
    """
    f = upload_file.file
    f.seek(0, 2)  # SEEK_END
    size = f.tell()
    f.seek(0)
    err = validate_upload(filename, size)
    if err:
        return None, err
    contents = f.read(UPLOAD_MAX_BYTES + 1)
    if len(contents) > UPLOAD_MAX_BYTES:  # size 报告与实际不符时的兜底（畸形 part）
        return None, "文件超过 100MB 上限"
    return contents, None


def _safe_basename(filename: str, max_bytes: int = 200) -> str:
    """S4 L-1（2026-11-17 批量上传安全复查）：上传文件名净化。

    NFC 归一 + 删控制/格式字符（\\n 合法文件名、U+202E 显示倒序欺骗）+ 分隔符剔除
    （穿越面已由调用方闭合，此处管落盘/DB 卫生）+ UTF-8 字节截断（ext4 与
    VARCHAR(255) 均 255 字节上限——超长 OSError 正是 L-1 触发 M-1 泄露的源头）。
    """
    s = unicodedata.normalize("NFC", filename or "")
    s = "".join(ch for ch in s
                if unicodedata.category(ch) not in ("Cc", "Cf")
                and ch not in "/\\<>:\"|?*")  # S3 M-3：Windows 保留字符（FR-7.1 交付面）
    s = s.strip() or "paper.pdf"
    had_pdf = s.lower().endswith(".pdf")
    raw = s.encode("utf-8")
    if len(raw) > max_bytes:
        limit = max_bytes - (4 if had_pdf else 0)  # 预留 .pdf 后缀的 4 字节
        s = raw[:limit].decode("utf-8", errors="ignore") or "paper.pdf"
    if had_pdf and not s.lower().endswith(".pdf"):
        s += ".pdf"
    return s
