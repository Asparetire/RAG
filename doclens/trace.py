"""问答 trace 落盘（m3-runbook K8，调研 R15；主计划未列此文件，收官补记）。

设计：
- 一行一个查询事件的 **JSONL**，落 `data/traces/`（data/ 被 gitignore，不入库）；
- 字段与 M5 失败归因 F0–F6 一一对应（m3-runbook §3.1 schema）：
  routes（各路 chunk_id+分数+排名 → F2 召回缺失）、fused/fused_dedup（融合序 → F3 融合错排）、
  rerank（前后序+degraded → F4 重排伤害）、context（最终上下文 → F5 生成失败的证据面）、
  llm.reasoning/content 分列（思考不入答案的审计）、fallback（→ F6 兜底误触发）；
- **脱敏纪律（m3-runbook §8）**：key/密码/.env 值绝不入 trace——本模块只写调用方传入的结构化数据；
- 文件按天滚动：traces-YYYYMMDD.jsonl（追加写，进程内不持锁——M3 单 CLI 进程，M4 再议）。
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path

from doclens.config import DATA_DIR

TRACE_DIR = DATA_DIR / "traces"


def _jsonable(obj):
    """dataclass / 常见容器 → JSON 可序列化结构（未知类型转 str，绝不抛错——trace 不能炸主链路）。"""
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if is_dataclass(obj) and not isinstance(obj, type):
        return {k: _jsonable(v) for k, v in asdict(obj).items()}
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_jsonable(v) for v in obj]
    return str(obj)


def query_id(question: str, profile: str) -> str:
    """trace 主键：时间戳 + 档位 + 问题哈希前 10 位（同问题同档可归组，跨日不冲突）。"""
    import hashlib

    h = hashlib.sha256(f"{profile}:{question}".encode("utf-8")).hexdigest()[:10]
    return f"{datetime.now().strftime('%Y%m%d%H%M%S')}-{profile}-{h}"


def append_event(query_id: str, kind: str, payload: dict, *, trace_dir: Path | None = None) -> Path:
    """追加一条子事件（routes/fused/rerank/context/llm/fallback…）；返回落盘文件路径。

    设计为"子事件流"而非"单行大 JSON"：检索与生成是两段耗时，先到的先落盘
    （进程崩溃也有前半段 trace 可归因——F2/F3/F4 与 F5/F6 可分开归档）。
    """
    d = trace_dir or TRACE_DIR
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"traces-{datetime.now().strftime('%Y%m%d')}.jsonl"
    event = {
        "ts": time.time(),
        "query_id": query_id,
        "kind": kind,
        **_jsonable(payload),
    }
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")
    return path
