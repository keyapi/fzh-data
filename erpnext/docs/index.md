---
okf: v0.1
type: Index
title: erpnext — 文档索引
description: ERPNext 工单数据排查模块的完整文档导航
tags: [erpnext, work-order, audit, index]
---

# 文档索引

## 目录结构

```
erpnext/
├── AGENT_HANDOFF.md                        ← Agent 入口
├── README.md                               ← 人读概览
├── scripts/
│   ├── setup.py                            ← 凭证检查
│   ├── fetch.py                            ← 数据拉取
│   └── gen_report.py                       ← Excel 报告
├── data/                                   ← 报告输出 (不提交)
└── docs/
    ├── index.md                            ← 你在这里
    ├── log.md                              ← 变更日志
    ├── work-order-investigation-methodology.md  ← 排查方法论
    ├── reference/
    │   └── index.md                        ← API/字段参考
    ├── research/
    │   └── index.md                        ← 调研记录
    └── lessons/
        └── index.md                        ← 经验教训
```

## 按需求导航

| 你需要... | 读这个 |
|----------|--------|
| 快速开始排查工单 | [AGENT_HANDOFF.md](../AGENT_HANDOFF.md) |
| 理解 8 步排查法 | [work-order-investigation-methodology](work-order-investigation-methodology.md) |
| 查 API 端点/字段 | [reference/](reference/index.md) |
| 看变更历史 | [log.md](log.md) |
| 看经验教训 | [lessons/](lessons/index.md) |
