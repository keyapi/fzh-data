---
okf: v0.1
type: Log
title: tongtool_order_cost 变更日志
---
# 变更日志

## 2026-08-14
- **Google Sheet**: 本地 service account（`secrets/gsheets-service-account.json`，gitignore）+ `gsheets.py` / `remap_gsheet_sku.py`；从 Colab notebook cell 0 bootstrap。
- **SKU 改名**: 井维护新名，订单表替换旧名；`lookup_tongtool_sku.py` 用 ERP2 goodsQuery 校验。已处理 `通途订单202606-特殊规则` 与 `通途订单202606` 各 3 张 FBA 相关表。
- **文档**: research 六月尾程缺口、lessons（gray60 / Foam97）、Skill `tongtool-order-cost`。

## 2026-08-13
- **FBA 尾程**: 正数/0 仍跳过（账期已含）；参考值 < 0 时写入 FBA `运费` 作为账期差异冲减。同步更新 AGENT_HANDOFF 验证要点与 README 示例规则表（20260813）。

## 2026-08-12
- **新增模块**: 本地 1.7.0 特殊规则引擎 + 多 Sheet 审计工作簿，用于 AMZBAINAUS 六月异议穿透核对。
