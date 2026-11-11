"""rerank 单测（m3-runbook 3.2）：纯逻辑/monkeypatch，不连真库不调 API（测试纪律 §6）。

覆盖：三级解析链（正常全排列/夹带解释文字/重复 ID/漏元素补尾/只输出前缀/完全乱码/越界）、
提示词格式与 300 词截断、缓存键敏感性、缓存命中不调 LLM、未命中写入、use_cache=False、
降级（可重试异常重试 1 次→回原序；非可重试不重试；解析全废）、空池/档位解析、cascade_input 截断。
"""
import asyncio
from types import SimpleNamespace

import httpx
import pytest
from openai import APITimeoutError

from doclens.config import settings
from doclens.retrieve import rerank as rr
from doclens.retrieve.rerank import (
    Candidate,
    RerankOutcome,
    build_prompt,
    cascade_input,
    clean_response,
    parse_ranking,
    receive_permutation,
    remove_duplicate,
    rerank_cache_key,
    truncate_words,
)


def _cands(*contents: str) -> list[Candidate]:
    """chunk_id c1..cn、doc_id d1、heading ['节A','节B'] 的候选（列表顺序 = 调用方 RRF 序）。"""
    return [
        Candidate(chunk_id=f"c{i}", doc_id="d1", page=i, kind="text",
                  heading_path=["节A", "节B"], content=content)
        for i, content in enumerate(contents, 1)
    ]


def _resp(content: str, total_tokens: int | None = 42):
    """模拟 openai ChatCompletion 响应（只带被测字段；message 只含 content，无 reasoning_content）。"""
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        usage=None if total_tokens is None else SimpleNamespace(total_tokens=total_tokens),
    )


# ---------- 三级解析链（R7） ----------

def test_clean_response_extracts_numbers_and_drops_noise():
    assert clean_response("最相关的是 [2]，其次 [1]，最后 [3]。") == [2, 1, 3]
    assert clean_response("[1] > [3] > [2]") == [1, 3, 2]      # Markdown 残渣
    assert clean_response("Answer: 2, 1") == [2, 1]
    assert clean_response("没有任何数字的输出") == []
    assert clean_response("") == []
    assert clean_response(None) == []                          # 防御：None 入参不炸


def test_clean_response_negative_sign_treated_as_noise():
    # 负号属非数字字符（清洗时替换为空格）——"-1" 只剩 1；RankGPT negative 过滤的简化等价
    assert clean_response("-1 2 -3") == [1, 2, 3]


def test_remove_duplicate_keeps_first_occurrence():
    assert remove_duplicate([2, 1, 2, 3, 1]) == [2, 1, 3]
    assert remove_duplicate([]) == []


def test_receive_permutation_filters_out_of_range_and_fills_missing():
    ids = ["a", "b", "c", "d", "e"]
    # 1-based：2→b、5→e；0/负数/越界 99 丢弃；缺失 a,c,d 按原序补尾
    assert receive_permutation([2, 5, 0, -1, 99], ids) == ["b", "e", "a", "c", "d"]
    assert receive_permutation([], ids) == ids                 # 全缺 → 原序（解析链兜底）
    assert receive_permutation([1, 2, 3], ids) == ids          # 前缀子集恒等


def test_parse_ranking_full_permutation_and_duplicates():
    ids = ["a", "b", "c"]
    assert parse_ranking("[3,1,2]", ids) == ["c", "a", "b"]       # 正常全排列
    assert parse_ranking("[1,2,2,1,3]", ids) == ["a", "b", "c"]   # 重复 ID：去重后恒等


def test_parse_ranking_with_explanatory_text():
    ids = ["a", "b", "c", "d"]
    text = "我认为最相关的是 [2]，其次是 [1]，然后 [4]，最后是 [3]。以上仅供参考。"
    assert parse_ranking(text, ids) == ["b", "a", "d", "c"]


def test_parse_ranking_missing_elements_appended_in_original_order():
    ids = ["a", "b", "c", "d", "e"]
    assert parse_ranking("[2,4]", ids) == ["b", "d", "a", "c", "e"]   # 漏元素补尾
    assert parse_ranking("[2,1]", ids) == ["b", "a", "c", "d", "e"]   # 只输出前缀


def test_parse_ranking_garbage_falls_back_to_original():
    ids = ["a", "b", "c"]
    assert parse_ranking("完全没有编号的输出", ids) == ids
    assert parse_ranking("", ids) == ids
    assert parse_ranking("[99]", ["a", "b"]) == ["a", "b"]     # 全部越界 → 补尾回原序


# ---------- 提示词 ----------

