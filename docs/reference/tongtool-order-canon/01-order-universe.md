---
okf: v0.1
type: Reference
title: 订单全集与身份（原始订单 / 作废原单 / 拆分子单 / FBA / 退货）
description: 定义哪些订单行进入成本计算、原始订单与拆分子单如何识别、作废原单只作锚不计价、FBA 与自发货分账、退货/补发的现状；给出不丢行/不重行的守恒约束
date: 2026-11-06
module: tongtool_order_cost
tags: [tongtool, order, universe, invalid, split, fba, canon]
---

# 订单全集与身份

> **状态：canon v0.1。** 本页只回答「哪些行算数、谁是原始订单、作废单怎么用」。
> 计价见 [03-price-matrix.md](03-price-matrix.md)；分组合并见 [02-grouping-and-merge.md](02-grouping-and-merge.md)。
> 证据一律放在每节末尾；正文不写源码行号（行号会漂移）。

## 1. 三个来源，一个权威

| 来源 | 内容 | 权威性 | 用途 |
|---|---|---|---|
| **EN `Tongtool Order`** | 订单头 + 明细行：`order_id / platform_sku / tongtool_sku / erp_item_code / quantity / shipping_method / invalid` | **身份与金额的权威源** | 决定行集合、作废、行级物料、发货方式 |
| **Google Sheet `通途订单YYYYMM`** | `{月}订单`（raw）、`写回…`、`写回…FBA订单` | 业务骨架与写回模板 | 提供业务列、对账；**不反过来定义订单身份** |
| **EN FBA 明细 / GS FBA 销量表** | FBA 行、站点、MSKU、数量 | FBA 子集的权威源 | FBA 单独计价，不与自发货混算 |

**规则**：三者冲突时，订单身份、作废标记、`erp_item_code`、`shipping_method` 以 EN `Tongtool Order` 为准；GS 只提供业务字段与写回列。FBA 的数量与站点以 EN FBA 明细为准，GS FBA 销量表作骨架与覆盖校验。

**历史边界（#290）**：GS 月表自 2023-01 起是历史**销售**真源，EN 自 2025-07 起基本完整；通途 API 可见性跟「最近更新时间」走，不能重建 2025-07 以前。**销售历史 ≠ 成本身份**：历史销售可借 GS，但订单身份/作废/`erp_item_code`/`shipping_method` 仍以 EN 为准。

**证据**
- [37-phase3.7-gs-ready.md](../../../tongtool_order_cost/docs/reference/cost-engine-spec/37-phase3.7-gs-ready.md)（原始表 / 写回表 / FBA 表的分工）
- [tongtu-order-universe-invalid-split-fba.md](../../../docs/solutions/workflow-issues/tongtu-order-universe-invalid-split-fba.md)
- `tongtool_order_cost/tongtool_order_cost/tongtu_cost_engine/domain/split_merge.py`（`load_orders`、`LoadResult`；2026-11-06 观测）

## 2. 原始订单：未拆单时，当前订单就是原始订单

**判定顺序**：

1. **没有拆单证据 → 当前订单就是原始订单。** 一行（或同 SKU 的多行数量）直接按自身计价，不找原单、不做合并、不把 `invalid` 行拉进来。
2. **拆单证据成立 → 才进入「原单 + 子单」模型。** 拆单证据是以下任一条：
   - 同一 `order_common` 下存在 ≥2 条有效行，且属于同一平台 SKU、同一解析产品，且通途 SKU 多于一个；
   - 存在同 `order_common` 的 EN 作废原单（`invalid=1`）；
   - 订单号带拆单尾号（`_1/_2` 或 `-1/-2`），且同组有其它有效行。

**订单号公共部分的铁律**：只剥末尾 **1–2 位数字** 后缀（`_N` / `-N`）。像 `OS-474530280` 这种「前缀-长数字」是订单本体，**不剥**；否则键会退化成平台名，把整平台订单塌并。

