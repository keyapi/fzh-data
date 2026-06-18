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
4. US Vultr VM 已有同事 RDP 操作 Amazon，不能影响现有业务

## 设计决策

### 为什么 CLIProxyAPI 部署在 Vultr VM 而非 USTX 实体电脑？

| 因素 | Vultr VM | USTX 实体电脑 |
|------|---------|-------------|
| 在线时长 | 24h 云服务器 | 办公室电脑，可能关机 |
| 网络稳定 | 云服务商骨干网 | 办公室宽带，NAT 后 |
| 资源 | 4GB, Windows Server 2022 | Win 10/11, 配置未知 |
| 干扰现有业务 | 极低 (CLIProxyAPI ~50MB) | 独占机器 |
| 运维 | 已有 RDP 访问 | 需要额外配置 |

**决策**：Vultr VM。资源占用极低，不影响同事 Amazon 操作。

### 为什么不用 HK 中转？

Tailscale P2P 打洞成功（北京↔Vultr 直连），延迟 252ms 可接受。部署 DERP relay 只会增加复杂度而不会降低延迟（北京→HK→US 路径更长）。

### 为什么不用 frp 或 nginx 反代？

Tailscale 已提供加密隧道 + 虚拟 IP + NAT 穿透。加 frp 是多一层维护负担，没有收益。

### 为什么初期不用 new-api？

单人使用场景不需要用户管理、额度控制、计费。CLIProxyAPI 裸用足够。多用户时再上 new-api。

## 数据流

```
┌──────────────┐     Tailscale P2P      ┌─────────────────────┐     HTTPS      ┌──────────┐
│  北京客户端    │ ◄──────────────────► │  US Vultr VM         │ ◄───────────► │ ChatGPT  │
│  Claude Desktop│   100.x.x.x:8317      │  CLIProxyAPI :8317   │   OAuth token │  API     │
│  Codex Desktop │                      │  (Tailscale IP bind) │               │          │
└──────────────┘                       └─────────────────────┘               └──────────┘
```

1. 北京客户端发 OpenAI 兼容请求 → Tailscale 虚拟 IP
2. Tailscale P2P 加密隧道传输到 Vultr
3. CLIProxyAPI 将 OpenAI 格式请求转为 ChatGPT web API 调用
4. ChatGPT 返回 → CLIProxyAPI 转回 OpenAI 格式 → 返回客户端

## 安全

- CLIProxyAPI 只监听 Tailscale IP（`100.85.49.112`），不监听 `0.0.0.0`
- 公网无法扫描到 8317 端口
- Tailscale 提供端到端 WireGuard 加密
- API Key 认证（Bearer token）

## 见也

- [reference/tools-index.md](reference/tools-index.md) — 工具和术语
- [lessons/lessons-learned.md](lessons/lessons-learned.md) — 经验教训
