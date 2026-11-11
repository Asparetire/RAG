"""DocLens 生成四件套（m3-runbook §3.4：K4 上下文组装 / K5 生成 / K6 引用 / K7 兜底）。

- context.py：重排结果 → Source N 编号 + 图文交错的最终上下文（K4/R12+D12）
- vlm.py：glm-5.3-flash 思考模型生成，reasoning_content 双字段分流（K5/R9/R14）
- citations.py：行内引用四类格式解析 + [n]→(doc,page,bbox) 映射（K6/R11）
- fallback.py：judge 充分性判定 + 兜底决策 + 引用自检（K7/R6/R13）
"""

from doclens.generate.citations import (
    CitationRef,
    CitationReport,
    DegradedSentence,
    SentenceCitations,
    map_to_sources,
    parse_citations,
)
from doclens.generate.context import (
    AssembledContext,
    ImageRef,
    SourceBlock,
    assemble,
    to_prompt_parts,
)
from doclens.generate.fallback import (
    REFUSAL_TEXT,
    FallbackDecision,
    JudgeVerdict,
    decide_fallback,
    judge_sufficiency,
    self_check,
)
from doclens.generate.vlm import (
    SYSTEM_PROMPT,
    GenResult,
    generate_answer,
)

__all__ = [
    # context
    "AssembledContext",
    "ImageRef",
    "SourceBlock",
    "assemble",
    "to_prompt_parts",
    # vlm
    "SYSTEM_PROMPT",
    "GenResult",
    "generate_answer",
    # citations
    "CitationRef",
    "CitationReport",
    "DegradedSentence",
    "SentenceCitations",
    "map_to_sources",
    "parse_citations",
    # fallback
    "REFUSAL_TEXT",
    "FallbackDecision",
    "JudgeVerdict",
    "decide_fallback",
    "judge_sufficiency",
    "self_check",
]
