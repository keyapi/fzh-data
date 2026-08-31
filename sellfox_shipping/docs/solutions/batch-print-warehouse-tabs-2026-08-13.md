---
okf: v0.1
type: Solution
title: 批量打印按仓库两级页签（仓库 → 文档类型）
description: 打印弹窗改为两级页签：一级选仓库（美东/美中-成品仓/美中-其他仓），二级选文档类型（背贴/Label 面单/面单+背贴），按需下载命名文件
timestamp: 2026-08-13
tags: [sellfox-shipping, batch-print, warehouse-group, two-level-tab]
---

# 批量打印按仓库两级页签

## 需求背景

美东、美中打印时需按仓库拆文件：美东只打面单，美中按通途发货仓库分成品仓/其他仓（各含面单+背贴）。打印弹窗需要两级页签——先选仓库，再选文档类型，选好后渲染对应 PDF 并下载命名文件。

## 实现

| 文件 | 内容 |
|---|---|
| `app.py` | 提取 `_print_group_meta()` 分组函数；`batch-print` 加 `group_key` 过滤；新增 `batch-print-groups` 端点；删除旧的 `batch-print-grouped` 及死代码 |
| `templates/packages.html` | 打印弹窗两级页签 + 按仓库/文档类型动态命名下载 |

## 关键设计

### 分组（`_print_group_meta`）

| warehouse_name | tongtool_shipping_warehouse | group_key | label |
|---|---|---|---|
| CENTRADE | — | `east` | 美东 |
| DANEEY | FZH-DANEEY-成品仓 | `meizhong_chengpin` | 美中-成品仓 |
| DANEEY | 皮壳/退货/半成品 | `meizhong_qita` | 美中-其他仓 |
| 其他 | — | None（跳过） | — |

### 后端两个端点

1. `POST /api/packages/batch-print-groups` — 返回分组信息 `{groups: [{key, label, count, has_sticker}], skipped}`，供一级 tab 渲染。
2. `POST /api/packages/batch-print`（改造）— 加 `group_key` 参数，按仓库过滤后按 `document_type`（sticker/label/both）合并单个 PDF。

### 前端两级页签

- 一级 tab：仓库（美东/美中-成品仓/美中-其他仓），来自 batch-print-groups。
- 二级 tab：**固定三个**（背贴 / Label 面单 / 面单+背贴），不随仓库增减。
- 选仓库 + 文档类型 → 调 batch-print（group_key + document_type）→ embed 预览。

### 下载文件名

按「仓库 + 文档类型」命名：
- 美东 label/both → `美东-面单.pdf`
- 美中-成品仓 label/both → `美中-成品仓.pdf`，sticker → `美中-成品仓_背贴.pdf`
- 美中-其他仓 label/both → `美中-其他仓.pdf`，sticker → `美中-其他仓_背贴.pdf`

## 顺序一一对应

后端按同一 `package_sns` 顺序遍历过滤后的包裹，背贴/面单页序天然对齐——第 N 页背贴 = 第 N 页面单 = 同一包裹。

## 边界

- 通途发货仓库为空 → 跳过 + 提示（batch-print-groups 的 skipped）。
- 无有效面单 → 跳过（batch-print 锚定有效面单）。
- 某仓库无包裹 → 一级 tab 不显示该仓库。

## 验证

- `uv run pytest tests/sellfox_shipping -q`：**312 passed, 2 warnings**。
- 浏览器验证：一级/二级 tab 渲染正确，美东/美中二级 tab 均固定三项，下载文件名正确。

## 踩坑

- Python heredoc 转义错误曾把 JS 里的 `\'` 写成 `''`，导致 JS 语法错误；改用 Edit 工具直接精确替换修复。
- 一度用 `has_sticker` 动态增减二级 tab，后按需求改为固定三项。
