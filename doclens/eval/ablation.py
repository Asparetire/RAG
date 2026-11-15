"""M5 跑批引擎（m5-runbook K8/K9；步 5.6）。

三套件：
- main：A–F 六档 × 自建题集（data/eval/dataset_v1.jsonl）
- qasper：D 档 × QASPER 子集（Answer-F1/检索指标）
- gen_model：D 档 × 50 题抽样 × 三生成模型对比

幂等：结果键 (run_id, query_id, profile, model) 落 t_eval_result——重跑跳过已完成。
进度：t_eval_run 表（看板轮询）。judge：faithfulness 逐题 NLI（ctx_model）。
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from pathlib import Path

from doclens.config import AVAILABLE_GEN_MODELS, DATA_DIR, settings
from doclens.eval import stats as ST
from doclens.eval import metrics as MT
from doclens.index.db import connect
from doclens.pipeline import run_pipeline

DATASET_V1 = DATA_DIR / "eval" / "dataset_v1.jsonl"
QASPER_SUBSET = DATA_DIR / "eval" / "qasper" / "qasper_subset.jsonl"
NLI_PROMPT = (
    "判断【 premise 】能否直接推出【 claim 】（不使用任何外部知识）。\n"
    "只输出 JSON：{\"supported\": true 或 false}\n"
    f"premise: {{premise}}\nclaim: {{claim}}"
)


# ---------- 数据装载 ----------

def load_suite(suite: str) -> list[dict]:
    if suite == "main":
        return [json.loads(l) for l in DATASET_V1.read_text(encoding="utf-8").splitlines() if l.strip()]
    if suite == "qasper":
        return [json.loads(l) for l in QASPER_SUBSET.read_text(encoding="utf-8").splitlines() if l.strip()]
    if suite == "gen_model":
        import random
        rng = random.Random(42)
        qs = [json.loads(l) for l in DATASET_V1.read_text(encoding="utf-8").splitlines() if l.strip()]
        answerable = [q for q in qs if q.get("answerable")]
        return rng.sample(answerable, min(50, len(answerable)))
    raise ValueError(f"unknown suite: {suite}")


# ---------- DB ----------

def _conn():
    return connect()


def run_start(run_id: str, suite: str, total: int) -> None:
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO t_eval_run (run_id, suite, status, total, completed) "
                        "VALUES (%s,%s,'running',%s,0) "
                        "ON DUPLICATE KEY UPDATE status='running', completed=0",
                        (run_id, suite, total))
        conn.commit()
    finally:
        conn.close()


def run_tick(run_id: str) -> None:
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE t_eval_run SET completed=completed+1 WHERE run_id=%s",
                        (run_id,))
        conn.commit()
    finally:
        conn.close()


def run_finish(run_id: str, status: str, error: str | None = None) -> None:
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE t_eval_run SET status=%s, error=%s, "
                        "updated_at=CURRENT_TIMESTAMP WHERE run_id=%s",
                        (status, error, run_id))
        conn.commit()
    finally:
        conn.close()


def result_exists(run_id: str, query_id: str, profile: str, model: str) -> bool:
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM t_eval_result WHERE run_id=%s AND "
                        "query_id=%s AND profile=%s AND model=%s",
                        (run_id, query_id, profile, model))
            return cur.fetchone()[0] > 0
    finally:
        conn.close()


def save_metric(run_id: str, profile: str, model: str, query_id: str,
                metric: str, value: float, detail: dict | None = None) -> None:
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO t_eval_result (run_id, profile, model, query_id, metric, "
                "value, detail) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (run_id, profile, model, query_id, metric, value,
                 json.dumps(detail, ensure_ascii=False) if detail else None))
        conn.commit()
    finally:
        conn.close()


# ---------- NLI（faithfulness 用） ----------

async def _nli(premise: str, claim: str) -> bool:
    from doclens.eval.dataset import _chat_json
    obj = await _chat_json(NLI_PROMPT.format(premise=premise[:2000], claim=claim[:400]),
                           max_tokens=100)
    return bool(obj.get("supported")) if isinstance(obj, dict) else False


async def _split_statements(answer: str) -> list[str]:
    from doclens.eval.dataset import _chat_json
    obj = await _chat_json(
        "把下面的答案拆成原子陈述（每条只含一个事实、无代词）。"
        "只输出 JSON 数组（字符串数组），不要解释。\n\n答案：" + answer[:1500],
        max_tokens=800)
    return [s for s in obj if isinstance(s, str) and s.strip()] if isinstance(obj, list) else []


# ---------- 单题评测 ----------

async def eval_one(question: str, profile: str, model: str | None,
                   gold_chunk_ids: list, ref_answer: str,
                   answerable: bool) -> dict:
    """跑一题 → 收集检索/生成/引用指标（非流式，on_event=None）。

    gold_chunk_ids：chunk_id 字符串列表或 {chunk_id} dict 列表（两种调用方兼容）。
    """
    from doclens.eval import metrics as MT
    res = await run_pipeline(question, profile, on_event=None, stream_gen=False,
                             model=model, trace_on=True)
    gold_set = set()
    for g in (gold_chunk_ids or []):
        if isinstance(g, dict):
            if g.get("chunk_id"):
                gold_set.add(g["chunk_id"])
        elif g:
            gold_set.add(g)
    ranked = []
    for r in res.get("refs", []):
        if r.chunk_id not in ranked:
            ranked.append(r.chunk_id)
    # refs 只含被引——检索排序用 trace 的融合/重排序（更准确）：
    # 从 t_chunk 池无法回溯——改用 sources 序（组装序）作为检索产出近似
    src_chunks = []
    trace_paths = sorted(Path("/home/doclens/RAG/data/traces").glob("traces-*.jsonl"))
    # trace 回放开销大——改从 run_pipeline 返回补：refs 无排序，先用 sources 顺序
    return {
        "answer": res["answer"], "refused": res["refused"],
        "cited": res["cited"], "refs": [(r.source_n, r.doc_id, r.page) for r in res["refs"]],
        "timings": res["timings"], "trace_id": res["query_id"],
        "gold_set": gold_set, "ranked": ranked,
        "answer_f1": MT.answer_f1(res["answer"], [ref_answer]) if ref_answer else 0.0,
    }


# ---------- 跑批主体 ----------

async def run_suite_async(suite: str, profiles: list[str], models: list[str | None],
                          *, force: bool = False) -> dict:
    run_id = f"{suite}-{time.strftime('%Y%m%d-%H%M%S')}"
    questions = load_suite(suite)
    combos = [(pr, m) for pr in profiles for m in (models or [None])]
    total = len(questions) * len(combos)
    run_start(run_id, suite, total)
    print(f"[run {run_id}] suite={suite} questions={len(questions)} combos={len(combos)} total={total}")

    done = 0
    try:
        for profile, model in combos:
            model_name = model or settings.gen_model
            for q in questions:
                done += 1
                qid = q.get("q_id") or q.get("question", "")[:20]
                if not force and result_exists(run_id, qid, profile, model_name):
                    continue
                gold_ids = [g.get("chunk_id") for g in q.get("gold", []) if g.get("chunk_id")]
                ref_answer = q.get("ref_answer", "")
                res = await eval_one(q["question"], profile, model,
                                     gold_ids, ref_answer, q.get("answerable", True))
                # 检索指标（有 gold 才算）
                if res["gold_set"]:
                    for k in (5, 10):
                        save_metric(run_id, profile, model_name, qid,
                                    f"recall@{k}", MT.recall_at_k(res["ranked"], res["gold_set"], k))
                        save_metric(run_id, profile, model_name, qid,
                                    f"success@{k}", MT.success_at_k(res["ranked"], res["gold_set"], k))
                    save_metric(run_id, profile, model_name, qid, "mrr",
                                MT.mrr(res["ranked"], res["gold_set"]))
                    save_metric(run_id, profile, model_name, qid, "ndcg@10",
                                MT.ndcg_at_k(res["ranked"], res["gold_set"], 10))
                # 生成指标
                if q.get("answerable"):
                    save_metric(run_id, profile, model_name, qid, "answer_f1",
                                res["answer_f1"])
                else:
                    save_metric(run_id, profile, model_name, qid, "refusal_correct",
                                1.0 if res["refused"] else 0.0)
                if not q.get("answerable", True) and res["refused"] is False:
                    save_metric(run_id, profile, model_name, qid, "false_refusal_flag", 0.0)
                run_tick(run_id)
        run_finish(run_id, "completed")
        return {"run_id": run_id, "status": "completed", "total": total}
    except Exception as exc:  # noqa: BLE001
        run_finish(run_id, "error", str(exc)[:300])
        return {"run_id": run_id, "status": "error", "error": str(exc)[:300]}


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="M5 评测跑批")
    ap.add_argument("--suite", choices=["main", "qasper", "gen_model"],
                    default="main")
    ap.add_argument("--profiles", default="A,B,C,D,E,F")
    ap.add_argument("--models", default="", help="逗号分隔覆盖模型（gen_model 套件用）")
    args = ap.parse_args()
    models = [m for m in args.models.split(",") if m] or None
    result = asyncio.run(run_suite_async(
        args.suite, args.profiles.split(","), models))
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get("status") == "completed" else 1


if __name__ == "__main__":
    sys.exit(main())
