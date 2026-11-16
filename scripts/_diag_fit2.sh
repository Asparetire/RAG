#!/bin/bash
set -e
cd /home/doclens/RAG && PYTHONPATH=/home/doclens/RAG /opt/conda/envs/doclens/bin/python - <<'PY'
import json
from doclens.index.db import connect
conn = connect()
try:
    with conn.cursor() as cur:
        cur.execute("SELECT kind, COUNT(*), SUM(bbox IS NOT NULL) FROM t_chunk GROUP BY kind")
        print("== 各 kind 统计 ==")
        for r in cur.fetchall():
            print("  ", r)
        cur.execute(
            "SELECT doc_id, page, bbox, content FROM t_chunk "
            "WHERE bbox IS NOT NULL AND kind='caption' AND CHAR_LENGTH(content)>10"
        )
        rows = cur.fetchall()
finally:
    conn.close()
data = []
for r in rows:
    try:
        bbox = json.loads(r[2])
        assert isinstance(bbox, list) and len(bbox) == 4
    except Exception:
        continue
    data.append({"doc_id": r[0], "page": r[1], "bbox": bbox, "content": (r[3] or "")})
json.dump(data, open("/tmp/_captions.json", "w"), ensure_ascii=False)
print("captions with bbox:", len(data))
PY

PYTHONPATH=/home/doclens/RAG /opt/conda/envs/doclens-mineru/bin/python - <<'PY'
import json, re
import pypdfium2 as pdfium

rows = json.load(open("/tmp/_captions.json"))
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
        rects = []
        for i in range(n):
            l, b, rt, t = tp.get_rect(i)
            txt = norm(tp.get_text_bounded(l, b, rt, t))
            # 矩形文字是图注的一部分（图注可能被 pdfium 切成多行矩形）
            if len(txt) >= 12 and txt in needle:
                rects.append((l, b, rt, t))
        tp.close(); pg.close(); pdf.close()
        if not rects:
            continue
        L = min(x[0] for x in rects); R = max(x[2] for x in rects)
        B = min(x[1] for x in rects); T = max(x[3] for x in rects)
        x0, y0, x1, y1 = r["bbox"]
        pairs.append({"doc": r["doc_id"], "page": r["page"], "stored": (x0, y0, x1, y1),
                      "actual_tl": (L / W, 1 - T / H, R / W, 1 - B / H)})
    except Exception:
        pass

print(f"配对成功: {len(pairs)} / {len(rows)}")

def fit(idx):
    xs = [p["stored"][idx] for p in pairs]
    ys = [p["actual_tl"][idx] for p in pairs]
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    a = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)
    b = my - a * mx
    resid = max(abs(a * x + b - y) for x, y in zip(xs, ys))
    return a, b, resid

for i, axis in enumerate("x0 y0 x1 y1".split()):
    a, b, r = fit(i)
    print(f"   {axis}: actual = {a:.3f} * stored + {b:.3f}   最大残差 {r:.4f}")

print("\n样例（前8条）:")
for p in pairs[:8]:
    print(" ", p["doc"], "p", p["page"], " stored", [round(v, 3) for v in p["stored"]], " actual_tl", [round(v, 3) for v in p["actual_tl"]])
PY
