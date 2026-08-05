---
okf: v0.1
type: Index
title: 参考文档 — API 端点 + 字段映射
description: ERPNext API 端点、字段说明、数据源速查
tags: [erpnext, api, reference]
---

# 参考文档

## API 端点

| 用途 | 端点 | 关键参数 |
|------|------|---------|
| 工单列表 | `GET /api/resource/Work Order` | `filters`, `fields`, `limit` |
| 单个工单 | `GET /api/resource/Work Order/{name}` | 返回含 operations 子表 |
| Job Card 列表 | `GET /api/resource/Job Card` | `filters=[["work_order","=",wo]]` |
| 单个 JC | `GET /api/resource/Job Card/{name}` | 返回含 time_logs 子表 |
| Stock Entry | `GET /api/resource/Stock Entry` | `stock_entry_type=Manufacture` |
| Version 记录 | `GET /api/resource/Version` | `ref_doctype=Work Order` |

## 关键字段

### Work Order

| 字段 | 含义 | 注意 |
|------|------|------|
| `production_item` | 产品编码 | KS=成品, PK#/ND#=半成品 |
| `open_material_qty` | 开料量 | 半成品=0异常 |
| `produced_qty` | 系统产出量 | 可能被一键完工虚报 |
| `operations` | 工序子表 | 只在单条查询返回 |
| `status` | 工单状态 | Completed/In Process/... |

### Job Card

| 字段 | 含义 | 注意 |
|------|------|------|
| `owner` | 创建人 | ≠ employee |
| `time_logs` | 工时记录子表 | 含 employee 字段, 单条查询才返回 |
| `time_logs[].employee` | 真实员工 ID | HR-EMP-00001=虚拟 |
