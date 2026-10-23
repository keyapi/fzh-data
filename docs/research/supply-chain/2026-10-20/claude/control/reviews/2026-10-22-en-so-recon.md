---
okf: v0.1
type: Review
title: EN 销售订单（SO）代表性侦察（只读，122 次 GET）
date: 2026-10-22
owner: claude-worker
status: 完成；只读生产 REST，无任何写入
artifacts:
  - experiments/auto_order/recon_so.py
  - out/auto_order/so_profile.json
  - out/auto_order/so_sample.csv
  - out/auto_order/recon_report.md
---

# EN SO 代表性侦察

> 只做事实侦察：单线程 GET、≤300 次、page_length ≤100、间隔 ≥200ms。
> 不写下单建议；不猜测字段含义；不推断全量覆盖率。
> 凭证从 `EN_API/.env` 读取，未打印/未落盘；输出只含哈希 id 与必要字段。

## 1. 预算与执行

| 项 | 值 |
|---|---|
| 请求数 | **122**（上限 300） |
| 耗时 | **24.4 s** |
| 间隔 / page_length | 0.2 s / 最大 100 |
| 停止原因 | 无（正常完成） |
| 错误 | 0 |
| 写入 | **无**（全部 GET） |

按路径：`Company` 1、`Sales Order` 列表 16、`Sales Order/<doc>` 52、
`Custom Field` 1、`DocType` 1、`Delivery Plan` 1 + `<doc>` 1、
`frappe.client.get_list` 25、`frappe.client.get_count` 24。

## 2. 结构与字段（实测）

- 两条 SO 全文档：header **75** 字段 / item **75** 字段（`so_profile.json structure.sample_sos`）。
- header 中与发货/计划相关的实测字段：
  `billing_status`、`delivery_date`、`delivery_status`、`per_delivered`、`per_picked`、
  `packed_items`、`skip_delivery_note`、`status`、`custom_attach_file_customer_item_code`。
- Custom Field（Sales Order / Sales Order Item，共 11 条）：
  - SO：`custom_item_group`、`type_of_manufacturing`、`custom_attach_file_customer_item_code` 等；
  - SO Item：`custom_fba_sku`、`custom_label_combination`（Link→Label Combination）、
    `custom_tongtool_item_name`、`plan_reserved_stock_qty`、`type_of_manufacturing`。
- 名称含 Delivery 的 doctype 有 **13** 个，包含独立的 **`Delivery Plan`**（及 Item/Item Cat/Qty/
  Unfinished Good 等 child doctype）。
- `Delivery Plan` 单条实测（哈希 `06d5e701936f`）：header 33 / item 33 字段；
  **关联键候选：header `sale_orders`；item `sales_order`、`so_detail`**；
  另有 `is_dn_pending`、`is_strict_so_source`、`merge_so_detail_rows_in_dn`。
- **未发现 scan/qr 字段**：SO header/item、Custom Field、Delivery Plan 实测字段中均无
  `scan`/`qr` 命名；扫码关联本轮**看不到**。
- SO 文档本身没有直接的 Delivery Plan 链接字段；关联在 Delivery Plan 一侧。

## 3. 月度规模（2024-10..2026-09，24 个月）

- 合计 **345 单**；零单月份：**2024-10、2025-12、2026-02**（保留为 0，不跳过）。
- 月度明细见 `recon_report.md §3`（含 draft/submitted/cancelled 分布）。
- **2026-10 为部分月**（截至扫描日）：12 单，未计入 24 个月。

## 4. 代表性样本 50 条

- 分层：3 年 × 5 家公司，每层最多 20 条，轮转；公司层不足按年回填（回填 0）。
- 实际 **50 单 / 1,874 item 行**；年份 2024 **17** / 2025 **17** / 2026 **16**；
  docstatus：submitted 40 / cancelled 10。
- **公司全部为 FZH**：另外 4 家公司在 2024–2026 的 SO 数为 0（实测），
  故公司维度实际退化为单层；仓库维度（来自 items）为：
  半成品仓-FZH 1,477 / 成品仓-FZH 325 / 仓库-FZH 64 / 包材仓-FZH 8。
- `so_sample.csv`：每行一个 item；`so_hash`、`customer_hash` 为哈希，**无客户名/原始单据号**。

