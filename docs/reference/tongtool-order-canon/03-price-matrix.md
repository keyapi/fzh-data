---
okf: v0.1
type: Reference
title: 计价矩阵（后缀 × 发货方式 × 目的地 × 是否 FBA）
description: 给出非 FBA 的四列后缀矩阵、三档发货方式、四个目的地的加工/头程来源，以及 FBA 绕过后缀、合并组不套后缀的规则；明确单位成本与数量口径
date: 2026-11-06
module: tongtool_order_cost
tags: [tongtool, order, price-matrix, cover, foam, ppcotton, fba, canon]
---

# 计价矩阵

> **状态：canon v0.1。** 订单身份见 [01](01-order-universe.md)；分组合并见 [02](02-grouping-and-merge.md)。
> 本页只定义「给定一行/一组，四列各取什么」，不写实现行号。

## 1. 四列与单位

每行/每组成本由四列组成：

| 列 | 含义 |
|---|---|
| **皮壳成本** | 产品皮壳（含包装口径由 BOM 决定） |
| **头程运费** | 绍兴 → 目的地/平台的干线段 |
| **二次加工成本**（目的地加工） | 目的地包装成品 BOM 的成本；FBA 为 0 |
| **绍兴二次加工成本** | 绍兴侧超出皮壳的加成（半成品/成品包装） |

恒等式：

```
1 件产品成本 = 皮壳成本 + 绍兴二次加工成本 + 二次加工成本   （不含头程）
产品成本*数量 = 1 件产品成本 × 件数
订单总成本 = 产品成本*数量 + 头程*数量 + 运费 + 海外仓成本*数量
```

**口径**：矩阵里的值都是**单位成本**；写回时再乘件数/数量。合并组用「组总成本 ÷ 件数」还原单位成本，再乘件数，避免舍入漂移。

**证据**
- [33-phase3-writeback-rehearsal.md](../../../tongtool_order_cost/docs/reference/cost-engine-spec/33-phase3-writeback-rehearsal.md)（单位成本与派生列）
- [04-cost-decision-tables.md](../../../tongtool_order_cost/docs/reference/cost-engine-spec/04-cost-decision-tables.md)（四列模型）

## 2. 判定顺序（先判这三件事）

```
1) 是否 FBA？          是 → 走 §5（绕过全部后缀与发货方式）
2) 是否合并组？        是 → 走 §6（整件按 carrier method，不套后缀）
3) 否则 → 非 FBA 逐行，按 §3 后缀 × 发货方式矩阵
```

**三条硬规则**：

- **只有非 FBA 才套后缀特例**；
- **FBA 绕过全部后缀**；
- **合并组不套后缀**（合并行代表一件整成品，按载体的发货方式取整件成本）。

**证据**
- [38-en-line-identity-and-single-item-suffix.md](../../../tongtool_order_cost/docs/reference/cost-engine-spec/38-en-line-identity-and-single-item-suffix.md)（仅非 FBA、合并组不套后缀）
- [08-special-cases.md](../../../tongtool_order_cost/docs/reference/cost-engine-spec/08-special-cases.md)（FBA 强制清零）

## 3. 非 FBA 主矩阵

### 3.1 无后缀（普通件）

| 发货方式 | 皮壳成本 | 绍兴二次加工 | 目的地二次加工 | 头程 |
|---|---|---|---|---|
| **皮壳** | `cost_fg` | **0** | 目的地 valuation | 皮壳头程 |
| **半成品** | `cost_fg` | `cost_sxbzbcp` | 目的地 valuation | 半成品头程 |
| **成品** | `cost_fg` | `cost_sxbzcp` | 目的地 valuation | 成品头程 |

> 「目的地 valuation」在 USNJ/USTX/PL 分别取对应包装成品 BOM 的 `total_cost`；美国海外仓取 USTX；FBA 取 0（见 §4、§5）。

### 3.2 `-COVER`（单独卖皮壳 / 拆单组里的皮壳行）

| 发货方式 | 皮壳成本 | 绍兴二次加工 | 目的地二次加工 | 头程 |
|---|---|---|---|---|
| 皮壳 / 半成品 / 成品 | `cost_fg` | **0** | **0** | 皮壳头程 |

