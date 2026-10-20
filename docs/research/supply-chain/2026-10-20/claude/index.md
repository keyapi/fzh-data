---
okf: v0.1
type: Index
title: 供应链整合 — Claude 独立调研
description: 销售分析→需求预测→库存/在途→补货/排产→审批 的独立穷尽调研；Claude 单路产出（与 Codex / Cursor 互不共享中间结论）
date: 2026-10-20
tags: [supply-chain, research, index]
---

# 供应链整合 — Claude 独立调研

> **独立性声明**：本项目由 Claude / Codex / Cursor 三家**各自独立**完成同一份调研
> （业界实践 + AI/Agent SOTA + 开源方案），独立分支、独立 PR，调研期间不共享中间结论。
> 本目录只属于 Claude 这一路；不要写入其他工具的内容。

## 状态

- 阶段：Phase 0–1（脚手架 + 项目内资产盘点）
- 分支：`research/supply-chain-claude`（基于 `origin/main` @ `e5d07c9d`）
- 交接包参考：`origin/docs/supply-chain-integration-handoff` @ `de899f4b`（PR #300，未合并）
- 检查点：`01-existing-assets.md` 完成后先交用户确认，再进入三条调研线

## 文件

| 文件 | 内容 |
|---|---|
| [00-plan.md](00-plan.md) | 问题分解、范围、子 Agent 分工、时间盒、检索清单、DoD |
| [01-existing-assets.md](01-existing-assets.md) | 项目内资产（main / 全部分支 / open + closed 未合并 PR / 历史资料） |
| [02-industry-practices.md](02-industry-practices.md) | 业界成熟架构与最佳实践 |
| [03-ai-agent-sota.md](03-ai-agent-sota.md) | AI / Agent 能力边界与 2026 SOTA |
| [04-open-source.md](04-open-source.md) | 开源方案、License、活跃度、TCO |
| [05-synthesis.md](05-synthesis.md) | 指标权威矩阵 + 3 个候选架构 + 推荐 + 成本 + 反证 |
| [06-open-questions.md](06-open-questions.md) | 需要老板/业务拍板的问题 |
| [sources.md](sources.md) | 证据账本（ID / 主张 / 来源 / 日期 / 原文 / 强度） |
| [log.md](log.md) | 过程记录、失败与放弃方向 |
| [experiments/](experiments/index.md) | E1–E3 最小验证的代码、输入哈希与结果 |

## 导航说明

跨工具共享的上级目录（`docs/research/supply-chain/`、`2026-10-20/`）**不建 index.md**，
避免与 Codex / Cursor 的 PR 冲突；等三家完成后在对比会话统一生成。

## 变更记录

见 [log.md](log.md)。
