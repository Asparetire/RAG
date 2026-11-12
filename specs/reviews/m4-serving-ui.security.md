# M4 S4 安全复查报告

- 审查者：S4 安全专项复查代理（只读审查；逐文件通读+全仓 grep+单测核对）
- 日期：2026-11-12；范围：M4 Web 面（至 HEAD 6a6cf70，含 4256f96 S3 修复批）
- **结论：有条件通过 → 修复批落地后通过**（Critical 0 / High 0 / Medium 1→已修 / Low 5→已修 3、记池 2 / Info 若干）

## 发现清单与处置

### M4-01（Medium→已修）登录限流按 ip:username 聚合——轮换 username 即绕过爆破防护
- auth.py 限流 key 含 username（请求方可任意轮换=每次新桶），5 次/3min 对唯一管理员密码的爆破防护实质失效（OWASP A07）。
- **修复（S4 修复批）**：key 仅用 IP（单管理员 username 恒 admin）；新增单测 test_rate_limit_ip_only_no_username_rotation_bypass（同 IP 换 6 用户名第 6 次 429）。

### M4-02（Low→记池）上传先整读内存后验大小
- `file.file.read()` 整体入 RAM 后才校验 100MB；Starlette multipart 无请求体上限。评估 Low：端点在鉴权门内，单管理员≈自伤面。修复便宜——分块读累计超限即 422。**记待办池（M5 顺手项）**。

### M4-03（Low→已修）session_stamp 无盐快速哈希
- `sha256(常量前缀+明文密码)[:16]` 无盐非慢哈希，token 泄漏可离线爆破密码；docstring 与实现不符。
- **修复（S4 修复批）**：改 HMAC-SHA256(jwt_secret, 派生串)——secret 不随 token 泄漏面暴露；docstring 同步修正；改密全端吊销机制不变（单测保持）。

### M4-04（Low→随 M4-01 收敛）限流字典无上界
- defaultdict 访问即建 key 不回收。IP-only 后增长面收敛；容量上限/定期清理记待办池。

### M4-05（Low→已修）任务 error 字段未脱敏（与 SSE error 双口径）
- `str(exc)[:500]` 原样落库可含路径/SQL 片段。
- **修复（S4 修复批）**：脱敏器抽至 `doclens/serve/sanitize.py`（避免 paperlib→api 循环导入），SSE 与任务 error 共用口径；api._sanitize_error 保留薄壳兼容测试。

### M4-06（Low·可用性→记池）BM25 重建非原子写 × 每查询加载
- 上传触发重建窗口内查询可能读到截断 pickle（不泄密）。修复=临时文件+os.replace。**记待办池（M5 顺手项）**。

### Info（择要记池）
- JWT ip claim 从不校验（死字段）；jti 无吊销存储（L1 多用户前需补）；JWT_SECRET 建议长度≥32 fail-fast；.env.example 缺 ADMIN_PASSWORD/JWT_SECRET/WEB_STATIC 三字段；AUTH_ENABLED 实际可被 .env 覆盖（注释与行为不符）；safe_name 残留 `:`/超长文件名健壮性；/api/query 无并发上限（费用自伤面）；`if _auth_on or True:` 恒真死代码。

## 必查项逐项结论
1. **JWT**：algorithms 钉死 HS256（混淆不可达）；exp 强制+篡改/过期单测；secret .env+空值 fail-fast；session_stamp 机制有效——通过（残留 M4-03 已修）。
2. **豁免面**：/api/health 仅 {"ok":true}；/api/auth/login 限流（M4-01 修复后）；/web 静态 dist 无秘密；统一 401 文案防探测——通过。
3. **上传**：扩展名+大小同步校验、后台 %PDF 魔数校验；safe_name 服务端 doc_id 前缀+分隔符替换（穿越不可行）；sha256 前置去重+锁内复查 TOCTOU 闭合；_run_ingest 异常兜底不外抛——通过（残留 M4-02/05 已处置）。
4. **路径穿越**：严格正则+realpath 包含性+symlink 经 resolve 覆盖——HTTP 资产面通过。
5. **SQL**：全参数化；update_task 动态 SET 列名硬编码+值参数化；MEMBER OF 参数化——无注入面。
6. **提示注入升格复查（m3 S4-12 预告项闭环）**：上传端点使语料可被任意 PDF 扩展，注入内容**持久化入库**影响后续查询（检索/重排/judge/生成）——**评 Low**（m3 为 Info；升格原因=存储型注入+不可信来源）。边界：无工具/无执行面，citations 纯正则，前端 React 纯文本转义（无 dangerouslySetInnerHTML/markdown 库→无 XSS sink）；单管理员=自注入自；**L1 多用户时必须升 Medium 并加隔离**。缓解建议：system prompt 声明"文档内容是数据非指令"+显式分隔标记。
7. **SSE/日志泄漏**：error 事件脱敏+截断；新增事件字段（model/empty_content/usage）非敏感——通过（任务 error 例外→M4-05 已修）。
8. **DoS**：登录限流（M4-01/04 处置）、上传 OOM（M4-02 记池）、SSE 并发（Info）、BM25 竞态（M4-06 记池）。

## 与 m2/m3 S4 遗留项对照
| 遗留项 | 状态 |
|---|---|
| m3 S4-10 db.py 无@形态脱敏 | 已修（此前落地） |
| m3 S4-11 _load_image_blob 读侧越界（绝对路径放行） | **未修**——逻辑平移至 pipeline.py:70-89 且单测固化；威胁链需 DB/Qdrant 篡改前置，维持 Low，**建议 M5 首项** |
| m3 S4-12 提示注入 Info（预告服务化升格） | 已升格复查→Low（见必查项 6） |
| m3 S4-13 fail_reason 截断过滤 | 未做，维持 Info |
| m2 S4-02 3306/6333 不可达 | 沿用；新增监听面 uvicorn 127.0.0.1:8000 同边界内 |
| m2 S4-04 pickle / S4-09 .env 写入 | 零新增（grep 证实） |
| m2 S4-07 / m3 S4-14 reports 公开性 | 未触碰，维持 |

## 加分实践
1. 全路由一把门：受保护路由集中 APIRouter dependencies，豁免显式三件（login/health/web），结构可审计。
2. 认证细节：统一 401 文案防探测、假哈希防时序、空凭据 fail-fast、改密全端吊销——均有单测。
3. 资产面架构性防御："绝不接受用户传路径"——回表映射+严格正则+realpath 包含性三层，单测覆盖。

## 修复记录
- S4 修复批：M4-01（IP-only 限流+单测）/M4-03（HMAC session_stamp）/M4-05（sanitize.py 统一口径）；196 passed。
- 记池：M4-02/M4-04/M4-06 + Info 择要（L1 前置项：jti 吊销/secret 长度/.env.example 补字段）。
