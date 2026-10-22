# EN 销售订单（SO）代表性侦察

> 只读 GET；预算：单线程、≤300 次、page_length ≤100、间隔 ≥200ms。
> 只写看到的字段/数字；不猜测含义、不写“应如何下单”。

## 1. 预算与请求

- 请求 **122** 次（上限 300）；耗时 **24.4 s**；停止原因：无（正常完成）
- 按路径：{'/api/resource/Company': 1, '/api/resource/Sales Order': 16, '/api/resource/Sales Order/<doc>': 52, '/api/resource/Custom Field': 1, '/api/resource/DocType': 1, '/api/resource/Delivery Plan': 1, '/api/resource/Delivery Plan/<doc>': 1, '/api/method/frappe.client.get_list': 25, '/api/method/frappe.client.get_count': 24}

## 2. 结构与字段（实测）

- 样本 SO 的 header 字段数 / item 字段数：d9eec23e48f1 header 75 / item 75；072dfe1061d0 header 75 / item 75
- header 中与发货/计划/扫码相关的实测字段：`billing_status`, `custom_attach_file_customer_item_code`, `delivery_date`, `delivery_status`, `docstatus`, `packed_items`, `per_delivered`, `per_picked`, `skip_delivery_note`, `status`
- Custom Field（Sales Order / Sales Order Item，最多 100 条）：

| dt | fieldname | label | fieldtype | options |
|---|---|---|---|---|
| Sales Order | `custom_attach_file_customer_item_code` | Attach File Customer Item Code | Attach |  |
| Sales Order | `custom_filters` | Filters | Section Break |  |
| Sales Order | `custom_item_group` | Item Group | Link | Item Group |
| Sales Order | `custom_process_file_customer_item_code` | Process File Customer Item Code | Button |  |
| Sales Order | `exempt_from_sales_tax` | Is customer exempted from sales tax? | Check |  |
| Sales Order | `type_of_manufacturing` | Default Manufacturing Type | Select | In House
Subcontract
Material Request |
| Sales Order Item | `custom_fba_sku` | FBA SKU | Data |  |
| Sales Order Item | `custom_label_combination` | Label Combination | Link | Label Combination |
| Sales Order Item | `custom_tongtool_item_name` | TongTool Item Name | Data |  |
| Sales Order Item | `plan_reserved_stock_qty` | Plan Reserved Stock Qty | Float |  |
| Sales Order Item | `type_of_manufacturing` | Manufacturing Type | Select | In House
Subcontract
Material Request |

- 名称含 Delivery 的 doctype：['Delivery Note Item Cat', 'Delivery Note Outer Box Summary', 'Delivery Plan', 'Delivery Plan Item', 'Delivery Plan Item Cat', 'Delivery Plan Item Qty', 'Delivery Plan Item Unfinished Good', 'Delivery Note', 'Delivery Note Item', 'Delivery Settings', 'Delivery Stop', 'Delivery Trip', 'Shipment Delivery Note']

- `Delivery Plan` 单条实测：`06d5e701936f`，header 33 字段 / item 33 字段；相关字段：['allocate_from_staging_warehouse', 'docstatus', 'total_actual_delivered_qty', 'total_planned_delivery_qty']；关联键候选：['is_dn_pending', 'is_strict_so_source', 'merge_so_detail_rows_in_dn', 'sale_orders']

## 3. 月度规模（2024-10..2026-09，24 个月）

| 月份 | 总数 | draft(0) | submitted(1) | cancelled(2) |
|---|---:|---:|---:|---:|
| 2024-10 | 0 | 0 | 0 | 0 |
| 2024-11 | 7 | 0 | 3 | 4 |
| 2024-12 | 14 | 0 | 13 | 1 |
| 2025-01 | 2 | 0 | 2 | 0 |
| 2025-02 | 23 | 0 | 21 | 2 |
| 2025-03 | 18 | 0 | 18 | 0 |
| 2025-04 | 23 | 0 | 21 | 2 |
| 2025-05 | 21 | 0 | 21 | 0 |
| 2025-06 | 27 | 0 | 27 | 0 |
| 2025-07 | 24 | 0 | 24 | 0 |
| 2025-08 | 28 | 0 | 27 | 1 |
| 2025-09 | 22 | 0 | 22 | 0 |
| 2025-10 | 13 | 1 | 11 | 1 |
| 2025-11 | 2 | 0 | 2 | 0 |
| 2025-12 | 0 | 0 | 0 | 0 |
| 2026-01 | 10 | 0 | 6 | 4 |
| 2026-02 | 0 | 0 | 0 | 0 |
| 2026-03 | 31 | 0 | 30 | 1 |
| 2026-04 | 14 | 1 | 11 | 2 |
| 2026-05 | 11 | 0 | 11 | 0 |
| 2026-06 | 17 | 0 | 16 | 1 |
| 2026-07 | 12 | 0 | 12 | 0 |
| 2026-08 | 14 | 0 | 14 | 0 |
| 2026-09 | 12 | 1 | 11 | 0 |

