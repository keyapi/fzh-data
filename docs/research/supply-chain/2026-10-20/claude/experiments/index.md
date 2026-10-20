---
okf: v0.1
type: Index
title: 供应链整合 — 最小验证实验
description: E1 预测基线对拍 / E2 OR-Tools 补货 LP / E3 只读 Agent 原型
date: 2026-10-20
tags: [supply-chain, research, experiments]
---

# 最小验证实验

> 切片：PB 楔形枕/三角靠枕 × 美中 Daneey × PB 渠道。
> 只读业务系统；提交代码、输入哈希与结果表，**不提交原始客户数据**。

| 实验 | 问题 | Pass | Falsify |
|---|---|---|---|
| E1 预测基线 | 复杂方法是否真的优于 naive / 现有 M1–M3b？ | 高价值 SKU 聚合 WAPE 比 naive 低 ≥10% 且排名稳定 | 无方法稳定胜 naive，或结论随窗口翻转 |
| E2 补货 LP | OR-Tools 是否优于「月需求×覆盖−可用−在途」启发式？ | 5 分钟内可行、约束可解释、回测更优 | 关键字段缺失或无可复现改进 |
| E3 只读 Agent | Agent 能否正确取数并解释，而不越权写？ | ≥90% 正确工具/口径，0 越权写，答案附证据 | SKU/仓库语义歧义 >20% |

## 目录约定

```text
experiments/
├── index.md
├── e1_forecast/
├── e2_replenishment/
└── e3_agent/
```

每个实验目录包含：`README.md`（方法、输入、复现命令）、代码、`results.md`（含输入哈希）。
