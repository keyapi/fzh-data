---
okf: v0.1
type: Log
title: 变更日志
description: US OpenAI API Proxy 模块的时序变更记录
tags: [openai, api-proxy, changelog]
---
# 变更日志

## 2026-06-22 (v0.5)

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
