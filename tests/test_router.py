"""router 单测（m3-runbook 3.3）：语言检测三态 + 占比边界 + BM25 旁路决策（纯函数）。"""
from __future__ import annotations

from doclens.config import PROFILES
from doclens.retrieve.router import bm25_weight_for, detect_lang


def test_detect_lang_pure_zh():
    """纯中文 → zh。"""
    assert detect_lang("今天的天气怎么样") == "zh"
    assert detect_lang("什么是检索增强生成") == "zh"


def test_detect_lang_pure_en():
    """纯英文（无中文字符）→ en。"""
    assert detect_lang("What is BERT?") == "en"
    assert detect_lang("hybrid retrieval with RRF fusion") == "en"


def test_detect_lang_mixed_lean_zh():
    """中英混排：少量英文专名不把占比拉到 0.3 以下 → zh（D11 判 zh 预期）。

    "什么是 BERT 模型？"共 12 字符、5 个汉字 → 5/12 ≈ 0.417 ≥ 0.3。
    """
    assert detect_lang("什么是 BERT 模型？") == "zh"


def test_detect_lang_mixed_lean_en():
    """英文为主、夹两个汉字：2/10 = 0.2 < 0.3 → en。"""
    assert detect_lang("This is a 测试") == "en"


def test_detect_lang_boundary_exact_threshold():
    """占比恰为 0.3（≥ 含边界）→ zh；略低于 0.3 → en。"""
    # 3/10 = 0.30 → zh（阈值含边界）
    assert detect_lang("一二三abcdefg") == "zh"
    # 3/11 ≈ 0.273 < 0.3 → en
    assert detect_lang("一二三abcdefgh") == "en"


def test_detect_lang_empty_string():
    """空串 → en（纯函数约定，不抛错）。"""
    assert detect_lang("") == "en"


def test_detect_lang_punct_only():
    """无任何中文字符（纯标点/数字/空白）→ en。"""
    assert detect_lang("?! 123 ...") == "en"


def test_bm25_weight_zh_bypass():
    """zh → 0.0（D11：BM25 旁路，整路不跑）。"""
    assert bm25_weight_for("zh", PROFILES["B"]) == 0.0


def test_bm25_weight_en_normal():
    """en → None（正常参与融合；0.5 降权档留 M5，本模块不返回）。"""
    assert bm25_weight_for("en", PROFILES["B"]) is None


def test_bm25_weight_unknown_lang_safe_default():
    """未知 lang 按正常处理（None）——旁路只对确认的 zh 生效，宁多召回不误杀。"""
    assert bm25_weight_for("fr", PROFILES["B"]) is None
