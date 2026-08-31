---
okf: v0.1
type: Solution
title: 通途发货仓库/方式标记 + 批量面单服务类型与一键审核 + 导出增强
description: 从通途上传文件名提取发货仓库/方式并持久化；批量创建面单支持服务类型选择、审核未通过一键通过重试、操作栏浮动；导出 Excel 增列
timestamp: 2026-08-13
tags: [sellfox-shipping, tongtool, warehouse, shipping-method, batch-label, export]
---

# 通途发货仓库/方式标记 + 批量面单增强 + 导出增列

## 需求背景

美中（DANEEY/TX）包裹在蜴国际导出前需要按「退货仓/半成品仓/成品仓/皮壳仓」分仓，且发货方式（蜴国际/尾程七条/Vite/USPS）不同。同事在通途 xls 上传时用文件名标识仓库与方式，例如文件名含「皮壳」「退货」「半成品」「成品」「蜴国际」。需要在系统中：

1. 上传通途文件时从**文件名**提取发货仓库与发货方式，持久化到包裹。
2. Transactions 支持按这两个字段过滤。
3. 批量创建面单时支持选择服务类型、审核未通过时一键通过重试。
4. 批量操作栏改为视口底部浮动。
5. 导出 Excel 增加通途相关列。

## 实现

| 文件 | 内容 |
|---|---|
| `migrations/versions/0024_tongtool_shipping_warehouse.py` | `shipping_packages` 加 `tongtool_shipping_warehouse` |
| `migrations/versions/0025_tongtool_shipping_method.py` | `shipping_packages` 加 `tongtool_shipping_method` |
| `package_repository.py` | PackageRow 两列；list/count 加过滤；mark/clear/get 支持两字段 |
| `package_models.py` / `package_service.py` | PackageListItem + PackageListRequest 加字段与过滤 |
| `tongtool_service.py` | `_warehouse_from_filename` / `_shipping_method_from_filename` 提取规则 |
| `app.py` | `/packages` 加过滤；`/api/lizard-services` 新增；`/api/packages/batch-review` 新增；batch-create 接受 `service_level`；batch-export 增列 |
| `templates/packages.html` | 过滤下拉、表格列、批量弹窗服务类型、一键通过重试、浮动操作栏 |
| `templates/package_detail.html` | 基本信息面板显示通途发货仓库/方式 |

## 文件名提取规则

### 发货仓库（`_warehouse_from_filename`）

| 文件名含 | 写入值 |
|---|---|
| 皮壳 | `FZH-DANEEY-皮壳仓库` |
| 退货 | `FZH-DANEEY-退货产品仓` |
| 半成品 | `FZH-DANEEY-半成品仓` |
| 成品 | `FZH-DANEEY-成品仓` |

> **关键**：半成品必须在成品之前检查（"半成品"包含"成品"二字）。

### 发货方式（`_shipping_method_from_filename`）

| 文件名含 | 写入值 |
|---|---|
| 蜴国际 | `蜴国际` |

后续可扩展：尾程七条、vite、usps（在函数注释处加 `if "xxx" in name: return "xxx"`，模板下拉框同步加 `<option>`）。

## 批量创建面单增强

1. **服务类型下拉**：弹窗按承运商动态切换（VITE: GOFO_PARCEL/FEDEX_GROUND；蜴国际: 从 `/api/lizard-services` 获取 sm_code）。后端 `batch-create-labels` 接受 `service_level` 传入 `LabelService.create_label`。
2. **一键通过并重试**：批量创建失败时若错误含 `approved`，显示「N 个包裹审核未通过」+「一键通过并重试」按钮。点击调 `POST /api/packages/batch-review` 批量 approve，再自动重试创建。
   - 注意：`onclick` 不得内嵌 `JSON.stringify`（双引号会打断 HTML 属性），改为存全局变量 `_bcNeedApprove`，按钮无参调用。
3. **浮动操作栏**：`#batch-bar` 由表格下方内联改为 `position: fixed; bottom: 20px; left: 50%; transform: translateX(-50%); z-index: 999`，随视口浮动。

## 导出 Excel 增列

`POST /api/packages/batch-export` 现为 20 列：

| 列 | 取值 |
|---|---|
| 追踪号 | 面单记录中有效追踪号（非取消、有追踪号的最近一条） |
| 赛狐追踪号 | 基本信息 `logistics.tracking_number`（赛狐原始值，可能是 packageSn 占位） |
| 通途包裹号 | 通途标记 `tongtool_p_numbers`（如 `P81739868`） |
| 通途发货仓库 | `tongtool_shipping_warehouse` |
| 通途发货方式 | `tongtool_shipping_method` |

## 验证

- `uv run pytest tests/sellfox_shipping -q`：**312 passed, 2 warnings**。
- 浏览器验证：过滤下拉/表格列/详情面板/浮动操作栏/一键通过重试流程均正常。
- 导出 CSV 20 列表头与数据行正确。

## 边界 / 后续

- 蜴国际产品（sm_code）与发件人绑定：美中 TX 用 `FedEx-Ground-J-TX`，选 `FedEx-Economy-10-USEA`（绑 CA）会报「发货地址不存在」——选对产品即可，非代码问题。
- 通途清单重新上传仍为叠加标记，未实现「清除旧标记再重建」。
