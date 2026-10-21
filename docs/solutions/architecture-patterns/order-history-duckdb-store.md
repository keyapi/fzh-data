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
  - "给分公司补货时，成品/皮壳/半成品到底发什么、BOM 怎么换算"
tags: [demand-forecast, duckdb, tongtool, gsheet, erpnext, replenishment, shipment-type, 3pl]
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
| `bom` / `bom_item` / `bom_exploded` | BOM | EN 默认 BOM（5,575 条去重）+ 多级展开（root/node/level/qty_per_unit） |
| `replenishment_v3_ship` | SKU×仓 | 成品补货 + 物料组发货形态 + cover 池提示 |
| `component_ship_plan` / `_summary` | 皮壳/内胆 | 按 BOM 第一层把补货量换算成 `PK#`/`ND#` 发货清单 |
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

- **库存来源只用通途**（EN Bin 不可作可用库存，PR #300 `02-capability-map` §4：EN 不扣减通途）：`erp2_stocks_stocksquery`，按仓分页（pageSize≤100、5 次/分钟）。三家主仓 **4,465 行**（美东 2,072 / 美中 1,024 / 波兰 1,369）；半成品/成品仓与 WayfairCG 另拉，见 §10。
- **预测**：`scripts/forecast_ensemble.py`，MA3/MA6/MA12/Croston/TSB + ens5 中位数，滚动 origin、horizon=3、指标 WAPE。
  - **回测结果（1,347 条 SKU×仓 序列）：ens5 0.690 最优**，ma3 0.703、ma12 0.705、tsb 0.723、ma6 0.724、croston 0.741。注意这是本数据集结论；PR #300 E1 的 held-out 里 TSB 0.511、ens5 0.520，且 E1 的选择规则选中 Croston，见 §10 末尾。
  - 预测覆盖已扩到 **2,357 条序列**（最少 3 个月历史，短史 SKU 用同一套方法兜底）；其中 **1,156 条有未来月预测**。回测仍只跑 ≥12 个有销量月的 1,347 条，保持与 E1 可比。
  - **口径修正（重要）**：`demand_forecast_90` 早期把 ens5 表的全部月份求和（包含回测 origin 和历史外推），会把已停售 SKU 的旧预测也算进需求。现只取 `month >= 当前月`，并按**实际未来月数 ×30** 归一（有的序列只剩 1–2 个月未来，不能一律除 90）。
- **补货 v3**：`scripts/forecast_replenishment_v3.py`，`ROP = 日均预测 × (交期 45 + 安全 30)`，`建议 = max(0, ROP − (available + intransit + PO未入库))`。
  - 供给 = 通途库存 `available` + `intransit` + 通途 PO 未入库量（`erp2_purchase_purchaseorderquery`，180 个 SKU×仓、16,043 件在途）。
  - 修正后首跑：4,465 个 SKU×仓，**1,156 有未来预测**，**311 需补货**，建议合计 **4,548 件**（美中 2,257 / 美东 1,324 / 波兰 967）。

### 10. 分公司补货的发货形态：成品 / 皮壳 / 半成品（2026-10-21 修正）

**先把术语摆正**（`CONCEPTS.md:149-153`）：成品 `KS` = 皮壳 `PK#` + 内胆 `ND#` + 充棉；半成品只有皮壳/内胆。「组件」不是公司内部业务分类，上一版把它展开到面料/拉链/PP 棉是错的——那是中国生产物料，不是分公司补货对象。

- **发货形态由物料组决定，带不带内胆看 BOM**：EN `Item Group.custom_shipment_type_to_branch`（皮壳 243 组 / 成品 169 / 半成品 62 / 空 107）。旧称「给分公司发皮壳」是口语，具体发什么以 BOM 为准：EN 启用且提交的 KS BOM 2,210 条里，`PK#+ND#` 1,745、`PK# only` 280、都没有 185。个别产品只有皮壳没有内胆，必须看 BOM。
- **销售订单按钮的真实逻辑（已核实代码与数据）**：Excel 上传只生成 `PK#` 行（`key_test.item_utils.read_excel_file`，`是否皮壳`→`PK#`），**不会自动加内胆**；内胆由另一个启用的 Client Script `销售订单 子表 items 所有行 增加配套物料20241030` 添加，调用 `key_test.item_utils.get_supporting_item`：按 **物料组 + 尺寸属性** 找 `内胆#<无前缀组名>` 变体（不是读 BOM），并遵循 `custom_replaced_by_other_item_group`（如 `内胆#三角靠枕无扣 → 内胆#三角靠枕`）。
  - 实测最近 90 天 22 张含 `PK#` 的已提交 SO：13 张有内胆、9 张没有；2026-08-17 起基本 1:1（`SO-26-00101` 49/49、`-00110` 106/106）。`SO-26-00102` 的 8 皮壳/5 内胆逐行与 BOM 一致；零内胆的几张（`-00111`/`-00115`/`-00130`）都能找到同尺寸内胆变体，判断是**没点按钮**，不是没有内胆。
  - BOM 与按钮逻辑在 1,811 个含皮壳的成品 BOM 中：两者都有 1,531（84.5%）、都没有 136、BOM 无但按钮会加 82、BOM 有但按钮找不到 62。规划时必须把这两种偏差显式标出来。
