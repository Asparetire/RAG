"""table_struct 单测（m2-runbook 2.0；夹具=容器真实解析产物 tests/fixtures/m2_table_samples.json）。

覆盖：span 复制补全两级表头拼接、全 td 无 th 表头判定、markdown 降级路径、
脚注/合计行排除与去向、伪代码表（纯文本无表头）防御、"(Continued)" 续表、form 表（全宽首行）。
"""
import json
import pathlib
import sys

import pytest

from doclens.parse.table_struct import (
    _grid_from_html,
    _grid_from_markdown,
    _is_numeric,
    transform_table,
)

FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "m2_table_samples.json"


def load_samples() -> list[dict]:
    return json.loads(FIXTURES.read_text(encoding="utf-8"))


def sample(kind: str, doc_id: str | None = None) -> dict:
    for s in load_samples():
        if s["kind"] == kind and (doc_id is None or s["doc_id"] == doc_id):
            return s
    raise AssertionError(f"fixture not found: kind={kind} doc_id={doc_id}")


# ---- 基础单元 ----


def test_is_numeric_variants():
    assert _is_numeric("1,234.5")  # 千分位
    assert _is_numeric("-1.4e-13")
    assert _is_numeric("8.81e-14")
    assert _is_numeric("42.779")
    assert not _is_numeric("F1")
    assert not _is_numeric("62, 180")  # 逗号+空格 = 多值串（阈值对），不算数值
    assert not _is_numeric("")


def test_grid_from_html_span_fill():
    """rowspan/colspan 复制补全：起点格存文本，覆盖格留空，网格矩形对齐。"""
    html = (
        "<table><tr><td rowspan='2'>A</td><td colspan='2'>B</td></tr>"
        "<tr><td>B1</td><td>B2</td></tr>"
        "<tr><td>r1</td><td>1</td><td>2</td></tr></table>"
    )
    g = _grid_from_html(html)
    assert len(g) == 3 and len(g[0]) == 3
    assert g[0] == ["A", "B", ""]
    assert g[1] == ["", "B1", "B2"]
    assert g[2] == ["r1", "1", "2"]


def test_grid_from_markdown_skips_separator_and_pads():
    md = "| a | b |\n| --- | --- |\n| 1 | 2 |\n| x |"
    g = _grid_from_markdown(md)
    assert g == [["a", "b"], ["1", "2"], ["x", ""]]


def test_grid_from_markdown_single_col_separator():
    """d059 真实伪影：分隔行 1 列、数据行 2 列 → 分隔行跳过、列数按最宽对齐。"""
    md = "| full width text |\n|---|\n| label | long text |"
    g = _grid_from_markdown(md)
    assert len(g[0]) == 2
    assert g[0] == ["full width text", ""]


# ---- 真实夹具：HTML 两级表头 ----


def test_two_level_header_join():
    """13c8e91b Table4：全 td 两级表头 → 逐列拼接 "一级/二级"。"""
    s = sample("html_raw", "13c8e91b3467")
    content, man = transform_table(s["raw"], caption="Table 4 test", page=20, order=1, doc_id=s["doc_id"])
    assert man["source"] == "html"
    assert man["columns"][2] == "Best objective function values/BFHS"
    assert man["columns"][6] == "Optimum threshold values/BFHS"
    assert man["columns"][0] == "Test images"  # rowspan 延续去重
    assert man["columns"][1] == "m"
    assert len(man["columns"]) == 10
    # 行名列 = 第 0 列，纵向 span 前充后行标签保留
    assert man["row_label_col"] == 0
    assert "1 (750 × 750)" in man["row_labels"] and "2 (512 × 512)" in man["row_labels"]
    # 卡片与正文
    assert "【表注】Table 4 test" in content
    assert "【列】" in content and "【行】" in content
    assert "| Test images |" in content  # 表头行
    assert "0.898988" in content  # 数据保留
    assert man["n_rows_raw"] > man["n_rows_clean"] or man["n_rows_clean"] > 0


def test_md_native_table_header_detected():
    """3627b932f186 Table2：F/CS/ABC… 两级表头（HTML 源）。"""
    s = sample("html_raw", "3627b932f186")
    content, man = transform_table(s["raw"], caption=None, page=6, order=2, doc_id=s["doc_id"])
    assert man["source"] == "html"
    assert man["columns"][1] == "CS/Ave"
    assert man["columns"][4] == "ABC/Ave"  # col4 = ABC 组第一子列
    assert man["row_label_col"] == 0
    assert man["row_labels"][:3] == ["F1", "F2", "F3"]
    assert "【表注】" not in content  # 无 caption 自动省略
    assert "-1400.000" in content


# ---- markdown 降级路径 ----


