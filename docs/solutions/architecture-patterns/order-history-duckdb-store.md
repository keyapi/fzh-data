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
  - "皮壳/内胆/面料等组件怎么按 BOM 展开做补货"
tags: [demand-forecast, duckdb, tongtool, gsheet, erpnext, replenishment, bom]
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
| `bom` / `bom_item` / `bom_exploded` | BOM | EN 默认 BOM（5,582 条）+ 多级展开（root/node/level/qty_per_unit） |
| `component_demand` | 组件 | 成品预测 × BOM 累计用量，日均（全公司） |
| `component_replenishment` | 组件 | EN Bin + 未结 PO 供给、ROP、MOQ/装箱取整 |
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

### 8. 仓库归一（关键，2026-10-21 按用户确认）

**GS 历史里绝大多数是旧仓名**：`CENTRADE`（16 万行）、`FZHPoland-covers`（10 万行）、`FZH-DANEEY`（2.6 万行）；新前缀名（`美东-CENTRADE` 等）只有少量。**任何按仓聚合前必须先映射**。

规则（`scripts/warehouse_map.py`）：

| 分类 | 举例 | 处理 |
|---|---|---|
| `current` | `美东-CENTRADE`、`美中-FZH-DANEEY`、`波兰-FZHPoland-covers` | 直接用 |
| `renamed` | `CENTRADE` → `美东-CENTRADE`；`FZHPoland-covers` → `波兰-…`；`FZH-DANEEY` → `美中-FZH-DANEEY` | 自动补前缀 |
| `component->main` | `FZH-DANEEY-成品仓/半成品仓/皮壳仓库`、`美中-FZH-DANEEY-皮壳仓库` | **并入 美中-FZH-DANEEY**（用户确认同属美中 DANEEY 仓） |
| `finished->main` | `FZHPoland-finished` | **并入 波兰-FZHPoland-covers** |
| `unused` | 北美之路 LA01/NJ02、枫筝海外仓（多伦多/温哥华）、休斯顿1号/备用、海外仓美西备用 | 海外仓，目前不用 |
| `pending` | `海外仓美中仓库备用仓`、`扬州仓库` | 待用户确认 |

### 9. 库存快照 + ens5 预测 + 补货 v3（2026-10-21）

- **库存来源改为通途**（EN 库存口径不可用）：`erp2_stocks_stocksquery`，按仓分页（pageSize≤100、5 次/分钟）。已拉三家主仓 **4,465 行**（美东 2,072 / 美中 1,024 / 波兰 1,369）；另拉组件仓「半成品仓 160 / 成品仓 250」作核对，但**通途里没有 PK#/面料/拉链**，组件库存只能取 EN。
- **预测**：`scripts/forecast_ensemble.py`，MA3/MA6/MA12/Croston/TSB + ens5 中位数，滚动 origin、horizon=3、指标 WAPE。
  - **回测结果（1,347 条 SKU×仓 序列）：ens5 0.690 最优**，ma3 0.703、ma12 0.705、tsb 0.723、ma6 0.724、croston 0.741 —— 与 PR #300 E1 的结论一致（简单组合优于单模型）。
  - 预测覆盖已扩到 **2,357 条序列**（最少 3 个月历史，短史 SKU 用同一套方法兜底）；其中 **1,156 条有未来月预测**。回测仍只跑 ≥12 个有销量月的 1,347 条，保持与 E1 可比。
  - **口径修正（重要）**：`demand_forecast_90` 早期把 ens5 表的全部月份求和（包含回测 origin 和历史外推），会把已停售 SKU 的旧预测也算进需求。现只取 `month >= 当前月`，并按**实际未来月数 ×30** 归一（有的序列只剩 1–2 个月未来，不能一律除 90）。
- **补货 v3**：`scripts/forecast_replenishment_v3.py`，`ROP = 日均预测 × (交期 45 + 安全 30)`，`建议 = max(0, ROP − (available + intransit + PO未入库))`。
  - 供给 = 通途库存 `available` + `intransit` + 通途 PO 未入库量（`erp2_purchase_purchaseorderquery`，180 个 SKU×仓、16,043 件在途）。
  - 修正后首跑：4,465 个 SKU×仓，**1,156 有未来预测**，**311 需补货**，建议合计 **4,548 件**（美中 2,257 / 美东 1,324 / 波兰 967）。

### 10. 组件级补货：EN BOM 展开（2026-10-21）

成品补货只看成品 SKU 不够：皮壳（PK#）、内胆（ND#）、面料、拉链、PP 棉要单独备料。做法：

- **BOM 取数**：EN 启用且默认的 BOM **5,582 条、明细 13,157 行**（`scripts/forecast_component_bom.py` 读 `bom.tsv` / `bom_items.tsv`）。
  - 层级实测**最多 2 层**：成品 → PK#/ND# → 面料/拉链/辅料；无环。
  - 同一 item 有 7 组重复默认 BOM（内容相同），按 BOM 名排序保留第一条。
- **需求**：ens5 成品日均 × BOM 累计用量（递归展开，最多 4 层）。**981/1,004（97.7%）** 有预测的成品能匹配到 BOM；缺的 22 个 KS + 1 个 TJ 需补 BOM。
- **供给**：EN `Bin.actual_qty`（只算中国境内 FZH/绍仓库，排除所有仓库聚合、海外到货/在途、不良/报废/呆滞/样品）+ EN 未结 PO（`received_qty < qty`）。
  - 组件库存**不在通途**：三家主仓与半成品/成品仓都没有 PK#、面料、拉链。
  - **负库存按 0 计**并打 `negative_stock` 标记（如 `NL1010-3#-32-WHITE-SINGLE` EN 为 −47,305，若不夹紧会凭空多出 5.5 万条拉链的建议量）。
