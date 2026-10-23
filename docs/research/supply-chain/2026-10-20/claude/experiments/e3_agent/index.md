---
okf: v0.1
type: Index
title: E3 只读 Agent 原型
description: 确定性路由 + 语义层 + 8 个只读工具 + prepare/confirm/execute/readback；15 题评估 15/15 通过，0 次写执行。
date: 2026-10-20
tags: [supply-chain, agent, semantic-layer, read-only]
---

# E3 只读 Agent 原型

> 切片：楔形枕 8 SKU × 美中-Daneey 仓 × 2026-03 至 2026-09。
> 不调用外部 LLM，不写业务系统；客户与人员信息已匿名化。

## 结论

- 可作答题：10/10（工具 + 槽位 + 值 + 证据）
- 歧义澄清：2/2
- 写意图拒绝 + 安全替代：1/1，写执行 0 次
- 证据覆盖：10/10
- 语义歧义率：13.3%（Falsify 阈值 20%）
- 判定：**PASS，未触发 Falsify**

## 文件

| 文件 | 用途 |
|---|---|
| [README.md](README.md) | 复现命令、交互模式、数据与匿名化说明 |
| [results.md](results.md) | 设计、指标注册表、评估表、失败分析、限制、Falsify 判定 |
| [agent.py](agent.py) | 路由器 + 语义层 + 8 个只读工具 + 评估入口 |
| [questions.json](questions.json) | 15 题评估集 |
| [results.json](results.json) | 逐题完整结果与证据 |
| [data/wedge_decision_package.json](data/wedge_decision_package.json) | 本地内嵌匿名化数据 |

## 复现

```bash
uv run python docs/research/supply-chain/2026-10-20/claude/experiments/e3_agent/agent.py --eval
```
