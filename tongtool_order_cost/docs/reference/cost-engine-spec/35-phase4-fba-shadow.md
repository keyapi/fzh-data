---
okf: v0.1
type: Reference
title: Phase 4.FBA — FBA 桥接 + 78 列 FBA/合并 shadow（本地，不写 GS）
description: EN FBA 明细 exact 物料定位 + BOM 成品口径单位成本（含直采成品例外）、GS FBA 销量骨架、通途导出覆盖校验；别名解析桥接、未登记 SKU 白名单（Colab 名称解析候选 + 有无扣 superset 自动映射）、78 列 FBA/合并 shadow（唯一键/pending）、三方对账与重复检测
date: 2026-11-05
module: tongtool_order_cost
tags: [cost, fba, bridge, shadow, reconciliation, phase4]
---

# Phase 4.FBA

> 落地：`domain/fba_shadow.py`；CLI `fba-shadow`。**只生成 shadow 文件，不写 GS/EN。**

## 1. 数据与成本口径

- **EN FBA 明细**（`en_items_all_089.csv`，warehouse 含 FBA）定位 exact `erp_item_code`；
  **BOM Cost List**（`bom_cost_product_with_kits.csv`）出**成品口径单位成本**；
  **GS FBA 销量表**（`raw_fba_YYYYMM.csv`）为输出骨架/业务粒度；
  **通途 FBA 导出**（`fba_export_YYYYMM.csv`）做覆盖校验。
- 成本查找一律用 EN 明细的 **exact `erp_item_code`**（保留大小写，如 `...-110x81x25-...`）；
  `normalize_sku`（去空白 + 大写）**只用于 GS SKU → 别名解析/桥接**，禁止用于 BOM 查找。
- FBA 四列 = BOM 成品口径（`method=成品`；套件用 `kit_method` 展开子件）：
  - 皮壳成本 = `cost_fg`
  - 绍兴二次加工 = `sx_cost_all − cost_fg`
    - 默认必须 > 0，否则 pending `sx_zero`；
    - **直采成品例外**：`cost_fg == sx_cost_all` 且 `cost_sxbzcp == 0` → 允许绍兴二次 = 0，
      `bridge_reason = direct_purchase_zero`，计入可定价、不进 pending。
  - 二次加工 = FBA valuation = **0**
  - 头程 = 对应国家 FBA freight（US/CA→9rr7、欧洲→88h、UK→0hn、JP→3s2）
  - 1件成本 = 皮壳 + 绍兴二次 + 二次（不含头程）
- 断言：`皮壳 + 绍兴二次 + 二次 == 1件`（到 1e-6）；违例 → pending `cost_identity_broken`。
- 套件：`exact item ∈ product_bundles` 时先校验 `kit_method`（子件 method 全一致），
  再由 `_bundle_unit_costs` 求子件四列之和。

## 2. 桥接

- 键 = **月份 + 国家 + 归一化 SKU**（SKU 经 `Item.customer_code` 别名 → Item；不做全局 SKU join）。
  归一化只服务于别名解析；成本与 BOM 查找用组内 EN 明细的 exact 物料号。
- 同键多 GS 行（MSKU/账号）按 `qty` 分摊 EN 成本；EN 总成本守恒到组。
- 桥接表字段：month/country/canonical_sku/site/MSKU/SKU/qty/en_qty/en_rows/share/
  product_id/bundle_item/bundle_version/status/reason。
- **跨月桥接（Phase 4.FBA.h）**：同月无 EN FBA 行时，按产品在 **±1 个月窗口**找 EN FBA 行；
  按 GS 数量逐行分配（已消费行不重复计），定价仍用 BOM 成品口径，标
  `bridge_reason=cross_month_bridge`，并记录 `en_month` / `en_rows_used` / `en_qty_used`。
- **BOM 兜底**：仍无相邻 EN 行，但产品唯一（别名/唯一候选）且 BOM 存在 → 按 BOM 定价，
  标 `bridge_reason=gs_only_bom_fallback`，不静默；只有缺 BOM / 产品歧义 / 直采零异常才 pending。
- **跨月数量核对**：`fba_cross_month_<month>.csv` 记录每次借用的 EN 月、行数、数量与该 EN 组总量；
  成本 = BOM 单价 × GS 数量，不累加 EN 成本，Aug/Sep 不会双计（`qty_diff` 应 ≥ 0 覆盖）。
