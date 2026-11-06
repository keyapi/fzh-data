---
okf: v0.1
type: Index
title: 通途订单规则库（canon）索引
description: 通途订单处理规则的唯一事实源；MVP 已含订单全集、分组合并、计价矩阵、冲突登记与机器可读规则
tags: [tongtool, order, canon, index]
---
# 通途订单规则库（canon）

> **状态：MVP canon v0.1（2026-11-06）。**
> `01 / 02 / 03` 是规范正文；`rules.yaml` 是可执行副本；`07` 是活冲突登记。
> `04 / 05 / 06` 尚未撰写，按需补齐。旧 `cost-engine-spec` 页面自 2026-11-06 起保留为**证据**，不再定义口径。

## 阅读路径

**第一次读：`01 → 02 → 03`**（订单身份 → 怎么合并 → 怎么计价）。
之后按需查 `04–07`；遇到「为什么两边不一致」直接看 `07`。

| 顺序 | 文件 | 回答什么 |
|---|---|---|
| 1 | [01-order-universe.md](01-order-universe.md) | 哪些行算数；原始订单/作废原单/拆分子单/FBA/退货 |
| 2 | [02-grouping-and-merge.md](02-grouping-and-merge.md) | 何时不合并、何时合并、件数取谁、共享组件谁定产品、单独卖后缀为何不是歧义 |
| 3 | [03-price-matrix.md](03-price-matrix.md) | 后缀 × 发货方式 × 目的地 × 是否 FBA 的四列矩阵 |
| 4 | [04-cost-sources.md](04-cost-sources.md) | 皮壳/头程/加工/绍兴/自采购/套件的取值链与时点 |
| 5 | [05-special-flows.md](05-special-flows.md) | 90 天改单窗口、尾程缺口/账单来源、补发/云仓、非商品边界 |
| 6 | [06-implementation-map.md](06-implementation-map.md) | 规则 → EN / 本地 / Colab / GS 的当前落点（文件/函数 + 观测日） |
| 7 | [07-conflicts.md](07-conflicts.md) | 15 条冲突的 owner、截止日、影响、下一动作 |

## 文件

| 文件 | 类型 | 状态 | 说明 |
|---|---|---|---|
| [00-audit-report.md](00-audit-report.md) | Reference | 证据/审计 | 源清单、24 个规则主题三层对照、15 条冲突、12 项缺口 |
| [01-proposed-structure.md](01-proposed-structure.md) | Reference | 方案 | 存储形态取舍、目录结构、权威分层、迁移步骤 |
| [01-order-universe.md](01-order-universe.md) | Reference | **canon** | 订单全集与身份 |
| [02-grouping-and-merge.md](02-grouping-and-merge.md) | Reference | **canon** | 分组合并、件数、产品归属 |
| [03-price-matrix.md](03-price-matrix.md) | Reference | **canon** | 后缀/发货方式/目的地/FBA 计价矩阵 |
| [04-cost-sources.md](04-cost-sources.md) | Reference | **canon** | 四列取值链、自采购、套件 |
| [05-special-flows.md](05-special-flows.md) | Reference | **canon** | 改单窗口 / 尾程 / 补发 / 非商品 |
| [06-implementation-map.md](06-implementation-map.md) | Reference | **canon** | 规则 → 实现落点（观测日；不写行号） |
| [07-conflicts.md](07-conflicts.md) | Reference | **living** | 冲突登记与裁决推进 |
| [adr/](adr/index.md) | Decision | **accepted** | ADR-0001：成本权威口径与五链路迁移 |
| [rules.yaml](rules.yaml) | Rules | **MVP** | 31 条（30 canon + 1 unverified，decision-needed 已清零）；含 FBA-001、GRP-009/010、UNIV-005、FLOW-001~003、PRICE-011、KIT-001；证据带 [SPEC]/[EN现状]/[LOCAL实现]/[DATA] 标签 |
| [log.md](log.md) | Log | — | 变更日志 |

## 权威顺序

1. **已接受的 ADR**（裁决，可覆盖旧规范）> **规范正文**（01–03）> 冲突登记（07）> 实现映射（06）> 证据（cost-engine-spec、solutions、审计报告）。
2. 代码与规范不一致 → 先判「代码 bug」还是「规范过期」，写进 07，不允许两边都算对。
3. 旧 `cost-engine-spec` 页面只作证据；行号、当月金额、Codex 复核过程都不进规范正文。

## 边界

- 本目录**不包含**业务代码，也不替代 `tongtool_order_cost/` 的 README/AGENT_HANDOFF。
- 本目录不写 GS/EN；写回动作仍走既有脚本与审批。
- 新增/修改规则必须同步 `rules.yaml` + `log.md`；口径变更另开 `adr/`。
