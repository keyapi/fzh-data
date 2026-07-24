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

## 接 api.vilavi.cn 模型

`.env` 已默认：

```text
OPENAI_API_BASE_URL=https://api.vilavi.cn/v1
OPENAI_API_KEY=sk-...
```

Admin → Settings → Connections 确认 OpenAI 兼容连接指向该 Base URL。用任意对话冒烟即可（S2）。

## 安装赛狐 Tool（S3）

1. 管理员登录 → **Workspace → Tools → +**  
2. 粘贴 [tools/sellfox_pull_sp_search_term.py](tools/sellfox_pull_sp_search_term.py) 全文（或从该文件 Import）  
3. **Valves** 填写 `SELLFOX_APP_ID` / `SELLFOX_APP_SECRET`（来自 `SELLFOX_API/.env`，仅管理员）  
4. `REPORT_DIR` 保持 `/data/sellfox_reports`（已挂载到本目录 `./reports`）  
5. 把 Tool 绑到模型；**不要**给运营「创建 Tool」权限  

宿主机无 CLI 自测（不经过 OWUI）：

```bash
# 在仓库根目录，需已配置 SELLFOX_API/.env
uv run python ai_access_poc/open_webui/scripts/pull_search_term_cli.py --days 7 --shop-name "店名片段"
```

## 安装 Skill（S4）

Workspace → Skills → Import → 选择 [skills/sellfox-search-term-pull.md](skills/sellfox-search-term-pull.md)。  
聊天中 `$赛狐搜索词拉取` 或绑到模型。

## 运营试用脚本（口头步骤）

1. 打开 http://localhost:3000，登录  
2. 新对话，启用 Tool「Sellfox SP Search Term Pull」  
3. 输入：`用赛狐搜索词拉取技能，列出店铺，然后拉最近 7 天搜索词`  
4. 确认回报里有 `filepath` 且 `./reports/` 出现 xlsx  
5. 确认助手**没有**声称已下否词 / 改竞价  

## 安全

- Open Terminal：**只用 Docker**（compose 已强制）；勿改 bare metal  
- 报告目录 gitignore；勿提交 xlsx / `.env`  
- 本 PoC **无广告写操作**

## 目录

```text
docker-compose.yml
.env.example
tools/sellfox_pull_sp_search_term.py
skills/sellfox-search-term-pull.md
scripts/pull_search_term_cli.py
reports/          # runtime output (gitignored)
```
