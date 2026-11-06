---
okf: v0.1
type: Reference
title: 分组合并与产品归属（拆单 / 拆包裹 / 件数 / 共享组件）
description: 正面回答未拆单时当前订单即原始订单、拆单如何识别、同 order_common 何时合并何时不合并、件数取谁、单独卖皮壳/海绵/PP棉为何不是产品歧义、共享组件谁定产品；给出不重不漏断言
date: 2026-11-06
module: tongtool_order_cost
tags: [tongtool, order, merge, split, grouping, identity, canon]
---

# 分组合并与产品归属

> **状态：canon v0.1。** 订单全集见 [01](01-order-universe.md)；合并后怎么计价见 [03](03-price-matrix.md)。
> 核心原则：**合并不是默认动作，而是拆单证据成立时的例外。**

## 1. 一句话规则

- **没拆单**：当前订单就是原始订单，逐行计价，不合并。
- **拆单/拆包裹**：同一原始订单下，一件成品被拆成皮壳行 + 填充行（或多子单）→ **先合并成一件成品，再对整件 BOM 计价**；组件行不再各自计价。
- **单独卖皮壳/海绵/PP棉**：只有一行、没有配套行 → **不合并**，按单品后缀计价；这是正常售卖形态，**不是产品歧义**。

## 2. 未拆单：当前订单就是原始订单

**判定**：同时满足以下条件，当前订单直接按原始订单处理：

1. 订单号没有拆单尾号（`_1/_2` 或 `-1/-2`），**或**有尾号但同组没有其它有效行、也没有作废原单；
2. 同一 `order_common + 平台SKU + 解析产品` 下没有第二条有效行；
3. 没有同 `order_common` 的 `invalid=1` 作废原单。

此时：

- 每一行都是自己的原始行，按 [03](03-price-matrix.md) 逐行计价；
- 不创建合并组、不找原单、不做件数汇总；
- `order_common` 仍可计算并写入血缘，但**不触发合并**。

**反例（不能这样判）**：看到订单号带 `-1` 就认定拆单；看到同 SKU 多行就合并；看到产品名含「包裹」就合并。

**证据**
- [30-design-merge-split-no-double-count.md](../../../tongtool_order_cost/docs/reference/cost-engine-spec/30-design-merge-split-no-double-count.md)（落点与算法）
- `tongtool_order_cost/tongtool_order_cost/ustx_cost_compare.py`（`order_common_part`；2026-11-06 观测）
- `tongtool_order_cost/tongtool_order_cost/tongtu_cost_engine/domain/split_merge.py`（`load_orders`、`find_groups`；2026-11-06 观测）

## 3. 拆单 / 拆包裹怎么认

**结构判据（必须同时满足）**：

1. 同一 `order_common`（订单号只剥末尾 1–2 位数字后缀）；
2. 同一 `平台SKU`（归一化后）；
3. 同一解析产品（`product_id`）；
4. 组内 ≥2 行，且通途 SKU **多于一个**。

**辅助信号（只作佐证，不作唯一判据）**：

- 组内同时出现 `-Cover` 与 `-Foam` / `-PPCotton`；
- 订单号带 `_1/_2`、`-1/-2` 尾号；
- 同 `order_common` 存在 EN 作废原单（`invalid=1`）；
- EN 同步字段 `is_deliver_good=0`。注意：通途 API 的 `isDeliverGoods="1"` 表示**未发货/被拆出**，EN 同步时取反写成 0；该字段语义反直觉，只能辅助判断。

**明确不用的判据**：

- 产品名/品名里是否含「包裹」；
- 平台 SKU 里是否含逗号（那是多商品，不是拆包）；
- 金额是否相等；
- 行号先后。

**证据**
- [30-design-merge-split-no-double-count.md](../../../tongtool_order_cost/docs/reference/cost-engine-spec/30-design-merge-split-no-double-count.md)（结构分组 ∩ EN 同产品）
- `tongtool_order_cost/tongtool_order_cost/tongtu_cost_engine/domain/split_merge.py`（`find_groups`、`group_split_rows`；2026-11-06 观测）
- `tongtool_integration/tongtool_integration/sync/order_sync.py`（`is_deliver_good` 取反；2026-11-06 观测）

## 4. 同 `order_common` 何时合并

**只有以下全部成立才合并**：

| # | 条件 | 不满足时 |
|---|---|---|
| 1 | 同 `order_common + 平台SKU + product_id` | 不合并 |
| 2 | ≥2 行、≥2 个不同通途 SKU | 不合并（同 SKU 多行只是数量行） |
| 3 | 能选出**唯一载体**（见 §5） | 阻断，不取 first/max |
| 4 | 能算出**唯一件数**且 >0 | 阻断 |
| 5 | 载体行身份字段一致（渠道、数量口径、发货方式等） | 阻断 `carrier_identity_conflict` |
| 6 | 作废原单若存在，method 与件数校验通过 | 阻断 `aux_method_mismatch` / `aux_qty_mismatch` |
| 7 | 不属于 FBA | FBA 走独立路径 |

