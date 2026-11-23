---
okf: v0.1
type: Reference
title: MOQ 与补货频率政策（2026-10-28）
description: 21 个非零 MOQ 物料清单（仓/渠道/决策键）、自有工厂无 MOQ、周补 7 天、小额订单建议阈值与库存影响
tags: [moq, replenishment, weekly-review, uom, policy]
date: 2026-10-28
status: implemented
---

# MOQ 与补货频率政策（2026-10-28）

依据 `2026-10-28-frepple-conversation-digest.md` §6（`item_attr` 15,230 个物料里 MOQ 非零
只有 21 个；绍兴自有工厂无 MOQ；月补改周补已接受）做的**政策层**产出：
只读、不改主表、不下单、不虚构渠道 MOQ。

- 脚本：[`../scripts/moq_replenish_policy.py`](../scripts/moq_replenish_policy.py)
- 测试：[`../tests/test_moq_replenish_policy.py`](../tests/test_moq_replenish_policy.py)（14 条）
- 产物（本地，不进 git）：
  `D:/Work/fzh-order-store/en-demand-v1/supply-netting/moq-replenish-policy-2026-10-28/`
  —— `report.md`、`moq_items_21.csv`、`replenish_policy.csv`、`small_order_analysis.csv`、
  `impact_summary.json`、`en_items_snapshot.json`

## 1. 21 个非零 MOQ 物料（结论）

| 维度 | 结论 | 证据 |
|---|---|---|
| 数量 | 21 / 15,230（0.14%） | `items_attr.tsv` 第 5 列；EN `Item` 过滤 `min_order_qty > 0` 同为 21 条 |
| 类别 | 全部**外购辅料**：缝纫线、流苏、PP棉、日字扣、自封袋、魔术贴、棉绳、防水牛津布、工具配件 | EN `is_purchase_item=1` + `include_item_in_manufacturing=1`；无成品/半成品 |
| UOM | 卷 / 米 / 个 / 千克（**不是「件」**） | EN `Item.stock_uom` |
| MOQ 值 | 1 / 11.5 / 25 / 48 / 50 / 60 / 100 / 300 / 350 / 1000（各按自身 UOM） | EN `Item.min_order_qty` |
| 所属仓 | 辅材仓 / 包材仓 / 面料仓 / 工具配件仓（`Item Default`，company FZH）；实际有库存的还有 `北京外协仓` | EN `Item Default` + `Bin` |
| 渠道 | 供应渠道 = 外购辅料 → 绍兴工厂生产；**没有销售渠道**（非成品）；**没有渠道级 MOQ** | EN 无渠道字段 |
| 本批决策键 | **0 / 21** 出现在 `decision-pack-2026-10-29-r2` 的 4,014 个键里 | 按 `canonical_sku` 精确匹配 |
| 缓冲 | 21 项 `safety_stock` 全为 0，提前期 0–7 天 | EN `Item.safety_stock` / `lead_time_days` |

列映射核对：`items_attr.tsv` 无表头 10 列，已用 EN REST 对 `FRX1210-WHITE-402#-20000YARDS/ROLL`
逐字段验证（`min_order_qty=48` / `safety_stock=0` / `lead_time_days=7` 与第 5/7/8 列一致）。

## 2. 政策表

| 层次 | 取值 | 依据 | 约束强度 |
|---|---|---|---|
| 自有工厂（绍兴）MOQ | **无 MOQ 限制** | digest §6 业务口径 + 21 项 MOQ 全是外购辅料 | 业务已确认 |
| 补货频率 | **周补：每 7 天复核一次** | digest §6（月补改周补，用户已接受） | 业务已确认 |
| 小额补货阈值 | 单次补货量 < **1 周 P50 需求** → 建议合并到下一次复核/观察；> 4 周 → 查重复下单 | 本批有建议量的键 × 各自周需求（按 UOM 分列） | **建议，非硬约束** |
| 外购辅料 MOQ（21 项） | 采购量 = `ceil(需求/MOQ)×MOQ`，MOQ 取 EN 值 | EN `Item.min_order_qty` | EN 数据；本批不触发 |
| 渠道级 MOQ | **不存在**（不做渠道维度） | EN 只有 item 级 MOQ | — |

为什么阈值用「周需求倍数」而不是一个全局 `X 件`：个/套/米/千克不能相加（`UOM-CANONICAL.md`），
一个跨 UOM 的全局件数会是假精确。需要单一数字时按 UOM 看报表里的分布，不要混算。

## 3. 对补货建议与库存的影响

本批（`decision-pack-2026-10-29-r2`，4,014 键）：

- `qty_current` 有值 543 键，**大于 0 的 91 键**；全部是「个」（套 0 键有正建议量）。
- **MOQ 影响 0**：21 个 MOQ 物料均不在决策键 → 现有建议量不做任何 MOQ 取整。
- 按 1 周 P50 需求分档（个）：
  - 观察（<1 周）：2 键 / 5 件
  - 正常（1–4 周）：18 键 / 162 件
  - 批量（>4 周）：71 键 / 328 件 —— 慢动销，**这周不必再下单**，不是要拆单
- 月补→周补的周期库存变化（均匀需求、不含安全库存）：个 **−273.3 件**
  （`Σweekly_p50 × (30−7)/2/7`）。
- MOQ 过冲公式：`下单量 = ceil(需求/MOQ)×MOQ`，例：PP棉 MOQ 350 千克、需求 175 → 下单 350
  （过冲 175）；日字扣 MOQ 1000 个、需求 500 → 下单 1000。物料层 `safety_stock=0`，
  过冲会直接变呆滞料。

## 4. 边界与待确认

- 不改 `decision_pack` / `supply_netting` / r6 / h180 的任何数字；不写 MOQ 到主表。
- 周补只改复核节奏，不改变保护期 14 天与安全库存口径。
- 周需求取预测 60 天窗口 P50 ÷ 60 × 7（`forecast-20261027-r2`）；预测缺失的键标
  「无需求证据」，不按 0 处理。
- 待确认：21 项 MOQ 的维护责任人 / 是否仍有效；MOQ 单位（卷/米/千克）与采购对话一致。
- 若未来要让 MOQ 生效，应作为**补货下单层**的一步另开任务，不在政策层改数。
