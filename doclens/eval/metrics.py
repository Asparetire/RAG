"""M5 指标计算（m5-runbook K5；口径全部来自调研 §11/§2.3 权威出处）。

检索指标（ir-measures 口径 [L8]）：
- recall@k：分母=全部相关数（不截断到 k——TREC 口径，报告须声明）
- success@k：top-k 命中与否（常见混用名为"recall"，本项目两者都报）
- mrr：首个相关文档位次倒数
- ndcg@10：DCG=Σrel/log₂(i+1)（pytrec_eval 默认公式，报告注明）

生成指标：
- answer_f1：SQuAD token-F1（QASPER 口径 [K1]，多参考取 max）
- faithfulness（RAGAS 自实现 [L1]）：答案→原子陈述→逐条 NLI vs 被引上下文
- citation recall/precision（ALCE 口径 [L6]）：句子级支持判定+必要性检验
"""

from __future__ import annotations

import math
import re


# ---------- 检索指标（纯规则） ----------

def recall_at_k(ranked: list[str], relevant: set[str], k: int) -> float:
    """TREC 口径 recall@k：分母=全部相关数（不截断）。"""
    if not relevant:
        return 0.0
    return len(set(ranked[:k]) & relevant) / len(relevant)


def success_at_k(ranked: list[str], relevant: set[str], k: int) -> float:
    """Success@k：top-k 内命中任意相关文档（0/1——单查询粒度，聚合后为命中率）。"""
    return 1.0 if set(ranked[:k]) & relevant else 0.0


def mrr(ranked: list[str], relevant: set[str]) -> float:
    for i, cid in enumerate(ranked, 1):
        if cid in relevant:
            return 1.0 / i
    return 0.0


def ndcg_at_k(ranked: list[str], relevant: set[str], k: int = 10) -> float:
    """nDCG@10，DCG=Σrel/log₂(i+1)（pytrec_eval 默认 log2 公式 [L8]）。二值相关。"""
    def dcg(ids: list[str]) -> float:
        return sum(1.0 / math.log2(i + 1) for i, cid in enumerate(ids[:k], 1)
                   if cid in relevant)
    ideal = [1.0] * min(len(relevant), k)
    idcg = sum(1.0 / math.log2(i + 1) for i in range(1, len(ideal) + 1))
    if idcg <= 0:
        return 0.0
    return dcg(ranked) / idcg


# ---------- 生成指标 ----------

def _tokens(s: str) -> list[str]:
    """SQuAD 风格 token 化（小写+去标点）。"""
    return re.sub(r"[^\w\s]", "", (s or "").lower()).split()


def answer_f1(prediction: str, references: list[str]) -> float:
    """SQuAD token-F1，多参考取 max（QASPER 口径 [K1]）。"""
    pt = _tokens(prediction)
    best = 0.0
    for ref in references:
        rt = _tokens(ref)
        if not pt or not rt:
            continue
        common = set(pt) & set(rt)
        if not common:
            continue
        precision = len(common) / len(pt)
        recall = len(common) / len(rt)
        best = max(best, 2 * precision * recall / (precision + recall))
    return best


def _split_sentences(text: str) -> list[str]:
    """切句：中英句末标点（ALCE 用 NLTK 英文规则，自备中英兼容）。"""
    parts = re.split(r"(?<=[.。!?！？])\s*", (text or "").strip())
    return [p.strip() for p in parts if p.strip()]


def citation_recall_stats(answer: str, cited_chunks_by_sentence: list[set[str]],
                          nli_fn) -> dict:
    """ALCE citation recall（[L6]）：每句被引文档拼接→NLI 判支持→被支持句占比。

    cited_chunks_by_sentence：与 _split_sentences(answer) 对齐的每句被引 chunk 内容
    集合（无引用句=空集）。nli_fn(premise, claim)->bool（能直接推出=True）。
    """
    sentences = _split_sentences(answer)
    supported = total = 0
    details = []
    for sent, chunks in zip(sentences, cited_chunks_by_sentence + [set()] * 10):
        if len(details) >= len(sentences):
            break
        total += 1
        if not chunks:
            details.append({"sentence": sent[:60], "supported": False, "no_citation": True})
            continue
        premise = " ".join(sorted(chunks))
        ok = bool(nli_fn(premise, sent))
        supported += ok
        details.append({"sentence": sent[:60], "supported": ok})
    return {"recall": supported / total if total else 0.0,
            "total_sentences": total, "supported_sentences": supported,
            "details": details}


# ---------- RAGAS 口径（自实现，NLI/拆陈述由调用方注入 LLM 函数） ----------

def faithfulness_from_statements(statements: list[dict], total: int | None = None) -> float:
    """RAGAS faithfulness（[L1]）：statements=[{statement, verdict(bool 可推出)}]，
    得分=可推出数/总数。"""
    if total is None:
        total = len(statements)
    if not total:
        return 0.0
    return sum(1 for s in statements if s.get("verdict")) / total


def context_precision_ap(usefulness_by_rank: list[bool]) -> float:
    """RAGAS context_precision（[L2]）：AP 口径——按排序逐位判有用，
    分子=Σ(命中位 i 的前缀命中率)，分母=命中总数。"""
    hits = 0
    ap = 0.0
    for i, useful in enumerate(usefulness_by_rank, 1):
        if useful:
            hits += 1
            ap += hits / i
    return ap / hits if hits else 0.0
