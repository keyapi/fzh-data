---
okf: v0.1
type: Index
title: sellfox_settlement — 文档索引
description: 赛狐自动拉取 Amazon 账期（结算中心V2 + 紫鸟插件列式报表）、两报表口径取舍、科目映射、赛狐店名↔渠道账号交叉表
tags: [sellfox, amazon, settlement, okf, index]
---

# sellfox_settlement — 文档索引

| 你需要... | 读这个 |
|----------|--------|
| 子项目入口/交接 | [AGENT_HANDOFF.md](../AGENT_HANDOFF.md) |
| 人读使用说明 | [README.md](../README.md) |
| 深度调研（赛狐自动拉取可行性、两报表口径、风险与路径） | [research/saihu-amazon-settlement-autofetch-2026-09-09.md](research/saihu-amazon-settlement-autofetch-2026-09-09.md) |
| Amazon 非 V2 月度报表国内报税分析（ZJ 填写总表、收入退款候选、费用成本、法人归属、实施路线） | [research/2026-10-09-amazon-non-v2-monthly-tax-analysis.md](research/2026-10-09-amazon-non-v2-monthly-tax-analysis.md) |
| ZJ 填写渠道选型（Notion / 自建局域网 / Google 表单） | [research/2026-10-10-zj-questionnaire-collection-options.md](research/2026-10-10-zj-questionnaire-collection-options.md) |
| 赛狐结算中心V2 端点与字段 | [reference/settlement-v2-endpoints.md](reference/settlement-v2-endpoints.md) |
| 科目映射（列式表 & 结算 amount-description → 钉钉列） | [reference/column-mapping.md](reference/column-mapping.md) |
| 2026-09 试点测试方法与断言（可复跑） | [reference/how-we-tested-2026-09.md](reference/how-we-tested-2026-09.md) |
| 踩坑清单 | [lessons/lessons-learned.md](lessons/lessons-learned.md) |
| 知识沉淀+交接（两报表取舍/风险/后续） | [../docs/solutions/tooling-decisions/amazon-settlement-autofetch-sellfox.md](../docs/solutions/tooling-decisions/amazon-settlement-autofetch-sellfox.md) |
| 账期「提交异常/迟交」审计方法与规则 | [../docs/solutions/workflow-issues/amazon-account-period-late-submission-audit.md](../docs/solutions/workflow-issues/amazon-account-period-late-submission-audit.md) |
| Google 表访问 + 「渠道账号」表规范 & 别名规则 | [reference/gsheet-access-and-channel-account.md](reference/gsheet-access-and-channel-account.md) |
| 变更历史 | [log.md](log.md) |

> 技能（跨会话发现）：`sellfox-amazon-settlement`（`<repo>/.agents/skills/`）。脚本：`reconcile_amazon.py`；交叉表：`out/storeName_to_account_candidates.csv`。
