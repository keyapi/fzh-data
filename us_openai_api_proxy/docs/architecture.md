---
okf: v0.1
type: Explanation
title: 架构设计
description: US OpenAI API Proxy 架构决策、数据流、组件关系
tags: [architecture, tailscale, cliproxyapi, design]
---
# 架构设计

## 问题

1. 北京办公室需要调用 ChatGPT API，但 OpenAI 不对中国开放
2. 向日葵国际版跨境远程桌面需要付费账号
3. 香港阿里云跑 ERPNext 生产，不能加负担
4. ~~US Vultr VM 已有同事 RDP 操作 Amazon，不能影响现有业务~~ → 已放弃，新开 Ubuntu

## 当前架构 (v0.3)

```
北京办公室                             美国
┌─────────────────────────┐         ┌─────────────────────┐
│  fzhpc13 (Tailscale)     │  P2P/   │  Ubuntu 24.04 (1C2G) │
│  └─ Codex++ :8317/v1 ────┼─DERP──→│  ├─ Tailscale         │
│                          │         │  └─ CLIProxyAPI :8317 │
│  LAN 网关 :3000          │         │     (systemd 自启)    │
│  └─ 同事 PC ─────────────┘         │     └─ ChatGPT OAuth  │
└─────────────────────────┘         └─────────────────────┘
```

## 设计决策

### 为什么 CLIProxyAPI 部署在美国而不是 HK？

| 因素 | US (Ubuntu) | HK (阿里云) |
|------|------------|------------|
| ChatGPT 访问 | 原生可用 | 可能被 OpenAI 封 |
| 资源 | 专属 1C2G | 共享 2C4G，跑 ERPNext |
| 运维风险 | 不影响生产 | 可能拖垮 ERPNext |
| OAuth 登录 | 美国 IP 原生 | 可能需要代理 |

**决策**：US。ChatGPT 账号在美国 IP 登录最安全，且不拖累 HK 生产环境。

### 为什么放弃 Windows Server？

1. **多用户 RDP 冲突**：Tailscale GUI socket 被第一个登录用户独占
2. **NSSM 注册失败**：无法将 CLIProxyAPI 注册为 Windows Service
3. **资源紧张**：4GB 95% 占用 + 同事日常工作
4. **运维负担**：GUI 操作 + RDP 延迟 + 多用户 session 管理

### 为什么选 Ubuntu 24.04？

| 优势 | 说明 |
|------|------|
| systemd 原生 | 注册服务零依赖，`Restart=always` 崩溃自愈 |
| 无 GUI 开销 | 1C2G 全部用于服务 |
| Tailscale 无冲突 | Linux 版是纯系统级服务，不存在用户 session 问题 |
| SSH 运维 | 轻量、稳定、可脚本化 |
| 低成本 | 最便宜的云服务器配置即可 |

### 为什么不用 HK 中转？

Tailscale P2P 打洞成功时直连（~260ms），失败时 DERP relay 兜底（~260ms）。加 HK 中转只会增加复杂度和延迟。

### 为什么初期不用 new-api？

单人使用场景不需要用户管理、额度控制。CLIProxyAPI 裸用足够。多用户时再上。

## 数据流

```
┌──────────────┐   Tailscale   ┌─────────────────┐    HTTPS     ┌──────────┐
│  客户端        │ ◄──────────► │  US Ubuntu       │ ◄─────────► │ ChatGPT  │
│  Codex++      │  100.x:8317  │  CLIProxyAPI     │  OAuth token│  API     │
│  Claude       │              │  (systemd)       │             │          │
└──────────────┘              └─────────────────┘             └──────────┘

或通过 LAN 网关:
  同事 PC ──HTTP──→ 网关 :3000 ──Tailscale──→ US Ubuntu :8317
```

## 安全

- CLIProxyAPI 只监听 Tailscale IP（100.x.x.x），不监听公网接口
- 公网无法扫描到 8317 端口
- Tailscale 提供端到端 WireGuard 加密
- API Key 认证（Bearer token）
- Ubuntu 防火墙仅开放 SSH + Tailscale 端口

## 见也

- [reference/tools-index.md](reference/tools-index.md) — 工具和术语
- [lessons/lessons-learned.md](lessons/lessons-learned.md) — 经验教训 (15 条)
- [lan-gateway.md](lan-gateway.md) — LAN 网关部署
