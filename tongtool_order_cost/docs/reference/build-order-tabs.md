---
okf: v0.1
type: Reference
title: build-order-tabs — 从原始订单重建 self 166 / FBA 95 / merged 78
description: 停用 Colab 后的三张订单表本地构建器：行集合、销售额与真实尾程口径、EN 产品属性、FBA UUID 展开、95↔78 对账与 202608/202609 对拍结论
date: 2026-11-10
module: tongtool_order_cost
tags: [tongtool, build-order-tabs, colab-replacement, self-166, fba-95, merged-78]
resource: tongtool_order_cost/tongtu_cost_engine/domain/build_tabs.py
---

# build-order-tabs

## 这是什么

`20250409 合并EN成本` Colab 截至 4.8 的逻辑，落到一个本地 CLI：

```bash
cd tongtool_order_cost
uv run python -m tongtool_order_cost.tongtu_cost_engine.cli build-order-tabs \
    --month 202608 --root .
```

它**不再读取 Colab 生成的模板**（`wb_fresh_*` / `wb_fba_*` / `merged_*`），而是从
原始订单 / GS FBA 销量表 / EN 明细 / BOM / 汇率 / 仓库映射重建三张表：

| 输出 | 行数（202608 / 202609） | 契约 |
|---|---:|---|
| `self_build_<月>.csv` | 10,819 / 6,221 | self 166 列 |
| `fba_build_<月>.csv` | 1,966 / 1,269 | FBA 95 列 |
| `merged_build_<月>.csv` | 12,785 / 7,490 | merged 78 列 |

同时输出对拍与审计：`parity_<月>.md`、`manifest.json`、`recon_95_78*.csv`、
`self_cost_audit.csv`、`fba_cost_audit.csv`。全部在 `out/build_tabs/<月>/`。

## 输入

| 输入 | 默认位置 | 说明 |
|---|---|---|
| 非 FBA 原始订单 | `out/snapshots/<月>/raw_<月>_filtered.csv`（无则 `out/raw_<月>.csv`） | 已删特殊订单（4.1.0.1） |
| EN 物料/别名 | `out/item_refcode.csv` | `name/customer_code/item_group/variant_of` |
| EN 订单明细 | `out/en_items_all_089.csv` | 行级 `erp_item_code` / `shipping_method` |
| 作废原单标记 | `out/snapshots/<月>/order_flags.csv` | 拆单原单（invalid=1） |
| 物料组树 | `out/item_group_branch.tsv` | 分支/父组 |
| BOM 成本 | `out/bom_cost_product_with_kits.csv` | 84 列，含四列成本/头程/valuation |
| 仓库分类 | `out/snapshots/<月>/wh_map.tsv` | 仓库 → USNJ/USTX/PL/FBA/海外仓 |
| 汇率 | `out/fx_<月>.csv` | `scripts/fetch_fx_rates.py` 导出 |
| 仓库成本来源 | `out/warehouse_cost_sources.tsv` | `scripts/fetch_warehouse_cost_sources.py` 导出 |
| 产品主数据（可选） | `out/product_attributes.tsv` | `scripts/build_product_attribute_master.py` 抽取历史属性 |
| GS FBA 销量表 | `out/raw_fba_<月>.csv` | 站点/MSKU/SKU/订单数量/销量/销售额 |
| 通途 FBA 导出 | `out/fba_export_<月>.csv` | 仅 `fba_shadow` 缺失时重建用（覆盖校验） |
| FBA shadow 78 | `out/fba_shadow/<月>/fba_shadow_<月>.csv` | 缺失时自动 `build_fba_shadow` |
| 旧写回表（可选） | `out/writeback_<月>.csv` | 只继承系数 / 历史属性；不参与行集合与金额 |

## self 166 口径

1. **行集合**：`split_merge` 成熟合并明细 = 合并组 1 行 + 透传行。
   202608：raw 10,912 → 删特殊订单 10,910 → 吸收 91 → **10,819**。
   202609：6,268 → 6,267 → 吸收 46 → **6,221**。
2. **合并组**：`发货数量 = pieces`（成品件数），`售价 = 组内全部组件行售价之和`，
   `售价*汇率 = 组售价 × 财务汇率`，`运费 = 组内「物流商运费」之和`。
   **不再复刻**旧 Colab 的“组件行 + 合并展示行”双计，也不再删除通用填充物行。
