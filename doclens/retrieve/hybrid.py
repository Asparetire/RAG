"""混合检索编排：三路召回 + 客户端融合 + 证据组去重（m3-runbook 3.1；K1）。

职责：
- 三路召回（开关全部来自 Profile，单一事实源 config.py）：
  dense_text（text 集合按档位）/ dense_image（image 集合）/ bm25（本地索引+kind 后过滤）；
- 融合器=可插拔纯函数（K1/R3/R19）：rrf / weighted_rrf / dbsf，M5 加消融档零改动；
- 证据组去重（K1/R2）：RRF 之后、重排之前，按 (doc_id,page)+figure 组归并，
  组内最优名次做代表、组成员保留供引用（引用可指组内任一成员）；
- retrieve() 编排：产物 RetrievalResult（routes/fused/deduped/pool），pool 交重排（D6 骨架）。

设计依据（specs/research/m3-retrieval-generation-survey.md R1/R2/R3/R4/R19）：
- R1  **两条官方坑（必读）**：
     ① Qdrant 服务端 RRF（prefetch+fusion）只能挂单集合——本项目三路异构（text 集合 +
       image 集合 + 本地 BM25），服务端融合天然不适用，故客户端自实现（本模块 fuse_*）。
       若将来改服务端融合：**prefetch 的 limit 必须 ≥ 主查询 limit+offset，否则可能得到
       空结果**（当前未用服务端融合，仅记录防复发）；
     ② 融合后的 score 只是排名合成值，**不再具备相似度语义**（各路分数量纲互不相关）——
       融合层之上再套 score_threshold、或跨查询比较融合分均不可靠（K7 兜底因此不设全局阈值）。
- R2  图-图注联动去重 = 证据组归并（页级聚合的块级等价物，无块级先例自研）；
- R3/R19 融合器三实现：k=2 维持 Qdrant 服务端默认（k=60 留 M5 对照位）；DBSF 为分数系
       消融代表（每路 z-score 归一，std=0 的路贡献 0）；
- R4  客户端加权 RRF 用 Qdrant 官方公式 1/(k+rank/w)（权重乘进名次，非乘分子）。

实现纪律：
- 档位映射：text_kinds=={"text"} → tier "A"，否则 "B"（qdrant_store.TIER_KINDS 仅有的
  两个键）。**不用 TIER_KINDS 判断 image**——那是 A/B 档 kind 过滤映射，image 路开关只看
  Profile.use_image_route（config.py 注释"image 档位"与文本档位是两套正交旋钮）；
- BM25 路的 kind 过滤=**后过滤**（索引含 text/table/caption 全部单元，不在 BM25 里加索引）：
  命中 chunk 的 kind ∉ profile.text_kinds 则剔除，kind/元数据从 t_chunk 回表
  （scripts/search_probe.py:_lookup_contents 的参数化 IN 模式，绝无字符串拼接）；
- 异步纪律（m2-runbook §3.1）：embed_query 是 async；PyMySQL 同步库 → 回表包
  asyncio.to_thread；qdrant-client 本身同步 HTTP，单次查询毫秒级，M3 维持直调；
- bm25_weight 语义（router.py 产出）：None=正常 / 0.0=旁路（整路不跑，连检索都不发起）/
  0.5=降权（M5 起）——降权经 weights 传给融合器。
"""

from __future__ import annotations

import asyncio
import json
import statistics
from collections.abc import Callable
from dataclasses import dataclass, field, replace

from doclens.config import Profile
from doclens.index.bm25 import Bm25Index, load_index
from doclens.index.db import connect
from doclens.index.embeddings import EmbeddingClient
from doclens.index.qdrant_store import IMAGE_COLLECTION, _client, search_tier

# ---------- 路名常量（trace schema §3.1：dense_text|dense_image|bm25，单一来源） ----------
ROUTE_DENSE_TEXT = "dense_text"
ROUTE_DENSE_IMAGE = "dense_image"
ROUTE_BM25 = "bm25"