- 三档发货方式结果相同；
- 加工成本清零；
- 头程一律取皮壳头程。

### 3.3 `-FOAM`（单独卖海绵 / 拆单组里的填充行）

| 发货方式 | 皮壳成本 | 绍兴二次加工 | 目的地二次加工 | 头程 |
|---|---|---|---|---|
| **半成品** | **0** | `cost_sxbzbcp` | 目的地 valuation | 半成品头程 − 皮壳头程 |
| **成品** | **0** | `cost_sxbzcp` | 目的地 valuation | 成品头程 − 皮壳头程 |
| **皮壳** | 见 §7 边界（现行 EN 无特例，按普通皮壳） | — | — | — |

- 头程是**差额**，不是全额；差额为负视为数据错误（见 §7 `PRICE-008`）。
- 皮壳成本归零，因为成本转移到填充物对应的绍兴包装成本。

### 3.4 `-PPCOTTON`（单独卖 PP 棉）

| 发货方式 | 皮壳成本 | 绍兴二次加工 | 目的地二次加工 | 头程 |
|---|---|---|---|---|
| **皮壳** | **0** | **0** | 目的地 valuation | **0** |
| 半成品 / 成品 | 无特例，按 §3.1 普通该档 | 同左 | 同左 | 同左 |

- `-PPCOTTON` 特例**只存在于「皮壳」档**；
- 皮壳、绍兴二次、头程三项归零，目的地二次加工保留；
- 成品/半成品档按普通件计价，不因后缀再清零。

### 3.5 后缀识别边界

- 后缀按**子串、大小写不敏感**识别：`-COVER`、`-FOAM`、`-PPCOTTON`。
- 数字后缀（`-COVER1`…`-COVER5`、`-FOAM1`…`-FOAM5`）**不改变计价分支**，只影响历史预估尾程的有效重量。
- 不带数字的 `-COVER` / `-FOAM` / `-PPCOTTON` 才进入本页矩阵。
- 合并组不套本矩阵（§6）。

**证据**
- [38-en-line-identity-and-single-item-suffix.md](../../../tongtool_order_cost/docs/reference/cost-engine-spec/38-en-line-identity-and-single-item-suffix.md)（后缀矩阵）
- [08-special-cases.md](../../../tongtool_order_cost/docs/reference/cost-engine-spec/08-special-cases.md)（数字后缀只改有效重量）
- `tongtool_integration/tongtool_integration/sync/order_sync.py`、`tongtool_integration/.../doctype/tongtool_cost_review/tongtool_cost_review.py`（2026-11-06 观测）
- `tongtool_order_cost/tongtool_order_cost/tongtu_cost_engine/domain/bom_cost.py`（`_unit_costs`；2026-11-06 观测）

## 4. 目的地差异（非 FBA）

| 目的地 | 目的地二次加工 | 皮壳头程 | 半成品头程 | 成品头程 |
|---|---|---|---|---|
| **美东 USNJ** | 美东包装成品 BOM `total_cost` | 美东 USNJ | 美东 USNJ | 美东 USNJ |
| **美中 USTX** | 美中包装成品 BOM `total_cost` | 美中 USTX | 美中 USTX | 美中 USTX |
| **波兰 PL** | 波兰包装成品 BOM `total_cost` | 波兰 PL | 波兰 PL | 波兰 PL |
| **美国海外仓** | **复用美中 USTX** | 美中 USTX | 美中 USTX | **USFBA** |
| **FBA** | **0** | — | — | 对应国家 FBA 成品头程 |

- 目的地加工成本取该物料 active + default BOM 的 `total_cost`；无 BOM 回退 `Item.valuation_rate`；`disabled=1` 置空。
- 海外仓不是独立成本体系：加工与皮壳/半成品头程借 USTX，成品头程借 USFBA。
- FBA 仓没有加工成本配置（`processing_cost_name` 为空），所以加工成本为 0。

