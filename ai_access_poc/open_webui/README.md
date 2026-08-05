# FZH AI Shell PoC — Open WebUI

浏览器壳：Open WebUI + **Docker-only** Open Terminal + 赛狐只读拉取 Tool。

上游计划：[docs/research/2026-07-24-unified-ai-access-poc-plan.md](../../docs/research/2026-07-24-unified-ai-access-poc-plan.md)

## 快速启动

```bash
cd ai_access_poc/open_webui
cp .env.example .env
# 编辑 .env：OPENAI_API_KEY、OPEN_TERMINAL_API_KEY（长随机串）

docker compose up -d
```

- Web UI: http://localhost:3000  
- 首次打开创建管理员账号  
- Open Terminal **不映射宿主机端口**（仅 Docker 内网）；在 OWUI 里用 Admin → Integrations → Open Terminal 配置：
  - URL: `http://open-terminal:8000`
  - API Key: 与 `.env` 中 `OPEN_TERMINAL_API_KEY` 相同

### 首次启动注意（本机实测）

默认会从 HuggingFace 拉 `sentence-transformers`，国内网络常卡在 `Fetching 30 files: 0%`，health 长时间 `unhealthy`。  
本 compose 已默认：

- `HF_ENDPOINT=https://hf-mirror.com`
- `RAG_EMBEDDING_ENGINE=openai`（走 `api.vilavi.cn`，跳过本地下载；RAG 非本 PoC 关键路径）

仍需在 `.env` 填入可用的 `OPENAI_API_KEY`，否则聊天无模型可选。

## 接 api.vilavi.cn 模型

`.env` 已默认：

```text
OPENAI_API_BASE_URL=https://api.vilavi.cn/v1
OPENAI_API_KEY=sk-...   # 公司 new-api 个人 Token（https://api.vilavi.cn/ 钉钉登录复制）
```

字段名是 OpenAI 兼容约定，**不是** OpenAI 官方 Key。可用模型含 DeepSeek V4 Flash / Pro 等。

Admin → Settings → Connections 确认 OpenAI 兼容连接指向该 Base URL。用任意对话冒烟即可（S2）。

> **本机实测**：若首次启动时 `.env` 里还是 `sk-replace-me`，OWUI 会把占位 Key 写入内部 DB；之后只改 `.env` 不够，需到 **Admin → Settings → Connections → 齿轮** 把 API Key 改成真实 Token 并 Save。

## 安装赛狐 Tool（S3）

**两种凭证（优先代理）**：

| 方式 | 变量 | 何时用 |
|------|------|--------|
| **代理（默认）** | `SELLFOX_PROXY_API_KEY` | 任意机器；`https://api.vilavi.cn/sellfox/admin` 钉钉取 Key |
| **直连（备用）** | `SELLFOX_APP_ID` + `SELLFOX_APP_SECRET` | 仅 VPS 白名单 IP；官方 `openapi.sellfox.com` |

1. 管理员登录 → **Workspace → Tools → +**  
2. 粘贴 [tools/sellfox_pull_sp_search_term.py](tools/sellfox_pull_sp_search_term.py) 全文（或从该文件 Import）  
3. **Valves** 优先填 `SELLFOX_PROXY_API_KEY`（也可依赖 compose 注入的同名环境变量）；直连仅作 fallback  
4. `REPORT_DIR` 保持 `/data/sellfox_reports`（已挂载到本目录 `./reports`）  
5. **把 Tool 绑到模型（默认自动启用）**：Workspace → Models → 编辑 `deepseek-v4-flash` → Tools 勾选本 Tool → Save。之后新对话无需每次手动开 Available Tools  
6. **不要**给运营「创建 Tool」权限  

Tool v0.3+ 会在拉取后返回 `summary.totals` 与 `summary.top_by_spend_csv`，模型应据此分析，不要再说「xlsx 读不了」。已有文件可用 `sellfox_summarize_search_term_xlsx`。

宿主机无 CLI 自测（不经过 OWUI）：

```bash
# 在仓库根目录；优先读根 .env 的 SELLFOX_PROXY_API_KEY
uv run python ai_access_poc/open_webui/scripts/pull_search_term_cli.py --days 7 --shop-name "店名片段"
```

## 安装 Skill（S4）

Workspace → Skills → Import → 选择 [skills/sellfox-search-term-pull.md](skills/sellfox-search-term-pull.md)。  
聊天中 `$赛狐搜索词拉取` 或绑到模型。

## 运营试用脚本（口头步骤）

1. 打开 http://localhost:3000，登录  
2. **选模型「FZH 赛狐只读分析 (DeepSeek Flash)」**（`fzh-sellfox-ops`，已绑 Tool+Skill）  
3. 输入：`列出店铺，然后拉 TOODDLY-Daneey-US 最近 7 天搜索词，用 summary 做只读分析`  
4. 确认回报有 `filepath`、`summary.totals`，且 `./reports/` 有 xlsx  
5. 深挖：Integrations 开 **Open Terminal**（不要同时开 Code Interpreter），对 `/data/sellfox_reports/...xlsx` 用 Python（openpyxl）  
6. 确认助手**没有**声称已下否词 / 改竞价  

Agent 交接细节：[AGENT_HANDOFF.md](AGENT_HANDOFF.md) · OKF：[../docs/index.md](../docs/index.md)

## Code Interpreter vs Open Terminal

| | Code Interpreter | Open Terminal |
|--|------------------|---------------|
| 引擎 | **Pyodide（legacy）** | Docker Linux（**推荐**） |
| 同聊 | 与 Terminal **互斥** | 与 CI **互斥** |
| 适合 | 粘贴 CSV / 小计算 | 读挂载卷 xlsx、shell |
| 注意 | API 路径常不真执行；真跑在浏览器 | slim：**无 pandas**；openpyxl 勿 `read_only` |

正式分析路径：**Tool summary → Open Terminal**。CI 仅作对照/零配置演示。

## 安全

- Open Terminal：**只用 Docker**（compose 已强制）；勿改 bare metal  
- 报告目录 gitignore；勿提交 xlsx / `.env`  
- 本 PoC **无广告写操作**

## 目录

```text
docker-compose.yml
.env.example
AGENT_HANDOFF.md
tools/sellfox_pull_sp_search_term.py
skills/sellfox-search-term-pull.md
scripts/          # CLI / 验收辅助
reports/          # runtime output (gitignored)
```
