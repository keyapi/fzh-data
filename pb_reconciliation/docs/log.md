---
okf: v0.1
type: Log
title: pb_reconciliation 变更日志
tags: [pb, reconciliation, log]
timestamp: 2026-08-14
---

# 变更日志

## 2026-08-14
- **新增**: `tm_commission.py` — TM 佣金结算表生成（从给财务表过滤账期付款 + 按天截止发票，英文 Notes、5% 佣金、付款总额硬校验）。生成 `20260519-20260618`（佣金 $709.29）、`20260619-20260718`（佣金 $442.14）。
- **修正**: 文档里发票日期表述改为"PB 侧发票日期只可能等于或晚于我方（按 UPS 实际发货确认），不可能早"。
- **初始化**: 创建 OKF bundle（index.md / log.md / reference/）。
- **新增**: `reconcile_pb.py` — PB 对账表月度更新脚本。追加付款到 PB Remittance Advice、追加发票到 Invoice to PB（截止首个 0 付款文件夹）、更新 Notes 汇总日期、双开票映射（1541→1530）、不重不漏硬校验、时间戳新文件输出。支持 `--dry-run` / `--write`。
- **新增**: 颜色标记（本轮未付黄底 / 之前未付本轮已付绿底 FF92D050）+ Notes 两个区块显式填色（修复样式继承被清空的问题）。
- **新增**: `UNPAID_NOTES` 配置 — 本轮未付发票写 UPS 实际发货日/交付日/跟踪号备注。
- **新增**: AGENT_HANDOFF.md / README.md / reference/workflow.md / reference/ups-delivery-check.md。
- **成果**: 生成 `...20260813_20260814_171350.xlsx`（507 付款 + 999 发票行）；5 张未付经 UPS 核查为迟发（交付 07/23–08/04 晚于 8/13 账期截止），顺延下账期。