def test_build_prompt_format_and_truncation():
    long = " ".join(f"w{i}" for i in range(400))
    cands = [Candidate("c1", "d1", 3, "table", ["材料与方法", "样本"], long),
             Candidate("c2", "d2", 1, "text", None, "短正文")]
    prompt = build_prompt("什么是重排?", cands)
    assert "你是检索重排器" in prompt and "[2,1,...]" in prompt       # header 完整
    assert "Query: 什么是重排?" in prompt
    # 行格式：1-based 编号 + (doc_id,page,kind) + heading_path " / " join
    assert "[1] (d1,3,table) 材料与方法 / 样本 / w0 w1 w2" in prompt
    assert f"w{299}" in prompt and f"w{300}" not in prompt           # 只取前 300 词（RankGPT 先例）
    assert "[2] (d2,1,text) / 短正文" in prompt                      # 无 heading 时不留双空格
    assert truncate_words("a  b\n c", 2) == "a b"                    # 空白切词口径


# ---------- 缓存键（R10） ----------

def test_rerank_cache_key_sensitivity():
    c1 = _cands("内容甲", "内容乙")
    base = rerank_cache_key("m1", 512, "问题Q", c1)
    assert len(base) == 64
    assert rerank_cache_key("m1", 512, "问题Q", _cands("内容甲", "内容乙")) == base   # 稳定
    assert rerank_cache_key("m2", 512, "问题Q", c1) != base                           # 换模型
    assert rerank_cache_key("m1", 256, "问题Q", c1) != base                           # 换参数
    assert rerank_cache_key("m1", 512, "问题R", c1) != base                           # 换问题
    assert rerank_cache_key("m1", 512, "问题Q", _cands("内容甲", "内容丙")) != base   # 换候选内容
    assert rerank_cache_key("m1", 512, "问题Q", list(reversed(c1))) != base           # 候选顺序变 → 键变
    # 候选指纹只取前 300 词：301 词之后变化不影响键（与提示词截断口径一致）
    long_a = " ".join(f"w{i}" for i in range(400))
    long_b = " ".join(f"w{i}" for i in range(300)) + " tail-differs"
    assert rerank_cache_key("m", 512, "q", _cands(long_a)) == \
           rerank_cache_key("m", 512, "q", _cands(long_b))


# ---------- 缓存命中/写入（monkeypatch，不连真库） ----------

def test_rerank_cache_hit_skips_llm(monkeypatch):
    cached_row = {"model": "m1", "n_candidates": 2, "ranking": ["c2", "c1"], "degraded": True}

    def fake_get(key):
        assert len(key) == 64
        return cached_row

    def fail_llm(*a, **kw):
        raise AssertionError("缓存命中不应调用 LLM")

    monkeypatch.setattr(rr, "_cache_get", fake_get)
    monkeypatch.setattr(rr, "_chat_once", fail_llm)

    out = asyncio.run(rr.rerank_candidates("Q", _cands("甲", "乙")))
    assert isinstance(out, RerankOutcome)
    assert out.ranking == ["c2", "c1"] and out.degraded is True and out.cache_hit is True
    assert out.usage_tokens is None and out.fail_reason is None    # 缓存命中不回填历史原因
    assert out.model == settings.rerank_model_flash                # 默认 flash 档
    assert out.latency_ms >= 0


def test_rerank_cache_miss_calls_llm_and_writes(monkeypatch):
    cands = _cands("甲", "乙")
    monkeypatch.setattr(rr, "_cache_get", lambda key: None)
    puts: list[tuple] = []
    monkeypatch.setattr(rr, "_cache_put", lambda key, model, n, ranking, degraded:
                        puts.append((key, model, n, ranking, degraded)))
    monkeypatch.setattr(rr, "_chat_once",
                        lambda prompt, model, timeout, max_tokens: _resp("最相关的是 [2]，其次 [1]", 123))

    out = asyncio.run(rr.rerank_candidates("Q", cands))
    assert out.ranking == ["c2", "c1"] and out.degraded is False and out.cache_hit is False
    assert out.usage_tokens == 123 and out.fail_reason is None
    assert out.model == settings.rerank_model_flash
    expected_key = rerank_cache_key(settings.rerank_model_flash, 512, "Q", cands)
    assert puts == [(expected_key, settings.rerank_model_flash, 2, ["c2", "c1"], False)]


def test_rerank_use_cache_false_skips_cache_io(monkeypatch):
    def fail_cache(*a, **kw):
        raise AssertionError("use_cache=False 不应读写缓存")

    monkeypatch.setattr(rr, "_cache_get", fail_cache)
    monkeypatch.setattr(rr, "_cache_put", fail_cache)
    monkeypatch.setattr(rr, "_chat_once", lambda *a, **kw: _resp("[1]", 7))
    out = asyncio.run(rr.rerank_candidates("Q", _cands("甲", "乙"), use_cache=False))
    assert out.ranking == ["c1", "c2"] and out.cache_hit is False


# ---------- 失败降级（R8） ----------

