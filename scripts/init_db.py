"""建 MySQL 六张表（m2-runbook 2.2 + m3-runbook K2；幂等 IF NOT EXISTS，可重复执行）。

表设计（§4 变更清单）：
- t_doc          文档元数据 + doc_hash（doc.json 全文 sha256——增量跳过依据，§3.1 增量语义）
- t_chunk        块清单单一事实源（content/bbox/kind/page/heading_path/content_hash/image_path
                 ——检索回表取正文与坐标，M3 生成、M4 高亮共用）
- t_embed_cache  嵌入缓存（键 = sha256(model+instruction+dim+content)，严格优于 LangChain 默认键）
- t_ctx_prefix   E 档块前缀缓存（FR-2.6，每 chunk 一条）
- t_eval_result  M5 评测结果（先建结构，run_id+profile 检索）
- t_rerank_cache M3 重排结果缓存（K2/R10，M5 消融复跑不重复计费）

用法（容器内 doclens 环境）：
    python scripts/init_db.py
验收：SHOW TABLES 6 张齐（t_doc/t_chunk/t_embed_cache/t_ctx_prefix/t_eval_result/t_rerank_cache）。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from doclens.index.db import connect

DDL = [
    # 文档级：doc_hash 变更 → 整篇先删后插；n_chunks 便捷对账
    """
    CREATE TABLE IF NOT EXISTS t_doc (
        doc_id     VARCHAR(16)  NOT NULL PRIMARY KEY COMMENT 'sha256 前 12 位',
        title      VARCHAR(512) NULL,
        doi        VARCHAR(128) NULL,
        sha256     CHAR(64)     NOT NULL,
        doc_hash   CHAR(64)     NOT NULL COMMENT 'doc.json 全文 sha256（增量跳过依据）',
        n_chunks   INT          NOT NULL DEFAULT 0,
        created_at DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='文档元数据（m2-runbook §3.1）'
    """,
    # 块级单一事实源：chunk_id = doc_id:0000（17 字符）；content 最长为表格卡片+markdown（实测 max≈7KB；
    # n-12：TEXT 64KB 余量偏紧且与写库失败叠加会半写 → MEDIUMTEXT 16MB）
    """
    CREATE TABLE IF NOT EXISTS t_chunk (
        chunk_id     VARCHAR(32)  NOT NULL PRIMARY KEY,
        doc_id       VARCHAR(16)  NOT NULL,
        kind         ENUM('text','table','caption','image') NOT NULL,
        content      MEDIUMTEXT   NOT NULL,
        page         INT          NOT NULL,
        bbox         JSON         NULL COMMENT '[x0,y0,x1,y1] 0–1 归一化（FR-2.4 坐标）',
        heading_path JSON         NULL,
        image_path   VARCHAR(255) NULL,
        caption      TEXT         NULL,
        content_hash CHAR(64)     NOT NULL,
        KEY idx_chunk_doc (doc_id),
        KEY idx_chunk_kind (kind),
        CONSTRAINT fk_chunk_doc FOREIGN KEY (doc_id) REFERENCES t_doc(doc_id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='块清单单一事实源（回表取正文/坐标）'
    """,
    # 嵌入缓存：vec = float32 小端 bytes（2048 维 = 8KB）；kind 决定向量进 text/image 集合
    """
    CREATE TABLE IF NOT EXISTS t_embed_cache (
        cache_key  CHAR(64)     NOT NULL PRIMARY KEY COMMENT 'sha256(model+instruction+dim+content)',
        model      VARCHAR(128) NOT NULL,
        kind       VARCHAR(16)  NOT NULL,
        dim        SMALLINT     NOT NULL,
        vec        MEDIUMBLOB   NOT NULL,
        created_at DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='嵌入缓存（K4 缓存先行）'
    """,
    # E 档前缀：每 chunk 一条（deepseek-v4-flash 生成，50–100 token）
    """
    CREATE TABLE IF NOT EXISTS t_ctx_prefix (
        chunk_id   VARCHAR(32)   NOT NULL PRIMARY KEY,
        prefix     VARCHAR(2048) NOT NULL,
        model      VARCHAR(128)  NOT NULL,
        created_at DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='E 档块上下文前缀（K7，FR-2.6）'
    """,
    # M5 评测：先建结构（run_id+profile 检索；detail 存逐题证据 JSON）
    """
    CREATE TABLE IF NOT EXISTS t_eval_result (
        id         BIGINT       NOT NULL AUTO_INCREMENT PRIMARY KEY,
        run_id     VARCHAR(64)  NOT NULL,
        profile    VARCHAR(8)   NOT NULL COMMENT 'A..F 消融档位',
        query_id   VARCHAR(64)  NOT NULL,
        metric     VARCHAR(32)  NOT NULL,
        value      DOUBLE       NULL,
        detail     JSON         NULL,
        created_at DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
        KEY idx_eval_run (run_id, profile)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='评测与消融结果（M5 用，先建结构）'
    """,
    # M5 跑批进度（m5-runbook 4.8 同款范式）：看板轮询 (run_id) 进度
    """
    CREATE TABLE IF NOT EXISTS t_eval_run (
        run_id     VARCHAR(64)  NOT NULL PRIMARY KEY,
        suite      VARCHAR(32)  NOT NULL COMMENT 'main/qasper/gen_model',
        status     ENUM('running','completed','error') NOT NULL DEFAULT 'running',
        total      INT          NOT NULL DEFAULT 0,
        completed  INT          NOT NULL DEFAULT 0,
        error      TEXT         NULL,
        created_at DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='评测跑批进度（M5 看板轮询）'
    """,
    # M3 重排结果缓存（m3-runbook K2，调研 R10）：键 = sha256(model+params+候选指纹+query)，
    # ranking = 重排后 chunk_id 有序列表 JSON——M5 消融跨配置重跑省钱+可复现（temp=0 非确定性兜底）
    """
    CREATE TABLE IF NOT EXISTS t_rerank_cache (
        cache_key   CHAR(64)      NOT NULL PRIMARY KEY COMMENT 'sha256(model+params+候选指纹+query)',
        model       VARCHAR(128)  NOT NULL,
        n_candidates INT          NOT NULL,
        ranking     JSON          NOT NULL COMMENT '重排后 chunk_id 有序列表',
        degraded    TINYINT(1)    NOT NULL DEFAULT 0 COMMENT '1=降级（回 RRF 序/解析失败）',
        created_at  DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='LLM 重排结果缓存（K2/R10，M5 复跑不重复计费）'
    """,
    # M4 论文库（m4-runbook 4.8，调研 §9）：FastGPT 式分类树（自引用+ancestor_ids 物化路径
    # +层级上限在应用层）+ dify 式任务状态机（batch 聚合号/chunk 计数/error 文本）。
    # user_id 一律可空——anything-llm 平滑升级路径（L1 启用时批量回填，零迁移）。
    """
    CREATE TABLE IF NOT EXISTS t_category (
        id           INT AUTO_INCREMENT PRIMARY KEY,
        name         VARCHAR(64)  NOT NULL,
        parent_id    INT          NULL COMMENT '自引用父节点（NULL=顶层）',
        ancestor_ids JSON         NOT NULL COMMENT '物化路径 [父id,...]（子树查询加速）',
        user_id      VARCHAR(64)  NULL COMMENT 'L1 预埋：归属用户（NULL=单管理员共用）',
        created_at   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
        KEY idx_cat_parent (parent_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='论文分类树（4.8）'
    """,
    """
    CREATE TABLE IF NOT EXISTS t_ingest_task (
        id               INT AUTO_INCREMENT PRIMARY KEY,
        batch_id         CHAR(32)     NOT NULL COMMENT '一次上传的聚合号（dify 惯例）',
        doc_id           VARCHAR(16)  NULL,
        filename         VARCHAR(255) NOT NULL,
        category_id      INT          NULL,
        status           ENUM('queued','parsing','indexing','completed','error') NOT NULL DEFAULT 'queued',
        progress         FLOAT        NOT NULL DEFAULT 0 COMMENT '0–1（dify/ragflow 口径）',
        progress_msg     VARCHAR(255) NULL,
        error            TEXT         NULL,
        completed_chunks INT          NULL,
        total_chunks     INT          NULL,
        user_id          VARCHAR(64)  NULL COMMENT 'L1 预埋',
        created_at       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        KEY idx_task_batch (batch_id),
        KEY idx_task_status (status)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='论文入库任务状态机（4.8）'
    """,
]


def main() -> int:
    expected = {"t_doc", "t_chunk", "t_embed_cache", "t_ctx_prefix", "t_eval_result",
                "t_rerank_cache", "t_category", "t_ingest_task", "t_eval_run"}
    conn = connect()
    try:
        with conn.cursor() as cur:
            for ddl in DDL:
                cur.execute(ddl)
            # 幂等补列（4.8）：t_doc 加 category_id/user_id（ALTER 失败=列已存在则忽略）
            for alter in (
                "ALTER TABLE t_doc ADD COLUMN category_id INT NULL",
                "ALTER TABLE t_doc ADD COLUMN user_id VARCHAR(64) NULL",
                "ALTER TABLE t_eval_result ADD COLUMN model VARCHAR(128) NULL",
            ):
                try:
                    cur.execute(alter)
                except Exception as e:  # noqa: BLE001 1060 重复列=已存在
                    if "1060" not in str(e) and "Duplicate column" not in str(e):
                        raise
            cur.execute("SHOW TABLES")
            tables = {r[0] for r in cur.fetchall()}
        missing = expected - tables
        if missing:
            print(f"[失败] 缺表: {sorted(missing)}")
            return 1
        print(f"[完成] {len(expected)}/{len(expected)} 张表就绪: {sorted(expected)}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
