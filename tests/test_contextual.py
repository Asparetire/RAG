"""contextual 单测（m2-runbook 2.6）：分层抽样纯逻辑（试产名额分配）+ 提示词装配 + 失败隔离。不调 API。"""
import asyncio

import doclens.index.contextual as ctx
from doclens.index.contextual import CTX_PROMPT_TEMPLATE, stratified_sample


def make_units(n_text=800, n_table=125, n_caption=202):
    units = []
    seq = 0
    for k, n in (("text", n_text), ("table", n_table), ("caption", n_caption)):
        for i in range(n):
            units.append({"chunk_id": f"d:{seq:04d}", "kind": k, "content": f"{k} {i}",
                          "heading_path": ["S"]})
            seq += 1
    return units


def test_stratified_sample_100_proportional():
    units = make_units()  # 800/125/202 ≈ 1127
    picked = stratified_sample(units, n=100)
    assert len(picked) == 100
    kinds = [u["kind"] for u in picked]
    # 各层都有代表（text 最多、caption 次之、table 最少）
    assert kinds.count("text") > kinds.count("caption") > kinds.count("table") >= 1
    # chunk_id 唯一
    ids = [u["chunk_id"] for u in picked]
    assert len(set(ids)) == 100


def test_stratified_sample_small_total_returns_all():
    units = make_units(n_text=30, n_table=5, n_caption=10)  # 45 < 100
    picked = stratified_sample(units, n=100)
    assert len(picked) == 45


def test_stratified_sample_excludes_image_and_empty():
    units = make_units(n_text=90, n_table=10, n_caption=10)
    units += [{"chunk_id": "d:9900", "kind": "image", "content": "", "heading_path": []}]
    units += [{"chunk_id": "d:9901", "kind": "text", "content": "  ", "heading_path": []}]
    picked = stratified_sample(units, n=100)
    assert all(u["kind"] in ("text", "table", "caption") for u in picked)
    assert all(u["content"].strip() for u in picked)


def test_prompt_template_fields():
    s = CTX_PROMPT_TEMPLATE.format(doc_title="T", heading="A / B", chunk="chunk body")
    assert "T" in s and "A / B" in s and "chunk body" in s
    assert "只输出前缀本身" in s  # 防解释污染


def test_generate_prefixes_failure_isolation(monkeypatch):
    """m-11：单块 LLM 调用重试耗尽 → 跳过不落库、不影响其余块成功落库（缓存跳过/落库均 monkeypatch，不连真库）。"""
    monkeypatch.setattr(ctx, "CTX_RETRIES", 2)
    monkeypatch.setattr(ctx, "CTX_BACKOFF_BASE", 0.0)  # 退避 0s，测试不等待
    monkeypatch.setattr(ctx, "OpenAI", lambda **kwargs: object())  # 不触真实客户端
    monkeypatch.setattr(ctx, "_prefix_get_existing", lambda ids, model: set())
    saved: dict[str, str] = {}
    monkeypatch.setattr(ctx, "_prefix_put_many",
                        lambda rows: saved.update({r[0]: r[1] for r in rows}))

    calls: list[str] = []

    def fake_gen_one(client, doc_title, chunk):
        calls.append(chunk["chunk_id"])
        if chunk["chunk_id"] == "d:0001":
            raise RuntimeError("LLM 瞬时 429")
        return f"前缀-{chunk['chunk_id']}"

    monkeypatch.setattr(ctx, "_gen_one", fake_gen_one)

    chunks = [
        {"chunk_id": "d:0000", "content": "a", "heading_path": ["S"]},
        {"chunk_id": "d:0001", "content": "b", "heading_path": ["S"]},
        {"chunk_id": "d:0002", "content": "c", "heading_path": ["S"]},
    ]
    done = asyncio.run(ctx.generate_prefixes("T", chunks))
    # 失败条目：重试 CTX_RETRIES 次后仍不在返回值、不落库
    assert calls.count("d:0001") == 2
    assert "d:0001" not in done and "d:0001" not in saved
    # 成功条目不受影响：返回且落库，各只调 1 次
    assert done == {"d:0000": "前缀-d:0000", "d:0002": "前缀-d:0002"}
    assert saved["d:0000"] == "前缀-d:0000" and saved["d:0002"] == "前缀-d:0002"
    assert calls.count("d:0000") == 1 and calls.count("d:0002") == 1
