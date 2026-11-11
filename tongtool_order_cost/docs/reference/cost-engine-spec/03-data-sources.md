---
okf: v0.1
type: Reference
title: 数据源清单（GS 工作簿/ws + EN 报表/Doctype/app）
description: 老系统（Google Sheet）每张工作簿→工作表→谁生成/谁消费/行数，以及 EN（ERPNext）侧的报表、Doctype、app 清单；含缺口指向
date: 2026-10-15
module: tongtool_order_cost
tags: [cost, data-sources, gsheet, erpnext, lineage, reference]
---

# 数据源清单

> 「这张表谁写、谁读、多少行」的单一事实源。取值规则见 [04-cost-decision-tables.md](04-cost-decision-tables.md)；键见 [02-keys-and-entities.md](02-keys-and-entities.md)。
> 行数为 **2026-10 冻结快照**实测；缺口结论一律标注时点（见 [09](09-known-issues-register.md) B3）。

## 1. GS 侧（Google Sheet）

### 1.1 `通途订单202607`（月度订单工作簿）

| 工作表 | 行数 | 生成者 | 消费者 | 说明 |
|---|---:|---|---|---|
| `2026年7月订单` | 9604 | 通途导出 | Colab 引擎（raw 输入） | **原始订单**（raw） |
| `写回2026年7月订单` | 9579 | Colab 引擎 | 运营/财务 | 引擎写回（派生输出，**绝不作 raw**） |
| `写回2026年7月FBA订单` / `写回…FBA订单和非FBA订单` | — | Colab | 运营 | FBA / 混合写回变体 |
| `检查运营人员-写回2026年7月FBA订单和非FBA订单` | — | Colab | 运营 | 校验表（`check` 类） |
| `弃用2026年7月订单*` | — | 人工 | — | 归档（`弃用*` 前缀） |
| `透视表2品类` 等 | — | 人工 | — | 透视（`透视表*`） |

> `audit_sources.py:31-44` 按前缀分类：`写回*`→WRITEBACK、`弃用*`→ARCHIVE、`透视表*`→PIVOT；`检查运营人员-写回*` 亦为派生（**不能当 raw**）。

### 1.2 `和财务部共享`

| 工作表 | 行数 | 生成者 | 消费者 | 说明 |
|---|---:|---|---|---|
| `订单发货仓库对应成本来源` | 47 | 人工 | Colab `cell_108` | 仓库→`二次加工成本来源编码`/`头程运费来源编码` 映射。**美中 USTX 行仍写 `2CJG-SX`**（键不对称，见 [../colab-cost-engine-spec.md](../colab-cost-engine-spec.md) §7） |
| `汇率` | 19 | 人工 | Colab 引擎 | 收款币种→汇率 |
| `Jeck特殊规则-订单改销售额成本` | 873 | 人工 | Colab 引擎（规则覆盖） | **6 列去重键**规则；`keep=last|first`（见 [02](02-keys-and-entities.md) §4） |

### 1.3 `二次加工成本2022`

| 工作表 | 行数 | 生成者 | 消费者 | 说明 |
|---|---:|---|---|---|
| `绍兴二次加工成本` | 920 | 人工/Colab | Colab `cell_125 L33-44` | 绍兴侧二次加工（**美中当前借此**）；硬编码月份列 `二次加工成本多月202511` |
| `测算 美中USTX二次加工成本` | 621 | 人工 | （未启用原型） | 新建美中表原型；**缺 115/615 键（美中缺 43.5%，影响 1146 行）** |
| `import皮壳成本` | 902 | EN 导出 | `ustx_cost_compare.py` | 皮壳成本 + `EN重量模板物料号`；**同名键→不同重量模板冲突 7 月有 3 个**。⚠️ 三列名「绍兴/美国/波兰二次加工成本」**实际装各地包装成品成本** |
| `importBOMCostList` | 3693 | EN 导出 | `ustx_cost_compare.py` | EN BOM 成本列表（含 `皮壳成本`/`绍兴包装成品成本`/`美中加工成本, USTX`…） |
| `美中USTX成本测算` | 478 | 人工 | （测算） | 美中成本测算 |
| 其它 | — | — | — | `美国二次加工成本`(美东 USNJ)、`波兰二次加工成本`、`测算 美东USNJ二次加工成本`；`gsheet_name_cost_2prod` 消费时**排除** 合并/orig/副本/copy/测试/测算/import 类 ws（[../colab-cost-engine-spec.md](../colab-cost-engine-spec.md)） |