## 5. 关联覆盖（仅样本内，不外推）

| 位置 | 字段 | present | nonempty |
|---|---|---:|---:|
| header | `delivery_date` / `delivery_status` / `status` | 50 | 50 |
| header | `per_delivered` | 50 | 32 |
| header | `per_picked` / `skip_delivery_note` | 50 | 0 |
| header | `packed_items` | 50 | 4 |
| item | `delivery_date` / `warehouse` / `item_code` | 1,874 | 1,874 |
| item | `delivered_qty` | 1,874 | 561 |
| item | `production_plan_qty` | 1,874 | 769 |
| item | `planned_qty` / `picked_qty` / `plan_reserved_stock_qty` | 1,874 | 0 |

- SO↔出库计划的关联在 **Delivery Plan** 侧（`sale_orders` / `so_detail`），
  SO 侧无直接链接字段；样本内无法统计 DP 覆盖（只取了 1 条 DP 结构）。

## 6. 模式初判（样本内数字）

| 指标 | 值 |
|---|---|
| 皮壳/内胆（PK#/ND#）配对 | both **28** / neither 19 / cover_only 2 / inner_only 1 |
| 每单行数 | min 1 / median **31** / max 135 |
| 单行数量 | p10 8 / p50 **20** / p90 50 / max 1,000（n=1,874） |
| 下单→交期天数（代理） | n=1,874，median **15**，范围 0–36 |
| 未发货（submitted 且 per_delivered<100） | **35 / 40 = 87.5%** |
| 已过交期且未发（item 行） | **1,356**（样本内，不等于全量积压） |
| 状态分布 | Closed 30 / Cancelled 10 / To Bill 5 / To Deliver and Bill 5 |

## 7. 三条事实结论

1. **结构**：SO header 有 `delivery_date`/`delivery_status`/`per_delivered`/`status` 等
   发货字段；出库计划是独立 `Delivery Plan`，通过 header `sale_orders` 与 item
   `sales_order`/`so_detail` 关联；SO 侧没有直接链接；**scan/qr 字段未观测到**。
2. **规模**：24 个月共 345 单，3 个月为 0（2024-10、2025-12、2026-02）；
   2026-10 部分月 12 单。
3. **样本模式**：50 单中 28 单同时出现 PK# 与 ND#；每单中位 31 行、单行中位 20 件；
   下单到交期中位 15 天；submitted 单中 35/40 的 per_delivered<100（样本内）。

## 8. 看到 / 看不到

- 看到：字段名与出处（doctype/item/custom field）、24 个月计数、50 条样本的 items 与
  发货字段、样本内配对/数量/交期/未发数字、Delivery Plan 的关联键。
- 看不到：字段的业务含义（只测存在与取值）、全量覆盖率、扫码关联（无 scan/qr 字段）、
  SO 侧的 Delivery Plan 直接链接。
- 不给下单建议，不推断未观测关系。

## 9. 复现

```bash
uv run python docs/research/supply-chain/2026-10-20/claude/experiments/auto_order/recon_so.py
uv run python scripts/check_secrets.py   # 无 finding、退出码 0
```

- 生产 REST 只读；预算在脚本内强制（请求上限/间隔/超时即停）。
- 凭证从 `EN_API/.env` 读取；输出无凭证、无客户名、无原始明细。

## 10. 约束自检

| 约束 | 结果 |
|---|---|
| 只新增 `recon_so.py`、`out/auto_order/*`、本记录 | ✅ |
| 只读 GET；无写入、无下单、无配置变更 | ✅ |
| 单线程、≤300 次、page_length ≤100、间隔 ≥200ms | ✅（122 次 / 最大 100 / 0.2s） |
| 超时或 5xx 立即停止 | 代码已实现；本轮 0 错误 |
| 凭证不打印/不提交 | ✅ |
| 不提交原始单据明细；id 哈希 | ✅（`so_hash`/`customer_hash`） |
| 不改主表与既有产物；未改 control 受保护文件 | ✅ |
| 未 push；只提交自己新增文件 | ✅ |
| `check_secrets.py` 无 finding | ✅ |
| 不留临时文件（含 `__pycache__`） | ✅ |
