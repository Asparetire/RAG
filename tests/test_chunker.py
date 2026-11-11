"""chunker 单测（m2-runbook 2.1；K1 节内聚合 + 内容过滤）。

合成夹具直接构造 DoclensDoc（聚合/过滤为纯逻辑），覆盖：
同节聚合、超限句切、单句硬切、跨节不合并、References 过滤、页眉页脚跨页重复判定（R1）、
表格/图注/图像单元产出、chunk_id 序号与 content_hash 稳定性、短节独立成块。
"""
import hashlib

from doclens.index.chunker import CHUNK_MAX, Chunk, chunk_doc
from doclens.parse.schema import Block, DoclensDoc

DOC = DoclensDoc(doc_id="abc123def456", sha256="a" * 64, title="t")


def blk(type_: str, content: str, page: int = 1, hp: list[str] | None = None,
        bbox: list[float] | None = None, caption: str | None = None,
        image_path: str | None = None, order: int = 0) -> Block:
    return Block(type=type_, page=page, content=content, bbox=bbox, caption=caption,
                 image_path=image_path, heading_path=hp or [], order=order)


def kinds(chunks: list[Chunk]) -> list[str]:
    return [c.kind for c in chunks]


# ---- 聚合 ----


def test_same_section_adjacent_blocks_merge():
    doc = DOC
    doc.blocks = [
        blk("title", "3. Experiments", hp=[]),
        blk("text", "First paragraph.", hp=["3. Experiments"]),
        blk("text", "Second paragraph.", hp=["3. Experiments"]),
        blk("text", "Third paragraph.", hp=["3. Experiments"]),
    ]
    cs = chunk_doc(doc)
    assert kinds(cs) == ["text"]
    assert cs[0].content == "3. Experiments\nFirst paragraph.\nSecond paragraph.\nThird paragraph."
    assert cs[0].heading_path == ["3. Experiments"]
    assert cs[0].page == 1


def test_short_section_stays_single_chunk():
    """宁短勿跨节：150 字符短节独立成块，不与下一节合并。"""
    doc = DOC
    doc.blocks = [
        blk("text", "A" * 150, page=1, hp=["S1"]),
        blk("text", "B" * 150, page=2, hp=["S2"]),
    ]
    cs = chunk_doc(doc)
    assert kinds(cs) == ["text", "text"]
    assert cs[0].content.startswith("S1\n") and cs[1].content.startswith("S2\n")


def test_non_adjacent_text_blocks_do_not_merge():
    """同节但中间隔表格 → 断组（表格是强语义边界）。"""
    doc = DOC
    doc.blocks = [
        blk("text", "Before table.", hp=["S"]),
        blk("table", "| a | b |", hp=["S"]),
        blk("text", "After table.", hp=["S"]),
    ]
    cs = chunk_doc(doc)
    assert kinds(cs) == ["text", "table", "text"]


# ---- 超限切分 ----


def test_long_section_split_by_sentences():
    """>1600 字符同节 → 句级贪心切分，块间不跨节、句子完整。"""
    s1 = "Alpha " + "x" * 800 + "."
    s2 = "Beta " + "y" * 800 + "."
    doc = DOC
    doc.blocks = [blk("text", f"{s1} {s2}", hp=["S"])]
    cs = chunk_doc(doc)
    assert len(cs) >= 2
    bodies = [c.content.split("\n", 1)[1] for c in cs]
    assert all(len(b) <= CHUNK_MAX for b in bodies)
    assert any("Alpha" in b for b in bodies) and any("Beta" in b for b in bodies)


def test_oversized_single_sentence_hard_split():
    """单句 3000 字符无句读 → 硬切，每片 ≤1600。"""
    doc = DOC
    doc.blocks = [blk("text", "w" * 3000, hp=["S"])]
    cs = chunk_doc(doc)
    assert len(cs) == 2
    for c in cs:
        body = c.content.split("\n", 1)[1]
        assert len(body) <= CHUNK_MAX


def test_heading_prefix_not_counted_in_budget():
    """前缀不占 1600 预算：500 字符正文 + 2000 字符前缀仍单块。"""
    doc = DOC
    hp = ["L" * 1000, "R" * 1000]
    doc.blocks = [blk("text", "z" * 500, hp=hp)]
    cs = chunk_doc(doc)
    assert len(cs) == 1
    assert cs[0].content == "L" * 1000 + " / " + "R" * 1000 + "\n" + "z" * 500


# ---- 内容过滤 ----


def test_references_section_skipped():
    doc = DOC
    doc.blocks = [
        blk("text", "Body text.", hp=["4. Results"]),
        blk("text", "Smith J. Paper title. 2023.", hp=["References"]),
        blk("text", "Doe A. Another. 2024.", hp=["Bibliography"]),
    ]
    cs = chunk_doc(doc)
    assert kinds(cs) == ["text"]
    assert cs[0].content.endswith("Body text.")