- **补货量只有一套**：`forecast_replenishment_v3` 按分公司仓的通途库存池（listing SKU）算 ROP；不要为组件另算一套 ROP，否则同一库存池会被扣两次。
- **换算成发货形态**（`scripts/forecast_shipment_plan.py`）：取 BOM 第一层 `PK#`/`ND#`，并按上面的按钮逻辑补齐：
  - 成品 → 发成品 KS；
  - 皮壳 → 发 `PK#`；内胆按 BOM，BOM 没有但按钮会加的标 `nd_from_button_not_bom`，BOM 有但按钮找不到的标 `bom_nd_no_button_match`；
  - 半成品 → 同样按第一层 BOM，包装半成品暂未进 KS BOM。
- 首跑（311 行 / 4,548 件）：**皮壳 246 行 / 3,702 件**、成品 47 / 655、半成品 14 / 171、未匹配 4 / 20。皮壳 249 行 / 3,831 件，内胆来自 BOM 219 行 / 3,637、按钮补 10 行 / 52、按钮对不上 11 行 / 121；另有 12 行无 BOM、3 行无物料映射。
- **不要用 EN Bin 当组件供给**：EN 不扣减通途，`Bin.actual_qty` 只是账面；组件没有独立的可用库存池。上一版用 EN Bin + 负库存夹紧算出 34,283 的做法已废弃。
- **`-Cover` 与 listing 是两个独立 SKU 账，不是同一数量镜像**（实测）：5 个 cover-only 物料的不带后缀 SKU 库存为 0，`-Cover` 有 50–222；通途 7 天变动明细里，卖哪个 SKU 就只动哪个，二者不联动；全部物料 cover 销量 404 件 vs listing 8,849 件（4.4%）。所以**可售总量应按 `listing + -Cover` 相加**（两个不同数量桶，不会重复计数），但不能把同一个数量同步写两遍。是否同一堆实物，数据不能证明（可能是同一批货按渠道拆账，也可能是两堆），需调拨单/盘点/运营确认。
- 脚本对 107 个有 cover 库存的物料输出 `cover_stock_same_item` / `pool_note`（`cover_only` / `cover_also`），**不自动合并到 ROP**；等实物池确认后再决定是否把 cover 库存计入可用供给。
- **面料/拉链/PP 棉不在范围内**：面料/拉链走中国生产物料计划；PP 棉是分公司填充耗材（部分产品 BOM 里确有，但本次不做补货）。

**3PL（WayfairCG）**：`erp2_stocks_stocksquery` 能查，但数据很薄——5 个启用仓实测只有 Cranbury 92 个 SKU / 880 件，Perris 4 个 / 0，Romeoville 2 个 / 0，McDonough、PortWentworth 为空；没有报表导出 API（文档镜像只有库存查询/变动/FBA），Excel 只能在 UI 导出。结论：**API 可作交叉核对，权威仍是 Wayfair 后台导出**（PR #300 `13-g1-data-sources` §1.5）；3PL 是否纳入补货等 PR #301 G1b 的责任确认，目前不并入分公司主仓补货。

**关于 E1 的准确说法**：PR #300 E1（8 个 PB SKU）的验证选择规则选中 Croston；held-out WAPE 为 TSB 0.511、ens5 0.520、Croston 0.530、naive 0.602——组合优于 naive，但**不能说 E1 验证了 ens5**。本库 1,347 条长史序列的回测里 ens5 0.690 最好，这是本数据集结论，不是 E1 的复现。

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

需要导的表：`tabBOM`（5,582）、`tabBOM Item`（13,157）、`tabItem`（15,230，含 MOQ/装箱/交期）、`tabItem Group`（发货方式 + `custom_replaced_by_other_item_group`）、`tabItem` 的 `ND#` 物料（852）、`tabItem Variant Attribute`（11,494，取「尺寸」）、`tabBin`（非零 3,123）、`tabPurchase Order Item`（未结 21 行）。全部只读，不碰业务写入。

