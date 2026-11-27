---
okf: v0.1
type: Log
title: workflow-issues — 变更日志
tags: [solutions, workflow-issues, log]
---

# workflow-issues 变更日志

## 2026-11-26
- **新增**: `tongtu-missing-finished-bom-zero-shell-cost.md` —— 1104 BOM 有 14 个成品 `bom_fg` 空（`cost_fg=0`）只剩 `cost_sxbzcp`，method=皮壳 → 皮壳成本被静默丢成 0；202607/08/09/10 命中 50/45/32/36 行。已加 build `warn` 门禁 + `known_zero_shell_allowlist.csv`。

## 2026-11-18
- **新增**: `tongtu-multicolor-cover-shared-foam-attribution.md` —— 多色 Cover 共享 Foam 时填充行挂错产品（KS0428 vs KS0316），只重挂成本物料、不合并；绍兴二次 +953.235、头程 −1,129.95。

## 2026-11-09

- **新增**: `tongtu-split-merge-writeback-cost-rules.md` — 8/9 月合并组自查从 18/11 组失败降到 0/0：Phase36 组行匹配（公共单号/单行组）、件数不因 EN 原单重复翻倍、PP棉/海绵由填充行定产品、模板订单号截断修正、审计按“单位成本×件数”对比组总成本。GS 写回变化：202608 20 行 +23,751.83、202609 10 行 +12,543.13，FBA 表 0 变化。

## 2026-11-05

- **新增**: `tongtu-order-universe-invalid-split-fba.md` — 订单全集用 EN 有效单（invalid 原单只作 aux 校验）；拆分 `_1/_2` 保留；GS 原始表 vs Colab 写回表分离；FBA 成本用 EN 明细、GS 销量表作骨架；canary 旧值不取上游销量报表。
