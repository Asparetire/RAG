# M6 论文删除+回收站 代码审查报告（S3）

> 审查方式：独立子代理逐行审（不带实现上下文）+ 被调方核对（db/qdrant_store/ingest/hybrid/assets）+ git 提交核对（4b45e40+9ef6fa4+c7b250b）+ 本机实跑测试。
> 审查范围：paperlib 回收站段 / bm25_rebuild / api 五端点与过滤面 / init_db 补列 / test_paper_trash.py / PaperLibrary.jsx。
> 结论：**初版发现 1 Blocker + 2 Major，已全部修复并容器实证；237 passed。**

## 发现清单与处理情况

### Blocker（已修复）

- **B-1 软删后 BM25 检索面未真正摘除**（bm25.py 语料源 + paperlib 软删顺序）：`load_units_from_db()` 直读 t_chunk 无 deleted_at 过滤，且软删"重建先于打标"——重建语料仍含已删文档，D 档问答仍可召回已删论文，R1 核心验收不成立。n-7 指出根因：17 条测试全部 mock 掉 bm25_rebuild，替身盲区。
  - **修复**（commit c7b250b）：①语料源 `JOIN t_doc WHERE d.deleted_at IS NULL`（软删后重建自然摘除、恢复后自然包含、purge 级联清空后同样排除）；②软删重序"打标→摘 Qdrant→重建"（审查建议只提了恢复侧调序，软删侧同病，实现补齐）；③恢复重序"清标记→重放→重建"（回到调研 L61 原定顺序）；④重复删除语义从"空转返回"改为"重放自愈"（打标后中断可补齐摘除）。
  - **验证**：新增 sqlite 内存库真 SQL + 真 build_index 用例（test_load_units_and_build_exclude_trashed）+ 两处顺序断言；容器终验 BM25 块数 25→0（软删）→25（恢复）。

### Major（已修复）

- **M-1 purge"三步一事务"声明失实**：autocommit 下三条 DELETE 逐条自动提交。修复：`conn.begin()/commit()/rollback()` 包住（仿 _write_chunks 先例），FakeConn 补 begin/rollback 计数断言。
- **M-2 R5 守卫缺两处 + retry/去重 deleted_at 盲区**：restore/purge 补 `_raise_if_ingesting`；`_run_ingest` 去重改查 deleted_at——垃圾桶内文档重复入库 → 任务报错引导恢复（防"任务完成"改写垃圾桶内文档分类的隐藏副作用）；`api_papers_retry` 垃圾桶内文档 → 422。

### Minor（m-1/m-2/m-4/m-5 已修；m-3 记入 runbook）

- m-1 清空垃圾桶改捕 Exception 记日志逐篇继续（ValueError/RuntimeError 均不拖垮，有测试）；m-2 "论文不存在"→404（新增 PaperNotFoundError）、格式非法→422，语义区分（有测试）；m-4 scripts/ingest.py main() 内联三连改调 bm25_rebuild()（D5 四处共用闭环）；m-5 purge 的 rmtree 去掉 ignore_errors、失败记 warning 留可追孤儿。
- m-3 软删期资产直链（PDF/figure）仍可访问——**设计明示**：软删仅移除"检索面+列表"，直链资产保留是垃圾桶可恢复的前提（paperless 同款），已写入 runbook §7。

### Nit（n-1/n-2 已修；n-3~n-6 记池）

- n-1 幂等预检并入锁内主流程（重复删除=重放自愈，B-1 修复一并覆盖）；n-2 前端 restore/purge/empty 非 AuthError 异常补 alert + r.json() 防非 JSON 500 响应。
- 记池：n-3 deleted_by 无审计出口（L1 多用户时一并做）；n-4 trash_files 同名覆盖记日志；n-5 deleted_at 无索引（百级文档量无碍）；n-6 _INGEST_LOCK 进程内锁，多 worker/多实例部署需换分布式锁（runbook 已明示前提）。

## 做对的地方（审查确认）

五端点全挂 @protected；SQL 全参数化（含 LIKE）；doc_id 格式守卫+"不存在不触发写库"有测试；过滤面四处齐全；restore force=True 已固化；_run_ingest 步骤 4 与内联三连逐字等价；资源均 finally 释放；前端 modal 复用+二次确认+部分失败提示。

## 验证

- 本机：**237 passed**（tests/test_paper_trash.py 22 条，含 sqlite 真语料回归）。
- 容器：删除→Qdrant 27 点摘除→清单/侧栏不可见→垃圾桶可见→恢复→点位 27 回归→**BM25 块数 25→0→25**→垃圾桶空→磁盘资产完好；trash 端点无鉴权 401；新 bundle 上线。

跳过安全专项复查：非敏感代码（无新增认证/外部调用/PII；SQL 参数化；文件操作有格式守卫+兜底目录），依据 ai-dev-workflow S4 判据。
