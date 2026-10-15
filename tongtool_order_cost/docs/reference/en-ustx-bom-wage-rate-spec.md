---
okf: v0.1
type: Reference
title: EN 美中 USTX 加工成本工资率链路与复算规格（167.8 → 105）
description: 逆向 ERPNext 生产库「美中加工成本, USTX」列的成本来源：公式、167.8 工资率的存放记录、随工资率变动的成本项、复制 BOM 机制，以及 167.8→105 的离线复算方法与结果
date: 2026-10-15
module: tongtool_order_cost
tags: [cost, ustx, bom, erpnext, wage-rate, reference, read-only]
---

# EN 美中 USTX 加工成本工资率链路与复算规格

> 数据口径：ERPNext **生产库**（`erpnext.vilavi.cn`），**全程只读**（未创建/修改/删除任何记录，未 migrate / restart / build）。
> 产出：`tongtool_order_cost/out/ustx_wage_sim/{ustx_bom_ops.csv, summary.json}`。
> 场景：EN 包装工站工资率计划由 **167.8 → 105**（尚未实施），需要离线复算所有 `USTXBZCP#%` 成品 BOM 的加工成本会变成多少。

## 结论摘要

1. **「美中加工成本, USTX」= 该 `USTXBZCP#` 物料的「`is_active=1 且 is_default=1`」BOM 的 `total_cost`**；若无此 BOM，回退 `Item.valuation_rate`。
2. **`total_cost = raw_material_cost + operating_cost + scrap_material_cost`**（生产库 309 张 USTX BOM 全部满足，0 例外）。
3. **只有 `operating_cost` 随工资率变化**：
   `operating_cost = Σ_工序( time_in_mins/60 × hour_rate )`，其中 `hour_rate = hour_rate_labour + hour_rate_manage + 电费 + 租金 + 耗材`。
4. **167.8 存在 `Workstation` 记录 `美中USTX包装` 的字段 `hour_rate_labour`**（自定义字段；同记录 `hour_rate_manage=34.24`，电费/租金/耗材均 0，净 `hour_rate=202.04`）。**不是** ERPNext 标准的 `Workstation.hour_rate`，**也不是**自定义 DocType `Hour Rate`（生产库 `tabHour Rate` 为空，0 行）。
5. **物料成本（raw_material_cost）不随工资率变化**，含按「美中USTX标准采购」价目表换价后的 PP 棉。
6. 共 **309 张** USTX BOM（264 个不同物料）：304 张受影响，2 条工序仍挂在 `包装` 工站（rate=23.2、labour=0）不受影响，3 张 BOM 无工序不受影响。
7. **复算结果**：净工费率 `202.04 → 139.24`（×0.68917）。
   - 全 309 张 BOM 的 `sum_delta = −7,217.3057`（未加权，逐 BOM 求和）。
   - 仅「active+default」BOM 的 `sum_delta = −5,884.464667`。
   （金额按「每张 BOM 一次」求和，**不是**按订单/发货数量加权；月度影响需再乘发货数量。）

## 成本公式（含代码位置）

「美中加工成本, USTX」列由报表 `BOM Cost List V2` 产出，字段名 `ustx_valuation_rate`：

```
ustx_valuation_rate
  = BOM(item=该 USTX 物料, is_active=1, is_default=1).total_cost
      ├─ 找到该 BOM：取其 total_cost
      └─ 找不到：回退 Item.valuation_rate
```

- 报表取值：`work_order_task/work_order_task/report/bom_cost_list_v2/bom_cost_list_v2.py`
  - `get_item_valuation_rate(item_code)`（约 541–566 行）：
    `frappe.db.get_value("BOM", {"item": item_code, "is_active": 1, "is_default": 1}, ["name", "total_cost"], as_dict=True)` → `rate = bom_total_cost if not None else valuation_rate`
  - 报表列定义 `{"label": "美中加工成本-USTX", "fieldname": "ustx_valuation_rate"}`（约 1278 / 1636 行）
