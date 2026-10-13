---
okf: v0.1
type: Reference
title: EN 通途 SKU → 销售订单 → 生产 → 销售出库 链路导航
description: 给一个通途 SKU，说明它在 ERPNext 里如何串起 销售订单/生产计划/工单/工序卡/销售出库，以及相关子项目与 PR
date: 2026-10-13
category: reference
module: en_api
tags: [erpnext, sales-order, production-plan, work-order, job-card, delivery-note,
       tongtool-sku, customer-code, fulfillment, item-shipment-status]
related_components: [item_shipment_status, dn_trace_report, erpnext-wo-audit, missing-products]
---

# EN 通途 SKU → 销售订单 → 生产 → 销售出库 链路导航

> **这是链路入口文。** 给一个通途 SKU，想在 EN（`erpnext.vilavi.cn`）里追「谁订的 → 生产到哪 → 出了多少货」，
> 先读本页认路，再跑 `EN_API/item_shipment_status.py --customer-code <通途SKU>`。
>
> 目标架构的完整设计（阶段状态机、头程、控制塔）在
> `docs/solutions/architecture-patterns/en-end-to-end-supply-chain-fulfillment-visibility.md` —— 那是**蓝图**，本页是**现状导航**。

## 1. 链路图

```
通途 SKU ─┬─ = Item Customer Detail.ref_code       （登记在「成品 KS 变体」上，唯一事实源）
          └─ = Sales Order Item.customer_item_code
                   │
                   ▼
             Sales Order              ← 子表过滤 Sales Order Item，按父单 name 去重
                   │
             Sales Order Item.name     ← 全链路主键
                   ├─ Production Plan Item.sales_order_item ─► Production Plan   （生产计划）
                   ├─ Work Order.production_item == SO Item.item_code ─► Work Order
                   │        └─ Job Card.work_order ─► Job Card   ★真实进度在这
                   └─ Delivery Note Item.against_sales_order / so_detail ─► Delivery Note （销售出库）
```

每段一句话职责：

| 段 | 职责 | 谁生产它 |
|---|---|---|
| `Item Customer Detail.ref_code` | 通途 SKU 在 EN 的登记（挂在成品 `KS` 变体上） | 人工/`missing_products` 主线登记 |
| `Sales Order (Item)` | 客户需求：谁、订多少、什么时候要 | 销售订单导入 |
| `Production Plan (Item)` | 排产：这批需求排进哪个计划 | 计划同事 |
| `Work Order` | 生产执行单 | 计划/生产下达 |
| `Job Card` | 每道工序的实际报工 | 车间扫码 |
| `Delivery Note (Item)` | 销售出库（工厂发货） | 仓库 |

## 2. 代码落点与查询链

**唯一入口脚本**：`EN_API/item_shipment_status.py`（交接文档 `EN_API/AGENT_HANDOFF_物料发货状态.md`）。

| # | 用途 | DocType | 关键 filters | 代码位置 |
|---|------|---------|-------------|---------|
| Q1 | 按客户码找单 | `Sales Order` | `[["Sales Order Item","customer_item_code","like","%码%"]]` | `find_sales_orders_by_customer_code` :390 |
| Q2 | 按物料码找单 | `Sales Order` | `[["Sales Order Item","item_code","in",[...]]]` | `find_sales_orders_by_items` :400 |
| Q3 | 订单行明细 | `Sales Order` | `get_single` → 读 `items[]` | `fetch_so_lines` :441 |
| Q4 | **销售出库** | `Delivery Note` | `against_sales_order` + `item_code` | `fetch_delivery_notes` :476 |
| Q5 | 生产工单 | `Work Order` | `[["production_item","in",[...]]]` | `fetch_work_orders` :518 |
| Q6 | 生产计划 | `Production Plan` | `[["Production Plan Item","sales_order","in",SOs]]` | `fetch_production_plans` :563 |
| Q7 | 物料主档 | `Item` | `get_single` / `[["Item Customer Detail","ref_code","like","%码%"]]` | `fetch_item_master` :613 / `resolve_customer_code` :599 |
| Q8 | 工序卡 | `Job Card` | `[["work_order","in",[...]]]`（分块） | `fetch_job_cards` :552 |

进度聚合（口径核心，勿动）：`op_progress` :653（取**第一道工序**完成量、**不跨工序求和**）、`jc_completed_qty` :636、`jobcards_by_wo` :629、`wos_for_line` :644。

### 2.1 统一查询入口（多输入 / 阶段 0–3 / 异常与下一行动）

