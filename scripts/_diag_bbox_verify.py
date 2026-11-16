"""临时诊断4：全库 bbox 定位准确性验证（用完即删）。

方法：t_chunk 里带 bbox 的块抽样 → pdfium 在 bbox 矩形（0-1 归一化、左上原点 →
PDF 点坐标、左下原点换算）内提取文字 → 与块内容前缀比对相似度。
"""
import random
import re
from difflib import SequenceMatcher

import pypdfium2 as pdfium

from doclens.index.db import connect

random.seed(42)
PDF_DIR = "/home/doclens/RAG/data/pdfs"


def norm(s: str) -> str:
    return re.sub(r"\s+", "", s or "")


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

by_doc = {}
for doc_id, kind, page, bbox, content in rows:
    by_doc.setdefault(doc_id, []).append((page, bbox, content[:200]))

print(f"docs={len(by_doc)} chunks_with_bbox={len(rows)}")
print(f"{'doc_id':<14}{'样本':>6}{'中位相似':>10}{'>0.5占比':>10}  备注")

import statistics

for doc_id, items in sorted(by_doc.items()):
    sample = random.sample(items, min(30, len(items)))
    scores = []
    for page, bbox, content in sample:
        try:
            pdf = pdfium.PdfDocument(f"{PDF_DIR}/{doc_id}.pdf")
            if page is None or page < 1 or page > len(pdf):
                continue
            pg = pdf[page - 1]
            W, H = pg.get_size()
            x0, y0, x1, y1 = [float(v) for v in bbox]
            rect = (x0 * W, (1 - y1) * H, x1 * W, (1 - y0) * H)
            tp = pg.get_textpage()
            rect_text = tp.get_text_bounded(*rect)
            tp.close()
            pg.close()
            pdf.close()
            a, b = norm(content)[:150], norm(rect_text)[:150]
            if not a or not b:
                scores.append(0.0)
                continue
            scores.append(SequenceMatcher(None, a, b).ratio())
        except Exception as e:
            scores.append(None)
    valid = [s for s in scores if s is not None]
    if not valid:
        print(f"{doc_id:<14}{len(sample):>6}  全部异常")
        continue
    med = statistics.median(valid)
    good = sum(1 for s in valid if s > 0.5) / len(valid)
    mark = "" if good > 0.7 else "  <<<< 定位疑似错位"
    print(f"{doc_id:<14}{len(valid):>6}{med:>10.2f}{good:>10.0%}{mark}")