3. **透传行**：数量/售价取原始行；`售价*汇率 = 售价 × 汇率`。
4. **汇率**：按 `收款币种` 取 `fx_<月>.csv`；缺失时才用 `售价(人民币)/售价` 兜底并记录。
5. **尾程运费**：取原始订单 `物流商运费`（真实尾程），不是 `包裹总运费`/`通途运费`。
   202608 与旧表完全一致；202609 旧表生成时只补了 1,344 行尾程，当前快照已补到 3,969 行。
6. **四列成本**：`bom_cost` Phase2 金额 ÷ `cost_qty` 得单位成本，再用 `_fill_cells`
   派生 29 列；`1件 = 皮壳 + 绍兴二次 + 二次`，`订单总成本 = 产品成本*数量 + 头程*数量 + 运费 + 海外仓*数量`，
   `订单利润 = 售价*汇率 − 订单总成本`。成本阻断行留空、不填 0。
7. **仓库来源编码**：`warehouse_cost_sources.tsv`（GS `订单发货仓库对应成本来源`），
   覆盖两月全部 12/5 个发货仓库，0 未映射。
8. **产品属性**：`品类orig` = 原始 `品类`；`品类/品类统一名/品类别名` = EN 物料组；
   `品类尺寸面料编码` = **EN 物料号 `item_fg`**（不再拼 Colab 旧键）；
   面料/尺寸/有无扣/带*尺寸/尺寸先大后小 优先从 BOM `item_zlmb_name` 解析；
   `品类编码/品类尺寸编码/材料编码/美版5尺寸` 从产品主数据兜底；
   `当月是否新品/产品发售日期/运营人员/美国分区/海外仓_USHWC` 从旧写回同键行继承。

### 成本列一致性（2026-11-10 修订）

- `皮壳含包装成本` / `皮壳不含包装成本` / 两列的 `*系数` **统一写当前 `皮壳成本`**
  （新引擎只有 BOM `cost_fg` 一个皮壳口径；旧 Colab 的 76.961 类历史值不再继承）。
- `EN绍兴包装半成品成本` / `EN绍兴包装成品成本` **统一写当前 BOM**
  `cost_sxbzbcp` / `cost_sxbzcp`。注意旧 Colab 的「成品」列实际是
  「合并后二次加工×系数」，语义已更正。
- **method 唯一依据 = BOM 主档 `shipping_method`**（2026-11-10 定案）：
  所有行（含 `-Cover/-Foam/-PPCotton` 组件后缀）都按 BOM method + 后缀矩阵计价；
  EN 订单行 `shipping_method` 只写审计（`en_method`），不参与定价。
  202608 仅 46 行、202609 仅 9 行 EN=皮壳 / BOM=半成品，其余完全一致。
  仓库（主仓/退货仓/皮壳仓）不改变 method 或成本算法。
- 审计：`self_method_warehouse_audit.csv` 列出 EN vs BOM method、raw vs EN 仓库的差异行；
  202609 有 468 行 raw `美中-FZH-DANEEY` 但 EN 是 `美中-FZH-DANEEY-退货产品仓`。

## FBA 95 口径

- 业务骨架 = GS FBA 销量表；按 `订单数量` 展开为 N 行（N = 订单数）。
- **首行**承载 `销量/销售额/发货数量/成本金额`；其余行为占位行：量额为 0，
  但保留单位成本、系数、属性与 GS 报表列（成本/订单费用/利润/利润率等逐行重复）。
- `订单号` = 基于 `(月, 站点, MSKU, SKU, index)` 的确定性 UUID5（旧表为随机 UUID4），
  `index_col = 0..N-1`。
- 单位成本来自 `fba_shadow`（EN FBA 明细 exact `erp_item_code` + BOM 成品口径）；
  `绍兴二次加工成本` 为 EN 绍兴成本，`二次加工成本 = 0`，`运费 = 0`（FBA 尾程在账期）。
