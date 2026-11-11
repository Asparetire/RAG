"""fallback 单测（m3-runbook §3.4 K7）：judge 三分支、坏 JSON 放行、force_refuse、self_check 正反例。"""
import asyncio
from types import SimpleNamespace

from doclens.generate import fallback
from doclens.generate.context import assemble
from doclens.generate.fallback import (
    REFUSAL_TEXT,
    JudgeVerdict,
    decide_fallback,
    judge_sufficiency,
    self_check,
)


def _ctx():
    ms = {"c1": {"chunk_id": "c1", "doc_id": "d", "kind": "text", "page": 1,
                 "content": "正文", "image_path": None, "caption": None,
                 "bbox": None, "heading_path": None}}
    return assemble("问题", ["c1"], ms)


def _resp(content):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))], usage=None)


def test_decide_refuses_on_insufficient():
    d = decide_fallback("Q", _ctx(), JudgeVerdict(sufficient=False, reason="缺关键表格"))
    assert d.refused is True and d.reason == "缺关键表格"


def test_decide_allows_on_sufficient():
    d = decide_fallback("Q", _ctx(), JudgeVerdict(sufficient=True, reason="上下文充分"))
    assert d.refused is False


def test_decide_allows_on_none():
    """judge=None（未跑 judge）→ 放行（R13：误拒伤害更大）。"""
    d = decide_fallback("Q", _ctx(), None)
    assert d.refused is False


def test_decide_force_refuse_for_tests():
    d = decide_fallback("Q", _ctx(), JudgeVerdict(sufficient=True, reason="x"), force_refuse=True)
    assert d.refused is True and "force_refuse" in d.reason


def test_refusal_text_constant():
    assert REFUSAL_TEXT == "根据现有文档库，未能找到足以回答该问题的依据。"


def _patch_judge(monkeypatch, raw=None, error=None):
    class Comp:
        async def create(self, **kw):
            if error is not None:
                raise error
            return _resp(raw)

    monkeypatch.setattr(fallback, "AsyncOpenAI",
                        lambda **kw: SimpleNamespace(chat=SimpleNamespace(completions=Comp())))


def test_judge_parses_bare_json(monkeypatch):
    _patch_judge(monkeypatch, raw='{"sufficient": false, "reason": "缺少实验数据"}')
    v = asyncio.run(judge_sufficiency("Q", _ctx()))
    assert v.sufficient is False and v.reason == "缺少实验数据" and v.judge_ok is True
    d = decide_fallback("Q", _ctx(), v)
    assert d.refused is True


def test_judge_parses_fenced_json(monkeypatch):
    _patch_judge(monkeypatch, raw='```json\n{"sufficient": true, "reason": "证据充分"}\n```')
    v = asyncio.run(judge_sufficiency("Q", _ctx()))
    assert v.sufficient is True and v.reason == "证据充分" and v.judge_ok is True


def test_judge_bad_json_defaults_to_allow(monkeypatch):
    """坏 JSON → 放行（R13 先压误拒），judge_ok=False 供 trace 标记。"""
    _patch_judge(monkeypatch, raw="抱歉，我无法按要求输出 JSON。")
    v = asyncio.run(judge_sufficiency("Q", _ctx()))
    assert v.sufficient is True and v.judge_ok is False and "放行" in v.reason
    assert decide_fallback("Q", _ctx(), v).refused is False


def test_judge_api_error_defaults_to_allow(monkeypatch):
    """judge 调用异常（网络/超时）→ 放行。"""
    _patch_judge(monkeypatch, error=RuntimeError("connection refused"))
    v = asyncio.run(judge_sufficiency("Q", _ctx()))
    assert v.sufficient is True and v.judge_ok is False and "放行" in v.reason


def test_judge_non_bool_sufficient_defaults_to_allow(monkeypatch):
    _patch_judge(monkeypatch, raw='{"sufficient": "yes", "reason": "x"}')
    v = asyncio.run(judge_sufficiency("Q", _ctx()))
    assert v.sufficient is True and v.judge_ok is False


def test_self_check_positive_and_negative():
    ctx = _ctx()  # 只有 Source 1
    assert self_check("根据[1]可以得出结论。", ctx) is True
    assert self_check("没有任何引用的回答。", ctx) is False          # 无引用
    assert self_check("引用越界[3]的回答。", ctx) is False           # 引用的 n 越界
    assert self_check("部分越界[1][3]。", ctx) is False              # 混有越界引用
