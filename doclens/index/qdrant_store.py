"""Qdrant 集合管理与入库（m2-runbook 2.4；K5 两集合 + uuid5 幂等点 ID）。

设计（§3.1 数据链路）：
- 两集合：doclens_text（2048, cosine；text/table/caption 单元，kind 过滤实现 A/B 档）
        + doclens_image（329 图图像向量，payload 带 image_path/caption/bbox）；
- 点 ID = uuid5(chunk_id)——同 chunk 永远同 ID，upsert 天然幂等（Qdrant 官方推荐模式，
  调研 §3 先例：OneUptime deterministic point ids + Qdrant Points 文档）；
- 正文/bbox 不进 text payload：命中后按 chunk_id 回表 t_chunk 取（M3 生成、M4 高亮共用）；
- 先删后插：变更文档按 doc_id filter 删除旧点再 upsert（§3.1 增量语义）。
"""

from __future__ import annotations

import uuid

from qdrant_client import QdrantClient, models
from qdrant_client.http import exceptions as qdrant_errors

from doclens.config import settings

TEXT_COLLECTION = "doclens_text"
IMAGE_COLLECTION = "doclens_image"
DIM = settings.embed_dimensions

# A/B 档 kind 过滤（K5：不建多余集合）
TIER_KINDS: dict[str, list[str] | None] = {
    "A": ["text"],                      # 纯文本
    "B": ["text", "table", "caption"],  # + 图表文字代理
}


def point_id(chunk_id: str) -> str:
    """chunk_id → 确定性 UUID（uuid5，同输入永远同 ID）。"""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"doclens:{chunk_id}"))


def _client() -> QdrantClient:
    return QdrantClient(
        url=settings.qdrant_url, api_key=settings.qdrant_api_key or None, timeout=30
    )


def ensure_collections(client: QdrantClient | None = None) -> list[str]:
    """两集合幂等创建（vector/cosine + payload 索引字段），返回集合名列表。"""
    own = client is None
    c = client or _client()
    try:
        existing = {col.name for col in c.get_collections().collections}
        for name in (TEXT_COLLECTION, IMAGE_COLLECTION):
            if name not in existing:
                c.create_collection(
                    collection_name=name,
                    vectors_config=models.VectorParams(size=DIM, distance=models.Distance.COSINE),
                )
        # kind 过滤与 doc 级删除都要走 payload 索引
        for name, field in ((TEXT_COLLECTION, "kind"), (TEXT_COLLECTION, "doc_id"),
                            (IMAGE_COLLECTION, "doc_id")):
            try:
                c.create_payload_index(name, field, models.PayloadSchemaType.KEYWORD)
            except (qdrant_errors.ApiException, qdrant_errors.ResponseHandlingException,
                    qdrant_errors.UnexpectedResponse) as e:
                # n-15：只吞 qdrant 异常（索引已存在/旧版无此 API），记日志不静默；
                # 连接错误（httpx 系）不再被吞，直接暴露
                print(f"[警告] create_payload_index {name}.{field} 跳过（已存在或旧版无此 API）: {e}")
        return sorted(n for n in (TEXT_COLLECTION, IMAGE_COLLECTION))
    finally:
        if own:
            c.close()


def delete_doc_points(client: QdrantClient, doc_id: str) -> int:
    """按 doc_id 删两集合旧点（先删后插的"先删"）。返回删除前的点数（对账用）。"""
    total = 0
    for name in (TEXT_COLLECTION, IMAGE_COLLECTION):
        cnt = client.count(name, count_filter=models.Filter(
            must=[models.FieldCondition(key="doc_id", match=models.MatchValue(value=doc_id))]),
            exact=True).count
        if cnt:
            client.delete(name, points_selector=models.FilterSelector(filter=models.Filter(
                must=[models.FieldCondition(key="doc_id", match=models.MatchValue(value=doc_id))])))
        total += cnt
    return total


def upsert_units(client: QdrantClient, units: list[dict]) -> dict[str, int]:
    """按集合 upsert 单元（units: chunk 模型 dict，含 kind/vec/payload 字段）。

    units 元素：{chunk_id, kind, vec, doc_id, page, heading_path, image_path, caption,
                content(text/table/caption 的正文——不入 payload，此处仅日志对账用)}
    返回各集合写入点数。
    """
    text_points, image_points = [], []
    for u in units:
        pid = point_id(u["chunk_id"])
        if u["kind"] == "image":
            image_points.append(models.PointStruct(
                id=pid, vector=u["vec"],
                payload={"doc_id": u["doc_id"], "chunk_id": u["chunk_id"],
                         "image_path": u.get("image_path"), "caption": u.get("caption"),
                         "page": u.get("page"), "bbox": u.get("bbox")}))
        else:  # text/table/caption → doclens_text，kind 过滤实现 A/B 档
            text_points.append(models.PointStruct(
                id=pid, vector=u["vec"],
                payload={"doc_id": u["doc_id"], "chunk_id": u["chunk_id"], "kind": u["kind"],
                         "page": u.get("page"), "heading_path": u.get("heading_path") or []}))
    written: dict[str, int] = {}
    for name, pts in ((TEXT_COLLECTION, text_points), (IMAGE_COLLECTION, image_points)):
        if pts:
            for i in range(0, len(pts), 200):  # 分批 upsert
                client.upsert(name, points=pts[i:i + 200], wait=True)
        written[name] = len(pts)
    return written


def search_tier(client: QdrantClient, vec: list[float], tier: str = "B", top: int = 20,
                doc_ids: list[str] | None = None) -> list[models.ScoredPoint]:
    """文本集合按档位检索（A=text，B=text+table+caption；FR-2.7 元数据过滤留 doc_ids 参数）。"""
    if tier not in TIER_KINDS:
        # n-15：未知 tier 一律报错——原实现静默等价 B 档，消融实验数据会被静默污染
        raise ValueError(f"未知 search_tier: {tier!r}（可选: {sorted(TIER_KINDS)}）")
    must = []
    kinds = TIER_KINDS[tier]
    if kinds:
        must.append(models.FieldCondition(key="kind", match=models.MatchAny(any=kinds)))
    if doc_ids:
        must.append(models.FieldCondition(key="doc_id", match=models.MatchAny(any=doc_ids)))
    return client.query_points(
        TEXT_COLLECTION, query=vec, limit=top,
        query_filter=models.Filter(must=must) if must else None,
    ).points
