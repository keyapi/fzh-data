---
okf: v0.1
type: Reference
title: 「货物到哪了」查询方法 — 四个数据源的可靠性分级与查询顺序
date: 2026-09-16
last_updated: 2026-09-16
category: workflow-issues
module: fulfillment-tracking
problem_type: workflow_issue
component: multi-source-reconciliation
severity: high
applies_when:
  - "要回答某个 SKU / PO / 批次的货现在到哪了"
  - "判断某批货是否已发出、是否已到国外仓"
  - "不同系统给出的日期互相矛盾，需要定谁为准"
tags: [erpnext, tongtool, dingtalk, ups, supply-chain, data-reliability, reconciliation]
related_components: [item_shipment_status, dingtalk_sheet, ups_track, tongtool_api, pb_orders]
---

# 「货物到哪了」查询方法

## 0. 核心原则

**先明确问的是哪个「到哪了」，再用对应来源回答。** 四个节点各有唯一可信来源，
混用就会拿错起算点做推算 —— 本文档就是从一次真实错误里总结出来的。

| 问的是 | 唯一可信来源 | 性质 |
|--------|-------------|------|
| 工厂出货了吗 | **EN Delivery Note `posting_date`** | 事实（单据） |
| UPS 收到了吗 | **UPS Track API 首个非 `MP` 节点** | 事实（承运人） |
| 到国外仓了吗 | **没有可靠来源** | 见 §3 |

## 1. 来源可靠性分级

### ✅ 事实层（可直接当结论）

| 来源 | 字段 | 说明 |
|------|------|------|
| EN Sales Order | `transaction_date` / `delivery_date` | 下单日 / 交货日 |
| EN Delivery Note | `posting_date` | **工厂出库日**（docstatus=1 才算） |
| EN Job Card | `status` / `total_completed_qty` / `actual_end_date` | 真实生产进度（**不要看 WO 头部**） |
| EN Bin | 各仓 `actual_qty` | 记账结存；含 `波兰PL到货仓` / `美中USTX到货仓` 等**海外到货仓** |
| UPS Track API | 首个非 `MP` 节点时间 | 承运人实际收件 |

### ⚠️ 登记层（可参考，但要说明是登记值）

| 来源 | 字段 | 注意 |
|------|------|------|
| 通途 API | `availableStockQuantity` | **美中的「可用 0」不可信** —— 通途为标记发货必须先报溢，实际流程是试探性发货 |
| 通途 API | `intransitStockQuantity` | 在途，较可信 |
| 通途 API | `PONum` | 通途采购单号（本身可信，是通往钉钉表的钥匙） |
| 通途 API | `purchaseDate` | **≠ 工厂发货日**（实测晚约 4 天） |
| 通途 API | `purchaseArrivalDate` | **未校验**，无独立来源可比对 |
| 钉钉 物流信息表 | `工厂发货日期` | 登记值，通常接近真实 |
| 钉钉 物流信息表 | `预计到货日期` / `实际签收日期` | **绝大多数为空**（实测 16 行只有 1 行填了） |
| 钉钉 物流跟踪Tracking | `离港` / `到港` / `入库` | 登记值；**近期批次常为空** |
| 钉钉 2026年度订单明细 | 工厂四件套 | 登记值；**可能滞后于实际生产** |
| PB orders `shipment *.csv` | ASN / `Ship Date` / 跟踪号 | **只证明「我们标记了发出」**，不等于 UPS 揽收 |

### ❌ 不可用作履约事实

| 来源 | 原因 |
|------|------|
| 赛狐库存 / 海外仓备货单 | 安全冗余数量，采购与成本口径 |
| 「下单 + 3 个月」 | 业务约定，非系统字段 |

## 2. 查询顺序