**合并结果**：一个合并组 = 一件成品；载体行计价；其余组件行成本显式 0（`component_absorbed`）；组内保留全部源 SKU 作为血缘。

## 5. 何时不合并（以及怎么处理）

| 情形 | 处理 | 理由 |
|---|---|---|
| 只有一行 | 不合并，按原始订单 | 没有拆单证据 |
| 同 SKU 多行 | 不合并，保留多行 | 只是数量/批次行，不是一件成品被拆 |
| 组内多个**成品** SKU | **拆成多件**逐件计价（`split_products`） | 多颜色/多件不同变体，不是一件成品 |
| 组内多个**皮壳** SKU | **拆成多件**逐件计价 | 多颜色皮壳，各自是独立成品 |
| 载体不唯一 / 无载体 | 阻断 | 不猜 |
| method 缺失或非 Cover 行 method 不一致 | 阻断 `mixed_methods` | 不猜发货方式 |
| 件数为 0 / 无法唯一确定 | 阻断 | 不取 max/first |
| 载体身份字段冲突 | 阻断 | 同一载体不能有两种身份 |
| 作废原单 method/件数与子单不一致 | 阻断 | 原单是锚，不是可忽略项 |
| FBA 行 | 不进入自发货合并组 | FBA 独立计价 |
| 平台 SKU 含逗号（多商品） | 不做产品覆盖；按行/多件处理 | 一件订单含多个商品，不是拆包 |

**阻断不是失败**：阻断行保留在输出中、成本留空、写 `cost_status` 与原因，等业务确认；**不允许静默取 first、max、平均数**。

**证据**
- [38-en-line-identity-and-single-item-suffix.md](../../../tongtool_order_cost/docs/reference/cost-engine-spec/38-en-line-identity-and-single-item-suffix.md)（组内例外与阻断）
- [32-phase2-bom-cost-policy.md](../../../tongtool_order_cost/docs/reference/cost-engine-spec/32-phase2-bom-cost-policy.md)（`mixed_methods`、`bom_item_ambiguous`）
- `tongtool_order_cost/tongtool_order_cost/tongtu_cost_engine/domain/split_merge.py`（`_pick_carrier`、`find_groups`；2026-11-06 观测）

## 6. 件数取谁

**件数 = 这件成品有几件，不是行数，也不是最大数量。**

| 载体形态 | 件数 |
|---|---|
| **皮壳载体** | 该皮壳 SKU（同 base）**全部行的数量之和** |
| **成品载体** | 只数**无拆单尾号的基行**数量之和；若只有 `-1/-2` 行、没有基行 → `pieces_ambiguous` 阻断 |
| **作废原单兜底** | 原单组件行重复、qty 合计不可用时，用原单件数锚定，标 `pieces_source=aux`；原单与子单件数不一致 → 阻断 |

**禁止**：取首行、取最大值、取行数、把组件行 qty 直接相加当件数。

**证据**
- [30-design-merge-split-no-double-count.md](../../../tongtool_order_cost/docs/reference/cost-engine-spec/30-design-merge-split-no-double-count.md)（件数 = Σ皮壳行）
- `tongtool_order_cost/tongtool_order_cost/tongtu_cost_engine/domain/split_merge.py`（`_count_pieces`；2026-11-06 观测）

## 7. 产品归属：先看行，再看共享组件

### 7.1 行级身份优先

1. EN 订单行的 `erp_item_code` 是该行**实际卖的物料**，是行级权威。
2. 唯一非空且能映射到 Item/产品 → 采用。
3. 多值冲突 → 不猜，阻断。
4. 空值 / 字面 `NULL` / `NONE` / `-` → 回退别名解析。
5. EN 物料不在 Item 表 → **不静默回退**；若别名也解不出唯一产品 → 阻断，计 `en_item_unmapped`。
6. BOM 取数优先用行级物料，否则会出现「产品换了但别名里没有该 Item」。

### 7.2 共享皮壳 → 填充行定产品

同一皮壳可配 PP 棉或海绵，两种填充物属于**同一皮壳、不同产品**。共享皮壳的别名天然有多个候选，不能当歧义留空。

**规则**：同一拆单组内已有 `-Foam` / `-PPCotton` 行时，**Cover 行不单独决定整组产品**；它常被默认到另一条产品线，产品由填充行解析结果锚定。Cover 行别名本身有歧义时，直接跳过它的 EN 物料号（不采信）。

### 7.3 共享填充物 → 皮壳定产品

反过来，填充物也可能只登记在另一个产品上。若：

- 组内只有一个皮壳 SKU；
- 皮壳别名能唯一解析到一个产品；
- 平台 SKU 不含逗号（不是多商品）；

则**皮壳产品覆盖填充行的产品**（`group_cover_override`）。

### 7.4 两条规则合起来

**差异化的那个组件决定产品**：

