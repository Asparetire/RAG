"""embeddings 单测（m2-runbook 2.3）：纯逻辑部分（缓存键/向量序列化/响应解析），不连真库不调 API。"""
import asyncio

import pytest

from doclens.config import CORPUS_TEXT_INSTRUCTION, settings
from doclens.index import embeddings as emb
from doclens.index.embeddings import (
    EmbedError,
    EmbeddingClient,
    _extract_embedding,
    bytes_to_vec,
    cache_key,
    vec_to_bytes,
)


def test_cache_key_stable_and_sensitive():
    k1 = cache_key("m", "instr", 2048, "hello")
    k2 = cache_key("m", "instr", 2048, "hello")
    assert k1 == k2 and len(k1) == 64
    # 任一字段变化 → 键变（模型/指令/维度/内容四要素全纳入）
    assert cache_key("m2", "instr", 2048, "hello") != k1
    assert cache_key("m", "instr2", 2048, "hello") != k1
    assert cache_key("m", "instr", 1024, "hello") != k1
    assert cache_key("m", "instr", 2048, "hellp") != k1


def test_vec_roundtrip():
    vec = [0.25, -1.5, 3.125, 0.0, 1e-7] * 410  # 2050 维（非整千）
    blob = vec_to_bytes(vec)
    assert len(blob) == len(vec) * 4
    back = bytes_to_vec(blob)
    assert len(back) == len(vec)
    for a, b in zip(vec, back):
        assert a == pytest.approx(b, rel=1e-6, abs=1e-9)


def test_extract_embedding_dual_format():
    dict_body = {"data": {"embedding": [0.1, 0.2]}}          # 方舟 multimodal 实测格式
    list_body = {"data": [{"embedding": [0.3, 0.4]}]}        # OpenAI 风格
    assert _extract_embedding(dict_body) == [0.1, 0.2]
    assert _extract_embedding(list_body) == [0.3, 0.4]
    with pytest.raises(EmbedError):
        _extract_embedding({"data": []})
    with pytest.raises(EmbedError):
        _extract_embedding({"error": "x"})


def test_embed_batch_partial_failure_caches_successes(monkeypatch):
    """m-10：批内一条最终失败 → 已成功兄弟请求的向量先落缓存再抛错（429 长退避下整批重跑不重付费）。"""
    monkeypatch.setattr(emb, "_cache_get_many", lambda keys: {})
    saved_rows: list[tuple] = []
    monkeypatch.setattr(emb, "_cache_put_many", lambda rows: saved_rows.extend(rows))

    async def fake_post_one(self, client, item):
        if item["text"] == "bad":
            raise EmbedError("重试 6 次后仍失败：HTTP 429")
        return [0.1, 0.2]

    monkeypatch.setattr(EmbeddingClient, "_post_one", fake_post_one)

    client = EmbeddingClient()
    with pytest.raises(EmbedError):
        asyncio.run(client.embed_texts(["good", "bad"]))
    # 成功条目已落缓存（键=good 的缓存键、dim=2），失败条目不落
    good_key = cache_key(settings.embed_model, CORPUS_TEXT_INSTRUCTION,
                         settings.embed_dimensions, "good")
    assert [(r[0], r[3]) for r in saved_rows] == [(good_key, 2)]
    assert client.stats["api_calls"] == 2  # 发起数口径（n-5）：失败那条也计入
