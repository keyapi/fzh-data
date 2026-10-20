---
okf: v0.1
type: Reference
title: 销售历史分析库（DuckDB）——GS 月表 + EN 并集，支撑销量预测与补货
date: 2026-10-20
category: architecture-patterns
module: demand_forecast
problem_type: architecture_pattern
component: tooling
severity: medium
applies_when:
  - "要做销量预测 / 补货决策，需要 2023 年至今的自发货与 FBA 历史销量"
  - "想判断 EN 的 Tongtool Order 能不能靠通途 API 补齐历史"
  - "要设计订单历史的分析库（表/字段/口径/增量方式）"
tags: [demand-forecast, duckdb, tongtool, gsheet, erpnext, replenishment]
related_components: [EN_API, tongtool_api, erpnext]
---

# 销售历史分析库：GS 月表 + EN，DuckDB 承载

目标：为**销量预测 + 补货决策**提供准确、可重建的历史销量。结论先行：**不要指望用通途 API 补齐 EN 的历史订单；历史真源是 GS 月表，用 DuckDB 做独立分析库，不要往 EN 业务表灌历史数据。**

## Context

- EN 的 `Tongtool Order` 由自定义 app 每晚同步，**2025-07 起基本完整**（2026-08 抽样 200/200 命中）。
- 更早的月份（2023-01 ~ 2025-06）EN 只有零星数据；而 GS 的 `通途订单YYYYMM / YYYY年M月订单` 从 **2023-01** 起都有。
- 用通途开放 API 回补历史时，实测其**可见性是部分的**（详见下节），无法完整重建 2025-07。

## Guidance（本学习沉淀的做法）

### 1. 分层取数，不硬灌 EN

```
EN Tongtool Order（运营真源，2025-07 起）
GS 通途订单YYYYMM（历史真源，2023-01 起）
        ↓ 解析成统一结构
DuckDB（分析库，独立文件）
        ↓ 按 order_id 并集（同号以 EN 为准）
销量序列 → 预测 → 补货建议
```
**不要把 GS 数据写回 EN**：口径不同（GS 是发货口径）、字段不同、会产生重复单与物料匹配错乱。若将来需要在 EN 里看历史，另建只读 DocType。

### 2. 通途 API 的历史可见性（实测，重要）

- **单次查询的分页深度有限**：不带 `accountCode` 查某月，第 60 页即空（约 5–6 千条）；按账号查能翻得更深（如某大账号到第 40 页，与其月量吻合）。
- **可见性跟"最近更新时间"相关，不是销售日期**：查 2025-06，只返回少数**近期被更新过**的单；大部分 6 月单已不可见。
- 结论：API 适合**近期补漏**，**不适合重建 2025-07 以前的历史**；GS 是唯一完整来源。
- 另：app 的批量导入把 `storeFlag` 写死为 `'0'`（活跃表），不传 `'1'` 拉不到一年表；即便传了，受上述可见性限制也无法拉全。

### 3. GS 月表的字段与口径（2023–2026 实测）

- 列数 **87 → 91**（2023-01 87；2026-08 91）。**核心字段全部稳定**：订单号、销售日期、发货日期、渠道、渠道账号、发货仓库、通途SKU、平台SKU、发货数量、售价、包裹号、跟踪号。
- 变化：删除 `ebay销售税`、`运费`；新增 `交易单号`、`通途运费`、`物流商运费`、`自定义费用`、`通途运费原币种(金额)`。
- **运费口径要兼容**：
  - 2023：只有 `运费` → 归入 `freight_actual`（`freight_semantics='legacy'`）；
  - 2024 起：`物流商运费` = **真实**运费 → `freight_actual`；`通途运费` = **预估** → `freight_estimated`。
- **日期口径**：月表是**发货口径**（`发货日期`），但带 `销售日期` 列。做销量预测用 `sale_date`；与 EN 比对用**订单号存在性**，不受口径影响。
- **金额**：`订单总售价(人民币)` 是通途口径，**不是财务口径**；字段命名 `amount_raw_cny` 明确标注，预测/补货不依赖它。

