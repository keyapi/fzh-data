---
okf: v0.1
type: Reference
title: EN 供应链全链路实体地图与仓库覆盖盘点
description: ERPNext(生产) 里从销售订单到销售出库的**全部单据与自定义 app**，以及本仓库已覆盖哪些、空白在哪（2026-10-13 API 实测版）
date: 2026-10-13
category: reference
module: en_api
tags: [erpnext, supply-chain, doctype, light-mes, work-order-task, delivery-plan, cutting,
       initial-work-order, tracking-number, job-card-scan, wip-transfer, gap-analysis]
---

# EN 供应链全链路实体地图与仓库覆盖盘点

> **事实来源**：2026-10-13 用 REST API 对生产 `erpnext.vilavi.cn` 枚举 DocType + dump 字段 +
> **取真实记录数**（这一步推翻了「建了即用」的假设）+ 仓库只读盘点。**不含头程/海运/国外仓**（外置，见蓝图 §5.2）。

## 0. 一句话：设计 vs 现网（最重要的更正）

车间执行层的 doctype **建了 ≠ 在用**。实测生产库记录数：

| 单据 | app | 生产记录数 | 实际由谁承担 |
|---|---|---|---|
| `Initial Work Order`（**开料工单**，name 是纯数字如 `753`） | Light Mes | **750** | ✅ **开料主力** |
| `Tracking Number`（**菲号**） | Light Mes | **4887** | ✅ 在用 |
| `Job Card`（**扫码报工**，48k 条） | Manufacturing + Light Mes 自定义字段 | **48854** | ✅ 真实进度源 |
| `Job Card Scan Input` | Light Mes | `issingle=1` | 扫码台**单例表单**，非数据表 |
| `Cutting Plan` / `Cutting Task` | Work Order Task | **0 / 0** | ❌ 未用 → 由 `Initial Work Order` 一步承担 |
| `Work Order Split` | Work Order Task | **0** | ❌ 未用 → 数量/结构变更走 ERPNext 原生 **Cancel+Amend** |
| `Wip Transfer`（含 `is_return`） | Light Mes | **0** | ❌ 未用 → WIP 外包改由 **`Job Card` 自定义字段**承载 |

## 1. 自定义 app 拓扑（各自独立仓库）

这些是**各自独立的 GitHub 仓库**（组织 `keyapi`），源码在各服务器 `frappe-bench/apps/<app>/`，
发布走 `CONTRIBUTING.md` 「EN 自定义 app 的开发与发布流程」。**没有**一个统一的 house app：

| app | 仓库（推断/已证） | 性质 | 主要单据 |
|---|---|---|---|
| **`key_test`** | `keyapi/key_test`（私有）| **house app**（SO/Item 定制主战场） | 自定义字段、`public/js/sales_order.js`、Script Report（如 `bom_cost_list`）、whitelist 方法（如 `item_utils.read_excel_file`） |
| `light_mes` | `keyapi/light_mes`（推断） | 车间 MES | `Initial Work Order`、`Tracking Number`、`Job Card Scan Input`、`Wip Transfer`、工序价、不良码 |
| `work_order_task` | `keyapi/work_order_task` | 工单任务 | `Cutting Plan`、`Cutting Task`、`Work Order Split`（均未投产） |
| `delivery_plan` | `keyapi/delivery_plan`（推断） | 出货计划 | `Delivery Plan`、`Outer Box Number`；也放 `Item Customer Detail.special_mark` 等 fixtures |
| `tongtool_integration` | `keyapi/tongtool_integration` | 通途/平台 | `Tongtool Order`/`Package`、成本类 |
| `vilavi_pim` | `keyapi/vilavi_pim` | PIM | 物料组/属性 |

> ⚠️ `key_test` 是分支割裂例外（历史，2026-10-08 已统一到 `main`@`6f0940d`），动前先问负责人。

## 2. 真实全链路（实体级，实测连接键）

