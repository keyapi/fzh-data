---
okf: v0.1
type: Index
title: Amazon 广告分析模块 — 文档索引
description: 渐进式加载入口
tags: [amazon, advertising, index]
---
# Amazon 广告分析模块 — 文档索引

> 渐进式加载。Agent 接手时只需读 `advertise/AGENT_HANDOFF.md`（入口），需要细节时按下面索引深入。

## 快速导航

| 你需要... | 读这个 |
|----------|--------|
| 快速了解模块 + 开始工作 | [`../AGENT_HANDOFF.md`](../AGENT_HANDOFF.md) |
| 了解怎么运行脚本 | [`../README.md`](../README.md) |
| 查看调研来源和方法论 | [research/](research/) |
| 查看设计决策和架构 | [specs/](specs/) |
| 查阅列名映射、数据源、工具对比 | [reference/](reference/) |
| 查阅经验教训 | [lessons/](lessons/) |

## 目录结构

```
advertise/docs/                         ← OKF v0.1 bundle
├── index.md                           ← 你在这里
├── log.md                             ← 变更历史 (OKF 规范)
├── roadmap.md                         ← 路线图 + 阶段状态
├── research/                          ← 调研报告
├── specs/                             ← 设计文档
├── reference/                         ← 参考资料（按需加载）
│   ├── column-mappings.md
│   ├── data-sources.md
│   ├── tools-ecosystem.md
│   ├── skills-mcp-catalog.md
│   └── source-urls.md
└── lessons/                           ← 经验教训
    └── lessons-learned.md
```

## 设计原则

- **渐进披露**: `AGENT_HANDOFF.md` 只放高频信息 + 导航，细节在 `reference/`
- **Diátaxis 四象限**: Tutorial (README) / How-to (AGENT_HANDOFF) / Reference (reference/) / Explanation (research/, specs/)
- **每个文件独立可读**: 不依赖上下文，有 "为什么读这个" 说明
- **交叉引用**: 每页底部有 "See also" 链接
