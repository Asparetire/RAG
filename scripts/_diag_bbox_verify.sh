#!/bin/bash
set -e
# 第一步：doclens 环境导出 bbox 块清单
cd /home/doclens/RAG && PYTHONPATH=/home/doclens/RAG /opt/conda/envs/doclens/bin/python - <<'PY'
import json
from doclens.index.db import connect
conn = connect()
try:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT doc_id, kind, page, bbox, content FROM t_chunk "
            "WHERE bbox IS NOT NULL AND kind IN ('text','title','table','caption') "
            "AND CHAR_LENGTH(content) > 10"
        )
        rows = cur.fetchall()
finally:
    conn.close()
data = [{"doc_id": r[0], "kind": r[1], "page": r[2], "bbox": json.loads(r[3]), "content": (r[4] or "")[:200]} for r in rows]
json.dump(data, open("/tmp/_bbox_dump.json", "w"), ensure_ascii=False)
print("dumped", len(data), "chunks")
PY
# 第二步：mineru 环境（有 pypdfium2）做矩形取字比对
PYTHONPATH=/home/doclens/RAG /opt/conda/envs/doclens-mineru/bin/python - <<'PY'
import json, random, re, statistics
from difflib import SequenceMatcher
import pypdfium2 as pdfium

random.seed(42)
PDF_DIR = "/home/doclens/RAG/data/pdfs"
rows = json.load(open("/tmp/_bbox_dump.json"))
by_doc = {}
for r in rows:
    by_doc.setdefault(r["doc_id"], []).append(r)
print(f"docs={len(by_doc)} chunks_with_bbox={len(rows)}")

def norm(s):
    return re.sub(r"\s+", "", s or "")

print(f"{'doc_id':<14}{'样本':>6}{'中位相似':>10}{'>0.5占比':>10}  备注")
for doc_id, items in sorted(by_doc.items()):
    sample = random.sample(items, min(30, len(items)))
    scores = []
    for r in sample:
        try:
            pdf = pdfium.PdfDocument(f"{PDF_DIR}/{doc_id}.pdf")
            page = r["page"]
            if page is None or page < 1 or page > len(pdf):
                pdf.close(); scores.append(None); continue
            pg = pdf[page - 1]
            W, H = pg.get_size()
            x0, y0, x1, y1 = [float(v) for v in r["bbox"]]
            tp = pg.get_textpage()
            rect_text = tp.get_text_bounded(x0 * W, (1 - y1) * H, x1 * W, (1 - y0) * H)
            tp.close(); pg.close(); pdf.close()
            a, b = norm(r["content"])[:150], norm(rect_text)[:150]
            scores.append(SequenceMatcher(None, a, b).ratio() if a and b else 0.0)
        except Exception:
            scores.append(None)
    valid = [s for s in scores if s is not None]
    if not valid:
        print(f"{doc_id:<14}{len(sample):>6}  全部异常")
        continue
    med = statistics.median(valid)
    good = sum(1 for s in valid if s > 0.5) / len(valid)
    mark = "" if good > 0.7 else "  <<<< 定位疑似错位"
    print(f"{doc_id:<14}{len(valid):>6}{med:>10.2f}{good:>10.0%}{mark}")
PY
