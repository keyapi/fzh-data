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
> 结构化输出：`out/g1b_en_fixed3.json`（SO/DN/WO/JC/SE/PP，已去 PII）。

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

对账（互斥分解）：

```text
订单量 3,220 = 有效 3,120 + 作废/改单 100
有效未发 1,036 = 死单 421 + 在产 622 + 无计划 9 + 超发(-16)
```

- 死单 421：`SO-24-00033-1` 100 + `SO-25-00021` 1 + `SO-26-00098` 320。
- 在产 622：`SO-26-00042` 2 + `SO-26-00103` 320 + `SO-26-00109` 300。
- 无计划 9：`SO-26-00036` 9（无 WO/PP，旧报告误归“在产”）。
- 超发 -16：`SO-26-00057` -13 + `SO-26-00074` -3（delivered > ordered）。
- 旧报告 `421+622=1,043` 与 1,036 的差 **7**，就是 `+9`（无计划）与 `-16`（超发）的净额；
  不是四舍五入，也不是漏单。

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
5. **Job Card 是主要进度证据，但不能免验证。** 22 张 WO 中 20 张有工序卡；
   需排除虚拟卡/撤销卡/重复卡，并按首道工序取完成量；未开工（0 卡）标 `unknown`，不能当 0。
   头部 `WO.status/produced_qty` 不可作为进度或产出（与 08 §1 一致）。
6. **DN 行自身键已保留。** `Delivery Note Item.name` = `dn_line_id`；
   `so_line_id`（来自 `so_detail`）只是 SO 行外键，不能当 DN 行主键。
7. **已提交 Manufacture SE 已抽出。** 本 SKU 63 张 SE；四量按 WO 分别记
   `first_op_qty / last_op_qty / se_finished_qty / produced_pending_stock_in`，
   不再用 JC 求和替代产出。无 JC 的 WO 四量留 `null`，不补 0。

## 3. 对 G1b 契约的含义

| 契约项 | 试点结论 |
|---|---|
| 需求冲减 | 有效订单 3,120 件；已发 2,084；未发 1,036；死单 421 单列，不进入 open demand |
| 未发互斥分解 | 死单 421 + 在产 622 + 无计划 9 + 超发 -16 = 1,036；差 7 已解释 |
| P4 已出库 | DN 实算 2,084 件；与 ERP `delivered_qty` 口径一致（本 SKU）；DN 行键用 `dn_line_id` |
| P1 首道报工 | 按 WO 的首道工序 JC 汇总；本试点 555 张 JC / 20 WO；无卡 = unknown |
| P3 已提交入库 | 63 张 Manufacture SE；按 WO 汇总成品行 |
| 生产四量 | 首道/末道/SE/待入库分开；未开工 WO 不能算 WIP；`produced_qty` 只作展示 |
| 重复单 | 同物料同量同交货日必须进异常，不直接相加 |
| 映射 | `KS → PK#` 是 G1b 必做映射；只用 KS 精确匹配会漏单 |

## 4. 限制与下一步

- 本试点只覆盖 **1 个 SKU**，不代表 family 全量；下一步选 top 10–20 个 SKU 做结构化抽取。
- 需要把控制台输出转成 JSON（SO/DN/WO/JC/PP 分级），再与库存快照做覆盖对账。
- WayfairCG 库存仍未接入（需 YTQ 后台导出）；3PL 需求单列。
- 美中历史受新运营 ramp 影响；覆盖月数只作指示，不输出固定到货日。
