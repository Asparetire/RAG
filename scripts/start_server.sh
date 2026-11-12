#!/bin/bash
# DocLens 服务自愈启动（交付态）：杀死旧实例→等端口释放→启动→健康检查重试。
cd /home/doclens/RAG
pkill -f 'uvicorn doclens.serve' 2>/dev/null
sleep 2
for i in 1 2 3; do
  pkill -9 -f 'uvicorn doclens.serve' 2>/dev/null
  sleep 1
done
setsid nohup env WEB_STATIC=1 /opt/conda/envs/doclens/bin/uvicorn doclens.serve.api:app \
  --host 127.0.0.1 --port 8000 > /tmp/uvicorn.log 2>&1 < /dev/null &
# 健康检查重试（最多 30s）
for i in $(seq 1 15); do
  sleep 2
  if curl -s -m 2 http://127.0.0.1:8000/api/health | grep -q '"ok"'; then
    echo "SERVER_UP (after ${i}x2s)"
    exit 0
  fi
done
echo "SERVER_FAILED"
tail -20 /tmp/uvicorn.log
exit 1
