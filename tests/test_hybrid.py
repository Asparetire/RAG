"""hybrid 单测（m3-runbook 3.1）：融合器手算期望值 + 证据组归并 + retrieve 编排。

测试纪律（runbook §6）：全部纯逻辑/monkeypatch，不连真库不调 API——
Qdrant（FakeQdrant）/嵌入（FakeEmbed）/BM25（FakeBM25）/DB（patch fetch_chunk_meta 或 connect）全部注入桩。
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from doclens.config import Profile
from doclens.index.qdrant_store import IMAGE_COLLECTION, TEXT_COLLECTION
from doclens.retrieve import hybrid
from doclens.retrieve.hybrid import (
    FUSERS,
    ROUTE_BM25,
    ROUTE_DENSE_IMAGE,
    ROUTE_DENSE_TEXT,
    Hit,
    build_members_map,
    dedup_evidence_groups,
    fuse,
    fuse_dbsf,
    fuse_rrf,
    fuse_weighted_rrf,
    search_image,
)

# ---------- 构造帮手 ----------


def mk_hit(chunk_id, kind="text", score=0.0, doc_id="d1", page=1, image_path=None):
    return Hit(chunk_id=chunk_id, kind=kind, score=score, doc_id=doc_id, page=page,
               image_path=image_path)


def mm_of(*hits, **image_path_overrides):
    """构造 members_map：{chunk_id: {doc_id, page, kind, image_path}}（模拟回表/payload 双源）。"""
    out = {}
    for h in hits:
        out[h.chunk_id] = {"doc_id": h.doc_id, "page": h.page, "kind": h.kind,
                           "image_path": image_path_overrides.get(h.chunk_id, h.image_path)}
    return out


@dataclass
class FakePoint:
    """ScoredPoint 桩：hybrid 只用 .payload 与 .score。"""
    payload: dict
    score: float


class FakeQdrant:
    """query_points 桩：search_tier / search_image 都走 client.query_points，按集合返回预置点。"""

    def __init__(self, by_collection=None):
        self.by_collection = by_collection or {}
        self.calls = []
        self.closed = False

    def query_points(self, *args, **kw):
        collection = args[0] if args else kw["collection_name"]
        self.calls.append({"collection": collection, "limit": kw.get("limit"),
                           "filter": kw.get("query_filter"), "query": kw.get("query")})
        pts = [FakePoint(dict(p.payload), p.score) for p in self.by_collection.get(collection, [])]
        return SimpleNamespace(points=pts[: kw.get("limit", len(pts))])

    def close(self):
        self.closed = True


class FakeBM25:
    def __init__(self, pairs):
        self.pairs = pairs
        self.calls = []

    def search(self, query, top=20):
        self.calls.append((query, top))
        return list(self.pairs[:top])


class FakeEmbed:
    def __init__(self, vec):
        self.vec = vec
        self.calls = []

    async def embed_query(self, text):
        self.calls.append(text)
        return self.vec


class _BoomEmbed:
    """哨兵：任何路径构建嵌入客户端都直接失败（断言"不该走嵌入"用）。"""

    def __init__(self, *a, **k):
        raise AssertionError("不应构建嵌入客户端")


class _BoomMeta:
    """哨兵：任何路径触达 DB 回表都直接失败（断言"不该连库"用）。"""

    def __call__(self, *a, **k):
        raise AssertionError("不应回表 t_chunk")


def filter_kinds(fake_qdrant, collection):
    """取某集合查询的 kind 过滤值（search_tier 传入的 FieldCondition.match.any），无过滤返回 None。"""
    for c in fake_qdrant.calls:
        if c["collection"] == collection and c["filter"] is not None:
            for cond in c["filter"].must:
                if cond.key == "kind":
                    return list(cond.match.any)
    return None


# ---------- B 档场景（dense text 3 + dense image 1 + BM25 3 + 回表元数据） ----------
_TEXT_PTS = [
    FakePoint({"chunk_id": "tA", "doc_id": "d1", "kind": "text", "page": 1,
               "heading_path": ["1", "1.1"]}, 0.9),
    FakePoint({"chunk_id": "tB", "doc_id": "d1", "kind": "text", "page": 2, "heading_path": []}, 0.8),
    FakePoint({"chunk_id": "capC", "doc_id": "d1", "kind": "caption", "page": 3,
               "heading_path": []}, 0.7),
]
_IMAGE_PTS = [FakePoint({"chunk_id": "imgI", "doc_id": "d1", "image_path": "fig/x.png",
                         "caption": "架构图", "page": 4, "bbox": None}, 0.6)]
_BM25_PAIRS = [("tB", 9.0), ("tabT", 7.0), ("capC", 5.0)]
_DB_META = {
    "tA": {"doc_id": "d1", "kind": "text", "page": 1, "heading_path": ["1", "1.1"], "image_path": None},
    "tB": {"doc_id": "d1", "kind": "text", "page": 2, "heading_path": [], "image_path": None},
    "capC": {"doc_id": "d1", "kind": "caption", "page": 3, "heading_path": [],
             "image_path": "fig/x.png"},
    "tabT": {"doc_id": "d1", "kind": "table", "page": 5, "heading_path": [], "image_path": None},
}
_PROF_C = Profile("C", "测试档 C")  # 三路齐开：三类 text_kinds + use_image_route=True + BM25（默认值）
_PROF_A = Profile("A", "测试档 A", text_kinds=("text",), use_image_route=False)
_PROF_TEXT_ONLY = Profile("T", "仅文本路", text_kinds=("text",), use_image_route=False,
                          use_bm25=False)


def _b_qdrant():
    return FakeQdrant({TEXT_COLLECTION: _TEXT_PTS, IMAGE_COLLECTION: _IMAGE_PTS})


# ---------- 融合器：RRF（K1/R1，手算期望值） ----------

def _rrf_routes():
    return {
        "dense_text": [mk_hit("t1", score=0.9), mk_hit("t2", score=0.8), mk_hit("t3", score=0.7)],
        "bm25": [mk_hit("t2", score=12.0), mk_hit("t4", score=9.0), mk_hit("t5", score=4.0)],
    }


def test_fuse_rrf_hand_calculated():
    """两路各 3 项、t2 双路命中：k=2 全部贡献分与顺序手算核对。"""
    fused = fuse_rrf(_rrf_routes(), k=2)
    assert [h.chunk_id for h in fused] == ["t2", "t1", "t4", "t3", "t5"]
    # t2 = dense_text rank2 + bm25 rank1 = 1/4 + 1/3
    assert fused[0].score == pytest.approx(1 / 4 + 1 / 3)
    # t1 = 1/3；t4 = 1/4；t3/t5 = 1/5 并列 → 稳定序保持首见（dense_text 先于 bm25）
    assert fused[1].score == pytest.approx(1 / 3)
    assert fused[2].score == pytest.approx(1 / 4)
    assert fused[3].score == pytest.approx(1 / 5)
    assert fused[4].score == pytest.approx(1 / 5)
    # route_hits 完整记录 (rank, raw_score)，元数据取首见路
    assert fused[0].route_hits == {"dense_text": (2, 0.8), "bm25": (1, 12.0)}
    assert fused[1].route_hits == {"dense_text": (1, 0.9)}
    assert fused[0].kind == "text" and fused[0].doc_id == "d1"


def test_fuse_rrf_weight_zero_and_flip():
    """权重敏感性：w=0 的路贡献 0；加大权重可翻转名次（w 乘在分子）。"""
    fused = fuse_rrf(_rrf_routes(), k=2, weights={"bm25": 0.0})
    by = {h.chunk_id: h.score for h in fused}
    assert by["t2"] == pytest.approx(1 / 4)      # 只剩 dense_text 的贡献
    assert by["t4"] == 0.0 and by["t5"] == 0.0   # bm25 独有项 → 0

    routes = {"a": [mk_hit("x", score=1.0), mk_hit("y", score=0.9)],
              "b": [mk_hit("z", score=2.0), mk_hit("q", score=1.0)]}
    no_w = fuse_rrf(routes, k=2)
    assert no_w[0].chunk_id == "x"                       # x=1/3 最高（z 未加权仅 1/4）
    with_w = fuse_rrf(routes, k=2, weights={"b": 3.0})   # z rank1 = 3/(2+1) = 1.0 反超
    assert with_w[0].chunk_id == "z"
    assert with_w[0].score == pytest.approx(1.0)
    assert with_w[1].chunk_id == "q" and with_w[1].score == pytest.approx(3 / 4)  # b rank2


def test_fuse_rrf_k_sensitivity():
    """k 敏感性：k 只压缩名次差、不改序（本组构型下）；数值按 k=60 手算核对。"""
    f2, f60 = fuse_rrf(_rrf_routes(), k=2), fuse_rrf(_rrf_routes(), k=60)
    s2 = {h.chunk_id: h.score for h in f2}
    s60 = {h.chunk_id: h.score for h in f60}
    assert s60["t2"] == pytest.approx(1 / 62 + 1 / 61)
    assert s60["t1"] == pytest.approx(1 / 61)
    assert [h.chunk_id for h in f60] == [h.chunk_id for h in f2]
    assert s2["t2"] - s2["t1"] == pytest.approx(1 / 4)
    assert (s60["t2"] - s60["t1"]) < (s2["t2"] - s2["t1"])


# ---------- 融合器：weighted RRF（R4，Qdrant 官方公式） ----------

def test_fuse_weighted_rrf_qdrant_formula():
    """score = Σ 1/(k+rank/w)：w=2 的图像路 rank1 → 1/(2+1/2)=0.4 > 1/3。"""
    routes = {"dense_text": [mk_hit("t1", score=0.9)],
              "dense_image": [mk_hit("i1", kind="image", score=0.7)]}
    fused = fuse_weighted_rrf(routes, k=2, weights={"dense_image": 2.0})
    assert [h.chunk_id for h in fused] == ["i1", "t1"]
    assert fused[0].score == pytest.approx(1 / (2 + 1 / 2))
    assert fused[1].score == pytest.approx(1 / 3)
    # 降权 0.5：i1 = 1/(2+2) = 0.25 < 1/3 → 序翻转（M5 降权档的数学行为预演）
    down = fuse_weighted_rrf(routes, k=2, weights={"dense_image": 0.5})
    assert [h.chunk_id for h in down] == ["t1", "i1"]
    assert down[1].score == pytest.approx(0.25)


def test_fuse_weighted_rrf_equals_rrf_at_w1():
    """w=1 严格退化为 fuse_rrf（公式等价性）。"""
    rr = fuse_rrf(_rrf_routes(), k=2)
    wr = fuse_weighted_rrf(_rrf_routes(), k=2)
    assert [h.chunk_id for h in wr] == [h.chunk_id for h in rr]
    for a, b in zip(wr, rr):
        assert a.score == pytest.approx(b.score)


# ---------- 融合器：DBSF（R3/R19） ----------

_Z = 1.2247448713915892  # = 2/sqrt(8/3)：路 [4,2,0] 的首元素 z-score，手算


def test_fuse_dbsf_hand_calculated():
    """z-score 归一：均值/标准差取自该路本次结果集；std=0 的路贡献 0。"""
    routes = {"a": [mk_hit("a1", score=4.0), mk_hit("a2", score=2.0), mk_hit("a3", score=0.0)],
              "b": [mk_hit("b1", score=10.0), mk_hit("b2", score=10.0),
                    mk_hit("b3", score=10.0)]}
    fused = fuse_dbsf(routes)
    by = {h.chunk_id: h.score for h in fused}
    assert by["a1"] == pytest.approx(_Z)
    assert by["a2"] == pytest.approx(0.0)
    assert by["a3"] == pytest.approx(-_Z)          # DBSF 分可为负（无相似度语义，R1 坑②）
    assert by["b1"] == 0.0 and by["b2"] == 0.0 and by["b3"] == 0.0  # b 路 std=0 → 贡献 0
    ids = [h.chunk_id for h in fused]
    assert ids[0] == "a1" and ids[-1] == "a3"


def test_fuse_dbsf_std_zero_route_and_weight():
    """单元素路 std=0 → 贡献 0；weights 乘在 z 上。"""
    solo = fuse_dbsf({"solo": [mk_hit("s1", score=5.0)]})
    assert solo[0].score == 0.0

    routes = {"a": [mk_hit("a1", score=4.0), mk_hit("a2", score=2.0), mk_hit("a3", score=0.0)],
              "b": [mk_hit("b1", score=10.0)]}
    fused = fuse_dbsf(routes, weights={"a": 2.0})
    by = {h.chunk_id: h.score for h in fused}
    assert by["a1"] == pytest.approx(2 * _Z)
    assert by["b1"] == 0.0


# ---------- 融合器：分发入口 ----------

def test_fuse_dispatch_and_unknown_valueerror():
    routes = {"a": [mk_hit("x", score=1.0), mk_hit("y", score=0.5)]}
    assert set(FUSERS) == {"rrf", "weighted_rrf", "dbsf"}
    assert fuse(routes, "rrf", k=2)[0].score == pytest.approx(1 / 3)
    for name, fn in FUSERS.items():  # 分发与直接调用等价
        assert [h.chunk_id for h in fuse(routes, name)] == [h.chunk_id for h in fn(routes)]
    with pytest.raises(ValueError, match="未知融合器"):
        fuse(routes, "cosine_sum")


def test_fuse_empty_routes():
    """空路/空结果：返回空列表；混合时空路无贡献。"""
    for fn in (fuse_rrf, fuse_weighted_rrf, fuse_dbsf):
        assert fn({}, k=2) == []
        assert fn({"a": []}, k=2) == []
    mixed = fuse_rrf({"a": [], "b": [mk_hit("x", score=1.0)]}, k=2)
    assert [h.chunk_id for h in mixed] == ["x"]
    assert mixed[0].score == pytest.approx(1 / 3)


# ---------- 证据组去重（K1/R2） ----------

def test_dedup_same_doc_page_merged():
    """同 (doc,page) 归并：代表=最高分保原位；group_members 完整；单元素组=[自身]。"""
    hits = [mk_hit("x", score=0.6, doc_id="d1", page=1),
            mk_hit("y", score=0.5, doc_id="d2", page=1),
            mk_hit("z", score=0.45, doc_id="d1", page=1)]
    out = dedup_evidence_groups(hits, mm_of(*hits))
    assert [h.chunk_id for h in out] == ["x", "y"]
    assert out[0].group_members == ["x", "z"]
    assert out[1].group_members == ["y"]


def test_dedup_representative_is_highest_not_first():
    """代表按融合分选（不按先出现）：低分在前、高分在后 → 高分者当代表。"""
    hits = [mk_hit("z", score=0.45, doc_id="d1", page=1),
            mk_hit("x", score=0.6, doc_id="d1", page=1)]
    out = dedup_evidence_groups(hits, mm_of(*hits))
    assert [h.chunk_id for h in out] == ["x"]
    assert out[0].group_members == ["z", "x"]   # 成员按入参序（=融合序）


def test_dedup_figure_cross_page_transitive():
    """figure 跨 page 强制同组（caption 的 image_path 由回表 members_map 补）；
    经并查集传递，image 的同页 text 伙伴一并入组。"""
    cap = mk_hit("cap", kind="caption", score=0.5, doc_id="d1", page=3)      # payload 无 image_path
    img = mk_hit("img", kind="image", score=0.4, doc_id="d1", page=4, image_path="fig/x.png")
    txt = mk_hit("txt", score=0.3, doc_id="d1", page=4)
    out = dedup_evidence_groups([cap, img, txt], mm_of(cap, img, txt, cap="fig/x.png"))
    assert [h.chunk_id for h in out] == ["cap"]
    assert out[0].group_members == ["cap", "img", "txt"]


def test_dedup_figure_groups_stay_separate():
    """不同 image_path 的 figure 组互不沾染。"""
    cap1 = mk_hit("cap1", kind="caption", score=0.5, doc_id="d1", page=3)
    img1 = mk_hit("img1", kind="image", score=0.4, doc_id="d1", page=3)
    cap2 = mk_hit("cap2", kind="caption", score=0.3, doc_id="d1", page=7)
    img2 = mk_hit("img2", kind="image", score=0.2, doc_id="d1", page=7)
    out = dedup_evidence_groups([cap1, img1, cap2, img2],
                                mm_of(cap1, img1, cap2, img2,
                                      cap1="fig/a.png", img1="fig/a.png",
                                      cap2="fig/b.png", img2="fig/b.png"))
    assert [h.chunk_id for h in out] == ["cap1", "cap2"]
    assert out[0].group_members == ["cap1", "img1"]
    assert out[1].group_members == ["cap2", "img2"]


def test_dedup_relative_order_preserved():
    """组间相对序 = 代表在原序列中的相对序（吸收式去重，不重排）。"""
    hits = [mk_hit("g1", score=0.9, doc_id="d1", page=1),
            mk_hit("m1", score=0.85, doc_id="d1", page=1),
            mk_hit("g2", score=0.8, doc_id="d2", page=1),
            mk_hit("m2", score=0.7, doc_id="d2", page=1),
            mk_hit("g3", score=0.6, doc_id="d3", page=1)]
    out = dedup_evidence_groups(hits, mm_of(*hits))
    assert [h.chunk_id for h in out] == ["g1", "g2", "g3"]
    assert out[0].group_members == ["g1", "m1"]
    assert out[1].group_members == ["g2", "m2"]
    assert out[2].group_members == ["g3"]


def test_dedup_unknown_meta_not_merged():
    """doc_id 未知（members_map 与 Hit 都缺）→ 各自成组，宁可少去重不误合并。"""
    hits = [Hit("a", "text", 0.5), Hit("b", "text", 0.4)]
    out = dedup_evidence_groups(hits, {})
    assert [h.chunk_id for h in out] == ["a", "b"]
    assert out[0].group_members == ["a"]


# ---------- 帮助函数 ----------

def test_build_members_map_merge_priority():
    """payload 侧优先、回表补缺：caption 的 image_path 只能回表取；payload 覆写回表同字段。"""
    payload = {"c1": {"doc_id": "d1", "page": 1, "kind": "text", "image_path": None},
               "c3": {"doc_id": "d1", "page": 7, "kind": "caption", "image_path": None}}
    db = {"c1": {"doc_id": "d1", "page": 1, "kind": "text", "image_path": "fig/a.png",
                 "heading_path": ["1"]},
          "c2": {"doc_id": "d1", "page": 4, "kind": "image", "image_path": "fig/a.png"},
          "c3": {"doc_id": "d1", "page": 1, "kind": "caption", "image_path": "fig/b.png"}}
    mm = build_members_map(payload, db)
    assert set(mm) == {"c1", "c2", "c3"}
    assert mm["c1"]["image_path"] == "fig/a.png"   # 回表补缺
    assert mm["c2"]["kind"] == "image"             # 只在回表侧
    assert mm["c3"]["page"] == 7                   # payload 优先


def test_search_image_uses_image_collection():
    qdrant = FakeQdrant({IMAGE_COLLECTION: _IMAGE_PTS})
    pts = search_image(qdrant, [0.1, 0.2], top=7)
    assert len(pts) == 1 and pts[0].payload["chunk_id"] == "imgI"
    assert qdrant.calls[0]["collection"] == IMAGE_COLLECTION
    assert qdrant.calls[0]["limit"] == 7


def test_fetch_chunk_meta_parameterized_and_json(monkeypatch):
    """回表 SQL：参数化占位符与入参一一对应（S4 纪律）；JSON 列 str → list；脏 JSON 降级不炸。"""

    class FakeCursor:
        def __init__(self, rows):
            self.rows = rows
            self.executed = []

        def execute(self, sql, params):
            self.executed.append((sql, params))

        def fetchall(self):
            return self.rows

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    class FakeConn:
        def __init__(self, rows):
            self.cur = FakeCursor(rows)

        def cursor(self):
            return self.cur

        def close(self):
            pass

    rows = [("c1", "d1", "caption", 3, '["1", "1.1"]', "fig/a.png"),
            ("c2", "d1", "image", 4, None, "fig/a.png"),
            ("c3", "d1", "text", 5, "not-json", None)]
    conn = FakeConn(rows)
    monkeypatch.setattr(hybrid, "connect", lambda: conn)

    assert hybrid.fetch_chunk_meta([]) == {}  # 空入参不连库
    meta = hybrid.fetch_chunk_meta(["c1", "c2", "c3"])
    assert meta["c1"] == {"doc_id": "d1", "kind": "caption", "page": 3,
                          "heading_path": ["1", "1.1"], "image_path": "fig/a.png"}
    assert meta["c2"]["heading_path"] == []
    assert meta["c3"]["heading_path"] == []   # 脏 JSON 降级为空列表
    sql, params = conn.cur.executed[0]
    assert sql.count("%s") == 3 and params == ["c1", "c2", "c3"]
    assert "t_chunk" in sql


# ---------- retrieve 编排（monkeypatch 三路 + 回表） ----------

def test_retrieve_c_profile_full_pipeline(monkeypatch):
    """C 档全链路（三路齐开）：三路召回 → RRF 手算序 → figure 归并 → pool 截断；过滤/回表入参核对。"""
    qdrant = _b_qdrant()
    bm25 = FakeBM25(_BM25_PAIRS)
    fetched = []
    monkeypatch.setattr(hybrid, "EmbeddingClient", _BoomEmbed)  # qvec 注入，不该走嵌入
    monkeypatch.setattr(hybrid, "fetch_chunk_meta",
                        lambda ids: (fetched.append(list(ids)), _DB_META)[1])

    res = asyncio.run(hybrid.retrieve("问题", _PROF_C, qvec=[0.1, 0.2],
                                      client=qdrant, bm25_idx=bm25))

    assert res.question == "问题" and res.profile_name == "C"
    # 三路齐开，键序 = 编排序；回表一次性拿齐全部候选 id（fetched 按调用记录，ASCII 序）
    assert list(res.routes) == [ROUTE_DENSE_TEXT, ROUTE_DENSE_IMAGE, ROUTE_BM25]
    assert fetched == [["capC", "imgI", "tA", "tB", "tabT"]]
    # 档位映射：text_kinds 三类 → B 档 kind 过滤；image 路打到 image 集合
    assert filter_kinds(qdrant, TEXT_COLLECTION) == ["text", "table", "caption"]
    assert any(c["collection"] == IMAGE_COLLECTION and c["limit"] == 30 for c in qdrant.calls)
    # dense 路命中与 payload 透传
    assert [h.chunk_id for h in res.routes[ROUTE_DENSE_TEXT]] == ["tA", "tB", "capC"]
    assert res.routes[ROUTE_DENSE_TEXT][0].heading_path == ["1", "1.1"]
    assert res.routes[ROUTE_DENSE_IMAGE][0].kind == "image"
    assert res.routes[ROUTE_DENSE_IMAGE][0].image_path == "fig/x.png"
    # BM25 路保留全部三类 kind，元数据来自回表
    assert [h.chunk_id for h in res.routes[ROUTE_BM25]] == ["tB", "tabT", "capC"]
    assert [h.kind for h in res.routes[ROUTE_BM25]] == ["text", "table", "caption"]
    assert res.routes[ROUTE_BM25][0].doc_id == "d1" and res.routes[ROUTE_BM25][0].page == 2
    # 融合（k=2 手算）：tB=1/4+1/3 > capC=1/5+1/5 > tA=1/3=imgI（首见序）> tabT=1/4
    assert [h.chunk_id for h in res.fused] == ["tB", "capC", "tA", "imgI", "tabT"]
    assert res.fused[0].score == pytest.approx(1 / 4 + 1 / 3)
    assert res.fused[0].route_hits == {"dense_text": (2, 0.8), "bm25": (1, 9.0)}
    # 证据组归并：capC(p3)+imgI(p4) 按 image_path 跨页归并，代表 capC（0.4 > 1/3）
    assert [h.chunk_id for h in res.deduped] == ["tB", "capC", "tA", "tabT"]
    cap = [h for h in res.deduped if h.chunk_id == "capC"][0]
    assert cap.group_members == ["capC", "imgI"]
    # pool = deduped[:fused_pool=50]
    assert [h.chunk_id for h in res.pool] == ["tB", "capC", "tA", "tabT"]


def test_retrieve_a_profile_bm25_postfilter(monkeypatch):
    """A 档（text_kinds=("text",)）：① A 档 kind 过滤下发；② BM25 后过滤剔掉 table/caption。"""
    qdrant = FakeQdrant({TEXT_COLLECTION: _TEXT_PTS[:2]})  # 服务端 A 档过滤后只有 text 点
    bm25 = FakeBM25(_BM25_PAIRS)                           # 索引侧仍含 table/caption 单元
    monkeypatch.setattr(hybrid, "EmbeddingClient", _BoomEmbed)
    monkeypatch.setattr(hybrid, "fetch_chunk_meta", lambda ids: _DB_META)

    res = asyncio.run(hybrid.retrieve("问题", _PROF_A, qvec=[0.1, 0.2],
                                      client=qdrant, bm25_idx=bm25))

    assert ROUTE_DENSE_IMAGE not in res.routes                       # use_image_route=False
    assert filter_kinds(qdrant, TEXT_COLLECTION) == ["text"]          # tier A 映射
    assert all(c["collection"] != IMAGE_COLLECTION for c in qdrant.calls)
    assert [h.chunk_id for h in res.routes[ROUTE_BM25]] == ["tB"]     # tabT/capC 被 kind 后过滤剔除
    assert all(h.chunk_id not in ("tabT", "capC") for h in res.fused)
    assert [h.chunk_id for h in res.fused] == ["tB", "tA"]            # tB=1/4+1/3 > tA=1/3


def test_retrieve_bm25_bypass_weight_zero(monkeypatch):
    """bm25_weight=0.0（D11 zh 旁路）：BM25 连检索都不发起，routes 无 bm25 键。"""
    qdrant = FakeQdrant({TEXT_COLLECTION: _TEXT_PTS[:2]})
    bm25 = FakeBM25(_BM25_PAIRS)
    monkeypatch.setattr(hybrid, "EmbeddingClient", _BoomEmbed)
    monkeypatch.setattr(hybrid, "fetch_chunk_meta", _BoomMeta())  # 无 BM25 候选/无 caption → 不回表

    res = asyncio.run(hybrid.retrieve("问题", _PROF_A, qvec=[0.1, 0.2],
                                      client=qdrant, bm25_idx=bm25, bm25_weight=0.0))

    assert bm25.calls == []                       # 桩没被调用 = 整路旁路
    assert ROUTE_BM25 not in res.routes
    assert [h.chunk_id for h in res.fused] == ["tA", "tB"]   # 纯 dense：tA=1/3 > tB=1/4
    assert all("bm25" not in h.route_hits for h in res.fused)


def test_retrieve_bm25_weight_half_applied(monkeypatch):
    """bm25_weight=0.5（M5 降权档）：权重乘进 RRF 分子——tB=1/4+0.5/3。"""
    qdrant = _b_qdrant()
    bm25 = FakeBM25(_BM25_PAIRS)
    monkeypatch.setattr(hybrid, "EmbeddingClient", _BoomEmbed)
    monkeypatch.setattr(hybrid, "fetch_chunk_meta", lambda ids: _DB_META)

    res = asyncio.run(hybrid.retrieve("问题", _PROF_C, qvec=[0.1, 0.2],
                                      client=qdrant, bm25_idx=bm25, bm25_weight=0.5))

    by = {h.chunk_id: h.score for h in res.fused}
    assert by["tB"] == pytest.approx(1 / 4 + 0.5 / 3)
    assert by["tabT"] == pytest.approx(0.5 / 4)
    assert by["capC"] == pytest.approx(1 / 5 + 0.5 / 5)   # dense_text rank3 未加权 + bm25 rank3 降权
    # tB=0.4167 > tA=imgI=1/3（首见序）> capC=0.3 > tabT=0.125
    assert [h.chunk_id for h in res.fused] == ["tB", "tA", "imgI", "capC", "tabT"]


def test_retrieve_pool_truncation(monkeypatch):
    """pool = deduped[:profile.fused_pool]（D6 骨架融合池截断）。"""
    prof = Profile("S", "截断档", fused_pool=2)  # 其余默认 = B 档
    monkeypatch.setattr(hybrid, "EmbeddingClient", _BoomEmbed)
    monkeypatch.setattr(hybrid, "fetch_chunk_meta", lambda ids: _DB_META)

    res = asyncio.run(hybrid.retrieve("问题", prof, qvec=[0.1, 0.2],
                                      client=_b_qdrant(), bm25_idx=FakeBM25(_BM25_PAIRS)))
    assert len(res.deduped) == 4
    assert [h.chunk_id for h in res.pool] == [h.chunk_id for h in res.deduped][:2] == ["tB", "capC"]


def test_retrieve_embed_client_used_without_qvec(monkeypatch):
    """qvec 未注入 → 走 embed_client.embed_query（async），向量透传给 Qdrant。"""
    qdrant = FakeQdrant({TEXT_COLLECTION: _TEXT_PTS[:1]})
    embed = FakeEmbed([0.25, 0.25])
    monkeypatch.setattr(hybrid, "fetch_chunk_meta", _BoomMeta())

    res = asyncio.run(hybrid.retrieve("你好", _PROF_TEXT_ONLY, client=qdrant, embed_client=embed))

    assert embed.calls == ["你好"]
    assert qdrant.calls[0]["query"] == [0.25, 0.25]
    assert [h.chunk_id for h in res.fused] == ["tA"]


def test_retrieve_qvec_injected_skips_embedding(monkeypatch):
    """qvec 已注入 → 绝不构建嵌入客户端（哨兵类兜底断言）。"""
    monkeypatch.setattr(hybrid, "EmbeddingClient", _BoomEmbed)
    monkeypatch.setattr(hybrid, "fetch_chunk_meta", _BoomMeta())
    res = asyncio.run(hybrid.retrieve("问题", _PROF_TEXT_ONLY, qvec=[0.1],
                                      client=FakeQdrant({TEXT_COLLECTION: _TEXT_PTS[:1]})))
    assert [h.chunk_id for h in res.fused] == ["tA"]


def test_retrieve_empty_profile_no_io(monkeypatch):
    """三路全关（text_kinds=None + 无 image + 无 BM25）：routes/fused/deduped/pool 全空，零 IO。"""
    prof = Profile("N", "无路档", text_kinds=None, use_image_route=False, use_bm25=False)
    qdrant = FakeQdrant()
    monkeypatch.setattr(hybrid, "EmbeddingClient", _BoomEmbed)
    monkeypatch.setattr(hybrid, "fetch_chunk_meta", _BoomMeta())

    res = asyncio.run(hybrid.retrieve("问题", prof, qvec=[0.1], client=qdrant,
                                      bm25_idx=FakeBM25([("x", 1.0)])))
    assert res.routes == {} and res.fused == [] and res.deduped == [] and res.pool == []
    assert qdrant.calls == []   # 没有发起任何向量查询


def test_retrieve_owned_client_closed(monkeypatch):
    """自建 client（client=None）由 retrieve 负责 close；注入的 client 不动（生命周期归调用方）。"""
    owned = FakeQdrant({TEXT_COLLECTION: _TEXT_PTS[:1]})
    injected = FakeQdrant({TEXT_COLLECTION: _TEXT_PTS[:1]})
    monkeypatch.setattr(hybrid, "_client", lambda: owned)
    monkeypatch.setattr(hybrid, "EmbeddingClient", _BoomEmbed)
    monkeypatch.setattr(hybrid, "fetch_chunk_meta", _BoomMeta())

    asyncio.run(hybrid.retrieve("问题", _PROF_TEXT_ONLY, qvec=[0.1]))
    assert owned.closed is True

    asyncio.run(hybrid.retrieve("问题", _PROF_TEXT_ONLY, qvec=[0.1], client=injected))
    assert injected.closed is False
