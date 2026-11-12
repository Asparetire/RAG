"""M4 资产路径安全单测（m4-runbook K8①/R10①：路径穿越守卫）。"""

from __future__ import annotations

from pathlib import Path

from doclens.serve import assets


def _mk_pdf(root: Path, doc_id: str) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    p = root / f"{doc_id}.pdf"
    p.write_bytes(b"%PDF-1.4 test")
    return p


def test_resolve_pdf_valid(monkeypatch, tmp_path):
    monkeypatch.setattr(assets, "PDF_DIR", tmp_path)
    _mk_pdf(tmp_path, "abc123456789")
    got = assets.resolve_pdf("abc123456789")
    assert got is not None and got.name == "abc123456789.pdf"


def test_resolve_pdf_rejects_traversal(monkeypatch, tmp_path):
    monkeypatch.setattr(assets, "PDF_DIR", tmp_path)
    # 非法 doc_id（点/斜杠/大写/长度不对）一律 None，绝不落盘拼接
    for bad in ["../etc", "abc12345678/../..", "ABC123456789", "abc1234567890", "",
                "abc123456789%00", "abc123456789/../../secret"]:
        assert assets.resolve_pdf(bad) is None


def test_resolve_pdf_rejects_missing_file(monkeypatch, tmp_path):
    monkeypatch.setattr(assets, "PDF_DIR", tmp_path)
    assert assets.resolve_pdf("abc123456789") is None


def test_resolve_figure_rejects_bad_chunk_id(monkeypatch, tmp_path):
    monkeypatch.setattr(assets, "_fetch_members", lambda ids: {})
    for bad in ["../x", "zzz", "abc123456789:12", "abc123456789:00012",
                "ABC123456789:0001", "", "abc123456789:0001/../../x"]:
        assert assets.resolve_figure(bad) is None


def test_resolve_figure_no_image(monkeypatch, tmp_path):
    monkeypatch.setattr(assets, "_fetch_members", lambda ids: {"abc123456789:0001": {}})
    assert assets.resolve_figure("abc123456789:0001") is None


def test_resolve_figure_containment(monkeypatch, tmp_path):
    """image_path 指向 data/ 之外 → 包含性校验拦下。"""
    chunk = "abc123456789:0001"
    monkeypatch.setattr(assets, "_fetch_members", lambda ids: {chunk: {"image_path": "parsed/x.png"}})
    # PARSED_DIR.parent 指到 tmp 里一个假 data/，但解析出的路径在其外
    outside = tmp_path / "outside"
    outside.mkdir()
    monkeypatch.setattr(assets, "PARSED_DIR", tmp_path / "data" / "parsed")
    monkeypatch.setattr(assets, "PROJECT_ROOT", tmp_path / "elsewhere")
    assert assets.resolve_figure(chunk) is None


def test_sanitize_error_masks_keys():
    from doclens.serve.api import _sanitize_error
    msg = "api_key=sk-abcdefgh1234567890 failed for token sk-ZZZZZZ1234567890xyz"
    out = _sanitize_error(msg)
    assert "sk-abcdefgh" not in out            # api_key= 形态整体打码
    assert "sk-ZZZZZZ1234567890" not in out    # sk- 形态保留前 6 位便于排查，主体打码
    assert "sk-ZZZZZZ***" in out
    assert "api_key=***" in out
