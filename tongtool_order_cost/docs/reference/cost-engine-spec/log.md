---
okf: v0.1
type: Log
title: cost-engine-spec 变更日志
---
# 变更日志

## 2026-10-17（A 收尾）
- **管理摘要**加「直连优先」覆盖行（`render_memo` 取 `b2_direct_coverage` 闸）。
- **[28](28-parse-vs-en-7to9.md) §1 更正**：「弧形海绵/PP棉 填充物判反」经查**不是判反**——同一 `…-Cover` 皮壳两种填充、平台SKU 明写 Foam/PPCotton、订单侧自洽；两填充二次加工确不同(49.45/31.95)。

## 2026-10-17（补）
- **新增 [30](30-design-merge-split-no-double-count.md)**：拆包裹合并 → 合成一件再对 BOM 的设计稿（落点/算法/断言/待拍板）。

## 2026-10-17
- **新增 [29](29-review-brief-for-codex.md)**：给 Codex 的评审包（6 条待证伪断言 + 未做项）。

## 2026-10-17
- **EN `ref_code` 定案 3 个样例 + 修 1 处 F**：用 EN `Item Customer Detail.ref_code`（**须经 SSH 查 DB**；REST 该字段 403）拿到通途SKU→EN 物料真值：
  - `TT0031054K0062974 → KS0174-WGMSR-45-BROWN`（中控台车载狗窝/无光磨砂绒）⇒ **皮壳表 行453 F 误抄四季款(KS0234) 已修** 为 `ZLMB#KS0174-WGMSR-45`；
  - `TT0312705K0064584 → KS0517-QDZZMMB-SET6-DEEPGREYMIX`（鹅卵石套装）⇒ **原「自洽、表没错」判断作废**，实为 **Colab 解析错 + 源表缺行**（品类使用面料/材料价格明细 缺 鹅卵石套装/全涤针织磨毛布）→ 待办加行；
  - `TT0312576K0064149/577/578 → KS0423/0424/0425-…-x23`（**大靠背＝部件**）⇒ 订单键对、§3 改法正确。
- **「整体 vs 部件」定案**：用户确认 `KS0364`=整体、`KS0423`=部件（EN 未建模）；7 月通途订单的 SKU + 产品名 + EN ref_code **三者一致 → 订单是「部件」** ⇒ 用 KS0423 模板正确，**不改回**。
- **清重复键（第 2 批）**：15 个重复键逐条核 F —— 14 个两行**同模板 ⇒ 无成本影响**（不动）；**1 真错已修**：糖果床头靠枕 行 625/626 F 串行（625→`…194x18x60`、626→`…153x18x60`）。回读 ✔。
- **回答「0364 是套装 / 0423 是组件？」**（[27](27-gsheet-source-root-cause.md) §3e）：EN BOM/Product Bundle 反查 ⇒ **两者是并列独立成品**（EN 未建模其包含关系）；成本差来自 **皮壳复杂度**（KS0364 皮壳 7 件含镀金线饰边/草莓球 vs KS0423 3 件）。
- **执行 gsheet 源头修正（经用户授权，按 EN 为准）**：`财务部绍兴成本核算表单2023` ——
  - `品类使用面料` 行 246/247/248（欧式床头靠枕-蓝/米白/腰果花滚边吊穗款）品类编码 `KS0425/0423/0424` → **`KS0366/0364/0365`**（EN 真码）；
  - `皮壳成本平均202409-202410-202411（用于通途订单202502）` 行 634-639 的 D/E 同步拆回各自码（`YHX-HS-002/003-*` 与 `KS0423-*` → `KS0364/0365/0366-*`）；
  - 两表各加「备注」列记录；改动前备份 + 逐格核对现值 + 回读验证（15 格全 ✔）。**修后 KS0423/0424/0425 不再与床头靠枕撞码。**
- **新增 [27-gsheet-source-root-cause.md](27-gsheet-source-root-cause.md)**：对 3 个「值不一样 / 键撞车」样例做源头根因定位，**更正 [26](26-answers-to-28-rows.md) §6**：
  - **链路钉死**：`import皮壳成本` 的 A/B 两列是 `=IMPORTRANGE(财务部绍兴成本核算表单2023, "皮壳成本平均202409-202410-202411（用于通途订单202502）!E:F")` ⇒ **改 `import皮壳成本` 无效**；Colab `cell_036` 读的是 `皮壳成本平均…`，`SX合并EN成本` 是写回产物。
  - **三例都不是 Colab 解析错**：①`TT0312576K0064149`（键 `KS0423-153-XNEOSTH`）= **键撞车**；②`TT0031054K0062974`（键 `RD-YM-pet-006-45-WGMSR`）= **表里 F 列跨产品**；③`TT0312705K0064584`（键 `SX-STH-SET6-YLR`）**自洽无误**。
  - **KS0423 是新款（用户之问）**：EN 建组 0364=2024-10-26、0423=2025-03-17（多 23 深度），两者成本都齐全 ⇒ 是两件合法产品，不可合并。
  - **剩余 15 个重复键**（同业待办）+ Colab `drop_duplicates('品类尺寸面料编码')` 取首行的整改建议。
  - 更正 [26](26-answers-to-28-rows.md) §2：7 月写回表实测 `TT0312705K0064584` 的 `二次加工成本=0`（非 101.07）。

