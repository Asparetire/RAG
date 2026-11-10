"""M0 冒烟六连测（runbook §0.4）。

六项测试，每项打印结果 + 耗时（供 reports/cost.md 成本表）：
  1. MySQL 连通      —— pymysql 连 MYSQL_URL，SELECT 1
  2. Qdrant 连通     —— QdrantClient(url, api_key).get_collections()
  3. 文本嵌入        —— POST {ARK_EMBED_BASE_URL}/embeddings/multimodal，text + Query 侧 instructions
  4. 图像嵌入        —— 同端点，data:image/png;base64 单图 + Corpus 侧 instructions
  5. LLM 重排        —— deepseek-v4-flash 列表式：1 query + 5 编号候选块，温度 0
  6. VLM 生成        —— doubao-seed-2-1-pro 带图 chat + stream=True

探测与回填（M0 决策点①）：ARK_EMBED_BASE_URL 为空时先探 coding/v3，再探 api/v3；
探通的端点自动写回 `.env`（其余行原样保留）。

用法：容器/本地任一端，conda activate doclens 后 `python scripts/smoke_test.py`。
"""

import base64
import re
import sys
import time
from pathlib import Path

import httpx

# 便于 `python scripts/smoke_test.py` 直接运行：把仓库根加入 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from doclens.config import (  # noqa: E402
    PROJECT_ROOT,
    QUERY_INSTRUCTION,
    CORPUS_IMAGE_INSTRUCTION,
    CORPUS_TEXT_INSTRUCTION,
    settings,
)

EMBED_TIMEOUT = 30
LLM_TIMEOUT = 60


def timed(label: str, fn):
    """跑一项测试，打印结果与耗时；失败只打印不中断（六项都要跑完）。"""
    print(f"\n===== [{label}] =====")
    start = time.perf_counter()
    try:
        detail = fn()
        elapsed = time.perf_counter() - start
        print(f"✅ PASS  {label}  耗时 {elapsed:.2f}s")
        if detail:
            print(detail)
        return True, elapsed
    except Exception as exc:  # noqa: BLE001 —— 冒烟脚本要六项全跑完再汇总
        elapsed = time.perf_counter() - start
        print(f"❌ FAIL  {label}  耗时 {elapsed:.2f}s")
        print(f"   {type(exc).__name__}: {exc}")
        return False, elapsed


# ---------- 测试 1：MySQL ----------
def test_mysql():
    import pymysql

    url = settings.mysql_url
    m = re.match(r"mysql\+pymysql://(?P<user>[^:@]+)(?::(?P<pwd>[^@]+))?@(?P<host>[^:/]+):(?P<port>\d+)/(?P<db>\w+)", url)
    if not m:
        raise ValueError(f"MYSQL_URL 无法解析: {url}")
    conn = pymysql.connect(
        host=m.group("host"),
        port=int(m.group("port")),
        user=m.group("user"),
        password=m.group("pwd") or "",
        database=m.group("db"),
        connect_timeout=5,
    )
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            row = cur.fetchone()
        assert row and row[0] == 1, "SELECT 1 未返回 1"
        return f"MySQL {m.group('host')}:{m.group('port')}/{m.group('db')} SELECT 1 = 1"
    finally:
        conn.close()


# ---------- 测试 2：Qdrant ----------
def test_qdrant():
    from qdrant_client import QdrantClient

    client = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key or None, timeout=10)
    try:
        collections = client.get_collections()
        return f"Qdrant {settings.qdrant_url} 集合列表: {collections.collections}"
    finally:
        client.close()


# ---------- 嵌入端点探测（决策点①） ----------
def _embed_base_candidates() -> list[str]:
    """先试 .env 已回填值，再依次探 coding/v3 → api/v3。"""
    coding = settings.ark_base_url.rstrip("/")
    api = coding.replace("/api/coding/v3", "/api/v3")
    candidates: list[str] = []
    if settings.ark_embed_base_url:
        candidates.append(settings.ark_embed_base_url.rstrip("/"))
    candidates.extend([b for b in (coding, api) if b not in candidates])
    return candidates


def _post_embedding(items: list[dict]) -> dict:
    """对当前候选端点依次 POST /embeddings/multimodal，返回首个成功响应。"""
    last_error: Exception | None = None
    for base in _embed_base_candidates():
        url = f"{base}/embeddings/multimodal"
        try:
            resp = httpx.post(
                url,
                headers={"Authorization": f"Bearer {settings.ark_api_key}"},
                json={"model": settings.embed_model, "input": items},
                timeout=EMBED_TIMEOUT,
            )
        except httpx.HTTPError as exc:
            last_error = RuntimeError(f"{url} 网络异常: {exc}")
            continue
        if resp.status_code == 200:
            body = resp.json()
            print(f"   探测成功端点: {url}")
            _write_back_embed_base(base)
            return body
        print(f"   端点 {url} → HTTP {resp.status_code}: {resp.text[:300]}")
        last_error = RuntimeError(f"{url} → HTTP {resp.status_code}: {resp.text[:300]}")
    raise last_error or RuntimeError("无可用嵌入端点")


