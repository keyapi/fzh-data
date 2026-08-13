---
okf: v0.1
type: Solution
title: 发货仓库过滤 + 多文件通途上传 + 跨页勾选持久化 + 按仓库分组批量面单
description: Transactions 增加发货仓库过滤；通途上传支持多文件；勾选跨页持久化；批量创建面单按仓库分组并默认填充服务类型
timestamp: 2026-08-13
tags: [sellfox-shipping, warehouse-filter, multi-file-upload, selection-persist, batch-label-grouping]
---

# 发货仓库过滤 + 多文件上传 + 跨页勾选 + 按仓库分组批量面单

## 需求背景

1. Transactions 需要按「发货仓库」（基本信息 `warehouse_name`）过滤。
2. 通途订单上传一次只能一个文件，需支持多文件批量匹配（美中按仓库分成多个 xls）。
3. 勾选包裹后切页，勾选丢失，且跨页勾选数量不累加。
4. 批量创建面单时，美东/美中混选需不同的承运商与服务类型（NJ→FedEx-Economy-10-USEA，TX→FedEx-Ground-J-TX）。

## 实现

| 文件 | 内容 |
|---|---|
| `package_models.py` | `PackageListItem` 新增 `warehouse_name` |
| `package_repository.py` | list/count 加 `warehouse_name` 过滤；list_packages 映射 `warehouse_name` |
| `package_service.py` | `PackageListRequest` 加 `warehouse_name` 过滤，`ListPackagesService` 透传 |
| `app.py` | `/packages` 加 `warehouse` 参数；`/tongtool/upload` 改多文件；`batch-create-labels` 支持 `groups` 格式 |
| `templates/packages.html` | 发货仓库下拉、跨页勾选持久化、按仓库分组批量面单弹窗、默认服务类型 |
| `templates/tongtool_upload.html` | 文件多选 + 分文件统计 |

## 关键设计

### 1. 发货仓库过滤
- `/packages` 加 `warehouse` 查询参数，映射到 `PackageRow.warehouse_name`。
- 下拉选项：CENTRADE(美东)、DANEEY(美中)、POLAND(波兰)、虚拟仓库。

### 2. 多文件通途上传
- `form.getlist("file")` 循环处理，每个文件独立匹配（各自从文件名提取仓库/方式）。
- 结果聚合：total/matched/unmatched 累加，多文件时显示「分文件统计」表。

### 3. 跨页勾选持久化（sessionStorage）
- 选择存储为 `{ package_sn: warehouse_name }` 映射，key `sellfox_selected_packages_v2`。
- `updateBatchBar()` 只更新 UI，不持久化；持久化仅在用户勾选（`onCheckboxChange`）时触发，避免切页时空勾选覆盖。
- 踩坑：① 变量 `selectedStorageKey` 声明在 IIFE 之后导致恢复读 undefined；② 旧版数组格式 sessionStorage 残留导致分组错乱，换 key + 防御解析解决。

### 4. 按仓库分组批量创建面单
- `getSelectedByWarehouse()` 按仓库分组选中包裹。
- 弹窗 `openBatchCreateModal()` 为每个仓库渲染独立的承运商 + 服务类型下拉。
- 后端 `batch-create-labels` 接受 `groups: [{carrier, service_level, package_sns}]`，兼容旧 flat 格式。
- 默认服务类型：DANEEY→`FedEx-Ground-J-TX`，CENTRADE→`FedEx-Economy-10-USEA`。

### 5. 批量操作栏浮动遮挡修复
- `.container` class 被复用 3 次（含标签容器），`padding-bottom` 加在 `.container` 会把表格下推；改为加在 `body` 上。

## 验证

- `uv run pytest tests/sellfox_shipping -q`：**312 passed, 2 warnings**。
- 浏览器验证：发货仓库过滤、多文件上传、跨页勾选累加、按仓库分组弹窗、默认服务填充。

## 边界 / 后续

- 蜴国际产品（sm_code）与发件人绑定：美中 TX 用 `FedEx-Ground-J-TX`，美东 NJ 用 `FedEx-Economy-10-USEA`（之前曾误报「发货地址不存在」是选错产品）。
- 默认服务映射当前仅覆盖 DANEEY/CENTRADE，其余仓库走「（自动）」。