- BOM 成本构成：`get_default_bom_and_cost`（约 96 行）→ `cost = operating_cost + raw_material_cost + scrap_material_cost`
- 工序 → 工站取价（V2 报表内 `get_ustxbzcp_info`，约 797 行）：`supporting_item_group = f"美中USTX包装成品#{item['item_group']}"`

**一个 USTX 物料映射到哪张 BOM**：取 `is_active=1 且 is_default=1` 的那张；物料可有多个 BOM（-001 / -006 …），只有默认那张进成本列。

## 工资率存放位置与具体记录

| 项 | 值 | 存放位置 |
|---|---:|---|
| `hour_rate_labour`（工资/时薪） | **167.8** | `Workstation` 记录 `美中USTX包装` 的字段 `hour_rate_labour` |
| `hour_rate_manage`（管理费率） | 34.24 | 同记录 `hour_rate_manage` |
| `hour_rate_electricity`（电费） | 0 | 同记录 |
| `hour_rate_rent`（租金） | 0 | 同记录 |
| `hour_rate_consumable`（耗材） | 0 | 同记录 |
| **净工费率 `hour_rate`** | **202.04** | `= 167.8 + 34.24 + 0 + 0 + 0`，`before_save` 自动求和 |

- 汇总逻辑：`work_order_task/work_order_task/doc_events.py` → `update_hour_rate(doc, method)`（约 386 行）：
  `doc.hour_rate = flt(hour_rate_labour) + flt(hour_rate_electricity) + flt(hour_rate_consumable) + flt(hour_rate_rent) + flt(hour_rate_manage)`，挂到 `Workstation` / `Workstation Type` 的 `before_save`。
- 自定义 DocType `Hour Rate`（`work_order_task/.../doctype/hour_rate/`）**存在但未被使用**：生产库 `tabHour Rate` 为 **0 行**，`Workstation.rel_hour_rate` 全为 NULL，工站上的工资率是**直接存储**的，不是从 `Hour Rate` 拉取。
- `BOM Operation` 上的 `hour_rate_labour` / `hour_rate_manage` 由工站 `fetch_from` 得来（见下「复制 BOM 机制」）。

## 随工资率变化的项（以及不变化的项）

| 成本项 | 是否随工资率变 | 说明 |
|---|---|---|
| `operating_cost`（工序加工成本） | **变** | `Σ time/60 × (hour_rate_labour + hour_rate_manage + 电费 + 租金 + 耗材)`；本案例只有 `hour_rate_labour` 从 167.8 改 105 |
| `raw_material_cost`（物料成本） | **不变** | 含按「美中USTX标准采购」价目表换价的 PP 棉；与工资率无关 |
| `scrap_material_cost`（报废物料成本） | **不变** | 全库 USTX BOM 均为 0 |
| `total_cost` | **变** | `= raw + operating + scrap`，只有 operating 项动 |

- 已验证：生产库 309 张 USTX BOM 中，`BOM.operating_cost` 与 `Σ BOM Operation.operating_cost` **完全一致（0 例外）**，且 `total_cost − (raw + operating + scrap) = 0`（0 例外）→ 当前两套口径等价，自定义 override 未改写该公式。

## 复制 BOM 机制

`USTXBZCP#%` 成品 BOM 不是手工建的，而是由绍兴侧成品 BOM **自动复制**而来。

- 触发：`BOM` 的 `on_submit` → `auto_copy_bom_on_submit(doc, method)`（`work_order_task/work_order_task/doc_events.py` 约 400 行）。
- 复制逻辑：`work_order_task/work_order_task/work_order_task/utils/bom.py`：
  - 前缀映射（约 25–29 行）：`{"波兰PL包装成品#": "PLBZCP#", "美东USNJ包装成品#": "USNJBZCP#", "美中USTX包装成品#": "USTXBZCP#"}`
  - `copy_bom_with_new_item`（约 147 行）：`new_bom = frappe.copy_doc(original_bom)` —— **整张 BOM 复制（含 items + operations）**，粒度是「**整张 BOM**」，不是逐物料。
  - 复制的字段替换（约 168–172 行）：
    - 成本取价方式：`rm_cost_as_per = "Price List"`，`buying_price_list` 按分支取（USTX = `美中USTX标准采购`）；
    - `items`：只保留 `item_group == "PP棉"`，并做特殊替换 `PPM1500-7D51-SILICONIZED-NEW → PPM1500-15D64-SILICONIZED-NEW`；
    - `operations`（`workstation_type in ("包装",)` 或为空时）：改写 `workstation = 目标工站`、`hour_rate_labour`、`hour_rate_manage`、`hour_rate`，并重算 `operation_labour`、`operation_manage_cost`、`op.operating_cost`（= `rate/60 × time`）；
    - 落库：`new_bom.docstatus=0; is_active=1; insert(); submit()`。