**证据**
- [en-shaoxing-shipment-cost-logic-spec.md](../../../tongtool_order_cost/docs/reference/en-shaoxing-shipment-cost-logic-spec.md)（仓库配置与目的地加工）
- [04-cost-decision-tables.md](../../../tongtool_order_cost/docs/reference/cost-engine-spec/04-cost-decision-tables.md)（目的地决策表）
- `work_order_task/.../report/bom_cost_list_v2/bom_cost_list_v2.py`（2026-11-06 观测）

## 5. FBA 矩阵（绕过全部后缀）

| 皮壳成本 | 绍兴二次加工 | 目的地二次加工 | 头程 |
|---|---|---|---|
| `cost_fg` | `sx_cost_all − cost_fg` | **0** | 对应国家 FBA 成品头程 |

- **不看发货方式**：无论皮壳/半成品/成品，FBA 一律按成品口径；
- **不看后缀**：`-COVER` / `-FOAM` / `-PPCOTTON` 在 FBA 下全部失效；
- 直采成品特例：`cost_fg == sx_cost_all` 且 `cost_sxbzcp == 0` 时，允许绍兴二次 = 0（`direct_purchase_zero`），不是缺值；
- 若 `绍兴二次 < 0` 或恒等式不成立 → pending，不补 0。

**证据**
- [35-phase4-fba-shadow.md](../../../tongtool_order_cost/docs/reference/cost-engine-spec/35-phase4-fba-shadow.md)（FBA 四列与直采例外）
- [08-special-cases.md](../../../tongtool_order_cost/docs/reference/cost-engine-spec/08-special-cases.md)（FBA 强制清零）
- `tongtool_order_cost/tongtool_order_cost/tongtu_cost_engine/domain/fba_shadow.py`（2026-11-06 观测）

## 6. 合并组：不套后缀

合并组只产出载体行，代表一件整成品：

- 按载体的 `shipping_method` 走 §3.1 的普通矩阵；
- **不套** `-COVER` / `-FOAM` / `-PPCOTTON`；
- 组件行成本显式 0（已含在整件 BOM）；
- 件数按 [02](02-grouping-and-merge.md) §6；
- 组单位成本 = 组总成本 ÷ 件数。

**为什么**：后缀描述的是「这一行卖的是组件」；合并后这一行卖的是整件成品，再套后缀会把整件成本错误清零。

**证据**
- [38-en-line-identity-and-single-item-suffix.md](../../../tongtool_order_cost/docs/reference/cost-engine-spec/38-en-line-identity-and-single-item-suffix.md)
- [33-phase3-writeback-rehearsal.md](../../../tongtool_order_cost/docs/reference/cost-engine-spec/33-phase3-writeback-rehearsal.md)（组件吸收）
- `tongtool_order_cost/tongtool_order_cost/tongtu_cost_engine/domain/bom_cost.py`（合并组后缀门；2026-11-06 观测）

## 7. 边界与待裁决

| 边界 | 现行处理 | 状态 |
|---|---|---|
| **`-FOAM` + 发货方式=皮壳** | EN 无此特例，按普通皮壳；本地引擎已于 2026-11-06 对齐（不再清零皮壳） | canon（`PRICE-007`） |
| **`-PPCOTTON` + 成品/半成品** | 无特例，按普通该档 | canon（EN 仅皮壳档） |
| **四列出现负值** | 视为数据错误：本地引擎阻断并暴露，不 clamp；实测 202608/202609 为 0 例 | canon（`PRICE-008`） |
| **数字后缀 >5** | 落通用有效重量分支，不改变计价 | unverified（是否有此类订单未统计） |
| **合并组内多成品/多皮壳** | 不合并，拆成多件 | canon（[02](02-grouping-and-merge.md) §5） |

**证据**
- [38-en-line-identity-and-single-item-suffix.md](../../../tongtool_order_cost/docs/reference/cost-engine-spec/38-en-line-identity-and-single-item-suffix.md)（矩阵只列半成品/成品 FOAM）
- [09-known-issues-register.md](../../../tongtool_order_cost/docs/reference/cost-engine-spec/09-known-issues-register.md)（口径漂移）
- `tongtool_integration/tongtool_integration/sync/order_sync.py`、`tongtool_order_cost/tongtool_order_cost/tongtu_cost_engine/domain/bom_cost.py`（2026-11-06 观测）
