"""表格结构理解管线（K2 / m2-runbook 2.0；PRD FR-1.3 表格线性化升级）。

四步（先扫地、再认门牌）：
  ① 网格化：HTML 表（rowspan/colspan 复制补全对齐）或 markdown 表（管道行）→ 二维网格；
  ② 无效区域标记：空白行/列、分隔行、脚注行、合计行（含 MinerU raw 块自带 footnotes）；
  ③ 结构判定（在②清洗后的网格上）：列名 = 顶部连续表头行逐列拼接（"一级/二级"），
     行名列 = 首部非数值 + 高去重率列；判定从保守——宁漏拼不错拼；
  ④ 输出：表格卡片（表注+列名+行名前置）+ 清洗后 markdown + manifest（供审计与检索）。

输入 = MinerU structured_content 的原始表格块（HTML 串或 markdown 串）；
输出 = (卡片式 markdown, manifest dict)。manifest 随 doc.json 同目录落 tables_manifest.json。
2026-11-11 实测依据（specs/research/m2-indexing-survey.md）：MinerU 输出无 <th>（全 td，
表头判定必须启发式）；64/125 表源头为 HTML（带 span），61 表为 markdown 原生（降级路径）；
跨页表以 "(Continued)" 表注衔接、HTML 无截断 → 每个物理表自含表头、独立处理。
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Any

# ---- 数值判定（兼容 "1,234.5" 千分位 / "-1.4e-13" / "42.779"；"62, 180" 类多值串不算） ----
_THOUSANDS_RE = re.compile(r"^-?\(?\d{1,3}(,\d{3})+(\.\d+)?\)?%?$")
_NUM_RE = re.compile(r"^-?\(?\d+(\.\d+)?\)?%?$|^-?\d+(\.\d+)?([eE][+-]?\d+)?$")


def _is_numeric(s: str) -> bool:
    s = s.strip()
    if not s:
        return False
    if _THOUSANDS_RE.match(s):
        return True
    t = s.replace(",", "")
    if " " in t:  # 删逗号后仍有内部空白 = 多值串（如阈值对 "62, 180"）
        return False
    return bool(_NUM_RE.match(t))


# ---- ① 网格化 ----

class _TableHTMLParser(HTMLParser):
    """抓 <tr>/<td>/<th> 单元格文本与 span 属性（convert_charrefs 处理 &lt; 等实体）。"""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[tuple[str, int, int]]] = []
        self._row: list[tuple[str, int, int]] | None = None
        self._buf: list[str] = []
        self._in_cell = False
        self._rs = 1
        self._cs = 1

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        t = tag.lower()
        if t == "tr":
            self._row = []
            self.rows.append(self._row)
        elif t in ("td", "th") and self._row is not None:
            d = {k.lower(): (v or "") for k, v in attrs}
            try:
                self._rs = max(1, int(float(d.get("rowspan", 1))))
            except ValueError:
                self._rs = 1
            try:
                self._cs = max(1, int(float(d.get("colspan", 1))))
            except ValueError:
                self._cs = 1
            self._in_cell = True
            self._buf = []
        elif t == "br" and self._in_cell:
            self._buf.append(" ")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "br" and self._in_cell:
            self._buf.append(" ")

    def handle_data(self, data: str) -> None:
        if self._in_cell:
            self._buf.append(data)

    def handle_endtag(self, tag: str) -> None:
        t = tag.lower()
        if t in ("td", "th") and self._in_cell and self._row is not None:
            text = " ".join("".join(self._buf).split())
            self._row.append((text, self._rs, self._cs))
            self._in_cell = False
        elif t == "table":
            self._in_cell = False


def _grid_from_html(html: str) -> list[list[str]]:
    """HTML → span 复制补全二维网格（起点格存文本，覆盖格留空）。"""
    p = _TableHTMLParser()
    try:
        p.feed(html)
        p.close()
    except Exception:  # noqa: BLE001 解析容错：异常时退空网格
        return []
    occ: set[tuple[int, int]] = set()
    grid: dict[tuple[int, int], str] = {}
    for r, row in enumerate(p.rows):
        c = 0
        for text, rs, cs in row:
            while (r, c) in occ:
                c += 1
            for dr in range(rs):
                for dc in range(cs):
                    occ.add((r + dr, c + dc))
                    grid[(r + dr, c + dc)] = text if (dr, dc) == (0, 0) else ""
            c += cs
    if not grid:
        return []
    height = max(r for r, _ in grid) + 1
    width = max(c for _, c in grid) + 1
    return [[grid.get((r, c), "") for c in range(width)] for r in range(height)]


_MD_SEP = re.compile(r"^:?-{2,}:?$")


def _grid_from_markdown(md: str) -> list[list[str]]:
    """markdown 管道表 → 二维网格（跳过分隔行，右侧补齐列数）。"""
    rows: list[list[str]] = []
    for line in md.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if cells and all(_MD_SEP.match(c) for c in cells):
            continue  # 分隔行
        rows.append(cells)
    if not rows:
        return []
    width = max(len(r) for r in rows)
    return [r + [""] * (width - len(r)) for r in rows]


# ---- ② 无效区域标记 ----

_FOOTNOTE_RE = re.compile(
    r"^\s*(\*{1,3}|†|‡|note[s]?\b|注\s*[:：]|来源|data source|[a-e]\)\s)",
    re.IGNORECASE,
)
_TOTAL_RE = re.compile(
    r"^\s*(total|overall|average|mean|avg|sum|合计|总计|小计|平均|均值)\b",
    re.IGNORECASE,
)


def _row_stat(cells: list[str]) -> tuple[int, float, float]:
    """(非空格数, 数值占比, 平均字符长)。"""
    vals = [c.strip() for c in cells if c.strip()]
    if not vals:
        return 0, 0.0, 0.0
    num = sum(1 for v in vals if _is_numeric(v))
    return len(vals), num / len(vals), sum(len(v) for v in vals) / len(vals)


def _mark_invalid(grid: list[list[str]]) -> tuple[set[int], set[int], list[dict]]:
    """返回 (排除行号集, 排除列号集, excluded 清单)。只标记，不动网格。"""
    drop_rows: set[int] = set()
    drop_cols: set[int] = set()
    excluded: list[dict] = []
    height, width = len(grid), len(grid[0]) if grid else 0
    # 空行
    for r in range(height):
        if not any(c.strip() for c in grid[r]):
            drop_rows.add(r)
            excluded.append({"where": f"row {r}", "type": "empty", "reason": "整行空白", "disposition": "丢弃"})
    # 空列
    for c in range(width):
        if all(not grid[r][c].strip() for r in range(height)):
            drop_cols.add(c)
            excluded.append({"where": f"col {c}", "type": "empty", "reason": "整列空白", "disposition": "丢弃"})
    # 脚注/合计行（首个非空格匹配前缀 + 数值特征佐证；保守：不确定时不动）
    for r in range(height):
        if r in drop_rows:
            continue
        first = next((c.strip() for c in grid[r] if c.strip()), "")
        if not first:
            continue
        _, num_ratio, _ = _row_stat(grid[r])
        if _FOOTNOTE_RE.match(first) and num_ratio <= 0.34:
            drop_rows.add(r)
            excluded.append(
                {"where": f"row {r}", "type": "footnote", "reason": f"脚注前缀 {first[:20]!r}",
                 "disposition": "移至 chunk 尾部（表注）"}
            )
        elif _TOTAL_RE.match(first) and any(_is_numeric(c) for c in grid[r]):
            drop_rows.add(r)
            excluded.append(
                {"where": f"row {r}", "type": "total", "reason": f"合计/均值前缀 {first[:20]!r}",
                 "disposition": "保留至 chunk 尾部（汇总行）"}
            )
    return drop_rows, drop_cols, excluded


# ---- ③ 结构判定 ----

def _detect_header_rows(rows: list[list[str]]) -> list[int]:
    """顶部连续表头行：非数值、短文本；其后须出现数值密集行佐证；无数值行则整体无表头。"""
    any_data = any(_row_stat(r)[1] >= 0.4 for r in rows)
    if not any_data:
        return []  # 纯文本表（伪代码/表单）：不设表头，全部按数据行
    header: list[int] = []
    for i, r in enumerate(rows):
        n, num_ratio, avg_len = _row_stat(r)
        if n >= 2 and num_ratio <= 0.2 and avg_len <= 30 and len(header) == i and len(header) < 3:
            header.append(i)
        else:
            break
    return header


def _join_header(grid: list[list[str]], header_rows: list[int], width: int) -> list[str]:
    """逐列拼接表头（"一级/二级"），span 延续造成的连续重复值去重。"""
    cols: list[str] = []
    for c in range(width):
        parts: list[str] = []
        for r in header_rows:
            v = grid[r][c].strip()
            if v and v != (parts[-1] if parts else None):
                parts.append(v)
        cols.append("/".join(parts))
    return cols


def _detect_row_label_col(grid: list[list[str]], data_rows: list[int], width: int) -> int | None:
    """行名列 = 前 3 列中首个"非数值 + 高去重率"的列。"""
    for c in range(min(3, width)):
        vals = [grid[r][c].strip() for r in data_rows if grid[r][c].strip()]
        if len(vals) < 2:
            continue
        num_ratio = sum(1 for v in vals if _is_numeric(v)) / len(vals)
        distinct = len(set(vals)) / len(vals)
        if num_ratio < 0.2 and distinct >= 0.5:
            return c
    return None


def _extract_html(raw: dict) -> str:
    """raw 块内最长的含 <table 的字符串值（content 可能是 HTML 串）。"""
    best = ""

    def _walk(node: Any) -> None:
        nonlocal best
        if isinstance(node, dict):
            for v in node.values():
                _walk(v)
        elif isinstance(node, list):
            for v in node:
                _walk(v)
        elif isinstance(node, str) and "<table" in node.lower() and len(node) > len(best):
            best = node

    _walk(raw.get("content"))
    return best


def _flat_text(raw: dict) -> str:
    """无 HTML 时取 content 纯文本（markdown 原生表）。content 为串或分段列表。"""
    c = raw.get("content")
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return "".join(
            seg.get("content", "") for seg in c if isinstance(seg, dict) and isinstance(seg.get("content"), str)
        )
    return ""


# ---- ④ 输出组装 ----

def _cell(v: str) -> str:
    return v.strip().replace("|", "/").replace("\n", " ").strip()


def _build_body(
    grid: list[list[str]],
    keep_rows: list[int],
    header_cols: list[str],
    drop_cols: set[int],
) -> str:
    lines: list[str] = []
    if header_cols:
        lines.append("| " + " | ".join(_cell(v) for v in header_cols) + " |")
        lines.append("|" + "---|" * len(header_cols))
    for r in keep_rows:
        vals = [_cell(grid[r][c]) for c in range(len(grid[r])) if c not in drop_cols]
        if any(vals):
            lines.append("| " + " | ".join(vals) + " |")
    return "\n".join(lines)


def _build_card(caption: str | None, cols: list[str], labels: list[str]) -> str:
    parts = []
    if caption:
        parts.append(f"【表注】{caption.strip()[:300]}")
    if cols:
        shown = cols[:40]
        more = " …" if len(cols) > 40 else ""
        parts.append("【列】" + " / ".join(shown) + more)
    if labels:
        shown = labels[:40]
        more = " …" if len(labels) > 40 else ""
        parts.append("【行】" + " / ".join(shown) + more)
    return "\n".join(parts)


def transform_table(
    raw: dict, *, caption: str | None, page: int, order: int, doc_id: str = ""
) -> tuple[str, dict]:
    """原始表格块 → (卡片式 markdown, manifest)。

    HTML 源走网格化+span 补全；markdown 原生表走降级路径（无 span 可复原，照常判定表头/行名/无效区）。
    判定从保守：无法确信时不标记、不拼接（宁漏拼不错拼）。
    """
    html = _extract_html(raw)
    source = "html" if html else "markdown"
    grid = _grid_from_html(html) if html else _grid_from_markdown(_flat_text(raw))
    width = len(grid[0]) if grid else 0
    manifest: dict = {
        "table_id": f"{doc_id}-p{page:02d}-o{order:03d}" if doc_id else f"p{page:02d}-o{order:03d}",
        "page": page,
        "caption": (caption or "").strip() or None,
        "source": source,
        "columns": [],
        "row_label_col": None,
        "row_labels": [],
        "excluded": [],
        "n_rows_raw": len(grid),
        "n_rows_clean": 0,
    }
    if not grid or not width:
        # 防御：解析不出网格 → 退回 v1 式原样文本，manifest 记录降级
        fallback = _flat_text(raw).strip()
        manifest["excluded"].append(
            {"where": "table", "type": "degraded", "reason": "网格化失败，保留原文本", "disposition": "原样保留"}
        )
        return fallback, manifest

    drop_rows, drop_cols, excluded = _mark_invalid(grid)
    manifest["excluded"] = excluded
    candidates = [r for r in range(len(grid)) if r not in drop_rows]
    header_rows = _detect_header_rows([grid[r] for r in candidates])
    header_rows = [candidates[i] for i in header_rows]  # 映射回原行号
    data_rows = [r for r in candidates if r not in header_rows]
    header_cols = _join_header(grid, header_rows, width)
    has_header = any(header_cols)
    if not has_header:
        header_cols = []
        data_rows = candidates
    rl_col = _detect_row_label_col(grid, data_rows, width)
    row_labels: list[str] = []
    if rl_col is not None:
        manifest["row_label_col"] = rl_col
        prev = ""
        for r in data_rows:  # 纵向 span 延续格为空 → 向下前充
            v = grid[r][rl_col].strip() or prev
            if v and (not row_labels or v != row_labels[-1]):
                row_labels.append(v)
            prev = v

    manifest["columns"] = header_cols
    manifest["row_labels"] = row_labels[:60]

    tail: list[str] = []
    for note in raw.get("footnotes") or []:
        t = str(note.get("content", "")).strip() if isinstance(note, dict) else str(note).strip()
        if t:
            tail.append(f"表注：{t}")
    for e in excluded:
        if e["type"] == "footnote":
            r = int(e["where"].split()[1])
            tail.append("表注：" + " ".join(c.strip() for c in grid[r] if c.strip()))
        elif e["type"] == "total":
            r = int(e["where"].split()[1])
            tail.append("汇总行：" + _build_body([grid[r]], [0], [], set()))

    body = _build_body(grid, data_rows, header_cols, drop_cols)
    manifest["n_rows_clean"] = len(data_rows)
    parts = [_build_card(caption, header_cols, row_labels), body, *tail]
    content = "\n\n".join(p for p in parts if p.strip())
    return content, manifest
