---
okf: v0.1
type: Log
title: architecture-patterns — 变更日志
tags: [solutions, architecture-patterns, log]
---

# architecture-patterns 变更日志

## 2026-11-02

- **更新**: `pb-orders-json-api-human-agent.md` — JSON API 已部署到 `api.vilavi.cn/pb/`（PR #297 仍未合并）。判定在不在跑看 healthz 是否 JSON；compose 服务名是 `pb-orders-web`；API 未上镜像时用签会话 cookie 走出件 HTML 路由，且必须打公网 `/pb/`（CSRF Path）。

## 2026-09-22

- **新增**: `public-private-agent-knowledge-split.md` — 公开仓、私有 Markdown 知识仓与 secret manager 三层分离；普通 clone + bootstrap 代替 submodule，保留 Agent 检索和非技术同事使用体验。
