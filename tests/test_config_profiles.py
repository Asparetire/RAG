"""档位注册表语义锁定（m3-runbook K8；PRD §7.1 消融阶梯的防线单测）。

这些断言锁定 A–F 六档的开关语义：M5 消融的结论可信度依赖"档位差异只来自
阶梯定义的组件增量"。config.py 的 PROFILES 改动若破坏阶梯语义，这里先红。
"""

from __future__ import annotations

from doclens.config import ABLATION_TIERS, PROFILES


def test_tier_ladder_semantics():
    """A→F 阶梯增量：图像路 C 起、重排 D 起、ctx 前缀 E 起、多模态重排仅 F。"""
    a, b, c, d, e, f = (PROFILES[k] for k in "ABCDEF")
    # A：纯文本（无图像路，BM25 开）
    assert a.text_kinds == ("text",) and a.use_image_route is False and a.use_bm25
    assert a.rerank is None and a.use_ctx_prefix is False and a.multimodal_rerank is False
    # B：+ table/caption 文本（图像路仍关）
    assert b.text_kinds == ("text", "table", "caption") and b.use_image_route is False
    # C：+ 图像嵌入路
    assert c.use_image_route is True and c.rerank is None
    # D：+ 重排（flash 默认；pro 为对比位，由 CLI 参数切换）
    assert d.rerank == "flash" and d.use_ctx_prefix is False
    # E：+ 块级上下文前缀
    assert e.rerank == "flash" and e.use_ctx_prefix is True and e.multimodal_rerank is False
    # F：+ 多模态重排（P1）
    assert f.multimodal_rerank is True


def test_profiles_share_knobs_and_desc():
    """共享旋钮默认一致（防某档被意外改召回量/融合器导致口径漂移）。"""
    for p in PROFILES.values():
        assert p.per_route_top == 30 and p.fused_pool == 50
        assert p.rerank_input == 30 and p.final_top == 20
        assert p.max_images == 5 and p.fusion == "rrf" and p.rrf_k == 2
        assert p.desc == ABLATION_TIERS[p.name]
    assert sorted(PROFILES) == list("ABCDEF")
