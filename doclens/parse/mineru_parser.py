"""MinerU 解析桥接（m1-runbook 步骤 1.3；PRD FR-1.1/1.2/1.3）。

职责：
- subprocess 调 doclens-mineru 环境的 mineru-kit CLI（plan D2：torch 系依赖隔离在独立环境）；
- 解析 zip 产物 → 统一文档模型 DoclensDoc（FR-1.2，映射表见下方常量）；
- 图注绑定（FR-1.3）：优先用 MinerU 自带的 captions 数组（实测它已把图注归组好），
  为空时做"同页就近 + Fig/Table/图/表 前缀"兜底绑定；
- sha256 缓存（FR-1.1 增量）：产物落 data/parsed/<doc_id>/（doc_id = sha256 前 12 位），
  已有 doc.json 直接返回，不重复解析、不重复花时间。

MinerU 4.1.7 `-f zip` 产物（实测结构，夹具见 tests/fixtures/mineru_sample/）：
- structured_content.json：{"pages": [{"page_idx": 0 起, "blocks": [...]}]}，
  块的 content 是纯字符串，bbox 为 0–1 归一化坐标 [x0, y0, x1, y1]；
- middle_json.json：metadata.document{title, identifiers(["doi:10.xxxx/yyy"]), page_count...}
  + pages[].blocks（content 为分段数组，image/chart 的 body 子块带 image_path）；
- images/：按页命名的图表截图（page_N_chart_M.jpg / image / equation）。

块类型映射（2026-11-10 实测 11 种类型全覆盖）：
    doc_title / paragraph_title → title     text / ref_text / equation → text
    chart / image               → image     header / footer / page_number / page_footnote → 丢弃
图片路径：structured_content 的 image/chart 块不带 image_path，
按 (page_idx, bbox) 从 middle_json 的 image_body/chart_body 子块配对。
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from doclens.config import PARSED_DIR, settings
from doclens.parse.schema import Block, DoclensDoc

_TO_TEXT = frozenset({"text", "ref_text", "equation"})
_TO_TITLE = frozenset({"doc_title", "paragraph_title"})
_TO_IMAGE = frozenset({"image", "chart"})
_TO_TABLE = frozenset({"table"})
_DISCARD = frozenset({"header", "footer", "page_number", "page_footnote"})

# 整图/整表级图注前缀（可信图注）；子图面板标签、句子碎片一律视为不可信
_FIG_PREFIX = re.compile(r"^\s*(?:Fig\.?|Figure|图)\s*[0-9０-９]+", re.IGNORECASE)
_TBL_PREFIX = re.compile(r"^\s*(?:Table|表)\s*[0-9０-９]+", re.IGNORECASE)
# 兜底图注前缀：同页文本块里找 Fig/Table/图/表 开头的句子
_CAPTION_PREFIX = re.compile(r"^\s*(?:Fig\.?|Figure|Table|图|表)\s*[0-9０-９]+", re.IGNORECASE)
_DOI_RE = re.compile(r"10\.\d{4,9}/[^\s\"'<>]+")


def sha256_of(pdf_path: Path) -> str:
    """流式计算文件 sha256（与 corpus_intake 同规则：hex 小写）。"""
    h = hashlib.sha256()
    with Path(pdf_path).open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _plain_text(content: Any) -> str:
    """structured_content 的 content 是纯字符串；middle_json 的是分段列表——都拍平成字符串。"""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            seg.get("content", "") for seg in content if isinstance(seg, dict) and isinstance(seg.get("content"), str)
        )
    return ""


def _doc_meta(middle: dict) -> tuple[str | None, str | None]:
    """从 middle_json.metadata.document 提取标题与 DOI（论文级去重依据）。"""
    doc = (middle.get("metadata") or {}).get("document") or {}
    title = str(doc["title"]).strip() if doc.get("title") else None
    doi: str | None = None
    for ident in doc.get("identifiers") or []:
        s = str(ident).strip()
        if s.lower().startswith("doi:"):
            doi = s[4:].strip()
            break
    if doi is None:  # 兜底：subject/description 里常写 "Nature Communications, doi:10.xxx/yyy"
        m = _DOI_RE.search(f"{doc.get('subject', '')} {doc.get('description', '')}")
        doi = m.group(0).rstrip(".,;)") if m else None
    return title, doi


def _image_path_lookup(middle: dict) -> dict[tuple[int, tuple[float, ...]], str]:
    """(page_idx, bbox) -> image_path，从 middle_json 的 image_body/chart_body 子块收集。"""
    lookup: dict[tuple[int, tuple[float, ...]], str] = {}
    for pg in middle.get("pages", []):
        pidx = int(pg.get("page_idx", 0))
        for b in pg.get("blocks", []):
            content = b.get("content")
            if not isinstance(content, list):
                continue
            for sub in content:
                if (
                    isinstance(sub, dict)
                    and sub.get("type") in ("image_body", "chart_body")
                    and sub.get("image_path")
                    and sub.get("bbox")
                ):
                    key = (pidx, tuple(round(float(x), 6) for x in sub["bbox"]))
                    lookup[key] = str(sub["image_path"])
    return lookup


def _table_to_markdown(text: str) -> str:
    """HTML 表格 → Markdown 线性化（PRD FR-1.3）；非 HTML 输入原样返回。"""
    if "<table" not in text.lower():
        return text
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", text, re.S | re.I)
    lines: list[str] = []
    for row in rows:
        cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S | re.I)
        cells = [" ".join(re.sub(r"<[^>]+>", "", c).split()) for c in cells]
        if cells:
            lines.append("| " + " | ".join(cells) + " |")
    if len(lines) >= 1:  # 首行当表头，插 Markdown 分隔行
        n = lines[0].count("|") - 1
        lines.insert(1, "|" + "---|" * n)
    return "\n".join(lines) if lines else text


def _prefix_caption(caption: str | None) -> str | None:
    """可信图注 = Fig/Figure/图/Table/表 + 编号 开头；面板标签、句子碎片返回 None。"""
    if caption and (_FIG_PREFIX.match(caption) or _TBL_PREFIX.match(caption)):
        return caption
    return None


def _center(bbox: list[float]) -> tuple[float, float]:
    return ((bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2)


def _bound_caption(raw: dict) -> str | None:
    """MinerU 已归组的图注（captions 数组），多条以空格拼接。"""
    texts = [
        str(c.get("content", "")).strip()
        for c in raw.get("captions") or []
        if isinstance(c, dict)
    ]
    texts = [t for t in texts if t]
    return " ".join(texts) if texts else None


def _fallback_caption(raw: dict, page_blocks: list[dict], self_idx: int) -> str | None:
    """兜底绑定：同页找带 Fig/Table/图/表 前缀、纵向离图最近的 text 块。"""
    bbox = raw.get("bbox")
    if not bbox:
        return None
    bottom = float(bbox[3])
    best: tuple[float, str] | None = None
    for j, other in enumerate(page_blocks):
        if j == self_idx or other.get("type") not in _TO_TEXT:
            continue
        text = _plain_text(other.get("content")).strip()
        if not _CAPTION_PREFIX.match(text):
            continue
        ob = other.get("bbox")
        if not ob:
            continue
        gap = abs(float(ob[1]) - bottom)  # 对方块顶边到图片底边的纵向距离
        if best is None or gap < best[0]:
            best = (gap, text)
    return best[1][:500] if best else None


def build_doc(sha256: str, structured: dict, middle: dict) -> DoclensDoc:
    """两个 JSON → 统一文档模型。纯函数，单测直接喂夹具。

    图注绑定两阶段：
    ① 逐块先记 MinerU 原始图注；② 页级收尾——不可信图注（面板标签/碎片）
    继承同页最近的可信图注（同一张大图的兄弟子图，bbox 中心距最近），
    再不行走"同页 Fig/Table 前缀文本块就近"兜底，最后才是 None。
    """
    title, doi = _doc_meta(middle)
    img_lookup = _image_path_lookup(middle)
    blocks: list[Block] = []
    heading_stack: list[tuple[int, str]] = []  # (level, 标题文字)
    order = 0
    raw_by_page: dict[int, list[dict]] = {}  # page_no -> 原始块（文本兜底用）
    img_drafts: dict[int, list[tuple[int, list[float] | None, str | None]]] = {}  # page_no -> [(blocks 下标, bbox, 原始图注)]

    for pg in structured.get("pages", []):
        page_no = int(pg.get("page_idx", 0)) + 1  # 统一模型用 1 起页码
        page_blocks = pg.get("blocks", [])
        raw_by_page[page_no] = page_blocks
        for i, raw in enumerate(page_blocks):
            rtype = raw.get("type")
            if rtype in _DISCARD:
                continue
            bbox = [float(x) for x in raw["bbox"]] if raw.get("bbox") else None

            if rtype in _TO_TITLE:
                text = _plain_text(raw.get("content")).strip()
                if not text:
                    continue
                level = int(raw.get("level") or 1)
                ancestors = [s for _, s in heading_stack]
                while heading_stack and heading_stack[-1][0] >= level:
                    heading_stack.pop()
                heading_stack.append((level, text))
                blocks.append(
                    Block(type="title", page=page_no, content=text, bbox=bbox, heading_path=ancestors, order=order)
                )
                order += 1

            elif rtype in _TO_TEXT:
                text = _plain_text(raw.get("content")).strip()
                if not text:
                    continue
                blocks.append(
                    Block(
                        type="text",
                        page=page_no,
                        content=text,
                        bbox=bbox,
                        heading_path=[s for _, s in heading_stack],
                        order=order,
                    )
                )
                order += 1

            elif rtype in _TO_TABLE:
                text = _table_to_markdown(_plain_text(raw.get("content"))).strip()
                if not text:
                    continue
                blocks.append(
                    Block(
                        type="table",
                        page=page_no,
                        content=text,
                        bbox=bbox,
                        caption=_bound_caption(raw),
                        heading_path=[s for _, s in heading_stack],
                        order=order,
                    )
                )
                order += 1

            elif rtype in _TO_IMAGE:
                caption = _bound_caption(raw)
                key = (int(pg.get("page_idx", 0)), tuple(round(float(x), 6) for x in raw.get("bbox") or []))
                blocks.append(
                    Block(
                        type="image",
                        page=page_no,
                        content="",
                        bbox=bbox,
                        caption=caption,
                        image_path=img_lookup.get(key),
                        order=order,
                    )
                )
                img_drafts.setdefault(page_no, []).append((order, bbox, caption))
                order += 1

    # ── 页级图注收尾：不可信图注 → 同页最近可信兄弟 → 文本前缀兜底 ──
    for page_no, drafts in img_drafts.items():
        raw_blocks = raw_by_page.get(page_no, [])
        prefixed = [(bb, cap) for _, bb, cap in drafts if _prefix_caption(cap)]
        for blk_idx, bbox, caption in drafts:
            good = _prefix_caption(caption)
            if good:
                blocks[blk_idx].caption = good
                continue
            best: tuple[float, str] | None = None
            if prefixed and bbox:
                for obb, ocap in prefixed:
                    if obb:
                        d = ((_center(bbox)[0] - _center(obb)[0]) ** 2 + (_center(bbox)[1] - _center(obb)[1]) ** 2) ** 0.5
                        if best is None or d < best[0]:
                            best = (d, ocap)
            if best is not None:
                blocks[blk_idx].caption = best[1]
                continue
            blocks[blk_idx].caption = _fallback_caption({"bbox": bbox}, raw_blocks, -1)

    return DoclensDoc(doc_id=sha256[:12], sha256=sha256, title=title, doi=doi, blocks=blocks)


def _resolve_mineru_bin() -> str:
    """取 MINERU_BIN（.env 配置 doclens-mineru 环境的绝对路径）；找不到就给中文报错。"""
    configured = settings.mineru_bin.strip() or "mineru-kit"
    if Path(configured).exists() or shutil.which(configured):
        return configured
    raise RuntimeError(
        f"找不到 mineru-kit（MINERU_BIN={configured!r}）。"
        "请在 .env 里配置 doclens-mineru 环境的绝对路径，"
        "容器示例：/opt/conda/envs/doclens-mineru/bin/mineru-kit"
    )


def _run_mineru(pdf_path: Path, workdir: Path) -> None:
    """调 CLI 生成 zip（失败重试一次，runbook §3）。"""
    cmd = [_resolve_mineru_bin(), "parse", str(pdf_path), "-o", str(workdir), "-f", "zip"]
    last_err: Exception | None = None
    for attempt in (1, 2):
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=settings.mineru_timeout)
        except subprocess.TimeoutExpired as e:
            last_err = e
            continue
        if proc.returncode == 0:
            return
        last_err = RuntimeError(
            f"MinerU 解析失败（exit {proc.returncode}）：{pdf_path.name}\n"
            f"--- stdout 末尾 ---\n{proc.stdout[-800:]}\n--- stderr 末尾 ---\n{proc.stderr[-800:]}"
        )
    raise RuntimeError(
        f"MinerU 重试后仍失败：{pdf_path.name}（最后错误：{last_err}）"
    ) from last_err


def parse_pdf(pdf_path: Path, *, force: bool = False) -> DoclensDoc:
    """解析单篇 PDF → DoclensDoc；sha256 缓存命中直接返回（FR-1.1 增量）。"""
    pdf_path = Path(pdf_path)
    digest = sha256_of(pdf_path)
    out_dir = PARSED_DIR / digest[:12]
    doc_json = out_dir / "doc.json"
    if doc_json.exists() and not force:
        return DoclensDoc.load(doc_json)  # 缓存命中：不重解析

    out_dir.mkdir(parents=True, exist_ok=True)
    workdir = Path(tempfile.mkdtemp(prefix=f"mineru_{digest[:12]}_", dir=out_dir))
    try:
        _run_mineru(pdf_path, workdir)
        zips = list(workdir.glob("*.zip"))
        if len(zips) != 1:
            raise RuntimeError(f"MinerU 产物异常：期望 1 个 zip，实际 {len(zips)} 个（{workdir}）")
        with zipfile.ZipFile(zips[0]) as zf:
            zf.extractall(out_dir)  # structured_content/middle_json/markdown/images 落到 doc 目录
        structured = json.loads((out_dir / "structured_content.json").read_text(encoding="utf-8"))
        middle = json.loads((out_dir / "middle_json.json").read_text(encoding="utf-8"))
        doc = build_doc(digest, structured, middle)
        doc.save(doc_json)
        return doc
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
