---
okf: v0.1
type: Reference
title: EN 成本引擎「分流点」穷举 + Tongtu Shipping Warehouse 仓库配置规格
description: 逆向 ERPNext 生产库里所有按「发货方式 / 目的地 / 仓库分类」分流的成本计算代码点（路径:行号 + 判据 + 分支差值），逐条列出 Tongtu Shipping Warehouse 40 行配置（含 FBA/海外仓 processing_cost_name 是否为空），以及目的地加工成本与头程三列的取值链
date: 2026-10-15
module: tongtool_order_cost
tags: [cost, branching, warehouse-config, erpnext, bom, first-leg, reference, read-only]
---

# EN 成本引擎「分流点」穷举 + Tongtu Shipping Warehouse 仓库配置规格

> 数据口径：ERPNext **生产库**（`erpnext.vilavi.cn`，SSH 别名 `阿里云-FZH-ERPNext-frappe`，bench 根 `/home/frappe/frappe-bench`），**全程只读**（只 SELECT；未 INSERT/UPDATE/DELETE，未 migrate / restart / build；临时物只落 `/tmp`）。
> 与前作关系：本文件是「总表」——把散落在 9 个消费方里的分流点一次列全。逐列深挖见同目录 [deduction-and-sxbzcp-adjustments.md](deduction-and-sxbzcp-adjustments.md)（剔除额）、[colab-engine-cell-by-cell.md](colab-engine-cell-by-cell.md)（老引擎）；绍兴发货方式分类见 [../en-shaoxing-ship-method-taxonomy-spec.md](../en-shaoxing-ship-method-taxonomy-spec.md)。

## 结论摘要

1. **分流点的三大正交维度**：
   - **维度 A · 仓库分类**：`Tongtu Shipping Warehouse.warehouse_classification` 是否含 `FBA` → FBA 分支（无视发货方式，只取「绍兴总成本 + 头程成品运费」，加工成本固定 0）；否则走「按绍兴发货方式」分支。
   - **维度 B · 绍兴发货方式**：`皮壳 / 成品 / 半成品`（来自 BOM 行的「绍兴发货方式」列，源头是 Item Group `custom_shipment_type_to_branch`）。
   - **维度 C · SKU 后缀**：`-PPCOTTON / -COVER / -FOAM`（以及带数字的 `-COVER1 / -FOAM1`）。**只有 order_sync 与 cost_review 认后缀；doc_event、delivery_note_filling_cost 不认后缀**。
2. **共识别 39 个分流点**，分布在 9 个文件里。**最关键的 5 个**：
   ① `bom_cost_list_v2.py:1496` `sx_cost_all`（绍兴总成本源口径，含「自采购」规则）；
   ② `bom_cost_list_v2.py:1552` `destination_processing_cost`（目的地加工成本选择）；
   ③ `order_sync.py:2791` `_update_order_item_cost_from_bom`（订单同步消费口径，最全的分支树）；
   ④ `cost_review.py:1038` `_calculate_single_item_cost`（成本复核消费口径，与 order_sync 有细节差异）；
   ⑤ `bom_cost_list_v2.py:541` `get_item_valuation_rate`（BOM `total_cost` vs `Item.valuation_rate` 回退 + `disabled` 处理）。
3. **「口径漂移」已确认 3 处**（同一输入可能算出不同成本）：
   - `order_sync` 的 **成品 `-FOAM`** 头程 = `cp−pk` **不 clamp 到 0**；`cost_review` 同分支用 `max(0, cp−pk)`。**→ 负值风险只在 order_sync**。
   - `delivery_note_filling_cost.py:675` 的 `sx_cost_all` = `cost_fg + cost_sxbzcp`（当 `product_bom and bom_sxbzcp`），**缺「自采购 / 半成品剔除」规则**，与报表口径不一致。
   - `doc_event` 的 DN 成本**完全不认 SKU 后缀**，且写的是 `custom_valuation_rate`（不是原生 `valuation_rate`）。
