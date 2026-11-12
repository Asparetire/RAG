# M4 S3 代码审查报告

- 审查者：独立代码审查代理（只读审查；行号以 HEAD f4898ab 为准）
- 日期：2026-11-12
- 范围：M4 全部新增/修改代码——doclens/{pipeline,serve/auth,serve/api,serve/assets,paperlib,config,generate/vlm}.py、scripts/{init_db,query_cli}.py、web/src/**、tests/{test_pipeline,test_sse_contract,test_serve_assets,test_auth}.py
- 处置结论：**1 Blocker + 5 Major 全部修复并实测**（见文末修复记录），Minor 随批修 3 条，其余记待办池。

## 结论
需修复后收官 → **修复批 4256f96 已落地**，回归 195 passed。

## 问题清单与处置

### Blocker
- **B-1 paperlib._run_ingest 只调 validate_pdf 未落 canonical**（data/pdfs/{doc_id}.pdf 永不生成）——`/api/docs/{doc_id}/pdf` 对上传论文 404、重试端点恒报"canonical 不存在"，论文库预览链路断。
  **修复（4256f96）**：解析前显式 `shutil.copy2` 落 canonical；容器实测上传后 canonical 存在（28279 bytes）。

### Major
- **M-1 `_subtree_ids` 用 `%s IN (ancestor_ids)` 对 JSON 列做成员判断**——MySQL IN 不展开 JSON 数组，恒假，只剩 id=%s 生效：delete 可删含子分类的父（子树孤儿）、move 级联空转致 ancestor_ids 陈旧、环检测失真可成真环。
  **修复（4256f96）**：改 `CAST(%s AS JSON) MEMBER OF (ancestor_ids)`；容器三层树实测 PASS（子树查询命中正确）+ 环检测拦截 PASS。
- **M-2 upload `category_id` 未标 Form()**——FastAPI 归为 query 参数，前端 FormData 分类字段被静默忽略，"上传到当前分类"失效。
  **修复（4256f96）**：`Annotated[int | None, Form()] = None`。
- **M-3 vite 未设 base 而 SPA 挂 /web**——交付态 JS/CSS/cMaps 全 404 白屏。
  **修复（4256f96+6a6cf70）**：`base: '/web/'` 重建 dist；容器实测 /web/ 页面引用 /web/assets/ 且 JS 200。
- **M-4 admin_password/jwt_secret 默认空串无启动校验**——空密码可登录、空 secret 可伪造 token。
  **修复（4256f96）**：create_app fail-fast（auth_enabled=True 且两值为空 → RuntimeError）。
- **M-5 sweep_stale_tasks 零调用**——重启后任务永久悬挂。
  **修复（4256f96）**：create_app 接线启动扫描（幂等；失败不阻塞启动）。

### Minor（随批修 3）
- **m-1** list_papers 状态列取到分类名（r[4]）而非任务状态（r[5])——error 状态被遮蔽。**已修**（4256f96）。
- **m-2** 登录限流 key 不含真实 IP（全局共享桶，错 5 次锁死管理员）。**已修**（4256f96，Request 注入 client.host）——后续 S4 M4-01 进一步改为 IP-only。
- **m-6** ChatPane Enter 未判 isComposing，中文输入法选词回车误发送。**已修**（4256f96）。

### Minor（记待办池）
- m-3 非 vision 模型未过滤图片 parts（选 kimi-k3/deepseek 带图上下文会 400）；模型选择 cookie 持久化未实现。
- m-4 上传整体读内存后才校验 100MB（multipart 无请求体上限）。
- m-5 vlm 每请求 new AsyncOpenAI 不关闭；K7 重试二次发整段 reasoning（思考面板重复拼接）；_ctx_prefixes 同步 DB 压事件循环。
- m-7 paperlib 423 行 0 测试（M-1/M-2 正因此漏网）；refused 路径/断连取消/上传端点无契约用例。

### Nit（记录）
- n-1 死代码 shutil/无意义 completed_chunks=None/list_tree user_id 未用；n-2 ORDER BY 语义反直觉（前端自组树无实害）；n-3 Message 条件 hook+每 token 全量写 localStorage（O(n²) 可节流）；n-4 assets 复用私有 _fetch_members/PDF_DIR 重复定义/折叠切换写法隐晦。

## 亮点
1. 契约测试设计扎实：mock 管线注入断言冻结事件序+schema+error 脱敏；K12 服务端白名单校验回退双层防御。
2. K7 守卫抽成纯函数全路径单测；编排抽共享管线后 query_cli 238 行削成薄壳，CLI/SSE 单一编排源落地。
3. assets.py 路径安全层干净：严格正则+realpath 包含性+统一 None→404 不回显，穿越用例成体系。

## 修复记录
- 修复批：4256f96（B-1/M-1/M-2/M-4/M-5/m-1/m-2/m-6）+ 6a6cf70（M-3 dist 重建）
- 回归：195→196 passed；容器实测：M-1 MEMBER OF 三层树+环检测 PASS、M-3 资源 200、B-1 canonical 28279 bytes
