"""corpus_intake 单测：校验、sha256 文件级去重、清单产出（m1-runbook 1.0）。"""

import hashlib
import json

from scripts.corpus_intake import intake


def _fake_pdf(path, payload: bytes = b"%PDF-1.4 fake-body " + b"x" * 20480) -> bytes:
    path.write_bytes(payload)
    return payload


def test_intake_collect_dedup_and_skip(tmp_path):
    inbox = tmp_path / "inbox"
    out = tmp_path / "pdfs"
    manifest_path = tmp_path / "corpus_manifest.json"
    inbox.mkdir()

    payload = _fake_pdf(inbox / "a.pdf")
    _fake_pdf(inbox / "a_copy_renamed.pdf", payload)                 # 同内容改名 → sha256 应拦下
    (inbox / "not_pdf.pdf").write_bytes(b"garbage" + b"y" * 20480)   # 扩展名对但内容坏 → 校验拒绝
    (inbox / "tiny.pdf").write_bytes(b"%PDF-")                       # 太小 → 校验拒绝

    papers = intake(inbox, out, manifest_path)

    # 只收 1 篇，doc_id = sha256 前 12 位
    assert len(papers) == 1
    assert papers[0]["doc_id"] == hashlib.sha256(payload).hexdigest()[:12]
    assert papers[0]["status"] == "canonical"
    assert papers[0]["title"] is None and papers[0]["doi"] is None  # 解析后回填位

    # 落盘文件以 doc_id 命名
    assert (out / f"{papers[0]['doc_id']}.pdf").exists()

    # 清单：count=1，三条跳过原因各就各位
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["count"] == 1
    reasons = " | ".join(s["reason"] for s in manifest["skipped"])
    assert "sha256 重复" in reasons
    assert "%PDF-" in reasons
    assert "文件过小" in reasons


def test_intake_idempotent_rerun(tmp_path):
    """同一 inbox 跑两遍：第二遍全部判重跳过，落盘不重复。"""
    inbox = tmp_path / "inbox"
    out = tmp_path / "pdfs"
    manifest_path = tmp_path / "m.json"
    inbox.mkdir()
    _fake_pdf(inbox / "a.pdf")

    first = intake(inbox, out, manifest_path)
    second = intake(inbox, out, manifest_path)
    assert len(first) == 1
    assert second == []  # 幂等：重跑不新增
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["count"] == 1  # 合并语义：重跑不清空既有清单
