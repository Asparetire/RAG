"""语料入库（m1-runbook 步骤 1.0，2026-11-10 改型：自选领域论文人工收料）。

流程：inbox 逐个 PDF → 校验（%PDF 头 / 体积）→ sha256 指纹（**文件级去重**：
内容相同就算改名也命中）→ 复制为 data/pdfs/<doc_id>.pdf → 产出
data/corpus_manifest.json 清单（doc_id / 原文件名 / sha256 / 体积；
title / doi 留空，解析后由 mineru_parser 回填——**论文级去重**见 runbook §3）。

用法（doclens 环境）：
    python scripts/corpus_intake.py                # 默认 inbox=data/pdfs_inbox
    python scripts/corpus_intake.py --inbox <dir>  # 指定收料目录
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

# 支持 `python scripts/corpus_intake.py` 直接执行：把仓库根加进模块搜索路径
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from doclens.config import DATA_DIR

MIN_PDF_BYTES = 10 * 1024  # 正常论文 PDF 远大于此；兜底空文件/损坏文件
PDF_MAGIC = b"%PDF-"


def sha256_of(path: Path) -> str:
    """流式计算文件 sha256（大文件不占整块内存）。"""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def validate_pdf(path: Path) -> str | None:
    """返回错误说明；None = 通过校验。"""
    size = path.stat().st_size
    if size < MIN_PDF_BYTES:
        return f"文件过小（{size} 字节），疑似损坏"
    with path.open("rb") as f:
        if f.read(5) != PDF_MAGIC:
            return "缺少 %PDF- 文件头，不是合法 PDF"
    return None


def intake(inbox: Path, out_dir: Path, manifest_path: Path) -> list[dict]:
    """执行入库，返回**本次新增**的 papers 列表。

    去重规则（文件级）：目标 data/pdfs/<doc_id>.pdf 已存在（sha256 前 12 位相同）
    即判重跳过——同时覆盖"运行内改名重复"与"跨运行重复"两种情况。
    清单采用合并语义：重跑不会覆盖既有条目。
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    existing: dict[str, dict] = {}  # doc_id -> 清单条目（含历史）
    if manifest_path.exists():
        try:
            old = json.loads(manifest_path.read_text(encoding="utf-8"))
            existing = {p["doc_id"]: p for p in old.get("papers", [])}
        except (json.JSONDecodeError, KeyError):
            existing = {}  # 清单损坏则重建

    new_papers: list[dict] = []
    skipped: list[dict] = []

    pdfs: list[Path] = []
    if inbox.exists():
        pdfs = sorted(p for p in inbox.iterdir() if p.is_file() and p.suffix.lower() == ".pdf")

    for pdf in pdfs:
        err = validate_pdf(pdf)
        if err:
            skipped.append({"name": pdf.name, "reason": err})
            continue
        digest = sha256_of(pdf)
        doc_id = digest[:12]
        dest = out_dir / f"{doc_id}.pdf"
        if dest.exists():
            skipped.append({"name": pdf.name, "reason": f"与已入库论文 {doc_id} 内容相同（sha256 重复）"})
            continue
        shutil.copy2(pdf, dest)
        entry = {
            "doc_id": doc_id,
            "original_name": pdf.name,
            "sha256": digest,
            "size_bytes": pdf.stat().st_size,
            "title": None,  # 解析后回填（论文级去重依据之一）
            "doi": None,
            "status": "canonical",
        }
        existing[doc_id] = entry
        new_papers.append(entry)

    manifest = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "count": len(existing),
        "papers": list(existing.values()),
        "skipped": skipped,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    for s in skipped:
        print(f"[跳过] {s['name']}: {s['reason']}")
    print(f"[完成] 本次新增 {len(new_papers)} 篇，清单累计 {len(existing)} 篇 → {out_dir}；清单 → {manifest_path}")
    return new_papers


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="DocLens 语料入库：校验 + sha256 文件级去重 + 清单")
    ap.add_argument("--inbox", type=Path, default=DATA_DIR / "pdfs_inbox")
    ap.add_argument("--out", type=Path, default=DATA_DIR / "pdfs")
    ap.add_argument("--manifest", type=Path, default=DATA_DIR / "corpus_manifest.json")
    args = ap.parse_args(argv)
    papers = intake(args.inbox, args.out, args.manifest)
    return 0 if papers else 1


if __name__ == "__main__":
    sys.exit(main())