def test_markdown_native_table():
    """5db85404be42 Table1（markdown 原生、无 span）：表头识别 + 行名列。"""
    s = sample("md_block", "5db85404be42")
    content, man = transform_table({"content": s["block"]["content"]}, caption=s["block"]["caption"], page=6, order=3)
    assert man["source"] == "markdown"
    assert man["columns"][:2] == ["Journal", "IF 2019"]
    assert man["row_label_col"] == 0
    assert "Pattern Recognition" in man["row_labels"]
    assert "【表注】Table 1" in content
    assert "7.196" in content


def test_pseudocode_table_no_header():
    """13c8e91b 续表（伪代码）：纯文本无数值行 → 不设表头（保守，不把数据行当列名）。"""
    s = sample("continued_block", "13c8e91b3467")
    b = s["block"]
    content, man = transform_table({"content": b["content"]}, caption=b["caption"], page=b["page"], order=b["order"])
    assert man["source"] == "markdown"
    assert man["columns"] == []
    # col0 是行号（35:/36:/…）——伪代码的合法行标识，判定为行名列无害且可被查询
    assert man["row_label_col"] == 0
    assert "【列】" not in content
    # 数据行不丢
    assert "Update the HS" in content
    assert "| --- |" not in content  # m-13：无表头即无分隔行（直接断言，不取段）


def test_form_table_full_width_first_row():
    """d059 Reporting Summary：全宽首行不当列名（判定保守）；两列键值行保留。"""
    s = sample("md_block", "d059e8540d5d")
    content, man = transform_table({"content": s["block"]["content"]}, caption=None, page=16, order=4)
    assert man["source"] == "markdown"
    assert man["columns"] == []  # 全宽长文本行不满足表头条件
    assert "Reporting on sex and gender" in content
    assert "【行】" in content or man["row_label_col"] is not None


def test_html_footnotes_to_tail():
    """d059 HTML 原始块自带 footnotes → 表注进尾部，数据行不混入。"""
    s = sample("html_raw", "d059e8540d5d")
    content, man = transform_table(s["raw"], caption=None, page=15, order=5, doc_id=s["doc_id"])
    assert man["source"] == "html"
    assert "表注：Note that full information" in content
    # 表注在正文之后
    assert content.index("表注：") > content.index("Reporting on sex")


def test_degraded_empty_content():
    """防御：内容无法成网格 → 原样保留 + manifest 降级记录。"""
    content, man = transform_table({"content": "not a table"}, caption=None, page=1, order=6)
    assert content == "not a table"
    assert man["excluded"][0]["type"] == "degraded"


def test_degraded_html_source_strips_tags():
    """m-6：HTML 源网格化失败 → 降级文本先去标签/线性化，不把原始 <table> 标签塞进 chunk。"""
    html = "<table><caption>x</caption>no rows</table>"
    content, man = transform_table({"content": html}, caption=None, page=1, order=10)
    assert man["source"] == "html"
    assert man["excluded"][0]["type"] == "degraded"
    assert "<" not in content and ">" not in content  # 原始标签不入 chunk
    assert "no rows" in content


def test_excluded_structure_fields():
    """excluded 每条含 where/type/reason/disposition 四字段（用户验收口径）。"""
    s = sample("html_raw", "13c8e91b3467")
    _, man = transform_table(s["raw"], caption=None, page=20, order=7)
    for e in man["excluded"]:
        assert set(e.keys()) == {"where", "type", "reason", "disposition"}


def test_total_row_excluded_and_kept_at_tail():
    """runbook §6 点名夹具：Average/Total 合计行 → 排除出数据区 + 保留至尾部（S3 审查补测）。"""
    html = (
        "<table><tr><td>Method</td><td>Score</td></tr>"
        "<tr><td>Base</td><td>80.1</td></tr>"
        "<tr><td>Ours</td><td>85.3</td></tr>"
        "<tr><td>Average</td><td>82.7</td></tr>"
        "</table>"
    )
    content, man = transform_table({"content": html}, caption=None, page=1, order=8)
    total_ex = [e for e in man["excluded"] if e["type"] == "total"]
    assert len(total_ex) == 1 and "Average" in total_ex[0]["reason"]
    assert total_ex[0]["disposition"] == "保留至 chunk 尾部（汇总行）"
    assert man["n_rows_clean"] == 2  # 数据行只剩 Base/Ours
    assert "82.7" not in content.split("汇总行")[0]  # 汇总值不在正文数据区
    assert "汇总行：| Average | 82.7 |" in content  # 尾部保留（可检索）
    # 中文合计同样命中
    content2, man2 = transform_table(
        {"content": "<table><tr><td>方法</td><td>得分</td></tr><tr><td>合计</td><td>90</td></tr></table>"},
        caption=None, page=1, order=9,
    )
    assert [e["type"] for e in man2["excluded"]] == ["total"]
    assert "汇总行" in content2


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
