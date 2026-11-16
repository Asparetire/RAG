#!/bin/bash
echo '--- node ---'
which node || ls /root/.vscode-server/cli/servers/*/server/node 2>/dev/null | head -2
node --version 2>/dev/null || /root/.vscode-server/cli/servers/*/server/node --version 2>/dev/null | head -1
echo '--- 最近上传任务（t_ingest_task）---'
cd /home/doclens/RAG && PYTHONPATH=/home/doclens/RAG /opt/conda/envs/doclens/bin/python - <<'PY'
from doclens.index.db import connect
conn = connect()
try:
    with conn.cursor() as cur:
        cur.execute("SHOW COLUMNS FROM t_ingest_task")
        print([r[0] for r in cur.fetchall()])
        cur.execute("SELECT * FROM t_ingest_task ORDER BY 1 DESC LIMIT 8")
        for row in cur.fetchall():
            print(row)
finally:
    conn.close()
PY
