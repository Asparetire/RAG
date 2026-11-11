"""K1 节内聚合切块（m2-runbook 2.1；PRD FR-2.1）。

规则（含调研 R1–R3 修订）：
- 同 heading_path 的**相邻** text 块合并；超 1600 字符按句切分（单句超限硬切）；
  短节独立成块（宁短勿跨节）；跨节不合并；节内句切块间不加 overlap（M5 消融位）；
- 标题块不单独入库（heading_path 已含层级链），作前缀随块走：`" / ".join(heading_path)` + 换行，
  前缀不计入 800–1600 预算（理由记录：总长远低于嵌入输入上限，调研 R3）；
- 内容过滤：References/Bibliography 节不入库；页眉页脚 = 无标题归属 + 短文本 +
  **跨页重复出现 ≥2 次**才丢弃（RAGFlow 先例，单次出现保留防误删，调研 R1）；
- 索引单元：text（聚合块）/ table（1 表 1 chunk，含卡片）/ caption（有图注图 → 图注文本块）
  / image（每图 1 单元，content=caption 可空——供图像向量入库，无图注图仅此一路，调研 R5；
  无图注且无 image_path 的空图单元不产出，m-8）；
- chunk_id = `{doc_id}:{doc 内序号}`（全单元统一递增，幂等入库与回表的联接键）。
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from doclens.parse.schema import Block, DoclensDoc

CHUNK_MAX = 1600  # 超限按句切分（字符，不含 heading 前缀）
RUNNING_HEAD_MAX = 300  # 页眉页脚候选长度上限
RUNNING_HEAD_REPEATS = 2  # 跨页重复 ≥2 次才判垃圾（RAGFlow 先例）

# 句切分：句末标点 + 空白 + 常见句首字符（缩写误切代价低，接受）
_SENT_RE = re.compile(r'(?<=[.!?])\s+(?=[A-Z0-9"(\\\[$<])')
# m-4：放开可选编号前缀——"4. References"/"5 参考文献"等编号型标题同样命中
_REFERENCE_RE = re.compile(r"^\s*(?:\d+[.:：]?\s*)?(references|bibliography|参考文献)\b", re.IGNORECASE)


@dataclass
class Chunk:
    """一个入库索引单元（t_chunk 单一事实源；Qdrant 点 ID = uuid5(chunk_id)）。"""

    chunk_id: str
    kind: str                       # text | table | caption | image
    content: str                    # text/table/caption：heading 前缀 + 正文；image：caption 可空
    page: int                       # 首块 1 起页码
    bbox: list[float] | None        # 首块坐标（0–1 归一化）
    heading_path: list[str]
    image_path: str | None = None   # caption/image 单元必带
    caption: str | None = None      # caption/image 单元带原表注/图注

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.content.encode("utf-8")).hexdigest()


def _norm(s: str) -> str:
    return " ".join(s.split())


def _hard_split(s: str, limit: int) -> list[str]:
    """单句超限硬切：优先在空格处断开。"""
    parts: list[str] = []
    i = 0
    while i < len(s):
        j = min(i + limit, len(s))
        if j < len(s):
            k = s.rfind(" ", i, j)
            if k > i:
                j = k
        piece = s[i:j].strip()
        if piece:
            parts.append(piece)
        i = j
    return parts


def _pack(body: str, limit: int) -> list[str]:
    """句级贪心打包：每块 ≤ limit；单句超限硬切。"""
    sents = [t for t in _SENT_RE.split(body) if t.strip()]
    out: list[str] = []
    cur: list[str] = []
    cur_len = 0
    for s in sents:
        if len(s) > limit:
            if cur:
                out.append(" ".join(cur))
                cur, cur_len = [], 0
            out.extend(_hard_split(s, limit))
            continue
        add = len(s) + (1 if cur else 0)
        if cur_len + add > limit:
            out.append(" ".join(cur))
            cur, cur_len = [s], len(s)
        else:
            cur.append(s)
            cur_len += add
    if cur:
        out.append(" ".join(cur))
    return out


def _prefixed(prefix: str, body: str) -> str:
    return f"{prefix}\n{body}" if prefix else body


def chunk_doc(doc: DoclensDoc) -> list[Chunk]:
    """DoclensDoc → 有序 Chunk 列表（text/table/caption/image 全单元）。"""
    seq = 0
    out: list[Chunk] = []

    def emit(kind: str, content: str, page: int, bbox: list[float] | None,
             hp: list[str], image_path: str | None = None, caption: str | None = None) -> None:
        nonlocal seq
        if kind == "image" and not content and not image_path:
            return  # m-8：无图注且无文件路径的空图单元不产 chunk（t_chunk 空行、Qdrant 无点，验收对不齐）
        if not content.strip() and kind != "image":
            return
        out.append(Chunk(
            chunk_id=f"{doc.doc_id}:{seq:04d}", kind=kind, content=content,
            page=page, bbox=bbox, heading_path=list(hp), image_path=image_path, caption=caption,
        ))
        seq += 1

    # ① 页眉页脚统计：无标题归属 + 短文本 + 跨页重复 ≥2 次（内容归一化后全等）
    counts: dict[str, int] = {}
    for b in doc.blocks:
        if b.type == "text" and not b.heading_path:
            k = _norm(b.content)
            if 0 < len(k) < RUNNING_HEAD_MAX:
                counts[k] = counts.get(k, 0) + 1

    def is_running_head(b: Block) -> bool:
        if b.type != "text" or b.heading_path:
            return False
        k = _norm(b.content)
        return 0 < len(k) < RUNNING_HEAD_MAX and counts.get(k, 0) >= RUNNING_HEAD_REPEATS

    # ② 顺序遍历：text 相邻同节聚合；其余块 flush 后独立成单元
    buf: list[Block] = []

    def flush() -> None:
        nonlocal buf
        if not buf:
            return
        hp = buf[0].heading_path
        prefix = " / ".join(hp)
        body = "\n".join(b.content.strip() for b in buf)
        pieces = _pack(body, CHUNK_MAX) if len(body) > CHUNK_MAX else [body]
        for piece in pieces:
            emit("text", _prefixed(prefix, piece), buf[0].page, buf[0].bbox, hp)
        buf = []

    for b in doc.blocks:
        if b.type == "title":
            flush()  # 标题块不入库（层级链已在后续块的 heading_path 中）
            continue
        if b.type == "text":
            if any(_REFERENCE_RE.match(e.strip()) for e in b.heading_path):
                flush()  # References/Bibliography 节不入库
                continue
            if is_running_head(b):
                flush()
                continue
            if buf and buf[0].heading_path != b.heading_path:
                flush()  # 跨节不合并
            buf.append(b)
            continue
        flush()
        if b.type == "table":
            prefix = " / ".join(b.heading_path)
            emit("table", _prefixed(prefix, b.content), b.page, b.bbox, b.heading_path)
        elif b.type == "image":
            prefix = " / ".join(b.heading_path)
            if b.caption:  # 有图注图 → 图注文本块（文本集合）+ 图像单元（图像集合）双路
                emit("caption", _prefixed(prefix, b.caption), b.page, b.bbox, b.heading_path,
                     image_path=b.image_path, caption=b.caption)
            emit("image", b.caption or "", b.page, b.bbox, b.heading_path,
                 image_path=b.image_path, caption=b.caption)
    flush()
    return out