4. **目的地加工成本一句话**：`usnj_valuation_rate / ustx_valuation_rate / pl_valuation_rate` 分别 = 该订单主物料对应「`{美东USNJ|美中USTX|波兰PL}包装成品#`」物料的 `is_active=1 且 is_default=1` BOM 的 `total_cost`（无则回退该物料 `Item.valuation_rate`），**物料 `disabled=1` 时置 `None`**；FBA 分支不使用这三列，加工成本固定 0。
5. **头程三列一句话**：`头程皮壳运费 / 头程半成品运费 / 头程成品运费`（各目的地）= 物流价目表 `头程-CNSX-<目的地>` 的取价，按发货方式分别落到 `pk_first_freight / bcp_first_freight / cp_first_freight`；`-COVER` 用皮壳头程、`-FOAM` 用 `成品头程 − 皮壳头程`（半成品则 `半成品头程 − 皮壳头程`）。

## 分流点总表（穷举）

> 判据列 = 触发该分支的条件；差值列 = 该分支相对「默认路径」改了哪些成本字段。

### A. 报表源口径 `apps/work_order_task/work_order_task/work_order_task/report/bom_cost_list_v2/bom_cost_list_v2.py`（1693 行）

| # | 位置 | 判据 | 分支行为差值 |
|---|------|------|------|
| 1 | `:96` `get_default_bom_and_cost` | — | `cost = operating_cost + raw_material_cost + scrap_material_cost`（BOM `total_cost` 的构成） |
| 2 | `:224` `get_sxbzbcp_deduction` | 发货方式=半成品 | 只**减**不加：从成品成本里扣掉重复计入的半成品成本（详见 deduction 文档） |
| 3 | `:279` `get_sxbzcp_info` | 存在物料组 `绍兴包装成品#{item_group}` | 命中 → 取该绍兴包装成品物料；否则该路径为空 |
| 4 | `:318` `get_sxbzbcp_info` | 存在物料组 `绍兴包装半成品#{item_group}` | 命中 → 取绍兴包装半成品物料 |
| 5 | `:503` `get_plbzcp_info` | 存在 `波兰PL包装成品#{item_group}` | 命中 → 提供 `pl_valuation_rate` 的源物料 |
| 6 | `:758` `get_usnjbzcp_info` | 存在 `美东USNJ包装成品#{item_group}` | 命中 → 提供 `usnj_valuation_rate` |
| 7 | `:796` `get_ustxbzcp_info` | 存在 `美中USTX包装成品#{item_group}` | 命中 → 提供 `ustx_valuation_rate` |
| 8 | `:541` `get_item_valuation_rate` | `Item` 有 `is_active=1,is_default=1` BOM | 有 → `BOM.total_cost`；无 → `Item.valuation_rate`；**返回 `is_disabled` 标志** |
| 9 | `:723` `get_shipment_type_by_ks_code` | KS 码 → Item Group `custom_model_id` | 解析出 `皮壳/半成品/成品`，写入 BOM 行的「绍兴发货方式」列 |
| 10 | `:834` `transform_logistic_header` | 物流表头 label 形如 `头程皮壳运费<br>美东USNJ` | 转成列名（用于三列头程） |
| 11 | `:881` `generate_logistic_columns`（过滤点在 `:910-911`, `:972-973`） | 目的地为 FBA / HWC | 过滤物流价目表（本库价目表名均为 `头程-CNSX-<code>`，故实际只排除 4 个 FBA 目的地） |
| 12 | `:1026` | 半成品运费缺失 | 「半成品运费缺失时用皮壳近似」开关（默认否） |
| 13 | `:1177 / :1190 / :1203` | `is_disabled` | 目的地加工成本 = `None`（当对应物料 `disabled`） |
| 14 | `:1496-1530` `sx_cost_all` | **自采购规则**：成品 + `cost_fg≠0` + `cost_sxbzcp==0` + BOM 自引用主物料 | → `sx_cost_all = cost_fg`（皮壳成本）；否则若 `bom_fg and bom_sxbzcp` → `cost_fg + cost_sxbzcp`；否则 0。半成品先扣剔除额（`:1511`） |
| 15 | `:1552-1558` `destination_processing_cost` | 目的地 ∉{FBA,HWC} 时按 code 选 | USNJ→`usnj_valuation_rate`；USTX→`ustx_valuation_rate`；PL→`pl_valuation_rate`；否则 0 |
| 16 | `:1560-1585` `pllc_cover` | 列名 `pllc_cover` 兼表「发皮壳」与「发半成品」 | 发皮壳：`cost_fg + cover_freight + dest_proc`；发半成品（`-FOAM` 式）：`cost_fg + cost_sxbzbcp + 头程 + dest_proc`；任一关键项为 0 → 整列置 0 |
| 17 | `:1600-1605` `pllc_fg` | 发成品 | `pllc_fg = sx_cost_all + fg_freight`；`sx_cost_all==0 或 fg_freight==0` → 0 |

