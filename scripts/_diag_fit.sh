#!/bin/bash
set -e
cd /home/doclens/RAG && PYTHONPATH=/home/doclens/RAG /opt/conda/envs/doclens/bin/python - <<'PY'
import json
from doclens.index.db import connect
conn = connect()
try:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT doc_id, page, bbox, content FROM t_chunk "
            "WHERE bbox IS NOT NULL AND kind='title' AND page=1 AND CHAR_LENGTH(content)>10"
        )
        rows = cur.fetchall()
finally:
    conn.close()
data = [{"doc_id": r[0], "page": r[2], "bbox": json.loads(r[3]), "content": (r[4] or "")} for r in rows]
json.dump(data, open("/tmp/_titles.json", "w"), ensure_ascii=False)
print("titles:", len(data))
PY

PYTHONPATH=/home/doclens/RAG /opt/conda/envs/doclens-mineru/bin/python - <<'PY'
import json, re
import pypdfium2 as pdfium

rows = json.load(open("/tmp/_titles.json"))
PDF_DIR = "/home/doclens/RAG/data/pdfs"

def norm(s):
    return re.sub(r"\s+", "", s or "")

pairs = []
for r in rows:
    needle = norm(r["content"])
    if len(needle) < 15:
        continue
    try:
        pdf = pdfium.PdfDocument(f"{PDF_DIR}/{r['doc_id']}.pdf")
        pg = pdf[r["page"] - 1]
        W, H = pg.get_size()
        tp = pg.get_textpage()
        n = tp.count_rects()
        # 收集所有文字属于该标题的矩形，合并成块的包围盒
        rects = []
        for i in range(n):
            l, b, rt, t = tp.get_rect(i)
            txt = norm(tp.get_text_bounded(l, b, rt, t))
            if txt and txt in needle:
                rects.append((l, b, rt, t))
        tp.close(); pg.close(); pdf.close()
        if not rects:
            continue
        L = min(x[0] for x in rects); R = max(x[2] for x in rects)
        B = min(x[1] for x in rects); T = max(x[3] for x in rects)
        x0, y0, x1, y1 = r["bbox"]
        pairs.append({
            "doc": r["doc_id"],
            "stored": (x0, y0, x1, y1),
            "actual_tl": (L / W, 1 - T / H, R / W, 1 - B / H),   # 左上原点假设
            "actual_bl": (L / W, B / H, R / W, T / H),           # 左下原点假设
        })
    except Exception:
        pass

print(f"配对成功: {len(pairs)}")
# 逐轴仿射拟合 actual = a*stored + b
import statistics

def fit(idx, key):
    xs = [p["stored"][idx] for p in pairs]
    ys = [p[key][idx] for p in pairs]
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    a = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)
    b = my - a * mx
    resid = max(abs(a * x + b - y) for x, y in zip(xs, ys))
    return a, b, resid

for key in ("actual_tl", "actual_bl"):
    print(f"== {key} ==")
    for i, axis in enumerate("x0 y0 x1 y1".split()):
        a, b, r = fit(i, key)
        print(f"   {axis}: actual = {a:.3f} * stored + {b:.3f}   最大残差 {r:.4f}")

print("\n样例（前6条）:")
for p in pairs[:6]:
    print(" ", p["doc"], "stored", [round(v, 3) for v in p["stored"]])
    print("      tl ", [round(v, 3) for v in p["actual_tl"]], " bl ", [round(v, 3) for v in p["actual_bl"]])
PY
