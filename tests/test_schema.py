"""schema 单测（m1-runbook 1.2 验收：字段完整 + JSON 序列化往返一致）。"""

import pytest

from doclens.parse.schema import Block, DoclensDoc


def _sample_doc() -> DoclensDoc:
    """覆盖四类块与全部可选字段的样例文档。"""
    return DoclensDoc(
        doc_id="a1b2c3d4e5f6",
        sha256="a" * 64,
        title="Binary Relation Learning and Classifying for Preselection in Evolutionary Algorithms",
        doi="10.1109/TEVC.2020.2986348",
        blocks=[
            Block(type="title", page=1, content="1. Introduction", order=0),
            Block(
                type="text",
                page=1,
                content="Preselection plays an important role in evolutionary algorithms.",
                bbox=[0.062, 0.117, 0.912, 0.133],
                heading_path=["1. Introduction"],
                order=1,
            ),
            Block(
                type="table",
                page=3,
                content="| Algorithm | Best | Mean |\n|---|---|---|\n| REL | 0.98 | 0.95 |",
                bbox=[0.1, 0.2, 0.9, 0.4],
                caption="Table 2: Comparison of preselection strategies.",
                order=4,
            ),
            Block(
                type="image",
                page=4,
                content="",
                bbox=[0.09, 0.3, 0.91, 0.55],
                caption="Fig. 3: Convergence curves on benchmark suite.",
                image_path="images/page_4_chart_3.jpg",
                order=7,
            ),
        ],
    )


def test_block_rejects_bad_type_and_page():
    with pytest.raises(ValueError):
        Block(type="paragraph", page=1, content="x")  # 非法类型
    with pytest.raises(ValueError):
        Block(type="text", page=0, content="x")       # 页码必须 1 起


def test_json_roundtrip_identical(tmp_path):
    doc = _sample_doc()
    path = tmp_path / "doc.json"
    doc.save(path)
    loaded = DoclensDoc.load(path)
    assert loaded == doc  # dataclass 字段级相等


def test_from_dict_tolerates_missing_optional_fields():
    doc = DoclensDoc.from_dict({"doc_id": "x", "sha256": "y"})
    assert doc.title is None
    assert doc.doi is None
    assert doc.blocks == []


def test_all_four_block_types_present():
    types = {b.type for b in _sample_doc().blocks}
    assert types == {"text", "title", "table", "image"}
