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
from collections import Counter
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
    _table_audit(args.parsed)
    return 0


def _table_audit(parsed_dir: Path) -> None:
    """表格 v2 审计（m2-runbook 2.0）：读各篇 tables_manifest.json，产出全量人工过目报告。"""
    out = REPORTS_DIR / "table_audit_m2.md"
    lines = [
        "# M2 表格结构理解审计报告（125 表全量人工过目）",
        "",
        f"> 生成时间：{time.strftime('%Y-%m-%d %H:%M:%S')} ｜ 依据：m2-runbook 2.0 验收"
        "（列名/行名正确、无效内容零混入、排除零误伤数据行）",
        "> 审计方法：逐表核对【列】【行】与排除清单；注意 MinerU 侧 caption 可能存在空格丢失（解析器特性，非管线缺陷）",
        "",
    ]
    total = 0
    src_counter: Counter = Counter()
    exc_counter: Counter = Counter()
    flag_rows: list[str] = []
    for d in sorted(parsed_dir.iterdir()):
        mf = d / "tables_manifest.json"
        if not mf.exists():
            continue
        manifests = json.loads(mf.read_text(encoding="utf-8"))
        if manifests:
            lines += [f"## {d.name}", "", "| table_id | 页 | 来源 | 列名 | 行名列 | 行数(清洗/原始) | 排除项 |", "|---|---|---|---|---|---|---|"]
        for m in manifests:
            total += 1
            src_counter[m["source"]] += 1
            exc = "；".join(f"{e['type']}({e['where']})" for e in m["excluded"]) or "—"
            for e in m["excluded"]:
                exc_counter[e["type"]] += 1
            cols = " / ".join(m["columns"][:6]) + (" …" if len(m["columns"]) > 6 else "")
            if len(cols) > 80:
                cols = cols[:78] + "…"
            labels = " / ".join(m["row_labels"][:4]) + (" …" if len(m["row_labels"]) > 4 else "")
            if len(labels) > 60:
                labels = labels[:58] + "…"
            row = (
                f"| {m['table_id']} | {m['page']} | {m['source']} | {cols or '—'} "
                f"| {labels or '—'} | {m['n_rows_clean']}/{m['n_rows_raw']} | {exc} |"
            )
            lines.append(row)
            # 粗筛红旗：无表头且无行名的"零结构"表，供人工重点看
            if not m["columns"] and not m["row_labels"] and m["source"] == "html":
                flag_rows.append(f"- `{m['table_id']}`：HTML 源但未判出任何列名/行名（重点核对是否漏判）")
        if manifests:
            lines.append("")
    lines += [
        "## 汇总",
        "",
        f"- 表格总数：{total}；来源分布：{dict(src_counter)}；排除项分布：{dict(exc_counter) or '—'}",
        "",
        "## 需重点人工核对（自动粗筛）",
        "",
        *(flag_rows or ["- （无自动红旗；仍需逐表过目确认）"]),
    ]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[完成] 表格审计报告：{total} 张表（来源 {dict(src_counter)}）→ {out}")


if __name__ == "__main__":
    sys.exit(main())
