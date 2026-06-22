---
okf: v0.1
type: Log
title: 变更日志
description: US OpenAI API Proxy 模块的时序变更记录
tags: [openai, api-proxy, changelog]
---
# 变更日志

## 2026-06-22

- **v0.3**: 决策放弃 Windows Server — 多用户 RDP Tailscale 冲突 + NSSM 注册失败 + 资源不足 (4GB 95%)
- **v0.3**: 新开 Ubuntu 24.04 (1C2G) 美国服务器，待迁移 Tailscale + CLIProxyAPI
- **v0.3**: Lesson 10-15 经验教训 — Windows 多用户 session、重启丢进程、Linux vs Windows、LAN 网关、P2P 退化、unattended 模式
- **v0.3**: AGENT_HANDOFF.md 重写 — 新增 Ubuntu 部署步骤、systemd 模板、SSH OAuth 流程

## 2026-06-18

- **v0.2**: LAN 网关部署 — 网关电脑开 `lite_lan_proxy.py` :3000 反代到远程 CLIProxyAPI，同事无需装 Tailscale
- **v0.2**: 踩坑 — ping 通 != TCP 端口通 (Windows 防火墙)，代理进程须常驻不能测试完就停
- **v0.2**: 新增文件 — `tools/lite_lan_proxy.py` (轻量反代)、`docs/lan-gateway.md` (部署文档)
- **v0.2**: AGENTS.md 新增「Agent 新机器首次 clone 后必做」自举章节

- **v0.1**: 初始搭建 — Tailscale 组网 (北京 + Vultr) P2P 直连成功
- **v0.1**: CLIProxyAPI v7.2.16 部署在 US Vultr Windows Server 2022
- **v0.1**: ChatGPT 免费账号 OAuth 登录成功 (`fzhselleruse@gmail.com`)
- **v0.1**: 端到端 API 测试通过 — 北京 curl → Tailscale → CLIProxyAPI → ChatGPT 对话正常
- **v0.1**: 确认 P2P 直连，无需在 HK 部署 DERP 中继
- **v0.1**: 架构决策 — CLIProxyAPI 部署在 Vultr VM 而非 USTX 实体电脑 (24h在线、网络稳定)
- **v0.1**: OKF 文档初始化 — 模块创建、文档骨架
- **v0.1**: 调研完成 — 远程桌面方案 (RustDesk / Tailscale RDP)、API 代理 (CLIProxyAPI / new-api / frp)、Tailscale 自建 DERP
