---
okf: v0.1
type: Reference
title: Phase 2 BOM 成本快照与通用组件变体锁定策略
description: BOM 成本快照必须包含 disabled 物料（历史订单可能引用停用 SKU）；合并组统一用 Phase1 carrier/product，通用组件（CURVE-PILLOW-*-PPCOTTON/-FOAM）按同订单 Cover/成品行锚定变体；method_diff 放行规则与 EN BOM 独立校验结论
date: 2026-11-04
module: tongtool_order_cost
tags: [cost, bom, phase2, disabled-item, curve-pillow, method-diff]
---

# Phase 2 BOM 成本快照与变体锁定策略

> 适用于 `tongtool_order_cost/tongtu_cost_engine/domain/bom_cost.py`（Phase 2 shadow）。
> 只读：不写 GS/EN；写回表仅对账、不采信。

## 1. BOM 快照必须 include disabled

- 成本快照用 **`out/bom_cost_product_with_disabled.csv`**（2358 行，含 `disabled=1` 的 Item）。
- **历史订单可能引用停用物料**：2026-08/09 的 42/49 行 `bom_item_missing` 对应 **33/33 个 item_fg 全部 `disabled=1`**，且 EN 仍有 BOM。若用只含启用物料的 BOM Cost List，会把这些行误判为缺行。
- 因此：**停用物料出现在成本快照中是预期行为，不是错误**；不因 disabled 自动阻断。
- 若某 item 确实无 BOM / 不在成本快照 → 仍按 `bom_item_missing` 阻断。

## 2. 变体锁定（item_fg 解析）

- **合并组**：统一用 Phase 1 的 `carrier_sku` + `product_id` 解析 item_fg；**不再逐行用组内通用组件 SKU**解析，也不从组内任一 BOM 任选。
- **透传行**：
  - 自身 SKU 在 Phase 1 产品子树内唯一 → 直接用；
  - 仍是多个 Item（`CURVE-PILLOW-*-PPCOTTON/-FOAM` 这类通用组件）→ 用**同订单（order_common）的 Cover/成品行**锚定：锚定行自身 item 唯一才用；
  - 锚定出多个 item / 无锚定 → `bom_item_ambiguous` **阻断**；禁止组内任选。
- 通用组件锚定时**不按通用行自身的 product 过滤**（通用别名可能登记在别的变体上）；以同订单 Cover/成品行的唯一 item 为准。

## 2.1 Phase1 同订单锚定（CURVE-PILLOW Cover 歧义）

- `-COVER` 别名同时命中 `KS0340`（弧形PP棉靠枕-拉链款）与 `KS0342`（弧形海绵靠枕-拉链款）时，
  Phase1 按顺序锚定，仍不唯一才阻断：
  1. **同订单组件行**（`order_id`，其次 `order_common`）中唯一命中的候选产品 → 锁定；
     例：`Curve-Pillow-50-PPCotton` → KS0340、`Curve-Pillow-50-Foam` → KS0342。
  2. 两条线都在时，Cover 平台 SKU 含 **PPCotton/Foam** → 按候选 item_group 的「PP棉/海绵」锁定；
  3. 平台 SKU 无材质词 → 用 Cover 平台 SKU 的颜色词匹配同订单组件行颜色，唯一命中才锁定。
- 锚定后 `resolution_status=resolved`，`_anchor_source` 记 `same_order/material/color`。
- **Cover 行与填充行 BOM method 不同**（拆包裹常态）：合并组方法以**非 Cover 行**为准；
  非 Cover 行仍不一致或无 → `mixed_methods` 阻断，不猜。
- 2026-11-05 实测：202608 锚定 9 行（same_order 8 + color 1），歧义 0；202609 锚定 8 行，
  剩 1 行（订单只有 Cover、平台无材质/颜色信号）保持阻断。

## 3. method / valuation 绑定（Phase 2.1 实测）

- USNJ/USTX/PL 的 valuation_rate **等于**对应 `USNJBZCP#`/`USTXBZCP#`/`PLBZCP#` BOM 的 `total_cost`；与 `shipping_method` 无关。
- 二次加工规则**对全部 method 生效**；无目的地 BZCP BOM 时 rate=0（本数据中成品 method 均如此）。
- **method 规则**（2026-11-10 定案）：
  - **定价 method 一律取 BOM 主档 `shipping_method`**（1104 BOM）；
    `load_orders` 用 EN 行级 exact item / 别名候选解析 BOM method。
  - EN 订单行 `shipping_method` **只作审计**（`en_method`），不一致时输出
    `method_diff` + `method_diff_alt_delta`（EN 口径成本差），**不阻断、不影响定价**。
  - 202608 仅 46 行、202609 仅 9 行 EN=皮壳 / BOM=半成品；其余 10,708 / 6,094 行完全一致。
  - 组件后缀行同样用 BOM method + 后缀矩阵；不再有任何「按 EN method」的定价分支。
- 2026-11-04 的旧依据（71 行 EN BOM 重算通过、两月差异 2,290.59）只覆盖正常订单；
  未覆盖「整成品 SKU 被 EN 标成皮壳」的退货仓/皮壳仓混用场景。
- 报表 `cost_sxbzcp` 与 EN SXBZCP 存在漂移（抽样 40 行），但漂移集中在 Phase2 未使用的列（半成品用 sxbzcp 以外的 `cost_sxbzbcp`、皮壳 sx=0、成品 method 与 EN 一致），故按 method 选列是必要的。

## 4. 对账与输出

- 写回表四列只做 `wb_*` / `diff_vs_writeback_*` 对账，**不参与计算**。
- Phase2 输出：`Phase2成本` sheet（四列、method、product_id、item_fg、units/pieces、source、diff_vs_writeback、method_diff_alt_delta）与 `差异归因` sheet。
- 审计脚本：`scripts/phase2_1_audit.py`（产物 `out/phase2_1/`）。

## 5. 当前结果（2026-11-04 重跑）

| 指标 | 202608 | 202609 |
|---|---:|---:|
| Phase2 可定价 / 阻断 | 10,689 / 3 | 6,061 / 1 |
| 阻断原因 | 全部 `bom_item_ambiguous` | 全部 `bom_item_ambiguous` |
| `bom_item_missing` | 0 | 0 |
| 四列合计 | 2,228,516.09 | 1,362,992.16 |

剩余阻断均为真正无法锁定变体的订单：同订单多个不同 Cover（ETSYUS-4137034553）或 Cover 别名本身歧义（TT0031186K0063918-COVER → KS0340/KS0342）。