## 2026-10-16
- **新增 [14-colab-key-derivation-chain.md](14-colab-key-derivation-chain.md)**：把老引擎主键 `品类尺寸面料编码` 的三段推导逐段落实一手证据：
  - **品类编码** ← GS `品类使用面料`（品类→品类编码）+ `产品用料工时明细.品类尺寸编码` 前 2 段（cell_009 L54）；订单侧靠 `df_fab_cat_alt_name`（`品类别名` 桥，cell_032）查表（cell_066 L1549）。附 cell_003 的「品类编码要求不重复」原始注释与 `品类使用面料` 表结构。
  - **尺寸** ← 两条路径 **4.2(cell_066) / 4.7.2(cell_141)**，逐字同一逻辑（注释「20230105 统一 4.2 4.7.2」×8；cell_141 L482 复用 4.2 的面料词表）；**不从 GS 取**，靠产品名称正则 + 特例改写。
  - **面料** ← GS `材料价格明细`（材料名称→材料编码，**只取 `材料类别=='面料'`**）；BOM 侧 cell_018/020、订单侧 cell_066 L1536-1542；候选词表 = 硬编码白名单 ∪ 表内面料名 ∪ 李惠表。
  - **海绵(HM) 三层特例**：品类层（弧形+海绵→弧形海绵，cell_066 L461-495）· 面料提取层（`海绵` 强制排候选末位，L624-628）· 物料层（`面料/海绵→ML-HM`，键尾缀 `-HM`）；并说明与旧键 `HM` 的语义关系。
- **就地返工 [colab-engine-cell-by-cell.md](colab-engine-cell-by-cell.md)**（保留头部「已知错误」警示，正文按 [13](13-codex-review-corrections.md) §6 改正 4 处）：
  - 补 `cell_047`（头程 melt → ws `EN头程运费`）与 `cell_049`（`df_final` 构造 + `fill_shipping_cost` 字面 1:2:4 + `select_by_sx_delivery` 是 `绍兴发货方式` 真实消费点）；§C 表与证据清单同步增行。
  - 改回 **`045`=19 列 / `096`=6 列**（原文写反），并说明两格都重绑 `df_en_zlmb`、`096` 后执行故 cell_100 用 6 列版；`has_sx_delivery` 分支归 `045`（非 096）。
  - 更正「无字面倍数运算」的错判（1:2:4 在 cell_049）；更正「绍兴发货方式无消费者」「df_final/尾缀来源未证实」两条。
  - §8 第 17 条按现状更新 `eval_delivery_en`（10/10 备份无 → 当前 10/14 notebook `cell_036` L158 `=True`；**保存≠已运行**）。
- **新增 [15-exception-rows-monthly-impact.md](15-exception-rows-monthly-impact.md)**：把 Codex 认定的「7 月 51 行需专门处理」与 `import皮壳成本` 的 161 个空重量模板键，按 2026 年 7/8/9 月美中（USTX）订单实测命中面：
  - 空键命中行/美中总行：**7 月 41/4379（0.94%）· 8 月 36/5479（0.66%）· 9 月 21/2959（0.71%）**；161 空键本季仅 **17 个**被真正用到。
  - Codex 4 类分月：白名单 3/6/36、源映射空 41/36/21、五件套 4/5/0、双模板冲突 3/1/2 → **51/48/61**（非 7 月独有）。
  - 逐月**新增空键**：8 月 6 个、9 月再增 1 个（累计 7 个）→ 断链在扩大。
  - 机器可读：`tongtool_order_cost/out/ustx_wage_sim/exception_month_impact.csv`（gitignore）。
- **修正 [09](09-known-issues-register.md) C1/C3/C5/C6**：按 Codex 4 类分法精确化（C5 冲突键 3 个→3 键/7月3行；C6 字面 0 与空键区分；C1/C3 标注为**不同缺口**）。
- **修正 [11](11-plan-new-ustx-processing-table.md) §3.3**：作废「A/A1/B/C + B 组 10 键」粗分类，改为 Codex 4 类（白名单/源映射空/五件套/双模板冲突）；§3.3b 新增双模板冲突专项；§3.1b 空键数 160→**161**；R5/S2/§3.4 同步改写。

