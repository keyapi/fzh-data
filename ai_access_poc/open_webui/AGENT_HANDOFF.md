# AGENT_HANDOFF — ai_access_poc / Open WebUI 壳

> Agent 入口。人读优先 `open_webui/README.md`；OKF 见 `ai_access_poc/docs/`。

## 目标（壳 PoC）

浏览器 Chat → 赛狐只读 Tool 拉 SP 搜索词 → xlsx 落盘 + **JSON summary** →（可选）Docker Open Terminal 深挖。  
**不做**：广告写/否词执行、运营看板、Portal/nginx、板 PoC（IvyeaOps）。

上游计划：`docs/research/2026-07-24-unified-ai-access-poc-plan.md`（S1–S4）。  
运行模式经验：`docs/solutions/tooling-decisions/owui-sellfox-xlsx-tool-summary-open-terminal.md`。

## 栈

| 组件 | 说明 |
|------|------|
| Open WebUI | `ghcr.io/open-webui/open-webui:main`，端口 `${OWUI_PORT:-3000}` |
| Open Terminal | `ghcr.io/open-webui/open-terminal:slim`，**仅 Docker 内网**，无宿主机端口 |
| 模型网关 | `OPENAI_API_BASE_URL=https://api.vilavi.cn/v1`（公司 Token，非 OpenAI 官方） |
| 赛狐 | 优先 `SELLFOX_PROXY_API_KEY` → `api.vilavi.cn/sellfox`；直连 AppId/Secret 备用 |
| 共享客户端 | `SELLFOX_API/client.py`（`mode=proxy\|direct`，限流重试） |

## 关键路径

```bash
cd ai_access_poc/open_webui
cp .env.example .env   # 填 OPENAI_API_KEY、OPEN_TERMINAL_API_KEY、SELLFOX_PROXY_*
docker compose up -d
# UI http://127.0.0.1:3000 — 首次建管理员
```

Open Terminal 在 Admin → Settings → Integrations → Open Terminal：

- URL: `http://open-terminal:8000`
- Key: 与 `.env` 的 `OPEN_TERMINAL_API_KEY` 一致

## Workspace 对象（本机 PoC 约定）

| 类型 | ID / 名 |
|------|---------|
| Tool | `sellfox_sp_search_term_pull`（源：`tools/sellfox_pull_sp_search_term.py`，v0.3+） |
| Skill | `sellfox-search-term-pull` |
| 自定义模型 | `fzh-sellfox-ops` /「FZH 赛狐只读分析 (DeepSeek Flash)」— 默认绑 Tool+Skill，`function_calling=native` |

运营应选 **自定义模型**，不要依赖裸 `deepseek-v4-flash` 手动勾 Tools。

## 分析路径（铁律）

| 能力 | 用途 | 注意 |
|------|------|------|
| Tool `summary` | 大盘 totals + top 花费词 CSV | 禁止再说「xlsx 读不了」 |
| Open Terminal | 对 `/data/sellfox_reports/*.xlsx` 跑 Python | slim：**openpyxl 有、pandas 无**；禁用 `read_only=True` |
| Code Interpreter | Admin 可开，引擎 **pyodide（legacy）** | 与 Terminal **同聊互斥**；真执行在浏览器；API 不跑 Pyodide |

默认模型能力倾向 Terminal（`code_interpreter: false`）；对照演示可临时开 CI。

## 环境变量（名；值勿提交）

`OPENAI_API_KEY`、`OPENAI_API_BASE_URL`、`OPEN_TERMINAL_API_KEY`、`SELLFOX_PROXY_API_KEY`、`SELLFOX_PROXY_BASE_URL`、`SELLFOX_PROXY_ACCOUNT`、`SELLFOX_APP_ID`、`SELLFOX_APP_SECRET`、`HF_ENDPOINT`、`RAG_EMBEDDING_ENGINE`、`RAG_EMBEDDING_MODEL`、`OWUI_PORT`

## 常见故障

1. UI unhealthy / HF 卡住 → compose 已设镜像与 openai embedding；仍需有效 `OPENAI_API_KEY`
2. 改 `.env` 仍无模型 → Admin → Connections 改掉首次写入的占位 Key
3. Tool 不触发 → 换 `fzh-sellfox-ops` 或手动 Available Tools
4. Terminal 读 xlsx 列错 → 去掉 openpyxl `read_only`
5. 限流 → `SELLFOX_API/client.py` 已有重试；缩小店铺/天数

## 脚本

- `scripts/pull_search_term_cli.py` — 宿主机拉数自测
- `scripts/create_owui_tool.py` / `enable_terminal_and_demo.py` / `audit_owui_ceiling.py` / `demo_code_interpreter.py` / `complex_ceiling_demo.py` — 运维/验收，勿提交密钥

## 验收快照（2026-07-24）

店铺 TOODDLY-Daneey-US，近 7 天：1922 行，spend 1663.32，sales 4697.22，ACOS 0.3541；Tool summary / Terminal / CI（贴 CSV）数字对账。

## 下一步（非本壳）

板 PoC：IvyeaOps fork → `sellfox_openapi` → `sellers` + 搜索词规范化 cache → optimizer 只读候选（关写）。两条绿后再 Portal。
