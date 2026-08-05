---
okf: v0.1
type: Reference
title: Compose 与环境变量
tags: [reference, docker, open-webui]
timestamp: 2026-07-24
resource: ai_access_poc/open_webui/docker-compose.yml
---

# Compose 与环境变量

## 服务

| 服务 | 镜像 | 网络 |
|------|------|------|
| `open-webui` | `ghcr.io/open-webui/open-webui:main` | public + internal |
| `open-terminal` | `ghcr.io/open-webui/open-terminal:slim` | **仅 internal**（无宿主机端口） |

## 卷

| 宿主机 | 容器 |
|--------|------|
| `./reports` | `/data/sellfox_reports`（OWUI + Terminal） |
| `./tools` | `/data/fzh_tools:ro`（OWUI） |

`reports/` 运行产物须 gitignore，勿提交 xlsx。

## 环境变量（名）

见 `open_webui/.env.example`：`OPENAI_*`、`OPEN_TERMINAL_API_KEY`、`SELLFOX_PROXY_*`、`SELLFOX_APP_*`、`HF_ENDPOINT`、`RAG_EMBEDDING_*`、`OWUI_PORT`。

## Open Terminal 连接

OWUI 内：`http://open-terminal:8000` + Bearer `OPEN_TERMINAL_API_KEY`。  
勿映射 `:8000` 到宿主机（PoC 安全约定）；调试可临时 uncomment ports。
