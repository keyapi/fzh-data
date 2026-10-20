---
okf: v0.1
type: Index
title: 供应链整合决策系统 — 交接包索引
description: 从销售分析到预测、补货、排产、头程在途的整合项目：背景、现有资产、能力地图、深度调研计划、多 Agent 分工
date: 2026-10-20
---

# 供应链整合决策系统 — 交接包

> **状态**：交接中（2026-10-20）。本目录只做「问题定义 + 现有信息盘点 + 调研计划 + 分工约定」，
> **不是**最终架构，也**没有**开始写业务代码。

## 怎么读

| 顺序 | 文件 | 内容 |
|---|---|---|
| 1 | [00-brief.md](00-brief.md) | 为什么做、做到什么算成功、边界与已知约束 |
| 2 | [01-asset-inventory.md](01-asset-inventory.md) | 仓库里**已核实**的相关资产（含未合并分支）+ 待确认项 |
| 3 | [02-capability-map.md](02-capability-map.md) | 系统需要哪些能力、哪些已有、哪些缺 |
| 4 | [03-research-plan.md](03-research-plan.md) | 三条深度调研线：业界实践 / AI Agent SOTA / 开源方案 |
| 5 | [04-multi-agent-handoff.md](04-multi-agent-handoff.md) | 在 Claude / Codex / Cursor 里怎么并行、怎么合并 |

## 一句话结论（待调研验证）

老板要的不是「再给一份 Excel」，而是**一条能反复跑、能被审计、能解释「为什么这么建议」的链路**：
销售事实 → 需求预测 → 库存与在途 → 补货/下单建议 → 排产建议 → 执行与预警。

技术上最可能的形态是 **「确定性计算内核 + AI 编排与解释 + 人工审批闸门」**，
而不是让大模型直接算数或直接下单 —— 这条是**待验证的假设**，不是已定方案。

## 给新对话的开场指令（直接复制）

```text
请先读 docs/plans/2026-10-20-supply-chain-integration/ 下的 5 份文件（index 开始），
然后按 03-research-plan.md 的三条线做深度调研、按 04-multi-agent-handoff.md 的分工执行。
先出架构方案与能力缺口，不要直接写业务代码。
```

## 变更记录

见 [log.md](log.md)。
