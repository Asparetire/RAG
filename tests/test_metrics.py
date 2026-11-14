"""M5 指标口径单测（固定排序→已知指标值；全项目测试密度最高处）。"""

from __future__ import annotations

from doclens.eval.metrics import (answer_f1, citation_recall_stats,
                                  context_precision_ap, faithfulness_from_statements,
                                  mrr, ndcg_at_k, recall_at_k, success_at_k)

RANKED = ["a", "b", "c", "d", "e"]
REL = {"b", "d"}


def test_recall_at_k_trec_denominator():
    """TREC 分母=全部相关（不截断到 k）。"""
    assert recall_at_k(RANKED, REL, 1) == 0.0
    assert recall_at_k(RANKED, REL, 2) == 0.5     # b 命中 / 2 相关
    assert recall_at_k(RANKED, REL, 4) == 1.0     # b+d 全命中


def test_success_at_k():
    assert success_at_k(RANKED, REL, 1) == 0.0
    assert success_at_k(RANKED, REL, 2) == 1.0


def test_mrr():
    assert mrr(RANKED, REL) == 0.5        # 首个相关在第 2 位
    assert mrr(RANKED, {"a"}) == 1.0
    assert mrr(RANKED, {"z"}) == 0.0


def test_ndcg_at_k():
    """b(位2)=1/log2(3)≈0.63, d(位4)=1/log2(5)≈0.43 → nDCG≈1.06/1.63…手算校验。"""
    got = ndcg_at_k(RANKED, REL, 10)
    import math
    dcg = 1 / math.log2(3) + 1 / math.log2(5)
    idcg = 1 / math.log2(2) + 1 / math.log2(3)
    assert abs(got - dcg / idcg) < 1e-9


def test_answer_f1_squad():
    assert answer_f1("the cat sat on the mat", ["the cat sat on the mat"]) == 1.0
    got = answer_f1("the cat sat", ["the cat sat on the mat"])
    # P=1.0, R=0.5 → F1=2/3（手算校验）
    assert abs(got - 2 / 3) < 1e-9
    assert answer_f1("完全无关的答案", ["the cat sat on the mat"]) == 0.0
    assert answer_f1("a b", ["c d", "a b c"]) == answer_f1("a b", ["a b c"])  # 多参考取 max


def test_faithfulness():
    stmts = [{"statement": "s1", "verdict": True},
             {"statement": "s2", "verdict": False},
             {"statement": "s3", "verdict": True}]
    assert faithfulness_from_statements(stmts) == 2 / 3
    assert faithfulness_from_statements([]) == 0.0


def test_context_precision_ap():
    """AP：有用位 1,3 → (1/1 + 2/3)/2 = 5/6。"""
    assert abs(context_precision_ap([True, False, True]) - 5 / 6) < 1e-9
    assert context_precision_ap([False, False]) == 0.0


def test_citation_recall_stats():
    """两句：第一句有引用且支持、第二句无引用→recall=0.5。"""
    answer = "第一句有引用。第二句没有引用。"
    per_sentence_chunks = [{"被引原文，支持第一句"}, set()]
    res = citation_recall_stats(answer, per_sentence_chunks,
                                nli_fn=lambda premise, claim: "支持" in premise)
    assert res["total_sentences"] == 2
    assert res["supported_sentences"] == 1
    assert abs(res["recall"] - 0.5) < 1e-9
