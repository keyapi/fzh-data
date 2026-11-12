# tongtool_order_cost — Agent 交接

> **CLI**: `scripts/run_audit_170.py` · `scripts/remap_gsheet_sku.py` · `scripts/lookup_tongtool_sku.py` · `scripts/upload_monthly_order_sheet.py` · `python -m tongtool_order_cost.tongtu_cost_engine.cli build-order-tabs --month <月> --root .`
> **人读**: [README.md](README.md)
> **Skill**: `.agents/skills/tongtool-order-cost/SKILL.md`

## 业务背景

运营对「特殊规则改成本」有异议时，需要证明 Colab **1.7.0** 逻辑：匹配哪些订单、各科目 before→after→Δ。六月 AMZBAINAUS 多为 **ref（参考值）** 模式。

2026-08 追加：通途允许**改主档 SKU 名**。井的规则表用新名；1.4/Google Sheet 订单仍可能是导出当时的旧名。1.7.0 精确匹配会漏行。处理方式是**改订单表旧名→新名**，不改井的新名。

## 管道

```
订单xlsx(未改成本) + 规则xlsx + FX
  → 时间窗过滤 → 6列去重 → attach FX → ￥参考值
  → backup_* → coeff/ref 写入（FBA 正数尾程跳过；负数账期差异写入）
  → 重算产品成本/订单总成本/利润
  → change_events → 多 Sheet 审计 xlsx
```

Google Sheet SKU 改名（与 1.7.0 审计独立）：

```
bootstrap_gsheets_credentials.py
  → secrets/gsheets-service-account.json（gitignore）
remap_gsheet_sku.py --sheet <标题>          # 默认 dry-run
remap_gsheet_sku.py --sheet <标题> --apply  # 用户确认后
lookup_tongtool_sku.py <SKU...>             # 主档是否存在
```

## 关键模块

| 文件 | 作用 |
|------|------|
| `tongtool_order_cost/engine_170.py` | 与 notebook Cell 22 对齐的应用引擎 |
| `tongtool_order_cost/audit_sources.py` | 只读源盘点/快照 + 分块取数二分失败隔离（U1/U3） |
| `tongtool_order_cost/profitability_audit.py` | 盈利审计核心：行身份/grain/口径矩阵/异常分类/利润倒挂（U2/U4/U5/U6） |
| `tongtool_order_cost/profitability_report.py` | 对账闸门 + JSON/Excel(17表)/管理摘要（U7） |
| `tongtool_order_cost/ustx_cost_compare.py` | 美中 USTX 三方案成本对比：列合同 / B1·B2 成本目录 / 全月逐行比较 / 归因 / 闸门 / 产出（纯离线） |
| `tongtool_order_cost/audit.py` | 事件 → 审计簿 |
| `tongtool_order_cost/io_loaders.py` | 订单/规则/汇率加载 |
| `tongtool_order_cost/pp_cotton.py` | 美中 DANEEY 订单 × BOM Cost List → PP 棉 kg 估算 |
| `tongtool_order_cost/gsheets.py` | 本地 SA JSON → gspread Client / gsheet2df |
| `tongtool_order_cost/sku_map.py` | 已确认旧→新映射；gray60 / Foam97 例外 |
| `tongtool_order_cost/tongtool_goods.py` | ERP2 `erp2_product_goodsquery` |
| `tongtu_cost_engine/domain/build_tabs.py` | **build-order-tabs**：raw+成熟合并+BOM → self 166 / FBA 95 / merged 78 |
| `tongtu_cost_engine/domain/tab_contracts.py` | 三张表的稳定列合同（166/95/78）与产品属性列 |
| `scripts/run_audit_170.py` | 1.7.0 特殊规则审计 CLI |
| `scripts/fetch_month_orders.py` | 导出源表 `YYYY年M月订单`/`FBA订单` → `raw_<月>.csv`/`raw_fba_<月>.csv` + manifest |
| `scripts/fetch_fx_rates.py` | GS `和财务部共享/汇率` 按月导出 |
| `scripts/fetch_special_orders.py` | 从 ws `处理特殊订单` 导出删除清单；`build-order-tabs` 默认自动应用（`--require-special-orders` 缺失即失败） |
| `scripts/check_warehouse_map.py` | raw 发货仓库 vs `wh_map.tsv` 覆盖检查 |
| `scripts/fetch_warehouse_cost_sources.py` | 仓库 → 成本来源编码映射导出（GS） |
| `scripts/build_product_attribute_master.py` | 从历史 self 表抽取产品属性主数据 TSV |
| `scripts/bootstrap_gsheets_credentials.py` | 从 Colab notebook cell 0 抽出 SA 到 `secrets/` |
| `scripts/remap_gsheet_sku.py` | Google Sheet SKU 列 dry-run / apply |
| `scripts/lookup_tongtool_sku.py` | 通途主档 SKU 存在性 |
| `scripts/estimate_pp_cotton.py` | PP 棉用量估算 CLI |
| `scripts/audit_monthly_profitability.py` | 月度盈利审计 CLI：`list`/`snapshot`(只读冻结)/`analyze`(离线)/`ustx-compare`(美中三方案离线对比) |