**只有一条带尾号的行、且没有同组行、没有作废原单**：按原始订单处理（不合并、不臆造原单），但保留尾号作为血缘标记。

**证据**
- [30-design-merge-split-no-double-count.md](../../../tongtool_order_cost/docs/reference/cost-engine-spec/30-design-merge-split-no-double-count.md)（分组与落点）
- `tongtool_order_cost/tongtool_order_cost/ustx_cost_compare.py`（`order_common_part`；2026-11-06 观测）
- `tongtool_order_cost/tongtool_order_cost/tongtu_cost_engine/domain/split_merge.py`（`load_orders`、`find_groups`；2026-11-06 观测）

## 3. 作废原单（`invalid=1`）：只作锚，不计价

EN 的作废原单仍然保留在订单表里，但**不进入成本行集合**。它的作用是给拆单组提供锚点：

| 用途 | 规则 |
|---|---|
| 数量锚 | 原单的件数用于校验子单合并件数；不一致 → 阻断，不取平均、不取最大 |
| 发货方式锚 | 原单的 `shipping_method` 与子单不一致 → 阻断 |
| 载体锚 | 子单结构无法唯一确定载体（缺皮壳/多载体）时，可用原单的载体兜底，并标记 `pieces_source=aux` |
| 金额/售价 | **不参与**成本、收入、利润计算；只做校验 |

**原单组件行重复**（同一组件多行，qty 合计不可用）：按件数锚定，不因 qty 合计不等而阻断；仍要保留审计标记。

**原单也缺失时**：只用有效子单；不凭空构造原单。件数/载体无法唯一确定 → 阻断并留空，不猜。

**输出**：作废原单在写回表中保留行与销售字段，成本与系数轨清空，状态标 `invalid_original`，旧成本值进备份。

**证据**
- [37-phase3.7-gs-ready.md](../../../tongtool_order_cost/docs/reference/cost-engine-spec/37-phase3.7-gs-ready.md)（作废原单处理）
- `tongtool_order_cost/tongtool_order_cost/tongtu_cost_engine/domain/split_merge.py`（`aux_rows`、`_aux_validate`、`lookup_aux`；2026-11-06 观测）

## 4. 拆分子单：全部有效行都进入，不按 SKU 去重

- `_1/_2`、`-1/-2` 等子单是**有效订单行**，全部进入行集合；不得只取第一条、不得按 SKU 合并掉。
- 子单与子单之间通过 `order_common` 关联；同一子单内也可以有多行（组件行）。
- **去重只允许发生在「规则表匹配」层**（6 列去重键），不允许在订单行集合层按 SKU 去重。
- 同一订单号下同一 SKU 多行：保留为多行；合并只发生在 [02](02-grouping-and-merge.md) 定义的拆单组，且合并后要保留源行血缘。

**证据**
- `tongtool_order_cost/tongtool_order_cost/tongtu_cost_engine/domain/split_merge.py`（`rows` 与 `aux_rows` 分离；2026-11-06 观测）
- [30-design-merge-split-no-double-count.md](../../../tongtool_order_cost/docs/reference/cost-engine-spec/30-design-merge-split-no-double-count.md)（不重不漏断言）

## 5. FBA：独立子集，与自发货分账

- **FBA 身份的唯一判据**：`Tongtu Shipping Warehouse.warehouse_classification` 含 `FBA`（ADR-0001 C3）。客户名/客户码关键字、`order_type=FBA`+渠道/账号**不再决定身份**，只作兼容/审计告警；`needs_last_leg` 是尾程标志，不是 FBA 身份。
- 仓库分类不在配置表 → **阻断**，不得默认成 FBA 或非 FBA。
- FBA 行单独走 FBA 计价路径（成品口径），**不进入自发货的合并组**，也不与自发货行做 union。
- 同一 `月份 | MSKU | SKU` 同时出现在 FBA 与自发货 → 标重复，**不直接相加**，先裁决归属。
- FBA 的数量以 EN FBA 明细为准；GS FBA 销量表作骨架；通途 FBA 导出作覆盖校验。
- FBA 跨月：同月无 EN FBA 行时，可在 ±1 个月窗口借用 EN 行，按 GS 数量分摊，标 `cross_month_bridge`；不得累加两月 EN 成本。
- FBA 计价**绕过全部后缀特例**，详见 [03](03-price-matrix.md) §5。

