#!/bin/bash
cd /home/doclens/RAG && PYTHONPATH=/home/doclens/RAG /opt/conda/envs/doclens/bin/python - <<'PY'
from doclens.index.db import connect

conn = connect()
try:
    with conn.cursor() as cur:
        for t in ("t_embed_cache", "t_rerank_cache", "t_ctx_prefix"):
            cur.execute(f"SHOW COLUMNS FROM {t}")
            cols = [r[0] for r in cur.fetchall()]
            print(f"== {t} cols ==", cols)
        # 嵌入缓存按时间倒序——查询嵌入的 created_at 就是提问时刻
        cur.execute("SELECT * FROM t_embed_cache ORDER BY created_at DESC LIMIT 5") if 'created_at' in [r[0] for r in cur.fetchall()] else None
        cur.execute("SHOW COLUMNS FROM t_embed_cache")
        cols = [r[0] for r in cur.fetchall()]
        tcol = 'created_at' if 'created_at' in cols else cols[-1]
        cur.execute(f"SELECT * FROM t_embed_cache ORDER BY {tcol} DESC LIMIT 5")
        for row in cur.fetchall():
            print("  EMBED:", tuple(str(x)[:60] for x in row))
finally:
    conn.close()
PY
