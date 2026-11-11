"""DocLens 全局配置（plan D10）。

职责：
- pydantic-settings 读取仓库根目录 `.env`；
- 模型名集中管理（plan D3/D6/D7/D8，改名只动 .env / 本文件默认值）；
- 嵌入 instructions 官方模板（Query/Corpus 分侧，跨模态问答场景，见 runbook §0.4）；
- 消融阶梯 A–F 常量（PRD §7.1）；
- data/ 路径常量（代码跨平台：pathlib，不写死系统路径）。
"""

from dataclasses import dataclass
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# ---------- 路径常量（pathlib，跨平台） ----------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
REPORTS_DIR = PROJECT_ROOT / "reports"
TEST_OUTPUT_DIR = DATA_DIR / "test"      # MinerU 样例解析输出（runbook §0.2）
PARSED_DIR = DATA_DIR / "parsed"         # 正式解析产物（plan D10：按 PDF sha256 落盘）


# ---------- 消融阶梯 A–F 常量（PRD §7.1，v2.0 扩展自 A–D） ----------
ABLATION_TIERS: dict[str, str] = {
    "A": "纯文本 RAG（文本向量 + BM25）——baseline 起点",
    "B": "A + 图注/表格线性化文本入库——图表的文字代理价值",
    "C": "B + 图像嵌入检索——跨模态检索真实增益",
    "D": "C + 重排——精排贡献（flash/pro 重排器对比位）",
    "E": "D + 块级上下文增强索引——索引侧增强增益",
    "F": "E + 多模态重排——跨模态精排增益",
}


# ---------- 消融档位注册表（m3-runbook K8，调研 R19：一条命令一个完整配置） ----------
@dataclass(frozen=True)
class Profile:
    """一个消融档位 = 一次问答的完整配置（六档共享字段 + 档位覆写）。

    字段即"召回方案旋钮"（调研 §1.1c）：路线开关用 kind 集合表达（None=该路关闭），
    融合器/权重/top-k 可切换，M5 加消融档零改动。
    """

    name: str
    desc: str
    text_kinds: list[str] | None = ("text", "table", "caption")  # 文本集合 kind 过滤；None=关文本路
    use_image_route: bool = True                                  # C 档起开图像向量路
    use_bm25: bool = True                                         # A..F 全开（zh 查询由 router 旁路）
    rerank: str | None = None                                     # None / "flash" / "pro"（D 档起）
    use_ctx_prefix: bool = False                                  # E 档起拼 t_ctx_prefix 前缀
    multimodal_rerank: bool = False                               # F 档视觉逐图打分（P1）
    per_route_top: int = 30          # 每路召回量（R1 调参位 20–50）
    fused_pool: int = 50             # RRF 融合池（D6 骨架 top-50）
    rerank_input: int = 30           # 重排输入截断（R8）
    final_top: int = 20              # 重排输出/组装上限（D12）
    max_images: int = 5              # FR-4.1 图片 ≤5
    fusion: str = "rrf"              # 融合器：rrf / weighted_rrf / dbsf（K1 可插拔）
    rrf_k: int = 2                   # RRF k（已定约束=Qdrant 服务端默认；k=60 留 M5 对照）


PROFILES: dict[str, Profile] = {
    "A": Profile("A", ABLATION_TIERS["A"], text_kinds=("text",)),
    "B": Profile("B", ABLATION_TIERS["B"]),
    "C": Profile("C", ABLATION_TIERS["C"]),
    "D": Profile("D", ABLATION_TIERS["D"], rerank="flash"),
    "E": Profile("E", ABLATION_TIERS["E"], rerank="flash", use_ctx_prefix=True),
    "F": Profile("F", ABLATION_TIERS["F"], rerank="flash", use_ctx_prefix=True,
                 multimodal_rerank=True),
}


class Settings(BaseSettings):
    """所有字段名与 `.env` 环境变量一一对应（大小写不敏感）。"""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",  # .env 中的注释键或未声明键不报错
    )

    # --- 火山方舟（单供应商，全链路一把 key；Coding Plan 支持第三方模型） ---
    ark_api_key: str = ""
    ark_base_url: str = "https://ark.cn-beijing.volces.com/api/coding/v3"
    ark_embed_base_url: str = ""  # M0 §0.4 冒烟探测后回填（coding/v3 或 api/v3）
    embed_model: str = "doubao-embedding-vision-251215"
    embed_dimensions: int = 2048
    gen_model: str = "glm-5.3-flash"  # 原生多模态 VLM，看图+生成（2026-11-10 起，替代 doubao-seed-2.1-pro）
    ctx_model: str = "deepseek-v4-flash"
    rerank_model_flash: str = "deepseek-v4-flash"
    rerank_model_pro: str = "doubao-seed-2-1-pro-260915"

    # --- 存储（容器侧 127.0.0.1 直连；Windows 侧写服务器 IP） ---
    mysql_url: str = "mysql+pymysql://doclens@127.0.0.1:3306/doclens"
    qdrant_url: str = "http://127.0.0.1:6333"
    qdrant_api_key: str = ""

    # --- 解析（MinerU 桥接，m1-runbook 1.3：subprocess 调 doclens-mineru 环境） ---
    mineru_bin: str = ""        # mineru-kit CLI 绝对路径，两端 .env 各自配置（容器 /opt/...；Windows D:\soft\anaconda\envs\doclens-mineru\Scripts\mineru-kit.exe）
    mineru_timeout: int = 1800  # 单篇解析超时（秒）


settings = Settings()


# ---------- 嵌入 instructions 模板（runbook §0.4，官方跨模态问答模板） ----------
QUERY_INSTRUCTION = (
    "Target_modality: text/image.\n"
    "Instruction:根据这个问题，找到能回答这个问题的相应文本或图片\nQuery:"
)
CORPUS_TEXT_INSTRUCTION = "Instruction:Compress the text into one word.\nQuery:"
CORPUS_IMAGE_INSTRUCTION = "Instruction:Compress the image into one word.\nQuery:"
