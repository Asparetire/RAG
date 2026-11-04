---
description: 安全专项复查——认证/授权/API/敏感数据场景下的 OWASP 逐项审查
argument-hint: [范围，缺省为本次改动]
allowed-tools: Read, Grep, Glob, Bash, Write
---

# /security-scan — 安全专项复查

范围：$ARGUMENTS（缺省：本次改动）

按技能 **ai-workflow** 的 **S4 安全专项复查** 执行。**仅敏感代码触发**；若 review.md 已判定非敏感，请说明并停止。

## 判定

命中任一即敏感：认证、授权、会话、JWT/OAuth、密码、MFA；外部 API/Webhook/第三方 SDK、网络出口、SSRF；敏感数据（PII、支付、密钥、token、凭据、审计）；文件上传下载、反序列化、SQL/命令拼接、模板渲染；依赖新增升级；加密与哈希。

## 检查项（逐条给结论：通过 / 需修复 / 不适用）

1. 注入：SQL/ORM、命令、模板、日志注入；参数化是否到位。
2. 鉴权与越权：横向/纵向越权、IDOR、资源归属校验、默认拒绝。
3. 认证流程：token 生命周期、刷新、重放、限速、登出失效、时序侧信道。
4. 凭据管理：无硬编码密钥、无入日志/入仓库、环境隔离、`.env` 未提交。
5. 数据保护：传输加密与 TLS 校验、存储加密、日志脱敏、错误信息不泄露内部细节。
6. Web 面：CORS、CSRF、Cookie（HttpOnly/Secure/SameSite）、CSP。
7. 文件与反序列化：路径穿越、白名单、大小限制、安全解析。
8. 依赖与供应链：运行项目自带审计命令（`npm audit` / `pip-audit` / `cargo audit` / `govulncheck`），如不可用则写明。
9. 第三方调用：超时、重试、证书校验、密钥作用域最小化。

## 输出

写 `specs/reviews/<slug>.security.md`：结论（通过 / 有条件通过 / 不通过）+ 检查表 + 修复清单（文件:行 + 具体改法）+ 复测结果。

**不通过** → 必须修复并复测通过才能进入收尾；连续 3 次未修复则停止并报告。
