# M0 操作手册（Runbook）

> 对应 [doclens-multimodal-rag.plan.md](doclens-multimodal-rag.plan.md) §5 M0（骨架与环境，约 0.5–1 天）。
> 完成标准：六连测冒烟全绿 + `git tag m0`。当前形态（5 轮修订后）：**火山全链路单供应商**（嵌入/生成/上下文增强/LLM 重排，一把 ARK key）+ 服务器原生 MySQL（apt）/ Qdrant（静态二进制）；服务器为容器环境（无 Docker、apt 可用），本地运行应用 + git。

---

## 开工前盘点（20 分钟，全部打勾才开工）

### ① 服务器信息确认（SSH 登录后逐条执行）
- [ ] SSH 可登录：`ssh <用户>@<服务器IP>`（Windows 10+ 自带 OpenSSH 客户端）
- [ ] 环境性质：`ps -p 1 -o comm=`——输出 `systemd` = 有 systemd；其他（bash/sleep 等）= 你在容器里，进程自启靠 nohup 或管理员机制
- [ ] 系统与资源：`uname -a`（发行版，决定 mysql-server 还是 mariadb）、`df -h`、`free -h`
- [ ] apt 可用：`sudo apt update`（你已确认可行）
- [ ] 服务器内网 IP：`hostname -I`（写进本地 `.env` 的 MYSQL_URL/QDRANT_URL）
- [ ] 外网试探：`curl -sI https://github.com -m 5`——通 = 服务器直接 wget Qdrant 二进制；不通 = 本地下载后 scp

### ② 本地→服务器连通性（替代原"公网出口 IP"项——服务器无公网暴露，不需要白名单）
- [ ] `Test-NetConnection <服务器IP> -Port 22`（SSH 通）
- [ ] 端口 3306/6333 在 0.0.5 部署后复测