## 2026-10-15
- **bundle 首次成型**：把散落在 Colab/SHEET/EN 三侧的「成本口径」逆向结果，收拢为**单一事实源**（入口 [01-overview-and-glossary.md](01-overview-and-glossary.md)）。本次补全 4 个缺失页 + 索引 + 本日志：
  - [01-overview-and-glossary.md](01-overview-and-glossary.md) —— 入口：系统上下文、范围/非目标、**数据时点**（快照 09-03 / 线上 10-15 / 剔除额 10-10）、实体与编码速查、用户惯用语对照、18 项「疑问→答案」总表。
  - [02-keys-and-entities.md](02-keys-and-entities.md) —— **键与实体**：三套键（`品类尺寸面料编码` = `品类尺寸编码 + "-" + 材料编码.replace("ML-","")`；`品类尺寸编码` = `品类编码 + "-" + 尺寸`；EN 等价键 `重量模板编号`→并入订单改名 `EN重量模板物料号`）、前缀实体（`PK#`/`SXBZBCP#`/`SXBZCP#`/`USNJBZCP#`/`USTXBZCP#`/`PLBZCP#`/`ZLMB#`/`ML-`）、分流字段（`custom_shipment_type_to_branch` 等，401 组分布 成品165/皮壳156/半成品62/空18）、**6 列去重键**（`运营人员+发货区域+通途SKU+渠道账号不含国家+渠道账号+发货仓按销售汇总分类`）、键的坑（同键歧义 7 月 3 个 / 空键 75 行 / 命名不一致 `ZLMB#KS0383-HLR- 140*50*24`）。
  - [03-data-sources.md](03-data-sources.md) —— **数据源清单**：GS 侧 5 个工作簿（`通途订单202607`/`和财务部共享`/`二次加工成本2022`/`财务部绍兴成本核算表单2023`/`头程运费成本`）逐 ws 的生成者·消费者·行数；EN 侧报表（BOM Cost List V1/V2 等）、Doctype（BOM/Item/Item Group/Workstation/Tongtu Shipping Warehouse/Tongtool Settings）、app（`work_order_task`/`key_test`/`tongtool_integration`/`delivery_plan`/`vilavi_pim`）；缺口指向 [../old-system-source-coverage-audit.md](../old-system-source-coverage-audit.md)。
  - [04-cost-decision-tables.md](04-cost-decision-tables.md) —— **核心决策表**：按 目的地 × 绍兴发货方式 的 皮壳/头程/目的地加工/绍兴侧加成 取值链；A/B1/B2/B3 四方案对照（7 月 ￥加权 526,225 / 752,854 / 791,137 / 717,678）；头程专项（A=B2 Δ=0）、二次加工专项（+225,982，占 85%）。
  - [colab-engine-cell-by-cell.md](colab-engine-cell-by-cell.md) —— 老引擎逐 cell 逆向（224 cell）：全流程骨架、每列取值链、13 开关、硬编码与清零/占位规则、已知坑。
  - [deduction-and-sxbzcp-adjustments.md](deduction-and-sxbzcp-adjustments.md) —— **剔除额**完整定义（`get_sxbzbcp_deduction` 只减不加）、受影响列、非 FBA 半成品发货成本**不受影响**、Jack commit `533ecad`/`cf0bbbd`(2026-10-10)、09-03 快照证实未扣。
  - [en-branching-and-warehouse-config.md](en-branching-and-warehouse-config.md) —— EN **39 个分流点**穷举（9 文件，路径:行号）+ `Tongtu Shipping Warehouse` **40 行**配置（FBA 19 行 `processing_cost_name` 全空，美国海外仓 2 行非空）+ 目的地加工成本/头程三列取值链。
  - [07-colab-vs-en.md](07-colab-vs-en.md) —— **替换进度表**：4 个 BOM 类成本列里 2 个已 EN（皮壳 Δ=0、头程 Δ=0）、2 个仍借用（二次加工 +225,982、绍兴二次加工 +38,930）。
  - [08-special-cases.md](08-special-cases.md) —— **特例**：`-COVER`/`-PPCOTTON`/`-FOAM`（含数字后缀 `-COVER1`/`-FOAM1`）、自采购、拆单多包裹系数、Product Bundle、FBA 强制清零、是否需尾程、`HEAD-SX→0`、品类白名单清零、灰区 `fillna(0)`（`大件云仓`/`主体骨架 沙发L形支架`）、`0.001` 占位（`注意-清零PL二次加工成本`）、星链海外仓→DANEEY 替换。
  - [09-known-issues-register.md](09-known-issues-register.md) —— **问题登记册**：A（EN 内部不一致 7 项）/B（时序错配 3 项）/C（数据缺口与脏数据 9 项）/D（命名坑 6 项）/E（待证实 8 项）。**全 bundle 的「未证实」均指向此页**。
  - [10-glossary.md](10-glossary.md) —— **术语表（字段级）**：实体与编码（前缀/成本来源编码/头程编码/SKU 后缀）与 字段与列名（EN 字段/GS 列名/Colab 开关/报表列）两张速查表。

