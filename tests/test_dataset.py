"""M5 出题质量闸单测（m5-runbook K2；纯函数零外部依赖）。"""

from __future__ import annotations

from doclens.eval.dataset import anchor_check, anchor_via_quote, bm25_pseudo_check, dedup_check


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


def test_anchor_rewritten_ref_still_passes_via_gold_coverage():
    """试审批 20/20 覆没的修正：VLM 出题常态=改写 ref_answer（非抄写）——
    双向锚定的 gold 覆盖分支必须放行这类题。"""
    gold = ["Kapur and Otsu methods are widely used optimal threshold selection techniques "
            "for image segmentation in the hybrid bio-inspired algorithm."]
    ref = ("该研究采用 Kapur 熵准则与 Otsu 类间方差两种经典方法作为混合算法的适应度函数，"
           "用于多级阈值分割场景。")  # 中文改写——字符级覆盖低，但 gold 覆盖分支不看这个
    # 中文 ref 对英文 gold：ref 侧滑窗必然 miss → 走 gold 覆盖分支也不该过（语言不同）
    # 真正要测的是：英文改写 ref（词序重组）能过
    ref_en = ("multilevel thresholds serve as fitness functions in the hybrid algorithm, "
              "combining Otsu inter-class variance with Kapur entropy criterion")
    assert anchor_check(ref_en, gold) is True


def test_anchor_via_quote_is_authoritative():
    """quote（VLM 逐字摘抄的原文依据句）锚定优先且可靠。"""
    gold = ["The proposed BFHS algorithm combines BFO and HS with a new update rule."]
    assert anchor_via_quote("The proposed BFHS algorithm combines BFO and HS", gold) is True
    assert anchor_via_quote("This quote is completely unrelated to the passage", gold) is False
    assert anchor_via_quote("", gold) is False


def test_bm25_pseudo_gap_detected():
    """质量闸③：gold 断层第一（3 倍+）= 字面重叠伪题。"""
    assert bm25_pseudo_check(gold_rank=1, gold_score=12.0, runner_up=3.0) is True
    assert bm25_pseudo_check(gold_rank=1, gold_score=12.0, runner_up=8.0) is False
    assert bm25_pseudo_check(gold_rank=3, gold_score=12.0, runner_up=1.0) is False


def test_bm25_pseudo_no_runner_up():
    """只有一个候选时无断层可言（不算伪题）。"""
    assert bm25_pseudo_check(gold_rank=1, gold_score=12.0, runner_up=None) is False

