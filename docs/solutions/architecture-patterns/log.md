---
okf: v0.1
type: Log
title: architecture-patterns — 变更日志
tags: [solutions, architecture-patterns, log]
---

# architecture-patterns 变更日志

## 2026-10-28

- **新增**: `shared-egress-vps-venv-systemd-no-docker.md` — 承载 Tailscale/CLIProxyAPI 应急出口的 VPS 上，新服务用 venv+systemd 绑定 127.0.0.1；不装 Docker，避免 iptables/NAT 变化影响既有转发。

## 2026-09-22

- **新增**: `public-private-agent-knowledge-split.md` — 公开仓、私有 Markdown 知识仓与 secret manager 三层分离；普通 clone + bootstrap 代替 submodule，保留 Agent 检索和非技术同事使用体验。
