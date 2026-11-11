"""K6 引用解析映射（m3-runbook §3.4；调研 R11）。

解析语义（ALCE 先例 + 修订）：
- 行内引用四类格式全兼容：`[1]`、`[1,2]`、`[1][2]`、`[1-3]`（区间闭区间展开；
  兼容 `1, 2` 空格与中文逗号 `1，2`）。
- **ALCE 原版坑**：`re.findall(r"\\[\\d+", answer)` 只抓 "[数字" 前缀，对
  `[1,2]` 只能拿到 "[1"——逗号后的 2 被静默丢掉，引用评测失真。本实现先抓
  完整方括号组、再在组内按逗号/区间展开，四类格式统一覆盖。
- **无效 n（越界/0/负）→ 所在句子降级**：整句记入 degraded_sentences（含
  bad_ids），**不静默删、不重写答案**——静默删会掩盖引用幻觉、评测失真（R11）。
- `cited` = 全答案范围内的**有效**引用（∈valid_ids），去重、首次出现序；
  无效编号只留在 per_sentence / degraded_sentences 的 trace 里，不进 cited。
- 无引用答案（has_any=False）不报错：report 原样返回——兜底交给 fallback 的
  第三道防线（prompt "无依据明确声明" + self_check），本模块不惩罚。

句子切分（简化规则，只影响 trace 粒度、不影响 cited）：。！？随时成句；
英文 "." 仅后跟空白/串尾时成句（保住 "93.5%" 这类小数不被切碎；"Fig. 1" 这类
缩写仍会误切，可接受）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from doclens.generate.context import SourceBlock

# 方括号引用组：内容只允许 数字/逗号（含中文）/连字符（含 en-dash）/空白
_BRACKET_RE = re.compile(r"\[([0-9,，\-–\s]+)\]")
_RANGE_RE = re.compile(r"(\d+)\s*[-–]\s*(\d+)")
_NEG_RE = re.compile(r"-(\d+)")
# 句子切分：。！？后必切成句点；英文 "." 仅在后跟空白/串尾时成句
_SENT_SPLIT_RE = re.compile(r"(?<=[。！？!?])|(?<=\.)(?=\s|$)")
_RANGE_SPAN_CAP = 50  # 异常大区间防御（如 [1-9999] 只展开前 50 个）


@dataclass
class SentenceCitations:
    """单个句子的解析结果（原文 + 该句所有引用编号，含无效的）。"""

    sentence: str
    ids: list[int]


@dataclass
class DegradedSentence:
    """含无效引用的句子（降级标记落 trace：不静默删、不重写答案）。"""

    sentence: str
    bad_ids: list[int]


@dataclass
class CitationReport:
    """引用解析报告。"""

    cited: list[int]                        # 有效引用，去重、首次出现序
    per_sentence: list[SentenceCitations]
    degraded_sentences: list[DegradedSentence]
    has_any: bool                           # 答案里是否出现过任何方括号引用（含无效）


@dataclass
class CitationRef:
    """[n] → (doc, page, bbox) 映射结果（引用溯源定位）。"""

    source_n: int
    chunk_id: str
    doc_id: str
    page: int | None
    bbox: list[float] | None = None


def _expand_group(inner: str) -> list[int]:
    """方括号组内展开：`1` / `1,2` / `1, 2` / `1，2` / `1-3` → 编号列表。"""
    ids: list[int] = []
    for part in re.split(r"[,，]", inner):
        part = part.strip()
        if not part:
            continue
        m = _RANGE_RE.fullmatch(part)
        if m:
            lo, hi = int(m.group(1)), int(m.group(2))
            if lo <= hi:  # 逆序区间（如 [5-2]）视为无效表达，跳过
                ids.extend(range(lo, min(hi, lo + _RANGE_SPAN_CAP - 1) + 1))
            continue
        if part.isdigit():
            ids.append(int(part))
            continue
        m_neg = _NEG_RE.fullmatch(part)
        if m_neg:
            ids.append(-int(m_neg.group(1)))  # 负数保留为无效编号 → 走句子降级
    return ids


def _split_sentences(text: str) -> list[str]:
    return [p.strip() for p in _SENT_SPLIT_RE.split(text) if p and p.strip()]


def parse_citations(answer: str, valid_ids: set[int]) -> CitationReport:
    """解析答案中的行内引用（纯函数）。

    valid_ids：有效的 Source 编号集合（1 起连续；来自 ctx.sources）。
    无引用答案不报错：has_any=False，report 原样返回（兜底由 fallback 处理）。
    """
    per_sentence: list[SentenceCitations] = []
    degraded: list[DegradedSentence] = []
    cited: list[int] = []
    seen: set[int] = set()
    has_any = False

    for sent in _split_sentences(answer or ""):
        ids: list[int] = []
        for m in _BRACKET_RE.finditer(sent):
            ids.extend(_expand_group(m.group(1)))
        if ids:
            has_any = True
        per_sentence.append(SentenceCitations(sentence=sent, ids=ids))
        bad = sorted({i for i in ids if i not in valid_ids})
        if bad:
            degraded.append(DegradedSentence(sentence=sent, bad_ids=bad))
        for i in ids:
            if i in valid_ids and i not in seen:
                seen.add(i)
                cited.append(i)

    return CitationReport(cited=cited, per_sentence=per_sentence,
                          degraded_sentences=degraded, has_any=has_any)


def map_to_sources(report: CitationReport, sources: list[SourceBlock]) -> list[CitationRef]:
    """[n] → (doc, page, bbox)（SourceBlock 由 context.py 从 t_chunk 回表带上 bbox）。

    只映射 cited 里的有效编号；无匹配 Source 的编号跳过（双保险）。
    """
    by_n = {s.source_n: s for s in sources}
    refs: list[CitationRef] = []
    for n in report.cited:
        s = by_n.get(n)
        if s is None:
            continue
        refs.append(CitationRef(source_n=n, chunk_id=s.chunk_id, doc_id=s.doc_id,
                                page=s.page, bbox=s.bbox))
    return refs
