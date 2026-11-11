"""trace.py 单测（m3-runbook K8/R15）：JSONL 落盘、脱敏边界、崩溃安全（纯逻辑，不连真库）。"""

from __future__ import annotations

import json

from doclens import trace as T


def test_append_event_writes_jsonl(tmp_path):
    path = T.append_event("q-1", "routes", {"dense_text": [{"chunk_id": "d:0001", "score": 0.42, "rank": 1}]},
                          trace_dir=tmp_path)
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    ev = json.loads(lines[0])
    assert ev["query_id"] == "q-1" and ev["kind"] == "routes"
    assert ev["dense_text"][0]["score"] == 0.42
    assert "ts" in ev


def test_append_event_dataclass_and_unknown_types(tmp_path):
    from dataclasses import dataclass

    @dataclass
    class Hit:
        chunk_id: str
        score: float

    # 未知类型（object）转 str 不抛错——trace 不能炸主链路
    class Weird:
        def __str__(self):
            return "weird!"

    path = T.append_event("q-2", "context", {"hit": Hit("d:0001", 0.5), "blob": Weird()},
                          trace_dir=tmp_path)
    ev = json.loads(path.read_text(encoding="utf-8").strip())
    assert ev["hit"] == {"chunk_id": "d:0001", "score": 0.5}
    assert ev["blob"] == "weird!"


def test_query_id_deterministic_per_day_grouping():
    a = T.query_id("什么是 Kapur 方法？", "D")
    b = T.query_id("什么是 Kapur 方法？", "D")
    c = T.query_id("什么是 Kapur 方法？", "A")
    assert a == b          # 同问题同档 → 同 id（可归组）
    assert a != c          # 不同档 → 不同 id
    assert "-D-" in a and "-A-" in c


def test_no_secret_leakage_in_payload(tmp_path):
    """脱敏纪律：payload 由调用方构造，本模块不该"帮忙"读取任何环境/配置值——
    这里验证显式传入的 dict 才会落盘（不存在隐式 settings 注入面）。"""
    import inspect

    src = inspect.getsource(T)
    assert "settings" not in src, "trace 模块不得依赖 settings（脱敏：只写调用方传入的数据）"
