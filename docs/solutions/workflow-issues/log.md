---
okf: v0.1
type: Log
title: workflow-issues — 变更日志
tags: [solutions, workflow-issues, log]
---

# workflow-issues 变更日志

## 2026-11-11

- **新增**: `dingtalk-attendance-export-runbook.md` — 钉钉考勤导出只记操作：入口在「考勤统计 → 报表管理」；子管理员细分权限「查看、导出报表」决定能看到几张表；人员范围要按**考勤组**全选（同一单位常拆多组），用组人数对账防漏；电脑端单次最多一个月；导出是快照；MCP 下载落 `.playwright-mcp/` 而非工作目录。不含任何考勤数据。

## 2026-11-09

- **新增**: `tongtu-split-merge-writeback-cost-rules.md` — 8/9 月合并组自查从 18/11 组失败降到 0/0：Phase36 组行匹配（公共单号/单行组）、件数不因 EN 原单重复翻倍、PP棉/海绵由填充行定产品、模板订单号截断修正、审计按“单位成本×件数”对比组总成本。GS 写回变化：202608 20 行 +23,751.83、202609 10 行 +12,543.13，FBA 表 0 变化。

## 2026-11-05

- **新增**: `tongtu-order-universe-invalid-split-fba.md` — 订单全集用 EN 有效单（invalid 原单只作 aux 校验）；拆分 `_1/_2` 保留；GS 原始表 vs Colab 写回表分离；FBA 成本用 EN 明细、GS 销量表作骨架；canary 旧值不取上游销量报表。