```
Sales Order ─(Sales Order Item.name / customer_item_code)─┐
   ├─ Production Plan ─► Production Plan Item（sales_order_item 为连接键）
   │      └─ Work Order  生产工单（production_item = PK# 皮壳 或 KS 成品）
   │           │
   │           │ (A) 开料 ★Initial Work Order（name=纯数字，workstation=裁床）
   │           │       ├─ Initial Work Order Item.work_order ─► Work Order（一张 IWO 覆盖多张皮壳 WO）
   │           │       ├─ required_items.item_code ─► Item（面料/拉链，带批次）
   │           │       └─ Woker Order Allocation.{work_order, group_number,
   │           │             tracking_number─►Tracking Number, job_card─►Job Card, fg_item}   ← 拼写照抄
   │           ▼
   │      Tracking Number（菲号 = "<皮壳WO>-NNN"）4887 条
   │           ├─ work_order ─► Work Order（皮壳）
   │           ├─ finished_product_work_order ─► Work Order（成品）  ← 949 条两侧不同；448 条为空（已知断点）
   │           ├─ so_materials ─► Item（交付物料）
   │           └─ initial_work_order ─► Initial Work Order
   │           │
   │           │ (B) 扫码报工 ★Job Card Scan Input（Single，扫工单+菲号+工序）──► Job Card 48854 条
   │           │       Job Card.{work_order, operation_id, sequence_id,
   │           │         tracking_number(Data), time_logs[].employee,
   │           │         custom_is_subcontracting/custom_supplier/{sent,received,invoiced}_qty}  ← WIP 外包
   │           ▼
   │      Stock Entry(Manufacture / Material Consumption)  完工入库/发料（带 tracking_number 维度）
   │
   ├─ (物料需求) Material Request ─► Purchase Order ─► Purchase Receipt   ← EN 侧基本空白
   │
   └─ Delivery Plan 出货计划 ──► Delivery Note 销售出库（行带菲号）──► 报关导出 / 回写通途采购单
                                    └─ Tongtool Order（平台账单侧）
```

**关键连接键汇总**：`Sales Order Item.name`（主键）；`Work Order.production_item == SO Item.item_code`；
`Job Card.work_order` + `operation_id`（聚合键）；`Tracking Number.work_order` / `finished_product_work_order`；
`Initial Work Order Item.work_order`；`Delivery Note Item.against_sales_order / so_detail`。
**所有车间环节都能经 `Work Order` 挂到 `Sales Order Item`** —— 无需新主键。

## 3. 本仓库覆盖 vs 空白

| 环节 | 覆盖 | 落点 |
|---|---|---|
| 通途 SKU → EN 物料登记 | ✅ | `missing_products/` |
| SO→PP→WO→JC→DN（阶段 0–3） | ✅ 扎实 | `EN_API/item_shipment_status.py`、`fulfillment_query.py`、`dn_trace_report.py` |
| 完工入库/发料（Stock Entry） | ✅ 反向 | `dn_trace_report.py`；工单审计 `erpnext/`+skill |
| 销售出库→报关 / →通途采购单 | ✅ | `customs_export.py`、`tongtool_purchase/` |
| **开料 Initial Work Order** | ⚠️ 仅口径散见 | `AGENT_HANDOFF_WO-26-02571.md`、`docs/fac-dev-notes.md` |
| **菲号 Tracking Number / 扫码 Job Card 自定义字段** | ⚠️ 散落在 DN/WO handoff | `AGENT_HANDOFF_DN-26-00080_82_83.md`、`_WO-26-02571.md` |
| **出货计划 Delivery Plan** | ⚠️ 只有性能/占用脚本，无结构文档 | `AGENT_HANDOFF_delivery_plan_perf.md`、`dp_*.py`、`patch_dp_*.py` |
| **Cutting Plan/Task、Work Order Split、Wip Transfer** | ➖ **生产未用**（0 条），无需覆盖 | — |
| **Material Request / Purchase Order / Purchase Receipt** | ⚠️/❌ EN 侧基本空白（仅审批工作流 JSON） | `EN_API/prod_wf_物料需求审批V6*.json`、`prod_wf_采购订单审批V4*.json` |
| 头程/海运/国外仓（阶段 4–8） | ❌ 外置；**2026-10-13 决定暂缓** | 蓝图 §5.2 |

## 4. 结论

- **阶段 0–3** 由 `EN_API/` 覆盖扎实；**车间执行层**（开料 `Initial Work Order`、菲号 `Tracking Number`、`Job Card` 自定义字段）**只在 handoff 里散落提及，无系统化覆盖**，但它们**都能经 `Work Order` 挂到 `Sales Order Item`**。
- **四个 app doctype（Cutting Plan/Task、Work Order Split、Wip Transfer）建了但零记录** —— 做覆盖前先确认在用版本（本页已列为「未用」）。
- **物料需求 / 采购 / 采购入库** EN 侧基本空白（按用户指示先记录不做）。
- **头程阶段** 外置且已决定暂缓。

> 呈现形式（报表/大屏/AI/嵌入单据）调研与建议 → `docs/solutions/architecture-patterns/supply-chain-visibility-forms-research.md`。
