---
okf: v0.1
type: Log
title: 变更日志
description: 平台账期对账模块的时序变更记录
tags: [platform, reconciliation, changelog]
timestamp: 2026-08-17
---

# 变更日志

## 2026-08-17

- **初始化模块**：新建 `platform_account_reconciliation/`，覆盖 Overstock/OSTK 账期与 EN/Tongtool Order 费用级对账，预留 Wayfair 扩展。
- **脚本**：新增 `scripts/reconcile_ostkus.py`，支持多账期文件、Payment Summary 解析、EN 只读拉取、拆单/重复主单识别和工作簿生成。
- **文档**：新建 OKF bundle、AGENT_HANDOFF、README、Skill，并记录 07-01/07-16 对账结果与字段口径。
- **本次结果**：350 个基础 OS 订单全部覆盖；销售金额两期差异 0；4 个跨期退单；EN 平台费与账期营销扣点差异待确认。