```text
Step 1  定位实体
        客户码 / 通途SKU → EN 物料        Item Customer Detail.ref_code
        PB PO            → EN 单          Tongtool Order  name = PBUS-<PO>（拆单为 -1/-2）
        批次号           → EN 销售订单     Sales Order.po_no（波兰/美中批次号就存在这里）

Step 2  EN 事实层（最硬）
        Sales Order  → 下单日 / 交货日 / 内部流转号
        Delivery Note→ 工厂出库日 + 数量（docstatus=1）
        Work Order + Job Card → 生产进度（以工序卡为准）
        Bin          → 各仓结存（含海外到货仓）

Step 3  通途（**只取单号与在途，不用日期做推算**）
        erp2_stocks_stocksquery          → 可用 / 在途（warehouseName 必填）
        erp2_purchase_purchaseorderquery → PONum（**钥匙**）、warehouseName、in_quantity

Step 4  钉钉（按 PONum 或批次号）
        物流信息表            → 工厂发货日期 + 物流单号(ZMT…) + 送货地
        物流跟踪Tracking      → 离港 / 到港 / 入库
        2026年度订单明细      → 工厂四件套

Step 5  承运人（真实运输事实）
        UPS Track API（ups_track）→ 是否已收件
        船期                      → 拿物流单号问货代（**没有系统源**）
```

## 3. 推不出来的东西（不要给结论）

| 想得到 | 为什么给不出 |
|--------|--------------|
| **到国外仓的日期** | 钉钉「预计到货/实际签收」大多为空；通途 `purchaseArrivalDate` 未校验；发货信息总表可能读不到 |
| 通途到货日期准不准 | 需要独立的到货记录交叉验证。钉钉物流信息表只存最近十几条，历史采购单不在里面；EN 无「美中到货」字段 → **无源可比** |
| 从「采购日」推 ETA | 起算点错（采购日 ≠ 工厂发货日） |

## 4. 四个已实测的坑

1. **通途采购日 ≠ 工厂发货日**。实测 `PO021711` 采购 `2026-08-26`，钉钉登记工厂发货 `8月22日`，晚 4 天。
2. **通途「可用库存 0」≠ 断货**。通途为标记发货必须先报溢让库存够扣减，实际是「试探性发货」（PB 订单照常发美中仓，有货发走、没货才回话）。
3. **我方 ASN / shipment csv ≠ 实际发出**。必须查 UPS 是否已收件；实测 9 月 120 个跟踪号里 10 个仍停在 `Shipper created a label`。
4. **WO 头部状态不可信**。以 Job Card 为准（实测 WO 头 `Not Started` 但工序卡已过 4 道）。

## 5. 已实测案例：`CEN961NLinen-SageGreen-153` 的 150 件

```text
SO-26-00089   下单 2026-07-30，交货 2026-08-15
   ↓  DN-26-00067（150 件，PK#KS0001-DM-153-GRASSGREEN）  ← EN 事实：工厂出库 2026-08-21
   ↓  通途 in_quantity=None                                 ← 登记：尚未到美中
   ↓  PONum PO021711 / 物流单号 ZMT26081716 / 普船 / TX 77099  ← 钉钉登记：工厂发货 8月22日
   ↓  预计到货 / 实际签收 = 空                               ← 无 ETA
   ✗  到美中日期：推不出
```

**能给的结论**：工厂 8/21 已出库 150 件、已拼柜（PO021711+PO021714 单）、普船发美中、截至查询时未到仓。
**不能给的结论**：哪天到美中。

## 6. 写结论时的措辞要求

- 事实 → 「已出库 150 件，出库单 DN-26-00067，日期 2026-08-21」
- 登记 → 「钉钉登记工厂发货 8月22日（登记值）」
- 估算 → 「按 +3 个月粗估为 10/30（业务约定，非系统字段）」
- 推不出 → **明说「无可靠来源，需要问货代/物流同事」**，不要用别的字段凑一个数

## Related

- `docs/solutions/workflow-issues/pb-out-of-stock-notification-and-zero-stock-orders.md` — PB 0 库存导出、UPS 收件口径、报溢机制
- `docs/solutions/architecture-patterns/en-end-to-end-supply-chain-fulfillment-visibility.md` — 履约查询蓝图
- `dingtalk/dingtalk_sheet/AGENT_HANDOFF.md` — 钉钉表只读读取
- `tongtool_api/AGENT_HANDOFF.md` — 通途 ERP2 API / 限流
- `ups_track/README.md` — UPS 官方 Track API
- `docs/solutions/workflow-issues/erpnext-so-closed-unshipped-and-unstarted-work-orders.md` — EN 侧口径与 Job Card 规则