### 1.4 `财务部绍兴成本核算表单2023`

| 工作表 | 规格 | 生成者 | 消费者 | 说明 |
|---|---|---|---|---|
| `皮壳成本平均202409-202410-202411（用于通途订单202502）` | — | 人工 | Colab `df_sx` | 皮壳成本平均（含新品保护期，`cell_036`） |
| `EN产品BOM成本列表20260202` | 3693 行 × 70 列 | EN 导出 **2026-09-03** | Colab `df_en`（EN 覆盖层） | 名字日期是**旧名**（实为 09-03 导出，见 [09](09-known-issues-register.md) D2/B1）；按 `重量模板编号` 取 **max** 覆盖皮壳成本 |

### 1.5 `头程运费成本`

| 工作表 | 生成者 | 消费者 | 说明 |
|---|---|---|---|
| `头程运费单价记录RMB` 等单价 ws | 人工 | Colab `df_cost_trans_head` | 键 `['头程运费来源编码','品类尺寸面料编码']` |
| `头程运费来源编码-EN成本列名对照表` | 人工 | Colab | 编码↔EN 列名（如 `HEAD-USTX`→`en头程成品运费美中USTX`） |
| `美国分公司USTX头程运费核算` | 人工 | Colab | **缺 78 键**（77 可经 `品类尺寸编码`+面料 rematch 修复） |
| `测算 按皮壳重量 美国分公司USTX头程运费核算` | 人工 | （测算） | — |
| `头程运费合并` | — | — | 消费时**排除** |

> 编码由 **worksheet 名 contains 规则**生成：`分公司+美国+USNJ→HEAD-US`、`分公司+美国+USTX→HEAD-USTX`、`+皮壳→HEAD-USTX-PK`、`分公司+波兰→HEAD-PL`、`海外仓+美国→HEAD-USHWC`…；`HEAD-SX→0`。

## 2. EN 侧（ERPNext）

### 2.1 报表（Reports）

| 报表 | 文件 | 用途 |
|---|---|---|
| `BOM Cost List`（V1） | `work_order_task/.../report/bom_cost_list/` | 旧版 BOM 成本列表 |
| **`BOM Cost List`（V2）** | `work_order_task/.../report/bom_cost_list_v2/bom_cost_list_v2.py`（1693 行） | **成本主源**：算 `皮壳成本`/`绍兴总成本`/`目的地加工成本`/`头程三列`（见 [en-branching-and-warehouse-config.md](en-branching-and-warehouse-config.md) §A） |
| `delivery_note_filling_cost` | `work_order_task/.../report/delivery_note_filling_cost/` | 送货单填充成本（含**口径漂移** `:675`） |
| `sales_gross_profit` | `work_order_task/.../report/sales_gross_profit/` | 销售毛利润 |

### 2.2 DocTypes

