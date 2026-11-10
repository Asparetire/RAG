"""DocLens 全局配置（plan D10）。

职责：
- pydantic-settings 读取仓库根目录 `.env`；
- 模型名集中管理（plan D3/D6/D7/D8，改名只动 .env / 本文件默认值）；
- 嵌入 instructions 官方模板（Query/Corpus 分侧，跨模态问答场景，见 runbook §0.4）；
- 消融阶梯 A–F 常量（PRD §7.1）；
- data/ 路径常量（代码跨平台：pathlib，不写死系统路径）。
"""

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


settings = Settings()


# ---------- 嵌入 instructions 模板（runbook §0.4，官方跨模态问答模板） ----------
QUERY_INSTRUCTION = (
    "Target_modality: text/image.\n"
    "Instruction:根据这个问题，找到能回答这个问题的相应文本或图片\nQuery:"
)
CORPUS_TEXT_INSTRUCTION = "Instruction:Compress the text into one word.\nQuery:"
CORPUS_IMAGE_INSTRUCTION = "Instruction:Compress the image into one word.\nQuery:"
