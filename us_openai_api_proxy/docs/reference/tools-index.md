---
okf: v0.1
type: Reference
title: 工具 / 术语 / 链接索引
description: 项目涉及的工具、术语、外部资源
tags: [reference, tools, glossary, links]
---
# 工具 / 术语 / 链接索引

## 核心工具

| 工具 | 用途 | 链接 |
|------|------|------|
| **Tailscale** | 零配置 WireGuard 虚拟局域网，免费 100 设备 | https://tailscale.com |
| **CLIProxyAPI** | ChatGPT/Claude/Gemini 订阅 → OpenAI API | https://github.com/router-for-me/CLIProxyAPI |
| **NSSM** | 将任意 exe 注册为 Windows Service | https://nssm.cc/ |
| **RustDesk** | 开源远程桌面（备选） | https://github.com/rustdesk/rustdesk |

## 术语

| 术语 | 说明 |
|------|------|
| **P2P 打洞** | Tailscale 在两台设备间建立直接 UDP 连接，无需中继 |
| **DERP** | Tailscale 的中继协议，P2P 失败时兜底 |
| **OAuth** | CLIProxyAPI 通过浏览器 OAuth 获取 ChatGPT 网页版的 session token |
| **Codex** | OpenAI 的 CLI 编程工具，CLIProxyAPI 用其认证通道登录 ChatGPT |
| **OpenAI Compatible** | 兼容 `/v1/chat/completions` 格式的 API 端点 |

## 备选/相关方案

| 方案 | 对比 | 备注 |
|------|------|------|
| **frp** | 比 Tailscale 重，需要独立服务端 | 仅当 Tailscale 不可用时考虑 |
| **new-api** | CLIProxyAPI 的上游管理层，加用户/额度管理 | 多用户场景时部署 |
| **Sunshine+Moonlight** | 比 RustDesk 延迟低、画质好 | 适合游戏/创作，缺文件传输 |
| **ZeroTier** | Tailscale 替代品 | 国内网络环境下 Tailscale 更优 |
| **向日葵国际版** | 商业远程桌面 | 跨境需要付费，已放弃 |

## 调研资料

- 远程桌面方案对比（RustDesk / Sunshine+Moonlight / CrossDesk）
- Tailscale 自建 DERP 中继方案（IP+自签证书 / 域名+Let's Encrypt）
- CLIProxyAPI 部署方案（Docker / 二进制 / Nginx 反代）
- frp 内网穿透方案
- ChatGPT 订阅共享工具对比（CLIProxyAPI / new-api / Sub2API / CliRelay）

> 详细调研报告待整理到 `docs/research/` 目录。

## 见也

- [architecture.md](../architecture.md) — 架构决策
- [lessons/lessons-learned.md](../lessons/lessons-learned.md) — 经验教训
