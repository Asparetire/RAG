"""M5 出题质量闸单测（m5-runbook K2；纯函数零外部依赖）。"""

from __future__ import annotations

from doclens.eval.dataset import anchor_check, bm25_pseudo_check, dedup_check


def test_dedup_similar_question_blocked():
    """质量闸①：3-gram Jaccard 高相似的题被拦。"""
    existing = ["What is the capital of France and its population?"]
    assert dedup_check("What is the capital of France and its population?", existing) is False


def test_dedup_different_question_passes():
    existing = ["What is the capital of France?"]
    assert dedup_check("How does gradient descent optimize neural networks?", existing) is True


def test_anchor_ref_in_gold_passes():
    ref = "The paper proposes a hybrid method for image segmentation using multilevel thresholds"
    gold = ["Kapur and Otsu methods are used for the hybrid method for image segmentation "
            "using multilevel thresholds as fitness functions."]
    assert anchor_check(ref, gold) is True


def test_anchor_ref_not_in_gold_fails():
    ref = "The answer mentions quantum entanglement in cryptographic protocols explicitly here"
    gold = ["Completely unrelated text about preprocessing steps and feature extraction methods."]
    assert anchor_check(ref, gold) is False


def test_bm25_pseudo_gap_detected():
    """质量闸③：gold 断层第一（3 倍+）= 字面重叠伪题。"""
    assert bm25_pseudo_check(gold_rank=1, gold_score=12.0, runner_up=3.0) is True
    assert bm25_pseudo_check(gold_rank=1, gold_score=12.0, runner_up=8.0) is False
    assert bm25_pseudo_check(gold_rank=3, gold_score=12.0, runner_up=1.0) is False


def test_bm25_pseudo_no_runner_up():
    """只有一个候选时无断层可言（不算伪题）。"""
    assert bm25_pseudo_check(gold_rank=1, gold_score=12.0, runner_up=None) is False
