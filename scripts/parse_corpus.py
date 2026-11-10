"""批量解析清单里的全部论文（m1-runbook 1.3 验收入口）。

做什么：读 data/corpus_manifest.json → 逐篇 parse_pdf（sha256 缓存增量）→
逐篇计时 → 回填清单的 title/doi（论文级去重的依据）→
DOI/归一化标题判重：后到者标 status=duplicate_of:<doc_id>。
清单采用合并式更新，失败论文标 failed 并继续跑其余（runbook §7）。

用法（doclens 环境，容器内执行）：
    python scripts/parse_corpus.py            # 全量（缓存命中自动跳过）
    python scripts/parse_corpus.py --force    # 忽略缓存重解析
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

# 支持 `python scripts/parse_corpus.py` 直接执行：把仓库根加进模块搜索路径
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from doclens.config import DATA_DIR
from doclens.parse.mineru_parser import parse_pdf


def _norm_title(title: str | None) -> str:
    """归一化标题：小写、只留字母数字——论文级去重用。"""
    return re.sub(r"[^a-z0-9]+", "", (title or "").lower())


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="DocLens 批量解析：清单逐篇 → 计时 → 回填 → 论文级去重")
    ap.add_argument("--manifest", type=Path, default=DATA_DIR / "corpus_manifest.json")
    ap.add_argument("--pdfs", type=Path, default=DATA_DIR / "pdfs")
    ap.add_argument("--force", action="store_true", help="忽略 sha256 缓存强制重解析")
    args = ap.parse_args(argv)

    manifest = json.loads(args.manifest.read_text(encoding="utf-8")) if args.manifest.exists() else None
    if not manifest:
        print(f"[错误] 清单不存在：{args.manifest}（先跑 scripts/corpus_intake.py）")
        return 1

    papers = manifest.get("papers", [])
    print(f"[开始] 清单共 {len(papers)} 篇" + ("（--force 强制重解析）" if args.force else ""))
    total_seconds = 0.0
    failed = 0

    for p in papers:
        doc_id, pdf_path = p["doc_id"], args.pdfs / f"{p['doc_id']}.pdf"
        if not pdf_path.exists():
            print(f"[跳过] {doc_id}: PDF 不存在（{pdf_path.name}）")
            p["status"] = "missing_pdf"
            failed += 1
            continue
        t0 = time.perf_counter()
        try:
            doc = parse_pdf(pdf_path, force=args.force)
        except Exception as e:  # 单篇失败不拖垮批次（runbook §7）
            p["status"] = f"failed: {e}"[:300]
            failed += 1
            print(f"[失败] {doc_id} {p.get('original_name', '')[:40]}: {e}")
            continue
        seconds = time.perf_counter() - t0
        total_seconds += seconds
        n_img = sum(1 for b in doc.blocks if b.type == "image")
        n_cap = sum(1 for b in doc.blocks if b.type == "image" and b.caption)
        p.update(
            {
                "title": doc.title,
                "doi": doc.doi,
                "parsed_seconds": round(seconds, 1),
                "n_blocks": len(doc.blocks),
                "n_images": n_img,
                "n_captions_bound": n_cap,
            }
        )
        print(
            f"[完成] {doc_id} {seconds:6.1f}s  块={len(doc.blocks):4d} 图={n_img:3d} 绑定图注={n_cap:3d}"
            f"  {p.get('original_name', '')[:40]}"
        )

    # ── 论文级去重（runbook §3 第二层）：DOI 优先，归一化标题兜底；后到者标 duplicate_of ──
    seen: dict[str, str] = {}
    for p in papers:
        key = (p.get("doi") or "").lower() or f"title:{_norm_title(p.get('title'))}"
        if not key or key == "title:":
            continue
        if key in seen:
            p["status"] = f"duplicate_of:{seen[key]}"
            print(f"[判重] {p['doc_id']} 与 {seen[key]} 同文（{ 'DOI' if not key.startswith('title:') else '标题' }）")
        else:
            seen[key] = p["doc_id"]
            if str(p.get("status", "")).startswith("duplicate_of"):
                p["status"] = "canonical"  # 前次判重、本次对方已不在清单 → 恢复正主

    manifest["parsed_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    args.manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    n_ok = sum(1 for p in papers if p.get("status") == "canonical" and "parsed_seconds" in p)
    print(f"[汇总] 成功 {n_ok}/{len(papers)}，失败 {failed}，总耗时 {total_seconds:.1f}s；清单已回填 → {args.manifest}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
