---
okf: v0.1
type: Index
title: 供应链整合 — Claude 独立调研
description: 销售分析→需求预测→库存/在途→补货/排产→审批 的独立穷尽调研；Claude 单路产出（与 Codex / Cursor 互不共享中间结论）
date: 2026-10-20
tags: [supply-chain, research, index]
---

# 供应链整合 — Claude 独立调研

> **独立性声明**：本项目由 Claude / Codex / Cursor 三家**各自独立**完成同一份调研。
> Claude 的早期独立 PR #302 已按用户要求关闭并合入 **PR #300**；Codex 的 #301 保持独立，不合并。
> 本目录只属于 Claude 这一路；Codex 内容不写入这里。

## 状态

- 阶段：Phase 0–4 + Codex 评审响应完成（资产盘点 → 三线调研 → E1–E3 → 综合 → 逐条处理）。
- 位置：**PR #300** 分支 `docs/supply-chain-integration-handoff`（交接包 + 本调研）。
- **推荐方向**：轻量决策链 + 薄 Agent；预测用 TSB/ens5 + naive 守门；补货先定预算与服务水平；
  库存用**独立只读快照 mart**，不写 EN Bin；计划引擎保留比较入口，不提前锁定。
- 检查点：01（已确认）、E1–E3（已确认）、Codex 两轮评审（已逐条处理，见 09/10）。

## 文件

| 文件 | 内容 |
|---|---|
| [00-plan.md](00-plan.md) | 问题分解、范围、子 Agent 分工、时间盒、检索清单、DoD |
| [01-existing-assets.md](01-existing-assets.md) | 项目内资产（main / 全部分支 / open + closed 未合并 PR / 历史资料） |
| [02-industry-practices.md](02-industry-practices.md) | 业界成熟架构与最佳实践 |
| [03-ai-agent-sota.md](03-ai-agent-sota.md) | AI / Agent 能力边界与 2026 SOTA |
| [04-open-source.md](04-open-source.md) | 开源方案、License、活跃度、TCO |
| [05-synthesis.md](05-synthesis.md) | 指标权威矩阵 + 3 个候选架构 + 计划引擎比较入口 + 推荐 + 成本 + 反证 |
| [06-open-questions.md](06-open-questions.md) | 需要老板/业务拍板的问题 |
| [07-review-guide.md](07-review-guide.md) | 审核顺序 + 给 Codex 的只读评审 brief |
| [08-fact-contract.md](08-fact-contract.md) | 生产数量四分法、实体/键、守恒式、批次关联、SKU/单位/配套映射 |
| [09-codex-review-response.md](09-codex-review-response.md) | 对 Codex 评审的接受/部分接受/不接受、已改内容、剩余分歧与裁决条件 |
| [10-codex-round2-response.md](10-codex-round2-response.md) | 第二轮定向复审 R01–R07 处理、共同框架/决策/合成样例对照 |
| [11-common-baseline.md](11-common-baseline.md) | G0 冻结基线（框架/契约/样例/决策表版本清单）+ G1 进入条件 |
| [12-codex-g1-instructions.md](12-codex-g1-instructions.md) | G1 阶段给 Codex 的执行清单（基线冻结/样例/08 定向复核/三角靠枕映射） |
| [13-g1-data-sources.md](13-g1-data-sources.md) | G1 数据来源与映射清单（现有 GSheet/本地成本文件/权威映射；缺口与脱敏） |
| [sources.md](sources.md) | 证据账本（ID / 主张 / 来源 / 日期 / 原文 / 强度） |
| [log.md](log.md) | 过程记录、失败与放弃方向 |
| [experiments/](experiments/index.md) | E1–E3 最小验证的代码、输入哈希与结果 |

## 导航说明

跨工具共享的上级目录（`docs/research/supply-chain/`、`2026-10-20/`）**不建 index.md**，
避免与 Codex / Cursor 的 PR 冲突；等三家完成后在对比会话统一生成。

## 变更记录

见 [log.md](log.md)。
