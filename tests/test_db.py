"""db.py 连接助手单测（2.2）：URL 解析纯逻辑，不连真库。"""
import pytest

from doclens.index.db import DBConfigError, parse_mysql_url


def test_parse_full_url_with_password():
    cfg = parse_mysql_url("mysql+pymysql://hifen37:s3cret@10.14.50.123:3306/doclens")
    assert cfg["user"] == "hifen37"
    assert cfg["password"] == "s3cret"
    assert cfg["host"] == "10.14.50.123"
    assert cfg["port"] == 3306
    assert cfg["database"] == "doclens"
    assert cfg["charset"] == "utf8mb4"


def test_parse_url_without_password_and_encoded_password():
    cfg = parse_mysql_url("mysql+pymysql://doclens@127.0.0.1:3306/doclens")
    assert cfg["password"] == "" and cfg["host"] == "127.0.0.1"
    # 密码含特殊字符可 %-encode（.env 中写法）
    cfg2 = parse_mysql_url("mysql+pymysql://u:p%40ss@127.0.0.1:3306/doclens")
    assert cfg2["password"] == "p@ss"


def test_parse_url_invalid_raises():
    for bad in ("", "mysql://u@h/db", "mysql+pymysql://u@h/doclens", "postgres://u@h/db"):
        with pytest.raises(DBConfigError):
            parse_mysql_url(bad)


def test_parse_url_rejects_hyphen_db_and_trailing_garbage():
    """m-12：锚定匹配（fullmatch）——库名带连字符/尾随垃圾/query 参数一律报错，不静默截断连错库。"""
    for bad in (
        "mysql+pymysql://u:p@h:3306/doclens-bad",           # 连字符：旧实现截断成 doclens 静默连错库
        "mysql+pymysql://u:p@h:3306/doclens?charset=utf8",  # query 参数不支持
        "mysql+pymysql://u:p@h:3306/doclens/trash",         # 尾随垃圾
    ):
        with pytest.raises(DBConfigError):
            parse_mysql_url(bad)


def test_parse_error_message_masked_password():
    """S4-01：解析失败的异常消息不得含明文密码（密码不入错误信息）。"""
    secret = "super-secret-pwd-123"
    # 真正解析失败的形态：缺库名（_URL_RE 要求 /<db>\w+）
    with pytest.raises(DBConfigError) as ei:
        parse_mysql_url(f"mysql+pymysql://u:{secret}@h:3306/")
    msg = str(ei.value)
    assert secret not in msg, "异常消息泄漏明文密码"
    assert "***" in msg  # 脱敏占位存在


def test_parse_error_message_masked_password_no_at_sign():
    """S4-10：URL 截断成 mysql+pymysql://u:SECRET（无 @）形态时密码同样不入异常。

    旧脱敏正则要求密码段后有 @，此形态下 SECRET 明文泄漏（S4 复查本机实证）。"""
    secret = "leaky-secret-456"
    with pytest.raises(DBConfigError) as ei:
        parse_mysql_url(f"mysql+pymysql://u:{secret}")
    msg = str(ei.value)
    assert secret not in msg, "无 @ 形态异常消息泄漏明文密码"
    assert "***" in msg