### B. 订单同步 `apps/tongtool_integration/tongtool_integration/sync/order_sync.py`

| # | 位置 | 判据 | 分支行为差值 |
|---|------|------|------|
| 18 | `:2193` `_get_warehouse_cost_config` | 仓库在 `Tongtu Shipping Warehouse` 且**至少一个列名字段非空** | 返回 9 个列名字段字典；不存在/全空 → `None` |
| 19 | `:2347` `_load_bom_cost_data` | 从 `Tongtool Settings.bom_cost_file_name` 读 gz；缺省回退 | 构建 `label_to_fieldname`；开启 `enable_bom_cost_backfill`(「启用重量模板成本兜底」) |
| 20 | `:2791-3018` `_update_order_item_cost_from_bom` | 见下方子分支 | 写入订单行的 `sx_shipping_cost / first_freight / cost_fg / cost_sxbzbcp / cost_sxbzcp` 等 |
| 20a | `:2921` | `'FBA' in warehouse_classification.upper()` | FBA → `sx_shipping_cost=sx_cost_all*数量*系数`，`first_freight=cp_first_freight*...` |
| 20b | `:2935` `shipping_mode=='皮壳'` | `-PPCOTTON`(`:2941`)→双侧清 0；`-COVER`(`:2947`)→ 取皮壳成本 + 皮壳头程；else(`:2956`)→ 皮壳成本 + 皮壳头程 |
| 20c | `:2959` `shipping_mode=='成品'` | `-COVER`(`:2964`)→ 皮壳成本 + 皮壳头程、加工成本清 0；`-FOAM`(`:2972`)→ **成品成本 + 头程=`cp−pk`（不 clamp）**；else(`:2981`)→ `sx_cost_all` + 成品头程 |
| 20d | `:2984` `shipping_mode=='半成品'` | `-COVER`(`:2989`)→ 皮壳；`-FOAM`(`:2997`)→ 半成品成本 + 头程=`bcp−pk`；else(`:3010`)→ `cost_fg+cost_sxbzbcp` + 半成品头程 |
| 21 | `:2913-2917` | 三列头程 `pk/bcp/cp_first_freight` | = BOM 三列 × 数量 × 拆分多包裹成本系数 |
| 22 | `:3120` `_fill_split_package_cost_factor_for_order` | 订单行有 `erp_item_code` | 从 `Item.custom_split_package_cost_factor` 回填 `split_package_cost_factor` |
| 23 | `:4484` `_calculate_effective_weight_for_hist_fee` | 数字后缀 `-COVER1/-FOAM1` 等 | 仅带数字后缀时改有效重量口径；无后缀的 `-COVER/-FOAM` 保持原逻辑 |

### C. 成本复核 `apps/tongtool_integration/tongtool_integration/tongtool_integration/doctype/tongtool_cost_review/tongtool_cost_review.py`（2896 行）