## 复算方法（167.8 → 105）

规则（与 ERPNext + 自定义一致）：

```
new_hour_rate = 105 + hour_rate_manage(34.24)          # 电费/租金/耗材仍为 0
new_op_cost   = time_in_mins / 60 × new_hour_rate
new_total     = raw_material_cost + new_op_cost + scrap_material_cost(=0)
delta         = new_total − total_cost
```

- **只对 `hour_rate_labour == 167.8` 的工序行做替换**；其余工序（如仍在 `包装` 工站、labour=0）与无工序的 BOM，`delta = 0`。
- 物料成本保持原值（不随工资率变）。
- 复算脚本：`tongtool_order_cost/out/ustx_wage_sim/build_sim.py`（常量 `OLD_LABOUR=167.8` / `NEW_LABOUR=105.0` / `MANAGE=34.24`）。
- 输入：`tongtool_order_cost/out/ustx_wage_sim/_raw_bom_ops.tsv`（USTX BOM ⋈ 工序的原始抽取）+ 表快照 `.../en_bom_cost/EN产品BOM成本列表20260202.csv`（仅用于反查重量模板 + 交叉核对 sheet 值）。

**结果**：`n_boms=309`、`n_boms_affected=304`、`n_boms_no_operation=3`、净工费率 `202.04 → 139.24`、`sum_delta = −7,217.3057`（全量逐 BOM 求和）、`sum_delta_active_default_only = −5,884.464667`。

> 口径提醒：上述 sum 是「每张 BOM 各计一次」的等权求和；换算成某月金额需按该 USTX 物料的**发货/生产数量**加权。逐行结果见 `ustx_bom_ops.csv`。

## 未证实 / 存疑

1. **Sheet 是快照**：sheet 里的「美中加工成本, USTX」是 **2026-09-03** 的默认 BOM；此后（如 2026-09-15）部分物料新增 BOM 并改了默认，故今天按 `is_active+is_default` 复跑的值与 sheet 旧值不同（例：`USTXBZCP#KS0455-92x56x75` sheet=206.479 对应 -001；现默认 -006=90.306）。
2. **重量模板来源**：`ZLMB#` 由基础产品编号按 `-` 拆分推导，USTX 物料本身**无** `weight_template_variant` 字段值（全库 0 条）；本 CSV 的 `weight_template` 由 sheet 的「美中包装成品USTX编号 → 重量模板编号」反查得到，个别 USTX 物料可能对应多个 ZLMB（本次 47 行为多值）。
3. **公式 override**：ERPNext 标准会在 BOM validate 时按 `hour_rate × time/60` 重算 `operating_cost`；本案例两者一致（0 例外），但**未逐行验证**自定义 override 是否显式改写该公式（`overrides/bom_override.py` 的 `CustomBOM` 未见改写 total/operating 公式，仅同步 routing 属性）。
4. **`bom_cost_list*.json.gz` 不含工资率**（已核实）：私有目录 `sites/erpnext.vilavi.cn/private/files/` 下有 192 个 `bom_cost_list_*.json.gz` / `bom_cost_list_v2_*.json.gz`，内容是 `BOM Cost List V2` 报表的**序列化输出**（顶层键 `chart/columns/execution_time/message/report_summary/result/status`）。列含 `ustx_valuation_rate`（＝加工成本结果值）与 `operation_1_name` / `operation_1_time` / `operation_2_name` / `operation_2_time`（只有工序名 + 时间），**无 `hour_rate` / `hour_rate_labour` / `time_in_mins` 原始字段** → 它只是同一结果的只读快照，**不是**工资率的另一来源。写入方引用见 `delivery_plan/doc_events:1477`、`tongtool_integration/sync/order_sync.py:2362`、`vilavi_pim/.../item_group_cost_service.py:9`（均指向 V2 报表模块）。
5. **`BOM 成本回写任务`（旁证）**：`bom_cost_logs/bom_cost_update_*.log` 显示后台任务「更新所有激活且默认的BOM总成本到物料成本价」——把 active+default BOM 的 `total_cost` 回写到 `Item` 成本价（与 `get_item_valuation_rate` 的回退口径一致）。该回写是否覆盖 USTX 物料本次未逐行核对（**待补**）。
6. **`Tongtool Settings` 是 Single doctype**（已核实）：它不存在独立表（故 `SELECT ... FROM \`tabTongtool Settings\`` 报 `1146`），实际存于 `tabSingles`（doctype='Tongtool Settings'，字段 27 个：sync/package/refresh/last_leg_fee 等）。**其中没有 `bom_cost_file_name` 等 bom_cost_* 键** → 代码里 `settings.bom_cost_file_name` 所指的设置对象**未确认**（可能为其它版本/对象的引用），`bom_cost_list*.json.gz` 的落盘触发方**待补**（不影响本规格的成本结论）。