## Notebook / Google Sheet 约定（2026-11-10 更新）

1.7.0 读 gs **和财务部共享** → ws **黄-特殊规则-订单改销售额成本**（`use_local_rule_csv_170 = NO`）。
旧 ws **Jeck特殊规则-订单改销售额成本** 自 2026-11-10 起只读留存，不再作为 1.7.0 输入。

**参考值优先（老板 2026-11-10 确认）**：同一行同时有系数和参考值时，按参考值执行、忽略系数；引擎打印 `⚠️ ... 按参考值优先`，并在 `meta["n_mixed_ref_priority"]` 计数。Colab cell 22 同步。

**FBA 列对齐**：28 条 FBA 规则的 `二次加工` 参考值已移到 `绍兴二次加工`（二次=0），参考值数值未改；新成本口径下 FBA 二次加工固定为 0。

**成本口径**：分公司发成品（USNJ/USTX/PL method=成品）二次加工=0（202609 18 行 −1,341.65；202608 16 行 −1,303.48）；FBA 二次=0，绍兴二次直接用 `cost_sxbzcp`，不要再用 `sx_cost_all − cost_fg`（264 行 `sx_cost_all=0` 但 `cost_sxbzcp>0` 会低估；issue `keyapi/work_order_task#6` / `keyapi/tongtool_integration#24`）。最终订单成本表是 `build_tabs/1104 BOM`；`out/merged_202609.csv` 11-04 是旧表，不作最终口径。

六月订单两份 workbook 都有这 3 张 FBA 相关表（列名不完全一样）：

| 工作表 | 常见 SKU 列 |
|--------|-------------|
| `2026年6月FBA订单` | `SKU`（销量汇总） |
| `写回2026年6月FBA订单` | `SKU`（订单明细） |
| `写回2026年6月FBA订单和非FBA订单` | `通途SKU` |

Workbook 标题：`通途订单202606-特殊规则`（1.7.0 用）、`通途订单202606`（不用来跑特殊规则，SKU 仍应对齐）。

## 已确认旧→新（AMZBAINAUS FBA Velvet）

| 订单旧名 | 井/主档新名 |
|----------|-------------|
| `BNFBAvelvetblack-100` | `BNUSFBA-Velvet-Black-100` |
| `BNFBAvelvetgray-100` | `BNUSFBA-Velvet-Grey-100` |
| `BNUSFBA-vel-grey153` | `BNUSFBA-Velvet-Grey-153` |
| `BNvelvetblack-153fba` | `BNUSFBA-Velvet-Black-153` |

**不要替换：** `BNFBAvelvetgray60`（通途主档存在：三角无扣 60CM）；`CENKZ159410287-BLACK-97`（自发货 CEN）。
**规则笔误：** `FoamFBAKZ159410287-BLACK-97` → 应写 `FoamFBAKZ159410287-BLACK-100`（改规则，不改订单 100→97）。

## 去重键（6 列）

`运营人员` + `发货区域` + `通途SKU` + `渠道账号不含国家` + `渠道账号` + `发货仓按销售汇总分类`（`keep=last|first`）

## 验证要点

1. `ref_usd × fx × 发货数量` = 数量列 after
2. FBA 尾程：参考值 **>0 或 =0** 不改 `运费`；参考值 **<0** 按账期差异写入 `运费`
3. `01_科目瀑布` 各科 Δ 与总览一致
4. SKU 替换：apply 后旧名计数为 0，新名计数 = 原旧名计数，gray60 计数不变
5. 混合规则：`meta["n_mixed_ref_priority"]` 应等于同时有系数/参考值的生效规则数；这些行不应进入 `n_skipped`

