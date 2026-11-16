#!/bin/bash
cd /home/doclens/RAG && PYTHONPATH=/home/doclens/RAG /opt/conda/envs/doclens/bin/python - <<'PY'
from doclens.index.db import connect
conn = connect()
try:
    with conn.cursor() as cur:
        cur.execute("SELECT kind, bbox FROM t_chunk WHERE bbox IS NOT NULL ORDER BY RAND() LIMIT 12")
        for k, b in cur.fetchall():
            print(k, "|", repr(b))
        print('--- caption 全量 ---')
        cur.execute("SELECT bbox FROM t_chunk WHERE kind='caption' AND bbox IS NOT NULL LIMIT 5")
        for (b,) in cur.fetchall():
            print(repr(b))
finally:
    conn.close()
PY
