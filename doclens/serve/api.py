"""M4 FastAPI 服务（m4-runbook K0/K1/K8/K11/K12；步 4.1/4.9/4.10）。

端面（R8 三件套 + R3 SSE + K11 登录门 + K12 模型切换）：
- POST /api/auth/login              登录（OAuth2 表单 → JWT；公开）
- GET  /api/auth/me                 当前会话自检（受保护）
- POST /api/query                   SSE 问答（契约=m4-runbook §3.1 冻结版；body.model=模型覆盖位）
- GET  /api/models                  可选模型清单（config 白名单+能力标记+当前默认）
- GET  /api/docs                    文档清单（前端侧栏）
- GET  /api/docs/{doc_id}/pdf       PDF 文件流（doc_id 严格校验 + realpath 包含性，K8①）
- GET  /api/figure/{chunk_id}       图/表原图（t_chunk 回表 + 包含性）
- GET  /api/health                  存活探针（公开；演示日隧道预检用）

鉴权（K11/R10）：公开组=login/health；受保护组=query/models/docs/figure 经 APIRouter
dependencies=[Depends(get_current_user)] 一把门；/web 静态托管豁免（登录页在 SPA 内）。
测试经 create_app(pipeline=..., auth_enabled=False) 关门。

交付形态（R1/K2）：app.frontend("dist") 托管 SPA（web/dist 入库；旧版 FastAPI 无该
API 时退 StaticFiles(html=True)，行为等价）。

安全（K8/R10）：bind 127.0.0.1 由启动命令约束（--host 127.0.0.1）；不开 CORS
中间件（dev=Vite proxy 同源、交付=同源静态托管）；该路由不加 GZip（uvicorn 默认
不压缩）；error 事件 message 脱敏 + 截断（key 永不外泄，M2 纪律）。

管线注入：create_app(pipeline=...) 供测试注入 mock（契约测试 4.2）——mock 需兼容
run_pipeline(question, profile_name, *, on_event, stream_gen, model=..., ...) 签名。
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.security import OAuth2PasswordRequestForm
from sse_starlette.sse import EventSourceResponse

from doclens.config import MODELS, PROJECT_ROOT, PROFILES, settings
from doclens.pipeline import run_pipeline
from doclens.serve import auth
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


def create_app(pipeline=None, *, auth_enabled: bool | None = None) -> FastAPI:
    """应用工厂；pipeline 仅供测试注入（默认 doclens.pipeline.run_pipeline）。

    auth_enabled：None=跟随 settings.auth_enabled（默认开）；False=测试关鉴权
    （契约测试等场景；公开/受保护路由结构不变，仅不挂 Depends）。
    """
    app = FastAPI(title="DocLens", version="0.4.0")
    app.state.pipeline = pipeline or run_pipeline
    _auth_on = settings.auth_enabled if auth_enabled is None else auth_enabled

    protected = APIRouter(dependencies=[Depends(auth.get_current_user)] if _auth_on else [])

    # ---- 登录（L0；公开组）----
    if _auth_on:

        @app.post("/api/auth/login")
        def api_login(form: Annotated[OAuth2PasswordRequestForm, Depends()]):
            token = auth.try_login(form.password, username=form.username)
            return {"access_token": token, "token_type": "bearer"}

        @protected.get("/api/auth/me")
        def api_me(user: dict = Depends(auth.get_current_user)):
            return user

    # ---- 问答（SSE；body.model=K12 模型覆盖位，服务端白名单校验回退默认）----
    @protected.post("/api/query")
    async def api_query(body: dict):
        question = (body.get("question") or "").strip()
        profile_name = body.get("profile") or "D"
        model_override = body.get("model") or None
        if not question:
            raise HTTPException(status_code=422, detail="question is required")
        if len(question) > 500:
            raise HTTPException(status_code=422, detail="question too long (max 500)")
        if profile_name not in PROFILES:
            raise HTTPException(status_code=422, detail="profile must be one of A..F")
        if model_override is not None:
            if not isinstance(model_override, str) \
                    or model_override not in {m["id"] for m in MODELS["gen"]}:
                raise HTTPException(status_code=422,
                                    detail="model must be one of /api/models whitelist")

        queue: asyncio.Queue = asyncio.Queue()

        async def _runner() -> None:
            try:
                await app.state.pipeline(
                    question, profile_name, on_event=queue.put_nowait, stream_gen=True,
                    model=model_override)
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

    # ---- 模型清单（K12；config 白名单+能力标记+当前默认）----
    @protected.get("/api/models")
    def api_models():
        return {
            "models": MODELS["gen"],
            "default": settings.gen_model,
            "rerank_tiers": [
                {"id": "flash", "label": "flash 重排（快）"},
                {"id": "pro", "label": "pro 重排（精）"},
            ],
        }

    # ---- 文档清单（侧栏）----
    @protected.get("/api/docs")
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
    @protected.get("/api/docs/{doc_id}/pdf")
    def api_pdf(doc_id: str):
        p = resolve_pdf(doc_id)
        if p is None:
            raise HTTPException(status_code=404, detail="not found")
        return FileResponse(p, media_type="application/pdf", filename=f"{doc_id}.pdf")

    # ---- 图/表原图（R8：chunk_id 回表，K8① 包含性）----
    @protected.get("/api/figure/{chunk_id}")
    def api_figure(chunk_id: str):
        p = resolve_figure(chunk_id)
        if p is None:
            raise HTTPException(status_code=404, detail="not found")
        return FileResponse(p, media_type=_MEDIA_BY_SUFFIX.get(p.suffix.lower(),
                                                              "application/octet-stream"))

    app.include_router(protected)

    # ---- 存活探针（公开组）----
    @app.get("/api/health")
    def api_health() -> dict:
        return {"ok": True}

    # ---- SPA 托管（交付形态，K2/R1）：显式开关 WEB_STATIC=1 才挂（dev 期 dist 存在
    # 也不干扰 /api）；fastapi>=0.162 官方 frontend()，fallback=auto 即 history fallback
    # （API 路由优先于前端，注册顺序已保证）。/web 豁免鉴权（登录页在 SPA 内）。
    dist = PROJECT_ROOT / "web" / "dist"
    if settings.web_static and dist.is_dir():
        if hasattr(app, "frontend"):
            app.frontend("/web", directory=str(dist), fallback="auto")
        else:
            from fastapi.staticfiles import StaticFiles
            app.mount("/web", StaticFiles(directory=dist, html=True), name="web")

    return app


app = create_app()