| # | 位置 | 判据 | 分支行为差值 |
|---|------|------|------|
| 24 | `:39-45` `_needs_last_leg` | 仓库名含 `FBA`/`多渠道仓库`，或渠道/账号对方付尾程 | → 0；否则 1 |
| 25 | `:68` `_get_warehouse_classification_for_excel` | 按仓库名查分类 | 供 FBA 判据用 |
| 26 | `:741-830` | SKU 数字后缀 `-COVER1/-FOAM1` | 复用 order_sync 的 `_calculate_effective_weight_for_hist_fee` |
| 27 | `:951-1122` `_calculate_single_item_cost` | 见子分支 | 写 `sx_shipping_cost / first_freight / valuation_rate / sx_cost_all` |
| 27a | `:1046` `is_fba_warehouse` | `'FBA' in classification` | FBA → `sx_shipping_cost=sx_cost_all`、`sx_cost_all`=同值、`first_freight=cp` |
| 27b | `:1057` 非 FBA · 皮壳 | `-PPCOTTON`(`:1062`)、`-COVER`(`:1068`)、else(`:1079`) |
| 27c | `:1088` 非 FBA · 成品 | `-COVER`(`:1091`)、`-FOAM`(`:1100`)→ **`first_freight = max(0, cp−pk)`**（有 clamp！）、else(`:1117`) |
| 27d | `:1124` 非 FBA · 半成品 | 同结构（`-COVER / -FOAM / else`），`sx_cost_all` 同步镜像 |
| 28 | `:2146` `process_fba_order_excel` | FBA 文件 | 加工成本、历史预估尾程、是否需要尾程、最终尾程费用**一律固定 0**（注释 `:2149-2152`） |

### D. 送货单事件 `apps/delivery_plan/delivery_plan/doc_event.py`

| # | 位置 | 判据 | 分支行为差值 |
|---|------|------|------|
| 29 | `:1371` `update_bom_cost_info` | 物料前缀 | `PK#`(`:1418`)→`cost_pk`；`ND#`(`:1426`)→`cost_nd`；else(`:1440`)→`sx_cost_all` |
| 30 | `:1515` `update_dn_item_cost_info` | 见子分支 | 写 `item.sx_shipping_cost / first_freight / **custom_valuation_rate**`（非原生 `valuation_rate`） |
| 30a | `:1652` | `'FBA' in classification` | FBA → `sx_cost_all + cp` + `custom_valuation_rate` |
| 30b | `:1662/:1676/:1690/:1694` | 皮壳 / 成品 / 半成品 / else | **不认 SKU 后缀**；成品用 `sx_cost_all`，半成品用 `cost_fg+cost_sxbzbcp` |
| 31 | `:34` | 重量模板匹配正则 `^(?:PK#)?(...)` | 剥 `PK#` 前缀再匹配重量模板 |
| 32 | `:1521/:1551-1566` `get_wh_config` | 缓存 `_get_warehouse_cost_config` | 与 order_sync 同源 |

### E. Excel 入口 `excel_tongtool_order.py`

| # | 位置 | 判据 | 分支行为差值 |
|---|------|------|------|
| 33 | `:535-555` | FBA 输出字段定义 | `valuation_rate / hist_predict_fee / needs_last_leg / final_last_leg_fee` **固定 0** |
| 34 | `:193-212` | `尾程费用来源` 列 | FBA 该列空时从非 FBA 表回填 |

### F. 销售毛利润 `sales_gross_profit.py`

| # | 位置 | 判据 | 分支行为差值 |
|---|------|------|------|
| 35 | `:284-308` | `needs_last_leg`（`:295`） | `gross_profit = 销售额 − sx_shipping_cost − valuation_rate − first_freight − last_leg_fee − 渠道成交费`；`needs_last_leg==0` 时 `last_leg_fee` 置 0 |

### G. 出厂价 PIM `apps/vilavi_pim/.../page/item_group_browser/item_group_cost_service.py`

| # | 位置 | 判据 | 分支行为差值 |
|---|------|------|------|
| 36 | `:208-210` | 字段 `fba_factory_price` | FBA 出厂价 = `sx_cost_all` |
| 37 | `:247-273` `_calculate_dynamic_freight` | 目的地 freight 字段 | 动态拼接头程 |
| 38 | `:276-300` `_calculate_fbm_factory_price` | FBM 出厂价 | 另一公式 |

### H. 送货单 API

