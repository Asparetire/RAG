#!/bin/bash
set -e
cd /home/doclens/RAG && PYTHONPATH=/home/doclens/RAG /opt/conda/envs/doclens/bin/python - <<'PY'
import json
from doclens.index.db import connect
conn = connect()
try:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT doc_id, kind, page, bbox, LEFT(content,60), caption FROM t_chunk "
            "WHERE bbox IS NOT NULL AND page<=2"
        )
        rows = cur.fetchall()
finally:
    conn.close()
out = []
for r in rows:
    try:
        bbox = json.loads(r[3])
        assert isinstance(bbox, list) and len(bbox) == 4
    except Exception:
        continue
    out.append({"doc_id": r[0], "kind": r[1], "page": r[2], "bbox": bbox,
                "content": (r[4] or ""), "caption": r[5]})
json.dump(out, open("/tmp/_page12.json", "w"), ensure_ascii=False)
print("blocks:", len(out))
PY

/opt/conda/envs/doclens-mineru/bin/python - <<'PY'
import json
import pypdfium2 as pdfium
import PIL

rows = json.load(open("/tmp/_page12.json"))
PDF_DIR = "/home/doclens/RAG/data/pdfs"

KIND_COLOR = {"text": (220, 30, 30), "table": (230, 140, 0), "caption": (160, 60, 200), "image": (30, 150, 60)}

by_doc_page = {}
for r in rows:
    by_doc_page.setdefault((r["doc_id"], r["page"]), []).append(r)

n = 0
for (doc_id, page), items in sorted(by_doc_page.items()):
    if n >= 6:
        break
    try:
        pdf = pdfium.PdfDocument(f"{PDF_DIR}/{doc_id}.pdf")
        pg = pdf[page - 1]
        W, H = pg.get_size()
        bmp = pg.render(scale=1.6)
        img = bmp.to_pil().convert("RGB")
        from PIL import ImageDraw
        d = ImageDraw.Draw(img)
        for it in items:
            x0, y0, x1, y1 = it["bbox"]
            color = KIND_COLOR.get(it["kind"], (0, 0, 255))
            d.rectangle([x0 * W, y0 * H, x1 * W, y1 * H], outline=color, width=3)
        out = f"/tmp/_overlay_{doc_id}_p{page}.png"
        img.save(out)
        print("saved:", out, "boxes:", len(items))
        pdf.close()
        n += 1
    except Exception as e:
        print("ERR", doc_id, page, e)
PY
