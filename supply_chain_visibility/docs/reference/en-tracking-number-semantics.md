---
okf: v0.1
type: Reference
title: 菲号（Tracking Number）语义与「工单→菲号→工序卡」层级
description: 菲号=一批皮壳/半成品实物流的身份证，开料按组生成、贯穿该工单全部工序；每个菲号每工序恰1张Job Card；决定链条可视化弹窗的正确层级
date: 2026-10-13
category: reference
module: supply_chain_visibility
tags: [erpnext, tracking-number, 菲号, work-order, job-card, initial-work-order, light-mes]
---

# 菲号（Tracking Number）语义

> 2026-10-13 用**生产**数据 + `light_mes`/`work_order_task` 代码查清。这是「链条弹窗该按什么层级展示」的依据。

## 1. 一句话

**菲号 = 一批（组）皮壳/半成品生产单元的「实物流身份证」**。开料（`Initial Work Order`）时按「组」生成，
`name = <皮壳工单>-NNN`，`qty` = 该批件数。它**不是一件成品**、也**不是某一道工序的一批**，
而是**贯穿该皮壳工单全部工序（实测 6–9 道，最多 11 道）**的一批件。
**成品(KS)工单基本没有菲号**（1118 张 KS 工单仅 3 张，测试残留）。

## 2. 关系与基数（实测）

```
Work Order(皮壳 PK#/ND#)
  └─ Initial Work Order(开料) ── Woker Order Allocation 子表  ← 菲号的「出生点」(1:1)
        ▼
  Tracking Number(菲号=<皮壳WO>-NNN)   4887 条 / 1344 张工单
       ｜  每个菲号在每个工序 恰 1 张 Job Card
        ▼
  Job Card(扫码报工)  ← 每张恰 1 个菲号(tracking_number) + 1 道工序
        ▼
  Stock Entry(Manufacture 完工入库 / Material Consumption 耗料) 带菲号
        ▼
  Delivery Note Item.stock_tracking_number  ← 销售出库绑菲号
```

| 关系 | 基数 | 备注 |
|---|---|---|
| Work Order → 菲号 | **1:N**（均值 3.6，最多 56） | 这些菲号是**贯穿全工序的多个「组」**，不是同工序多批 |
| 菲号 → Job Card | **1:N**（均值 6.9，最多 14） | 一个菲号跨 6–9 道工序 |
| 菲号 → 工序 | 一个菲号 ≈ **6–9 道**（最多 11） | 工序是菲号内部的**顺序轴** |
| Job Card → 菲号 | **N:1**（每张恰 1 个） | 实测无多值 |
| 菲号 → Work Order | **N:1**（`work_order` 恒非空） | 不跨工单复用 |
| 菲号 → `Initial Work Order` | N:1，**100% 有值** | 菲号必来自开料 |
| 菲号 → `finished_product_work_order` | N:1，448 空 / 949 异 | 「皮壳批次→成品工单」的桥；**断点**已记于 DN handoff |
| 菲号 → DN Item | 1:N（3584 行 / 1652 菲号） | 销售出库按菲号绑定 |

## 3. 结论：链条弹窗的正确层级

**= 工单 → 菲号 → 逐工序 Job Card**（工序是菲号内部的轴，**不是**树的父节点）。

- 唯一键 `(菲号, 工序)` → 天然是树的叶子。
- 「工单 → 工序 → 菲号」是**转置投影**，会把一个菲号撕到多个工序节点里，无法表达「这一批走到哪了」。
- 原生 UI 同构：`work_order_task` 在**工单表单**挂「开料工单 + 跟踪单号」，在**菲号表单**挂「工序卡」计数
  （`tracking_number_dashboard_extension.js` / `work_order_dashboard_extension.js`）。
- **本项目已按此重构**（`key_test/so_chain.py` + JS v4）：弹窗 = 工单 → 菲号(`<details>`折叠) → 工序卡表；另列「未绑定菲号的报工」。

**当需要「哪一批堵在哪道工序」的看板时**，可再加「工序 × 菲号」矩阵（同一份数据的透视），但主干不变。

## 4. 代码依据

- `light_mes/.../api.py`：`generate_tracking_numbers`（`f"{work_order}-{NNN:03d}"`）、`generate_combined_tracking_numbers`（拼卷父菲号，**未投产**：`is_parent_tracking_number` 生产全 0）。
- `light_mes/.../doc_events.py::work_order_on_submit`；`Light Mes Settings.work_order_is_tracking_number = 0`。
- `work_order_task/.../overrides/initial_work_order_override.py::generate_work_order_allocations`（菲号落库于 `Woker Order Allocation`）。
- `work_order_task/.../public/js/{tracking_number,work_order}_dashboard_extension.js`。
