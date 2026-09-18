---
okf: v0.1
type: Reference
title: 赛狐踩坑与选择器参考
description: 赛狐 ERP 的关键选择器模式、DOM 知识、Excel 导入陷阱
tags: [sellfox, pitfalls, playwright, element-ui, selectors, excel-import]
timestamp: 2026-05-25
---

# 赛狐踩坑与选择器参考

## 关键选择器模式

- **下拉框**: `input[placeholder="全部仓库"]` — el-select 组件
- **按钮**: 可能是纯图标（如 `.icon_sf_download`），页面搜不到文字
- **弹窗**: `el-dialog` 组件，标题在 `.el-dialog__title`
- **表格**: `el-table` 或 `vxe-table`
- **复选框**: `el-checkbox`

## Element UI 弹性窗定位

**永远**用 `.filter(d => d.getBoundingClientRect().width > 0)` 过滤 —— 赛狐页面有 20+ 个隐藏的 `.el-dialog__wrapper`，`querySelector` 默认拿第一个（是隐藏空壳）。

## 登录检测（双重判定）

1. **URL 检测**：`"login" not in page.url`（登录后跳离 login.html）
2. **用户元素检测**：`page.locator('text=克勇').first.is_visible()`（用户名出现）

登录成功 → 立刻检测 `page.url`：
- 如果在 dashboard → `page.goto(PAGE_URL)` 跳到仓库页
- 如果已在仓库页 → 直接继续

## 赛狐 Excel 导入

- **必须 sheet_name='商品'**：模板文件有 3 个 sheet (`['商品','hidden1','hidden2']`)，`pd.to_excel()` 默认 `Sheet1` 会被赛狐拒绝
- **禁止 pd.read_excel(模板)**：读模板会带 hidden sheet，`to_excel` 后丢失这些 sheet → 导入卡死
- **正确做法**：只取表头列名 → `pd.DataFrame()` 构造数据 → `ExcelWriter(sheet_name='商品')` 写入
- **文件上传**：Python Playwright 用 `expect_file_chooser` + `set_files()`，或直接用 `set_input_files`
- **上传后弹窗**：`POST /excel/import.json` (multipart/form-data) 返回 200+taskID，但前端等 WebSocket 通知

## el-dropdown-menu__item 不可见

Playwright click 超时 (element not visible) → 使用 `page.evaluate("item.click()")` 绕过可见性检查。

## Element UI checkbox

`cb.click()` 在 evaluate 中不改变 Vue 组件状态 → 必须用 Playwright `page.locator().click()` 真实点击。
