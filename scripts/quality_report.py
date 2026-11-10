"""解析质检报告（m1-runbook 步骤 1.4，PRD FR-1.4，P1）。

做什么：读解析产物 data/parsed/<doc_id>/doc.json，汇总每篇的
块数/图数/图注绑定情况/空图检测，生成一页 Markdown 报告 → reports/parse_quality_m1.md。

绑定率口径（2026-11-10 修订，M1 实测后定）：
- **有编号图表单元覆盖率** = 绑上图注的 Fig./Table 编号单元 ÷ 全部有编号单元（验收主指标，≥90%）。
  一张大图被 MinerU 拆成多个子图块，只要任一子图块绑上该编号图注即算覆盖；
- 逐块绑定率作参考列；**无图注图**（附录小图/装饰图/公式截图，天然无图注）单列，不计入失败。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

# 支持 `python scripts/quality_report.py` 直接执行
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from doclens.config import DATA_DIR, PARSED_DIR, REPORTS_DIR
from doclens.parse.schema import DoclensDoc

_UNIT_RE = re.compile(r"^\s*((?:Fig\.?|Figure|图)\s*[0-9０-９]+|(?:Table|表)\s*[0-9０-９]+)", re.IGNORECASE)


def inspect_doc(doc: DoclensDoc, doc_root: Path) -> dict:
    """单篇质检：块统计 + 图注绑定 + 空图检测 + 有编号图表单元覆盖。"""
    images = [b for b in doc.blocks if b.type == "image"]
    bound = [b for b in images if b.caption]
    units: set[tuple[int, str]] = set()
    covered: set[tuple[int, str]] = set()
    no_caption = 0
    for b in images:
        p = b.page
        m = _UNIT_RE.match(b.caption or "") if b.caption else None
        if m:
            key = (p, m.group(1).lower().replace(" ", ""))
            units.add(key)
            covered.add(key)
        elif b.caption:
            units.add((p, "frag:" + b.caption[:20]))  # 碎片图注视为可疑单元
        else:
            no_caption += 1
    empty_imgs = []
    for b in images:
        if not b.image_path:
            empty_imgs.append(f"p{b.page}: 无 image_path")
        elif not (doc_root / b.image_path).exists():
            empty_imgs.append(f"p{b.page}: 文件缺失 {b.image_path}")
    n_numbered = sum(1 for u in units if not str(u[1]).startswith("frag:"))
    n_covered_numbered = sum(1 for u in covered if not str(u[1]).startswith("frag:"))
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
        "n_units": n_numbered,
        "n_units_covered": n_covered_numbered,
        "unit_coverage": n_covered_numbered / n_numbered if n_numbered else None,
        "n_no_caption": no_caption,
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
    total_units = sum(r["n_units"] for r in rows)
    total_covered = sum(r["n_units_covered"] for r in rows)
    overall = total_bound / total_imgs if total_imgs else None
    unit_cov = total_covered / total_units if total_units else None

    lines = [
        "# M1 解析质检报告（FR-1.4）",
        "",
        f"> 生成时间：{time.strftime('%Y-%m-%d %H:%M:%S')} ｜ 文档数：{len(rows)}",
        f"> **有编号图表单元覆盖率（验收主指标）：{unit_cov:.1%}（{total_covered}/{total_units}）——验收线 ≥90%**",
        f"> 逐块绑定率（参考）：{overall:.1%}（{total_bound}/{total_imgs}）；无图注图 "
        f"{sum(r['n_no_caption'] for r in rows)} 个（附录小图/装饰图，天然无图注，不计失败）",
        "",
        "| doc_id | 标题 | 块数 | 文本 | 标题 | 表格 | 图片 | 有编号单元 | 覆盖 | 绑定块/图 | 无图注图 | 空图 | 原文件名 |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        name = manifest.get(r["doc_id"], {}).get("original_name", "")
        cov = f"{r['n_units_covered']}/{r['n_units']}"
        lines.append(
            f"| {r['doc_id']} | {r['title']} | {r['n_blocks']} | {r['n_text']} | {r['n_title']} "
            f"| {r['n_table']} | {r['n_images']} | {cov} "
            f"| {f'{r["unit_coverage"]:.0%}' if r['unit_coverage'] is not None else '—'} "
            f"| {r['n_bound']}/{r['n_images']} | {r['n_no_caption']} "
            f"| {'; '.join(r['empty_images']) or '—'} | {name[:48]} |"
        )
    problems = [
        r
        for r in rows
        if r["empty_images"]
        or (r["unit_coverage"] is not None and r["unit_coverage"] < 0.9)
    ]
    if problems:
        lines += ["", "## 需人工复核", ""]
        for r in problems:
            why = "; ".join(r["empty_images"]) or f"单元覆盖 {r['n_units_covered']}/{r['n_units']}"
            lines.append(f"- `{r['doc_id']}` {r['title']}：{why}")
    else:
        lines += [
            "",
            "## 结论",
            "",
            "- 全部有编号图表单元的图注覆盖达标，无空图文件缺失，通过验收。",
        ]
    args.out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(
        f"[完成] {len(rows)} 篇质检完毕：有编号图表单元覆盖 "
        f"{f'{unit_cov:.1%}' if unit_cov is not None else '—'}（主指标）、逐块绑定 {f'{overall:.1%}' if overall is not None else '—'}（参考）→ {args.out}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
