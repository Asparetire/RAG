"""错误信息脱敏（S4 M4-05）：SSE error 事件与任务 error 字段共用同一口径。

独立模块避免 paperlib→api 循环导入。
"""

from __future__ import annotations

import re


def sanitize_error(exc: BaseException | str) -> str:
    """key 形态打码 + 绝对路径打码 + 截断（300），防内部细节（路径/凭据片段）外泄。M2 纪律。

    2026-11-17 S4 M-1（批量上传复查）：补绝对路径打码——OSError 等异常常内嵌
    服务器绝对路径（DATA_DIR/inbox），批量端点逐文件 detail 回显时不得泄露。
    """
    msg = str(exc)
    msg = re.sub(r"(sk-[A-Za-z0-9]{6})[A-Za-z0-9_-]+", r"\1***", msg)
    msg = re.sub(r"(api[_-]?key\s*[=:]\s*)\S+", r"\1***", msg, flags=re.IGNORECASE)
    msg = re.sub(r"/(?:[\w.\-]+/)+[\w.\-]+", "<path>", msg)                    # Unix 绝对路径
    msg = re.sub(r"[A-Za-z]:\\(?:[\w.\-]+\\)*[\w.\-]+", "<path>", msg)         # Windows 盘符路径
    return msg[:300]
