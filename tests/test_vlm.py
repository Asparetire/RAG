"""vlm 单测（m3-runbook §3.4 K5/R9）：monkeypatch 流式/非流式响应，不连 API。

断言核心：reasoning_content 只进 trace 绝不混答案、usage 取末 chunk、TTFT 只计首 content。
"""
import asyncio
from types import SimpleNamespace

from doclens.config import settings
from doclens.generate import vlm
from doclens.generate.context import assemble


def _ctx(with_image=False):
    ms = {"c1": {"chunk_id": "c1", "doc_id": "d", "kind": "text", "page": 1,
                 "content": "正文", "image_path": None, "caption": None,
                 "bbox": None, "heading_path": None}}
    ranked = ["c1"]
    if with_image:
        ms["cap"] = {"chunk_id": "cap", "doc_id": "d", "kind": "caption", "page": 2,
                     "content": "Fig.1", "image_path": "images/f.jpg", "caption": None,
                     "bbox": None, "heading_path": None}
        ms["img"] = {"chunk_id": "img", "doc_id": "d", "kind": "image", "page": 2,
                     "content": "", "image_path": "images/f.jpg", "caption": "Fig.1",
                     "bbox": None, "heading_path": None}
        ranked = ["c1", "cap", "img"]
    return assemble("问题", ranked, ms)


def _chunk(content=None, reasoning=None, usage=None):
    return SimpleNamespace(
        choices=[SimpleNamespace(delta=SimpleNamespace(content=content,
                                                       reasoning_content=reasoning))],
        usage=usage,
    )


class FakeCompletions:
    """记录调用参数的假 chat.completions；stream 返回异步迭代器，非流式返回固定响应。"""

    def __init__(self, chunks=None, response=None):
        self.chunks = chunks or []
        self.response = response
        self.calls: list[dict] = []

    async def create(self, **kw):
        self.calls.append(kw)
        if self.response is not None:
            return self.response
        async def _agen():
            for c in self.chunks:
                yield c
        return _agen()


def _patch(monkeypatch, comp):
    monkeypatch.setattr(vlm, "AsyncOpenAI",
                        lambda **kw: SimpleNamespace(chat=SimpleNamespace(completions=comp)))


def test_stream_reasoning_never_enters_answer(monkeypatch):
    usage_final = SimpleNamespace(prompt_tokens=111, total_tokens=222)
    chunks = [
        _chunk(reasoning="思考A"),
        _chunk(reasoning="思考B"),
        _chunk(content="答案[1]。"),
        _chunk(reasoning="迟到的思考"),      # 证明分流与分片顺序无关
        _chunk(content="补句[1]"),
        SimpleNamespace(choices=[], usage=usage_final),  # 末 chunk 仅 usage、choices 为空
    ]
    comp = FakeCompletions(chunks=chunks)
    _patch(monkeypatch, comp)

    res = asyncio.run(vlm.generate_answer("问题", _ctx(), stream=True))

    assert res.answer == "答案[1]。补句[1]"                 # 纯 content 拼接
    assert res.reasoning_chars == len("思考A思考B迟到的思考")
    assert res.reasoning_text_head == "思考A思考B迟到的思考"  # ≤200 字符，仅 trace
    assert res.usage_tokens == 222 and res.prompt_tokens == 111  # usage 取末 chunk
    assert res.ttft_ms is not None and res.ttft_ms >= 0
    assert res.model == settings.gen_model
    assert res.total_ms >= res.ttft_ms
    # 调用参数：stream=True、固定 system 三要素、user content 为多模态数组
    kw = comp.calls[0]
    assert kw["stream"] is True and kw["model"] == settings.gen_model
    assert kw["max_tokens"] == 2048
    sys_text = kw["messages"][0]["content"]
    assert "只依据所给 Source" in sys_text and "行内标注形如 [1]" in sys_text
    assert "相同的语言" in sys_text
    assert kw["messages"][1]["content"][0]["type"] == "text"
    assert "Source 1" in kw["messages"][1]["content"][0]["text"]


def test_nonstream_content_only_and_reasoning_to_trace(monkeypatch):
    msg = SimpleNamespace(content="依据[1]作答。", reasoning_content="内心独白")
    resp = SimpleNamespace(
        choices=[SimpleNamespace(message=msg)],
        usage=SimpleNamespace(prompt_tokens=10, total_tokens=99),
    )
    comp = FakeCompletions(response=resp)
    _patch(monkeypatch, comp)

    res = asyncio.run(vlm.generate_answer("问题", _ctx(), stream=False))

    assert res.answer == "依据[1]作答。"          # 答案=message.content
    assert res.reasoning_chars == len("内心独白")  # reasoning_content 只进统计
    assert res.ttft_ms is None                    # 非流式无 TTFT
    assert res.usage_tokens == 99 and res.prompt_tokens == 10
    kw = comp.calls[0]
    assert "stream" not in kw                     # 非流式分支不带 stream 参数
    assert kw["messages"][0]["content"].startswith("你是文档问答助手")


def test_image_blobs_become_data_urls(monkeypatch):
    comp = FakeCompletions(response=SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="看图[2]。"))], usage=None))
    _patch(monkeypatch, comp)

    res = asyncio.run(vlm.generate_answer(
        "问题", _ctx(with_image=True), image_blobs={"images/f.jpg": b"\xff\xd8\xffJFIF"}))

    assert res.answer == "看图[2]。"
    parts = comp.calls[0]["messages"][1]["content"]
    img_parts = [p for p in parts if p["type"] == "image_url"]
    assert len(img_parts) == 1
    assert img_parts[0]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    assert "Source 2" in parts[0]["text"]


def test_png_suffix_and_missing_blob_skipped(monkeypatch):
    """png 后缀 → image/png；未传 bytes 的图不生成 image part（读文件归 3.5 CLI）。"""
    comp = FakeCompletions(response=SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="答[2]。"))], usage=None))
    _patch(monkeypatch, comp)

    ms = {"cap": {"chunk_id": "cap", "doc_id": "d", "kind": "caption", "page": 2,
                  "content": "Fig.1", "image_path": "images/a.png", "caption": None,
                  "bbox": None, "heading_path": None},
          "img": {"chunk_id": "img", "doc_id": "d", "kind": "image", "page": 2,
                  "content": "", "image_path": "images/a.png", "caption": "Fig.1",
                  "bbox": None, "heading_path": None}}
    ctx = assemble("问题", ["cap", "img"], ms)
    asyncio.run(vlm.generate_answer("问题", ctx, image_blobs={}))  # 空 blobs → 无图片 part
    parts = comp.calls[0]["messages"][1]["content"]
    assert all(p["type"] != "image_url" for p in parts)

    asyncio.run(vlm.generate_answer("问题", ctx, image_blobs={"images/a.png": b"\x89PNG"}))
    parts2 = comp.calls[1]["messages"][1]["content"]
    assert parts2[1]["image_url"]["url"].startswith("data:image/png;base64,")