> **时点声明**：本 bundle 的「线上事实」以 **2026-10-15** 为观测点；GS 快照另有明确时点（见 [01](01-overview-and-glossary.md) §4）。跨时点结论一律先声明时点。


## 2026-11-04
- **[32-phase2-bom-cost-policy.md](32-phase2-bom-cost-policy.md)**：Phase 2 成本快照与变体锁定策略定案。
  - BOM 快照切到 `out/bom_cost_product_with_disabled.csv`（2358 行，含 disabled=1）：历史订单引用停用物料，不再误判 `bom_item_missing`（33/33 缺行 item_fg 均为 disabled）。
  - 合并组统一用 Phase1 carrier_sku + product_id；透传通用组件（CURVE-PILLOW-*-PPCOTTON/-FOAM）用同订单 Cover/成品行锚定变体，唯一才用，否则阻断。
  - EN BOM 独立重算 71/71 通过；valuation_rate = BZCP BOM `total_cost`，与 method 无关；method_diff 按 EN method 放行并输出审计差（两月合计 2,290.59）。
  - 重跑：202608 可定价 10,689 / 阻断 3；202609 6,061 / 1；`bom_item_missing` 清零，剩余均为 `bom_item_ambiguous`（真正无法锁定变体）。

## 2026-11-04（Phase 3.0）
- **[33-phase3-writeback-rehearsal.md](33-phase3-writeback-rehearsal.md)**：本地写回演练落地。
  - 166 列合同模板 + Phase1 合并明细行集合 + Phase2 四列（合计）；阻断/跳过四列留空写 reason，不沿用旧值/不填 0。
  - 缺列按 `(order_common,平台SKU)`（透传优先精确 `订单号+通途SKU`）从旧写回映射；冲突/无来源留空并写 `unmapped_columns`。
  - 血缘 100% 通过；差异归因按 列×method×合并/透传×disabled×status 输出。
  - 演练：202608 10,854 行 / 可定价 10,689 / 阻断 3；202609 6,230 / 6,061 / 1；四列合计 2,228,516.09 / 1,362,992.16。

## 2026-11-04（Phase 3.1）
- **[33-phase3-writeback-rehearsal.md](33-phase3-writeback-rehearsal.md)** 修正：四列改为**单位成本**（合并行=Phase2 合计/pieces，透传=合计/qty），并补齐 `*数量`、`1件产品成本`、`产品成本*数量` 与按输入可得的 `订单总成本/订单利润`；缺列一律优先按 `(order_common,平台SKU)` 映射。
- 新增断言：`per_unit×数量=Phase2 合计`、`1件成本=四列(除头程)之和`；两月单位成本恒等失败 0 行。
- 重跑：202608 10,854 行 / 可定价 10,689 / 阻断 3；202609 6,230 / 6,061 / 1。订单总成本/利润因 `运费` 未映射分别留空 76/39 行（已写 reason）。

## 2026-11-04（Phase 3.2）
- **[33-phase3-writeback-rehearsal.md](33-phase3-writeback-rehearsal.md)** 补齐关键未映射列：是否皮壳全表非空（皮壳/否）、运费原始包裹总运费兜底、同组源行聚合、suffix/件套/产品发售日期等映射与产品级兜底；`未映射对比`/`映射缺口` sheet；新增关键列非空率、派生列可算率断言。
- 结果：是否皮壳/运费空白 0；订单总成本/利润空白降至 165/169（仅阻断/跳过）；单位成本恒等失败 0；四列合计不变。

## 2026-11-05（Phase 3.3）
- **[33-phase3-writeback-rehearsal.md](33-phase3-writeback-rehearsal.md)**：清跳过/阻断。
  - method 兜底：EN shipping_method 空 → item_group_branch（branch 空向上找祖先），标 item_group_fallback；铁架 TT0312701K0064561 96 行 → 成品。
  - alias 刷新：TT0312687K0064377-COVER/-FOAM → KS0495…（白日梦躺椅）；TT0312614K0064240 → KS0455…。
  - 非商品配件（BUTTONKIT/PP*LB/DLZYFX001/COTTON-EU）四列显式 0；TJ# 套件未展开 → pending_bundle；歧义/多载体输出建议白名单。
  - 结果：202608 可定价 10,819 / 阻断 3 / 跳过 6 / 0成本 14 / 待审 5；202609 6,184 / 1 / 4 / 39 / 0。单位成本恒等失败 0。