**证据**
- [35-phase4-fba-shadow.md](../../../tongtool_order_cost/docs/reference/cost-engine-spec/35-phase4-fba-shadow.md)（FBA 桥接、跨月、三方对账）
- `tongtool_order_cost/tongtool_order_cost/tongtu_cost_engine/domain/fba_shadow.py`（`build_fba_shadow`；2026-11-06 观测）

## 6. 退货、补发、取消：范围界定

| 形态 | 口径 | 状态 |
|---|---|---|
| **退货** | **通途订单不包含退货交易**。正常发货都算销售额；退货只在**钉钉账期**体现。订单表里的「退货产品仓」只是一个发货仓名，行仍是正常正数出库，按所属分支计价。 | canon（业务口径，2026-11-06 用户确认） |
| **补发** | 订单号 `-M<数字>` 且渠道为 OSTK/WAYFAIR 时，强制 `needs_last_leg=1`；这是尾程标记，不是退货 | 已实现于 Cost Review 链路；订单同步链路未证实 |
| **取消 / 负数量** | 未发现独立成本口径；依赖 `invalid=1` 或订单同步删除。实测 202608/202609 负数数量 = 0 | canon（数据事实） |
| **作废** | `invalid=1`，按 §3 只作锚 | canon |

**不要把退货等同于作废**：作废是「这笔订单不算」；退货是「结算侧的事」，不进入通途订单成本。**不要在通途订单里新增退货成本逻辑**——退货冲减由钉钉账期处理。

**数据证据（2026-11-06）**
- 202608/202609：`发货数量 < 0` 的行数均为 **0**；四列成本负值行数均为 **0**。
- `退货产品仓` 行（202608 62 行）均为正常正数出库（qty=1、有售价）。

**参考**
- [en-branching-and-warehouse-config.md](../../../tongtool_order_cost/docs/reference/cost-engine-spec/en-branching-and-warehouse-config.md)（退货仓命名）
- `work_order_task/.../report/delivery_note_filling_cost/delivery_note_filling_cost.py`、`tongtool_integration/.../doctype/tongtool_cost_review/tongtool_cost_review.py`（2026-11-06 观测；仅见补发尾程标记，未见退货成本分支）

## 7. 守恒约束（写回前必须成立）

1. **行守恒**：每条有效订单行恰好被一行输出消费；合并组有 `group_id`，透传行有源行号。
2. **作废不计**：`invalid=1` 行不进入成本合计、收入合计、利润合计。
3. **FBA/自发货零重叠**：订单号交集与 `站点|SKU` 交集都应为空；非空即阻断。
4. **不丢行**：未登记 SKU、产品歧义、缺 BOM 的行保留在输出中，带 `cost_status` 与原因，不静默删除。
5. **不重行**：合并组内只有载体行计价，组件行显式 0；TJ# 套件与其子件不得双计。
6. **数量守恒**：合并前各行数量之和与合并后件数按 [02](02-grouping-and-merge.md) §5 的口径对账；差数必须可解释。

**证据**
- [36-phase3.6-fill-tables.md](../../../tongtool_order_cost/docs/reference/cost-engine-spec/36-phase3.6-fill-tables.md)（填充率、空白清单）
- [37-phase3.7-gs-ready.md](../../../tongtool_order_cost/docs/reference/cost-engine-spec/37-phase3.7-gs-ready.md)（95↔78 对账、重叠检查）
- `tongtool_order_cost/tongtool_order_cost/tongtu_cost_engine/domain/writeback_rehearsal.py`（血缘与断言；2026-11-06 观测）
