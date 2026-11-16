# 服务器栈部署说明（前置）

DocLens 的应用跑在服务器容器内（VS Code Remote-SSH 直达），本页列全新服务器的栈前置。

## 1. 基础栈

| 组件 | 版本要点 | 说明 |
|---|---|---|
| MySQL 8 | utf8mb4，库 `doclens` | 应用账号 `hifen37`；3306 仅容器内可达 |
| Qdrant | 静态二进制部署 | 6333 仅容器内可达 |
| Miniconda | conda 26.x | 环境 `doclens`（应用）+ `doclens-mineru`（PDF 解析） |
| MinerU | mineru-kit ≥ 4.x | 模型 2.0 GB 落 `/root/.mineru/models/`（容器重建需重下） |

## 2. 数据库初始化

```bash
python scripts/init_db.py    # 幂等：9 张表 + t_doc 补列
```

## 3. 端口边界（重要）

- 3306/6333 **未对外发布**：容器内 127.0.0.1 直连；Windows 开发场景走 SSH 隧道（13306/16333）
- Web 服务 8000 也只绑 127.0.0.1——对外访问走 SSH 隧道 8000 或反向代理（自行配置）

## 4. 常见坑

- pip 默认源切清华镜像（pypi.org 直连不可达）
- MinerU 模型在容器重建后需重新下载（2.0 GB）
- 同一 PyMySQL 包勿混装版本（1.2.x 与 2.x 的 `Connection.begin()` 语义不同——本项目锁 1.2.4 并在代码里显式事务）