`EN_API/fulfillment_query.py` 在引擎之上叠加（蓝图 V1）：

- **多输入**：客户码/EN 物料码混合，逗号分隔；**逐输入保留命中与未命中**（蓝图 §2.2）。
- **阶段 0–3 状态机**（蓝图 §3）：销售需求 / 待计划 / 生产中 / 工厂待出库。
- **数量阶梯 + 对账**（§3.1）：`有效需求 = 已工厂出库 + 工厂未出库`。
- **证据分层**（§4）：每个值标 `fact / derived / estimate`。
- **异常 §8 结构 + 下一行动**（§8.1 十条 V1 规则）：`severity / code / 影响量 / 责任角色 / 建议行动`。
- **多态输出**：JSON（权威）+ 控制台 + Excel（默认 9 分区；`--legacy-sheets` 复刻旧 3 Sheet）。

```bash
uv run python EN_API/fulfillment_query.py --codes "CENKZ1325-Yellow-138,PK#KS0001-DM-140-YELLOW"
uv run python EN_API/fulfillment_query.py --codes CENKZ1325-Yellow-138 --assert-fixture   # 回归自检
```

实现见 `EN_API/fulfillment/`：**包裹引擎**（复用其查询函数），不改动 `item_shipment_status.py`
—— 引擎带 fixture 断言与单测（含对 `api_get_status` 的 monkeypatch），整体搬迁会破坏其契约。
阶段 4–8（头程/到港/上架）数据不在 EN，本入口不产出（占位，V2 接钉钉表）。

## 3. 必须记住的易错口径

1. **通途 SKU 注册在成品 `KS` 上，订单行卖的是 `PK#` 皮壳** —— 两者不是同一个 `item_code`。
   实测 `CENKZ1325-Yellow-138` 注册在 `KS0001-DM-140-YELLOW`，订单行是 `PK#KS0001-DM-140-YELLOW`。
   所以「订单行物料自身的 `customer_items` 为空」是**常态**，不是数据缺失。
2. **出库单必须按 `item_code` 匹配，不能用 `customer_item_code`** —— 老单据该字段为 NULL，只按客户码会漏件
   （实测 SO-25-00067 的出库行 `customer_item_code = NULL`，靠它匹配会漏 20 件）。
3. **订单行物料码精确匹配、只有客户码允许 `like` 子串**（`item_code_equals` :141 vs `code_in` :128）。
   `KS0001-…` 不能因是 `PK#KS0001-…` 的子串而误命中皮壳。
4. **`Work Order.status` / `produced_qty` 不可信** —— 头部可能写 `Not Started` 但工序卡已有几十件。
   完成量取第一道工序（裁剪）的 `total_completed_qty`，**不能跨工序求和**（会把同一批按工序数重复累加）。
5. **ERPNext 的 `Closed` ≠ 已发完** —— 实测 3 张 `Closed` 单仍有未发量（死单）。
6. **EN 的 `po_no` 不是客户 PO 号** —— 是离职同事自编的内部流转号，**待废弃**；不得对外称客户 PO，不得用作头程键。
   头程要用 `Sales Order.name` 查钉钉「发货信息总表」。
7. **API 五条硬约束**（详见 handoff）：子表不能裸 list（403）；父单直查子字段要四元组（否则 417）；
   子表过滤一行一子行、先按父单去重；`in` 列表 `chunks(40)`；`fields` 只能是父单字段（保留 417 回退）。

## 4. 相关子项目

| 子项目 | 在链路里的角色 |
|---|---|
| **`EN_API/`** | **核心**。`item_shipment_status.py`（SO→PP→WO→JC→DN）、`dn_trace_report.py`（反向：DN→SO→WO→Stock Entry 发料）、`customs_export.py`（出库→报关）、`bom_cost_*`（BOM 成本）、`tongtool_purchase/`（出库→通途采购单） |
| `missing_products/` | 链路**起点**：通途有库存 SKU → EN 成品变体 `customer_items.ref_code` 的匹配/登记 |
| `erpnext/` + skill `erpnext-wo-audit` | 只覆盖**生产工单**这一段（「一键完工」假数据稽查视角），**不碰 SO/DN/通途 SKU** |
| `tongtool_api/` | 通途 ERP2 API（含采购单→EN DN 的映射口径） |
| `tongtool_order_cost/`、`tongtool_order_shipping/` | 通途订单成本链 / 面单背贴（旁支） |
| `item_cost_sx/`、`stock_init/`、`warehouse_restock/` | 下游：EN BOM 成本 → 赛狐采购成本/库存/备货单 |

