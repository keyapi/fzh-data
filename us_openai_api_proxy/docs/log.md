---
okf: v0.1
type: Log
title: 变更日志
description: US OpenAI API Proxy 模块的时序变更记录
tags: [openai, api-proxy, changelog]
---
# 变更日志

## 2026-06-18

- **v0.1**: 初始搭建 — Tailscale 组网 (北京 + Vultr) P2P 直连成功
- **v0.1**: CLIProxyAPI v7.2.16 部署在 US Vultr Windows Server 2022
- **v0.1**: ChatGPT 免费账号 OAuth 登录成功 (`fzhselleruse@gmail.com`)
- **v0.1**: 端到端 API 测试通过 — 北京 curl → Tailscale → CLIProxyAPI → ChatGPT 对话正常
- **v0.1**: 确认 P2P 直连，无需在 HK 部署 DERP 中继
- **v0.1**: 架构决策 — CLIProxyAPI 部署在 Vultr VM 而非 USTX 实体电脑（24h在线、网络稳定）
- **v0.1**: OKF 文档初始化 — 模块创建、文档骨架
- **v0.1**: 调研完成 — 远程桌面方案 (RustDesk / Tailscale RDP)、API 代理 (CLIProxyAPI / new-api / frp)、Tailscale 自建 DERP
