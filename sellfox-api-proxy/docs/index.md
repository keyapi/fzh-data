---
okf: v0.1
type: Index
title: sellfox-api-proxy — 文档索引
description: 赛狐 API 代理网关项目的完整文档导航
tags: [sellfox, api-proxy, gateway, index]
---

# 文档索引

## 目录结构

```
sellfox-api-proxy/
├── AGENT_HANDOFF.md                       # Agent 入口
├── README.md                              # 人类可读概览
└── docs/
    ├── index.md                           # ← 你在这里
    ├── log.md                             # 变更日志
    ├── research/
    │   ├── 2026-07-07-problem-background.md       # 问题背景
    │   ├── 2026-07-07-conversation-evolution.md   # 对话过程完整记录
    │   ├── 2026-07-07-existing-solutions-survey.md # 现成方案调研
    │   ├── 2026-07-08-api-gateway-deep-dive.md    # API 网关深入调研
    │   └── 2026-07-08-kong-architecture-analysis.md # Kong 架构分析
    ├── specs/
    │   └── index.md                               # 设计规格
    ├── reference/
    │   └── index.md                               # 技术参考
    └── lessons/                                    # 经验教训（实施后）
```

## 按需求导航

| 你需要… | 读这个 |
|----------|--------|
| 理解为什么要做这个项目 | [problem-background](research/2026-07-07-problem-background.md) |
| 了解整个对话推演过程 | [conversation-evolution](research/2026-07-07-conversation-evolution.md) |
| 看所有现成方案调研结果 | [existing-solutions-survey](research/2026-07-07-existing-solutions-survey.md) |
| 看通用 API 网关深度对比 | [api-gateway-deep-dive](research/2026-07-08-api-gateway-deep-dive.md) |
| 理解 Kong 架构及借鉴点 | [kong-analysis](research/2026-07-08-kong-architecture-analysis.md) |
| 看完整经验教训（15 条） | [架构演进全记录](lessons/2026-07-09-full-architecture-evolution.md) |
| 看实施计划 | 上级目录 `CLAUDE.md` 计划文件 |
| 看变更日志 | [log.md](log.md) |

## 核心结论

经过 4 轮方案迭代（通用方案调研 → NyaProxy Fork → 自研 → Micro Kong），最终选定：

**借鉴 Kong 插件阶段模型 + 声明式 Provider 配置，Python/FastAPI 实现，~500 行。**