_TIER_A_KINDS = {"text"}  # 档位映射：仅 text → A 档；其余（text+table+caption）→ B 档
_FIGURE_KINDS = ("caption", "image")  # figure 组参与方（caption 与 image 按 image_path 联动）


# ---------- 数据结构 ----------
@dataclass
class Hit:
    """统一命中单元（三路召回 → 融合 → 去重全链路共用）。

    - route_hits：路名 → (rank 名次从 1 起, raw_score 该路原始分)。RRF 系只看 rank，
      DBSF 只看 raw_score——两者都留，消融分析免重跑；
    - doc_id/page/kind/image_path/heading_path：来自 Qdrant payload 或 t_chunk 回表，
      供证据组归并与下游（重排/组装/引用）直接取用，避免二次回表；
    - score：融合分（R1 官方坑②：无相似度语义，不可跨查询比较、不可设全局阈值）；
    - group_members：证据组成员 chunk_id（含代表自身、按融合序）——仅去重后的代表
      Hit 非空；单元素组为 [自身]，下游取用口径统一。
    """

    chunk_id: str
    kind: str
    score: float
    route_hits: dict[str, tuple[int, float]] = field(default_factory=dict)
    doc_id: str = ""
    page: int | None = None
    image_path: str | None = None
    heading_path: list[str] = field(default_factory=list)
    group_members: list[str] = field(default_factory=list)


@dataclass
class RetrievalResult:
    """retrieve() 产物：全链路中间态（3.5 query_cli 序列化进 trace / 消融分析用）。

    pool = deduped[:profile.fused_pool]——交重排的融合池（D6 骨架 top-50）。
    """

    question: str
    profile_name: str
    routes: dict[str, list[Hit]]
    fused: list[Hit]
    deduped: list[Hit]
    pool: list[Hit]


# ---------- Hit 构造（payload / 回表 → 统一单元） ----------
def _hit_from_text_point(p) -> Hit:
    """text 集合 ScoredPoint → Hit（payload：chunk_id/doc_id/kind/page/heading_path）。"""
    pl = p.payload
    return Hit(chunk_id=pl["chunk_id"], kind=pl.get("kind") or "text", score=float(p.score),
               doc_id=pl.get("doc_id") or "", page=pl.get("page"),
               heading_path=list(pl.get("heading_path") or []))


def _hit_from_image_point(p) -> Hit:
    """image 集合 ScoredPoint → Hit（payload：chunk_id/doc_id/image_path/caption/page/bbox）。

    image payload 无 kind 键（两集合按 kind 天然分区）→ 恒置 "image"。
    """
    pl = p.payload
    return Hit(chunk_id=pl["chunk_id"], kind="image", score=float(p.score),
               doc_id=pl.get("doc_id") or "", page=pl.get("page"),
               image_path=pl.get("image_path"))


def _hit_from_bm25(chunk_id: str, score: float, meta: dict) -> Hit:
    """BM25 (chunk_id, score) + 回表元数据 → Hit（kind 过滤已在其上游完成）。"""
    return Hit(chunk_id=chunk_id, kind=meta.get("kind") or "", score=float(score),
               doc_id=meta.get("doc_id") or "", page=meta.get("page"),
               image_path=meta.get("image_path"),
               heading_path=list(meta.get("heading_path") or []))


def search_image(client, vec: list[float], top: int = 20) -> list:
    """image 集合检索（K1 补齐——qdrant_store 无现成函数）：无过滤直查。

    过滤参数暂无场景（FR-2.7 doc 级过滤需要时再扩签名），与 search_tier 保持同款
    query_points 调用形态；集合名取 qdrant_store.IMAGE_COLLECTION 单一来源。
    """
    return client.query_points(IMAGE_COLLECTION, query=vec, limit=top).points


# ---------- 回表（同步，调用方包 asyncio.to_thread） ----------
_FETCH_SQL = (
    "SELECT chunk_id, doc_id, kind, page, heading_path, image_path "
    "FROM t_chunk WHERE chunk_id IN ({ph})"
)