### 12. 仍未覆盖 / 下一步

- **3PL（WayfairCG）**：API 可查但只有 Cranbury 有量（92 SKU / 880 件），其余仓几乎为空；权威仍是 Wayfair 后台导出，是否纳入补货待责任确认（PR #301 G1b 已暂停）。
- **BOM 缺口**：22 个 KS + 1 个 TJ 有销量但无默认 BOM；12 行皮壳/半成品补货因此无法拆组件。
- **皮壳池身份**：`-Cover` 与 listing 在通途是**两个独立 SKU 账**（变动不镜像，cover 销量只占 4.4%），可售总量可相加，但**是否同一堆实物未证**；需调拨单/盘点/运营确认后，才能决定 cover 库存是否计入 ROP。
- **内胆库存**：通途没有独立的 `ND#` 库存码；本次只按 BOM 算「该发多少内胆」，没有内胆可用库存口径。
- **半成品包装**：KS BOM 只含 `PK# + ND#`，绍兴包装半成品未进 BOM。
- **组件（皮壳/内胆）没有独立 ROP**：补货量沿用成品池，发货形态只是换算；等分公司能分别盘点皮壳/成品后再考虑独立库存池。

## Why This Matters

- 预测的准确性首先取决于**历史是否完整**；靠 EN 一家会缺掉 2023–2025 的大半历史。
- 用 DuckDB 独立承载，既不动生产业务表，又能随时重算；字段口径（运费、金额、日期）的差异被显式建模而不是被掩盖。

## When to Apply

- 做销量预测/补货分析、需要 2023 年以来的数据时。
- 有人问"能不能用通途 API 把 EN 历史补齐"——答案是不能，见 §2。
- 需要把成品补货换算成皮壳/内胆的发货清单时，见 §10。
- 需要新增数据源（FBA、库存、在途）时，按 §4 的表结构扩展。

## Examples

```bash
# 全量订单 + FBA + SKU 映射（只读 GS/EN，不占通途 API）
uv run python scripts/forecast_order_store.py --months 202301,...,202609 --with-fba --sku-map
# 增量补一个月
uv run python scripts/forecast_order_store.py --months 202609 --en-sample 0
# 通途库存快照（三家主仓；5 次/分钟，12s 间隔）
uv run python scripts/tongtool_stock_snapshot.py --warehouses "美东-CENTRADE,美中-FZH-DANEEY,波兰-FZHPoland-covers"
# 半成品/成品仓库存（通途没有 PK#/ND# 码，皮壳/海绵用 -Cover/-Foam 后缀）
uv run python scripts/tongtool_stock_snapshot.py --warehouses "FZH-DANEEY-半成品仓,FZH-DANEEY-成品仓"
# 3PL 库存（API 可查但数据很薄，仅作交叉核对）
uv run python scripts/tongtool_stock_snapshot.py --warehouses "WayfairCG-Cranbury仓,WayfairCG-McDonough仓,WayfairCG-Perris仓,WayfairCG-PortWentworth仓,WayfairCG-Romeoville仓"
# 通途采购在途
uv run python scripts/tongtool_po_snapshot.py --from 2026-06-01
# ens5 预测 + 回测（短史 SKU 也出预测；回测仍只跑 ≥12 个有销量月）
uv run python scripts/forecast_ensemble.py --horizon 3 --origins 6 --min-months 3
# 成品补货建议（ROP）
uv run python scripts/forecast_replenishment_v3.py --lead-days 45 --safety-days 30
# 按「绍兴发货方式」换算成 成品/皮壳/半成品 发货清单
uv run python scripts/forecast_shipment_plan.py
```

产物统一落在 **`D:/Work/fzh-order-store/`**（持久目录，不进 git；Windows 临时目录会被清理）。

## Related

- [EN 通途订单/包裹同步为什么会漏与空壳](../integration-issues/en-tongtool-order-package-sync-failures.md) — API 可见性/同步缺陷的完整背景
- [背贴品名缺失怎么补——通途SKU 在 EN 有两种登记写法](../integration-issues/sku-name-backfill-via-en-customer-code.md) — `customer_code` / `customer_items[].ref_code`
- [生产 2核4G 跑批量回填会压死机器](../developer-experience/prod-batch-backfill-oom-small-box.md) — 为什么历史回补不在生产跑
