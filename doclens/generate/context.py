"""K4 上下文组装（m3-runbook §3.4；调研 R12 + D12）。

职责：把重排后的 chunk_id 有序列表（rerank 输出）+ 回表成员数据（members，
t_chunk 回表字段：chunk_id/doc_id/kind/page/content/bbox/heading_path/image_path/caption，
结构对齐 3.1 hybrid 检索命中约定）组装成 "Source N 编号 + 图文交错" 的最终上下文。

要点（与 runbook K4 一一对应）：
- **Source N 编号（D12/R11）**：展示序中每块编号 Source N（N 从 1 递增）——
  生成侧行内引用 [n] 与 citations.py 的 [n]→(doc,page,bbox) 映射共用该编号。
- **图文交错（R12，LlamaIndex 多模态引用先例）**：caption 块与其原图同 Source——
  top-k 内存在同 image_path 的 image 块时，原图作为附件挂在该 caption 的 Source
  下（image 块不再单独占编号，避免同图正文双份）；image 块独立命中（其 caption
  未入选）时自成一个 Source，caption 文本作正文。
- **选图上限（FR-4.1，max_images=5）**：图超限时按"所属 Source 的排序分"取前
  max_images 张——实现上按展示序先到先得（展示序=ranking 序，排位靠前即分高）；
  未入选的图 caption 文本保留在正文、原图不附。
- **首尾优先（D12）简化声明**：lost-in-the-middle 的对策本应是"重要块放两端"
  （首尾优先装载），本版**直接采用 ranking 原序**——理由：top-20 已是重排精选，
  次序即相关度，主要风险是"堆太长"而非顺序；"奇数位填头、偶数位填尾"的精排版
  留 M5 消融对比，届时只改本函数展示序，Source 编号与引用映射不受影响。
- **E 档（use_ctx_prefix=True）**：content 前拼 t_ctx_prefix 前缀（"\n" 分隔）；
  前缀由调用方经 ctx_prefixes 传入（本模块不查库），无前缀的块原样。
- 本模块**不做任何文件/网络 IO**：图片文件读取归 3.5 CLI，base64 编码归 vlm.py
  （to_prompt_parts 经 image_urls 注入 data URL）。
"""

from __future__ import annotations

import json
from dataclasses import dataclass


@dataclass
class SourceBlock:
    """最终上下文中的一个证据块（Source N）。"""

    source_n: int                      # 展示序编号（从 1 递增；行内引用 [n] 即此编号）
    chunk_id: str
    doc_id: str
    kind: str                          # text / table / caption / image
    page: int | None
    heading_path: list[str] | None
    content: str                       # E 档时含 ctx 前缀；image 块用 caption 文本
    image_path: str | None = None
    bbox: list[float] | None = None    # FR-2.4 [x0,y0,x1,y1] 0–1 归一化（引用映射用）


@dataclass
class ImageRef:
    """随 Source 附上的原图引用（原图文件读取归 3.5 CLI，编码归 vlm.py）。"""

    source_n: int
    image_path: str
    doc_id: str
    page: int | None


@dataclass
class AssembledContext:
    """组装结果：生成（vlm.py）与兜底判定（fallback.py）共用的上下文载体。"""

    question: str
    sources: list[SourceBlock]
    images: list[ImageRef]
    truncated: bool                    # ranked_ids 超过 final_top 而截断


def _maybe_json_list(val) -> list | None:
    """回表 JSON 列容错：pymysql 对 JSON 列可能回传 str——list 原样、str 尝试解析、其余 None。"""
    if isinstance(val, list):
        return val
    if isinstance(val, str) and val.strip():
        try:
            parsed = json.loads(val)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, list) else None
    return None


