---
okf: v0.1
type: Index
title: US OpenAI API Proxy — 文档索引
description: 渐进式加载入口
tags: [openai, api-proxy, tailscale, vultr, chatgpt]
---
# US OpenAI API Proxy — 文档索引

> 渐进式加载。Agent 接手时只需读 `../AGENT_HANDOFF.md`（入口），需要细节时按下面索引深入。

## 快速导航

| 你需要... | 读这个 |
|----------|--------|
| 快速了解模块 + 开始工作 | [`../AGENT_HANDOFF.md`](../AGENT_HANDOFF.md) |
| 了解怎么部署和使用 | [`../README.md`](../README.md) |
| 查看架构设计决策 | [architecture.md](architecture.md) |
| 查阅工具、术语、链接 | [reference/tools-index.md](reference/tools-index.md) |
| 查阅经验教训 | [lessons/lessons-learned.md](lessons/lessons-learned.md) |
| 日常运维、监控、同事接入 | [operations.md](operations.md) |
| 部署 LAN 网关让同事使用 | [lan-gateway.md](lan-gateway.md) |
| 办公室全员访问 Tailscale (5方案) | [office-lan-access.md](office-lan-access.md) |
| 查看变更历史 | [log.md](log.md) |

## 目录结构

```
us_openai_api_proxy/
├── README.md
├── AGENT_HANDOFF.md
├── .env.example
├── .gitignore
└── docs/                         ← OKF v0.1 bundle
    ├── index.md                  ← 你在这里
    ├── log.md                    ← 变更历史
    ├── architecture.md           ← 架构设计
    ├── reference/
    │   └── tools-index.md        ← 工具/术语/链接
    └── lessons/
        └── lessons-learned.md    ← 经验教训
```

## 设计原则

- **渐进披露**：`AGENT_HANDOFF.md` 只放高频信息 + 导航，细节在 `reference/`
- **每个文件独立可读**：不依赖上下文，有"为什么读这个"说明
- **敏感信息不入库**：密码/密钥/IP 用占位符，真实值在 `.env`（gitignore）
