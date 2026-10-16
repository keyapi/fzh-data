---
okf: v0.1
type: Log
title: cost-engine-spec 变更日志
---
# 变更日志

## 2026-10-17
- **清重复键（第 2 批）**：逐条核 15 个重复键的 F 列 —— 14 个两行**同模板 ⇒ 无成本影响**（不动）；**1 个真错已修**：糖果床头靠枕 行 625/626 的 `EN重量模板物料号` **串了**（625→`…194x18x60`、626→`…153x18x60`，由 C 列尺寸+E 列键+EN 模板名互证）。回读 ✔。
- **回答「0364 是套装 / 0423 是组件？」**（[27](27-gsheet-source-root-cause.md) §3e）：EN BOM/Product Bundle 反查 ⇒ **两者是并列独立成品**（BOM 结构同＝皮壳+内胆），互不包含；成本差（皮壳 203 vs 119）来自 **皮壳复杂度**（KS0364 皮壳 7 件含镀金线饰边/草莓球 vs KS0423 3 件）。**不改回**，待业务口径为准。
- **实测**：7 月写回表里 **只有大靠背(KS0423/0424/0425)、没有床头靠枕(KS0364/0365/0366)订单** ⇒ §3 的「各归各码」对现有订单零影响。
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