## 2026-11-05（Phase 3.4）
- **[33-phase3-writeback-rehearsal.md](33-phase3-writeback-rehearsal.md)**：最后清理剩余 19 行。
  - `TT0031186K0063918-COVER` 用同订单 FOAM/PPCotton 锁定产品线（KS0342/KS0340 变体）。
  - 同产品多颜色整件/皮壳 → `split_products` 逐件计价（YUS 4 行、OSFD 3 行）；通用内胆按 1:1 数量吸收为零成本。
  - TJ# 套件用 EN Product Bundle 展开（5 子件）按子件 BOM 成本求和。
  - 结果：两月 blocked/skipped/pending 均 **0**；可定价 10,830 / 6,188；四列合计 2,252,841.53 / 1,374,012.26；单位成本恒等失败 0。

## 2026-11-05（Phase 3.5）
- **[33-phase3-writeback-rehearsal.md](33-phase3-writeback-rehearsal.md)**：套件分支固化。
  - `product_bundles.csv` 增加 bundle creation/modified + 子件 hash → `bundle_version`。
  - `kit_method`：子件 method 全一致才取；混合/空/缺版本 → pending。
  - 子件求和计价（不新增列），并与 `bom_cost_product_with_kits.csv` 套件行逐项对账（>0.01 阻断）。
  - 同订单 TJ# + 子件行 → `kit_child_double_count` 阻断。
  - 202608：套件 priced 5 / pending 0，kit_method 成品 5，对账差 0，双计 0；202609 无套件订单。四列合计不变（2,252,841.53 / 1,374,012.26）。

## 2026-11-05（Phase 4.0）
- **[34-phase4-run-package-canary.md](34-phase4-run-package-canary.md)**：生产写回演练（run 包 + canary，不写 GS）。
  - 输入 manifest/hash + 月末版本 + bundle_version；不可变 `out/runs/<run_id>/`（manifest/audit/summary/diff/readback）。
  - 门禁：版本锁、非空 run 拒绝覆盖、重复 fingerprint 检测；写后回读 6/6 通过。
  - 202608 + USNJ（4,138 行）canary；四列 242,735.26 / 30,363.86 / 748,411.06 / 801.05；非商品配件 7 行四列 0；利润空白 7 行只写 reason。

## 2026-11-05（Phase 4.1）
- **[34-phase4-run-package-canary.md](34-phase4-run-package-canary.md)**：canary 差异行级解释。
  - `diff_explain.xlsx/md` 入 run 包；按 item_fg + 原因分类（旧写回陈旧/BOM 月末版本/method 兜底/disabled/变体/包装口径）。
  - 覆盖率 100%，未解释 0；随机 10 行 BOM 手算 40/40 通过。
  - 皮壳 -40,674.69：旧写回陈旧 50.0% + BOM 月末版本 48.7% + 包装口径 1.0% + method 兜底 0.2%；成品 +4,131.25 主要是铁架 method 兜底（+4,128）。
  - 写前要求（覆盖率≥95%）已满足，仍未写 GS。

## 2026-11-05（Phase 4.FBA）
- **[35-phase4-fba-shadow.md](35-phase4-fba-shadow.md)**：FBA 桥接与 78 列 shadow。
  - EN FBA 明细为成本源；GS FBA 销量表作骨架；通途 FBA 导出做覆盖。
  - 月份+国家+归一化 SKU 桥接；同键多 MSKU 按 qty 分摊；套件头程走子件 FBA freight。
  - 202608：FBA 146 行（priced 106 / pending 40），合并 10,993，重复 0；GS/EN/TT 2,066/2,159/2,173；四列 72,333.89/62,936.80/91,312.54/0。
  - 202609：FBA 133（98/35），合并 6,361，重复 0；1,328/1,367/1,328；四列 45,310.29/44,974.45/66,236.64/0。
  - 待审主要为旧 FBA SKU 未登记（EN erp_item_code=NULL、成本 0）与 BOM 缺行；未静默补值。

