# AGENT_HANDOFF — ai_access_poc / Portal

> Agent 入口。人读 `portal/README.md`；OKF 见 `portal/docs/`。

## 目标（Portal PoC）

同域 nginx：`/chat` → OWUI 壳，`/ops` → 板 stub；钉钉 OIDC 配置 + dry-run。  
**不做**：生产上线、运营审签字、赛狐写、整仓 vendoring IvyeaOps。

上游：`docs/research/2026-07-24-unified-ai-access-independent-review.md` §8.4；计划 Portal 切片。

## 栈

| 组件 | 说明 |
|------|------|
| `portal-nginx` | `nginx:1.27-alpine`，宿主机 `${PORTAL_PORT:-8088}` |
| `ops-stub` | FastAPI，读 `../board/out`，路径前缀 `/ops` |
| `open-webui` | **外部** compose（`ai_access_poc/open_webui`），网络 `open_webui_public` |
| `dingtalk-oidc` | profile `dingtalk`，复用 `new-api-dingtalk-oidc/` |

## OWUI 子路径说明

官方不支持真正的 `/chat` base path。本 PoC：

1. `/chat/` strip 前缀反代到 OWUI
2. 同时劫持 OWUI 根路径资产：`/_app/` `/static/` `/api/` `/ws` `/ollama/` `/openai/` `/oauth/`
3. `/ops` 全部命名空间化，避免与 OWUI `/api` 冲突

生产更稳的方案是子域（`chat.` / `ops.`）；PoC 验证同域路径入口。

## 启动

```powershell
cd ai_access_poc/portal
powershell -ExecutionPolicy Bypass -File scripts/start_portal.ps1
uv run python scripts/e2e_verify.py
```

勿用 PowerShell `Start-Job` 启服务（Lesson 58）。uvicorn 在 stub Dockerfile 已 `--log-level info`（Lesson 59）。

## 环境变量（名；值勿提交）

见 `.env.example`：`PORTAL_*`、`IVYEAOPS_UPSTREAM`、`DINGTALK_*`、`OIDC_ISSUER`、`ALLOWED_CORP_ID`。

## 完整 IvyeaOps UI

仓外 `d:\Work\赛狐\IvyeaOps-sellfox`（无预构建 `client/dist` 时优先 stub）。  
可选 `IVYEAOPS_UPSTREAM=http://host.docker.internal:8001` → `/ops/api/ivyeaops/health`。

## 运营审

**DEFERRED** — 不阻塞本 PR。