- 皮壳共用、填充物不同 → **填充行定产品**；
- 填充物共用、皮壳不同 → **皮壳定产品**；
- 两者都多候选 / 多条规则指向不同产品 → **阻断**，不猜。

**保护条件**：平台 SKU 含逗号（多商品）或多皮壳 SKU（多颜色多件）时，不套用反向覆盖，避免误并。

**证据**
- [38-en-line-identity-and-single-item-suffix.md](../../../tongtool_order_cost/docs/reference/cost-engine-spec/38-en-line-identity-and-single-item-suffix.md)（行级身份、Cover 让位、反向覆盖）
- [32-phase2-bom-cost-policy.md](../../../tongtool_order_cost/docs/reference/cost-engine-spec/32-phase2-bom-cost-policy.md)（同订单锚定）
- `tongtool_order_cost/tongtool_order_cost/tongtu_cost_engine/domain/split_merge.py`（`_cover_product_precedence`、`_anchor_same_order`；2026-11-06 观测）

## 8. 单独卖 `-Cover` / `-Foam` / `-PPCotton` **不是产品歧义**

**判据**：同一原始订单内**没有配套行**（只有 Cover，或只有 Foam，或只有 PP 棉），就是单独卖单品。

处理：

1. **不合并**；
2. 先用 EN `erp_item_code` 定行级身份；
3. 没有 EN 物料时回退别名；
4. 共享皮壳导致别名多候选时，用同订单的 Cover/填充行锚定；仍不唯一才阻断；
5. 按 [03](03-price-matrix.md) 的后缀矩阵**逐行计价**。

**必须记住**：

- 一个皮壳可配 PP 棉或海绵，这是**同一皮壳、不同填充物**，不是两个皮壳；
- 单独卖皮壳时，直接取皮壳成本 + 皮壳头程；
- 单独卖海绵/PP 棉时，按对应后缀矩阵；
- **不能因为别名有多个候选就把单独卖皮壳留空**。

**证据**
- [38-en-line-identity-and-single-item-suffix.md](../../../tongtool_order_cost/docs/reference/cost-engine-spec/38-en-line-identity-and-single-item-suffix.md)（两类订单必须先分开）
- `tongtool_order_cost/AGENT_HANDOFF.md`（「单独卖皮壳/海绵/PP棉 ≠ 产品歧义」）
- `tongtool_order_cost/tongtool_order_cost/tongtu_cost_engine/domain/bom_cost.py`（`_unit_costs` 后缀矩阵；2026-11-06 观测）

## 9. 合并后的计价边界

- 合并组只产出**一行**（载体行），代表一件成品；
- **不套后缀特例**：合并行按载体的 `shipping_method` 取整件成本；`-Cover`/`-Foam` 只影响组件行身份，不影响合并行计价；
- 组件行成本显式 0，不进入四列；
- 件数 × 单位成本 = 组总成本；
- 合并组内若出现多个成品/多个皮壳 → 不合并，按 §5 拆件。

**证据**
- [38-en-line-identity-and-single-item-suffix.md](../../../tongtool_order_cost/docs/reference/cost-engine-spec/38-en-line-identity-and-single-item-suffix.md)（合并组不套后缀）
- [33-phase3-writeback-rehearsal.md](../../../tongtool_order_cost/docs/reference/cost-engine-spec/33-phase3-writeback-rehearsal.md)（组件吸收、组行单位成本）

## 10. 不重不漏断言

1. **数量守恒**：合并前各行数量之和与合并后件数可对账；差数必须有原因。
2. **件数守恒**：`Σ合并后件数 = Σ皮壳行数量`（无皮壳组单列，不静默补）。
3. **键不退化**：合并后的产品键必须 ∈ 组内原键集合；**禁止字符串拼接**。
4. **成本不重**：同组只有载体行进 BOM；组件行成本 0。
5. **歧义即阻断**：载体/产品/件数/身份任一不唯一 → 阻断，不取 first/max/平均。
6. **作废不计**：`invalid=1` 不进入件数与成本合计。
7. **FBA 不混**：FBA 行不进入自发货合并组，业务键重复要单独标记。
8. **金额守恒**：`售价`、`售价(人民币)`、`运费` 合并前后必须相等。
   - 合并行的销售额 = 组内全部源行之和；
   - **合并行的尾程运费 = 组内各源行运费之和**（同一键多行按出现顺序）；
   - 模板完全没有该行时才允许用「包裹总运费」兜底，否则会把组件运费重复计；
   - **作废原单/模板独有行不得参与有效子单映射**，否则原单运费会被带进有效子单；
   - `运费` 是**行总额**，不乘数量；订单总成本 = 单位成本×数量 + 运费。

**证据**
- [30-design-merge-split-no-double-count.md](../../../tongtool_order_cost/docs/reference/cost-engine-spec/30-design-merge-split-no-double-count.md)（5 条断言）
- `tongtool_order_cost/tongtool_order_cost/tongtu_cost_engine/domain/split_merge.py`（`_check_qty_conservation` 等；2026-11-06 观测）
