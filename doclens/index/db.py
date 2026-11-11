"""MySQL 连接助手（M2 共享；MYSQL_URL 解析 + 连接工厂）。

约定（plan D13 / AGENTS 环境细节）：
- MYSQL_URL = mysql+pymysql://<user>[:<pwd>]@<host>:<port>/<db>，两端 .env 各自配置
  （容器 127.0.0.1，Windows 10.14.50.123），凭据只存 .env 绝不入库不入日志；
- charset=utf8mb4（doclens 库既定）；autocommit 显式开启（DDL/写入简单可靠）；
- PyMySQL 为同步库：asyncio 并发场景用 asyncio.to_thread 包裹（m2-runbook §3.1 实现注意）。
"""

from __future__ import annotations

import re
from urllib.parse import unquote

from doclens.config import settings

_URL_RE = re.compile(
    r"mysql\+pymysql://(?P<user>[^:@]+)(?::(?P<pwd>[^@]*))?@(?P<host>[^:/]+):(?P<port>\d+)/(?P<db>\w+)"
)


class DBConfigError(ValueError):
    """MYSQL_URL 无法解析（格式错误或缺省字段）。"""


def parse_mysql_url(url: str | None = None) -> dict:
    """解析 MYSQL_URL → pymysql.connect 参数 dict；密码 URL 解码（含特殊字符时 .env 里可 %-encode）。"""
    raw = url if url is not None else settings.mysql_url
    m = _URL_RE.match(raw.strip())
    if not m:
        raise DBConfigError(f"MYSQL_URL 无法解析: {raw!r}（期望 mysql+pymysql://user:pwd@host:port/db）")
    return {
        "host": m.group("host"),
        "port": int(m.group("port")),
        "user": m.group("user"),
        "password": unquote(m.group("pwd") or ""),
        "database": m.group("db"),
        "charset": "utf8mb4",
    }


def connect(url: str | None = None, **overrides):
    """新建 pymysql 连接（autocommit）；调用方负责 close。"""
    import pymysql

    cfg = parse_mysql_url(url)
    cfg.update(overrides)
    return pymysql.connect(**cfg, autocommit=True)