- **未登记 SKU 白名单**（Phase 4.FBA.2/4.FBA.3）：`en_item_missing` 的 GS 行落
  `fba_whitelist_<month>.csv` + 汇总模板 `out/fba_shadow/fba_whitelist_template.csv` + SKU 级
  `fba_whitelist_skus.csv`，字段 month/site/country/msku/sku/product_name/qty/en_rows/en_qty/
  en_item_status/candidate_count/candidate_items/candidate_basis/status/auto_pref/approved_*/note。
- **候选生成改用 Colab 商品名称解析思路**（`14-colab-key-derivation-chain.md` 4.2/4.7.2）：
  - 品类：EN `item_group` 去后缀得基名（三角靠枕/三角靠枕无扣→三角；平条靠枕→平条），
    长度优先匹配产品名；含「弧形」→ 弧形海绵/弧形PP棉，含「带圆柱」→ 对应基名；
  - 尺寸：去品类 → 清 `^数字.`/`; 数字.`/5 位以上数字 → 多段 `*|x|×` 取最大 → 首个数字（排除件套）；
    三角品类 138→140（Colab 同规则）；
  - 面料：BOM 物料名面料段词表（长度优先，**海绵排末位**）；
  - 有无扣：`(有扣|无扣)`，仅三角品类有效；
  - 再按 **EN Item（item_group + item_fg_name）** 过滤：品类 → 尺寸 → 面料，颜色做偏好，
    逐级放宽（尺寸未命中 → 面料未命中 → 仅品类）。
- **自动映射（用户口径）**：
  - `superset`：同一款只差「有无扣」时（候选里同时有 `无扣` 项与同后缀 `KS0001-` 项），
    自动取 **KS0001（更全）**，`auto_pref=superset`；
  - `single_candidate`：`candidate_count==1` 且 `candidate_basis` 含 **`尺寸+面料+颜色`**（强依据）→
    自动映射，`auto_pref=single_candidate`；尺寸/面料未命中的单一候选**不**自动映射；
  - 仅作用于 FBA 白名单/桥接，不改自发货；其余多候选仍 `needs_business_confirmation`。

## 3. 输出

`out/fba_shadow/<month>/`：
- `fba_shadow_<month>.csv`：78 列 FBA 写回 shadow + 血缘/桥接标注（fulfillment=FBA、source_key、business_key、unique_key、pending_flag、bridge_status/reason、gs_share、product/bundle、en_item_code、kit_method）。
- `merged_shadow_<month>.csv`：78 列合并 shadow（SELF + FBA），每行带 `fulfillment`、`source_key`、
  `unique_key`（行级唯一，重复源键追加 `#n`）、`pending_flag`、`business_key`、`duplicate_flag`。
- `fba_bridge_<month>.csv`、`fba_recon_<month>.csv`、`fba_pending_<month>.csv`、
  `fba_unmatched_en_<month>.csv`、`fba_whitelist_<month>.csv`、`fba_cross_month_<month>.csv`
- `fba_shadow_<month>.xlsx`（汇总/ FBA行/合并行/桥接/三方对账/待审/EN未匹配/对账Top/未登记SKU）与 `.md`
- `out/fba_shadow/fba_whitelist_template.csv`：跨月白名单模板（按月覆盖，保留其它月已登记）
- `out/fba_shadow/fba_whitelist_skus.csv`：SKU 级汇总（一行一个未登记 SKU，含月/站点/数量/候选）

## 4. 2026-11-05 结果（Phase 4.FBA.h，跨月桥接 + BOM 兜底）

