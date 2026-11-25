---
okf: v0.1
type: Reference
title: pandas 兜底回填的 NaN 写进 Frappe decimal → 整单 save 失败（mask 里 NaN != 0 为真）
date: 2026-11-25
category: integration-issues
module: tongtool_integration
problem_type: integration_issue
component: tongtool_integration
severity: medium
symptoms:
  - "订单同步日志：nan can not be used with MySQL（物料成本 / 差额分摊 / 尾程分摊三步连续失败）"
  - "订单主数据已同步，但子表成本、尾差、尾程停留在旧值（多为 0）"
  - "只在启用「重量模板成本兜底」且 SKU 无重量模板时出现（如套件 TJ# 开头）"
root_cause: "pandas 分组回填把 0 覆盖成 NaN（NaN != 0 为 True），且成本函数对 BOM 取值无 NaN 防护；flt(nan) 仍是 nan"
resolution_type: "源头 mask 加 notna + 成本列 fillna(0)；取值前统一清洗 NaN"
tags: [pandas, nan, frappe, decimal, erpnext, order-sync, data-pipeline, tongtool]
---

# BOM 兜底 NaN 写库失败：pandas 回填 + Frappe decimal

## Problem

`tongtool_integration` 订单同步在写子表成本时抛 `nan can not be used with MySQL`，
该订单的「物料成本 → 金额差异分摊 → 尾程费用」三步后处理全部失败（各自 try 里 save 时报同一个错），
成本/尾差/尾程停留在旧值。2026-11-07 起累计 86 条 Error Log / 17 张订单，低频但长期存在。

## Symptoms

- Error Log：`更新订单后更新物料成本失败 {order_id_code}: nan can not be used with MySQL`（同一单另有两条同因）。
- 订单本身在库里，`order_items` 的成本列多为 0；`modified` 只到第一次 save 的时间。
- 触发条件：`Tongtool Settings.enable_bom_cost_backfill = '启用重量模板成本兜底'`，且 SKU 在 BOM 成本表里
  `重量模板编号` 为空（套件/新上架常见）。

## What Didn't Work

- **只给 `flt()` 加参数**：`frappe.utils.flt(float('nan'))` 仍返回 `nan`（实测），`nan or 0` 也仍是 `nan`
  —— 既有 `flt((value or 0) * qty, 4)` 写法根本拦不住 NaN。
- **只在 `cover_weight` 判断 `is not None`**：`NaN is not None` 为真，照样写入。
- **用 `refresh_single_order` 修数据**：不再报错，但成本仍为 0 —— 刷新路径会重新解析拆包系数，
  把仓库判成 `warehouse_unconfirmed`，成本守卫直接跳过（见下）。

## Solution（已上线：PR #29 / `eaef7f2`）

两处改动都在 `tongtool_integration/sync/order_sync.py`：

1. **源头（`_fill_missing_bom_cost_data`）**
   - 回填 mask 由 `(df[col] == 0) & (df[max_col] != 0)` 改为
     `(df[col] == 0) & df[max_col].notna() & (df[max_col] != 0)`。
     `groupby` 会丢弃分组键为 NaN 的行（无重量模板），merge 后 `*_max` 为 NaN，
     而 **`NaN != 0` 为 True**，旧条件会把 0 回填成 NaN。
   - 合并回填后补 `df[cost_fields] = df[cost_fields].fillna(0)`，防止 NaN 外泄给上层。
2. **纵深防御（`_update_order_item_cost_from_bom`）**
   - 取到 BOM 行后立刻清洗：`float('nan') -> 0.0`，再进入所有分支（FBA / 皮壳 / 成品 / 半成品 / 默认）。
   - 不同分支约 40 处 `bom_row.get(...)` 无需逐处改，覆盖面更稳。

**历史数据修复**：17 张受影响订单里 6 张重算成功（成本 0 → 48/96）；11 张仍是 0，
原因是 `match_status_code` 为空（legacy 未确证），成本守卫按设计拒绝写入 —— 需先做物料匹配确证，不是本 bug。

## 验证方法（只用生产 BOM 文件，不改数据）

- 把生产 BOM `json.gz` 喂给修补后的 `_fill_missing_bom_cost_data`：4086 行 **0 行 NaN**（修复前 265 行 / 261 SKU）。
- 内存里构造订单子表做 dry-run（不进库）：
  - `doc.flags.split_factor_applied = True` 模拟同步态，跳过重新解析拆包系数；
  - 子表行需手动设 `it.name = "row-1"`（`item_technical_key` 用行 name，未保存的子行 name 为空会被判 `missing_child_identity`）；
  - `match_status_code` 取 `item_match_resolver.MATCHED_STATUSES` 中任一值。
- 回归：随机 20 行，NaN=0 且 `cost_fg` 与 BOM 原值逐行一致（无口径漂移）。

## Why This Works

`df[cost_fields]` 在回填前已被 `pd.to_numeric(..., errors='coerce').fillna(0)` 规整过，
所以最终 `fillna(0)` 只可能影响 NaN —— 有重量模板的行数值完全不变。成本侧统一清洗保证：
无论上游哪个分支漏出 NaN，都不会落到 `decimal(21,9)` 列上。

## Prevention

- 任何 **pandas → DocType 字段** 的通道，落库前做一次 NaN 清洗（或整行 `where(pd.notna)`），
  不要指望 `flt()` / `or 0` 兜底。
- 布尔掩码里出现比较运算时，先排除 NaN（`notna()`），尤其在 `!=` 上 —— `NaN != x` 恒真。
- 后处理链用 `try` 分别包住三步时，第一步失败会被后面两条掩盖成"三条错误"；看 Error Log 先按订单聚合。
- 同步任务的健康度要看 app 自己的 Run 记录 + Error Log，不看 `Scheduled Job Log=Complete`。

## Related

- [通途 OpenAPI 大面积 500 的判定](tongtool-openapi-gateway-500-nosuchmethod.md) —— 同一天排查的另一个独立故障
- `supply_chain_visibility/docs/reference/en-custom-apps-and-deploy.md` —— 自定义 app 发布链路（生产远端 `upstream`；改 .py 后必须 restart）
- `tongtool_api/docs/reference/purchase-orders.md` —— 通途货品/采购字段口径