| # | 位置 | 判据 | 分支行为差值 |
|---|------|------|------|
| 39 | `sellfox_oversea_pick.py:99/:144` | 海外仓拣货 | 汇总 `sx_shipping_cost` → `manualPurchaseCost`（`:172`） |
| 39b | `delivery_note_excel.py:111/:115` | 导出 | `指定采购单价 = sx_shipping_cost`；`其他费用 = custom_valuation_rate` |

> 另：`apps/work_order_task/.../report/delivery_note_filling_cost/delivery_note_filling_cost.py` 内还含 3 个分流点（见「其它影响成本的分支」§FBA 客户）。

## Tongtu Shipping Warehouse 配置（逐条）

### DocType 字段（`apps/tongtool_integration/tongtool_integration/tongtool_integration/doctype/tongtu_shipping_warehouse/tongtu_shipping_warehouse.json`）

| 字段 | 类型 | 说明 |
|------|------|------|
| `warehouse_name` | Data（autoname） | 仓库名（= 通途发货仓库名） |
| `warehouse_classification` | Link → `Tongtu Shipping Warehouse Classification` | 仓库分类（含 FBA 关键词 → FBA 分支） |
| `shipping_region` | Select（readonly） | 美国 / 欧洲 / 其它 / 英国 / 日本 / 加拿大（从分类带出） |
| `warehouse_code` | Select（readonly） | USNJ / PL / USHWC / SXZFH / EUHWC / USFBA / EUFBA / UKFBA / JPFBA / CAHWC / USTX |
| `shell_cost_column_name` | Data | 「皮壳成本」列名 |
| `shaoxing_semi_finished_cost_column_name` | Data | 「绍兴包装半成品成本」列名 |
| `shaoxing_finished_cost_name` | Data | 「绍兴包装成品成本」列名 |
| `shaoxing_total_cost_name` | Data | 「绍兴总成本」列名 |
| `processing_cost_name` | Data | **加工成本列名**（目的地加工成本） |
| `first_leg_shell_freight_name` | Data | 头程皮壳运费列名 |
| `first_leg_semi_finished_freight_name` | Data | 头程半成品运费列名 |
| `first_leg_finished_freight_name` | Data | 头程成品运费列名 |

分类 Select 全量选项（`tongtu_shipping_warehouse_classification.json`）：`USNJ美东分公司 / PL波兰分公司 / 美国海外仓 / 绍兴自发货 / 欧洲海外仓 / 美国FBA / 欧洲FBA / 英国FBA / 日本FBA / 加拿大海外仓 / USTX美中分公司`。

### 配置行（生产库共 **40 行**，按分类分组；组内字段值完全一致）

| 分类 | 行数 | `processing_cost_name` | `first_leg_皮壳/半成品/成品` | 仓库名 |
|------|------|------------------------|-------------------------------|--------|
| PL波兰分公司 | 5 | `波兰加工成本<br>PL` | 头程皮壳/半成品/成品运费<br>波兰PL | FZHPoland-covers, FZHPoland-finished, 波兰-FZHPoland-covers, 波兰-FZHPoland-退货产品仓, 波兰公司 |
| USNJ美东分公司 | 4 | `美东加工成本<br>USNJ` | 三列均 `<br>美东USNJ` | CENTRADE, WayfairCG-Cranbury仓, 美东-CENTRADE, 美东-CENTRADE-退货产品仓 |
| USTX美中分公司 | 10 | `美中加工成本<br>USTX` | 三列均 `<br>美中USTX` | DANEEY, FZH-DANEEY, FZH-DANEEY-半成品仓, FZH-DANEEY-成品仓, FZH-DANEEY-皮壳仓库, FZH-DANEEY-退货产品仓, WayfairCG-McDonough仓, 美中-FZH-DANEEY, 美中-FZH-DANEEY-皮壳仓库, 美中-FZH-DANEEY-退货产品仓 |
| 美国海外仓 | 2 | **`美中加工成本<br>USTX`（非空！）** | 皮壳/半成品 `<br>美中USTX`；**成品 `<br>USFBA`（不一致）** | 大件云仓, 星链海外仓 |
| 美国FBA | 4 | **NULL（空）** | 皮壳/半成品 NULL；成品 `<br>USFBA` | 加拿大FBA仓, 多渠道仓库, 美国FBA仓, 美国多渠道仓库 |
| 欧洲FBA | 12 | **NULL（空）** | 皮壳/半成品 NULL；成品 `<br>DEFBA` | 德国FBA仓, 德国多渠道仓库, 意大利FBA仓, 意大利多渠道仓库, 比利时FBA仓, 法国FBA仓, 法国多渠道仓库, 波兰FBA仓, 英国FBA仓, 荷兰FBA仓, 西班牙FBA仓, 西班牙多渠道仓库 |
| 日本FBA | 2 | **NULL（空）** | 皮壳/半成品 NULL；成品 `<br>JPFBA` | 日本FBA仓, 日本多渠道仓库 |
| 英国FBA | 1 | **NULL（空）** | 皮壳/半成品 NULL；成品 `<br>UKFBA` | 英国多渠道仓库 |