| 指标 | 202608 | 202609 |
|---|---:|---:|
| FBA 行 / 可定价 / 待审 | 146 / 146 / 0 | 133 / 133 / 0 |
| 待审原因 | — | — |
| 跨月桥接（行 / 件） | 0 / 0 | 1 / 1（EN 202608） |
| BOM 兜底（行 / 件） | 0 / 0 | 0 / 0 |
| 直采成品绍兴二次=0 行 | 3（13 件） | 3（4 件） |
| 未登记白名单（全部 alias） | 22 SKU / 22 行 / 110 件 | 19 SKU / 19 行 / 82 件 |
| 合并行 / 唯一键 / 重复键 | 10,993 / 10,993 / 0 | 6,361 / 6,361 / 0 |
| 合并 pending 行 | 0 | 0 |
| 业务键重复行（FBA/自发货同键） | 0 | 0 |
| GS / EN / TT 数量 | 2,066 / 2,159 / 2,173 | 1,328 / 1,367 / 1,328 |
| priced 覆盖 GS 数量 | **100.00%** | **100.00%** |
| GS/EN 数量覆盖 | 95.7% | 97.1% |
| GS/TT 数量覆盖 | 95.1% | 100% |
| FBA 四列合计（皮壳 / 绍兴二次 / 二次 / 头程） | 79,755.82 / 76,707.28 / 0 / 70,291.65 | 52,818.95 / 52,426.99 / 0 / 48,745.45 |
| 绍兴二次非零行 / 恒等违例 | 143/146 · 0 | 130/133 · 0 |
| EN 未匹配组 | 6 | 4 |
| GS vs TT 成本差 / 头程差 | -9,597.42 / -3,314.50 | -60.90 / 0 |

**最后 1 件待审原因已闭环**：GS 202609 `BNUSFBA-Velvet-Blue-100` 按付款在 9 月，
EN FBA 明细在 2026-08（8/11 美国FBA），属跨月错位——现按 ±1 月窗口借用 202608 EN 行
（按 GS 1 件分配 1/40 行），标 `cross_month_bridge`，`qty_diff=0`；无 Aug/Sep 双计。
202608 待审与跨月桥接均为 0。

- `direct_purchase_zero`：`KS0523-KQCLXGBS-36x60x10-{BLUE,GREY,WHITE}` BOM 为直采成品
  （`method=成品`、`cost_fg = sx_cost_all = 48`、`cost_sxbzcp = 0`），允许绍兴二次=0 并定价。
- `no_en_fba_rows`：9 月 `BNUSFBA-Velvet-Blue-100`（1 件）GS 有销量但本月 EN FBA 无该物料行。
- BOM 命中：所有带单个 exact 码的物料 **100% 命中 BOM**（修复前大写化导致 12 个 `...x...` 物料误判缺行）。

## 5. 约束

- FBA 与自发货按 `business_key = month|MSKU|SKU` 检测同键重复；命中即 `duplicate_flag`，不直接 union。
- 合并行唯一性由 `unique_key` 保证（`merged_unique_key_dupes` 必须为 0）；pending 行 `pending_flag=True`。
- 缺失/歧义待审，不静默补值；白名单候选供业务确认；不写 GS/EN。
- 自动映射只用于 FBA 白名单/桥接：`superset`（同款仅差有无扣取 KS0001）与
  `single_candidate`（唯一候选且尺寸+面料+颜色强依据）两种，均标 `auto_pref`；
  **不改自发货**（SELF 行与合并逻辑不变）。
- `exact erp_item_code` 只做 strip/空值处理，**绝不 upper**；桥接归一化不得回流到 BOM 查找。
## 6. Canary run 包（Phase 4.FBA.c）

> 落地：`domain/fba_run_package.py`；CLI `fba-canary`。**绝不写 GS/EN，只生成本地 run 包。**

- **选桶**：按账号/站点（`site`）分组，排除待确认 SKU（默认 `OSKBG-RSUS-FBA`），
  取最小桶（行数 → 数量 → 站点名）；202608 选出 **AMZStruseryDE（1 行 / 3 件）**。
- **Canary CSV**：78 列 FBA 写回骨架 + `cost_status` / `auto_pref` / `bridge_status` /
  `bridge_reason` / `unique_key`；四列取 FBA shadow（成品口径、二次=0、头程=FBA 成品头程）。
- **旧值来源（已修正）**：**目标写回表 FBA 行**（`merged_<month>.csv`，`发货仓分类=FBA`），
  不再用通途 FBA 销量报表的聚合「成本/头程费用」；备份整行 + sha256。
- **写前 diff**：逐行比四列单件与金额、头程、1 件合计；差异标 `diff_reason=bom_version_change`，
  并对「旧写回绍兴侧在二次加工列」给 `caliber_note`。
