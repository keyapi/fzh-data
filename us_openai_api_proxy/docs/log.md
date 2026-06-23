---
okf: v0.1
type: Log
title: 变更日志
description: US OpenAI API Proxy 模块的时序变更记录
tags: [openai, api-proxy, changelog]
---
# 变更日志

## 2026-06-23 (v0.8)

- **v0.8**: Tailscale 安全升级 v1.32.3 → v1.98.4 (手动静态二进制替换, arm64)
- **v0.8**: 验证新版 iptables 规则 — ts-forward MARK 方向未变化, 手工 MASQUERADE 仍需保留
- **v0.8**: 升级后重新认证, 所有节点正常, 手机 new-api + 翻墙正常

## 2026-06-23 (v0.7)

- **v0.7**: 方案 A 实施完成 — 办公室全员可通过路由器访问 Tailscale 网络
- **v0.7**: OpenWrt R68S 安装 Tailscale v1.32.3 + 防火墙 zone 配置 + LAN↔tailscale 转发
- **v0.7**: 关键修复: MASQUERADE on tailscale0 (ts-forward MARK 只匹配入站，出站无 SNAT)
- **v0.7**: 回程路由: 192.168.10.0/24 via 192.168.100.181 (新华三 LAN 子网)
- **v0.7**: 新华三 ER3208G3-P-E 静态路由: 100.64.0.0/10 → 192.168.100.1 (WAN1)
- **v0.7**: 验证通过: 手机 (无 Tailscale) 访问 new-api + 翻墙均正常
- **v0.7**: 踩坑 5 条: 防火墙冲掉 iptables / MARK 方向 / 三层 NAT 回程 / 新华三 LuCI 混淆 / Hash 路由

## 2026-06-23 (v0.6)

- **v0.6**: 新增 `docs/office-lan-access.md` — 办公室全员访问 Tailscale 5 种方案全景 (OpenWrt/PC网关/公网/全员Tailscale/Subnet Router)
- **v0.6**: 方案 A (OpenWrt 路由器) 详细部署步骤 — 当前优先级最高

## 2026-06-22 (v0.5)

- **v0.5**: Lesson 25 — docker-compose 必须自包含 (漏 SQL_DSN → 降级 SQLite), 必须从官方 compose 出发
- **v0.5**: Lesson 26 — Docker bridge 无法访问宿主机 Tailscale (经典冲突, iptables MASQUERADE 修复, 附 5 个社区链接)

- **v0.5**: 上海 ERPNext 测试服务器加入 Tailscale (100.119.28.72)
- **v0.5**: Docker v29.1.3 安装 (DaoCloud 镜像, 清华 apt 源)
- **v0.5**: new-api Docker 部署 (MySQL 8.0 + Redis 7 + calciumion/new-api, 端口 3000)
- **v0.5**: 上海 Tailscale 延迟优化 — 启用 Peer Relays (`--relay-server-port 3478`)
- **v0.5**: Lesson 20-24 — Tailscale MagicDNS / shim-signed / 阿里云镜像 / Docker 代理 / 国内 Tailscale 延迟
- **v0.5**: sh-agent 用户创建 + 用户权限体系确立
- **v0.5**: 上海 SSH config: `ssh sh-erpnext-test`

## 2026-06-22 (v0.4)

- **v0.4**: 迁移至 Ubuntu 24.04 (1C2G) — 放弃 Windows Server，新开 Vultr Ubuntu
- **v0.4**: systemd 部署 + 健康检查 cron + SSH SOCKS OAuth
- **v0.4**: Lesson 16-19

## 2026-06-18 (v0.3)

- **v0.3**: 放弃 Windows Server（多用户 RDP 冲突 + NSSM 失败）
- **v0.3**: Lesson 10-15

## 2026-06-18 (v0.2)

- **v0.2**: LAN 网关部署 + ping != TCP 端口通
- **v0.2**: Lesson 8-9

## 2026-06-18 (v0.1)

- **v0.1**: 初始搭建 — Tailscale P2P 直连、CLIProxyAPI v7.2.16、OKF 文档骨架
- **v0.1**: Lesson 1-7
