"""quality_report 核心统计逻辑单测（m1-runbook 1.4）。"""

from doclens.parse.schema import Block, DoclensDoc
from scripts.quality_report import inspect_doc


def test_inspect_doc_counts_and_empty_images(tmp_path):
    doc = DoclensDoc(
        doc_id="x" * 12,
        sha256="x" * 64,
        title="t",
        blocks=[
            Block(type="text", page=1, content="a", order=0),
            Block(type="title", page=1, content="H", order=1),
            Block(type="table", page=1, content="| a |", order=2),
            Block(type="image", page=1, content="", caption="Fig. 1 | ok", image_path="images/a.jpg", order=3),
            Block(type="image", page=2, content="", caption=None, image_path=None, order=4),
            Block(type="image", page=3, content="", caption="Fig. 2 | lost", image_path="images/gone.jpg", order=5),
        ],
    )
    (tmp_path / "images").mkdir()
    (tmp_path / "images" / "a.jpg").write_bytes(b"x")  # gone.jpg 故意不给 → 空图检测

    r = inspect_doc(doc, tmp_path)
    assert r["n_blocks"] == 6
    assert r["n_images"] == 3 and r["n_bound"] == 2
    assert r["binding_rate"] == 2 / 3
    # 有编号单元：Fig. 1（bound）与 Fig. 2（lost，绑了但无编号匹配？——
    # Fig. 2 | lost 是前缀型 → 算单元且覆盖）；无图注块不计单元
    assert r["n_units"] == 2 and r["n_units_covered"] == 2 and r["unit_coverage"] == 1.0
    assert r["n_no_caption"] == 1
    assert r["empty_images"] == ["p2: 无 image_path", "p3: 文件缺失 images/gone.jpg"]


def test_inspect_doc_unit_coverage_counts_subfigures_once(tmp_path):
    """一张大图拆多个子图块：同页同编号只算一个单元；碎片/无图注不算单元。"""
    doc = DoclensDoc(
        doc_id="y" * 12,
        sha256="y" * 64,
        blocks=[
            Block(type="image", page=1, content="", caption="Fig. 3 | main caption", image_path="images/a.jpg", order=0),
            Block(type="image", page=1, content="", caption=None, image_path="images/b.jpg", order=1),
            Block(type="image", page=1, content="", caption="Fig. 3 | main caption", image_path="images/c.jpg", order=2),
            Block(type="image", page=1, content="", caption="a. panel label", image_path="images/d.jpg", order=3),
            Block(type="image", page=2, content="", caption=None, image_path="images/e.jpg", order=4),
        ],
    )
    (tmp_path / "images").mkdir()
    for f in ("a.jpg", "b.jpg", "c.jpg", "d.jpg", "e.jpg"):
        (tmp_path / "images" / f).write_bytes(b"x")
    r = inspect_doc(doc, tmp_path)
    assert r["n_units"] == 1 and r["n_units_covered"] == 1  # 只有 Fig. 3 一个编号单元
    assert r["n_no_caption"] == 2
