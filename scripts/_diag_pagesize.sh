#!/bin/bash
cd /home/doclens/RAG
echo '===== structured_content.json 页面结构（1022ebce8e2e 第1页）====='
/opt/conda/envs/doclens/bin/python - <<'PY'
import json
d = json.load(open('data/parsed/1022ebce8e2e/structured_content.json'))
pages = d.get('pages', [])
print('top keys:', list(d.keys()))
pg = pages[0]
print('page keys:', list(pg.keys()))
# 打印除 blocks 外的全部字段（找页面尺寸信息）
for k, v in pg.items():
    if k != 'blocks':
        print(' ', k, '=', json.dumps(v, ensure_ascii=False)[:200])
blk = pg['blocks'][0]
print('block keys:', list(blk.keys()))
print('block0 bbox:', blk.get('bbox'), 'type:', blk.get('type'))
PY
echo '===== middle_json 页面尺寸 ====='
/opt/conda/envs/doclens/bin/python - <<'PY'
import json
d = json.load(open('data/parsed/1022ebce8e2e/middle_json.json'))
pg = d['pages'][0]
print('page keys:', list(pg.keys()))
for k in ('page_size', 'page_idx', 'w', 'h', 'width', 'height'):
    if k in pg:
        print(' ', k, '=', pg[k])
info = pg.get('page_info') or pg.get('info') or {}
print('  page_info:', json.dumps(info, ensure_ascii=False)[:300])
PY
echo '===== PDF 实际尺寸（pdfium）vs mediabox/cropbox（pypdf）====='
/opt/conda/envs/doclens-mineru/bin/python - <<'PY'
import pypdfium2 as pdfium
from pypdf import PdfReader
pdf = pdfium.PdfDocument('data/pdfs/1022ebce8e2e.pdf')
print('pdfium get_size page1:', pdf[0].get_size())
r = PdfReader('data/pdfs/1022ebce8e2e.pdf')
p = r.pages[0]
print('mediabox:', [float(v) for v in p.mediabox], ' cropbox:', [float(v) for v in p.cropbox], ' rotate:', p.get('/Rotate', 0))
PY
