#!/bin/bash
set -e
cd /home/doclens/RAG
echo '===== 1022ebce8e2e 第1页：raw 块 vs t_chunk 框 ====='
PYTHONPATH=/home/doclens/RAG /opt/conda/envs/doclens/bin/python - <<'PY'
import json
from doclens.index.db import connect

raw = json.load(open('data/parsed/1022ebce8e2e/structured_content.json'))
print('-- raw blocks p1 --')
raw_map = {}
for i, b in enumerate(raw['pages'][0]['blocks']):
    bb = b.get('bbox')
    c = b.get('content')
    if isinstance(c, list):
        c = ''.join(s.get('content', '') for s in c if isinstance(s, dict))
    print(f"  [{i}] {b.get('type'):<16} {bb} | {str(c)[:40]!r}")
    if bb and len(bb) == 4:
        raw_map[tuple(round(float(x), 3) for x in bb)] = (i, b.get('type'), str(c)[:40])

conn = connect()
try:
    with conn.cursor() as cur:
        cur.execute("SELECT kind, bbox, LEFT(content,60) FROM t_chunk WHERE doc_id='1022ebce8e2e' AND page=1 AND bbox IS NOT NULL")
        rows = cur.fetchall()
finally:
    conn.close()
print('-- t_chunk p1 --')
for k, b, c in rows:
    bb = json.loads(b)
    key = tuple(round(float(x), 3) for x in bb)
    hit = raw_map.get(key)
    print(f"  [{k}] {bb} | content={c[:45]!r}")
    print(f"        -> 命中 raw 块: {hit}")
PY
