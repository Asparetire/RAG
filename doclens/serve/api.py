"""M4 FastAPI 服务（m4-runbook K0/K1/K8；步 4.1）。

端面（R8 三件套 + R3 SSE）：
- POST /api/query                  SSE 问答（契约=m4-runbook §3.1 冻结版）
- GET  /api/docs                   文档清单（前端侧栏）
- GET  /api/docs/{doc_id}/pdf      PDF 文件流（doc_id 严格校验 + realpath 包含性，K8①）
- GET  /api/figure/{chunk_id}      图/表原图（t_chunk 回表 + 包含性）
- GET  /api/health                 存活探针（演示日 checklist 隧道预检用）

交付形态（R1/K2）：app.frontend("dist") 托管 SPA（web/dist 入库；旧版 FastAPI 无该
API 时退 StaticFiles(html=True)，行为等价）。

安全（K8/R10）：bind 127.0.0.1 由启动命令约束（--host 127.0.0.1）；不开 CORS
中间件（dev=Vite proxy 同源、交付=同源静态托管）；该路由不加 GZip（uvicorn 默认
不压缩）；error 事件 message 脱敏 + 截断（key 永不外泄，M2 纪律）。

管线注入：create_app(pipeline=...) 供测试注入 mock（契约测试 4.2）——mock 需兼容
run_pipeline(question, profile_name, *, on_event, stream_gen, ...) 签名。
"""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from sse_starlette.sse import EventSourceResponse

from doclens.config import PROJECT_ROOT, PROFILES
from doclens.pipeline import run_pipeline
from doclens.serve.assets import resolve_figure, resolve_pdf

_SENTINEL_RESULT = "__result__"
_SENTINEL_ERROR = "__error__"

_MEDIA_BY_SUFFIX = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                    ".webp": "image/webp"}


def _sanitize_error(exc: BaseException) -> str:
    """error 事件 message 脱敏（R10⑤）：key 形态打码 + 截断，防内部细节外泄。"""
    msg = str(exc)
    msg = re.sub(r"(sk-[A-Za-z0-9]{6})[A-Za-z0-9_-]+", r"\1***", msg)
    msg = re.sub(r"(api[_-]?key\s*[=:]\s*)\S+", r"\1***", msg, flags=re.IGNORECASE)
    return msg[:300]


def create_app(pipeline=None) -> FastAPI:
    """应用工厂；pipeline 仅供测试注入（默认 doclens.pipeline.run_pipeline）。"""
    app = FastAPI(title="DocLens", version="0.4.0")
    app.state.pipeline = pipeline or run_pipeline

    # ---- 问答（SSE）----
    @app.post("/api/query")
    async def api_query(body: dict):
        question = (body.get("question") or "").strip()
        profile_name = body.get("profile") or "D"
        if not question:
            raise HTTPException(status_code=422, detail="question is required")
        if len(question) > 500:
            raise HTTPException(status_code=422, detail="question too long (max 500)")
        if profile_name not in PROFILES:
            raise HTTPException(status_code=422, detail="profile must be one of A..F")

        queue: asyncio.Queue = asyncio.Queue()

        async def _runner() -> None:
            try:
                await app.state.pipeline(
                    question, profile_name, on_event=queue.put_nowait, stream_gen=True)
                await queue.put({"event": _SENTINEL_RESULT, "data": {}})
            except Exception as exc:  # noqa: BLE001 任何异常 → error 事件（脱敏）后关流
                await queue.put({"event": _SENTINEL_ERROR,
                                 "data": {"code": type(exc).__name__,
                                          "message": _sanitize_error(exc)}})

        async def _stream():
            task = asyncio.create_task(_runner())
            try:
                while True:
                    payload = await queue.get()
                    event = payload.get("event")
                    if event == _SENTINEL_RESULT:
                        break
                    data = payload.get("data")
                    if event == _SENTINEL_ERROR:
                        yield {"event": "error",
                               "data": json.dumps(data, ensure_ascii=False)}
                        break
                    yield {"event": event, "data": json.dumps(data, ensure_ascii=False)}
            finally:
                if not task.done():
                    task.cancel()

        return EventSourceResponse(_stream(), ping=15)

    # ---- 文档清单（侧栏）----
    @app.get("/api/docs")
    def api_docs() -> list[dict]:
        from doclens.index.db import connect  # 局部导入：测试注入场景可不触库
        conn = connect()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT doc_id, title, n_chunks FROM t_doc ORDER BY doc_id")
                return [{"doc_id": r[0], "title": r[1], "n_chunks": r[2]}
                        for r in cur.fetchall()]
        finally:
            conn.close()

    # ---- PDF 文件流（R8：路径全部服务端推导，K8① 穿越守卫）----
    @app.get("/api/docs/{doc_id}/pdf")
    def api_pdf(doc_id: str):
        p = resolve_pdf(doc_id)
        if p is None:
            raise HTTPException(status_code=404, detail="not found")
        return FileResponse(p, media_type="application/pdf", filename=f"{doc_id}.pdf")

    # ---- 图/表原图（R8：chunk_id 回表，K8① 包含性）----
    @app.get("/api/figure/{chunk_id}")
    def api_figure(chunk_id: str):
        p = resolve_figure(chunk_id)
        if p is None:
            raise HTTPException(status_code=404, detail="not found")
        return FileResponse(p, media_type=_MEDIA_BY_SUFFIX.get(p.suffix.lower(),
                                                              "application/octet-stream"))

    # ---- 存活探针 ----
    @app.get("/api/health")
    def api_health() -> dict:
        return {"ok": True}

    # ---- SPA 托管（交付形态；web/dist 存在才挂，dev 期不干扰）----
    dist = PROJECT_ROOT / "web" / "dist"
    if dist.is_dir():
        if hasattr(app, "frontend"):
            app.frontend(str(dist))
        else:
            from fastapi.staticfiles import StaticFiles
            app.mount("/", StaticFiles(directory=dist, html=True), name="web")

    return app


app = create_app()
