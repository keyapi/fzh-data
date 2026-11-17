---
okf: v0.1
type: Log
title: architecture-patterns — 变更日志
tags: [solutions, architecture-patterns, log]
---

# architecture-patterns 变更日志

## 2026-11-17

- **新增**: `office-dual-wan-direct-ssid.md` — 办公室双 WAN 与「直连 SSID」设计：H3C 在 OpenWrt 下游（默认路由 → OpenWrt LAN），客户端被 NAT 成单一源 IP，所以去掉代理只能走 WAN2；含 2026-11-17 实机盘点（WAN1/WAN2 静态地址、多WAN 当前是"平均分配"、现成的 VLAN1→WAN2 策略路由是禁用的）、新增 VLAN+SSID+策略路由顺序、**Tailscale `100.64/10` 必须做 PBR 例外**、静态DNS 指向 `192.168.1.5` 而非 `.242` 的理由、以及链路探测/回切需实测的边界。

## 2026-09-22

- **新增**: `public-private-agent-knowledge-split.md` — 公开仓、私有 Markdown 知识仓与 secret manager 三层分离；普通 clone + bootstrap 代替 submodule，保留 Agent 检索和非技术同事使用体验。
