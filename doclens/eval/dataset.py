"""M5 评测题集构建（m5-runbook K1/K2；步 5.1–5.2）。

三层评测的 L1 层：自建域内题集 ~185 题（可回答 150 + 不可答 15 + 负面 20）。

出题管线（每篇论文）：
  VLM 读 parsed 产物（markdown + 图表原图）按题型模板出候选（JSON 严格输出）
  → 三道质量闸：相似去重（embedding 余弦）/原文锚定（ref_answer 关键句在 gold
  chunk 原文）/BM25 伪题检测（gold 断层第一=字面重叠题）
  → 幸存者写 candidates → 人审报告（markdown 并排）→ 定稿 dataset_v1.jsonl

纪律：
- 题面文本绝不入库（防评测泄漏）——本模块只读语料产物，不写任何索引；
- s15 教训入 prompt：禁止出"答案只在图内数字/只在图表中"而文本不可得的题
  （图表题必须图注或表格卡片文本可佐证，或明确标注 reading=figure）。
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from openai import AsyncOpenAI

from doclens.config import PARSED_DIR, settings

# ---------- 题目数据结构 ----------

@dataclass
class EvalQuestion:
    """一道评测题（dataset JSONL 的一行）。"""

    q_id: str
    type: str                       # text | figure | table | unanswerable | noise | counterfactual
    lang: str                       # zh | en
    question: str
    ref_answer: str                 # 参考答案（judge/F1 比对用）
    gold: list[dict]                # [{doc_id, page, chunk_id}]
    answerable: bool = True
    difficulty: str = "direct"      # direct | synthesis
    pair_of: str | None = None
    origin: str = "vlm"             # vlm | smoke
    noise_variant: bool = False     # True=评测时注入噪声上下文
    quote: str = ""                 # 原文依据句（VLM 逐字摘抄；锚定校验用）
    gold_hint: str = ""
    status: str = "candidate"       # candidate | approved | rejected | rewritten

    def to_dict(self) -> dict:
        return asdict(self)


# ---------- VLM 出题调用（轻量 JSON chat，不走 generate_answer 引用链） ----------

GEN_TEMPERATURE = 0.7  # 出题要多样性（与生成的 temp=0 不同）


async def _chat_json(prompt: str, images: list[bytes] | None = None,
                     max_tokens: int = 2000) -> dict | list | None:
    """调 gen_model 出题（强制 JSON 输出；容错解析——出题失败不炸批）。"""
    content: list = [{"type": "text", "text": prompt}]
    for b in (images or []):
        import base64
        content.append({"type": "image_url",
                        "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(b).decode()}})
    client = AsyncOpenAI(api_key=settings.ark_api_key, base_url=settings.ark_base_url)
    resp = await client.chat.completions.create(
        model=settings.gen_model,
        messages=[{"role": "user", "content": content}],
        temperature=GEN_TEMPERATURE, max_tokens=max_tokens, timeout=120)
    raw = (getattr(resp.choices[0].message, "content", None) or "").strip()
    # 容错 JSON 解析：剥围栏/抓首尾结构
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.M)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"[\[{].*[\]}]", raw, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                return None
    return None


# ---------- 质量闸（纯函数，可单测） ----------

def _norm_text(s: str) -> str:
    """小写+去空白+去标点（跨语言粗粒度归一）。"""
    return re.sub(r"[\s\W_]+", "", (s or "").lower())


def dedup_check(question: str, existing: list[str], threshold: float = 0.85) -> bool:
    """质量闸①：相似去重（字符 3-gram Jaccard 简化版；embedding 版留扩展位）。"""
    def grams(s: str) -> set:
        s = _norm_text(s)
        return {s[i:i + 3] for i in range(max(0, len(s) - 2))} or {s}
    g = grams(question)
    for ex in existing:
        e = grams(ex)
        if g and e and len(g & e) / len(g | e) > threshold:
            return False
    return True


def anchor_check(ref_answer: str, gold_contents: list[str], min_ratio: float = 0.6) -> bool:
    """质量闸②：原文锚定（双向）。

    a) ref_answer 归一化 8 字符滑窗 ≥min_ratio 命中 gold 原文（ref 抄原文形态）；
    b) 或 gold 原文的实词 3-gram 被 ref_answer 覆盖 ≥min_ratio（ref 归纳改写形态——
       VLM 出题常态是改写而非抄写，单向滑窗会误杀，试审批 20/20 覆没的教训）。
    """
    ref = _norm_text(ref_answer)
    joined = _norm_text(" ".join(gold_contents))
    if len(ref) < 8 or not joined:
        return False
    # a) ref 滑窗命中 gold
    step = max(4, len(ref) // 12)
    windows = [ref[i:i + 8] for i in range(0, max(1, len(ref) - 7), step)]
    hits = sum(1 for w in windows if w in joined)
    if hits / max(1, len(windows)) >= min_ratio:
        return True
    # b) gold 3-gram 覆盖率（gold 的信息被 ref 覆盖）——改写形态实测水位 ~0.34
    #    （0.6 会误杀；0.3 排除完全不相关 ref，试审批教训的校准值）
    gold_grams = {joined[i:i + 3] for i in range(max(0, len(joined) - 2))}
    if not gold_grams:
        return False
    covered = sum(1 for g in gold_grams if g in ref)
    return covered / len(gold_grams) >= 0.3


def anchor_via_quote(quote: str, gold_contents: list[str]) -> bool:
    """质量闸②增强：出题时要求 VLM 附**原文依据句**（quote，抄原文形态）——
    依据句滑窗命中 gold 即锚定成立（比改写型 ref_answer 可靠）。"""
    if not (quote or "").strip():
        return False
    joined = _norm_text(" ".join(gold_contents))
    q = _norm_text(quote)
    if len(q) < 8:
        return False
    step = max(4, len(q) // 10)
    windows = [q[i:i + 8] for i in range(0, max(1, len(q) - 7), step)]
    hits = sum(1 for w in windows if w in joined)
    return hits / max(1, len(windows)) >= 0.7


def bm25_pseudo_check(gold_rank: int, gold_score: float, runner_up: float | None,
                      gap_ratio: float = 3.0) -> bool:
    """质量闸③：BM25 伪题检测——gold 断层第一（score/次名 > gap_ratio）=字面重叠题。

    返回 True=是伪题（需重写）。
    """
    if gold_rank != 1:
        return False
    if not runner_up or runner_up <= 0:
        return False
    return gold_score / runner_up > gap_ratio


# ---------- 块池（从 t_chunk 回表；出题脚本容器端跑） ----------

def load_chunk_pool(doc_id: str) -> list[dict]:
    """一篇论文的全部块（出题原料）：kind/content/page/chunk_id/heading_path。"""
    from doclens.index.db import connect
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT chunk_id, kind, content, page, heading_path FROM t_chunk "
                "WHERE doc_id=%s AND kind IN ('text','table','caption') ORDER BY chunk_id",
                (doc_id,))
            return [{"chunk_id": r[0], "kind": r[1], "content": r[2], "page": r[3],
                     "heading_path": json.loads(r[4]) if r[4] else []}
                    for r in cur.fetchall()]
    finally:
        conn.close()


def load_image_units(doc_id: str) -> list[dict]:
    """图注+原图路径（图表题出题原料：caption 文本 + 原图 bytes 路径）。"""
    from doclens.index.db import connect
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT chunk_id, content, page, image_path FROM t_chunk "
                "WHERE doc_id=%s AND kind='image' AND image_path IS NOT NULL ORDER BY chunk_id",
                (doc_id,))
            return [{"chunk_id": r[0], "content": r[1] or "", "page": r[2],
                     "image_path": r[3]} for r in cur.fetchall()]
    finally:
        conn.close()


# ---------- 出题 prompt 模板（三套题型 + 不可答/负面） ----------

_JSON_RULES = (
    "只输出一个 JSON 数组，不要解释、不要代码块围栏。"
    "每个元素字段：question(字符串)、ref_answer(参考答案字符串，可同义改写)、"
    "**quote(直接摘抄的原文依据句，逐字复制片段中的句子，不得改写)**、"
    "evidence_chunk_ids(支撑该题的 chunk_id 数组)、"
    "difficulty(\"direct\"或\"synthesis\")。"
)

_TEXT_PROMPT = (
    "你是 RAG 评测题集的出题专家。下面是一篇学术论文的若干文本片段（已标注 chunk_id）。"
    "请基于这些内容出 {n} 道**理解型**中文问答题：\n"
    "要求：1) 问题考察对内容的理解，禁止直接复述原文措辞（同义改写）；"
    "2) 答案必须完全出自所给片段（在 evidence_chunk_ids 标注的片段里能找到）；"
    "3) 禁止出'答案只是一个图中数字/只在图表里'的题（你没有看到图）；"
    "4) 覆盖不同片段，不要都集中在一个片段；5) 每题标注 direct（单片段可答）或 synthesis（需综合多片段）。\n\n"
    "片段：\n{chunks}\n\n" + _JSON_RULES
)

_TABLE_PROMPT = (
    "你是 RAG 评测题集的出题专家。下面是论文中的表格（已文本化为 markdown 卡片，标注 chunk_id）。"
    "请出 {n} 道**表格数据题**（比较/极值/占比/趋势类）：\n"
    "要求：1) 答案必须能在表格文本中找到；2) 优先出需要跨行/跨列对比的题（考察结构理解）；\n\n"
    "表格：\n{chunks}\n\n" + _JSON_RULES
)

_FIG_PROMPT = (
    "你是 RAG 评测题集的出题专家。下面是论文中某图表的**图注文本**和**原图**。"
    "请看图出 {n} 道**图表内容理解题**：\n"
    "要求：1) 问题问图中可视觉确认的信息（趋势/对比/结构/标注文字）；"
    "2) 参考答案必须与图注或图中可见信息一致；"
    "3) 如果图内容过于简单（无信息量），宁可少出。\n\n"
    "图注：{caption}\n\n" + _JSON_RULES
)

_UNANS_PROMPT = (
    "你是 RAG 评测题集的出题专家。下面是论文的主题概述。"
    "请出 {n} 道**语料中无法回答**的问题（用于测试系统的拒答能力）：\n"
    "模板四选一：①把文中某数字/年份改成不存在的值提问；②询问论文完全没有涉及的概念或方法；"
    "③要求论文中不存在的代码/数据集/联系方式；④把两篇不相关论文的事实拼接成假前提。\n"
    "要求：问题必须看起来合理（与论文主题相关），但**全文确实没有答案**；"
    "ref_answer 填'应拒答'。每个元素额外加字段 trap_reason（一句话说明为何不可答）。\n\n"
    "论文概述：\n{summary}\n\n" + _JSON_RULES
)

_NOISE_PROMPT = (
    "你是 RAG 评测题集的出题专家。下面是论文片段。请出 {n} 道**正常可回答**的问题"
    "（用于噪声鲁棒性测试：评测时会在上下文里注入无关干扰段落）：\n"
    "要求：答案必须明确出自所给片段（这样注噪后答错才能归因于噪声）。\n\n"
    "片段：\n{chunks}\n\n" + _JSON_RULES
)


async def generate_candidates_for_doc(doc_id: str, *, per_type: int = 6) -> dict:
    """一篇论文的全部候选题（VLM 出题 + 锚定校验）。

    返回 {doc_id, candidates: [EvalQuestion...], errors: [..]}。
    chunk 池与图注从 t_chunk 回表；文本/表格题用文本池，图表题带原图。
    """
    from doclens.pipeline import _load_image_blob
    pool = load_chunk_pool(doc_id)
    imgs = load_image_units(doc_id)
    candidates: list[EvalQuestion] = []
    errors: list[str] = []

    def _fmt_chunks(chunks: list[dict], limit: int = 1400) -> str:
        out = []
        for c in chunks:
            out.append(f"[{c['chunk_id']}] ({c['kind']} p{c['page']}) "
                       f"{(c['content'] or '')[:limit]}")
        return "\n\n".join(out)

    def _pick(pool_: list[dict], n: int) -> list[list[dict]]:
        """把池子按相邻分组（试审批教训：3 块视野太窄 → 5 块）。"""
        groups = []
        for i in range(0, len(pool_), n):
            groups.append(pool_[i:i + n])
        return groups or []

    import asyncio
    sem = asyncio.Semaphore(2)  # VLM 限速

    async def _ask(prompt: str, images: list[bytes] | None = None) -> list[dict]:
        async with sem:
            raw = await _chat_json(prompt, images=images)
        return raw if isinstance(raw, list) else []

    # 1) 文本题（相邻 5 块一组，每组 1 题）
    text_groups = _pick([c for c in pool if c["kind"] == "text"], 5)
    for g in text_groups[:per_type]:
        raw = await _ask(_TEXT_PROMPT.format(n=1, chunks=_fmt_chunks(g)))
        for item in raw[:1]:
            gold_ids = item.get("evidence_chunk_ids") or [c["chunk_id"] for c in g]
            candidates.append(EvalQuestion(
                q_id="", type="text", lang="zh",
                question=item.get("question", ""),
                ref_answer=item.get("ref_answer", ""),
                gold=[{"doc_id": doc_id, "chunk_id": cid} for cid in gold_ids],
                difficulty=item.get("difficulty", "direct"),
                quote=_extract_quote(item)))

    # 2) 表格题
    tables = [c for c in pool if c["kind"] == "table"]
    for t in tables[:per_type]:
        raw = await _ask(_TABLE_PROMPT.format(n=1, chunks=_fmt_chunks([t], limit=1800)))
        for item in raw[:1]:
            candidates.append(EvalQuestion(
                q_id="", type="table", lang="zh",
                question=item.get("question", ""),
                ref_answer=item.get("ref_answer", ""),
                gold=[{"doc_id": doc_id, "chunk_id": t["chunk_id"]}],
                quote=_extract_quote(item)))
            if len([c for c in candidates if c.type == "table"]) >= per_type:
                break

    # 3) 图表题（带原图）
    figs = imgs[:per_type]
    for im in figs:
        blob = _load_image_blob(doc_id, im["image_path"])
        if blob is None:
            continue
        raw = await _ask(_FIG_PROMPT.format(n=1, caption=im["content"][:600]),
                         images=[blob])
        for item in raw[:1]:
            candidates.append(EvalQuestion(
                q_id="", type="figure", lang="zh",
                question=item.get("question", ""),
                ref_answer=item.get("ref_answer", ""),
                gold=[{"doc_id": doc_id, "chunk_id": im["chunk_id"]}]))
            if len([c for c in candidates if c.type == "figure"]) >= per_type:
                break

    # 4) 不可答（反事实四模板）
    summary = _fmt_chunks(pool[:6], limit=800)
    raw = await _ask(_UNANS_PROMPT.format(n=4, summary=summary))
    for item in (raw or [])[:4]:
        candidates.append(EvalQuestion(
            q_id="", type="unanswerable", lang="zh",
            question=item.get("question", ""),
            ref_answer="应拒答",
            gold=[], answerable=False,
            gold_hint=item.get("trap_reason", "")))

    # 5) 噪声题（题面正常，评测时注噪）
    noise_groups = _pick([c for c in pool if c["kind"] == "text"], 5)
    for g in noise_groups[:4]:
        raw = await _ask(_NOISE_PROMPT.format(n=1, chunks=_fmt_chunks(g)))
        for item in raw[:1]:
            candidates.append(EvalQuestion(
                q_id="", type="noise", lang="zh",
                question=item.get("question", ""),
                ref_answer=item.get("ref_answer", ""),
                gold=[{"doc_id": doc_id, "chunk_id": cid}
                      for cid in (item.get("evidence_chunk_ids") or [g[0]["chunk_id"]])],
                noise_variant=True,
                quote=_extract_quote(item)))

    # 锚定校验（质量闸②，试审批 20/20 覆没的修正）：
    # 优先 quote 锚定（VLM 抄的原文依据句）→ 双向 ref 锚定兜底
    content_by_id = {c["chunk_id"]: c["content"] for c in pool}
    errors = []
    kept = []
    for q in candidates:
        if not q.question.strip() or (q.answerable and not q.ref_answer.strip()):
            errors.append(f"空题弃: {q.question[:30]}")
            continue
        if q.answerable and q.gold:
            contents = [content_by_id.get(g["chunk_id"], "") for g in q.gold]
            anchored = (anchor_via_quote(q.quote, contents)
                        or anchor_check(q.ref_answer, contents))
            if not anchored:
                errors.append(f"锚定失败弃: {q.question[:40]}")
                continue
        kept.append(q)
    return {"doc_id": doc_id, "candidates": kept, "errors": errors}


def _extract_quote(item: dict) -> str:
    return item.get("quote") or item.get("evidence_quote") or ""


# ---------- 持久化 ----------

def save_candidates(doc_id: str, result: dict, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    p = out_dir / f"candidates_{doc_id}.json"
    p.write_text(json.dumps({
        "doc_id": doc_id,
        "candidates": [q.to_dict() for q in result["candidates"]],
        "errors": result["errors"],
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return p
