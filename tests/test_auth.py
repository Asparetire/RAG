"""M4 登录门单测（m4-runbook K11/4.9；调研 §10 G 线范式）。"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from doclens.serve import auth


def test_try_login_success_and_token_shape(monkeypatch):
    monkeypatch.setattr(auth, "_admin_hash_cache", None)  # 重置惰性缓存
    token = auth.try_login(auth.settings.admin_password, username="admin")
    payload = auth.decode_token(token)
    assert payload["sub"] == "admin"
    assert payload["stamp"] == auth._session_stamp()
    assert "jti" in payload and "exp" in payload


def test_try_login_wrong_password(monkeypatch):
    monkeypatch.setattr(auth, "_admin_hash_cache", None)
    auth.reset_attempts("test-ip:admin")
    with pytest.raises(HTTPException) as ei:
        auth.try_login("wrong-password", ip="test-ip")
    assert ei.value.status_code == 401


def test_rate_limit_blocks_after_5(monkeypatch):
    monkeypatch.setattr(auth, "_admin_hash_cache", None)
    key = "limit-test-ip:admin"
    auth.reset_attempts(key)
    for _ in range(auth._MAX_ATTEMPTS):
        with pytest.raises(HTTPException):
            auth.try_login("bad", ip="limit-test-ip")
    # 第 6 次直接 429（不再做哈希比对）
    with pytest.raises(HTTPException) as ei:
        auth.try_login(auth.settings.admin_password, ip="limit-test-ip")
    assert ei.value.status_code == 429
    auth.reset_attempts(key)


def test_decode_rejects_tampered_and_expired():
    token = auth.create_access_token()
    with pytest.raises(HTTPException):
        auth.decode_token(token + "x")  # 签名破坏
    payload = auth.decode_token(token)
    import time
    payload["exp"] = int(time.time()) - 10
    forged = __import__("jwt").encode(payload, auth.settings.jwt_secret, algorithm="HS256")
    with pytest.raises(HTTPException):
        auth.decode_token(forged)  # 过期


def test_session_stamp_revokes_on_password_change(monkeypatch):
    monkeypatch.setattr(auth, "_admin_hash_cache", None)
    token = auth.create_access_token()
    assert auth.decode_token(token)["sub"] == "admin"
    # 改密码 → stamp 变化 → 旧 token 吊销（open-webui 同款全端吊销）
    monkeypatch.setattr(auth.settings, "admin_password", "new-password")
    with pytest.raises(HTTPException):
        auth.decode_token(token)
