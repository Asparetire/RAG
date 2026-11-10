"""mineru_parser 映射/绑定/缓存单测（m1-runbook 1.3）。

夹具 = M0 探针解析的真实产物（Nature Communications 样例论文，11 页，
tests/fixtures/mineru_sample/），不真调 MinerU。
"""

import json
from pathlib import Path

import pytest

from doclens.parse import mineru_parser as mp
from doclens.parse.mineru_parser import build_doc, parse_pdf
from doclens.parse.schema import DoclensDoc

FIXTURES = Path(__file__).parent / "fixtures" / "mineru_sample"


@pytest.fixture(scope="module")
def doc() -> DoclensDoc:
    structured = json.loads((FIXTURES / "structured_content.json").read_text(encoding="utf-8"))
    middle = json.loads((FIXTURES / "middle_json.json").read_text(encoding="utf-8"))
    return build_doc("f" * 64, structured, middle)


def test_doc_meta_extracted(doc: DoclensDoc):
    """标题 + DOI 来自 middle_json 元数据（论文级去重的依据）。"""
    assert doc.title == "Bayesian teaching enables probabilistic reasoning in large language models"
    assert doc.doi == "10.1038/s41467-025-67998-6"
    assert doc.doc_id == "f" * 12


def test_only_canonical_types(doc: DoclensDoc):
    """全部块都落在四类之内；夹具论文无表格（MinerU 未输出 table 类型），不强求四类齐现。"""
    canonical = {"text", "title", "table", "image"}
    types = {b.type for b in doc.blocks}
    assert types <= canonical
    assert {"text", "title", "image"} <= types  # 夹具至少应出现这三类
    raw = json.loads((FIXTURES / "structured_content.json").read_text(encoding="utf-8"))
    raw_blocks = [b for pg in raw["pages"] for b in pg["blocks"]]
    n_img_src = sum(1 for b in raw_blocks if b.get("type") in ("image", "chart"))
    n_image_blocks = sum(1 for b in doc.blocks if b.type == "image")
    assert n_image_blocks == n_img_src  # chart+image 一个不少地映射为 image 块


def test_table_mapping_synthetic():
    """MinerU 输出 table 类型（部分文档会有）→ HTML 转 Markdown，不得静默丢弃。"""
    structured = {
        "pages": [
            {
                "page_idx": 0,
                "blocks": [
                    {
                        "type": "table",
                        "bbox": [0.1, 0.1, 0.9, 0.3],
                        "content": "<table><tr><th>Algo</th><th>Best</th></tr><tr><td>REL</td><td>0.98</td></tr></table>",
                    }
                ],
            }
        ]
    }
    doc = build_doc("b" * 64, structured, {})
    assert len(doc.blocks) == 1
    b = doc.blocks[0]
    assert b.type == "table" and b.page == 1
    assert b.content.splitlines()[0] == "| Algo | Best |"
    assert b.content.splitlines()[1] == "|---|---|"
    assert "| REL | 0.98 |" in b.content


def test_caption_binding(doc: DoclensDoc):
    """绑定率 ≥90%（PRD FR-1.3 验收线），且绑上的都是 Fig/Table/图/表 前缀的可信图注——
    子图面板标签、句子碎片不允许冒充图注（必须继承整图图注）。"""
    images = [b for b in doc.blocks if b.type == "image"]
    assert images
    bound = [b for b in images if b.caption]
    rate = len(bound) / len(images)
    assert rate >= 0.9, f"图注绑定率 {rate:.0%} 低于 90%"
    assert all(_CAPTION_OK.match(b.caption) for b in bound)


import re as _re

_CAPTION_OK = _re.compile(r"^\s*(?:Fig\.?|Figure|Table|图|表)\s*[0-9０-９]+", _re.IGNORECASE)


def test_image_path_paired_from_middle_json(doc: DoclensDoc):
    images = [b for b in doc.blocks if b.type == "image"]
    with_path = [b for b in images if b.image_path and b.image_path.startswith("images/")]
    assert with_path, "没有任何 image 块配到 image_path"
    assert all((FIXTURES / b.image_path).exists() for b in with_path), "image_path 指向的文件不在夹具目录"


def test_heading_path(doc: DoclensDoc):
    titles = [b for b in doc.blocks if b.type == "title"]
    assert titles[0].content.startswith("Bayesian teaching")  # doc_title 是全文第一个标题
    assert titles[0].heading_path == []  # 根标题没有祖先
    # "Results" 之下紧跟三级子标题" Evaluating belief updates..."——
    # 子标题的祖先链应含 "Results"；其正文的叶路径应含该子标题（层级栈替换正确）
    results_idx = next(i for i, b in enumerate(doc.blocks) if b.type == "title" and b.content == "Results")
    subsection = doc.blocks[results_idx + 1]
    assert subsection.type == "title" and "Results" in subsection.heading_path
    text_after = next(b for b in doc.blocks[results_idx + 2 :] if b.type == "text" and b.heading_path)
    assert subsection.content in text_after.heading_path
    # 任意正文块的祖先链都应能追溯到根标题
    some_text = next(b for b in doc.blocks if b.type == "text" and b.heading_path)
    assert some_text.heading_path[0].startswith("Bayesian teaching")


def test_equation_becomes_text(doc: DoclensDoc):
    texts = [b.content for b in doc.blocks if b.type == "text"]
    assert any("argmax" in t for t in texts), "公式（LaTeX）应作为 text 块保留"


def test_order_strictly_increasing(doc: DoclensDoc):
    orders = [b.order for b in doc.blocks]
    assert orders == sorted(orders) and len(set(orders)) == len(orders)
    pages = [b.page for b in doc.blocks]
    assert min(pages) >= 1


def test_parse_pdf_cache_hit(tmp_path, monkeypatch):
    """doc.json 已存在 → 直接返回缓存，绝不调 MinerU。"""
    parsed_dir = tmp_path / "parsed"
    pdf = tmp_path / "fake.pdf"
    pdf.write_bytes(b"%PDF-1.4 " + b"z" * 20480)
    digest = mp.sha256_of(pdf)

    cached = DoclensDoc(doc_id=digest[:12], sha256=digest, title="cached-doc")
    cached.save(parsed_dir / digest[:12] / "doc.json")

    monkeypatch.setattr(mp, "PARSED_DIR", parsed_dir)
    monkeypatch.setattr(mp, "_resolve_mineru_bin", lambda: (_ for _ in ()).throw(AssertionError("不应调用 MinerU")))

    got = parse_pdf(pdf)
    assert got == cached


def test_fallback_caption_nearest_prefix():
    """MinerU 没给 captions 时，同页就近前缀兜底。"""
    page_blocks = [
        {"type": "text", "bbox": [0.1, 0.05, 0.9, 0.08], "content": "Some intro sentence."},
        {"type": "chart", "bbox": [0.1, 0.1, 0.9, 0.4], "content": "", "captions": []},
        {"type": "text", "bbox": [0.1, 0.44, 0.9, 0.5], "content": "Fig. 2 | Accuracy across rounds."},
        {"type": "text", "bbox": [0.1, 0.55, 0.9, 0.6], "content": "Fig. 1 | A farther caption."},
    ]
    cap = mp._fallback_caption(page_blocks[1], page_blocks, 1)
    assert cap == "Fig. 2 | Accuracy across rounds."  # 离图底边最近者胜
