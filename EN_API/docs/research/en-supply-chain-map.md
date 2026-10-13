---
okf: v0.1
type: Reference
title: EN 供应链全链路实体地图与仓库覆盖盘点
description: ERPNext(生产) 里从销售订单到销售出库的**全部单据与自定义 app**（含开料/扫码/采购/出货计划），以及本仓库已覆盖哪些、空白在哪
date: 2026-10-13
category: reference
module: en_api
tags: [erpnext, supply-chain, doctype, light-mes, work-order-task, delivery-plan, cutting,
       job-card-scan, wip-transfer, material-request, purchase-order, gap-analysis]
---

# EN 供应链全链路实体地图与仓库覆盖盘点

> **本文回答**：EN 里「下单→出库」到底经过哪些单据？本仓库的工具覆盖到哪、哪里是空白？
> 事实来源 = 2026-10-13 用 REST API 对生产 `erpnext.vilavi.cn` 的 DocType 枚举 + 字段 dump，
> 加仓库只读盘点。**不含头程/海运/国外仓**（那部分外置，见蓝图 §5.2）。

## 1. EN 上的自定义 app（不是原生 ERPNext）

| 模块 | 性质 | 主要单据 |
|---|---|---|
| `Light Mes`（13 单据） | **车间 MES 层** | `Initial Work Order`（初次/领料工单）、`Job Card Scan Input`（工人扫码）、`Tracking Number`（跟踪单号/菲号）、`Wip Transfer`（在制转移/外发回收，含 `is_return`）、`Defect Code`、`Operation Price*` / `Subcontracting Service Price`、`User Employee Group` |
| `Work Order Task`（5 单据） | 工单任务/开料 | `Cutting Plan`（开料计划）、`Cutting Task`（开料任务）、`Work Order Split`（工单拆分）、`Hour Rate`、`Spec3d Operation Price` |
| `Delivery Plan`（4 单据） | **出货计划** | `Delivery Plan`（`sale_orders`/`item_qties`/`items`/staging/实际交付 字段齐全）、`Outer Box Number`（外箱号）、`Sellfox Settings`、`Tencent TMT Settings` |
| `Tongtool Integration`（15 单据） | 通途/平台侧 | `Tongtool Order`/`Item`/`Package`、`Excel Tongtool Order`、成本类、`Tongtu Shipping Warehouse` |

原生仍用：`Sales Order`、`Production Plan`、`Work Order`、`Job Card`、`BOM`、`Stock Entry`、`Material Request`、`Purchase Order`、`Purchase Receipt`。

## 2. 真实全链路（实体级）

```
Sales Order ──(客户物料号 ref_code / customer_item_code)──┐
   │                                                      │
   ├─ Production Plan ─► Production Plan Item（sales_order_item 为连接键）
   │       └─ Work Order  生产工单
   │            ├─ Work Order Split        工单拆分（关键物料、拆分明细）
   │            ├─ Cutting Plan / Cutting Task   开料计划/任务（待裁剪→裁剪中→已完成）
   │            ├─ Initial Work Order     初次/领料工单（employee/workstation/领料/跟踪单号）
   │            │     └─ Tracking Number  跟踪单号（菲号，扫码标识；挂 work_order/item）
   │            │           └─ Job Card Scan Input  工人扫码（operation/employee/良品数/不良数）
   │            │                 └─ Job Card        工序卡 ★真实进度
   │            ├─ Wip Transfer           在制转移/外发回收（From/To Supplier，可 is_return）
   │            └─ Stock Entry (Manufacture)  完工入库；Material Consumption 生产发料
   │
   ├─ (物料需求侧)  Material Request ─► Purchase Order ─► Purchase Receipt
   │
   └─ Delivery Plan  出货计划（装箱/外箱/跟踪单号/待包装仓分配）
            └─ Delivery Note  销售出库 → 报关导出 / 回写通途采购单
                     └─ Tongtool Order（平台账单侧，对账用）
```

**关键连接键**（沿用 `en-order-to-shipment-chain.md`）：主键仍是 `Sales Order Item.name`；
`Work Order.production_item == SO Item.item_code`；`Job Card.work_order`；
`Delivery Note Item.against_sales_order / so_detail`。

## 3. 本仓库覆盖 vs 空白

| 环节 | 覆盖情况 | 落点 |
|---|---|---|
| 通途 SKU → EN 物料登记 | ✅ | `missing_products/`（`Item Customer Detail.ref_code`） |
| Sales Order → Production Plan → Work Order → Job Card → Delivery Note | ✅ 扎实（阶段 0–3） | `EN_API/item_shipment_status.py`、`EN_API/fulfillment_query.py`（多输入/阶段/异常/齐套）、`EN_API/dn_trace_report.py`（反向） |
| 完工入库 / 生产发料（Stock Entry） | ✅ 反向（DN→SO→WO→SE） | `EN_API/dn_trace_report.py`；工单审计 `erpnext/` + skill `erpnext-wo-audit` |
| 销售出库 → 报关 | ✅ | `EN_API/customs_export.py` |
| 销售出库 → 通途采购单 | ✅（写入通途） | `EN_API/tongtool_purchase/` |
| **出货计划 Delivery Plan** | ⚠️ 只有性能/占用类实操脚本，**无结构设计文档** | `EN_API/AGENT_HANDOFF_delivery_plan_perf.md`、`dp_*.py`、`patch_dp_*.py` |
| **开料 Cutting Plan / Cutting Task** | ⚠️ 仅"开料工单"口径散见，**无 DocType 文档** | `EN_API/AGENT_HANDOFF_WO-26-02571.md`、`docs/fac-dev-notes.md` |
| **扫码 Job Card Scan Input / Tracking Number(菲号)** | ⚠️ 散落在 DN/WO handoff，**无 MES 单据文档** | `EN_API/AGENT_HANDOFF_DN-26-00080_82_83.md`、`_WO-26-02571.md` |
| **Work Order Split** | ❌ 无 | — |
| **Wip Transfer（在制转移/外发回收）** | ❌ 无 | — |
| **Defect Code / Operation Price（MES 计价与不良）** | ❌ 无 | — |
| **Material Request（物料需求）** | ⚠️ 仅工作流导出 JSON | `EN_API/prod_wf_物料需求审批V6*.json` |
| **Purchase Order（采购订单）** | ⚠️ 仅工作流导出 JSON + 通途侧采购单 | `EN_API/prod_wf_采购订单审批V4*.json`、`tongtool_api/` |
| **Purchase Receipt（采购入库）** | ❌ 无 | — |
| 头程/海运/国外仓（阶段 4–8） | ❌ 外置；**2026-10-13 决定暂缓** | 蓝图 §5.2；数据在钉钉表 / 同事「智美通大屏」（代码未共享） |

## 4. 结论

- **阶段 0–3（SO→PP→WO→JC→DN + Stock Entry 反向）** 由 `EN_API/` 覆盖扎实；
- **车间执行细节**（开料、扫码/菲号、Work Order Split、WIP 外发）**只在 DN/WO handoff 里散落提及，无系统化覆盖**；
- **物料需求 / 采购 / 采购入库** 在 EN 侧**基本空白**（只有审批工作流 JSON）；
- **出货计划** 有实操脚本但无结构文档；
- **头程阶段** 明确外置且已决定暂缓。

> 呈现形式（报表/大屏/AI/嵌入单据）的调研与建议 → `docs/solutions/architecture-patterns/supply-chain-visibility-forms-research.md`。
