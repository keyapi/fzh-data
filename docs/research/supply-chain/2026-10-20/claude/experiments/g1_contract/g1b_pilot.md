---
okf: v0.1
type: Experiment-Results
title: G1b EN 单据只读试点（单个头部 SKU）
description: 用 EN 生产只读 API 跑通 SO→DN/PP→WO→Job Card 链路，核对订单量、已发、未发、死单与未开工
date: 2026-10-20
tags: [supply-chain, g1b, erpnext, production, delivery, pilot]
---

# G1b EN 单据只读试点（单个头部 SKU）

> 目的：在跑全量前，先用一个头部 SKU 验证 EN 只读链路能否支撑 08 契约的
> 需求冲减 / 生产四量 / 互斥余额。**不是全量回放，也不写生产。**
>
> 输入：`C/Linen-Natural-194-688-wow`（2026-09 family 出库第 1，129 件）
> → BOM `KS0001-XMMBS-194-HEMPNATURAL`；EN 订单行实际物料
> `PK#KS0001-XMMBS-194-HEMPNATURAL`（皮壳/成品包装码）。
>
> 命令：
> `uv run python EN_API/item_shipment_status.py --customer-code "C/Linen-Natural-194-688-wow" --no-excel`
>
> 原始控制台输出：`out/en_customer_C_Linen_Natural_194_688_wow.txt`（不入库原始客户数据）。
> 结构化输出：`out/g1b_en_C_Linen_Natural_194_688_wow.json`（SO/DN/WO/JC/PP，已去 PII）。

## 1. 命中与数量

| 项 | 数值 |
|---|---:|
| SO 张数 | 26 |
| 订单行 | 26 |
| 订单量 | 3,220 件 |
| 有效订单量（扣改单/作废） | 3,120 件 |
| 已发（DN 实算） | 2,084 件 |
| 未发 | 1,036 件 |
| DN 张数（去重后） | 17 张 / 100 行 |
| 工单（WO） | 22 |
| 工序卡（Job Card） | 555，覆盖 20 张 WO |
| 生产计划（PP） | 28 |

对账：`订单量 3220 = 有效 3120 + 已改单(作废) 100`；
`未发 1036 = 死单(Closed未发) 421 + 在产/待发 622`；
`DN 实算未发 1036 = ERP delivered_qty 口径 1036`。

## 2. 关键发现

1. **EN 订单行卖的是 `PK#` 码，不是 BOM 的 `KS` 码。**
   - BOM `产品编号` = `KS0001-XMMBS-194-HEMPNATURAL`；
   - EN SO 行 `item_code` = `PK#KS0001-XMMBS-194-HEMPNATURAL`；
   - 客户码挂在成品 KS 上，订单行卖的是 PK#（皮壳）是常态。
   - **G1b 用 `--item KS...` 查不到 SO**；必须用 `--customer-code`，或先做 `KS → PK#` 映射。
2. **ERP `Closed` ≠ 已发完。** 本 SKU 有 3 张 Closed 但未发：
   `SO-24-00033-1` 100、`SO-25-00021` 1、`SO-26-00098` 320，共 **421 件死单**。
   这些不能当 open demand，也不能当已发；必须单列 `dead/closed_unshipped`。
3. **未开工工单占比高。** `WO-26-02663`（320 件）与 `WO-26-03128`（300 件）
   工序卡为 0、全部 Pending；`SO-26-00036` 未发 9 件且无生产计划。
   这些是真实缺口的候选，但需要产能/交期区间，不能按固定 3 个月到货。
4. **存在同物料同量、交货日相同的疑似重复单。**
   `SO-24-00033` 与 `SO-24-00033-1`（100/100）、`SO-26-00098` 与 `SO-26-00103`（320/320）。
   前者 `SO-24-00033` 已取消并被后继单取代；后者需要业务确认是否改单/重下，不能直接相加。
5. **Job Card 是唯一可信的生产进度。** 22 张 WO 中 20 张有工序卡；
   头部 `WO.status/produced_qty` 不可作为进度或产出（与 08 §1 一致）。

## 3. 对 G1b 契约的含义

| 契约项 | 试点结论 |
|---|---|
| 需求冲减 | 有效订单 3,120 件；已发 2,084；未发 1,036；死单 421 单列，不进入 open demand |
| P4 已出库 | DN 实算 2,084 件；与 ERP `delivered_qty` 口径一致（本 SKU） |
| P1 首道报工 | 需按 Job Card 逐 WO 汇总；本试点 555 张 JC / 20 WO |
| 生产四量 | 未开工 WO 不能算 WIP；`produced_qty` 只作展示 |
| 重复单 | 同物料同量同交货日必须进异常，不直接相加 |
| 映射 | `KS → PK#` 是 G1b 必做映射；只用 KS 精确匹配会漏单 |

## 4. 限制与下一步

- 本试点只覆盖 **1 个 SKU**，不代表 family 全量；下一步选 top 10–20 个 SKU 做结构化抽取。
- 需要把控制台输出转成 JSON（SO/DN/WO/JC/PP 分级），再与库存快照做覆盖对账。
- WayfairCG 库存仍未接入（需 YTQ 后台导出）；3PL 需求单列。
- 美中历史受新运营 ramp 影响；覆盖月数只作指示，不输出固定到货日。