def fetch_chunk_meta(chunk_ids: list[str]) -> dict[str, dict]:
    """t_chunk 回表（同步函数——PyMySQL 同步库，编排侧用 asyncio.to_thread 包裹，m2 §3.1）。

    SQL 模式照搬 scripts/search_probe.py:_lookup_contents（参数化 IN、按 500 分批——
    同 embeddings._cache_get_many 先例）；heading_path 为 JSON 列，pymysql 返回 str
    （rerank.py 同款实证），此处统一 json.loads 成 list。
    返回 {chunk_id: {doc_id, kind, page, heading_path, image_path}}；查无的 chunk_id 不在结果里。
    """
    if not chunk_ids:
        return {}
    conn = connect()
    try:
        out: dict[str, dict] = {}
        with conn.cursor() as cur:
            for i in range(0, len(chunk_ids), 500):
                batch = chunk_ids[i:i + 500]
                ph = ",".join(["%s"] * len(batch))
                cur.execute(_FETCH_SQL.format(ph=ph), batch)
                for cid, doc_id, kind, page, heading_path, image_path in cur.fetchall():
                    hp = heading_path
                    if isinstance(hp, (str, bytes)):
                        try:
                            hp = json.loads(hp)
                        except ValueError:
                            hp = None  # 脏数据不炸检索：降级为空 heading_path
                    out[cid] = {"doc_id": doc_id, "kind": kind, "page": page,
                                "heading_path": list(hp or []), "image_path": image_path}
        return out
    finally:
        conn.close()


# ---------- 融合器（K1/R3/R19：模块级纯函数，全部无 IO；rank 从 1 起） ----------
def _accumulate(routes: dict[str, list[Hit]], route_contrib: Callable) -> list[Hit]:
    """遍历各路累加贡献分 → 合并 route_hits/元数据 → 按融合分降序（稳定）返回新 Hit 列表。

    - route_contrib(route, rank, raw_score) → 该次命中的贡献分；
    - 同 chunk 多路命中：route_hits 逐路合并，元数据（doc_id/page/kind/…）取首见路；
    - 纯函数：不改入参；融合分并列时保持"路枚举序 + 路内名次"的首见序（稳定排序）。
    """
    order: list[str] = []
    by_id: dict[str, dict] = {}
    for route, hits in routes.items():
        for rank, h in enumerate(hits, start=1):
            entry = by_id.get(h.chunk_id)
            if entry is None:
                entry = {
                    "score": 0.0,
                    "hit": Hit(chunk_id=h.chunk_id, kind=h.kind, score=0.0, route_hits={},
                               doc_id=h.doc_id, page=h.page, image_path=h.image_path,
                               heading_path=list(h.heading_path)),
                }
                by_id[h.chunk_id] = entry
                order.append(h.chunk_id)
            entry["score"] += route_contrib(route, rank, h.score)
            entry["hit"].route_hits[route] = (rank, h.score)
    out = [by_id[cid]["hit"] for cid in order]
    for entry in by_id.values():
        entry["hit"].score = entry["score"]  # 累加完毕再回填融合分
    out.sort(key=lambda h: -h.score)
    return out


def fuse_rrf(routes: dict[str, list[Hit]], k: int = 2,
             weights: dict[str, float] | None = None) -> list[Hit]:
    """客户端 RRF（K1 主线，R1 定稿）：score = Σ w_r/(k+rank)，rank 从 1 起。

    - k 默认 2（恰为 Qdrant 服务端默认；k=60 留 M5 对照位）；
    - weights 可选按路乘在**分子**（w 缺省 1；w=0 的路贡献 0）；
    - 融合分对分数质量与量纲免疫（只看名次）——三路异构下这是主线既定理由。
    """
    w = weights or {}

    def contrib(route: str, rank: int, _raw: float) -> float:
        return w.get(route, 1.0) / (k + rank)

    return _accumulate(routes, contrib)


