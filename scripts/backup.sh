#!/usr/bin/env bash
# ============================================================
# DocLens 灾备脚本：把"清空服务器会丢的东西"备份进 /home/backup
# ============================================================
# 背景约定：服务器清空只保留 /home——因此
#   天然安全（本就在 /home）：代码 /home/doclens/RAG、论文 data/pdfs+data/parsed、
#                          .env、Qdrant 本体与 storage（/home/doclens/qdrant）
#   会丢、由本脚本兜底：    MySQL 数据(/var/lib/mysql)、Python 环境(/opt/conda 2.6G)、
#                          MinerU 模型(/root/.mineru 2.0G)
#
# 用法：
#   bash /home/doclens/backup.sh          # 每日备份（MySQL dump + Qdrant 快照 + .env）
#   bash /home/doclens/backup.sh --full   # 追加环境大包（conda+MinerU，约 4G/10 分钟，环境变更后手动跑一次）
#
# ★ 容器重建后的恢复手册（按序执行）：
#   1) apt update && apt install -y mysql-server cron && service mysql start
#   2) cd /opt && tar xzf /home/backup/<最新full>/conda-full.tgz        # 恢复 Python 环境
#      mkdir -p /root/.mineru && tar xzf /home/backup/<最新full>/mineru-models.tgz -C /root/.mineru --strip-components=2
#   3) mysql -e "CREATE DATABASE IF NOT EXISTS doclens CHARACTER SET utf8mb4"
#      gunzip < /home/backup/<最新>/mysql-doclens.sql.gz | mysql doclens
#      再执行同目录 mysql-recreate-user.sql.txt 里的建号语句（密码取自 dot-env-backup.txt 的 MYSQL_URL）
#   4) /home/doclens/RAG 在 home 保留区直接可用（git 状态按需修复）；前端改过才需 cd web && npm run build
#   5) cd /home/doclens/qdrant && nohup ./qdrant > qdrant.log 2>&1 &
#      （storage/ 与 qdrant 本体都在 home 保留区，向量数据直接在）
#   6) bash /home/doclens/RAG/scripts/start_server.sh
#   7) 重挂定时：apt install -y cron 后按 /etc/cron.d/doclens-backup 原样重建该文件
# ============================================================
set -e
TS=$(date +%Y-%m-%d_%H%M)
DEST=/home/backup/$TS
mkdir -p "$DEST"
cd /home/doclens/RAG
PY=/opt/conda/envs/doclens/bin/python

# 1) MySQL 逻辑备份（doclens 库：建表+数据+触发器，单事务一致性）
mysqldump --single-transaction --routines --triggers doclens > "$DEST/mysql-doclens.sql"
gzip -f "$DEST/mysql-doclens.sql"

# 2) MySQL 账号重建说明（dump 不含用户账号；密码在 .env 的 MYSQL_URL 里，勿外传备份目录）
cat > "$DEST/mysql-recreate-user.sql.txt" <<'EOF'
-- 恢复库后执行（把 <pwd> 换成 dot-env-backup.txt 里 MYSQL_URL 的密码段）：
-- CREATE USER IF NOT EXISTS 'hifen37'@'%' IDENTIFIED BY '<pwd>';
-- GRANT ALL PRIVILEGES ON doclens.* TO 'hifen37'@'%';
-- FLUSH PRIVILEGES;
EOF

# 3) Qdrant 快照（动态列 collections；POST 建快照 → GET 直接下载到备份目录，
#    不依赖 qdrant 的快照落盘位置——顶层 snapshots/ 与 storage/ 都见过）
QKEY="$(grep -E '^QDRANT_API_KEY=' /home/doclens/RAG/.env | cut -d= -f2- | tr -d '\r')"
COLS=$($PY -c "import urllib.request,json
req=urllib.request.Request('http://127.0.0.1:6333/collections',headers={'api-key':'$QKEY'})
d=json.load(urllib.request.urlopen(req))
print(' '.join(r['name'] for r in d['result']['collections']))")
for c in $COLS; do
  snap=$(curl -s -m 120 -X POST -H "api-key: $QKEY" "http://127.0.0.1:6333/collections/$c/snapshots?wait=true" \
         | $PY -c "import sys,json;print(json.load(sys.stdin)['result']['name'])" 2>/dev/null)
  if [ -n "$snap" ]; then
    curl -s -m 600 -H "api-key: $QKEY" "http://127.0.0.1:6333/collections/$c/snapshots/$snap" \
      -o "$DEST/qdrant-$c.snapshot" && echo "[快照] $c → $snap"
  else
    echo "[警告] $c 快照未生成"
  fi
done

# 4) .env（含全部密钥——备份目录不要外传/不要提交 git）
cp /home/doclens/RAG/.env "$DEST/dot-env-backup.txt"

# 5) 可选：环境大包（--full；环境变更后手动跑一次即可，平时不必）
if [ "${1:-}" = "--full" ]; then
  echo "== conda 环境打包（排除 pkgs 缓存）=="
  tar czf "$DEST/conda-full.tgz" --exclude='opt/conda/pkgs' -C / opt/conda
  echo "== MinerU 模型打包 =="
  tar czf "$DEST/mineru-models.tgz" -C / root/.mineru
fi

# 6) 轮换：只保留最近 7 份
ls -1dt /home/backup/*/ | tail -n +8 | xargs -r rm -rf

echo "备份完成 → $DEST"
du -sh "$DEST"
ls -lh "$DEST"
