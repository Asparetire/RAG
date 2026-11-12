"""M4 SSE 契约测试（m4-runbook K10/4.2；M3↔M4 接口边界的自动化锁）。

断言对象 = m4-runbook §3.1 冻结契约（= 调研 §1.4 超集）：
  stage → sources(先于首 token) → stage(generate) → thinking(started)
  → reasoning×M + token×N → thinking(done) → citations → done
  → 异常路径：error 事件（message 脱敏）后关流。
管线用 mock 注入（不真调 LLM/库），只测事件序与 schema。
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from doclens.serve.api import create_app


async def _happy_pipeline(question, profile_name, *, on_event=None, **kw):
    """按冻结契约顺序发射全事件集的 mock 管线。"""
    assert on_event is not None and kw.get("stream_gen") is True

    def ev(event, **data):
        on_event({"event": event, "data": data})

    ev("stage", stage="retrieve", detail="三路召回+融合去重")
    ev("sources", sources=[{"n": 1, "chunk_id": "abc123456789:0001", "doc_id": "abc123456789",
                            "kind": "text", "page": 1, "snippet": "证据片段",
                            "image_path": None, "bbox": [0.1, 0.2, 0.3, 0.4]}],
       routes={"dense_text": [{"chunk_id": "abc123456789:0001", "score": 0.5, "rank": 1}]},
       profile=profile_name)
    ev("stage", stage="generate", detail="生成")
    ev("thinking", status="started")
    ev("reasoning", text="思考片段")
    ev("token", content="答案")
    ev("token", content=" [1]")
    ev("thinking", status="done", elapsed_ms=123.4)
    ev("citations", cited=[1], invalid=[])
    ev("done", finish_reason="stop", usage={"total_tokens": 10, "prompt_tokens": 5},
       timing={"retrieve_ms": 1.0}, trace_id="20260101000000-D-0000000000")
    return {"query_id": "20260101000000-D-0000000000", "answer": "答案 [1]"}


async def _boom_pipeline(question, profile_name, *, on_event=None, **kw):
    def ev(event, **data):
        on_event({"event": event, "data": data})

    ev("stage", stage="retrieve", detail="x")
    raise RuntimeError("boom api_key=sk-abcdefgh1234567890 secret")


def _parse_sse(lines):
    """SSE 文本帧 → [(event, data_dict)]；跳过 ping 注释行与空行。"""
    frames = []
    cur_event, cur_data = None, None
    for line in lines:
        if not line.strip() or line.startswith(":"):
            continue
        if line.startswith("event:"):
            cur_event = line[len("event:"):].strip()
        elif line.startswith("data:"):
            cur_data = line[len("data:"):].strip()
            frames.append((cur_event, json.loads(cur_data)))
            cur_event, cur_data = None, None
    return frames


@pytest.fixture()
def happy_client():
    app = create_app(pipeline=_happy_pipeline)
    return TestClient(app)


@pytest.fixture()
def boom_client():
    app = create_app(pipeline=_boom_pipeline)
    return TestClient(app)


def test_contract_event_order_and_schema(happy_client):
    with happy_client.stream("POST", "/api/query",
                             json={"question": "测试问题", "profile": "D"}) as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        frames = _parse_sse(resp.iter_lines())

    events = [e for e, _ in frames]
    assert events == ["stage", "sources", "stage", "thinking", "reasoning", "token",
                      "token", "thinking", "citations", "done"]

    by_name = {}
    for e, d in frames:
        by_name.setdefault(e, []).append(d)

    # sources 先于首个 token（R4），schema 关键字段齐
    src = by_name["sources"][0]
    assert src["sources"][0]["n"] == 1 and src["sources"][0]["bbox"] == [0.1, 0.2, 0.3, 0.4]
    assert "dense_text" in src["routes"] and src["profile"] == "D"

    # thinking 配对：started → done（带 elapsed_ms）
    assert by_name["thinking"][0]["status"] == "started"
    assert by_name["thinking"][1]["status"] == "done"
    assert by_name["thinking"][1]["elapsed_ms"] == 123.4

    # token 只透传 content
    assert all(set(t.keys()) == {"content"} for t in by_name["token"])

    # done 收尾：finish_reason/usage/timing/trace_id
    done = by_name["done"][0]
    assert done["finish_reason"] == "stop"
    assert done["usage"]["total_tokens"] == 10
    assert set(done.keys()) == {"finish_reason", "usage", "timing", "trace_id"}


def test_contract_error_event_sanitized(boom_client):
    with boom_client.stream("POST", "/api/query", json={"question": "x"}) as resp:
        frames = _parse_sse(resp.iter_lines())
    events = [e for e, _ in frames]
    assert events == ["stage", "error"]
    err = frames[-1][1]
    assert err["code"] == "RuntimeError"
    assert "sk-abcdefgh" not in err["message"]      # key 形态必须被打码
    assert "api_key=***" in err["message"]          # api_key= 整体打码（api_key 形态优先）


def test_query_validation(happy_client):
    r = happy_client.post("/api/query", json={"question": "   "})
    assert r.status_code == 422
    r = happy_client.post("/api/query", json={"question": "x", "profile": "Z"})
    assert r.status_code == 422
    r = happy_client.post("/api/query", json={"question": "长" * 501})
    assert r.status_code == 422


def test_health(happy_client):
    assert happy_client.get("/api/health").json() == {"ok": True}