def test_numbered_references_heading_skipped():
    """m-4：编号型 References 标题（"4. References"/"5 参考文献"）同样过滤，不漏进 BM25。"""
    doc = DOC
    doc.blocks = [
        blk("text", "Body text.", hp=["3. Methods"]),
        blk("text", "Smith J. Paper title. 2023.", hp=["4. References"]),
        blk("text", "Doe A. Another. 2024.", hp=["5 参考文献"]),
    ]
    cs = chunk_doc(doc)
    assert kinds(cs) == ["text"]
    assert cs[0].content.endswith("Body text.")


def test_running_head_repeated_dropped_single_kept():
    """R1：无归属短块跨页重复 ≥2 次丢弃；单次出现保留；有归属不判页眉页脚。"""
    doc = DOC
    doc.blocks = [
        blk("text", "Article", page=1, hp=[]),   # 重复第 1 次
        blk("text", "Article", page=2, hp=[]),   # 重复第 2 次 → 丢弃
        blk("text", "Article", page=3, hp=[]),   # 重复第 3 次 → 丢弃
        blk("text", "Received: 1 Jan 2024", page=1, hp=[]),  # 单次 → 保留
        blk("text", "Article", page=4, hp=["S"]),  # 有归属 → 保留
    ]
    cs = chunk_doc(doc)
    contents = [c.content for c in cs if c.kind == "text"]
    assert any("Received" in c for c in contents)
    assert any(c.endswith("Article") and c.startswith("S") for c in contents)
    bare = [c for c in cs if c.content == "Article"]
    assert not bare


# ---- 表格 / 图注 / 图像单元 ----


def test_table_chunk_keeps_content_with_prefix():
    doc = DOC
    doc.blocks = [blk("table", "【表注】T1\n\n| a | b |", page=2, hp=["3. R", "3.1 D"],
                      bbox=[0.1, 0.2, 0.8, 0.4])]
    cs = chunk_doc(doc)
    assert kinds(cs) == ["table"]
    assert cs[0].content == "3. R / 3.1 D\n【表注】T1\n\n| a | b |"
    assert cs[0].page == 2 and cs[0].bbox == [0.1, 0.2, 0.8, 0.4]


def test_image_with_caption_emits_caption_plus_image_units():
    doc = DOC
    doc.blocks = [blk("image", "", page=3, hp=["S"], caption="Fig. 1 | Accuracy curve.",
                      image_path="images/page_3_image_1.jpg")]
    cs = chunk_doc(doc)
    assert kinds(cs) == ["caption", "image"]
    assert "Fig. 1 | Accuracy curve." in cs[0].content
    assert cs[0].image_path == "images/page_3_image_1.jpg"
    assert cs[1].content == "Fig. 1 | Accuracy curve."  # image 单元 content=caption（供图像集合 payload）


def test_image_without_caption_emits_image_only():
    """无图注图仅图像单元（M3DocRAG 先例，调研 R5）。"""
    doc = DOC
    doc.blocks = [blk("image", "", page=5, hp=[], image_path="images/page_5_image_2.jpg")]
    cs = chunk_doc(doc)
    assert kinds(cs) == ["image"]
    assert cs[0].content == "" and cs[0].caption is None
    assert cs[0].image_path == "images/page_5_image_2.jpg"


def test_image_bare_and_pathless_skipped():
    """m-8：无图注且无 image_path 的空图单元直接跳过不 emit（否则 t_chunk 空行与 Qdrant 点数对不齐）。"""
    doc = DOC
    doc.blocks = [
        blk("image", "", page=3, hp=["S"], caption="Fig. 1 | 有图注无路径。"),
        blk("image", "", page=4, hp=["S"]),  # 双无 → 跳过，不占 chunk_id 序号
    ]
    cs = chunk_doc(doc)
    assert kinds(cs) == ["caption", "image"]  # 仅第 1 图的双路单元
    assert cs[0].image_path is None and cs[1].image_path is None
    assert [c.chunk_id for c in cs] == ["abc123def456:0000", "abc123def456:0001"]


# ---- 标识与哈希 ----


def test_chunk_id_sequence_and_hash_stable():
    doc = DOC
    doc.blocks = [
        blk("text", "a", hp=["S"]),
        blk("table", "| x |", hp=["S"]),
        blk("image", "", page=2, hp=["S"], caption="Fig. 2 | c.", image_path="i.jpg"),
    ]
    cs = chunk_doc(doc)
    assert [c.chunk_id for c in cs] == ["abc123def456:0000", "abc123def456:0001", "abc123def456:0002",
                                        "abc123def456:0003"]
    for c in cs:
        assert c.content_hash == hashlib.sha256(c.content.encode("utf-8")).hexdigest()
    # 幂等：同一文档重跑结果全等
    again = chunk_doc(doc)
    assert [(c.chunk_id, c.content, c.kind) for c in again] == [(c.chunk_id, c.content, c.kind) for c in cs]