## 2026-11-05（Phase 4.FBA 修复）
- **[35-phase4-fba-shadow.md](35-phase4-fba-shadow.md)**：两处口径/查找 bug 修复 + 重跑。
  - 绍兴二次不再硬编码 0：FBA 行统一按 **BOM 成品口径**（`method=成品`；套件用 `kit_method`）——
    皮壳=`cost_fg`、绍兴二次=`sx_cost_all−cost_fg`、二次加工=FBA valuation=0、头程=对应 FBA freight；
    `1件 = 皮壳+绍兴二次+二次` 恒等断言，绍兴二次 ≤0 → pending `sx_zero`。
  - BOM 查找改用 EN 明细 **exact `erp_item_code`**（大小写敏感，`...x...` 不再被大写化）；归一化只用于别名解析。
  - 202608：114/146 可定价，priced 覆盖 GS 90.7%，绍兴二次 69,837.29，重复 0，断言违例 0。
  - 202609：103/133，91.5%，48,319.45，重复 0，违例 0。
  - 覆盖率天花板 91.3%/91.8%：33 个未登记旧 FBA SKU（287 件）EN erp_item_code=NULL，需业务登记别名才能上 98%。

## 2026-11-05（Phase 4.FBA.2）
- **[35-phase4-fba-shadow.md](35-phase4-fba-shadow.md)**：白名单 + 直采成品例外 + 合并键。
  - 新增 `fba_whitelist_<month>.csv` 与跨月 `out/fba_shadow/fba_whitelist_template.csv`：
    month/site/MSKU/SKU/产品名/数量/EN 行状态/候选物料/审批位；候选按尺寸+面料+颜色+有无扣
    从 BOM 物料名生成，逐级放宽；**只建议不映射**（55 行全部有候选）。
  - 直采成品（`cost_fg==sx_cost_all` 且 `cost_sxbzcp==0`）允许绍兴二次=0，`reason=direct_purchase_zero`，不计 pending。
  - 合并 shadow 每行补 `unique_key`（重复源键追加 `#n`）、`pending_flag`，保留 fulfillment/business_key/duplicate_flag。
  - 202608：可定价 117 / 待审 29（全部 en_item_missing，179 件），priced 覆盖 GS 91.3%，绍兴二次 69,837.29；
    202609：106 / 27（108 件 en_item_missing + 1 件 no_en），91.8%，48,319.45。
  - 直采 0 行 3+3；合并唯一键 10,993/6,361 无重复；业务键重复 0；恒等违例 0。
  - 91.3%/91.8% 为 exact 物料口径天花板；上 98% 需业务按白名单登记别名。

## 2026-11-05（Phase 4.FBA.3）
- **[35-phase4-fba-shadow.md](35-phase4-fba-shadow.md)**：候选改用 Colab 名称解析 + 有无扣 superset 自动映射。
  - 产品名称解析（4.2/4.7.2 思路）：品类（EN item_group 基名，长名优先 + 弧形/带圆柱改写）→ 尺寸
    （去品类/清噪声/多段取大/排除件套，三角 138→140）→ 面料（BOM 面料词表，海绵末位）→ 有无扣（仅三角）。
  - 再按 EN Item（item_group 基名 + item_fg_name）匹配；颜色做偏好；逐级放宽。
  - 同一款只差有无扣（同后缀存在无扣项与 KS0001）→ 自动映射 KS0001，`auto_pref=superset`，仅 FBA。
  - 202608：priced 124 / 待审 22，覆盖 **91.3%→94.2%**，自动映射 7 SKU，绍兴二次 71,903.76。
  - 202609：114 / 19，**91.8%→95.0%**，自动 8 SKU，49,744.89。
  - 跨月自动映射 8 SKU / 仍待确认 25 SKU；合并唯一键/重复不变（SELF 不改）。

## 2026-11-05（Phase 4.FBA.4）
- **[35-phase4-fba-shadow.md](35-phase4-fba-shadow.md)**：单一候选强依据自动映射（`single_candidate`）。
  - 规则：`candidate_count==1` 且 `candidate_basis` 含「尺寸+面料+颜色」→ 自动映射，`auto_pref=single_candidate`；
    尺寸/面料未命中的单一候选不自动；`superset` 规则保留；多候选仍待确认。
  - 202608：priced 145/146，覆盖 **94.2%→99.95%**，自动映射 28 SKU（superset 7 + single 21），绍兴二次 76,646.88。
  - 202609：130/133，**95.0%→99.77%**，自动 24 SKU（superset 8 + single 16），52,232.10。
  - 跨月自动 30 SKU；仍待确认 3 SKU（FUDE-huxingdima-wh-200 8 候选、SUK-SFZCD 2 候选、OSKBG 弱依据）
    + 9 月 1 件 no_en。合并唯一键/重复不变，SELF 不改。

## 2026-11-05（Phase 4.FBA.c）
- **[35-phase4-fba-shadow.md](35-phase4-fba-shadow.md)**：FBA canary run 包（本地，不写 GS）。
  - `domain/fba_run_package.py` + CLI `fba-canary`：按站点选最小桶、排除待确认 SKU、78 列骨架 + 状态列。
  - 写前旧值备份 + hash、7 输入 manifest（含 263 bundle_version 与白名单 sha）、diff；写后 10 项回读模拟。
  - 202608 / AMZStruseryDE：1 行 / 3 件；四列 72.183 / 62.8014 / 0 / 42.9；diff 成本 +12.4944、头程 -43.35；
    门禁 8/8、回读 10/10；重复键 0。run 包 `out/runs/fba-202608-AMZStruseryDE-<ts>/`。
  - 待审行留空不补 0、直采行保留 `direct_purchase_zero` 状态；仍不写 GS/EN。

