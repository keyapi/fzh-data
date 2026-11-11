---
okf: v0.1
type: Index
title: 供应链整合 — Claude 独立调研
description: 销售分析→需求预测→库存/在途→补货/排产→审批 的独立穷尽调研；Claude 单路产出（与 Codex / Cursor 互不共享中间结论）
date: 2026-10-20
tags: [supply-chain, research, index]
---

# 供应链整合 — Claude 独立调研

> **当前项目交付入口（2026-10-23）**：[整体计划](control/PROJECT_ROADMAP.md)、[实时看板](control/PROJECT_BOARD.md)、[老板简报](control/BOSS_BRIEF.md)、[库存业务评价理论](control/INVENTORY_EVALUATION.md)。这些是跨角色控制面，不是另一份独立调研；下文保留早期研究轨迹。

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
| [14-daily-inventory-backup.md](14-daily-inventory-backup.md) | 每日库存备份、销售报表对比、落库与服务器建议 |
| [15-full-family-etl.md](15-full-family-etl.md) | 全 family/全 SKU 批量 ETL 方向与架构 |
| [control/reviews/2026-10-22-sku-match-audit.md](control/reviews/2026-10-22-sku-match-audit.md) | 通途-EN SKU 匹配只读审计（GS 订单侧 297 SKU / 4,115 行四分类） |
| [control/reviews/2026-10-22-eta-cover-uom-evidence.md](control/reviews/2026-10-22-eta-cover-uom-evidence.md) | B v2：5 trace SKU 主口径 + 10 expand10 扩展；ETA/Cover/UOM/在途证据与可复算键 |
| [control/reviews/2026-10-22-sample-2sku.md](control/reviews/2026-10-22-sample-2sku.md) | G2+G3 2-SKU 端到端样例（历史需求→预测/回测→库存/PO/在产→A/B 情景） |
| [control/reviews/2026-10-22-supply-demand-replenishment-v0.md](control/reviews/2026-10-22-supply-demand-replenishment-v0.md) | G2+G3 10-SKU 窄范围 V0（只读；不是下单建议） |
| [control/reviews/2026-10-22-model-race.md](control/reviews/2026-10-22-model-race.md) | **V1 五候选赛马**：6 起点回测、共形累计 P90、6 SKU 8%–20% 分解、White 8 月峰值、补货动作敏感性 |
| [control/reviews/2026-10-22-model-race-task.md](control/reviews/2026-10-22-model-race-task.md) | V1 赛马任务书（10 SKU、五候选、滚动回测、经验/共形 P90） |
| [control/reviews/2026-10-22-v0-review1-response.md](control/reviews/2026-10-22-v0-review1-response.md) | 对 Codex1 V0 review1 的逐条修复响应（正向 SO、A/B 边界、日历窗口、P90 √6、零需求保留） |
| [control/reviews/2026-10-22-replenishment-triage.md](control/reviews/2026-10-22-replenishment-triage.md) | D9 补货行动分层：可准备 1 / 待核实 2 / 暂缓 7（不是下单清单） |
| [control/reviews/2026-10-22-replenishment-actions-v0.md](control/reviews/2026-10-22-replenishment-actions-v0.md) | **P90-free 暂行行动清单**：always_replenish 0 / depends_on_arrival 6 / insufficient_evidence 4；只读 98e1c664，不含 P90 与数量 |
| [out/replenishment_v0/actions.json](out/replenishment_v0/actions.json) | 行动清单机器可读版（T1–T4 判定、D1/D2 与 A/B 边界、需补证据、责任角色、启动条件） |
| [out/replenishment_v0/evidence.json](out/replenishment_v0/evidence.json) | V0 聚合证据（10 SKU；无原始订单行；含查询定义与源哈希） |
| [out/replenishment_v0/model_race.json](out/replenishment_v0/model_race.json) | **V1 赛马 canonical 证据**（逐 SKU 候选/回测/共形标定/动作敏感性） |
| [experiments/g2g3_pilot/](experiments/g2g3_pilot/) | G2+G3 只读构建脚本、2-SKU 样例 JSON、V1 `model_race.py` |
| [sources.md](sources.md) | 证据账本（ID / 主张 / 来源 / 日期 / 原文 / 强度） |
| [log.md](log.md) | 过程记录、失败与放弃方向 |
| [experiments/](experiments/index.md) | E1–E3 最小验证的代码、输入哈希与结果 |
| [experiments/g1_contract/](experiments/g1_contract/index.md) | G1a 本地映射覆盖率（三角靠枕 × 两仓 × 2026-04..09） |

## 导航说明

跨工具共享的上级目录（`docs/research/supply-chain/`、`2026-10-20/`）**不建 index.md**，
避免与 Codex / Cursor 的 PR 冲突；等三家完成后在对比会话统一生成。

## 变更记录

见 [log.md](log.md)。