## 相关档案

- [审派生成本/规则结果的独立验证法](../docs/solutions/best-practices/auditing-derived-costs-independent-verification.md)
  —— 老板质疑成本/利润率时：外部对偶、同名列陷阱、无留档只能"量级吻合"

- [gspread insert_cols 把行当列](../docs/solutions/developer-experience/gspread-insert-cols-rows-as-columns.md)
  —— 批量插列前先确认 API 的 rows/cols 语义；写前备份、写后回读

- [月度盈利审计](docs/reference/monthly-profitability-audit.md)
  —— 老板质疑「平均成本/运费低、回款低反而利润高」时：**先 snapshot 冻结、再 analyze 离线**，
  口径矩阵 + 对账闸门 + JSON/Excel/管理摘要；**只读，不回写 GSheet/EN**。
  含 **美中 USTX 三方案成本对比**（`ustx-compare`：A 现状 / B1 测算表 / B2 EN-import 重建）——
  证明美中改走当地二次加工后四项成本怎么变；**纯离线、不写任何表**。
  要点：B1(人工测算) 与 B2(EN 重建) 非同源，**差异即结论**；头程与现状同源（A 已按绍兴发货方式取 EN 值 → Δ=0），仅「按皮壳重量」勾选项会再差 −16,517；
  另有 **B3 新工资情景**（工资率 167.8→105，只动 `operating_cost`，其余保持 9/3 快照）：7 月美中合计 A 526,225 → B2 791,137 → **B3 717,678**（ΔB3 +191,453）；需 `--wage-boms` 指向 EN 逐 BOM 工序表。见 `docs/reference/en-ustx-bom-wage-rate-spec.md`。
- [Colab 成本引擎逆向规格](docs/reference/colab-cost-engine-spec.md)
  —— 皮壳/头程/二次加工/绍兴二次加工的确切 pandas、仓库→成本来源编码、美中口径不对称的代码证据。
- [EN 直接采购件用「自套 BOM」出成本惯例 + 骨架缺口](../docs/solutions/architecture-patterns/en-direct-purchase-self-bom.md)
  —— 订单成本码为空时，先查物料有没有自套 BOM / 在不在皮壳平均表（`WL-shape-frame` 骨架就是漏项）

## 凭证

| 用途 | 本地文件 | git |
|------|----------|-----|
| Google Sheet | `secrets/gsheets-service-account.json` + `tongtool_order_cost/.env` | 忽略 |
| 通途 ERP2 | `tongtool_api/.env` | 忽略 |

Cursor Agent 用用户级 MCP `user-tongtool_erp2_primary`（`~/.cursor/mcp.json`，由 `tongtool_api/setup_cursor_mcp.py` 写入）。CLI 脚本仍用 `tongtool_api/mcp_http.py`。限流仍是商户合计 5 次/分钟。

## 禁止

- 不要把订单/规则大 xlsx 提交进 git
- 不要提交 service account JSON / notebook 私钥
- 不要修改旧 ws「Jeck特殊规则-订单改销售额成本」（只读留存）
- 不要把新 ws 第 511–516、610–614、776–777 行的系数重新填回；参考值优先，系数只作历史对照
- 不要直接 push main；走 `feature/...` + PR

## 通途SKU→EN物料 的权威桥（2026-10-17 起）

排查 USTX 成本时确立，**优先用·别猜解析**：

- **两条权威源**（都不需通途 API）：EN `Item Customer Detail.ref_code`（**REST 403，须 SSH 查 DB**）；gsheet `importBOMCostList.客户物料号`（现成列）。
- EN 物料名 → 重量模板：**去末段(颜色) + 前缀 `ZLMB#`**。
- 口径 **直连优先、旧键兜底**：`ustx-compare` 的 `--direct-map` / 默认取 `客户物料号`；`--no-direct` 关。7 月美中直连覆盖 **99.9%**（4367/4372），相对旧键 ΔB2 264,912→268,610。
- **改 gsheet 前**：`import皮壳成本` 是 `IMPORTRANGE` 拉的，**改它无效**；改源工作簿 `财务部绍兴成本核算表单2023`（`皮壳成本平均…`/`品类使用面料`/`材料价格明细`），且**源表+成本表成对改**。
- 详见 `docs/reference/cost-engine-spec/`（27/28 页）与 `docs/solutions/integration-issues/tongtu-en-item-mapping-and-gsheet-source-fix.md`。

