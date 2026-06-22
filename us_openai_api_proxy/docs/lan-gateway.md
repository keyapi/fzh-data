---
okf: v0.1
type: Explanation
title: 北京办公室 LAN 网关部署
description: 用一台已装 Tailscale 的 Windows 电脑做局域网反代入口，让同事无需装 Tailscale 即可通过 Codex++ 共享 CLIProxyAPI
tags: [gateway, lan, codex, tailscale, onboarding, lessons]
---

# 北京办公室 LAN 网关部署

> 目标：让北京办公室 3-5 名同事不用装 Tailscale，只需在 codex++ 里填局域网地址，即可共享远程 CLIProxyAPI。

## 架构

北京同事电脑 (Codex++, 无需Tailscale) -> http://192.168.10.250:3000/v1 -> 网关电脑(Tailscale) -> US Vultr VM CLIProxyAPI :8317 -> ChatGPT

- 网关电脑：安装 Tailscale，能访问远程 CLIProxyAPI
- 同事电脑：只连办公室局域网，不装 Tailscale
- 网关进程：Python 标准库实现，无需额外依赖

## 前置条件

1. 远程 CLIProxyAPI 已部署并正常运行
2. 网关电脑已安装 Tailscale 并加入同一 tailnet
3. 网关电脑能访问 http://<remote_tailscale_ip>:8317/v1/models
4. Windows 防火墙放行网关端口（3000）入站

## 部署步骤

### 1. 放行防火墙（管理员 PowerShell）

New-NetFirewallRule -DisplayName 'Codex LAN Proxy 3000' -Direction Inbound -Action Allow -Protocol TCP -LocalPort 3000 -Profile Private

### 2. 启动本地反代

\='你的上游key'
python tools/lite_lan_proxy.py --listen-host 0.0.0.0 --listen-port 3000 --upstream http://<remote_tailscale_ip>:8317/v1

### 3. 验证

curl http://192.168.10.250:3000/v1/models

### 4. 同事 codex++ 配置

- Base URL: http://192.168.10.250:3000/v1
- API key: 共享的上游 key

## 方案选择

A: netsh portproxy — 需管理员权限，被拒绝
B: 用户态 Python 反代 — 采纳。约 100 行标准库代码，无额外依赖，自动注入上游 key
C: 每人装 Tailscale — 未采纳，客户端安装太麻烦
D: 独立网关机 — 推荐未来使用

## 踩坑记录

坑1: ping 通不等于 TCP 端口通。同事 ping 通但 codex++ 报错 = 防火墙拦了 TCP 3000。诊断方法：网关机本机 curl 192.168.10.250:3000 能通则问题在防火墙
坑2: 代理进程测试后被误停。验证脚本用 Start-Process;test;Stop-Process 模式，测试完后进程被终止。网关须常驻运行
坑3: 本机自测不能代替外部验证。必须从另一台机器做最终验证

## 安全

- 端口仅内网暴露
- key 通过环境变量注入，不写文件
- 内网不启用 HTTPS

## 相关文件

- tools/lite_lan_proxy.py — 本地反代脚本
- ../AGENT_HANDOFF.md — US OpenAI API Proxy 状态和导航
- architecture.md — 整体架构设计
- lessons/lessons-learned.md — 历史经验教训

## 后续

1. NSSM 做成 Windows Service 开机自启
2. 升级 new-api 做独立账号管理
3. 深圳分公司通过 Tailscale/VPN 统一接入