## 2026-11-05（Phase 4.FBA.d）
- **[35-phase4-fba-shadow.md](35-phase4-fba-shadow.md)**：canary 旧值来源修正 + alias 归一化 + 登记 dry-run。
  - canary 旧值改为目标写回表 FBA 行（`merged_202608.csv`），diff 重算：单件 皮壳 23.008→24.061、
    绍兴侧 17.95→20.9338、头程 14.3 不变；金额 +3.159 / +8.9514 / 0 / 1件 +12.1104；门禁 9/9、回读 10/10。
  - `EnResolver` 别名键改为去空格/连字符/下划线 + 大写；样例 SKU 四种写法均命中 KS0001-DM-45-GREY；
    FBA 数据无仅归一化差异项 → 自动解析增量 0，覆盖 99.95%/99.77% 不变。
  - 新增 `alias_dryrun`（CLI `fba-alias-dryrun`，不写 EN）：3 项提案（2 add_alias + 1 cost_borrow），
    old/new customer_code + hash + 影响 1/1/1；30 个 auto SKU 全部真正缺登记。

## 2026-11-05（Phase 4.FBA.e）
- **[35-phase4-fba-shadow.md](35-phase4-fba-shadow.md)**：alias dry-run 扩展到全部 auto SKU。
  - 30 个 auto_mapped SKU 各生成 add_alias 提案；目标 item 已登记且归一化后别名存在 → `noop`，否则 `needs_review`。
  - FUDE-huxingdima-wh-200 增加 add_alias → KS0007-DM-200-IVORY（note=cost_borrow_white→ivory），与 cost_borrow 并列。
  - 输出 `proposals_all.csv`（34 行：add_alias 33 + cost_borrow 1；noop 0 / needs_review 33）。
  - 仍不写 EN/GS；item_group 优先取 item_refcode，缺失时回退 BOM item_fg_name 前缀。

## 2026-11-05（Phase 4.FBA.f）
- **[35-phase4-fba-shadow.md](35-phase4-fba-shadow.md)**：EN 别名登记后重跑（item_refcode 刷新）。
  - 202608：priced 145/146，覆盖 99.95%，待审 1（OSKBG），重复 0；白名单 22 SKU（alias 16 + single 5）。
  - 202609：131/133，覆盖 99.85%（+0.08pp），待审 2（SUK + no_en），重复 0；白名单 19 SKU（alias 14 + single 4）。
  - 33 个提案 SKU 中 26 个已可别名直读；5 个仍单一候选（目标物料别名未出现在导出）、2 个仍待审。

## 2026-11-05（Phase 4.FBA.g）
- **[35-phase4-fba-shadow.md](35-phase4-fba-shadow.md)**：item_refcode 扩到 2621 物料后重跑。
  - 33 个曾提案 SKU 全部别名直读；202608 priced 146/146（**100.00%**）、待审 0；202609 132/133（**99.92%**），
    仅剩 1 件 `no_en_fba_rows`；重复 0，恒等违例 0。
  - 白名单 22/19 SKU 全部 `auto_pref=alias`；四列合计 79,755.82/76,707.28/0/70,291.65 与
    52,785.94/52,395.90/0/48,715.70。
  - `fba_pending_*.csv` 空结果也写表头（0 行时下游可读）。

## 2026-11-05（Phase 4.FBA.h）
- **[35-phase4-fba-shadow.md](35-phase4-fba-shadow.md)**：跨月桥接 + BOM 兜底，待审归零。
  - 同月无 EN FBA 行 → ±1 月窗口按产品借行（按 GS 数量逐行分配，标 cross_month_bridge）；
    仍无 → 产品唯一且 BOM 存在则 BOM 定价（gs_only_bom_fallback）；仅缺 BOM/歧义才 pending。
  - 跨月核对输出 `fba_cross_month_<month>.csv`；成本=BOM 单价×GS 数量，不累加 EN 成本，避免双计。
  - 202608：146/146（100.00%），待审 0；202609：133/133（100.00%），跨月 1 行/1 件
    （BNUSFBA-Velvet-Blue-100 → EN 202608，1/40 行，qty_diff 0）；重复 0、恒等违例 0。