**关键结论**：
- **FBA（美/欧/英/日，共 19 行）`processing_cost_name` 全部为空**，且皮壳/半成品头程也为空——FBA 只用「绍兴总成本 + 头程成品运费」，加工成本由代码强制 0。
- **美国海外仓（2 行）`processing_cost_name` 非空**（复用「美中加工成本<br>USTX」），皮壳/半成品头程也非空——海外仓**走非 FBA 分支**，会带目的地加工成本。
- **分类选项里存在但生产库无配置行**：`绍兴自发货`、`欧洲海外仓`、`加拿大海外仓`（分类 Select 有，`Tongtu Shipping Warehouse` 无对应行）。
- **消费方**：`_get_warehouse_cost_config`（`order_sync.py:2193`）/ `_get_warehouse_classification_for_excel`（`cost_review.py:68`）/ `get_wh_config`（`doc_event.py:1521,1566`）/ `item_group_cost_service` 等，全部只读本 DocType。

## 目的地加工成本取值链

1. **源物料定位**：主物料的 KS 码 → 目的地包装成品物料组 `{美东USNJ|美中USTX|波兰PL}包装成品#{item_group}`（`bom_cost_list_v2.py:758 / :796 / :503`）。
2. **取值**：`get_item_valuation_rate`（`:541`）——优先该物料 `is_active=1 且 is_default=1` 的 BOM `total_cost`；无则回退 `Item.valuation_rate`。
3. **`disabled` 处理**：物料 `disabled=1` → 报表把这列置 **`None`**（`:1177 / :1190 / :1203`）。
4. **落到哪一列**：`usnj_valuation_rate`（美东）/ `ustx_valuation_rate`（美中）/ `pl_valuation_rate`（波兰）；列定义在 `:1274-1282` 与 `:1635-1637`。
5. **进不进「目的地加工成本」合计**：`destination_processing_cost`（`:1552-1558`）按仓库 code 选一列，**FBA / HWC 分类恒为 0**。
6. **消费**：`pllc_cover`（`:1569/:1580`）与 `pllc_fg` 把 `destination_processing_cost` 加进尾程前成本；订单同步里 FBA 分支不使用它（加工成本固定 0）。
7. **FBA/海外仓是否带加工成本**：**FBA = 0（配置 `processing_cost_name` 为空 + 代码强制 0）**；**美国海外仓 = 非 0（配置复用 USTX 加工成本，走非 FBA 分支）**。

## 头程三列与联动

