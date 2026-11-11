"""citations 单测（m3-runbook §3.4 K6）：四类格式、[1,2] 双编号、区间展开、越界降级、句切、映射。"""
from doclens.generate.citations import map_to_sources, parse_citations
from doclens.generate.context import SourceBlock


def test_format_single():
    r = parse_citations("依据[1]作答。", {1, 2, 3})
    assert r.cited == [1] and r.has_any and not r.degraded_sentences


def test_format_comma_pair_alce_pitfall():
    """ALCE 原版 re.findall(r"\\[\\d+") 对 [1,2] 只拿到 1——本实现两条都必须在。"""
    r = parse_citations("结论[1,2]。", {1, 2, 3})
    assert r.cited == [1, 2]


def test_format_adjacent_brackets():
    r = parse_citations("结论[1][2]。", {1, 2, 3})
    assert r.cited == [1, 2]


def test_format_range_expansion():
    r = parse_citations("见[1-3]。", {1, 2, 3, 4})
    assert r.cited == [1, 2, 3]
    # 中文逗号/空格变体
    r2 = parse_citations("见[1，2]。", {1, 2})
    assert r2.cited == [1, 2]
    r3 = parse_citations("见[1, 2]。", {1, 2})
    assert r3.cited == [1, 2]


def test_out_of_range_degrades_sentence_not_answer():
    """无效 n → 所在句降级标记，不静默删、不重写答案；有效引用照常收集。"""
    ans = "第一句[1]。第二句提到[9]。第三句[2]。"
    r = parse_citations(ans, {1, 2})
    assert r.cited == [1, 2]
    assert len(r.degraded_sentences) == 1
    assert r.degraded_sentences[0].bad_ids == [9]
    assert "[9]" in r.degraded_sentences[0].sentence          # 原句保留
    assert any("[9]" in s.sentence for s in r.per_sentence)   # per_sentence 原文不删


def test_zero_and_negative_ids_degrade():
    r = parse_citations("A[0]。B[-3]。C[1]。", {1})
    assert r.cited == [1]
    assert len(r.degraded_sentences) == 2
    assert r.degraded_sentences[0].bad_ids == [0]
    assert r.degraded_sentences[1].bad_ids == [-3]


def test_mixed_sentence_valid_and_invalid():
    """同句混有有效/无效引用：句子降级，但有效编号仍进 cited。"""
    r = parse_citations("混句[1,9]。", {1})
    assert r.cited == [1]
    assert len(r.degraded_sentences) == 1 and r.degraded_sentences[0].bad_ids == [9]


def test_sentence_split_mixed_punctuation():
    """中英文句末标点都能切：。!? 三句。"""
    r = parse_citations("中文一句[1]。English two [2]! 第三[3]?", {1, 2, 3})
    assert len(r.per_sentence) == 3
    assert r.cited == [1, 2, 3]


def test_decimal_number_not_split():
    """英文 "." 后跟数字不切句（93.5% 保持完整）。"""
    r = parse_citations("准确率为 93.5%[2]。", {2})
    assert len(r.per_sentence) == 1 and r.cited == [2]


def test_no_citation_answer_ok():
    """无引用答案不报错：has_any=False，report 原样返回（兜底由 fallback 处理）。"""
    r = parse_citations("没有任何引用的回答。", {1})
    assert r.cited == [] and r.has_any is False
    assert r.degraded_sentences == []
    assert len(r.per_sentence) == 1 and r.per_sentence[0].ids == []


def test_map_to_sources_with_bbox():
    sources = [
        SourceBlock(source_n=1, chunk_id="c1", doc_id="dA", kind="text", page=1,
                    heading_path=None, content="x", image_path=None,
                    bbox=[0.1, 0.2, 0.3, 0.4]),
        SourceBlock(source_n=2, chunk_id="c2", doc_id="dA", kind="caption", page=3,
                    heading_path=None, content="y", image_path="images/f.jpg",
                    bbox=None),
    ]
    r = parse_citations("答[2,1]。", {1, 2})
    refs = map_to_sources(r, sources)
    assert [(x.source_n, x.chunk_id) for x in refs] == [(2, "c2"), (1, "c1")]  # 首次出现序
    assert refs[0].page == 3 and refs[0].bbox is None
    assert refs[1].bbox == [0.1, 0.2, 0.3, 0.4]


def test_map_to_sources_skips_unmapped():
    """valid_ids 与 sources 不一致（调用方双保险场景）：无匹配 SourceBlock 的编号跳过。"""
    sources = [SourceBlock(source_n=1, chunk_id="c1", doc_id="dA", kind="text",
                           page=1, heading_path=None, content="x")]
    r = parse_citations("答[1,5]。", {1, 5})   # 5 ∈ valid_ids 但没有 SourceBlock 5
    refs = map_to_sources(r, sources)
    assert [(x.source_n, x.chunk_id) for x in refs] == [(1, "c1")]
    assert refs[0].doc_id == "dA" and refs[0].page == 1
