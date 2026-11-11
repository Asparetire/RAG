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
    """解析 MYSQL_URL → pymysql.connect 参数 dict；密码 URL 解码（含特殊字符时 .env 里可 %-encode）。

    锚定匹配（m-12：re.fullmatch）——库名只接受 \\w+（连字符等字符会直接报错，而非静默截断
    连错库），**不支持 query 参数**（?charset=… 会被拒；charset 固定 utf8mb4）。
    安全约定（S4-01）：解析失败的异常消息**必须脱敏**——密码不入错误信息/日志（m2-runbook §8）。
    """
    raw = (url if url is not None else settings.mysql_url).strip()
    m = _URL_RE.fullmatch(raw)
    if not m:
        # S4-10：脱敏正则去掉尾部 @ 要求——URL 截断成 mysql+pymysql://u:SECRET（无 @）
        # 形态时密码同样不入异常（S4 复查附带发现，leak 实证后修复）
        safe = re.sub(r"(://[^:@/]+:)[^@]*", r"\1***", raw)
        raise DBConfigError(f"MYSQL_URL 无法解析: {safe!r}（期望 mysql+pymysql://user:pwd@host:port/db）")
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
    # n-9：connect_timeout 兜底 10s（库不可达时不挂 OS 级超时）；overrides 可覆盖
    cfg.setdefault("connect_timeout", 10)
    return pymysql.connect(**cfg, autocommit=True)
