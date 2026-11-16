#!/bin/bash
set -e
DOC=13c8e91b3467
cd /home/doclens/RAG
echo '===== t_chunk 中该文档第1页的块 ====='
PYTHONPATH=/home/doclens/RAG /opt/conda/envs/doclens/bin/python - <<'PY'
import json
from doclens.index.db import connect
conn = connect()
try:
    with conn.cursor() as cur:
        cur.execute("SELECT kind, bbox, LEFT(content,50) FROM t_chunk WHERE doc_id='13c8e91b3467' AND page=1 AND bbox IS NOT NULL")
        for k, b, c in cur.fetchall():
            print(f"  [{k}] {b} | {c[:45]!r}")
finally:
    conn.close()
PY
echo '===== structured_content.json 第1页原始块 ====='
/opt/conda/envs/doclens/bin/python - <<'PY'
import json
d = json.load(open('data/parsed/13c8e91b3467/structured_content.json'))
pg = d['pages'][0]
for i, b in enumerate(pg['blocks']):
    c = b.get('content')
    if isinstance(c, list):
        c = ''.join(s.get('content','') for s in c if isinstance(s, dict))
    print(f"  [{i}] {b.get('type'):<16} bbox={b.get('bbox')} | {str(c)[:45]!r}")
PY
echo '===== 生成对照叠加图 ====='
PYTHONPATH=/home/doclens/RAG /opt/conda/envs/doclens/bin/python - <<'PY'
import json
from doclens.index.db import connect
conn = connect()
try:
    with conn.cursor() as cur:
        cur.execute("SELECT kind, bbox FROM t_chunk WHERE doc_id='13c8e91b3467' AND page=1 AND bbox IS NOT NULL")
        chunk_boxes = [(k, json.loads(b)) for k, b in cur.fetchall()]
finally:
    conn.close()
raw = json.load(open('data/parsed/13c8e91b3467/structured_content.json'))
raw_boxes = [(b.get('type'), b.get('bbox')) for b in raw['pages'][0]['blocks'] if b.get('bbox')]
json.dump({"chunk": chunk_boxes, "raw": raw_boxes}, open('/tmp/_two_boxes.json', 'w'), ensure_ascii=False)
print("chunk boxes:", len(chunk_boxes), " raw boxes:", len(raw_boxes))
PY
/opt/conda/envs/doclens-mineru/bin/python - <<'PY'
import json
import pypdfium2 as pdfium
from PIL import ImageDraw, ImageFont

d = json.load(open('/tmp/_two_boxes.json'))
pdf = pdfium.PdfDocument('/home/doclens/RAG/data/pdfs/13c8e91b3467.pdf')
pg = pdf[0]
W, H = pg.get_size()
img = pg.render(scale=2.0).to_pil().convert('RGB')
dr = ImageDraw.Draw(img)
for i, (k, bb) in enumerate(d['chunk']):
    x0, y0, x1, y1 = bb
    dr.rectangle([x0*W, y0*H, x1*W, y1*H], outline=(220,30,30), width=4)
    dr.text((x0*W+4, y0*H+2), f'C{i}:{k}', fill=(220,30,30))
for i, (t, bb) in enumerate(d['raw']):
    if not bb or len(bb) != 4:
        continue
    x0, y0, x1, y1 = bb
    dr.rectangle([x0*W+3, y0*H+3, x1*W-3, y1*H-3], outline=(30,80,220), width=2)
img.save('/tmp/_overlay_two_13c8_p1.png')
print('saved /tmp/_overlay_two_13c8_p1.png')
pdf.close()
PY
