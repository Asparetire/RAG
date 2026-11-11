"""context 单测（m3-runbook §3.4 K4）：Source N 连续性、图文交错、选图限额、E 档前缀、truncated。

纯逻辑测试：不连库、不读文件（原图读取归 3.5 CLI）。
"""
from doclens.generate.context import ImageRef, assemble, to_prompt_parts


def mk(cid, *, kind="text", page=1, doc="docA", content="", image_path=None,
       caption=None, bbox=None, heading=None):
    """构造一条 members 成员（字段名对齐 3.1 hybrid 检索命中 + t_chunk 回表）。"""
    return {"chunk_id": cid, "doc_id": doc, "kind": kind, "page": page,
            "content": content, "image_path": image_path, "caption": caption,
            "bbox": bbox, "heading_path": heading, "score": 0.9, "rank": 0}


def members(*chunks):
    return {c["chunk_id"]: c for c in chunks}


def test_source_n_continuity_and_truncated():
    ms = members(*[mk(f"c{i}", content=f"正文{i}") for i in range(1, 26)])
    ranked = [f"c{i}" for i in range(1, 26)]
    ctx = assemble("Q", ranked, ms)
    assert ctx.truncated is True                      # 25 > final_top(20)
    assert [s.source_n for s in ctx.sources] == list(range(1, 21))  # 编号从 1 连续
    assert ctx.sources[0].chunk_id == "c1"            # 保持 ranking 原序
    assert ctx.sources[19].content == "正文20"
    # 不超上限 → 不截断
    ctx2 = assemble("Q", ["c1", "c2"], {k: ms[k] for k in ("c1", "c2")})
    assert ctx2.truncated is False and len(ctx2.sources) == 2


def test_caption_image_interleave_same_source():
    """R12：caption 与原图同 Source——image 块被 caption 吸收，不单独占编号。"""
    ms = members(
        mk("t1", content="文本一"),
        mk("cap", kind="caption", content="Fig.1 准确率曲线", image_path="images/f1.jpg", page=3),
        mk("img", kind="image", content="", image_path="images/f1.jpg",
           caption="Fig.1 准确率曲线", page=3),
        mk("t2", content="文本二"),
    )
    ctx = assemble("Q", ["t1", "cap", "img", "t2"], ms)
    assert [s.chunk_id for s in ctx.sources] == ["t1", "cap", "t2"]  # img 不单独占 Source
    assert [s.source_n for s in ctx.sources] == [1, 2, 3]
    assert ctx.images == [ImageRef(source_n=2, image_path="images/f1.jpg", doc_id="docA", page=3)]
    assert ctx.sources[1].content == "Fig.1 准确率曲线"


def test_image_without_caption_own_source():
    """image 块独立命中（caption 未入选）→ 自成一个 Source，caption 文本作正文。"""
    ms = members(
        mk("img", kind="image", content="", image_path="images/f2.jpg",
           caption="Fig.2 架构图", page=5),
        mk("t1", content="文本"),
    )
    ctx = assemble("Q", ["img", "t1"], ms)
    assert ctx.sources[0].chunk_id == "img" and ctx.sources[0].source_n == 1
    assert ctx.sources[0].content == "Fig.2 架构图"
    assert ctx.images[0].source_n == 1


def test_max_images_quota_keeps_caption_text():
    """FR-4.1 选图限额：超 max_images 的图不附原图，caption 文本保留。"""
    chunks, ranked = [], []
    for i in range(1, 7):
        chunks += [mk(f"cap{i}", kind="caption", content=f"图注{i}",
                      image_path=f"images/{i}.jpg", page=i),
                   mk(f"img{i}", kind="image", content="", image_path=f"images/{i}.jpg",
                      caption=f"图注{i}", page=i)]
        ranked += [f"cap{i}", f"img{i}"]
    ctx = assemble("Q", ranked, members(*chunks), max_images=2)
    assert len(ctx.images) == 2
    # 展示序先到先得（所属 Source 排序分最高者入选）：cap1=Source1、cap2=Source2
    assert [(im.source_n, im.image_path) for im in ctx.images] == [
        (1, "images/1.jpg"), (2, "images/2.jpg")]
    # 超额图：SourceBlock 仍在（caption 文本保留），仅原图不附
    assert ctx.sources[2].content == "图注3"
    assert ctx.sources[2].image_path == "images/3.jpg"
    assert all(im.image_path != "images/3.jpg" for im in ctx.images)


def test_ctx_prefix_e_tier():
    """E 档：use_ctx_prefix=True 时拼前缀（换行分隔）；无前缀块原样；关闭时不拼。"""
    ms = members(mk("c1", content="正文"), mk("c2", content="正文2"))
    ctx = assemble("Q", ["c1", "c2"], ms, use_ctx_prefix=True,
                   ctx_prefixes={"c1": "本块讨论方法A"})
    assert ctx.sources[0].content == "本块讨论方法A\n正文"
    assert ctx.sources[1].content == "正文2"
    ctx2 = assemble("Q", ["c1"], ms, use_ctx_prefix=False, ctx_prefixes={"c1": "X"})
    assert ctx2.sources[0].content == "正文"


def test_bbox_and_missing_member_tolerated():
    """bbox/heading_path 透传（JSON 列 str 也能解析）；members 缺失的块跳过。"""
    ms = members(
        mk("c1", content="正文", bbox=[0.1, 0.2, 0.3, 0.4], heading=["第3章", "实验"]),
        mk("c2", content="str格式", bbox="[0.5,0.6,0.7,0.8]"),
    )
    ctx = assemble("Q", ["c9", "c1", "c2"], ms)   # c9 不在 members → 跳过
    assert [s.chunk_id for s in ctx.sources] == ["c1", "c2"]
    assert ctx.sources[0].bbox == [0.1, 0.2, 0.3, 0.4]
    assert ctx.sources[0].heading_path == ["第3章", "实验"]
    assert ctx.sources[1].bbox == [0.5, 0.6, 0.7, 0.8]  # str JSON 列容错


def test_to_prompt_parts_text_and_images():
    ms = members(
        mk("t1", content="甲"),
        mk("cap", kind="caption", content="Fig.1", image_path="images/f.jpg", page=2),
        mk("img", kind="image", content="", image_path="images/f.jpg", page=2),
    )
    ctx = assemble("问题Q", ["t1", "cap", "img"], ms)
    parts = to_prompt_parts(ctx)
    assert parts[0]["type"] == "text"
    text = parts[0]["text"]
    assert "问题：问题Q" in text
    assert "Source 1: (docA, p1, text) 甲" in text
    assert "Source 2: (docA, p2, caption) Fig.1" in text
    assert len(parts) == 1                          # 未给 image_urls → 无图片 part
    parts2 = to_prompt_parts(ctx, image_urls={"images/f.jpg": "data:image/jpeg;base64,AAA"})
    assert len(parts2) == 2
    assert parts2[1] == {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,AAA"}}