## 通途订单成本引擎迁移（`tongtu_cost_engine`，2026-11-05 起）

- 目标：Colab 成本引擎 → 本地包；主路径 **合并成一件成品 + 月末 BOM 单位成本 × 件数**；EN 订单行存储成本只作对账（会陈旧，如 CENTRADE 0 vs BOM 165.128）。
- 四列：皮壳=BOM `cost_fg`；头程=BOM 头程列；二次加工=目的地 `valuation_rate`（FBA=0、美国海外仓=USTX；**分公司发成品=0**）；绍兴二次=皮壳 0 / 半成品包装半成品 / 成品包装成品 / FBA `cost_sxbzcp`（含半成品包装）。恒等式：四列（除头程）= 1件产品成本。
- 订单全集：EN 有效单（`invalid=1` 只作 aux 校验）；拆分子单 `_1/_2` 保留；GS 原始表作业务骨架，`写回…` 只对拍；FBA 成本用 EN 明细，GS FBA 销量表作 78 列骨架。
- 套件：Product Bundle 全子件 method 一致才派生；TJ# 与子件不得双计；`show_kit_items` 报表可对账。
- Canary：旧值必须取目标写回表（不是销量报表）；写前备份/hash/锁，写后回读；不一致用备份整体回滚。
- 代码：`tongtool_order_cost/tongtu_cost_engine/`；文档：`docs/reference/cost-engine-spec/32-38`；经验：`docs/solutions/architecture-patterns/tongtu-cost-engine-local-migration.md` 等三篇。

### 坑：单独卖皮壳/海绵/PP棉 ≠ 产品歧义（2026-11-06）

- **共享皮壳**（如 `TT0031187K0063920-Cover` 同时挂 KS0340 PP棉 / KS0342 海绵）别名天然多候选；不能当歧义留空。
- **先看原始订单有没有配套行**：同 `order_common` 有 Cover + Foam/PPCotton → 拆单，合并成一件成品计价；只有一行 → 单独卖单品，按 EN 后缀特例逐行计价。
- **行级身份用 EN `erp_item_code`**（行级权威）；但**拆单组内 Cover 行不采信**自己的 EN 物料号（常被默认到另一产品线），由填充行锚定。
- `-COVER`：皮壳成本 + 皮壳头程，绍兴二次/二次=0；`-FOAM`：皮壳=0，绍兴二次=绍兴包装成本，头程=总额−皮壳；`-PPCOTTON`（method=皮壳）：皮壳/绍兴二次/头程=0；FBA 全部绕过。
- 规则与实测：`docs/reference/cost-engine-spec/38-en-line-identity-and-single-item-suffix.md`。

### 坑：拆单合并成本写回（2026-11-09）

- **组行识别**：模板行可能是拆单前公共单号（`Cds-…QFL`）、TikTok 归一化单号（`…-1`）或单行组显示组件 SKU；Phase36 必须按 `order_common` / 数字主体映射，不能按 `(订单号,通途SKU)` 精确匹配后清零。
- **件数**：EN 原单组件行重复不代表件数翻倍；子单皮壳件数可确定时以子单为准，只有 `pieces_ambiguous/zero` 才用原单兜底。
- **产品族**：同一皮壳用于 PP 棉/海绵两种成品；两族 `item_group` 只差「PP棉 vs 海绵」→ 填充行定产品；只差款式/图案 → 皮壳定产品；皮壳 EN 行在错误族时按族前缀替换（`KS0342-HLR-50-DEEPBLUE`→`KS0340-HLR-50-DEEPBLUE`），构造不出则阻断。
- **订单号截断**：模板订单号少一段会表现为 `crosswalk_missing`，不是缺行；本地模板与 GS 要同步改。
- **审计**：合并组按「单位成本 × 发货数量」对比 Phase2 四列合计；组内行不套单品后缀矩阵。
- **FBA 对比**：绍兴包装半成品是共同部分；分公司/FBA 的绍兴二次是扣掉半成品后的增量，`半成品+增量=四列绍兴二次`；FBA合计=皮壳+成品包装+FBA头程。财务表在 `out/fba_vs_branch/`，共享副本在 `D:\Work\王忠于\成本核算\`。
- 经验：`docs/solutions/workflow-issues/tongtu-split-merge-writeback-cost-rules.md`、`docs/solutions/conventions/tongtu-split-types-and-presplit-sku.md`。
- **EN 登记**：只写子表 `customer_items.ref_code`，不写主表 `Item.customer_code`；组件多对多、完整 SKU 唯一；配套 issue `work_order_task#4` / `tongtool_integration#22`。
- **Colab 退场**：截至 4.8 的成本/拆单合并核心已移植；2026-11-10 已补 `build-order-tabs`，可本地重建三表。对照表见 `docs/research/2026-11-09-colab-local-parity-audit.md`。前置脚本：`scripts/fetch_month_orders.py`、`scripts/fetch_fx_rates.py`、`scripts/fetch_special_orders.py`、`scripts/check_warehouse_map.py`、`scripts/fetch_warehouse_cost_sources.py`、`scripts/build_product_attribute_master.py`。GS 读写触点矩阵见 `docs/reference/tongtool-order-pipeline.md` §0.1（唯一未移植写回：`检查运营人员-写回…`）。