- 2026-10 为**部分月**（截至扫描日），不计入 24 个月：总数 12，docstatus {'1': 12}。

## 4. 代表性样本（50 条，分层）

- 分层：3 年 × 5 家公司，每层最多 20 条，轮转取 50；公司层不足时按年回填（回填 0 条）。
- 实际取得 **50** 条；样本构成：{'so': 50, 'items': 1874, 'companies': {'FZH': 50}, 'years': {'2024': 17, '2025': 17, '2026': 16}, 'warehouses': {'半成品仓 - FZH': 1477, '仓库 - FZH': 64, '成品仓 - FZH': 325, '包材仓 - FZH': 8}, 'docstatus': {'2': 10, '1': 40}}

## 5. 关联覆盖（仅样本内）

| 位置 | 字段 | present | nonempty |
|---|---|---:|---:|
| header | `billing_status` | 50 | 50 |
| header | `custom_attach_file_customer_item_code` | 48 | 48 |
| header | `delivery_date` | 50 | 50 |
| header | `delivery_status` | 50 | 50 |
| header | `docstatus` | 50 | 50 |
| header | `packed_items` | 50 | 4 |
| header | `per_delivered` | 50 | 32 |
| header | `per_picked` | 50 | 0 |
| header | `skip_delivery_note` | 50 | 0 |
| header | `status` | 50 | 50 |
| item | `customer_item_code` | 1874 | 1147 |
| item | `delivered_by_supplier` | 1874 | 0 |
| item | `delivered_qty` | 1874 | 561 |
| item | `delivery_date` | 1874 | 1874 |
| item | `docstatus` | 1874 | 1874 |
| item | `ensure_delivery_based_on_produced_serial_no` | 1874 | 0 |
| item | `item_code` | 1874 | 1874 |
| item | `picked_qty` | 1874 | 0 |
| item | `plan_reserved_stock_qty` | 1874 | 0 |
| item | `planned_qty` | 1874 | 0 |
| item | `production_plan_qty` | 1874 | 769 |
| item | `warehouse` | 1874 | 1874 |

- 仅样本内 present/nonempty 计数，不推测全量覆盖率

## 6. 模式初判（样本内数字）

- 皮壳/内胆配对：{'both': 28, 'neither': 19, 'cover_only': 2, 'inner_only': 1}
- 每单行数：{'min': 1, 'median': 31.0, 'max': 135}
- 单行数量：{'n': 1874, 'p10': 8.0, 'p50': 20.0, 'p90': 50.0, 'max': 1000.0}
- 下单→交期天数（代理）：{'n': 1874, 'median': 15.0, 'min': 0, 'max': 36}
- 未发货（submitted 且 per_delivered<100）：{'so_total': 40, 'unshipped': 35, 'ratio': 0.875}
- 已过交期且未发（item 行）：1356
- 状态分布：{'Cancelled': 10, 'Closed': 30, 'To Bill': 5, 'To Deliver and Bill': 5}

## 7. 看到 / 看不到

- 看到：SO header/item 的实际字段名；`Delivery Plan` 是独立 doctype，header 有 `sale_orders`、item 有 `sales_order`/`so_detail`（可作 SO↔出库计划关联键）；24 个月 SO 数量与 docstatus；50 条样本的 items、发货字段与样本内模式数字。
- 看不到：字段的业务含义（只测到存在与取值）、全量覆盖率（样本内计数）、SO 文档内没有直接的 Delivery Plan 链接字段；**SO / SO Item / Delivery Plan 实测量均未出现 scan/qr 字段**，扫码关联未在本轮看到。
- 本报告不给出下单建议，也不推断未观测到的关系。

## 8. 复现

```bash
uv run python docs/research/supply-chain/2026-10-20/claude/experiments/auto_order/recon_so.py
uv run python scripts/check_secrets.py
```

凭证从 `EN_API/.env` 读取，未打印/未落盘；输出只含哈希 id 与必要字段。

