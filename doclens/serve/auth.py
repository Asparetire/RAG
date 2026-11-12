"""M4 登录门 L0（m4-runbook K11/4.9；调研 §10 G 线）。

单管理员 + JWT（FastAPI 官方 OAuth2 范式 [G15]：pwdlib[argon2] + PyJWT HS256）：
- ADMIN_PASSWORD 经 .env 注入（随机生成，不入库）；argon2 校验；
- JWT 载荷含 sub/jti/session_stamp——session_stamp=argon2 哈希的派生指纹，
  **改密码即全端吊销**（旧 token 的 stamp 与新哈希不匹配；open-webui 同款 [G9]）；
- 登录限流 5 次/3 分钟（进程内存计数，单机作品集量级足够）；
- 未知来源密码错时仍执行一次假哈希比对，防时序探测（open-webui 同款）；
- 全路由一把门：/api/health、/api/auth/login、/web 豁免，其余 Depends 校验。
- L1 升级路径预埋：token 载荷与 get_current_user 返回形态带 user 概念，
  业务表已预埋可空 user_id（anything-llm 同款，anything-llm [G3]）。
"""

from __future__ import annotations

import hashlib
import secrets
import time
from collections import defaultdict, deque

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from pwdlib import PasswordHash

from doclens.config import settings

_pwd_hasher = PasswordHash.recommended()  # argon2id（pwdlib 默认推荐）

TOKEN_EXPIRE_SECONDS = 7 * 24 * 3600  # 7 天（演示场景；anything-llm 默认 30d 偏长）
_MAX_ATTEMPTS = 5
_WINDOW_SECONDS = 180


def _session_stamp() -> str:
    """从 ADMIN_PASSWORD 派生的会话指纹：改密即全端吊销（不存明文/不存库）。"""
    return hashlib.sha256(
        ("doclens-session-stamp:" + settings.admin_password).encode("utf-8")
    ).hexdigest()[:16]


def verify_password(plain: str) -> bool:
    return _pwd_hasher.verify(plain, _admin_hash())


def _admin_hash() -> str:
    """管理员密码的 argon2 哈希——进程内惰性缓存（首次校验时计算）。"""
    global _admin_hash_cache
    if _admin_hash_cache is None:
        _admin_hash_cache = _pwd_hasher.hash(settings.admin_password)
    return _admin_hash_cache


_admin_hash_cache: str | None = None


# ---------- 登录限流（进程内存；按来源 IP+用户名聚合） ----------

_attempts: dict[str, deque[float]] = defaultdict(deque)


def _rate_limit_key(ip: str, username: str) -> str:
    return f"{ip}:{username}"


def check_rate_limit(key: str) -> None:
    now = time.time()
    dq = _attempts[key]
    while dq and now - dq[0] > _WINDOW_SECONDS:
        dq.popleft()
    if len(dq) >= _MAX_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="尝试次数过多，请 3 分钟后再试",
        )


def record_failure(key: str) -> None:
    _attempts[key].append(time.time())


def reset_attempts(key: str) -> None:
    _attempts.pop(key, None)


# ---------- JWT ----------

_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


def create_access_token(ip: str = "") -> str:
    now = time.time()
    payload = {
        "sub": "admin",
        "jti": secrets.token_urlsafe(12),
        "stamp": _session_stamp(),
        "ip": ip,
        "iat": int(now),
        "exp": int(now + TOKEN_EXPIRE_SECONDS),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_token(token: str) -> dict:
    """校验签名/过期/session_stamp；失败一律 401（不区分原因，防探测）。"""
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录或登录已过期")
    if payload.get("stamp") != _session_stamp():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录或登录已过期")
    return payload


def get_current_user(token: str | None = Depends(_oauth2_scheme)) -> dict:
    """全路由一把门（Depends 注入；user 概念为 L1 预埋形态）。"""
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录或登录已过期")
    payload = decode_token(token)
    return {"user": payload.get("sub", "admin"), "jti": payload.get("jti", "")}


# ---------- 登录端点逻辑（api.py 引用；分离便于单测） ----------

def try_login(password: str, ip: str = "", username: str = "admin") -> str:
    """校验密码并签发 token；失败走限流+假哈希防时序。"""
    key = _rate_limit_key(ip, username)
    check_rate_limit(key)
    # 假哈希防时序探测：密码错也执行一次 argon2 校验（恒 False）
    if not verify_password(password):
        _pwd_hasher.verify(password, _FAKE_HASH)
        record_failure(key)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="密码错误")
    reset_attempts(key)
    return create_access_token(ip=ip)


# 预生成的假哈希（常量，避免每次请求重算）
_FAKE_HASH = _pwd_hasher.hash("doclens-fake-password-for-timing-equalization")
