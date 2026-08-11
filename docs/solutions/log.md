---
okf: v0.1
type: Log
title: 解决方案变更日志
tags: [solutions, log]
---

# 变更日志

## 2026-08-11
- **新增**: `conventions/tongtu-en-sellfox-instock-sku-mainline.md` — 通途有库存 SKU 的完整码登记、EN 产品映射、赛狐产品 SKU 验证及半成品边界。
- **背景**: 旧审计把 `-Cover/-Foam` 的基码匹配误作完整登记；本次以 EN 产品 `customer_items` 完整回读修正，固化三系统主线与只读调查边界。

## 2026-08-07
- **新增**: `conventions/erpnext-item-variant-creation-convention.md` — EN 物料/变体创建惯例（四层属性体系、9 类配套物料、API 创建链条、已知坑）
- **新增**: `conventions/index.md` — conventions 分类索引
- **背景**: 通途→EN→赛狐缺口分析中补建缺失物料 `KS0001-CMM-153-PURPLE`，逆向还原物料体系惯例；此前无文档记录此惯例
