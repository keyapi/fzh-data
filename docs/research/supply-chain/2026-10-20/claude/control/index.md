---
okf: v0.1
type: Index
title: 自动补货项目控制面索引
date: 2026-10-23
---

# 控制面入口

| 需要了解 | 文档 |
|---|---|
| 整体目标、里程碑、任务与验收 | [PROJECT_ROADMAP](PROJECT_ROADMAP.md) |
| 当前完成情况和下一动作 | [PROJECT_BOARD](PROJECT_BOARD.md) |
| 向老板汇报 | [BOSS_BRIEF](BOSS_BRIEF.md) |
| 为什么用库存业务指标而非准确率选模 | [INVENTORY_EVALUATION](INVENTORY_EVALUATION.md) |
| 角色句柄/重启交接 | [HANDOFF](HANDOFF.md) |
| 决策的历史依据 | [DECISIONS](DECISIONS.md) |
| 已有研究采纳与未采纳 | [RESEARCH_ADOPTION](RESEARCH_ADOPTION.md) |
| 旧里程碑与完整审计轨迹 | [CONTROL](CONTROL.md) |
| 监督触发与协调规则 | [SUPERVISOR](SUPERVISOR.md) |
| 变更记录 | [log](log.md) |

## 外部协作（Jack · W1 供应时间线）

| 需要了解 | 文档 |
|---|---|
| **Jack 唯一入口** | [handoffs/JACK_ENTRY](handoffs/JACK_ENTRY.md) |
| **Jack 唯一问答日志** | [handoffs/JACK_QA](handoffs/JACK_QA.md) |
| Jack 任务书（W1–W4） | [handoffs/2026-10-23-jack-supply-timeline](handoffs/2026-10-23-jack-supply-timeline.md) |
| 早期七问答复（归档） | [handoffs/2026-10-23-jack-w1-answers](handoffs/2026-10-23-jack-w1-answers.md) |
| R1 详细答复（2026-10-26） | [handoffs/2026-10-26-jack-w1-answers-r1](handoffs/2026-10-26-jack-w1-answers-r1.md) |
| 数据/背景读取地图 | [handoffs/2026-10-23-jack-data-map](handoffs/2026-10-23-jack-data-map.md) |
| 阅读顺序 + 旧版识别 | [handoffs/2026-10-23-jack-reading-list](handoffs/2026-10-23-jack-reading-list.md) |
| W1/W3 验收契约 | [reviews/2026-10-23-sc14-spec](reviews/2026-10-23-sc14-spec.md) + `experiments/sc14/` |
| 9 个冻结 SKU | [reviews/2026-10-23-jack-sample10](reviews/2026-10-23-jack-sample10.md) |
| 履约查询统一入口（#291，已合并 `3405ac10`） | `EN_API/fulfillment_query.py` + `supply_chain_visibility/AGENT_HANDOFF.md` |

> 沟通通道：分支 `docs/jack-w1-channel`；PR 评论用 `[W1-Qxx]` / `[W1-Axx]`。
> 技术口径可直接对话；业务决策（服务水平/预算/交期假设/采购授权）仍由用户拍板。
> **公开仓库不放行级业务 CSV/JSON**（D33）。

任务书在tasks，具体成果在reviews；301独立审核在其自己的工作区。业务数据不要提交公开仓库。