- 三列列名由 `transform_logistic_header`（`bom_cost_list_v2.py:834`）从物流价目表生成，形如 `头程皮壳运费<br>美东USNJ`、`头程半成品运费<br>美中USTX`、`头程成品运费<br>PL`。
- 价目表（生产库 `tabLogistic Price List` 全量 8 条）：`头程-CNSX-{USNJ,USTX,PL,USFBA,EUFBA,UKFBA,JPFBA}` + `头程-PL-ROFBE`。报表按 `头程-CNSX` 过滤，FBA/HWC 分支被排除（本库实际只排除 4 个 FBA 目的地）。
- **落到订单行的映射**：皮壳 → `pk_first_freight`（列 `first_leg_shell_freight_name`）；半成品 → `bcp_first_freight`；成品 → `cp_first_freight`（`order_sync.py:2913-2917`）。
- **联动规则（按发货方式/后缀）**：
  - `皮壳` / `-COVER` → 头程取**皮壳头程**；
  - `成品` → 成品头程；`半成品` → 半成品头程；
  - **`-FOAM`** → 成品分支取 `cp − pk`；半成品分支取 `bcp − pk`。**order_sync 不 clamp**（`order_sync.py:2978 / :3003`），**cost_review 用 `max(0, …)`**（`cost_review.py:1107` 等）。
  - `-PPCOTTON` → 头程与发货成本双侧清 0（`order_sync.py:2941`；`cost_review.py:1062`）。
- **系数**：三列头程都会再乘 `quantity × split_package_cost_factor`（拆分多包裹成本系数，`Item.custom_split_package_cost_factor`）。

## 其它影响成本的分支

1. **自采购（皮壳 BOM 自引用主物料）**：`bom_cost_list_v2.py:1496-1530`。条件 = 成品 + `cost_fg≠0` + `cost_sxbzcp==0` + 该物料 BOM 自引用主物料 → `sx_cost_all = cost_fg`。**doc_event / delivery_note_filling_cost 无此规则**。
2. **半成品剔除额**：`get_sxbzbcp_deduction`（`bom_cost_list_v2.py:224`，调用点 `:1511`），只减不加。
3. **拆单 / 多包裹**：`split_package_cost_factor` 对绍兴发货成本与三列头程统一乘系数（`order_sync.py:2907-2917`、`_fill_split_package_cost_factor_for_order:3120`）。
4. **`-COVER` / `-PPCOTTON` / `-FOAM` 后缀**：见上表 A20b–d、C27b–d；`-COVER1/-FOAM1` 等数字后缀另改有效重量口径（`order_sync.py:4484`）。
5. **Product Bundle（套件#，UOM=套）**：`product_bundle_lifecycle.py`（`BUNDLE_ITEM_GROUP="套件#"`, `BUNDLE_UOM="套"`）——套件拆解影响订单行粒度，进而影响按行的成本聚合。
6. **PK# / ND# 前缀**：`doc_event.py:1371/:1799`——皮壳物料取 `cost_pk`、内胆取 `cost_nd`，与产品取 `sx_cost_all` 三路分流。
7. **FBA 客户（按客户名/客户码含 "FBA"）**：`delivery_note_filling_cost.py:327 _contains_fba_keyword`、`:381 / :414` 强制按成品（`cost_fg + cost_sxbzcp`），`:618` 强制纳入 `sxbzcp`——**按客户名而非仓库分类判 FBA**，与前面所有分流点判据不同源。
8. **`delivery_note_filling_cost.sx_cost_all`（`:675`）**：`= cost_fg + cost_sxbzcp`（当 `product_bom and bom_sxbzcp` else 0），**缺自采购 / 剔除规则**，为口径漂移点。
9. **FBA 强制清 0**：`excel_tongtool_order.py:535-555`、`cost_review.py:2146+`（加工成本 / 尾程四项置 0）。
10. **是否需尾程**：`cost_review.py:39-45`、`sales_gross_profit.py:295`——仓库含 FBA/多渠道/云仓或对方付尾程 → 0。

## 未证实 / 存疑

- **`绍兴自发货` / `欧洲海外仓` / `加拿大海外仓`** 三个分类在 Select 里有、但生产库无 `Tongtu Shipping Warehouse` 配置行；**未证实**它们在真实单据里如何解析（可能 `_get_warehouse_cost_config` 返回 `None`，走「无 BOM 回退」路径）。
- **`reservation_rate` / 汇率** 等与成本相关但非「分流」的分支未纳入本表。
- **报表 `bom_cost_list_v2.py:1496` 自采购规则**的存量触发笔数未统计（仅确认规则存在与判据）。
- `order_sync` 成品 `-FOAM` 不 clamp 与 `cost_review` clamp 的差异**是否造成实际负值单据**未取证（仅代码层确认差异）。
- `product_bundle_lifecycle.py` 对「按行成本聚合」的确切影响路径**未逐行核实**。
- `delivery_note_filling_cost.py` 与报表口径漂移**是否为已知有意设计**未确认（无注释/文档说明）。