def test_rerank_retries_once_then_degrades_to_original_order(monkeypatch):
    calls = {"n": 0}

    def boom(prompt, model, timeout, max_tokens):
        calls["n"] += 1
        raise APITimeoutError(request=httpx.Request("POST", "http://ark/test"))

    monkeypatch.setattr(rr, "_cache_get", lambda key: None)
    monkeypatch.setattr(rr, "_cache_put", lambda *a: None)
    monkeypatch.setattr(rr, "_chat_once", boom)
    monkeypatch.setattr(rr, "RETRY_BACKOFF_S", 0)   # 测试免 1s 退避

    out = asyncio.run(rr.rerank_candidates("Q", _cands("甲", "乙", "丙")))
    assert calls["n"] == 2                                  # 初次 + 重试 1 次（R8）
    assert out.ranking == ["c1", "c2", "c3"]                # 回调用方传入序（=RRF 序）
    assert out.degraded is True and "APITimeoutError" in (out.fail_reason or "")
    assert out.usage_tokens is None and out.cache_hit is False


def test_rerank_non_retryable_error_degrades_without_retry(monkeypatch):
    calls = {"n": 0}

    def boom(*a, **kw):
        calls["n"] += 1
        raise RuntimeError("boom")   # 非可重试（鉴权/参数/未知）：不重试直接降级

    monkeypatch.setattr(rr, "_cache_get", lambda key: None)
    monkeypatch.setattr(rr, "_cache_put", lambda *a: None)
    monkeypatch.setattr(rr, "_chat_once", boom)

    out = asyncio.run(rr.rerank_candidates("Q", _cands("甲")))
    assert calls["n"] == 1
    assert out.degraded is True and "RuntimeError" in (out.fail_reason or "")
    assert out.ranking == ["c1"]


def test_rerank_parse_garbage_marks_degraded(monkeypatch):
    monkeypatch.setattr(rr, "_cache_get", lambda key: None)
    monkeypatch.setattr(rr, "_cache_put", lambda *a: None)
    monkeypatch.setattr(rr, "_chat_once", lambda *a, **kw: _resp("抱歉，我无法完成该任务。", 10))

    out = asyncio.run(rr.rerank_candidates("Q", _cands("甲", "乙")))
    assert out.ranking == ["c1", "c2"] and out.degraded is True
    assert out.fail_reason and "全废" in out.fail_reason


def test_rerank_all_out_of_range_marks_degraded(monkeypatch):
    monkeypatch.setattr(rr, "_cache_get", lambda key: None)
    monkeypatch.setattr(rr, "_cache_put", lambda *a: None)
    monkeypatch.setattr(rr, "_chat_once", lambda *a, **kw: _resp("[9,8,7]", 10))

    out = asyncio.run(rr.rerank_candidates("Q", _cands("甲", "乙")))
    assert out.ranking == ["c1", "c2"] and out.degraded is True   # 全部越界 = 零可用信号


# ---------- 空池 / 档位 / 级联 ----------

def test_rerank_empty_candidates_no_llm(monkeypatch):
    def fail_llm(*a, **kw):
        raise AssertionError("空池不应调用 LLM")

    monkeypatch.setattr(rr, "_chat_once", fail_llm)
    out = asyncio.run(rr.rerank_candidates("Q", []))
    assert out.ranking == [] and out.degraded is False and out.cache_hit is False


def test_rerank_unknown_tier_raises():
    with pytest.raises(ValueError):
        asyncio.run(rr.rerank_candidates("Q", _cands("甲"), model_tier="turbo"))


def test_rerank_pro_tier_uses_pro_model(monkeypatch):
    monkeypatch.setattr(rr, "_cache_get", lambda key: None)
    monkeypatch.setattr(rr, "_cache_put", lambda *a: None)
    seen: dict = {}

    def fake_chat(prompt, model, timeout, max_tokens):
        seen["model"] = model
        return _resp("[1]", 1)

    monkeypatch.setattr(rr, "_chat_once", fake_chat)

    out = asyncio.run(rr.rerank_candidates("Q", _cands("甲"), model_tier="pro"))
    assert out.model == settings.rerank_model_pro and seen["model"] == settings.rerank_model_pro
    # pro 键与 flash 键不同（换模型不串缓存）
    assert rerank_cache_key(settings.rerank_model_pro, 512, "Q", _cands("甲")) != \
           rerank_cache_key(settings.rerank_model_flash, 512, "Q", _cands("甲"))


def test_cascade_input_truncates_preserving_order():
    cands = _cands("甲", "乙", "丙", "丁", "戊")
    assert [c.chunk_id for c in cascade_input(cands, top=3)] == ["c1", "c2", "c3"]  # 截断保持序
    assert cascade_input(cands) == cands            # 默认 top=15 > 5：全量
    assert cascade_input(cands, top=15) == cands
    assert cascade_input(cands, top=0) == []
    assert cascade_input(cands, top=-2) == []
