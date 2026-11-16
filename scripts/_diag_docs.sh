#!/bin/bash
echo '--- all tables ---'
cd /home/doclens/RAG && PYTHONPATH=/home/doclens/RAG /opt/conda/envs/doclens/bin/python - <<'PY'
from doclens.index.db import connect

conn = connect()
try:
    with conn.cursor() as cur:
        cur.execute("SHOW TABLES")
        tables = [r[0] for r in cur.fetchall()]
        print(tables)
finally:
    conn.close()
PY
echo '--- t_doc vs data/pdfs 对账 ---'
ls /home/doclens/RAG/data/pdfs/ | sed 's/\.pdf//' | sort > /tmp/_pdfs.txt
PYTHONPATH=/home/doclens/RAG /opt/conda/envs/doclens/bin/python - <<'PY'
from doclens.index.db import connect
conn = connect()
try:
    with conn.cursor() as cur:
        cur.execute("SELECT doc_id, title FROM t_doc")
        docs = cur.fetchall()
        import pathlib
        have = set(pathlib.Path('/tmp/_pdfs.txt').read_text().split())
        for doc_id, title in docs:
            mark = 'OK' if doc_id in have else 'PDF缺失!'
            print(f"  {doc_id} {mark} {str(title)[:35]}")
finally:
    conn.close()
PY
