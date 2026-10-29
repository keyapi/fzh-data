---
okf: v0.1
type: Log
title: architecture-patterns — 变更日志
tags: [solutions, architecture-patterns, log]
---

# architecture-patterns 变更日志

## 2026-10-29

- **新增**: `wayfair-cg-stock-table-and-parquet-grain.md` — 一张 DocType 同时放 CG 总计行（warehouse_id=CG）与分仓行；无位置 part 进目录；Parquet 按粒度拆两份（total / warehouse），不让两种粒度混在一张表里被 SUM；发布同事务、同粒度对账。

## 2026-10-28

- **新增**: `shared-egress-vps-venv-systemd-no-docker.md` — 承载 Tailscale/CLIProxyAPI 应急出口的 VPS 上，新服务用 venv+systemd 绑定 127.0.0.1；不装 Docker，避免 iptables/NAT 变化影响既有转发。

## 2026-09-22

- **新增**: `public-private-agent-knowledge-split.md` — 公开仓、私有 Markdown 知识仓与 secret manager 三层分离；普通 clone + bootstrap 代替 submodule，保留 Agent 检索和非技术同事使用体验。
