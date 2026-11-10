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
    assert r["empty_images"] == ["p2: 无 image_path", "p3: 文件缺失 images/gone.jpg"]