- **重订货**：`ROP = 日均组件需求 × (交期 + 安全 15)`；交期优先取 Item `lead_time_days`，缺省 30 天。
- **取整**：先按 Item `custom_quantity_per_outer_package`（其次 `min_pack_qty`）向上取整，再满足 `min_order_qty`（MOQ）。目前只有 21 个物料维护了 MOQ、747 个维护了装箱数，取整影响约 +2%。
- 首跑：**1,731 个组件有需求**（1,048 个半成品 + 683 个原料），**1,334 个需补货**，建议合计 **34,283**（按件/米等各自单位）。

### 11. EN 侧数据导出（BOM / Bin / PO）

`bench --site ... mariadb` 的输出**会在 1000 行截断**（本次实测：表里 5,582 行，导出只有 1,000 行），批量导出必须直连 mysql 客户端：

```bash
ssh 阿里云-FZH-ERPNext-frappe "python3 - <<'PY'
import json, subprocess, os
cfg=json.load(open('/home/frappe/frappe-bench/sites/erpnext.vilavi.cn/site_config.json'))
env=dict(os.environ); env['MYSQL_PWD']=cfg['db_password']
sql='SELECT ... FROM tabBOM ...'
r=subprocess.run(['mysql','-u'+cfg['db_name'],'-N','-B','-e',sql,cfg['db_name']],
                 capture_output=True,text=True,env=env)
open('/tmp/export.tsv','w',encoding='utf-8').write(r.stdout)
PY"
```

需要导的三张小表：`tabBOM`（5,582）、`tabBOM Item`（13,157）、`tabBin`（非零 3,123）、`tabPurchase Order Item`（未结 21 行）。全部只读，不碰业务写入。

### 12. 仍未覆盖 / 下一步

- **3PL（WayfairCG）库存**：通途里是启用仓，但库存需人工导出，尚未并入。
- **BOM 缺口**：22 个 KS + 1 个 TJ 有销量但无默认 BOM；补齐后需求会更完整。
- **组件供给口径**：只有 EN `Bin.actual_qty`，且个别物料存在大额负库存（已夹紧并标记）；EN 的在制品/委外仓是否都算可用，需要业务确认。
- **MOQ/装箱数维护率低**：21/15,230 有 MOQ、747 有装箱数，取整目前只影响少数物料。
- **组件需求未按仓拆分**：按全公司汇总（组件在中国集中采购/生产），海外仓备料需另建调拨逻辑。

## Why This Matters

- 预测的准确性首先取决于**历史是否完整**；靠 EN 一家会缺掉 2023–2025 的大半历史。
- 用 DuckDB 独立承载，既不动生产业务表，又能随时重算；字段口径（运费、金额、日期）的差异被显式建模而不是被掩盖。

## When to Apply

- 做销量预测/补货分析、需要 2023 年以来的数据时。
- 有人问"能不能用通途 API 把 EN 历史补齐"——答案是不能，见 §2。
- 需要把成品预测展开到皮壳/内胆/面料等组件时，见 §10。
- 需要新增数据源（FBA、库存、在途）时，按 §4 的表结构扩展。

## Examples

```bash
# 全量订单 + FBA + SKU 映射（只读 GS/EN，不占通途 API）
uv run python scripts/forecast_order_store.py --months 202301,...,202609 --with-fba --sku-map
# 增量补一个月
uv run python scripts/forecast_order_store.py --months 202609 --en-sample 0
# 通途库存快照（三家主仓；5 次/分钟，12s 间隔）
uv run python scripts/tongtool_stock_snapshot.py --warehouses "美东-CENTRADE,美中-FZH-DANEEY,波兰-FZHPoland-covers"
# 组件仓库存核对（通途里只有零星半成品，没有 PK#/面料）
uv run python scripts/tongtool_stock_snapshot.py --warehouses "FZH-DANEEY-半成品仓,FZH-DANEEY-成品仓"
# 通途采购在途
uv run python scripts/tongtool_po_snapshot.py --from 2026-06-01
# ens5 预测 + 回测（短史 SKU 也出预测；回测仍只跑 ≥12 个有销量月）
uv run python scripts/forecast_ensemble.py --horizon 3 --origins 6 --min-months 3
# 成品补货建议（ROP）
uv run python scripts/forecast_replenishment_v3.py --lead-days 45 --safety-days 30
# 组件补货建议（BOM 展开 + MOQ/装箱取整）
uv run python scripts/forecast_component_bom.py --lead-days 30 --safety-days 15
```

产物统一落在 **`D:/Work/fzh-order-store/`**（持久目录，不进 git；Windows 临时目录会被清理）。

## Related

- [EN 通途订单/包裹同步为什么会漏与空壳](../integration-issues/en-tongtool-order-package-sync-failures.md) — API 可见性/同步缺陷的完整背景
- [背贴品名缺失怎么补——通途SKU 在 EN 有两种登记写法](../integration-issues/sku-name-backfill-via-en-customer-code.md) — `customer_code` / `customer_items[].ref_code`
- [生产 2核4G 跑批量回填会压死机器](../developer-experience/prod-batch-backfill-oom-small-box.md) — 为什么历史回补不在生产跑