## 2026-11-05（全链路重跑，ref 源改为 Item Customer Detail.ref_code）
- `item_refcode.csv` 由子表 `Item Customer Detail.ref_code` 重建（2,621 物料）；不再用 `Item.customer_code` 文本。
- Phase1（merge-shadow）：202608 输入 10,912 → 明细 10,850，可定价 10,822，阻断 28
  （未登记 14 / method 缺失 5 / 别名歧义 9）；202609 6,268 → 6,235，可定价 6,187，阻断 48
  （未登记 39 / 别名歧义 9）。合并组 60 / 31，阻断组 0，断言全通过。
  - 新 ref 下 `-COVER` 别名同时命中 KS0340/KS0342（PPCotton/Foam），歧义行 9/9，按规则阻断不猜。
- Phase2：202608 priced 10,824 / blocked 3 / skipped 3；202609 6,185 / 2 / 3；
  套件 priced 5（202608），双计 0；四列合计 2,252,197.38 / 1,373,391.01。
- Phase3：202608 10,824 / 3 / 3（blank 6，zero 14，absorbed 6）；202609 6,185 / 2 / 3（blank 5，zero 39，absorbed 6）；
  8 项断言全 pass；四列合计 571,217.37/122,649.05/1,492,211.94/66,119.00 与 352,415.42/88,371.07/884,244.46/48,360.05。
- FBA shadow：202608 146/146（100.00%），待审 0；202609 133/133（100.00%），跨月 1 行/1 件；重复 0。
- 合并 shadow：10,996 / 6,368 行，唯一键无重复，pending 0。

## 2026-11-05（Phase1 同订单锚定：CURVE-PILLOW Cover 歧义）
- `split_merge`：`-COVER` 歧义行按同订单组件行锚定（`Curve-Pillow-50-PPCotton`→KS0340、
  `Curve-Pillow-50-Foam`→KS0342）；两线并存时按平台 SKU 材质词/颜色词；仍不唯一才阻断。
- 合并组 Cover 与填充行 method 不一致时以非 Cover 行为准（非 Cover 仍不一致才 `mixed_methods`）。
- 结果：202608 锚定 9 行（same_order 8 + color 1），歧义 0，Phase2/3 blocked/skipped **0/0**、
  空白 0（非商品配件 14 行零成本）；Phase3 四列 571,328.45/122,724.61/1,492,469.22/66,067.61。
  202609 锚定 8 行，剩 1 行（仅 Cover、无材质/颜色信号）阻断；四列 352,499.24/88,507.41/884,244.46/48,508.23。
- FBA 100%/100%（146/146、133/133），合并 10,987/6,359，唯一键无重复，pending 0。

## 2026-11-05（Phase 3.6 成本+系数块补全）
- 新增 `domain/phase36_fill.py` + CLI `fill-tables`：self 166 / FBA 95 / merged 78 三表补全成本与系数块。
- 公式按 colab cell_125/168/169；系数从旧写回按行/crosswalk 继承，合并组取载体、冲突阻断；0/空/1 语义保留。
- 202608：10,870/1,966/12,836 行；成本填充 99.88/100/99.90%，系数 99.81/100/99.84%；空白 13；违例 0。
- 202609：6,246/1,269/7,515 行；成本 99.84/100/99.87%，系数 99.59/100/99.66%；空白 10（含 1 行 Phase3 skipped）；违例 0。

## 2026-11-05（Phase 3.7 作废原单 + 95↔78 + GS-ready）
- `fill-tables` 扩展：作废原单（invalid=1 且 crosswalk_missing）保留行/销售，成本与系数轨清空，
  标 `invalid_original`，旧值入 `invalid_original_backup.csv`，不写 0。
- 95↔78 按 SKU/数量/销售额/四列/系数/派生聚合对账（`recon_95_78*.csv`），FBA/非FBA 重叠检查
  （`overlap_self_fba.csv`）。两月均 **0 差异 / 0 重叠**。
- `gs_ready/` 输出严格 166/95/78 列；审计版（+2 列）保留顶层。
- 202608：作废 11、其他缺失 2；GS-ready 10,870/1,966/12,836。
  202609：作废 9、skipped 1；GS-ready 6,246/1,269/7,515。恒等违例 0。

## 2026-11-06（EN 行级身份 + 单品后缀）
- 新增 [38](38-en-line-identity-and-single-item-suffix.md)：EN 订单行 `erp_item_code` 作行级身份；
  单独卖 `-COVER`/`-FOAM`/`-PPCOTTON` 按 `order_sync.py:2941-3003` 计价；拆单组内 Cover 让位填充行；
  非 FBA 生效、FBA 绕过、合并组不套后缀。
- 修正 202608 self/merged（订单总成本 −18,040.63，110 行）；202609 唯一 Cover 歧义单改为皮壳计价。
