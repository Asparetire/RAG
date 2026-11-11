"""M3 问答 CLI（m3-runbook 3.5 / K8；主计划 §5 步 3.5）。

用法：
    python scripts/query_cli.py --profile D --question "问题"
    python scripts/query_cli.py --profile D --smoke          # 20 冒烟题自动验收报告
    python scripts/query_cli.py --profile D --question ... --rerank-pro   # pro 级联对比位

管道（K1–K7 编排序，全链路 trace 落盘 data/traces/）：
    语言路由(3.3) → 三路召回+融合+去重(3.1) → 重排(3.2) → 组装(3.4 context)
    → 兜底判定(3.4 fallback) → 生成(3.4 vlm) → 引用解析映射(3.4 citations)
Windows 编码（体检发现①）：入口即 reconfigure stdout/stderr 为 UTF-8。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from doclens.config import PROFILES, settings  # noqa: E402
from doclens.generate import citations as CITE  # noqa: E402
from doclens.generate import fallback as FB  # noqa: E402
from doclens.generate.context import assemble  # noqa: E402
from doclens.generate.vlm import generate_answer  # noqa: E402
from doclens.retrieve import hybrid, router  # noqa: E402
from doclens.retrieve.rerank import Candidate, cascade_input, rerank_candidates  # noqa: E402
from doclens import trace as TR  # noqa: E402
from doclens.index import bm25 as B  # noqa: E402
from doclens.index.db import connect  # noqa: E402

SMOKE_FILE = Path(__file__).resolve().parent / "smoke_queries.json"
PROJ_ROOT = Path(__file__).resolve().parent.parent
PARSED_DIR = PROJ_ROOT / "data" / "parsed"


def _fetch_members(chunk_ids: list[str]) -> dict[str, dict]:
    """全字段回表（context.assemble 需要 content/bbox/caption——比 hybrid 的 6 列多）。"""
    if not chunk_ids:
        return {}
    conn = connect()
    try:
        out: dict[str, dict] = {}
        with conn.cursor() as cur:
            for i in range(0, len(chunk_ids), 500):
                batch = chunk_ids[i:i + 500]
                ph = ",".join(["%s"] * len(batch))
                cur.execute(
                    f"SELECT chunk_id, doc_id, kind, page, content, bbox, heading_path, "
                    f"image_path, caption FROM t_chunk WHERE chunk_id IN ({ph})",
                    batch,
                )
                for r in cur.fetchall():
                    out[r[0]] = dict(zip(
                        ("chunk_id", "doc_id", "kind", "page", "content", "bbox",
                         "heading_path", "image_path", "caption"), r))
        return out
    finally:
        conn.close()


def _load_image_blob(image_path: str) -> bytes | None:
    """image_path（M2 落库的相对路径）→ 原图 bytes；缺失容错（trace 记录，不炸主链路）。"""
    if not image_path:
        return None
    p = Path(image_path)
    if not p.is_absolute():
        p = PROJ_ROOT / image_path if (PROJ_ROOT / image_path).exists() else PARSED_DIR.parent / image_path
    try:
        return p.read_bytes()
    except OSError:
        return None


async def answer_question(question: str, profile_name: str, *, rerank_pro: bool = False,
                          trace_on: bool = True) -> dict:
    """端到端一问（管道序 = runbook §3 K1–K7），返回展示用 dict（含 trace_id）。"""
    profile = PROFILES[profile_name]
    qid = TR.query_id(question, profile_name)
    t0 = time.perf_counter()
    timings: dict[str, float] = {}

    # 1. 语言路由（K3/D11）
    lang = router.detect_lang(question)
    bm25_weight = router.bm25_weight_for(lang, profile)

    # 2. 三路召回 + 融合 + 证据组去重（K1）
    t = time.perf_counter()
    rr = await hybrid.retrieve(question, profile, bm25_weight=bm25_weight)
    timings["retrieve_ms"] = round((time.perf_counter() - t) * 1000, 1)

    # 3. 重排（K2；D 档起）——pool → candidates → top-20
    rerank_out = None
    final_ranking = [h.chunk_id for h in rr.pool]  # 无重排 = 融合池即最终序
    if profile.rerank:
        t = time.perf_counter()
        members_map = hybrid.build_members_map(
            hybrid._payload_meta(rr.routes), {})  # pool 内元数据在 Hit 上，直接构造
        cand_map: dict[str, Candidate] = {}
        for h in rr.pool:
            cand_map[h.chunk_id] = Candidate(
                chunk_id=h.chunk_id, doc_id=h.doc_id, page=h.page, kind=h.kind,
                heading_path=h.heading_path, content="")  # content 由回表填充（下步）
        # 回表补 content（重排提示词要正文前 300 词）
        ids = list(cand_map)
        meta = await asyncio.to_thread(_fetch_members, ids)
        for cid, c in cand_map.items():
            m = meta.get(cid) or {}
            c.content = (m.get("content") or "").strip()
        tier = "pro" if rerank_pro else profile.rerank
        inp = cascade_input(list(cand_map.values()), top=profile.rerank_input) if tier == "pro" \
            else list(cand_map.values())[:profile.rerank_input]
        rerank_out = await rerank_candidates(question, inp, model_tier=tier)
        final_ranking = rerank_out.ranking
        timings["rerank_ms"] = round((time.perf_counter() - t) * 1000, 1)

    # 4. 上下文组装（K4）——members 全字段回表（E 档前缀 t_ctx_prefix）
    meta = await asyncio.to_thread(_fetch_members, final_ranking)
    ctx_prefixes = None
    if profile.use_ctx_prefix:
        conn = connect()
        try:
            with conn.cursor() as cur:
                ph = ",".join(["%s"] * len(final_ranking)) or "%s"
                cur.execute(
                    f"SELECT chunk_id, prefix FROM t_ctx_prefix WHERE chunk_id IN ({ph}) "
                    f"AND model=%s", (*final_ranking, settings.ctx_model))
                ctx_prefixes = {r[0]: r[1] for r in cur.fetchall()}
        finally:
            conn.close()
    ctx = assemble(question, final_ranking, meta, final_top=profile.final_top,
                   max_images=profile.max_images, use_ctx_prefix=profile.use_ctx_prefix,
                   ctx_prefixes=ctx_prefixes)

    # 5. 兜底判定（K7；judge 失败放行）
    judge = await FB.judge_sufficiency(question, ctx)
    decision = FB.decide_fallback(question, ctx, judge)

    # 6. 生成或拒答（K5）
    t = time.perf_counter()
    if decision.refused:
        answer = FB.REFUSAL_TEXT
        gen = None
    else:
        blobs = {}
        for img in ctx.images:
            b = _load_image_blob(img.image_path)
            if b is not None:
                blobs[img.image_path] = b
        gen = await generate_answer(question, ctx, image_blobs=blobs or None, stream=False)
        timings["generate_ms"] = round((time.perf_counter() - t) * 1000, 1)

    # 7. 引用解析与映射（K6）
    valid_ids = {s.source_n for s in ctx.sources}
    report = CITE.parse_citations(answer, valid_ids)
    refs = CITE.map_to_sources(report, ctx.sources)
    checked = FB.self_check(answer, ctx)

    # 8. trace（K8/R15；子事件流）
    if trace_on:
        TR.append_event(qid, "meta", {"profile": profile_name, "question": question,
                                      "lang": lang, "bm25_weight": bm25_weight,
                                      "timings": timings})
        TR.append_event(qid, "routes", {
            k: [{"chunk_id": h.chunk_id, "score": h.score,
                 "rank": (h.route_hits.get(k) or (None, None))[0],
                 "raw": (h.route_hits.get(k) or (None, None))[1]}
                for h in v]
            for k, v in rr.routes.items()})
        TR.append_event(qid, "fused", {"fused": [{"chunk_id": h.chunk_id, "score": h.score}
                                                 for h in rr.fused],
                                       "deduped": [{"chunk_id": h.chunk_id, "score": h.score,
                                                    "group": h.group_members} for h in rr.deduped],
                                       "pool": [h.chunk_id for h in rr.pool]})
        if rerank_out is not None:
            TR.append_event(qid, "rerank", {"output": rerank_out.ranking,
                                            "degraded": rerank_out.degraded,
                                            "model": rerank_out.model,
                                            "latency_ms": rerank_out.latency_ms,
                                            "usage_tokens": rerank_out.usage_tokens,
                                            "cache_hit": rerank_out.cache_hit,
                                            "fail_reason": rerank_out.fail_reason})
        TR.append_event(qid, "context", {"sources": [{"source_n": s.source_n, "chunk_id": s.chunk_id,
                                                      "doc_id": s.doc_id, "kind": s.kind,
                                                      "page": s.page}
                                                     for s in ctx.sources],
                                         "images": [{"source_n": i.source_n,
                                                     "image_path": i.image_path}
                                                    for i in ctx.images],
                                         "truncated": ctx.truncated})
        TR.append_event(qid, "llm_fallback", {"fallback": {"refused": decision.refused,
                                                           "reason": decision.reason,
                                                           "judge_ok": judge.judge_ok,
                                                           "judge_reason": judge.reason},
                                              "llm": None if gen is None else {
                                                  "answer": gen.answer,
                                                  "reasoning_chars": gen.reasoning_chars,
                                                  "reasoning_text_head": gen.reasoning_text_head,
                                                  "usage_tokens": gen.usage_tokens,
                                                  "prompt_tokens": gen.prompt_tokens,
                                                  "ttft_ms": gen.ttft_ms,
                                                  "total_ms": gen.total_ms,
                                                  "model": gen.model},
                                              "citations": {"cited": report.cited,
                                                            "degraded": [d.bad_ids for d in
                                                                         report.degraded_sentences],
                                                            "self_check": checked,
                                                            "refs": [{"source_n": r.source_n,
                                                                      "doc_id": r.doc_id,
                                                                      "page": r.page}
                                                                     for r in refs]},
                                              "total_ms": round((time.perf_counter() - t0) * 1000, 1)})

    return {"query_id": qid, "profile": profile_name, "lang": lang, "question": question,
            "answer": answer, "refused": decision.refused,
            "cited": report.cited, "refs": refs, "degraded_citations": report.degraded_sentences,
            "self_check": checked, "n_sources": len(ctx.sources), "n_images": len(ctx.images),
            "timings": timings, "judge": judge, "rerank": rerank_out}


def _print_answer(res: dict) -> None:
    print(f"\n[{res['profile']} 档｜{res['lang']}｜trace={res['query_id']}]")
    print(f"Q: {res['question']}")
    print(f"A: {res['answer']}")
    if res["cited"]:
        print("引用:", ", ".join(f"[{n}]" for n in res["cited"]))
    for r in res["refs"]:
        print(f"  [{r.source_n}] → {r.doc_id} p{r.page}" + (f" bbox={r.bbox}" if r.bbox else ""))
    if res["degraded_citations"]:
        print(f"⚠️ {len(res['degraded_citations'])} 句含无效引用（已标记未删除）")
    if res["timings"]:
        print("耗时:", res["timings"])


def _run_smoke(profile_name: str, rerank_pro: bool) -> int:
    """20 冒烟题 × 当前档 → Markdown 报告（人工"通过/失败"列留空待填，R16）。"""
    spec = json.loads(SMOKE_FILE.read_text(encoding="utf-8"))
    queries = spec["queries"]
    report_path = PROJ_ROOT / "reports" / f"smoke_{profile_name}{'_pro' if rerank_pro else ''}.md"
    lines = [
        f"# M3 冒烟验收报告——{profile_name}{'（pro 级联）' if rerank_pro else ''} 档",
        "",
        f"- 生成时间：{time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 题集：{SMOKE_FILE.name}（v{spec.get('version', '?')}，{len(queries)} 题）",
        "- 判定规则：可回答题人工对照 gold_hint 判通过/失败；不可回答题以 refused=True 为通过；",
        f"- 验收线：通过率 ≥80%（≥16/20）；不可回答拒绝 ≥3/4；可回答误拒 ≤1（m3-runbook §1）",
        "",
        "| # | q_id | 类型 | 语言 | 问题 | 答案（截 300 字） | 引用 | 弃答 | trace | 通过/失败 |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    n_pass_unans = 0
    n_unans = 0
    for i, q in enumerate(queries, 1):
        res = asyncio.run(answer_question(q["question"], profile_name, rerank_pro=rerank_pro))
        refused = "是" if res["refused"] else "否"
        if q["type"] == "unanswerable":
            n_unans += 1
            n_pass_unans += 1 if res["refused"] else 0
        ans = res["answer"].replace("|", "\\|").replace("\n", " ")[:300]
        cites = ", ".join(f"[{n}]" for n in res["cited"]) or "-"
        lines.append(f"| {i} | {q['q_id']} | {q['type']} | {q['lang']} "
                     f"| {q['question'].replace('|', '\\|')} | {ans} | {cites} | {refused} "
                     f"| {res['query_id']} | |")
    lines += [
        "",
        f"**不可回答拒绝率（自动统计）**：{n_pass_unans}/{n_unans}",
        "",
        "## 人工判定",
        "",
        "- gold_hint 对照：见 scripts/smoke_queries.json",
        f"- 逐题证据定位：data/traces/traces-*.jsonl 按 trace 列回放",
        "",
        "| # | q_id | gold_hint | 备注 |",
        "|---|---|---|---|",
    ]
    for i, q in enumerate(queries, 1):
        lines.append(f"| {i} | {q['q_id']} | {q['gold_hint'].replace('|', '\\|')} | |")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n[完成] 报告已写 {report_path}")
    print(f"[自动统计] 不可回答拒绝 {n_pass_unans}/{n_unans}（验收 ≥3/4）；其余人工对照 gold_hint 填报告末列")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="DocLens M3 问答 CLI")
    ap.add_argument("--profile", choices=list(PROFILES), default="D", help="消融档位 A..F")
    ap.add_argument("--question", "-q", help="单次提问")
    ap.add_argument("--smoke", action="store_true", help="跑 20 冒烟题产验收报告")
    ap.add_argument("--rerank-pro", action="store_true", help="pro 档级联重排（对比实验位）")
    ap.add_argument("--no-trace", action="store_true", help="调试期关闭 trace 落盘")
    args = ap.parse_args()

    if args.smoke:
        return _run_smoke(args.profile, args.rerank_pro)
    if not args.question:
        ap.error("需要 --question 或 --smoke")
    res = asyncio.run(answer_question(args.question, args.profile,
                                      rerank_pro=args.rerank_pro, trace_on=not args.no_trace))
    _print_answer(res)
    return 0


if __name__ == "__main__":
    sys.exit(main())