def fuse_weighted_rrf(routes: dict[str, list[Hit]], k: int = 2,
                      weights: dict[str, float] | None = None) -> list[Hit]:
    """客户端加权 RRF（R4）：score = Σ 1/(k+rank/w_r)——与 Qdrant 官方公式一致。

    官方公式 score=Σ1/(k+(rank+1)/w−1) 在 rank 从 1 起时即 1/(k+rank/w)：w 乘进**名次**
    （w=2 → 名次折半计），不是乘分子；w=1 严格退化为 fuse_rrf。w≤0 的路贡献 0。
    """
    w = weights or {}

    def contrib(route: str, rank: int, _raw: float) -> float:
        wr = w.get(route, 1.0)
        if wr <= 0:
            return 0.0
        return 1.0 / (k + rank / wr)

    return _accumulate(routes, contrib)


def fuse_dbsf(routes: dict[str, list[Hit]], k: int = 2,
              weights: dict[str, float] | None = None) -> list[Hit]:
    """DBSF 分布归一融合（R3/R19 分数系消融代表）：每路 z-score 归一后加权求和。

    - 均值/标准差取自**该路本次结果集**（总体标准差 statistics.pstdev）；
    - std=0（含单元素路）→ 该路贡献 0（无区分度的路不参与排序）；
    - 融合分可为负、无相似度语义（R1 官方坑②同样适用）；
    - k 参数为 fuse() 分发接口统一而保留，本融合器不使用。
    """
    w = weights or {}

    def zscores(hits: list[Hit]) -> list[float]:
        scores = [h.score for h in hits]
        if not scores:
            return []
        std = statistics.pstdev(scores)
        if std == 0:
            return [0.0] * len(scores)
        mean = statistics.fmean(scores)
        return [(s - mean) / std for s in scores]

    zmap = {route: zscores(hits) for route, hits in routes.items()}

    def contrib(route: str, rank: int, _raw: float) -> float:
        return w.get(route, 1.0) * zmap[route][rank - 1]

    return _accumulate(routes, contrib)


FUSERS: dict[str, Callable[..., list[Hit]]] = {
    "rrf": fuse_rrf,
    "weighted_rrf": fuse_weighted_rrf,
    "dbsf": fuse_dbsf,
}


def fuse(routes: dict[str, list[Hit]], method: str, **kwargs) -> list[Hit]:
    """按 method 分发融合器（K1 可插拔入口）；未知 method raise ValueError。"""
    fn = FUSERS.get(method)
    if fn is None:
        raise ValueError(f"未知融合器: {method!r}（可选: {sorted(FUSERS)}）")
    return fn(routes, **kwargs)


