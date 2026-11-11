"""contextual 单测（m2-runbook 2.6）：分层抽样纯逻辑（试产名额分配）+ 提示词装配。不调 API。"""
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
