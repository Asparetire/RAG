r"""M4 资产接口的路径安全层（m4-runbook K0/K8；R8 三件套 + R10 安全五条）。

路径穿越守卫（R10①）：
- PDF：/api/docs/{doc_id}/pdf 只接受 doc_id（严格 ^[0-9a-f]{12}$ 校验），
  文件路径由服务端按 M2 语料入库命名规则推导（data/pdfs/{doc_id}.pdf），
  **绝不接受用户传入路径**；realpath 后强制包含于 PDF_DIR 内。
- figure：chunk_id 严格格式校验（^[0-9a-f]{12}:\d{4}$）→ t_chunk 回表取
  image_path（库内数据，非用户输入）→ realpath 包含性校验于 data/（PARSED_DIR
  与 pdfs 的共同父目录）。
- 校验失败一律返回 None（调用方转 404，不回显细节，R10⑤）。
"""

from __future__ import annotations

import re
from pathlib import Path

from doclens.config import PARSED_DIR, PROJECT_ROOT
from doclens.pipeline import PDF_DIR, _fetch_members

DOC_ID_RE = re.compile(r"^[0-9a-f]{12}$")
CHUNK_ID_RE = re.compile(r"^[0-9a-f]{12}:\d{4}$")


def _contained(path: Path, root: Path) -> bool:
    """realpath 包含性校验：path 解析后必须位于 root 之内（含 root 直下）。"""
    try:
        rp = path.resolve()
        rr = root.resolve()
    except OSError:
        return False
    return rp == rr or rr in rp.parents


def resolve_pdf(doc_id: str) -> Path | None:
    """doc_id → PDF 文件路径；格式/存在性/包含性任一不过 → None。"""
    if not DOC_ID_RE.match(doc_id or ""):
        return None
    p = PDF_DIR / f"{doc_id}.pdf"
    if not p.is_file() or not _contained(p, PDF_DIR):
        return None
    return p


def resolve_figure(chunk_id: str) -> Path | None:
    """chunk_id → 图片文件路径；格式/回表无图/包含性任一不过 → None。"""
    if not CHUNK_ID_RE.match(chunk_id or ""):
        return None
    meta = _fetch_members([chunk_id])
    m = meta.get(chunk_id) or {}
    image_path = m.get("image_path")
    if not image_path or not isinstance(image_path, str) or "\x00" in image_path:
        return None
    p = Path(image_path)
    if not p.is_absolute():
        cand = PROJECT_ROOT / image_path
        p = cand if cand.exists() else PARSED_DIR.parent / image_path
    if not _contained(p, PARSED_DIR.parent):
        return None
    return p if p.is_file() else None