- 产品属性：`品类/品类统一名/品类别名` = EN 物料组；面料/尺寸/有无扣/带*尺寸 从 BOM
  `item_zlmb_name` + GS 产品名解析；`品类尺寸面料编码` = EN 物料号；仓库来源编码从
  `warehouse_cost_sources.tsv` 覆盖（`发货区域=美国/欧洲`、`汇总分类=美国FBA/欧洲FBA`）；
  `品类编码/品类尺寸编码/材料编码/当月是否新品/产品发售日期` 从旧 FBA 表或产品主数据兜底。
- 202608/202609 与 `phase36/gs_ready` 的 FBA 95 **金额指标逐项 0 差异**；属性同键一致率：
  品类orig 100%、品类统一名 93.8%、面料 97.5%、尺寸 89.9%、编码类 100%。

## merged 78 口径

- self 166 按列名取 78 列（缺 `运营部当月是否新品/图片` 补空）+ FBA 95 映射 78 列：
  `平台SKU ← MSKU`、`通途SKU ← SKU`、`售价/汇率` 留空、`售价*汇率 ← 销售额`。
- 行数 = self + FBA；`recon_95_78*.csv` 按 `(站点,MSKU,SKU)` 对 14 个指标做 95↔78 粒度对账，
  两月总计差异 0。

## 对拍结论（vs `out/phase36/<月>/gs_ready/`）

| 指标 | 202608 | 202609 |
|---|---:|---:|
| self 行数 | 10,870 → 10,819 | 6,246 → 6,221 |
| 售价*汇率 | +1,729.97 | +1,276.64 |
| 运费 | 0.00 | **+304,541.93** |
| 产品成本*数量 | 0.00 | 0.00 |
| 订单总成本 | 0.00 | +304,541.93 |
| 订单利润 | +1,729.97 | −303,265.29 |
| FBA 95 | 全部 0 | 全部 0 |

- `售价*汇率` 增加 = 旧表删除通用填充物行造成的销售额丢失被追回
  （202608 254.79 售价 / 1,729.98 汇率额；202609 188.27 / 1,278.13）。
- 202609 运费 +304,541.93 是**数据补齐**（旧表 1,344 行有真实尾程，新快照 3,969 行），
  不是算法差异。**重写 202609 GS 前需财务确认是否采用新尾程。**
- 行数减少 = 合并组 1 行替代旧表的组件行（202608 83 组、202609 42 组）。

## 已知缺口 / 后续

- `品类` 现在是 EN 物料组，与旧 Colab 的叶子品类只有 13.5%（self）/ 22.2%（FBA）同名；
  `品类统一名` 命中 91.2% / 93.8%。如需旧叶子品类，需另建「EN 物料组 → 叶子品类」主数据。
- `品类尺寸面料编码` 改为 EN 物料号（旧表是 Colab 拼的品类-尺寸-面料键），下游如按旧键
  连接需同步调整。
- `EN绍兴包装成品成本` 现在取 BOM 真实 `cost_sxbzcp`；旧 Colab 该列实际是
  「合并后二次加工成本×系数」，语义不同。
- `品类编码/品类尺寸编码` 新 SKU 尚缺（202608 110 行 / 202609 141 行，依赖产品主数据）；
  `产品发售日期/当月是否新品` 与旧表可用率一致（约 10%/4%）；
  `平台SKU-渠道账号&实际运营人员`、`美版5尺寸` 旧表本身为空。
- `product_attributes.tsv` 是从历史 self 表抽取的产品属性缓存；新增产品需要更新主数据。
- 202609 有 1 行 `加拿大FBA仓` 不在 GS 仓库来源表（只有「加拿大海外仓」），
  区域保留 shadow 的 `CA`/`FBA`；成本来源仍是 `COST-USFBA`。
- 尚未替换 `fill-tables` / GS 写回链路：先对拍、财务确认后，再决定切到本构建器。

## 相关

- Colab parity 审计：`docs/research/2026-11-09-colab-local-parity-audit.md`
- 拆单合并成本规则：`docs/solutions/workflow-issues/tongtu-split-merge-writeback-cost-rules.md`
- 拆单类型与拆单前 SKU：`docs/solutions/conventions/tongtu-split-types-and-presplit-sku.md`
- 尾程补齐流水线：`docs/reference/monthly-tail-cost-pipeline.md`
