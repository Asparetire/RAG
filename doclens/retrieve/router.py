"""语言检测与 BM25 路由决策（m3-runbook 3.3；K3，D11+R14）。

职责：
- detect_lang：查询语言三态判定（zh/en）——中文字符（\\u4e00-\\u9fff）占比 ≥0.3 判 zh；
- bm25_weight_for：语言 → BM25 路权重，供调用方传给 hybrid.retrieve(bm25_weight=…)。

设计依据（specs/plans/m3-runbook.md K3 / specs/research/m3-retrieval-generation-survey.md）：
- D11  zh 查询 **BM25 旁路**（权重 0.0）：jieba 对中英混排的切分噪声使 BM25 在 zh 查询上
       先天吃亏，与其降权不如整路旁路；降权 0.5 档**留 M5**（FR-3.4 中英对照调参位），
       本模块暂不返回 0.5（常量 _WEIGHT_HALF 注释占位）。
- R14  不加查询翻译：研究证实翻译劣于多语言嵌入（eval 调研已核），检索侧语言适配只做路由。
- 纯函数、无 IO：语言字段由调用方（3.5 query_cli 编排）写入 trace，本模块不落盘。
"""

from __future__ import annotations

from doclens.config import Profile

ZH_RATIO_THRESHOLD = 0.3  # 中文占比判 zh 阈值（D11 既定：≥0.3 → zh）
_BYPASS = 0.0             # zh：BM25 旁路（D11）
_WEIGHT_HALF = 0.5        # 降权档：留 M5 FR-3.4 调参（本模块暂不返回，占位防魔数漂移）


def detect_lang(text: str) -> str:
    """语言检测（纯函数）：中文字符占比 ≥0.3 → "zh"，否则 "en"；空串 → "en"。

    占比 = \\u4e00-\\u9fff 字符数 / 全部字符数（分母含空格标点——标点/符号密度
    本身是语言信号，不做剔除）。混排查询里少量英文专名（如"什么是 BERT 模型？"）
    不会把占比拉到 0.3 以下，符合 D11 的判 zh 预期。
    """
    if not text:
        return "en"
    zh = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    return "zh" if zh / len(text) >= ZH_RATIO_THRESHOLD else "en"


def bm25_weight_for(lang: str, profile: Profile) -> float | None:
    """语言 → BM25 路权重：zh → 0.0（D11 旁路）；其余（含 en）→ None（正常参与融合）。

    返回值语义与 hybrid.retrieve(bm25_weight=…) 对齐：None=正常 / 0.0=旁路 / 0.5=降权（M5 起）。
    - profile 参数为 M5 留位（FR-3.4 按消融档覆写权重），当前实现不读取其字段；
    - 未知 lang 一律按正常（None）处理——旁路只对确认的 zh 生效，宁多召回不误杀。
    """
    if lang == "zh":
        return _BYPASS
    return None