## 证据清单（路径:行号）

**EN 服务器（生产 `erpnext.vilavi.cn`，只读 SQL / 代码阅读）**

- `apps/work_order_task/work_order_task/work_order_task/utils/bom.py`
  - `copy_bom_for_supporting_items`（约 6 行）、`prefix_mapping`（约 25–29 行）、`copy_bom_with_new_item`（约 147 行）、字段替换（约 168–172 行）
- `apps/work_order_task/work_order_task/doc_events.py`
  - `update_hour_rate`（约 386 行）、`auto_copy_bom_on_submit`（约 400 行）
- `apps/work_order_task/work_order_task/utils/workstation.py` → `get_hour_rate_update`（约 163 行，`Hour Rate` 查询）
- `apps/work_order_task/work_order_task/doctype/hour_rate/hour_rate.json` / `.py`（自定义 DocType `Hour Rate`）
- `apps/work_order_task/work_order_task/overrides/bom_override.py` → `CustomBOM.get_routing` / `sync_attributes_to_operations`
- `apps/work_order_task/work_order_task/report/bom_cost_list_v2/bom_cost_list_v2.py`
  - `get_item_valuation_rate`（约 541–566 行）、`get_default_bom_and_cost`（约 96 行）、`get_zlmb_info`（约 357/378 行）、`get_ustxbzcp_info`（约 797 行）、列定义（约 1278/1636 行）
- 只读校验（生产库）：
  - `Workstation` `美中USTX包装`：`hour_rate_labour=167.8`、`hour_rate_manage=34.24`、`hour_rate=202.04`
  - `tabHour Rate`：0 行；`Workstation.rel_hour_rate`：全部 NULL
  - 309 张 `USTXBZCP#%` BOM：`total_cost = raw + operating + scrap`（0 例外）、`BOM.operating_cost = Σ 工序 operating_cost`（0 例外）

**本仓库（worktree）**

- `tongtool_order_cost/out/ustx_wage_sim/build_sim.py`（复算脚本，常量 `OLD_LABOUR=167.8` / `NEW_LABOUR=105.0` / `MANAGE=34.24`）
- `tongtool_order_cost/out/ustx_wage_sim/_raw_bom_ops.tsv`（原始抽取：USTX BOM ⋈ 工序）
- `tongtool_order_cost/out/ustx_wage_sim/ustx_bom_ops.csv`（309 行逐 BOM 复算结果）
- `tongtool_order_cost/out/ustx_wage_sim/summary.json`（汇总 + 假设 + 存疑）
- `tongtool_order_cost/out/profitability_audit/2026年7月订单_ustx2/en_bom_cost/EN产品BOM成本列表20260202.csv`（2026-09-03 sheet 快照，70 列；col18=`美中包装成品, USTX 编号`、col20=`美中加工成本, USTX`、col24=`重量模板, 编号`）
