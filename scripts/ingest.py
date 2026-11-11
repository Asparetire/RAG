"""全量/增量入库编排（m2-runbook 2.7；§3.1 增量语义）。

流程（每篇）：
  doc.json hash 对比 t_doc → 未变整篇跳过（零 API + 零写入）
  → chunk_doc 切块 → 文本单元嵌入（缓存先行）/ 图像单元嵌入（长边>1024px 先降采样，调研 R4）
  → Qdrant 先删后插（uuid5 点 ID）→ MySQL t_chunk 先删后插 → t_doc upsert
收尾：BM25 从 t_chunk 全量重建（~1500 块秒级）+ 汇总输出（API 次数/缓存命中/点数——2.8 验收证据）。

用法（容器内 doclens 环境）：
    python scripts/ingest.py            # 全量；重跑即增量（doc 级跳过）
    python scripts/ingest.py --force    # 忽略 doc 级跳过、全部重建（嵌入缓存仍生效，不重复计费）
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import io
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from doclens.config import PARSED_DIR
from doclens.index import qdrant_store as qs
from doclens.index import bm25 as B
from doclens.index.chunker import chunk_doc
from doclens.index.db import connect
from doclens.index.embeddings import EmbeddingClient
from doclens.parse.schema import DoclensDoc

IMAGE_LONG_EDGE = 1024  # 调研 R4：仅长边 >1024px 的图降采样（小图原样嵌入防扰动）


def _file_hash(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _image_file(doc_dir: Path, image_path: str) -> Path:
    """image_path → 文件路径（防越界：S4-03，将来接外部解析产物时防任意文件读）。"""
    p = (doc_dir / image_path).resolve()
    if not p.is_relative_to(doc_dir.resolve()):
        raise ValueError(f"image_path 越界: {image_path!r}")
    return p


def _downsample_bytes(path: Path) -> bytes | None:
    """长边 > IMAGE_LONG_EDGE 时降采样为 JPEG bytes；否则 None（原样读）。"""
    from PIL import Image

    with Image.open(path) as im:
        if max(im.size) <= IMAGE_LONG_EDGE:
            return None
        im.thumbnail((IMAGE_LONG_EDGE, IMAGE_LONG_EDGE))
        buf = io.BytesIO()
        im.convert("RGB").save(buf, format="JPEG", quality=90)
        return buf.getvalue()


def _chunk_rows(doc: DoclensDoc, chunks: list) -> list[tuple]:
    """t_chunk 行：bbox/heading_path 走 JSON 列。"""
    rows = []
    for c in chunks:
        rows.append((
            c.chunk_id, doc.doc_id, c.kind, c.content, c.page,
            json.dumps(c.bbox) if c.bbox else None,
            json.dumps(c.heading_path, ensure_ascii=False) if c.heading_path else None,
            c.image_path, c.caption, c.content_hash,
        ))
    return rows


def _write_chunks(conn, doc: DoclensDoc, rows: list[tuple], doc_hash: str) -> None:
    """t_doc 先 upsert（外键父表），t_chunk 先删后插——单事务原子提交（S3 Major-1）。

    autocommit 连接下用 conn.begin() 显式开事务：三步要么全部生效、要么全部回滚。
    否则 t_doc（带新 doc_hash）先落库、t_chunk 中途失败 → 增量重跑被 hash 判等静默跳过，
    文档将永久缺失于 BM25/回表（击穿 2.8 幂等验收）。
    """
    with conn.begin():
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO t_doc (doc_id, title, doi, sha256, doc_hash, n_chunks) "
                "VALUES (%s,%s,%s,%s,%s,%s) "
                "ON DUPLICATE KEY UPDATE title=VALUES(title), doi=VALUES(doi), "
                "sha256=VALUES(sha256), doc_hash=VALUES(doc_hash), n_chunks=VALUES(n_chunks)",
                (doc.doc_id, doc.title, doc.doi, doc.sha256, doc_hash, len(rows)),
            )
            cur.execute("DELETE FROM t_chunk WHERE doc_id=%s", (doc.doc_id,))
            cur.executemany(
                "INSERT INTO t_chunk (chunk_id, doc_id, kind, content, page, bbox, "
                "heading_path, image_path, caption, content_hash) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                rows,
            )
    # conn.begin() 上下文退出即提交；失败自动回滚，无需显式 commit/rollback


def process_doc(client: EmbeddingClient, qclient, conn, doc_dir: Path, force: bool) -> dict:
    """处理单篇：返回统计 {doc_id, skipped, n_units, n_img, downsampled}。"""
    doc_json = doc_dir / "doc.json"
    doc = DoclensDoc.load(doc_json)
    dh = _file_hash(doc_json)

    with conn.cursor() as cur:
        cur.execute("SELECT doc_hash FROM t_doc WHERE doc_id=%s", (doc.doc_id,))
        row = cur.fetchone()
    if row and row[0] == dh and not force:
        return {"doc_id": doc.doc_id, "skipped": True}

    chunks = chunk_doc(doc)
    text_units = [c for c in chunks if c.kind in ("text", "table", "caption")]
    # 图像单元：路径越界/文件缺失的直接跳过并记日志（S4-03 防越界；保持嵌入批对齐）
    img_pairs: list[tuple] = []
    for c in chunks:
        if c.kind != "image":
            continue
        try:
            p = _image_file(doc_dir, c.image_path) if c.image_path else None
        except ValueError as e:
            print(f"  [警告] {doc.doc_id} {e}——跳过该图像单元")
            continue
        if p is not None and p.exists():
            img_pairs.append((c, p))
        else:
            print(f"  [警告] {doc.doc_id} 图像文件缺失: {c.image_path!r}——跳过该图像单元")

    # Qdrant 先删后插（变更文档）
    qs.delete_doc_points(qclient, doc.doc_id)

    async def embed_all() -> tuple[list, list]:
        vecs_t = await client.embed_texts([c.content for c in text_units])
        blobs, reused = [], []
        for _c, p in img_pairs:
            small = await asyncio.to_thread(_downsample_bytes, p)
            blobs.append(small if small is not None else p.read_bytes())
            reused.append(small is not None)
        vecs_i = await client.embed_image_blobs(blobs)
        return vecs_t, vecs_i

    vecs_t, vecs_i = asyncio.run(embed_all())

    units = []
    for c, v in zip(text_units, vecs_t):
        units.append({"chunk_id": c.chunk_id, "kind": c.kind, "vec": v, "doc_id": doc.doc_id,
                      "page": c.page, "heading_path": c.heading_path})
    for (c, _p), v, ds in zip(img_pairs, vecs_i, reused):
        units.append({"chunk_id": c.chunk_id, "kind": "image", "vec": v, "doc_id": doc.doc_id,
                      "page": c.page, "heading_path": c.heading_path,
                      "image_path": c.image_path, "caption": c.caption, "downsampled": ds})
    written = qs.upsert_units(qclient, units)

    _write_chunks(conn, doc, _chunk_rows(doc, chunks), dh)
    return {
        "doc_id": doc.doc_id, "skipped": False, "n_text": len(text_units), "n_img": len(img_pairs),
        "downsampled": sum(1 for f in reused if f), "written": written,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="DocLens 全量/增量入库（m2-runbook 2.7）")
    ap.add_argument("--force", action="store_true", help="忽略 doc 级跳过、全部重建（嵌入缓存仍生效）")
    args = ap.parse_args()

    doc_dirs = sorted(d for d in PARSED_DIR.iterdir()
                      if d.is_dir() and (d / "doc.json").exists())
    if not doc_dirs:
        print("[错误] data/parsed 下无解析产物")
        return 1

    client = EmbeddingClient()
    qclient = qs._client()
    conn = connect()
    qs.ensure_collections(qclient)
    t0 = time.perf_counter()
    results = []
    try:
        for d in doc_dirs:
            r = process_doc(client, qclient, conn, d, args.force)
            tag = "跳过(未变)" if r["skipped"] else f"入库 text={r['n_text']} img={r['n_img']} 降采样={r['downsampled']}"
            print(f"{r['doc_id']}: {tag}")
            results.append(r)
        # BM25 从 t_chunk 全量重建（单一事实源；~1500 块秒级）
        units = B.load_units_from_db()
        idx = B.build_index(units)
        B.save_index(idx, meta_rows=[{"chunk_id": u["chunk_id"], "doc_id": u["doc_id"],
                                      "kind": u["kind"]} for u in units])
        print(f"BM25 重建: {len(units)} 文本单元 → {B.BM25_DIR}")
    finally:
        conn.close()
        qclient.close()

    # 收尾汇总（2.8 幂等验收证据）
    dt = time.perf_counter() - t0
    skipped = sum(1 for r in results if r["skipped"])
    total_units = sum(r.get("n_text", 0) + r.get("n_img", 0) for r in results)
    print("=== 汇总 ===")
    print(f"文档: {len(results)} 篇（跳过 {skipped}）；本轮入库单元 {total_units}")
    print(f"嵌入 API 调用: {client.stats['api_calls']}；缓存命中: {client.stats['cache_hits']}")
    qclient2 = qs._client()
    try:
        print(f"Qdrant 点数: {qs.TEXT_COLLECTION}={qclient2.count(qs.TEXT_COLLECTION).count}, "
              f"{qs.IMAGE_COLLECTION}={qclient2.count(qs.IMAGE_COLLECTION).count}")
    finally:
        qclient2.close()
    print(f"总耗时 {dt:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