- **manifest**：8 个输入（FBA shadow / GS FBA 订单 / EN 明细 / BOM / 套件 / item_refcode /
  白名单 / 旧写回表）hash、月末版本、263 个 bundle_version、白名单 sha。
- **写后回读（模拟）**：行数、键唯一、键 hash、四列金额、非目标列零变化、状态保留、
  待审成本留空、直采绍兴二次=0、行 hash、摘要 hash。
- **不可变目录**：`out/runs/fba-<month>-<bucket>-<ts>/`
  （manifest.json / audit.log / readback.json / diff.csv / summary.md / fba_canary_*.csv /
  old_values_*.csv）；非空目录拒绝覆盖，同输入指纹重复运行拒绝。
- **状态规则**：待审行保留 `cost_status=pending:<reason>`，成本列留空（不填 0、不沿用旧值）；
  直采成品保留 `direct_purchase_zero`（绍兴二次=0 来自 BOM，不是补 0）。

### 2026-11-05 结果（202608 / AMZStruseryDE）

| 指标 | 值 |
|---|---:|
| 桶 / 行数 / 数量 | AMZStruseryDE / 1 行 / 3 件 |
| 四列合计（皮壳 / 绍兴二次 / 二次 / 头程） | 72.183 / 62.8014 / 0 / 42.9 |
| 旧值（写回表 FBA 行） | 2 行；皮壳 69.024 / 绍兴侧 53.85 / 头程 42.9（金额） |
| 单件 diff（旧→新） | 皮壳 23.008→24.061（+1.053）；绍兴侧 17.95→20.9338（+2.9838）；头程 14.3→14.3 |
| 金额 diff（我方−旧） | 皮壳 +3.159；绍兴侧 +8.9514；二次 -53.85（归入绍兴侧）；头程 0；1件 +12.1104 |
| 重复键（unique / business） | 0 / 0 |
| 门禁 | 9/9 pass |
| 写后回读 | 10/10 pass |

**约束**：仍不写 GS/EN；run 包仅本地审计用；待审/直采行只保留状态，不补值。

## 7. Alias 归一化与登记 dry-run（Phase 4.FBA.d）

- **归一化**：`EnResolver` 的别名键改为 `normalize_alias` = 去空格/连字符/下划线 + 大写；
  `SUK-SJWKDM-grey 45cm`、`SUK-SJWKDM-GREY45CM`、`SUK-SJWKDM-GREY-45CM`、`SUK_SJWKDM_GREY45CM`
  均可命中 `KS0001-DM-45-GREY`。宽松归一化引入的歧义不猜（多产品仍判 ambiguous）。
- **自动解析优先级**：已登记别名（`auto_pref=alias`）> 有无扣 superset > 单一候选强依据。
  202608/202609 数据中没有「仅归一化差异」的 FBA SKU → alias 增量 **0**，覆盖不变（99.95%/99.77%）。
- **登记 dry-run**（`domain/alias_dryrun.py`；CLI `fba-alias-dryrun`，不写 EN/GS）：
  生成 `proposals_all.csv`（字段 action/sku/target_item/item_group/old_customer_code/
  new_customer_code/old_hash/new_hash/affected/note/status），另保留手动提案 `proposals.csv` 与
  分类 `classification.csv`。
  - **手动 4 项**：`OSKBG-RSUS-FBA` → `KS0423-XNEOSTH-153x65x23-OFFWHITE`（add_alias）；
    `SUK-SFZCD-black3pcs FBA` → 套件 `TJ#KS0156x3-001`（add_alias）；
    `FUDE-huxingdima-wh-200` → `KS0007-DM-200-IVORY` **两条**：`cost_borrow`（借成本建议）+
    `add_alias`（note=`cost_borrow_white→ivory`，供用户确认）。
  - **auto 30 项**：每个 auto_mapped SKU 都生成 add_alias 提案（target=approved_item_code）。
  - **状态**：目标 item 已在 item_refcode 且归一化后别名已存在 → `noop`；未命中 → `needs_review`；
    `cost_borrow` → `suggestion`。
  - 202608/202609 结果： **34 提案**（add_alias 33 + cost_borrow 1）；**noop 0 / needs_review 33**；
    30 个 auto SKU 全部真正缺登记（0 个仅归一化差异）。