| DocType | 关键字段 | 说明 |
|---|---|---|
| `BOM` | `total_cost` = `operating_cost + raw_material_cost + scrap_material_cost` | 成本主载体；`is_active` / `is_default` |
| `BOM Item` | — | BOM 明细行（含「绍兴发货方式」列） |
| `BOM Operation` | `operating_cost` | 工站 → `Workstation.hour_rate_labour` |
| `Item` | `valuation_rate` / `disabled` / `custom_split_package_cost_factor` / `default_material_request_type` | 物料；无 BOM → 回退 `valuation_rate` |
| `Item Group` | `custom_shipment_type_to_branch` / `custom_model_id` / `is_group` / `is_leaf_group` | 发货方式源头（见 [02](02-keys-and-entities.md) §3） |
| `Workstation` | `hour_rate_labour` / `hour_rate_manage` | 工资率（`美中USTX包装` = 167.8 + 34.24） |
| `Tongtu Shipping Warehouse` | 9 个成本列名字段 + `warehouse_classification` | 仓库→成本列映射（**40 行**，见 [en-branching-and-warehouse-config.md](en-branching-and-warehouse-config.md)） |
| `Tongtool Settings` | `bom_cost_file_name` / `enable_bom_cost_backfill` | 活跃 BOM 成本 gz 文件名 + 重量模板成本兜底开关 |

### 2.3 app / 消费方

| app | 关键文件 | 角色 |
|---|---|---|
| `work_order_task` | `report/bom_cost_list_v2/…py`、`report/delivery_note_filling_cost/…py`、`report/sales_gross_profit/…py` | 报表源口径（成本主算） |
| `key_test` | — | 测试用（与生产割裂） |
| `tongtool_integration` | `sync/order_sync.py`、`doctype/tongtool_cost_review/…py`、`doctype/tongtu_shipping_warehouse/…json` | 订单同步 / 成本复核 / 仓库配置 |
| `delivery_plan` | `doc_event.py`、`api/sellfox_oversea_pick.py`、`api/delivery_note_excel.py` | 送货单事件 / 海外仓拣货 / 导出 |
| `vilavi_pim` | `page/item_group_browser/item_group_cost_service.py` | 出厂价（`fba_factory_price=sx_cost_all`） |

> **消费方**（只读 `Tongtu Shipping Warehouse`）：`_get_warehouse_cost_config`（`order_sync.py:2193`）/ `_get_warehouse_classification_for_excel`（`cost_review.py:68`）/ `get_wh_config`（`doc_event.py:1521,1566`）。

## 3. 缺口（指向覆盖率审计）

| 缺口 | 量 | 影响 | 详见 |
|---|---|---:|---|
| `测算 美中USTX二次加工成本` 缺键 | 115/615（美中缺 43.5%） | 1146 行订单 | [../old-system-source-coverage-audit.md](../old-system-source-coverage-audit.md)、[09](09-known-issues-register.md) C1 |
| 头程 USTX 核算表缺键 | 78（77 可 rematch） | 行级 2443/2446 完备 | 同上 C2 |
| 无 BOM 的美中物料 | 96 | 走 `valuation_rate` 回退，不随工资率变 | [../en-ustx-no-bom-items-spec.md](../en-ustx-no-bom-items-spec.md)、[09](09-known-issues-register.md) C3 |
| 空键订单行 | 75（7 月） | 不并入匹配 | [../old-system-source-coverage-audit.md](../old-system-source-coverage-audit.md) |

> **行完备度要求**：下限 177 / 推荐 332 / 对齐 868~881（按 `品类尺寸面料编码` 唯一数）。

## 4. 证据清单

- 代码：`audit_sources.py:31-44`、`io_loaders.py:32-33`、`scripts/audit_monthly_profitability.py:88-93,176-186,477-481`、`ustx_cost_compare.py:34,53-54`
- GS：`通途订单202607`、`和财务部共享`、`二次加工成本2022`、`财务部绍兴成本核算表单2023`、`头程运费成本`（2026-10 快照）
- 文档：[../colab-cost-engine-spec.md](../colab-cost-engine-spec.md) §2、[../monthly-profitability-audit.md](../monthly-profitability-audit.md)、[../old-system-source-coverage-audit.md](../old-system-source-coverage-audit.md)、[en-branching-and-warehouse-config.md](en-branching-and-warehouse-config.md)
