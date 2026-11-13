"""M5 全量出题+AI 复审（步 5.2；按篇幂等断点：已有 candidates_{doc}.json 跳过）。

用法（容器 doclens 环境）：
    python scripts/eval_generate_all.py            # 全量（11 篇）
    python scripts/eval_generate_all.py --force    # 重跑已有篇
产出（data/eval/）：
    candidates_{doc}.json     每篇原始候选（含 verdict 分拣）
    review_uncertain.md       待人工裁决队列（用户只审这里）
    review_stats.json         分拣统计
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from doclens.config import PARSED_DIR
from doclens.eval.dataset import generate_candidates_for_doc, save_candidates
from doclens.eval.review import review_question
from doclens.index.db import connect

OUT_DIR = Path(__file__).resolve().parent.parent / "data" / "eval"


def _all_doc_ids() -> list[str]:
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT doc_id FROM t_doc ORDER BY doc_id")
            return [r[0] for r in cur.fetchall()]
    finally:
        conn.close()


async def _review_doc(candidates: list[dict]) -> tuple[list[dict], list[dict]]:
    """AI 复审一篇的候选题，分拣 (passed, uncertain)。reject 直接弃。"""
    passed, uncertain = [], []
    for q in candidates:
        if not q.get("answerable", True):
            q["review"] = {"verdict": "pass", "confidence": 1.0,
                           "reason": "不可答题：以拒答为正确行为，无需事实复审"}
            passed.append(q)
            continue
        gold_contents = []
        for g in q.get("gold", []):
            from doclens.eval.dataset import load_chunk_pool
            pool = {c["chunk_id"]: c["content"] for c in load_chunk_pool(g["doc_id"])}
            gold_contents.append(pool.get(g["chunk_id"], ""))
        try:
            v = await review_question(q["question"], q.get("ref_answer", ""),
                                      gold_contents, q.get("type", "text"))
        except Exception as e:  # noqa: BLE001 复审失败=uncertain（交人工）
            v = {"verdict": "uncertain", "confidence": 0.0,
                 "reason": f"复审调用失败：{str(e)[:80]}"}
        q["review"] = v
        if v["verdict"] == "pass":
            passed.append(q)
        elif v["verdict"] == "uncertain":
            uncertain.append(q)
        # reject：不进任何桶（统计里可见）
    return passed, uncertain


async def main_async(force: bool) -> int:
    doc_ids = _all_doc_ids()
    print(f"[docs] {len(doc_ids)} 篇")
    stats = {"docs": 0, "candidates": 0, "pass": 0, "uncertain": 0, "reject": 0}
    uncertain_all: list[dict] = []

    for i, doc_id in enumerate(doc_ids, 1):
        out_file = OUT_DIR / f"candidates_{doc_id}.json"
        if out_file.exists() and not force:
            print(f"[{i}/{len(doc_ids)}] {doc_id} 已有候选（跳过；--force 重跑）")
            data = json.loads(out_file.read_text(encoding="utf-8"))
        else:
            print(f"[{i}/{len(doc_ids)}] {doc_id} 出题中…")
            result = await generate_candidates_for_doc(doc_id)
            save_candidates(doc_id, result, OUT_DIR)
            data = {"doc_id": doc_id,
                    "candidates": [q.to_dict() for q in result["candidates"]],
                    "errors": result["errors"]}
        cands = data.get("candidates", [])
        passed, uncertain = await _review_doc(cands)
        stats["docs"] += 1
        stats["candidates"] += len(cands)
        stats["pass"] += len(passed)
        stats["uncertain"] += len(uncertain)
        stats["reject"] += len(cands) - len(passed) - len(uncertain)
        uncertain_all += [{**q, "doc_id": doc_id} for q in uncertain]
        print(f"    出题 {len(cands)} → pass {len(passed)} / uncertain {len(uncertain)} "
              f"/ reject {len(cands) - len(passed) - len(uncertain)}")

    # 待人工裁决队列（用户只审这里）
    lines = ["# 待人工裁决队列（AI 复审 uncertain）", "",
             f"共 {len(uncertain_all)} 题——请逐题在 review 行标 `收录` / `弃用(原因)`。", ""]
    for i, q in enumerate(uncertain_all, 1):
        lines += [f"## 第 {i} 题 [{q.get('type')}] {q.get('doc_id')}",
                  "", f"**题目**：{q.get('question')}", "",
                  f"**参考答案**：{q.get('ref_answer')}", "",
                  f"**复审意见**：{q.get('review', {}).get('reason', '')}",
                  "(confidence {:.2f})".format(q.get("review", {}).get("confidence", 0)),
                  "", "**裁决**：", "", "---", ""]
    (OUT_DIR / "review_uncertain.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (OUT_DIR / "review_stats.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    print("[stats]", json.dumps(stats, ensure_ascii=False))
    print(f"[uncertain 队列] data/eval/review_uncertain.md（{len(uncertain_all)} 题）")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="M5 全量出题+AI 复审")
    ap.add_argument("--force", action="store_true", help="重跑已有篇")
    args = ap.parse_args()
    return asyncio.run(main_async(args.force))


if __name__ == "__main__":
    sys.exit(main())