### ③ 火山方舟 API Key（本地操作；API 调用全走本地出口，服务器不需要外网）
- [ ] 登录 [volcengine 控制台](https://console.volcengine.com)（首次需实名认证）
- [ ] 火山方舟 →「API Key 管理」→ 创建 API Key → 复制保存（即 `ARK_API_KEY`）
- [ ] 「开通管理」页确认已开通：`doubao-embedding-vision`、`doubao-seed-2.1-pro`、`deepseek-v4-flash`（按 token 计费，开通即用；Coding Plan 订阅模型走 coding 端点）

### ④ 私有 git 远端
- [ ] GitHub（Settings → Developer settings → Personal access token）或 Gitee（国内网络更稳）新建 **Private** 仓库，**不勾选**初始化 README
- [ ] 本地推送：`git remote add origin <URL>` → `git push -u origin main`

### ⑤ 本地磁盘
- [ ] PowerShell `Get-PSDrive D | Select-Object Used,Free` → 剩余 ≥20GB（MinerU basic 模型 + 双 conda 环境）

---

## 0.0 服务器准备（SSH，一次性，约 1–2h）

### 0.0.1 建私有远端并首次推送
```bash
git remote add origin <私有仓库URL>
git push -u origin main        # 当前 1 commit（048a994）+ 本轮 specs 修订
```

### 0.0.2 MySQL：apt 原生安装（无 Docker）
```bash
sudo apt update && sudo apt install -y mysql-server   # Ubuntu；Debian 源里没有 mysql-server，见下方说明
sudo service mysql start || sudo systemctl enable --now mysql   # 容器里可能没有 systemd → service/mysqld 兜底
sudo mysql_secure_installation                         # 按提示做基础加固
sudo mysql <<'SQL'
CREATE DATABASE doclens CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'doclens'@'%' IDENTIFIED BY '<应用密码>';
GRANT ALL PRIVILEGES ON doclens.* TO 'doclens'@'%';
FLUSH PRIVILEGES;
SQL
```
允许本地机器远程连入（两处关键，缺一不可）：
- 编辑 `/etc/mysql/mysql.conf.d/mysqld.cnf`：`bind-address = 0.0.0.0`（或服务器内网 IP）→ `sudo service mysql restart`
- 账号必须是 `'doclens'@'%'`（上面 SQL 已是；`@'localhost'` 从本地连不进来）
- Debian 发行版：apt 里只有 `mariadb-server`——直接用 MariaDB 亦可（PyMySQL 完全兼容；本项目不在数据库侧做向量检索，无差别），坚持真 MySQL 则加 MySQL 官方 APT 仓库

### 0.0.3 Qdrant：静态二进制部署（无 Docker）
本地下载官方静态版（无依赖、任何 Linux 可跑；先在服务器试 `curl -sI https://github.com -m 5`，通就直接 wget，不通走 scp）：
```powershell
# https://github.com/qdrant/qdrant/releases → 资产 qdrant-x86_64-unknown-linux-musl.tar.gz
scp qdrant-x86_64-unknown-linux-musl.tar.gz <用户>@<服务器IP>:~/
```
服务器上部署：
```bash
mkdir -p ~/doclens/qdrant && tar xzf ~/qdrant-x86_64-unknown-linux-musl.tar.gz -C ~/doclens/qdrant
cd ~/doclens/qdrant
QDRANT__SERVICE__API_KEY="<强随机串>" nohup ./qdrant > qdrant.log 2>&1 &
sleep 2 && curl -s http://localhost:6333/healthz    # 服务器本机验证
```
进程守护：容器里通常没有 systemd → `nohup` 兜底；若管理员提供 systemd/supervisor 则用 unit 托管更稳（数据默认落 `./storage`，容器重启后由宿主/管理员机制拉起——找管理员确认容器常驻策略）。

### 0.0.4 安全基线（内网、无公网暴露面）
- MySQL：专用账号 `doclens`@`%`（非 root）；`bind-address` 内网可达即可，多人共用服务器时改 `127.0.0.1` 走隧道
- Qdrant：`QDRANT__SERVICE__API_KEY` 必设（防同网段其他机器误用）
- 同网段信任度低 → SSH 隧道：MySQL bind 改 `127.0.0.1`、Qdrant `service.host` 改 `127.0.0.1`，本地常驻 `ssh -N -L 3306:127.0.0.1:3306 -L 6333:127.0.0.1:6333 <用户>@<服务器IP>`，本地 `.env` 一律写 `127.0.0.1`

### 0.0.5 本地连通验证（PowerShell）
```powershell
Test-NetConnection <服务器内网IP> -Port 3306   # 走 SSH 隧道则测 127.0.0.1
Test-NetConnection <服务器内网IP> -Port 6333
curl http://<服务器内网IP>:6333/healthz
```

**验收**：两端口本地可达（方案 B 为隧道建立后可达）。

---

## 0.1 本地主环境 doclens（约 0.5h）

```bash
# conda 未入 PATH：用 Anaconda Prompt，或全路径 D:\soft\anaconda\condabin\conda.bat
conda create -n doclens python=3.12 -y
conda activate doclens
pip install -r requirements.txt -r requirements-dev.txt
pip list    # 核对清单
```

`requirements.txt` 初稿（安装后 `pip freeze` 锁版本回填）：
```
openai                 # 火山 OpenAI 兼容 chat/VLM 流式
httpx                  # /embeddings/multimodal 直调
pydantic-settings      # config.py 读 .env
PyMySQL[cryptography]  # MySQL 9 caching_sha2_password 需要 cryptography
qdrant-client          # url 模式
rank-bm25  jieba  numpy  pillow
fastapi  uvicorn[standard]  sse-starlette   # M4 用，M0 一并锁版
```
`requirements-dev.txt`：`pytest  pytest-cov  pip-audit`

**验收**：`pip list` 与清单一致。

---

## 0.2 MinerU 环境 doclens-mineru（约 1h，含模型下载）

```bash
conda create -n doclens-mineru python=3.12 -y
conda activate doclens-mineru
pip install "mineru>=4.0,<5"
mineru-kit models download --tier basic        # 或首次解析自动下载
```
样例解析（拿任一 PDF 试跑，CLI 子命令以 `mineru-kit --help` 为准）：
```bash
mineru-kit parse <样例.pdf> -o data/test/
```
记录：安装耗时、模型下载体积、单篇解析耗时（写入 0.5 成本表）。

**验收**：1 篇样例 PDF 解析成功，产出 content list JSON。
**风险触发线**：安装失败或解析过慢 → 试 flash tier 预筛；仍不行触发退 docling 预案（改动面仅 `mineru_parser.py`）。

---

## 0.3 配置骨架（约 1h）

建目录骨架：`doclens/`（含 parse/index/retrieve/generate/eval/serve 空包）、`scripts/`、`tests/`、`reports/`。

1. **`.gitignore`**：`data/`、`.env`、`*.db`、`__pycache__/`、`.venv*/`
2. **`.env.example`**（不含真实值）：
```bash
ARK_API_KEY=
ARK_BASE_URL=https://ark.cn-beijing.volces.com/api/coding/v3
ARK_EMBED_BASE_URL=            # 0.4 冒烟探测后回填（coding/v3 或 api/v3）
EMBED_MODEL=doubao-embedding-vision-251215
EMBED_DIMENSIONS=2048
GEN_MODEL=doubao-seed-2-1-pro-260915     # 以方舟模型列表页 Model ID 为准
CTX_MODEL=deepseek-v4-flash
RERANK_MODEL_FLASH=deepseek-v4-flash     # D 档两种重排器对比位之一
RERANK_MODEL_PRO=doubao-seed-2-1-pro-260915
MYSQL_URL=mysql+pymysql://doclens:<pwd>@<服务器IP>:3306/doclens
QDRANT_URL=http://<服务器IP>:6333
QDRANT_API_KEY=
```
3. **本地 `.env`**：填真实值（不入库）
4. **`config.py`**：pydantic-settings 读 `.env`；模型名集中（D3/D6/D7/D8）；消融档位 A–F 常量；`data/` 路径常量
5. **`tests/test_config.py`**：配置读取一条测试

**验收**：`pytest tests/test_config.py` 过；`git add && git commit`（M0 骨架）。

---

## 0.4 冒烟测试 scripts/smoke_test.py（约 1–2h）

六连测，每项打印结果 + 耗时（供 0.5 成本表用）：

| # | 测试 | 调用 | 预期 |
|---|---|---|---|
| 1 | MySQL 连通 | pymysql 连 `MYSQL_URL`，`SELECT 1` | 返回 1 |
| 2 | Qdrant 连通 | `QdrantClient(url, api_key).get_collections()` | 返回空集合列表 |
| 3 | 文本嵌入 | POST `{ARK_EMBED_BASE_URL}/embeddings/multimodal`，text 输入 + Query 侧 instructions | 2048 维向量；**先探 coding/v3，404/拒绝则改 api/v3 并回填 `.env` 的 `ARK_EMBED_BASE_URL`** |
| 4 | 图像嵌入 | 同端点，`data:image/png;base64,…` 单图输入 + Corpus 侧 instructions | 向量返回 |
| 5 | LLM 重排 | `deepseek-v4-flash` 列表式：1 query + 5 个编号候选块 → 温度 0 输出排序 | 返回合理排序 |
| 6 | VLM 生成（火山） | doubao-seed-2-1-pro：带图 chat + `stream=True` | 流式 chunk 正常 |

Query/Corpus 分侧 instructions 按官方模板（跨模态问答场景）：
```
Query 侧：Target_modality: text/image.\nInstruction:根据这个问题，找到能回答这个问题的相应文本或图片\nQuery:
Corpus 文本：Instruction:Compress the text into one word.\nQuery:
Corpus 图片：Instruction:Compress the image into one word.\nQuery:
```

**验收**：六项全绿；`ARK_EMBED_BASE_URL` 探测结论已回填 `.env`（**M0 决策点 ①**）。

---

## 0.5 成本核算表 reports/cost.md（约 0.5h）

按方舟定价页核算：
- 嵌入：文本 token 单价；图像 token = `min(宽×高÷784, 单图上限)`，按 10 篇论文估块数/图数
- 生成：doubao-seed-2.1-pro 输入/输出单价；E 档 deepseek-v4-flash 一次性前缀成本（100 块小样实测再放大）
- 重排：LLM 列表式（top-50 ≈ 10k–20k 输入 token/查询，flash 与 pro 两种对比位），按方舟 token 价 × 评测查询数估算
- 本地成本：MinerU 解析耗时（0 API 费）、服务器进程资源占用（MySQL/Qdrant）
- 记录：Coding Plan 额度覆盖嵌入的结论（探测结果）

**验收**：表产出，含每千块/每千图的估算行。

---

## 收尾

```bash
git add -A && git commit -m "M0: 环境/配置/冒烟/成本核算"
git tag m0 && git push origin main --tags
```

---

## M0 内必须拍板的 3 个决策点

| # | 决策 | 依据 | 落点 |
|---|---|---|---|
| ① | 嵌入走 coding/v3 还是 api/v3 | 0.4 第 3 项探测结果 | `.env` 的 `ARK_EMBED_BASE_URL`；写入 cost.md 额度结论 |
| ② | MinerU 是否可用 | 0.2 安装+解析实测 | 可用 → 继续；不可用 → flash tier → 退 docling |
| ③ | 内网直连还是加 SSH 隧道 | 0.0.4（同网段信任度） | 服务监听地址（MySQL bind-address / Qdrant host）+ 本地 `.env` 写法 |