def assemble(
    question: str,
    ranked_ids: list[str],
    members: dict[str, dict],
    *,
    final_top: int = 20,
    max_images: int = 5,
    use_ctx_prefix: bool = False,
    ctx_prefixes: dict[str, str] | None = None,
) -> AssembledContext:
    """组装最终上下文（纯函数，无 IO）。

    ranked_ids：重排后的 chunk_id 有序列表（3.2 rerank 输出）；
    members：chunk_id → 回表/命中数据 dict（含 content/bbox/heading_path/image_path/caption 等，
    缺 key 容错）。回表缺失的块跳过不进上下文（防脏数据）。
    """
    top = list(ranked_ids[:final_top])
    truncated = len(ranked_ids) > final_top
    prefixes = ctx_prefixes or {}

    taken: set[str] = set()        # 已作为图片附件的 image chunk_id（不再单独占 Source）
    sources: list[SourceBlock] = []
    images: list[ImageRef] = []
    used_paths: set[str] = set()   # 已附原图的 image_path（同图只附一次）

    def _companion(caption_cid: str, image_path: str) -> str | None:
        """在 top 内找同 image_path 且未被认领的 image 块（R12：原图紧跟 caption 同 Source）。"""
        for other in top:
            if other == caption_cid or other in taken:
                continue
            om = members.get(other) or {}
            if om.get("kind") == "image" and om.get("image_path") == image_path:
                return other
        return None

    for cid in top:
        if cid in taken:
            continue
        m = members.get(cid)
        if m is None:              # 回表缺失的块不进上下文
            continue
        kind = m.get("kind") or "text"
        image_path = m.get("image_path") or None
        # 正文：content 优先，空则退 caption 列（image 块的正文通常只有 caption）
        text = (m.get("content") or "").strip() or (m.get("caption") or "").strip()
        companion = _companion(cid, image_path) if (kind == "caption" and image_path) else None
        if not text and (kind == "image" or companion):
            text = "（图像块，无文字内容）"
        # E 档：t_ctx_prefix 前缀拼在正文前（"\n" 分隔；无前缀的块原样）
        if use_ctx_prefix and prefixes.get(cid):
            text = f"{prefixes[cid]}\n{text}" if text else prefixes[cid]
        sb = SourceBlock(
            source_n=len(sources) + 1,
            chunk_id=cid,
            doc_id=m.get("doc_id") or "",
            kind=kind,
            page=m.get("page"),
            heading_path=_maybe_json_list(m.get("heading_path")),
            content=text,
            image_path=image_path,
            bbox=_maybe_json_list(m.get("bbox")),
        )
        sources.append(sb)
        # 图附件：standalone image 块，或 caption 认领到 top 内原图（R12 同 Source 交错）
        if kind == "image" or companion:
            if image_path and image_path not in used_paths:
                used_paths.add(image_path)
                images.append(ImageRef(source_n=sb.source_n, image_path=image_path,
                                       doc_id=sb.doc_id, page=sb.page))
            if companion:
                taken.add(companion)

    # 选图限额（FR-4.1）：images 已按"所属 Source 的展示序（=排序分）"排列，先到先得；
    # 超额图不附原图，其 caption 文本已保留在对应 SourceBlock.content 里。
    return AssembledContext(question=question, sources=sources,
                            images=images[:max_images], truncated=truncated)


def to_prompt_parts(ctx: AssembledContext, *, image_urls: dict[str, str] | None = None) -> list[dict]:
    """组装 openai chat messages 的 user content 数组（多模态格式）。

    返回：[{"type": "text", "text": <问题 + 全部 Source 合成的大字符串>},
           {"type": "image_url", "image_url": {"url": <data URL>}}, ...]
    - text 段格式：问题在前，随后每个 Source 一段
      `Source N: (doc, p页, kind) 正文`（LlamaIndex "Source N:" 块头先例）；
    - 图片 part 仅当调用方传入 image_urls（image_path → data URL）时生成；
      **本模块不做文件读取**——读文件归 3.5 CLI、base64 编码归 vlm.py。
    """
    lines = [f"问题：{ctx.question}", ""]
    for s in ctx.sources:
        page = s.page if s.page is not None else "?"
        lines.append(f"Source {s.source_n}: ({s.doc_id}, p{page}, {s.kind}) {s.content}".rstrip())
    parts: list[dict] = [{"type": "text", "text": "\n".join(lines).strip()}]
    for img in ctx.images:
        url = (image_urls or {}).get(img.image_path)
        if url:
            parts.append({"type": "image_url", "image_url": {"url": url}})
    return parts
