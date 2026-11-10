---
okf: v0.1
type: Reference
title: 通途订单成本管道：从原始订单到 GS 三张写回表的完整步骤与判断标准
description: 逐步说明读取 raw/EN/BOM/FX/仓库映射、订单身份与拆单合并、BOM 四列成本、写回演练、GS 29 列最小修补、build_tabs 全量重建与 FBA/merged 的口径
date: 2026-11-10
module: tongtool_order_cost
tags: [tongtool, pipeline, cost-engine, gsheet, split-merge, fba, build-order-tabs]
---

# 通途订单成本管道（端到端）

> 本文只描述**当前代码的真实行为**（2026-11-10 起）。关键变化：
> **绍兴发货方式（method）一律取 BOM 主档 `shipping_method`，EN 订单行的
> `shipping_method` 只做审计，不参与定价；仓库（主仓/退货仓/皮壳仓）不改变成本算法。**

## 0. 输入

| 输入 | 位置 | 用途 |
|---|---|---|
| 通途原始订单 | `out/snapshots/<月>/raw_<月>_filtered.csv`（已删特殊订单） | 行集合、数量、售价、真实尾程 `物流商运费`、仓库/包裹/地址 |
| EN 订单明细 | `out/en_items_all_089.csv` | 行级 `erp_item_code`（产品身份）、EN `shipping_method`（仅审计）、FBA 明细 |
| EN 物料/别名 | `out/item_refcode.csv`（`name/customer_code/item_group/variant_of`） | 通途 SKU/客户物料号 → EN Item / 产品 |
| BOM 成本表 | `out/bom_cost_product_with_disabled.csv`（1104 版） | `shipping_method`（定价唯一依据）+ 四列成本 + 头程 |
| 套件报表 | `out/bom_cost_product_with_kits.csv` + `product_bundles.csv` | 套件展开/对账 |
| 汇率 | `out/fx_<月>.csv` | `售价*汇率`（财务汇率，不用 raw 的人民币列替代） |
| 仓库分类 | `out/snapshots/<月>/wh_map.tsv` | 发货仓库 → USNJ/USTX/PL/FBA/海外仓 |
| 仓库成本来源 | `out/warehouse_cost_sources.tsv` | 仓库 → 成本来源编码/头程来源/发货区域 |
| GS FBA 销量表 | `out/raw_fba_<月>.csv` | FBA 95 业务骨架（站点/MSKU/SKU/订单数量/销量/销售额） |
| FBA shadow | `out/fba_shadow/<月>/fba_shadow_<月>.csv` | 146/133 个 SKU 的 EN BOM 单位成本与 78 列属性 |
| 旧写回表（可选） | `out/writeback_<月>.csv` | 只继承财务系数/历史属性；**不参与行集合与成本** |

## 1. 读原始订单 + 解析身份

1. 读 raw（**已删特殊订单**；`fetch_special_orders.py` 生成过滤文件）。
2. 用 EN 行级 `erp_item_code` 定产品身份；同一行多个物料 → 不猜，走别名/阻断。
3. 拆单原单（`order_flags.invalid=1`）只作 aux 校验，不单独出行。
4. 单行身份优先级：EN 行级 exact item → `customer_items.ref_code` 别名 → 产品族；
   Cover 行在拆单组内让位给填充行（避免 Cover 的 EN 物料号被设成另一产品线）。

## 2. 定「绍兴发货方式」（method）

```
定价 method = BOM 主档该 item 的 shipping_method
             （EN 行级 exact item 优先；否则别名候选 item 的 BOM method 必须唯一）
EN shipping_method = 仅记录到 en_method，用于审计；不参与任何成本取数
```

- 同一个产品，不管从 `美中-FZH-DANEEY`、`-退货产品仓`、`-皮壳仓库` 发货，
  **method 和成本算法相同**。
- 202608/202609 实测：BOM method 与 EN method 仅在 **46 / 9 行**不同
  （全是 EN=皮壳、BOM=半成品），其余 10,708 / 6,094 行完全一致。
- 无 BOM method 的行：非商品配件显式零成本；其余按 item_group 兜底或阻断。

## 3. 拆单合并（`split_merge`）

- 键：`order_common_part + 产品`；同单多子单/多包裹/多组件合并成**一件成品**。
- 合并组：1 行；`发货数量 = pieces`（皮壳件数）；组内组件为 0；
  销售额/售价(人民币)/运费 = 组内求和；售价*汇率 = 组售价 × 财务汇率。
- 产品归属：共享皮壳看填充类型（PP 棉/海绵）；共享填充看皮壳（图案/颜色）；
  仍不唯一 → 阻断（不猜）。
- 件数：子单皮壳件数为准；原单重复组件不翻倍；仅 pieces 无法确定时才用原单兜底。
- 单独卖 `-Cover/-Foam/-PPCotton`：不合并，按**后缀矩阵**计价（见 §4）。
- 行全集：成熟合并组 1 行 + 透传行；**不复刻**旧 Colab 的组件行+展示行双计。

## 4. BOM 四列成本（`bom_cost`）

