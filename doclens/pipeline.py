"""M4 共享问答管线（m4-runbook K1/K7；从 scripts/query_cli.answer_question 抽取）。

单一编排源：CLI（query_cli）与 SSE 服务（doclens/serve/api.py）共用本模块，
杜绝契约双侧漂移（m4 调研 P3/R3）。

事件出口（可选 on_event 回调，载荷 dict：{"event": str, "data": dict}）——
冻结契约见 m4-runbook §3.1（= 调研 §1.4 超集，D 线 §8.3 三家校验）：
  stage{stage,detail} → sources{sources,routes,profile} → stage(generate)
  → thinking{status:started} → reasoning{text}×M + token{content}×N
  → thinking{status:done,elapsed_ms} → citations{cited,invalid} → done{...}
CLI 场景 on_event=None：零事件开销，行为与 M3 全等（--smoke 不回归）。

空答案守卫（K7；2026-11-12 冒烟 A 档 s01 观察项闭环）：
glm-5.3-flash 强制思考可能耗尽 max_tokens（实测 reasoning 6932 字符/content 空，
usage 5297 = prompt 3249 + completion 2048）——生成 content 为空时重试一次
（max_tokens 上调一档），仍空则按无依据兜底（REFUSAL_TEXT + refused 语义）
并落 trace 标记 empty_content，CLI 与 SSE 两路同时受益。
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

from doclens.config import PARSED_DIR, PROJECT_ROOT, PROFILES, settings
from doclens.generate import citations as CITE
from doclens.generate import fallback as FB
from doclens.generate.context import assemble
from doclens.generate.vlm import GenResult, generate_answer
from doclens.index.db import connect
from doclens.retrieve import hybrid, router
from doclens.retrieve.rerank import Candidate, cascade_input, rerank_candidates
from doclens import trace as TR

PDF_DIR = PROJECT_ROOT / "data" / "pdfs"  # M2 语料入库命名 {doc_id}.pdf（实测 11 篇）


def _emit(on_event, event: str, **data) -> None:
    """事件出口：on_event=None 时零开销（CLI）。回调签名 cb({"event":..., "data":...})。"""
    if on_event is not None:
        on_event({"event": event, "data": data})


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


def _load_image_blob(doc_id: str, image_path: str) -> bytes | None:
    """image_path（M2 语义：相对 doc 解析目录）→ 原图 bytes。

    真实位置 = data/parsed/{doc_id}/{image_path}（ingest._image_file 同款拼接，
    m4 修复：M3 版本漏拼 {doc_id} 段导致图文多模态输入静默失效——图表题一直
    靠 caption 文本代理答题，B 档语义掩盖了该缺陷；缺失容错保留，trace 可见）。
    """
    if not doc_id or not image_path:
        return None
    p = Path(image_path)
    if p.is_absolute():
        try:
            return p.read_bytes()
        except OSError:
            return None
    p = PARSED_DIR / doc_id / image_path
    try:
        return p.read_bytes()
    except OSError:
        return None


def _ctx_prefixes(final_ranking: list[str]) -> dict[str, str] | None:
    """E 档 t_ctx_prefix 前缀回表（500 分批纯占位符，S4-15 口径）。"""
    if not final_ranking:
        return None
    conn = connect()
    try:
        with conn.cursor() as cur:
            ph = ",".join(["%s"] * len(final_ranking))
            cur.execute(
                f"SELECT chunk_id, prefix FROM t_ctx_prefix WHERE chunk_id IN ({ph}) "
                f"AND model=%s", (*final_ranking, settings.ctx_model))
            return {r[0]: r[1] for r in cur.fetchall()}
    finally:
        conn.close()


async def _generate_with_guard(gen_fn) -> tuple[GenResult, bool]:
    """K7 空答案守卫（纯编排，可单测）。

    gen_fn(max_tokens) -> GenResult：调用方包装好的单次生成。
    空 content（含纯空白）→ 重试一次（max_tokens 上调一档）→ 仍空 →
    返回 (REFUSAL_TEXT 形态 GenResult, True)；正常则 (gen, False)。
    """
    gen = await gen_fn(settings.gen_max_tokens)
    if gen.answer.strip():
        return gen, False
    gen = await gen_fn(settings.gen_max_tokens_retry)
    if gen.answer.strip():
        return gen, False
    refusal = GenResult(
        answer=FB.REFUSAL_TEXT,
        reasoning_chars=gen.reasoning_chars,
        reasoning_text_head=gen.reasoning_text_head,
        usage_tokens=gen.usage_tokens,
        prompt_tokens=gen.prompt_tokens,
        ttft_ms=gen.ttft_ms,
        total_ms=gen.total_ms,
        model=gen.model,
    )
    return refusal, True


async def run_pipeline(
    question: str,
    profile_name: str,
    *,
    on_event=None,
    rerank_pro: bool = False,
    trace_on: bool = True,
    stream_gen: bool = False,
) -> dict:
    """端到端一问（管道序 = m3-runbook §3 K1–K7；M3 行为全保留 + 事件出口）。"""
    profile = PROFILES[profile_name]
    qid = TR.query_id(question, profile_name)
    t0 = time.perf_counter()
    timings: dict[str, float] = {}

    # 1. 语言路由（K3/D11）
    lang = router.detect_lang(question)
    bm25_weight = router.bm25_weight_for(lang, profile)

    # 2. 三路召回 + 融合 + 证据组去重（K1）
    _emit(on_event, "stage", stage="retrieve", detail="三路召回+融合去重")
    t = time.perf_counter()
    rr = await hybrid.retrieve(question, profile, bm25_weight=bm25_weight)
    timings["retrieve_ms"] = round((time.perf_counter() - t) * 1000, 1)

    # 3. 重排（K2；D 档起）——pool → candidates → top-20
    rerank_out = None
    final_ranking = [h.chunk_id for h in rr.pool]  # 无重排 = 融合池即最终序
    if profile.rerank:
        _emit(on_event, "stage", stage="rerank", detail=f"LLM 重排（{profile.rerank}）")
        t = time.perf_counter()
        cand_map: dict[str, Candidate] = {}
        for h in rr.pool:
            cand_map[h.chunk_id] = Candidate(
                chunk_id=h.chunk_id, doc_id=h.doc_id, page=h.page, kind=h.kind,
                heading_path=h.heading_path, content="")  # content 由回表填充（下步）
        ids = list(cand_map)
        meta = await asyncio.to_thread(_fetch_members, ids)
        for cid, c in cand_map.items():
            m = meta.get(cid) or {}
            c.content = (m.get("content") or "").strip()
        tier = "pro" if rerank_pro else profile.rerank
        inp = cascade_input(list(cand_map.values()), top=profile.rerank_input) if tier == "pro" \
            else list(cand_map.values())[:profile.rerank_input]
        rerank_out = await rerank_candidates(question, inp, model_tier=tier)
        # B-1 修复：重排序为主干——组员就地展开必须作用在**重排输出**上（而非融合池序），
        # 否则 LLM 重排（11s+token 费）对最终上下文零影响（审查 1bf4229 回归发现）。
        hit_by_id = {h.chunk_id: h for h in rr.pool}
        final_ranking = []
        seen: set[str] = set()

        def _push(cid: str) -> None:
            if cid not in seen:
                seen.add(cid)
                final_ranking.append(cid)

        for cid in rerank_out.ranking:
            _push(cid)
            h = hit_by_id.get(cid)
            if h is not None:
                for mid in h.group_members:
                    _push(mid)
        for h in rr.pool[:profile.final_top]:   # 保底：重排丢块/降级回退时的窗口补齐
            _push(h.chunk_id)
            for mid in h.group_members:
                _push(mid)
        timings["rerank_ms"] = round((time.perf_counter() - t) * 1000, 1)

    # 4. 上下文组装（K4）——members 全字段回表（E 档前缀 t_ctx_prefix）
    _emit(on_event, "stage", stage="assemble", detail="上下文组装")
    meta = await asyncio.to_thread(_fetch_members, final_ranking)
    ctx_prefixes = _ctx_prefixes(final_ranking) \
        if profile.use_ctx_prefix and final_ranking else None
    ctx = assemble(question, final_ranking, meta, final_top=profile.final_top,
                   max_images=profile.max_images, use_ctx_prefix=profile.use_ctx_prefix,
                   ctx_prefixes=ctx_prefixes)

    # 4.5 sources 事件（R4：先于首 token，侧栏即时可点；routes 供 FR-5.3 并列分数）
    final_set = set(final_ranking)
    routes_out: dict[str, list] = {}
    for route_name, hits in rr.routes.items():
        lst = []
        for h in hits:
            if h.chunk_id in final_set:
                rank = (h.route_hits.get(route_name) or (None, None))[0]
                lst.append({"chunk_id": h.chunk_id, "score": round(h.score, 4), "rank": rank})
        routes_out[route_name] = lst
    sources_payload = [
        {"n": s.source_n, "chunk_id": s.chunk_id, "doc_id": s.doc_id, "kind": s.kind,
         "page": s.page, "snippet": (s.content or "")[:160],
         "image_path": s.image_path, "bbox": s.bbox}
        for s in ctx.sources
    ]
    _emit(on_event, "sources", sources=sources_payload, routes=routes_out,
          profile=profile_name)

    # 5. 兜底判定（K7；judge 失败放行）
    judge = await FB.judge_sufficiency(question, ctx)
    decision = FB.decide_fallback(question, ctx, judge)

    # 6. 生成或拒答（K5）+ 空答案守卫（K7）
    t = time.perf_counter()
    gen: GenResult | None = None
    empty_content = False
    if decision.refused:
        answer = FB.REFUSAL_TEXT
        _emit(on_event, "token", content=answer)  # 拒答话术一次成文
    else:
        _emit(on_event, "stage", stage="generate", detail="生成（glm-5.3-flash）")
        _emit(on_event, "thinking", status="started")
        blobs = {}
        for img in ctx.images:
            b = _load_image_blob(img.doc_id, img.image_path)
            if b is not None:
                blobs[img.image_path] = b

        def _on_delta(kind: str, text: str) -> None:
            # R5 双字段分流：reasoning 只进临时态事件，绝不进 token/答案
            if kind == "reasoning":
                _emit(on_event, "reasoning", text=text)
            elif kind == "content":
                _emit(on_event, "token", content=text)

        async def _gen_call(mt: int) -> GenResult:
            return await generate_answer(
                question, ctx, image_blobs=blobs or None,
                stream=stream_gen, max_tokens=mt,
                on_delta=_on_delta if stream_gen else None)

        gen, empty_content = await _generate_with_guard(_gen_call)
        answer = gen.answer
        timings["generate_ms"] = round((time.perf_counter() - t) * 1000, 1)
        think_ms = gen.ttft_ms if gen.ttft_ms is not None else gen.total_ms
        _emit(on_event, "thinking", status="done", elapsed_ms=round(think_ms or 0.0, 1))

    # 7. 引用解析与映射（K6）
    valid_ids = {s.source_n for s in ctx.sources}
    report = CITE.parse_citations(answer, valid_ids)
    refs = CITE.map_to_sources(report, ctx.sources)
    checked = FB.self_check(answer, ctx)
    invalid_ids = sorted({bad for d in report.degraded_sentences for bad in d.bad_ids})
    _emit(on_event, "citations", cited=report.cited, invalid=invalid_ids)

    # 8. trace（K8/R15；子事件流）——沿用 M3 六类事件 + empty_content 标记
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
                                                           "judge_reason": judge.reason,
                                                           "empty_content": empty_content},
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

    finish_reason = "refused" if (decision.refused or empty_content) else "stop"
    _emit(on_event, "done", finish_reason=finish_reason,
          usage={"total_tokens": gen.usage_tokens if gen else None,
                 "prompt_tokens": gen.prompt_tokens if gen else None},
          timing=timings, trace_id=qid)

    return {"query_id": qid, "profile": profile_name, "lang": lang, "question": question,
            "answer": answer, "refused": bool(decision.refused or empty_content),
            "empty_content": empty_content,
            "cited": report.cited, "refs": refs, "degraded_citations": report.degraded_sentences,
            "self_check": checked, "n_sources": len(ctx.sources), "n_images": len(ctx.images),
            "timings": timings, "judge": judge, "rerank": rerank_out}


# M3 兼容别名（query_cli --smoke/单问沿用旧签名；新参数均为 keyword-only 可选）
answer_question = run_pipeline
