"""qdrant_store 单测（m2-runbook 2.4）：点 ID 确定性 + 档位映射（纯逻辑，不连 Qdrant）。

集成验收（建集合/上传/过滤查询/同 doc 重跑点数不变）走容器真实调用，见 2.7/2.8。
"""
import uuid

from doclens.index.qdrant_store import IMAGE_COLLECTION, TIER_KINDS, TEXT_COLLECTION, point_id


def test_point_id_deterministic():
    """uuid5(chunk_id)：同输入永远同 ID（upsert 幂等的根基）。"""
    a = point_id("abc123def456:0001")
    b = point_id("abc123def456:0001")
    assert a == b
    assert uuid.UUID(a).version == 5
    # 不同 chunk_id → 不同 ID；合法 UUID 格式
    assert point_id("abc123def456:0002") != a


def test_tier_kinds_mapping():
    """A/B 档 kind 过滤口径（K5：不建多余集合）。"""
    assert TIER_KINDS["A"] == ["text"]
    assert set(TIER_KINDS["B"]) == {"text", "table", "caption"}
    assert TEXT_COLLECTION == "doclens_text" and IMAGE_COLLECTION == "doclens_image"
