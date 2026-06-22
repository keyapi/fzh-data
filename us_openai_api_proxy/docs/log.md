---
okf: v0.1
type: Log
title: 变更日志
description: US OpenAI API Proxy 模块的时序变更记录
tags: [openai, api-proxy, changelog]
---
# 变更日志

## 2026-06-22 (v0.4)

- **v0.4**: 迁移至 Ubuntu 24.04 (1C2G) — 放弃 Windows Server，新开 Vultr Ubuntu
- **v0.4**: systemd 部署 — `cliproxyapi.service` 开机自启，`Restart=always` 崩溃自愈
- **v0.4**: SSH SOCKS 代理 OAuth 方案 — `ssh -D 1080` 解决无 GUI Ubuntu 的浏览器登录问题，同时确保 OpenAI 看到美国 IP
- **v0.4**: 健康检查 — `health_check.sh` + cron 每 5 分钟自动检查 systemd + API 端口
- **v0.4**: 运维体系 — SSH config 一键登录、gq-agent 最小权限用户、Windows Terminal profile
- **v0.4**: 敏感信息分层 — L1 占位符文档 / L2 .env gitignore / L3 SSH config / L4 Tailscale 控制台
- **v0.4**: Lesson 16-18 — SSH SOCKS OAuth、systemd 自动拉起、Tailscale 新机入网流程
- **v0.4**: 新 OAuth 账号 — `fzhvickyjing@gmail.com` (免费，待升级)

## 2026-06-18 (v0.3)

- **v0.3**: 决策放弃 Windows Server — 多用户 RDP Tailscale 冲突 + NSSM 注册失败 + 资源不足
- **v0.3**: Lesson 10-15 — Windows 多用户、重启丢进程、Linux vs Windows、LAN 网关、P2P 退化

## 2026-06-18 (v0.2)

- **v0.2**: LAN 网关部署 — 网关电脑开 `lite_lan_proxy.py` :3000，同事无需装 Tailscale
- **v0.2**: ping 通 != TCP 端口通 (Windows 防火墙)，代理进程须常驻

## 2026-06-18 (v0.1)

- **v0.1**: 初始搭建 — Tailscale P2P 直连、CLIProxyAPI v7.2.16、OKF 文档骨架
- **v0.1**: 确认 P2P 直连无需 HK DERP、架构决策 Vultr VM 而非实体电脑
