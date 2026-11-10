"""统一文档模型（PRD FR-1.2 / m1-runbook 步骤 1.2）。

四类块：text（段落）/ title（标题）/ table（表格）/ image（图片）；
每块带 1 起页码与页内 bbox 坐标（供 M4 前端原页高亮）；
图注就近绑定后回填 caption；图片落盘相对路径记 image_path；
heading_path 记录标题层级链（M2 上下文增强与检索过滤用）。

序列化约定：to_dict / from_dict / to_json / from_json / save / load
往返必须一致（tests/test_schema.py 验收）。
MinerU 原始块类型 → 四类块的映射在 mineru_parser.py，本文件只管模型本身。
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

VALID_BLOCK_TYPES: frozenset[str] = frozenset({"text", "title", "table", "image"})


@dataclass
class Block:
    """文档内一个连续区域：一段、一个标题、一张表或一张图。"""

    type: str                              # text | title | table | image
    page: int                              # 1 起页码
    content: str                           # 文字；表格为 Markdown 线性化；图片为空串
    bbox: list[float] | None = None        # [x0, y0, x1, y1]，沿用解析器输出的坐标（0–1 归一化）
    caption: str | None = None             # 图注/表注（就近绑定后回填）
    image_path: str | None = None          # 图片文件相对路径（image 块）
    heading_path: list[str] = field(default_factory=list)  # 所在标题层级链
    order: int = 0                         # 文档内阅读顺序号（0 起递增）

    def __post_init__(self) -> None:
        if self.type not in VALID_BLOCK_TYPES:
            raise ValueError(f"非法块类型: {self.type!r}，应为 {sorted(VALID_BLOCK_TYPES)} 之一")
        if not isinstance(self.page, int) or self.page < 1:
            raise ValueError(f"页码应为 1 起整数，收到 {self.page!r}")


@dataclass
class DoclensDoc:
    """一篇解析完成的论文 = 统一文档模型顶层对象。"""

    doc_id: str                            # intake 定档：PDF sha256 前 12 位
    sha256: str
    title: str | None = None
    doi: str | None = None
    blocks: list[Block] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DoclensDoc":
        blocks = [Block(**b) for b in data.get("blocks", [])]
        return cls(
            doc_id=data["doc_id"],
            sha256=data["sha256"],
            title=data.get("title"),
            doi=data.get("doi"),
            blocks=blocks,
        )

    def to_json(self, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    @classmethod
    def from_json(cls, text: str) -> "DoclensDoc":
        return cls.from_dict(json.loads(text))

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json(), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "DoclensDoc":
        return cls.from_json(Path(path).read_text(encoding="utf-8"))