## 5. 相关 PR

| PR | 内容 | 状态 |
|---|---|---|
| [#231](https://github.com/keyapi/fzh-data/pull/231) | **物料发货状态报表脚本**（`item_shipment_status.py`）+ Closed 死单/工单进度结论 | MERGED |
| [#114](https://github.com/keyapi/fzh-data/pull/114) | 销售出库→物料移动追溯报表（`dn_trace_report.py`） | MERGED |
| [#193](https://github.com/keyapi/fzh-data/pull/193) / [#198](https://github.com/keyapi/fzh-data/pull/198) | 销售出库→报关单据导出 + BOM 成本参照 | MERGED |
| [#271](https://github.com/keyapi/fzh-data/pull/271) | 端到端供应链履约查询蓝图 + 钉钉表只读模块 | MERGED |
| [#78](https://github.com/keyapi/fzh-data/pull/78) | erpnext 工单排查方法论 + 一键完工检测 | MERGED |
| [#236](https://github.com/keyapi/fzh-data/pull/236) | 通途 ERP2 采购单 API + EN DN 映射链 | MERGED |
| [#162](https://github.com/keyapi/fzh-data/pull/162) | missing_products 三方主线审计修正 | MERGED |
| [#290](https://github.com/keyapi/fzh-data/pull/290) | 沉淀「通途同步五类缺陷」（Tongtool Order 空壳单/拆单缺父单） | **OPEN** |

## 6. 最新实跑快照

**日期 2026-10-13**，`--customer-code CENKZ1325-Yellow-138`（客户美中公司 DANEEY，仓库「半成品仓 - FZH」）：

```bash
uv run python EN_API/item_shipment_status.py \
  --customer-code CENKZ1325-Yellow-138 \
  --env-file "D:/Work/赛狐/Cursor/EN_API/.env"      # worktree 无 .env，指父仓库
```

- 10 张 SO / 330 件 = **有效 310 + 已改单(作废) 20**
- 已发 **166** / 未发 **144**（`DN 实算未发 144 == ERP delivered_qty 口径 144` ✓）
  - 死单(Closed 未发) **64** = SO-25-00198 4 + SO-26-00003 20 + SO-26-00099 40
  - 在产/待发 **80** = SO-26-00110（WO-26-03264 1/9 工序）
- 出库单 5 张：DN-25-00043(20) / DN-25-00138(60) / DN-26-00003(26) / DN-26-00039(20) / DN-26-00089(40)
- 工单 18 张；工序卡 143 张覆盖 18 张工单；生产计划 6 张
- `--assert-fixture`：**稳定档 14/14 通过，exit 0**（漂移仅在「在产快照」，属预期）

> 这是**活业务对象**：已发/未发会随发货推进而变（基线 2026-09-14 是 126/184，本轮 166/144）。
> 稳定档（so_count / order_qty / DN 行数 / master_item / PP 覆盖 / 工序下界）不变，才说明口径没漂。

## 7. 上下游与缺口

| 环节 | 现状 |
|---|---|
| 通途 SKU → EN 物料 | ✅ `resolve_customer_code` :599 |
| SO / PP / WO / JC / DN | ✅ `item_shipment_status.py` 全覆盖 |
| 生产发料（Stock Entry） | ✅ 反向走 `dn_trace_report.py` |
| **头程/海运/国外仓（阶段 4–8）** | ❌ 数据在**钉钉表**，**尚未接入**；目前只能用「下单 + 3 个月」粗估。**2026-10-13 决定暂缓接入** —— 同事另有「智美通数据大屏」实现但**代码未共享**，待评估如何移植到 EN（见蓝图 §5.2） |
| 退货净额抵扣 | ❌ 未做 |
| 整单齐套 | ❌ 未实现（蓝图 §13.6 明确不擅自展开） |

## Related

- `EN_API/item_shipment_status.py` — 链路查询实现（SO/PP/WO/JC/DN）
- `EN_API/AGENT_HANDOFF_物料发货状态.md` — 查询链、五条 API 硬约束、业务口径
- `docs/solutions/architecture-patterns/en-end-to-end-supply-chain-fulfillment-visibility.md` — 目标架构蓝图
- `docs/solutions/workflow-issues/erpnext-so-closed-unshipped-and-unstarted-work-orders.md` — Closed 死单与工单状态口径
- `docs/solutions/conventions/tongtu-en-sellfox-instock-sku-mainline.md` — 通途 SKU ↔ EN `ref_code` 主线
- `EN_API/docs/reference/en-server-access.md` — 服务器与环境访问
