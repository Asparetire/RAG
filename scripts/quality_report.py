"""解析质检报告（m1-runbook 步骤 1.4，PRD FR-1.4，P1）。

做什么：读解析产物 data/parsed/<doc_id>/doc.json，汇总每篇的
块数/图数/图注绑定率/空图检测（image_path 缺失或指向文件不存在），
生成一页 Markdown 报告 → reports/parse_quality_m1.md，供人工审阅。

用法（doclens 环境）：
    python scripts/quality_report.py            # 全量扫描已解析文档
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

# 支持 `python scripts/quality_report.py` 直接执行
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from doclens.config import DATA_DIR, PARSED_DIR, REPORTS_DIR
from doclens.parse.schema import DoclensDoc


def inspect_doc(doc: DoclensDoc, doc_root: Path) -> dict:
    """单篇质检：块统计 + 图注绑定 + 空图检测。"""
    images = [b for b in doc.blocks if b.type == "image"]
    bound = [b for b in images if b.caption]
    empty_imgs = []
    for b in images:
        if not b.image_path:
            empty_imgs.append(f"p{b.page}: 无 image_path")
        elif not (doc_root / b.image_path).exists():
            empty_imgs.append(f"p{b.page}: 文件缺失 {b.image_path}")
    return {
        "doc_id": doc.doc_id,
        "title": (doc.title or "")[:60],
        "doi": doc.doi,
        "n_blocks": len(doc.blocks),
        "n_text": sum(1 for b in doc.blocks if b.type == "text"),
        "n_title": sum(1 for b in doc.blocks if b.type == "title"),
        "n_table": sum(1 for b in doc.blocks if b.type == "table"),
        "n_images": len(images),
        "n_bound": len(bound),
        "binding_rate": len(bound) / len(images) if images else None,
        "empty_images": empty_imgs,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="DocLens 解析质检报告（FR-1.4）")
    ap.add_argument("--parsed", type=Path, default=PARSED_DIR)
    ap.add_argument("--manifest", type=Path, default=DATA_DIR / "corpus_manifest.json")
    ap.add_argument("--out", type=Path, default=REPORTS_DIR / "parse_quality_m1.md")
    args = ap.parse_args(argv)

    doc_dirs = sorted(d for d in args.parsed.iterdir() if d.is_dir() and (d / "doc.json").exists()) if args.parsed.exists() else []
    if not doc_dirs:
        print(f"[错误] {args.parsed} 下没有解析产物（先跑 scripts/parse_corpus.py）")
        return 1

    manifest = {}
    if args.manifest.exists():
        manifest = {p["doc_id"]: p for p in json.loads(args.manifest.read_text(encoding="utf-8")).get("papers", [])}

    rows: list[dict] = []
    for d in doc_dirs:
        doc = DoclensDoc.load(d / "doc.json")
        rows.append(inspect_doc(doc, d))
    rows.sort(key=lambda r: r["doc_id"])

    total_imgs = sum(r["n_images"] for r in rows)
    total_bound = sum(r["n_bound"] for r in rows)
    overall = total_bound / total_imgs if total_imgs else None

    lines = [
        "# M1 解析质检报告（FR-1.4）",
        "",
        f"> 生成时间：{time.strftime('%Y-%m-%d %H:%M:%S')} ｜ 文档数：{len(rows)} ｜ "
        f"图注绑定率（全量）：{overall:.1%}（{total_bound}/{total_imgs}）——验收线 ≥90%",
        "",
        "| doc_id | 标题 | 块数 | 文本 | 标题 | 表格 | 图片 | 绑定 | 绑定率 | 空图 | 原文件名 |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        name = manifest.get(r["doc_id"], {}).get("original_name", "")
        lines.append(
            f"| {r['doc_id']} | {r['title']} | {r['n_blocks']} | {r['n_text']} | {r['n_title']} "
            f"| {r['n_table']} | {r['n_images']} | {r['n_bound']} "
            f"| {f'{r["binding_rate"]:.0%}' if r['binding_rate'] is not None else '—'} "
            f"| {'; '.join(r['empty_images']) or '—'} | {name[:48]} |"
        )
    problems = [r for r in rows if r["empty_images"] or (r["binding_rate"] is not None and r["binding_rate"] < 0.9)]
    if problems:
        lines += ["", "## 需人工复核", ""]
        for r in problems:
            lines.append(f"- `{r['doc_id']}` {r['title']}：{'; '.join(r['empty_images']) or '绑定率偏低'}")
    else:
        lines += ["", "## 结论", "", "- 无空图、无低绑定文档，全部通过。"]
    args.out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[完成] {len(rows)} 篇质检完毕，全量图注绑定率 "
          f"{f'{overall:.1%}' if overall is not None else '—'} → {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
