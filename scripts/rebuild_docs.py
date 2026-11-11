"""从缓存 raw JSON 重建 doc.json + tables_manifest.json（m2-runbook 2.0；表格 v2）。

不重跑 MinerU：structured_content.json / middle_json.json 已在 data/parsed/<doc_id>/ 落盘，
直接走 build_doc（内含表格结构理解管线 v2）重新生成 doc.json 与表格 manifest。

用法（容器内 doclens 环境）：
    python scripts/rebuild_docs.py            # 重建全部 11 篇
    python scripts/rebuild_docs.py <doc_id>   # 只重建指定篇（调试用）

输出摘要：每篇表格数 / 来源分布（html|markdown）/ 排除项计数；doc.json 中原 sha256/title/doi 保持不变。
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

# 支持 `python scripts/rebuild_docs.py` 直接执行（仓库根路径自举，与 quality_report 同法）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from doclens.config import PARSED_DIR
from doclens.parse.mineru_parser import build_doc


def rebuild_one(doc_dir: Path) -> dict:
    doc_json = doc_dir / "doc.json"
    if not doc_json.exists():
        raise FileNotFoundError(f"缺 doc.json：{doc_dir}")
    old = json.loads(doc_json.read_text(encoding="utf-8"))
    sha256 = old["sha256"]  # 重建保持 doc_id/sha256 不变（doc_id = sha256 前 12 位）
    structured = json.loads((doc_dir / "structured_content.json").read_text(encoding="utf-8"))
    middle = json.loads((doc_dir / "middle_json.json").read_text(encoding="utf-8"))

    manifests: list = []
    doc = build_doc(sha256, structured, middle, collect=manifests)
    doc.save(doc_json)
    (doc_dir / "tables_manifest.json").write_text(
        json.dumps(manifests, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    src = Counter(m["source"] for m in manifests)
    exc = Counter(e["type"] for m in manifests for e in m["excluded"])
    return {"doc_id": doc_dir.name, "blocks": len(doc.blocks), "tables": len(manifests),
            "src": dict(src), "excluded": dict(exc)}


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    dirs = [PARSED_DIR / a for a in args] if args else sorted(
        p for p in PARSED_DIR.iterdir() if p.is_dir() and (p / "structured_content.json").exists()
    )
    if not dirs:
        raise SystemExit("没有可重建的文档目录（data/parsed/<doc_id>/ 缺 structured_content.json）")
    total_tables = 0
    total_src: Counter = Counter()
    total_exc: Counter = Counter()
    for d in dirs:
        r = rebuild_one(d)
        total_tables += r["tables"]
        total_src.update(r["src"])
        total_exc.update(r["excluded"])
        print(f"{r['doc_id']}  blocks={r['blocks']} tables={r['tables']} src={r['src']} excluded={r['excluded']}")
    print(f"=== 共 {len(dirs)} 篇，{total_tables} 张表；来源 {dict(total_src)}；排除项 {dict(total_exc)} ===")


if __name__ == "__main__":
    main()
