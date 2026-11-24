---
okf: v0.1
type: Index
title: 供应链研究 2026-11-24 — 证据链 / Agent 接口 / 默认参数 / 统一契约
description: 同日四份研究：补货证据链与人工闭环、Agent 数据读写接口、可配置默认值、统一数据契约 v1
tags: [supply-chain, research, evidence-chain, human-in-the-loop, agent-interface, defaults, contract, index]
---

# 2026-11-24 供应链研究

四份同日研究，来自四个并行分支，本目录合并入库，**内容未改**（只重写本索引与日志）。

| 文档 | 类型 | 一句话 |
|---|---|---|
| [evidence-chain-and-human-loop.md](evidence-chain-and-human-loop.md) | Research | 证据链逐字段定义（需求/供给/计算/来源/人工五段）、对照 11-13 抽查的差距清单（A 数据未接 / B 口径有误 / C 留痕缺失）、人工判断类型与防自批模型，以及 FVA + override + tracking signal + Diebold–Mariano 的闭环评估与四层 UI。 |
| [agent-data-interface.md](agent-data-interface.md) | Research | Agent 数据读写接口分工：REST/OpenAPI 为业务契约、MCP 为任务适配、CLI 为批处理入口、语义层为共同语言；含接口目录、权限与审计分级、开源选型、8 项 MVP 验收。 |
| [decision-defaults.md](decision-defaults.md) | Research | 可配置默认值建议表：分档、分位、交期、新鲜度、授权范围、评估窗等参数的作用域/审批人/失效方式，`po_on_time` 三态，以及不可解除的硬约束与版本化回退。 |
| [unified-data-contract.md](unified-data-contract.md) | Spec | 统一数据契约 v1：7 维 `scope_key` + `snapshot_id` → `row_id`、行级证据信封（来源/时点/口径/未知语义）、人工判断与审核写入、`MODEL_ONLY`/`FULL_FLOW` 闭环评估、REST/MCP/CLI 与权限映射、迁移与 35 项验收清单；§0.3 对三份研究的 7 处冲突逐条裁决。 |

## 阅读顺序建议

1. 先读**统一数据契约**（Spec）看全局与结论；
2. 再看**证据链**（为什么每个数字要可回溯、人工判断如何留痕）与**默认参数**（哪些阈值可配、谁能改）；
3. 最后看 **Agent 接口**（这些字段以什么形态暴露给 Agent / 人 / 批处理）。

## 边界（四份文档共同声明）

- 只做调研与设计：**不改业务代码、不部署、不写生产数据、不调用 EN 写接口**。
- 本仓库为 PUBLIC：只写口径、字段、路径与行号，**不写分行数量、SKU 级库存、客户名明细、凭证**。
- 证据等级统一为 **L** 本地事实 / **F** 外部事实 / **R** 建议（需实施验收）/ **U** 未核实（不得当现状）。

## 上级

- [供应链研究索引](../index.md)
- [本目录变更日志](log.md)