# ---------- 证据组去重（K1/R2：RRF 之后、重排之前） ----------
def dedup_evidence_groups(hits: list[Hit], members_map: dict[str, dict]) -> list[Hit]:
    """证据组归并：同 (doc_id,page) 归并；caption↔image 按 image_path 跨 page 强制同组。

    规则（R2）：
    - 常规 key=("page", doc_id, page)：同 key 命中归并一组；
    - figure 组：kind ∈ {caption, image} 且 image_path 非空 → 追加 key ("fig", image_path)
      强制同组（跨 page 也归并）；经并查集传递，caption 的同页伙伴与 image 的同页伙伴
      随之并入同组；
    - 组代表 = 组内融合分最高者（并列取先出现者），保留其在原序列中的位置；
    - 组成员 chunk_id（含代表自身、按入参序=融合序）记入代表 Hit.group_members；
    - doc_id 或 page 未知（members_map 与 Hit 元数据都缺）的命中各自成组——宁可少去重
      不可误合并；doc_id 缺失的 figure 组同理不成立；
    - 组间相对序 = 代表在原序列中的相对序（本函数不重排，只做吸收式去重）。

    纯函数：返回新 Hit 列表（dataclasses.replace 浅拷贝代表，group_members 单独实例化）。
    """
    n = len(hits)
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]  # 路径压缩
            i = parent[i]
        return i

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)  # 小索引为根：组内元素集与根解耦，代表单独选

    # 1) 归并键
    keys_for: list[list[tuple]] = []
    for h in hits:
        meta = members_map.get(h.chunk_id) or {}
        kind = meta.get("kind") or h.kind
        doc_id = meta.get("doc_id") or h.doc_id
        page = meta.get("page") if meta.get("page") is not None else h.page
        image_path = meta.get("image_path") or h.image_path
        ks: list[tuple] = []
        if doc_id and page is not None:
            ks.append(("page", doc_id, page))
        if kind in _FIGURE_KINDS and image_path:
            ks.append(("fig", image_path))
        if not ks:
            ks.append(("solo", h.chunk_id))
        keys_for.append(ks)

    # 2) 同键并查集合并
    by_key: dict[tuple, list[int]] = {}
    for i, ks in enumerate(keys_for):
        for key in ks:
            by_key.setdefault(key, []).append(i)
    for members in by_key.values():
        for j in members[1:]:
            union(members[0], j)

    # 3) 分组、选代表（最高融合分；并列取先出现者）
    members_of: dict[int, list[int]] = {}
    for i in range(n):
        members_of.setdefault(find(i), []).append(i)
    rep_of: dict[int, int] = {}
    for root, members in members_of.items():
        rep = members[0]
        for i in members[1:]:
            if hits[i].score > hits[rep].score:
                rep = i
        rep_of[root] = rep

    # 4) 代表按原位输出，成员完整记入 group_members
    out: list[Hit] = []
    for i in range(n):
        root = find(i)
        if rep_of[root] != i:
            continue
        member_ids = [hits[j].chunk_id for j in members_of[root]]
        out.append(replace(hits[i], group_members=member_ids))
    return out


def build_members_map(payload_meta: dict[str, dict], db_meta: dict[str, dict]) -> dict[str, dict]:
    """组装证据组成员映射 {chunk_id: {doc_id, page, kind, image_path}}（R2/K1 帮助函数）。

    来源合并（payload 侧优先、t_chunk 回表补缺）：
    - payload_meta：三路命中 Hit 携带的元数据（text/image 集合 payload 直接可取）；
    - db_meta：fetch_chunk_meta 的回表结果——caption 的 image_path 不在 text 集合
      payload 里（qdrant_store.upsert_units 只给 image 点写 image_path），只能回表取，
      figure 联动（R2）因此依赖回表补缺。
    """
    merged: dict[str, dict] = {}
    for cid in set(payload_meta) | set(db_meta):
        p = payload_meta.get(cid) or {}
        d = db_meta.get(cid) or {}
        page = p.get("page") if p.get("page") is not None else d.get("page")
        merged[cid] = {
            "doc_id": p.get("doc_id") or d.get("doc_id"),
            "page": page,
            "kind": p.get("kind") or d.get("kind"),
            "image_path": p.get("image_path") or d.get("image_path"),
        }
    return merged


def _payload_meta(routes: dict[str, list[Hit]]) -> dict[str, dict]:
    """三路 Hit 的元数据拍平成 payload 侧视图（build_members_map 的第一个入参）。"""
    out: dict[str, dict] = {}
    for hits in routes.values():
        for h in hits:
            out.setdefault(h.chunk_id, {
                "doc_id": h.doc_id, "page": h.page,
                "kind": h.kind, "image_path": h.image_path,
            })
    return out