### build-order-tabs（2026-11-10，停用 Colab 的关键件）

```bash
cd tongtool_order_cost
uv run python -m tongtool_order_cost.tongtu_cost_engine.cli build-order-tabs --month 202608 --root .
```

- 输出 `out/build_tabs/<月>/`：`self_build_<月>.csv`（166）、`fba_build_<月>.csv`（95）、
  `merged_build_<月>.csv`（78）、`parity_<月>.md`、`manifest.json`、`recon_95_78*.csv`、
  `self_cost_audit.csv`、`fba_cost_audit.csv`。
- **行集合**：成熟合并组 1 行 + 透传行（202608 10,819；202609 6,219，2026-11-11 新增 2 单 QDY 删除）。
  旧 Colab 的「组件行 + 合并展示行」双计 **不复刻**。
- **特殊订单自动处理**：build 默认读 `out/special_orders_<月>.csv`（`fetch_special_orders.py`
  从 ws `处理特殊订单` 导出）并自动过滤 raw、写回 `raw_<月>_filtered.csv`；
  `manifest.stats.special_orders` 记录删除行/单数与命中订单号。正式月跑加
  `--require-special-orders`，清单缺失直接失败（否则断言为 `warn` 并按原始 raw 构建）。
- **合并组金额**：发货数量=pieces；售价=组内组件售价之和；售价*汇率=组售价×财务汇率；
  运费=组内 `物流商运费` 之和。**不要**再用 `包裹总运费`/`通途运费` 当尾程。
- **FBA 95**：按 GS `订单数量` 展开 UUID 行；首行承载量/额，占位行只保留单位成本；
  订单号是确定性 UUID5；单位成本来自 `fba_shadow`。
- **merged 78**：`平台SKU←MSKU`、`通途SKU←SKU`、`售价/汇率` 空、`售价*汇率←销售额`。
- **对拍**（vs `phase36/<月>/gs_ready`）：FBA 全 0；self/merged 成本与数量 0；
  202608 利润 +1,729.97（追回旧表丢的填充物销售额）；202609 运费 +304,541.93
  （旧表生成时尾程只补了 1,344 行，当前快照 3,969 行）→ **重写 9 月 GS 前必须财务确认**。
- **属性口径**：`品类尺寸面料编码` 写 EN 物料号（不是 Colab 旧键）；`品类` 写 EN 物料组；
  旧叶子品类/部分编码从 `product_attributes.tsv` 或旧写回兜底，缺失见 parity 报告。
- **成本列一致性（2026-11-10）**：`皮壳含包装成本/不含/系数` 统一=当前 `皮壳成本`；
  `EN绍兴包装半成品/成品成本` 统一=当前 BOM `cost_sxbzbcp/cost_sxbzcp`。
  **不要**再从旧写回继承这些列，否则会出现 76.961 与 53.939 并存。
- **method 唯一依据（2026-11-10 定案）**：定价 method 一律取 **BOM 主档 `shipping_method`**
  （`load_orders` 按 EN 行级 exact item / 别名候选解析）；EN 订单行 method 只写 `en_method`
  审计，不参与定价。仓库（主仓/退货仓/皮壳仓）不改变 method/成本。
  组件后缀行同样按 BOM method + 后缀矩阵；不要再用 EN method 做任何定价分支。
  202608 仅 46 行、202609 仅 9 行 EN=皮壳 / BOM=半成品，其余完全一致。
