---
okf: v0.1
type: Reference
title: Portal Compose 与路由
tags: [portal, nginx, docker]
timestamp: 2026-07-24
resource: ai_access_poc/portal/docker-compose.yml
---

# Compose 与路由

## 服务

| 服务 | 镜像/构建 | 端口 |
|------|-----------|------|
| `portal-nginx` | nginx:1.27-alpine | `${PORTAL_PORT:-8088}:80` |
| `ops-stub` | `./ops_stub` | `${OPS_STUB_PORT:-8090}:8090` |
| `dingtalk-oidc` | `new-api-dingtalk-oidc`（profile） | 仅 Docker 内网 8086 |

## 网络

| 网络 | 类型 | 用途 |
|------|------|------|
| `portal` | bridge | nginx ↔ ops-stub ↔ oidc |
| `open_webui_public` | **external** | 到达已运行的 `open-webui` |

## 路由表

| 对外路径 | 上游 |
|----------|------|
| `/` | 静态落地页 |
| `/health` | nginx 内联 JSON |
| `/chat/` | `open-webui:8080/`（strip 前缀） |
| `/_app/` `/static/` `/api/` `/ws` … | `open-webui:8080`（根路径劫持） |
| `/ops/` | `ops-stub:8090`（保留 `/ops` 前缀） |
| `/oidc/` | `dingtalk-oidc:8086/`（strip；down → dry-run JSON） |

## 卷

| 宿主机 | 容器 |
|--------|------|
| `../board/out` | `/data/board_out:ro`（ops-stub） |
