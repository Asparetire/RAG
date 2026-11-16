"""M5 失败归因（m5-runbook K9；F0–F6 首个失败环节定位）。

输入：评测题 + trace JSONL + t_eval_result → 每道错题的归因。
判定顺序（取首个失败环节）：
  F0 出题错（gold 未命中但 ref_answer 支持——题目本身有问题）
  F1 解析缺失（gold 关键句不在 parsed 产物）
  F2 召回缺失（gold chunk 不在融合池）
  F3 融合错排（gold 在池中但排名 >final_top 且检索分数正常）
  F4 重排伤害（融合池 top 内→重排后掉出）
  F5 生成失败（检索到位但答案无引用/引用错/内容不符）
  F6 兜底误触发（可答题被拒答）
"""

from __future__ import annotations

import json
from pathlib import Path

TRACES_DIR = Path("/home/doclens/RAG/data/traces")


def load_trace(trace_id: str) -> dict:
    """按 trace_id 从 traces-*.jsonl 回放子事件流 → {kind: payload}。"""
    events = {}
    for f in sorted(TRACES_DIR.glob("traces-*.jsonl")):
        with f.open(encoding="utf-8") as fh:
            for line in fh:
                if trace_id not in line:
                    continue
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue
                kind = d.get("kind")
                if kind:
                    events[kind] = d
        if "llm_fallback" in events:
            break
    return events


def attribute_one(q: dict, res: dict, trace: dict) -> str:
    """判定一道错题的归因（res=run_pipeline 结果，trace=回放的事件流）。"""
    answerable = q.get("answerable", True)
    refused = res.get("refused")
    gold_ids = {g.get("chunk_id") for g in q.get("gold", []) if g.get("chunk_id")}

    if answerable and refused:
        # judge 拒答——判上下文是否真缺（gold chunk 是否进了 sources）
        sources = {s.get("chunk_id") for s in trace.get("context", {}).get("sources", [])}
        if gold_ids & sources:
            return "F6"  # 证据在上下文里却拒答=兜底误触发
        # gold 不在 sources——检索层就没找到
        fused = {h.get("chunk_id") for h in trace.get("fused", {}).get("fused", [])}
        if gold_ids & fused:
            return "F3"  # 融合池有但组装丢失（截断/组归并牺牲）
        return "F2"  # 召回缺失
    if not answerable and not refused:
        return "F6"  # 不可答但没拒=兜底未触发（反向）
    if res.get("cited") and res.get("answer"):
        # 有引用有答案但判错——生成内容质量（faithfulness 低分题）
        return "F5"
    if not res.get("cited"):
        return "F5"  # 无引用=生成未锚定
    return "F5"


def attribute_run(run_id: str, questions: list[dict], results_by_qid: dict) -> dict:
    """整个 run 的归因分布：错题逐题定位 → Counter。"""
    from collections import Counter
    dist = Counter()
    details = []
    for q in questions:
        qid = q.get("q_id")
        res = results_by_qid.get(qid)
        if res is None:
            continue
        # 错题定义：answerable 但 F1 低 或 refused；unanswerable 但没拒
        answerable = q.get("answerable", True)
        wrong = (answerable and not res.get("refused") and res.get("answer_f1", 0) < 0.3) \
            or (not answerable and not res.get("refused")) \
            or (answerable and res.get("refused"))
        if not wrong:
            continue
        trace = load_trace(res.get("trace_id", ""))
        f = attribute_one(q, res, trace)
        dist[f] += 1
        details.append({"q_id": qid, "stage": f, "question": q["question"][:80]})
    return {"distribution": dict(dist), "details": details}