- **方法/仓库审计**：`out/build_tabs/<月>/self_method_warehouse_audit.csv`。
  202609 有 468 行 raw 仓库=`美中-FZH-DANEEY` 但 EN=`…-退货产品仓`，同一 SKU 会因此
  出现 绍兴二次 0 vs 16.52；排查先看这张表，不要只看 raw `发货仓库`。
- **GS 写回（2026-11-10）**：先做了 29 列最小修补（8/9 月 6 个 ws，readback 0）；
  随后 **202608 全量替换**为 build_tabs（self 10,870→10,819、merged 12,836→12,785、
  FBA 不变；总成本 0 差异、利润 +1,729.97），readback 0。
  202609 同期全量替换（运费按更新后的快照 +304,541.93，利润 −303,265.29）。
  备份/明细：`out/gs_min_patch_<月>/`、`out/gs_full_replace_<月>/`。
  端到端步骤与判断标准见 `docs/reference/tongtool-order-pipeline.md`。
- **未动列**：`运费`（9 月仍是模板旧值）、销售额、商品属性、`EN绍兴包装*`、
  `是否皮壳/当月类型`、行集合；全量替换 build_tabs 前需逐项确认语义。
- **FBA shadow 缓存**：`fba_shadow_<月>.manifest.json` 记录 BOM/EN/GS 输入 sha256；BOM 变化后 build-order-tabs 自动重建；显式 `--fba-shadow` 不一致直接失败。成本阻断/shadow 缺失已纳入失败门禁。
- **GS 全量写回入口**：`scripts/gs_full_replace.py`（默认 dry-run，`--apply` 写）。
- **FBA 绍兴二次 = `cost_sxbzcp`**（含半成品包装）；上游 `sx_cost_all` 在 `cost_fg=0` 时漏计，已提 `work_order_task#6`，消费侧兜底 `tongtool_integration#24`。
- **GS 写回已切换**（2026-11-10 起 8/9 月；2026-11-12 起 7 月）：入口 `scripts/gs_full_replace.py`
  （默认 dry-run；`--book` 可写 `通途订单YYYYMM-特殊规则`）。
- 详细说明：`docs/reference/build-order-tabs.md`。

### 202607 重算与美国本地成本（2026-11-12）

- **202607**：self 9,552 / FBA 1,653 / merged 11,205；self 总成本 2,750,957.10、利润 2,707,801.37。
  已写回 `通途订单202607` 与 `-特殊规则` 三表（特殊规则表被覆盖为基础表，**1.7.0 需重跑**）。
- **差异主因**：美中二次加工改用目的地 valuation（旧表误用绍兴/半成品）；1104 BOM 皮壳；
  FBA 绍兴二次=`cost_sxbzcp`、二次=0；2 个包裹尾程手工修正 −586.67。
- **美国本地产品（棉包 KS0050）架构**：产品不建 BOM（`cost_fg=0`）；
  `USNJBZCP#/USTXBZCP#KS0050-<尺寸>` BOM = PP 棉 kg × 美国采购价 + 5 分钟 × 16.607 元/h；
  物料组 `棉包` 发货类型=成品。引擎例外：**成品 + cost_fg=0 + 绍兴=0 + 目的地 valuation>0
  → 二次加工=valuation**（皮壳/绍兴/头程=0）。规则见 `cost-engine-spec/32`。
- **别名登记**：FBA 3 个 Rosoon SKU 已写入 EN `customer_items.ref_code`；本地补丁
  `config/item_alias_overrides.csv`。美国销售尺寸 138 = EN 140。
- **大件云仓**：第三方大件（金属文件柜）显式零成本 `third_party_warehouse`，不按未登记阻断。
- **已用 EN 报表验证**（`BOM Cost List V2`，filters 见 `build-order-tabs.md`）：KS0050 六个尺寸
  `cost_fg=0 / cost_sxbzcp=0 / shipping_method=成品`，USNJ/USTX valuation 正确（5LB=35.4239/35.8839）。
  日报表带 `show_ref_code=1` 会按每个客户码重复行；本地导出用 `show_ref_code=0` 或按 `item_fg` 去重。