## 证据清单（路径:行号 / SQL）

**代码（EN 服务器，相对 `/home/frappe/frappe-bench/`）**
- `apps/work_order_task/work_order_task/work_order_task/report/bom_cost_list_v2/bom_cost_list_v2.py`：`:96, :224, :279, :318, :503, :541, :723, :758, :796, :834, :881, :910-911, :972-973, :1026, :1177, :1190, :1203, :1274-1282, :1496-1530, :1552-1558, :1560-1585, :1600-1605, :1635-1637`
- `apps/tongtool_integration/tongtool_integration/sync/order_sync.py`：`:2193, :2347, :2791-3018, :3120, :4484`
- `apps/tongtool_integration/tongtool_integration/tongtool_integration/doctype/tongtool_cost_review/tongtool_cost_review.py`：`:39-45, :68, :741-830, :951-1122, :2146`
- `apps/delivery_plan/delivery_plan/doc_event.py`：`:34, :1371, :1515, :1521, :1551-1566, :1652, :1799`
- `apps/tongtool_integration/tongtool_integration/tongtool_integration/doctype/tongtu_shipping_warehouse/tongtu_shipping_warehouse.json`
- `apps/tongtool_integration/tongtool_integration/tongtool_integration/doctype/tongtu_shipping_warehouse_classification/tongtu_shipping_warehouse_classification.json`
- `apps/work_order_task/work_order_task/work_order_task/report/delivery_note_filling_cost/delivery_note_filling_cost.py`：`:327, :332, :381, :414, :588, :618, :675`
- `apps/work_order_task/work_order_task/work_order_task/report/sales_gross_profit/sales_gross_profit.py`：`:284-308`
- `apps/vilavi_pim/.../page/item_group_browser/item_group_cost_service.py`：`:208-210, :247-273, :276-300`
- `apps/delivery_plan/delivery_plan/api/sellfox_oversea_pick.py`：`:99, :144, :172`；`apps/delivery_plan/delivery_plan/api/delivery_note_excel.py`：`:111, :115`

**SQL（均只读）**
- 仓库配置逐行：`SELECT name, warehouse_classification, shipping_region, warehouse_code, shell_cost_column_name, shaoxing_semi_finished_cost_column_name, shaoxing_finished_cost_name, shaoxing_total_cost_name, processing_cost_name, first_leg_shell_freight_name, first_leg_semi_finished_freight_name, first_leg_finished_freight_name FROM \`tabTongtu Shipping Warehouse\` ORDER BY warehouse_classification, name;`
- 行数/空值统计：`SELECT warehouse_classification, COUNT(*) c, SUM(processing_cost_name IS NULL) null_pc, SUM(first_leg_shell_freight_name IS NULL) null_fl FROM \`tabTongtu Shipping Warehouse\` GROUP BY warehouse_classification;`（结果：PL 5 / USNJ 4 / USTX 10 / 日本FBA 2 / 欧洲FBA 12 / 美国FBA 4 / 美国海外仓 2 / 英国FBA 1，合计 **40**；FBA 四类 `null_pc` = 行数，美国海外仓 `null_pc` = 0）
- 活跃 BOM 成本文件：`SELECT field, value FROM tabSingles WHERE doctype='Tongtool Settings' AND field IN ('bom_cost_file_name','enable_bom_cost_backfill');` → `bom_cost_list_v2_2026-35-14-16-10.json.gz` / `启用重量模板成本兜底`
- 物流价目表：`SELECT name FROM \`tabLogistic Price List\` ORDER BY name;` → 8 条（`头程-CNSX-*` 7 条 + `头程-PL-ROFBE`）
- 分类 Select 选项：读 `tongtu_shipping_warehouse_classification.json` 的 `options` 字段
