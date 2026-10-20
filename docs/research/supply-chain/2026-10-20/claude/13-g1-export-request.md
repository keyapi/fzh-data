---
okf: v0.1
type: Reference
title: G1 脱敏导出请求清单（三角靠枕 × 两仓 × 2026-04..09）
description: 给业务/仓库/财务的导出字段、范围、脱敏规则、文件命名与验收检查
date: 2026-10-20
tags: [supply-chain, g1, export, anonymization]
---

# 13 — G1 脱敏导出请求清单

> 来源选项：**业务导出**（用户 2026-10-20 确认）。Claude 只读文件，不访问生产、不写业务系统。
> 目标：支撑 G1 契约回放（映射、需求冲减、生产四量、互斥余额、收货分摊、异常清单）。

## 1. 范围

| 项 | 值 |
|---|---|
| 品类 | 三角靠枕 family：EN 叶子物料组 `KS0001 三角靠枕` + `KS0248 三角靠枕无扣` |
| 仓 | 美中-FZH-DANEEY + 美东-CENTRADE |
| G1 窗口 | 2026-04-01..2026-09-30（6 个月） |
| 可选 G2/G3 | 2023-01-01..2026-09-30（如导出方便；PR #304 核心集为 2023-01..2026-07） |
| 粒度 | 订单/包裹行、单据行、SKU × 仓 × 日/月 |

## 2. 需要的文件与字段

### A. 通途库存快照（每仓每日或至少月末）

- 快照时间、仓库、通途 SKU、可用量、在途量、库存状态（良品/不良/退货）。
- 如有多个库存状态，保留状态列，不要先汇总。
- 文件：`inventory_<warehouse>_<date>.csv/xlsx`。

### B. 通途订单/包裹行

- 发货日期、通途 SKU、平台 SKU、解析后 SKU、发货数量、渠道、渠道账号、发货仓库、包裹号、跟踪号、订单号。
- 保留原始行号（或导出时加 `source_row_no`）。
- 文件：`orders_<month>.csv/xlsx`；可按月分文件。

### C. EN 单据（如业务能导出）

- SO / SO Item：name、item_code、qty、delivered_qty、status、transaction_date、delivery_date。
- Production Plan / Work Order / Job Card：name、work_order、sales_order_item、operation、sequence、total_completed_qty、status、docstatus。
- 已提交 Manufacture Stock Entry：name、work_order、item_code、qty、is_finished_item、posting_date、docstatus。
- 已提交 Delivery Note：DN Item `name`、parent、so_detail、against_sales_order、item_code、qty、posting_date、docstatus。
- 文件：`en_<doctype>_<period>.csv/xlsx`。

### D. 采购/在途

- 通途采购单：PO 号、SKU、数量、下单日、预计到货日、仓库、状态。
- 文件：`purchase_orders_<period>.csv/xlsx`。

### E. 头程（如有）

- 批次/票号、EN SO 号、DN 号、装柜/离厂/到港/清关/入仓日期、数量、状态、来源。
- 没有结构化数据就标 `unknown`，不要用“订单日期 + 3 个月”冒充事实。
- 文件：`headhaul_<period>.csv/xlsx`。

### F. 映射表

- EN item_code（KS0001/KS0248 及其变体）、通途 SKU、客户物料号、状态（启用/停用）。
- 仓库别名族（新名/旧名/退货仓/半成品仓）。
- 渠道别名（Amazon/Wayfair/OSTK/PB/Mirakl/…）。
- 文件：`mapping_items.csv`、`mapping_warehouses.csv`、`mapping_channels.csv`。

## 3. 脱敏规则

- **删除/替换**：客户姓名、收货地址、电话、邮箱、买家 ID、支付信息。
- **保留**：source row id、日期、数量、SKU、物料号、仓库、渠道、单据号（可哈希）、状态、docstatus。
- 订单号/包裹号如需保留关联，用稳定哈希或内部流水号替换，不要保留原始平台单号（如业务允许可保留）。
- 不导出凭证、账号、密钥。
- 文件只放本地/NAS 指定目录，**不入 git**。

## 4. 验收检查（Claude 收到文件后先跑）

- [ ] 文件清单齐全，行数与日期范围与导出说明一致。
- [ ] 两个仓都有数据；2026-04..09 每月都有记录。
- [ ] KS0001 / KS0248 映射覆盖率与未匹配清单。
- [ ] 订单/包裹行、DN/SE 行的 source row id 可追溯。
- [ ] 无客户 PII、无凭证。
- [ ] 缺失/坏数量/歧义单列，不静默丢弃。

## 5. 命名与交付

```text
g1_export_20261020/
├── inventory/
├── orders/
├── en/
├── purchase/
├── headhaul/
├── mapping/
└── manifest.md          # 导出范围、时间、行数、字段、已知缺失
```

> 如果业务只能先给一部分，先给 **A+B+F**（库存、订单、映射）即可启动 G1 的映射与需求冲减；
> EN 单据和采购/头程可以后补，但缺失项必须标 `unknown`，不能补 0。