| 列 | 取数 |
|---|---|
| 皮壳成本 | 当前 BOM `cost_fg` |
| 头程运费 | 按仓库价格表 + shape/method：`-Cover`→cover；`-Foam`→freight−cover；半成品→sfg；成品→freight；FBA→FBA freight |
| 二次加工成本（目的地加工） | USNJ→`usnj_valuation_rate`；USTX/美国海外仓→`ustx_valuation_rate`；PL→`pl_valuation_rate`；FBA=0 |
| 绍兴二次加工成本 | 半成品→`cost_sxbzbcp`；成品→`cost_sxbzcp`；皮壳→0；FBA→`sx_cost_all−cost_fg` |

后缀矩阵（仅非 FBA，shape 由通途SKU 后缀决定）：
- `-Cover`：绍兴二次=0、二次加工=0、头程=皮壳头程；
- `-Foam`：皮壳=0、绍兴二次=半成品/成品包装、头程=总额−皮壳；
- `-PPCotton`：皮壳/绍兴二次/头程=0。

公式：
```
1件产品成本 = 皮壳 + 绍兴二次 + 二次加工          （不含头程）
产品成本*数量 = 1件 × 件数
订单总成本 = 产品成本*数量 + 头程*数量 + 运费 + 海外仓*数量
订单利润 = 售价*汇率 − 订单总成本
```
恒等式/后缀闸门/EN 独立重算在 Phase2 内断言，违例即失败。

## 5. 写回演练（`writeback_rehearsal`）

- 行集合 = Phase1 合并明细；每行带 `source_row/group_id/method/pieces`，100% 可追溯。
- 非成本列优先原始订单；缺列按 `(order_common, 平台SKU)` 从旧写回映射，多值冲突留空。
- 成本四列来自 Phase2；阻断/跳过行留空 + reason，**不填 0**。
- 产出 `writeback_new_<月>.csv`（185 列，含审计）。

## 6. 本地三张表（`build-order-tabs`，全量重建）

- **self 166**：raw + 成熟合并组 + 财务系数 → 166 列。
  - 售价/数量/运费/汇率口径见 §3；成本 29 列见 §4。
  - `品类尺寸面料编码` = EN 物料号；`品类` = EN 物料组；属性优先 BOM/EN，旧表仅兜底。
  - 写出 `self_build_<月>.csv` + `self_method_warehouse_audit.csv`。
- **FBA 95**：GS 销量表按 `订单数量` 展开确定性 UUID；首行承载量/额，占位行保留单位成本；
  `index_col` 全局连续；单位成本来自 FBA shadow；写出 `fba_build_<月>.csv`。
- **merged 78**：self + FBA 按 78 列合同拼接；`平台SKU←MSKU`、`通途SKU←SKU`、
  `售价/汇率` 空、`售价*汇率←销售额`；附 `recon_95_78*.csv` 粒度对账。
- 断言：行集合、销售额/运费守恒、成本恒等、FBA 展开、95↔78 总计。

## 7. 写 GS（两种模式）

### 7.1 最小修补（已用于 2026-11-10）

- 只写 **29 个成本/系数列**；行数/销售额/运费/属性/EN包装等不动。
- 脚本 `out/_gs_min_patch.py`（默认 dry-run，`--apply` 写）；备份 + 回读。
- 列：皮壳含/不含/成本、绍兴二次、二次加工、头程、运费(**不写**)、海外仓(**不写**)、
  `*数量`、1件、产品成本*数量、总成本、利润、3 个基础系数、12 个派生系数。
- 202608 self 46 行 +1,920.04；202609 self 9 行 +370.55；FBA 只改含/不含。

### 7.2 全量替换（build_tabs）

- 用 `self_build/fba_build/merged_build` 整体替换 ws：行集合/销售额/属性/成本全部按新表。
- 脚本 `out/_gs_full_replace.py`（默认 dry-run，`--apply` 备份+写入+回读）。
- 202608 已执行：self 10,870→10,819、merged 12,836→12,785，FBA 1,966 不变；
  订单总成本 0 差异、利润 +1,729.97（追回旧表丢的销售额）。
- 202609 已 dry-run：self 6,246→6,221、merged 7,515→7,490；
  **运费 +304,541.93（快照真实尾程 423,892.72 vs 旧 GS 119,350.79）**，
  利润 −303,265.29。尾程更新后需整流程重跑再决定是否全量替换。

## 8. 判断标准速查

| 情况 | 处理 |
|---|---|
| 同一 SKU 不同仓库/退货仓 | 不影响 method/成本；按产品 BOM 算 |
| EN method ≠ BOM method | 按 BOM method 定价；EN 记 `en_method` 审计 |
| 单独卖 `-Cover/-Foam/-PPCotton` | 按后缀矩阵；不按 EN method |
| FBA | 绕过全部后缀；皮壳=`sx_cost_all`、绍兴二次=`sx_cost_all−cost_fg`、二次=0 |
| 合并组 | 1 行、件数=pieces、组件行=0、组内金额/运费守恒 |
| 缺 BOM/多 BOM/缺仓库分类 | 阻断，不猜、不填 0 |
| 成本 vs 销售额 | 成本只信 BOM；销售额 = 原始订单（组内求和）；运费 = 真实尾程 |

## Related

- 写回历史/列用途/BOM 版本：`docs/research/2026-11-10-gs-cost-write-history-and-column-map.md`
- build-order-tabs：`docs/reference/build-order-tabs.md`
- 拆单合并成本规则：`docs/solutions/workflow-issues/tongtu-split-merge-writeback-cost-rules.md`
- Phase2 策略：`docs/reference/cost-engine-spec/32-phase2-bom-cost-policy.md`
