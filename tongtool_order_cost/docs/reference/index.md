---
okf: v0.1
type: Index
title: reference 索引
description: 特殊规则列与模式参考
tags: [reference, index]
---
# reference

| 文档 | 说明 |
|------|------|
| [rule-columns.md](rule-columns.md) | 系数列 / 参考值列 / 目标订单列 |
| [gsheets-credentials.md](gsheets-credentials.md) | gspread 本地 SA JSON |
| [gsheet-monthly-sheet-upload.md](gsheet-monthly-sheet-upload.md) | 月度成品 xlsx → 固定 gsheet 月度 ws（patch 写入：复制/归档/只覆盖变化列） |
| [monthly-tail-cost-pipeline.md](monthly-tail-cost-pipeline.md) | 月度尾程补齐全链路（通途导出→EN 预估→键值合并→GSheet）+ 覆盖率口径 + 缺尾清单 |
| [colab-cost-engine-spec.md](colab-cost-engine-spec.md) | Colab 成本引擎逆向规格（皮壳/头程/二次加工/绍兴二次加工 + 仓库→来源编码 + 美中 USTX 不对称） |
| [monthly-profitability-audit.md](monthly-profitability-audit.md) | 月度盈利审计：只读冻结→口径矩阵→对账闸门→JSON/Excel/管理摘要（两阶段 CLI）；含美中 USTX 三方案对比 `ustx-compare` |
| [ustx-cost-caliber-note.md](ustx-cost-caliber-note.md) | 美中仓库二次加工成本口径变更说明（给财务/业务）：A/B1/B2 差额 + 分歧归因 + 待确认项 |
| [sku-remap.md](sku-remap.md) | 订单旧 SKU → 井新名 |