# ---------- 主入口（编排，async） ----------
async def retrieve(question: str, profile: Profile, *, qvec: list[float] | None = None,
                   client=None, bm25_idx: Bm25Index | None = None,
                   bm25_weight: float | None = None,
                   embed_client: EmbeddingClient | None = None) -> RetrievalResult:
    """三路召回 → 客户端融合 → 证据组去重 → 融合池截断（K1 管道序）。

    参数注入约定（单测/复用）：qvec / client / bm25_idx / embed_client 传 None 才自建
    （embed_query 是 async；client 为 qdrant_store._client()）；bm25_weight 见模块
    docstring（None=正常 / 0.0=旁路 / 0.5=降权），由调用方经 router.bm25_weight_for 决定。
    融合器与 k 从 profile.fusion / profile.rrf_k 读取；自建 client 由本函数负责 close，
    注入的 client 生命周期归调用方。
    """
    own_client = client is None
    qc = client if client is not None else _client()
    try:
        # 0. 查询向量（注入优先，否则走嵌入客户端——async）
        if qvec is None:
            ec = embed_client if embed_client is not None else EmbeddingClient()
            qvec = await ec.embed_query(question)

        routes: dict[str, list[Hit]] = {}

        # 1a. dense text 路：text_kinds 为 None/空 → 整路关闭；档位映射 {"text"}→A 否则 B
        if profile.text_kinds:
            tier = "A" if set(profile.text_kinds) == _TIER_A_KINDS else "B"
            points = search_tier(qc, qvec, tier=tier, top=profile.per_route_top)
            routes[ROUTE_DENSE_TEXT] = [_hit_from_text_point(p) for p in points]

        # 1b. dense image 路：只看 use_image_route（与 TIER_KINDS 的 A/B kind 映射无关）
        if profile.use_image_route:
            points = search_image(qc, qvec, top=profile.per_route_top)
            routes[ROUTE_DENSE_IMAGE] = [_hit_from_image_point(p) for p in points]

        # 1c. BM25 路：0.0=旁路（整路不跑，连检索都不发起，D11）；其余先取原始 (chunk_id, score)
        bm25_pairs: list[tuple[str, float]] = []
        bm25_ran = profile.use_bm25 and bm25_weight != 0.0
        if bm25_ran:
            idx = bm25_idx if bm25_idx is not None else load_index()
            bm25_pairs = idx.search(question, top=profile.per_route_top)

        # 2. 一次回表拿齐元数据（BM25 后过滤 + caption 的 figure 联动都靠它；
        #    PyMySQL 同步库 → to_thread，m2 §3.1 纪律）
        need_meta = bool(bm25_pairs) or any(
            h.kind == "caption" for hits in routes.values() for h in hits)
        db_meta: dict[str, dict] = {}
        if need_meta:
            ids = sorted({h.chunk_id for hits in routes.values() for h in hits}
                         | {cid for cid, _ in bm25_pairs})
            db_meta = await asyncio.to_thread(fetch_chunk_meta, ids)

        # 2b. BM25 后过滤（R19/K1：索引含 text/table/caption 全部单元，kind 在此按档剔除；
        #     text_kinds=None 的档不做 kind 约束；回表无行的 chunk 丢弃不猜 kind）
        if bm25_ran:
            kept: list[Hit] = []
            for cid, raw in bm25_pairs:
                meta = db_meta.get(cid)
                if meta is None:
                    continue
                if profile.text_kinds is not None and meta.get("kind") not in profile.text_kinds:
                    continue
                kept.append(_hit_from_bm25(cid, raw, meta))
            # 键存在=该路真的跑过（0 命中留空列表）；没跑（开关关/旁路）则无键——trace 可区分
            routes[ROUTE_BM25] = kept

        # 3. 客户端融合（K1 可插拔；bm25_weight 注入为该路权重）
        weights = {ROUTE_BM25: bm25_weight} if bm25_weight is not None else None
        fused = fuse(routes, profile.fusion, k=profile.rrf_k, weights=weights)

        # 4. 证据组归并（R2：融合后、重排前；members_map 由 payload + 回表双源组装）
        members_map = build_members_map(_payload_meta(routes), db_meta)
        deduped = dedup_evidence_groups(fused, members_map)

        # 5. 融合池截断（D6 骨架 top-50 交重排；重排输入再截 30 归 3.2 rerank）
        pool = deduped[:profile.fused_pool]
        return RetrievalResult(question=question, profile_name=profile.name,
                               routes=routes, fused=fused, deduped=deduped, pool=pool)
    finally:
        if own_client:
            qc.close()