def _write_back_embed_base(base: str) -> None:
    """把探通的端点写回 .env 的 ARK_EMBED_BASE_URL 行（决策点①回填）。"""
    if settings.ark_embed_base_url.rstrip("/") == base:
        return
    env_path = PROJECT_ROOT / ".env"
    lines = env_path.read_text(encoding="utf-8").splitlines()
    pattern = re.compile(r"^ARK_EMBED_BASE_URL=.*$")
    replaced = False
    for i, line in enumerate(lines):
        if pattern.match(line):
            lines[i] = f"ARK_EMBED_BASE_URL={base}"
            replaced = True
    if not replaced:
        lines.append(f"ARK_EMBED_BASE_URL={base}")
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"   已回填 .env: ARK_EMBED_BASE_URL={base}")


# ---------- 测试 3：文本嵌入 ----------
def test_text_embedding():
    body = _post_embedding(
        [
            {
                "type": "text",
                "text": "DocLens 冒烟测试：什么是多模态检索增强生成？",
                "instructions": QUERY_INSTRUCTION,
            }
        ]
    )
    data = body["data"][0]["embedding"]
    assert len(data) == settings.embed_dimensions, f"维度 {len(data)} != {settings.embed_dimensions}"
    return f"文本嵌入维度 = {len(data)}（目标 {settings.embed_dimensions}）"


# ---------- 测试 4：图像嵌入 ----------
def _make_test_image_b64() -> str:
    """用 pillow 现场生成一张小测试图（不依赖外部素材）。"""
    import io

    from PIL import Image, ImageDraw

    img = Image.new("RGB", (256, 128), "white")
    draw = ImageDraw.Draw(img)
    draw.rectangle([16, 16, 240, 112], outline="black", width=4)
    draw.text((32, 56), "DocLens smoke test", fill="black")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def test_image_embedding():
    b64 = _make_test_image_b64()
    body = _post_embedding(
        [
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{b64}"},
                "instructions": CORPUS_IMAGE_INSTRUCTION,
            }
        ]
    )
    data = body["data"][0]["embedding"]
    assert len(data) == settings.embed_dimensions, f"维度 {len(data)} != {settings.embed_dimensions}"
    return f"图像嵌入维度 = {len(data)}"


# ---------- 测试 5：LLM 重排 ----------
def test_llm_rerank():
    from openai import OpenAI

    client = OpenAI(api_key=settings.ark_api_key, base_url=settings.ark_base_url)
    query = "DocLens 的检索流程中，重排的作用是什么？"
    candidates = [
        "1. 数据库连接池负责维持与 MySQL 的长连接。",
        "2. 重排器对召回的候选块按相关性精排，把最相关的块排到最前。",
        "3. Qdrant 是向量数据库，支持 HNSW 近似检索。",
        "4. BM25 是基于词频的经典关键词检索算法。",
        "5. MinerU 将 PDF 解析为结构化的内容清单。",
    ]
    prompt = (
        "你是检索重排器。根据与 Query 的相关性对候选块排序，"
        "只输出从最相关到最相关的编号序列，形如 [2,1,...]，不要解释。\n\n"
        f"Query: {query}\n\n候选块:\n" + "\n".join(candidates)
    )
    resp = client.chat.completions.create(
        model=settings.rerank_model_flash,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        max_tokens=64,
        timeout=LLM_TIMEOUT,
    )
    answer = resp.choices[0].message.content or ""
    assert re.search(r"\d", answer), f"重排输出无编号序列: {answer!r}"
    return f"重排模型返回: {answer.strip()[:80]}"


# ---------- 测试 6：VLM 带图流式生成 ----------
def test_vlm_stream():
    from openai import OpenAI

    client = OpenAI(api_key=settings.ark_api_key, base_url=settings.ark_base_url)
    b64 = _make_test_image_b64()
    chunks: list[str] = []
    stream = client.chat.completions.create(
        model=settings.gen_model,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                    {"type": "text", "text": "用一句话描述这张图。"},
                ],
            }
        ],
        stream=True,
        max_tokens=128,
        timeout=LLM_TIMEOUT,
    )
    for chunk in stream:
        delta = chunk.choices[0].delta.content if chunk.choices else None
        if delta:
            chunks.append(delta)
    text = "".join(chunks).strip()
    assert text, "VLM 流式输出为空"
    return f"VLM 流式响应 {len(chunks)} 个 chunk: {text[:80]}"


def main() -> int:
    print("DocLens M0 冒烟六连测（runbook §0.4）")
    if not settings.ark_api_key:
        print("⚠️  .env 里 ARK_API_KEY 为空——第 3~6 项（火山方舟）将失败，属预期。")

    results = [
        timed("1 MySQL 连通", test_mysql),
        timed("2 Qdrant 连通", test_qdrant),
        timed("3 文本嵌入", test_text_embedding),
        timed("4 图像嵌入", test_image_embedding),
        timed("5 LLM 重排", test_llm_rerank),
        timed("6 VLM 生成", test_vlm_stream),
    ]

    passed = sum(1 for ok, _ in results if ok)
    print("\n========== 汇总 ==========")
    print(f"通过 {passed}/6")
    for i, (ok, elapsed) in enumerate(results, 1):
        print(f"  测试{i}: {'✅' if ok else '❌'}  {elapsed:.2f}s")
    print("==========================")
    print("全绿标准：6/6。ARK_EMBED_BASE_URL 已回填则决策点①完成。")
    return 0 if passed == 6 else 1


if __name__ == "__main__":
    sys.exit(main())