### 4. DuckDB 表设计（已落地）

| 表 | 粒度 | 说明 |
|---|---|---|
| `gs_orders` | 明细行 | 统一字段（order_id/platform_sku/sku_tongtool/qty/sale_date/despatch_date/channel/account/warehouse/package_id/tracking/currency/amount_raw_cny/freight_actual/freight_estimated/freight_semantics/line_id/source/month） |
| `fba_demand` | 月×MSKU×站点 | 来自 `YYYY年M月FBA订单` 工作表：订单数、销量、销售额、成本、费用、利润、利润率 |
| `sku_map` | SKU→物料 | 来自 EN `Item Customer Detail`（见下） |
| `stock_bin` / `po_open` | 物料 | EN 现存、未结采购在途 |
| `replenishment` | 物料 | on_hand / on_order / 90 天日均 / 覆盖天数 / 建议补货量 |
| `orders_unified` | 订单级视图 | EN 优先，GS 只补 EN 没有的 |
| `raw_wide/raw_YYYYMM.parquet` | 原样 | **每月整表原样保存**，可追溯、可换真源重算 |

**重建成本极低**：整个库就是一个 `.duckdb` 文件 + Parquet，删掉重跑即可 → 设计可以迭代，不必一次到位。

### 5. 子表不能走 REST 列表（403）

`Item Customer Detail`、`Purchase Order Item`、`Item Language` 这类**子表**用 `/api/resource/<child>` 查询会 **403**。可行做法：按订单号/父文档逐条取，或**在生产 DB 上直出小表**（TSV）再导入分析库。`Bin`、`Purchase Order` 等主表可以正常列表。

### 6. SKU 归一

用 EN 的 `Item Customer Detail.ref_code`（通途SKU 的登记处）建 `sku_map`：**99.2% 的明细行能映射到 EN 物料**（2,838/3,135 个 distinct SKU）。未映射的主要是 `-Cover`/`-Foam` 后缀变体与辅料（如 PP 棉），属正常。

### 7. 补货决策第一版

- **仓库命名两边不一致**（GS `美东-CENTRADE` vs EN `辅材仓 - FZH`），第一版先按**物料级**汇总。
- 公式：`suggested_qty = max(0, 日均销量 × 目标天数 − (现存 + 在途))`；日均取近 90 天。
- 首跑（目标 60 天）：4,682 个物料，**191 个需补货**，平均覆盖 5.6 天，建议合计 7,357 件。
- 下一步可加：断货标记、交期（PO 创建→入库）、MOQ、按仓拆分（需先建仓库映射）。

## Why This Matters

- 预测的准确性首先取决于**历史是否完整**；靠 EN 一家会缺掉 2023–2025 的大半历史。
- 用 DuckDB 独立承载，既不动生产业务表，又能随时重算；字段口径（运费、金额、日期）的差异被显式建模而不是被掩盖。

## When to Apply

- 做销量预测/补货分析、需要 2023 年以来的数据时。
- 有人问"能不能用通途 API 把 EN 历史补齐"——答案是不能，见 §2。
- 需要新增数据源（FBA、库存、在途）时，按 §4 的表结构扩展。

## Examples

```bash
# 全量订单 + FBA + SKU 映射（只读 GS/EN，不占通途 API）
uv run python scripts/forecast_order_store.py --months 202301,...,202609 --with-fba --sku-map
# 增量补一个月
uv run python scripts/forecast_order_store.py --months 202609 --en-sample 0
# 补货快照
uv run python scripts/forecast_replenishment.py --target-days 60
```

## Related

- [EN 通途订单/包裹同步为什么会漏与空壳](../integration-issues/en-tongtool-order-package-sync-failures.md) — API 可见性/同步缺陷的完整背景
- [背贴品名缺失怎么补——通途SKU 在 EN 有两种登记写法](../integration-issues/sku-name-backfill-via-en-customer-code.md) — `customer_code` / `customer_items[].ref_code`
- [生产 2核4G 跑批量回填会压死机器](../developer-experience/prod-batch-backfill-oom-small-box.md) — 为什么历史回补不在生产跑
