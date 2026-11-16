#!/bin/bash
set -e
# 标定 bbox 坐标约定：用文本搜索拿真实位置，与存储 bbox 对比四种候选变换
cd /home/doclens/RAG && PYTHONPATH=/home/doclens/RAG /opt/conda/envs/doclens/bin/python - <<'PY'
import json
from doclens.index.db import connect
conn = connect()
try:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT doc_id, kind, page, bbox, content FROM t_chunk "
            "WHERE bbox IS NOT NULL AND kind IN ('text','title') "
            "AND CHAR_LENGTH(content) > 30"
        )
        rows = cur.fetchall()
finally:
    conn.close()
data = [{"doc_id": r[0], "page": r[2], "bbox": json.loads(r[3]), "content": (r[4] or "")[:200]} for r in rows]
json.dump(data, open("/tmp/_bbox_dump2.json", "w"), ensure_ascii=False)
print("dumped", len(data))
PY

PYTHONPATH=/home/doclens/RAG /opt/conda/envs/doclens-mineru/bin/python - <<'PY'
import json, re
import pypdfium2 as pdfium

rows = json.load(open("/tmp/_bbox_dump2.json"))
PDF_DIR = "/home/doclens/RAG/data/pdfs"

def norm(s):
    return re.sub(r"\s+", "", s or "")[:40]

# 每篇文档取 2 个样本
seen, samples = set(), []
random_pool = {}
for r in rows:
    random_pool.setdefault(r["doc_id"], []).append(r)
for doc_id, items in random_pool.items():
    samples.extend(items[:2])
    if len(samples) >= 40:
        break

stats = {"tl": 0, "bl": 0, "none": 0}
detail = []
for r in samples:
    needle = norm(r["content"])
    if len(needle) < 20:
        continue
    try:
        pdf = pdfium.PdfDocument(f"{PDF_DIR}/{r['doc_id']}.pdf")
        pg = pdf[r["page"] - 1]
        W, H = pg.get_size()
        rot = pg.get_rotation()
        tp = pg.get_textpage()
        # 全文取矩形，逐矩形取字找目标段
        n = tp.count_rects()
        found = None
        for i in range(n):
            l, b, rt, t = tp.get_rect(i)
            txt = tp.get_text_bounded(l, b, rt, t)
            if norm(txt) and (needle[:30] in norm(txt) or norm(txt)[:30] in needle[:40]):
                found = (l, b, rt, t)
                break
        tp.close(); pg.close(); pdf.close()
        if not found:
            stats["none"] += 1
            continue
        l, b, rt, t = found
        x0, y0, x1, y1 = r["bbox"]
        # 候选A：左上原点；候选B：左下原点
        err_tl = abs(x0 - l / W) + abs(y0 - (1 - t / H)) + abs(x1 - rt / W) + abs(y1 - (1 - b / H))
        err_bl = abs(x0 - l / W) + abs(y0 - b / H) + abs(x1 - rt / W) + abs(y1 - t / H)
        conv = "tl" if err_tl <= err_bl else "bl"
        stats[conv] += 1
        detail.append((r["doc_id"], r["page"], rot, [round(v, 3) for v in (x0, y0, x1, y1)],
                       [round(v / W, 3) for v in (l, rt)], [round(v / H, 3) for v in (b, t)],
                       round(err_tl, 3), round(err_bl, 3)))
    except Exception as e:
        stats["none"] += 1

print("约定统计:", stats, "(tl=左上原点, bl=左下原点, none=没找到文本)")
for d in detail[:12]:
    print("doc", d[0], "p", d[1], "rot", d[2])
    print("   存储bbox:", d[3])
    print("   实际x(l,r)/W:", d[4], " 实际y(b,t)/H:", d[5], " 误差tl/bl:", d[6], d[7])
PY
