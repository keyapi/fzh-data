---
okf: v0.1
type: Log
title: sellfox_settlement 变更日志
tags: [sellfox, amazon, settlement, okf, log]
---

# 变更日志

## 2026-09-09
- **初始化 OKF bundle**: 建 `docs/`（index.md/log.md）`docs/research/` `docs/reference/`；`AGENT_HANDOFF.md`；`docs/research/saihu-amazon-settlement-autofetch-2026-09-09.md`（从 `docs/research/` 移入）。
- **新增** `docs/reference/settlement-v2-endpoints.md`、`docs/reference/column-mapping.md`、`docs/reference/gsheet-access-and-channel-account.md`——端点/字段、科目映射、谷歌表访问+渠道账号别名规则。
- **文档沉淀**：`docs/solutions/tooling-decisions/amazon-settlement-autofetch-sellfox.md`（ce-compound 知识沉淀+交接）；`docs/solutions/architecture-patterns/account-period-revenue-reconciliation-ecosystem.md`（账期/收款核算生态地图）；`docs/solutions/workflow-issues/amazon-account-period-late-submission-audit.md`（账期迟交审计+规则+最新状态多账期结果）；`CONCEPTS.md` 增「账期/回款核算」术语簇；技能 `sellfox-amazon-settlement` 入 `.agents/skills/`。
- **工具**：`reconcile_amazon.py`（shops/fetch/fetch-custom/candidates/reconcile，`--currency` 取原币）；`audit_late_submission.py`（单文件多账期桶迟交审计，`--platform` 分流）；交叉表 `out/storeName_to_account_candidates.csv`。
- **实测**：赛狐结算中心V2(6月103结算/16.8k明细)、紫鸟插件列式报表(`getPlugPageList type=3`→ZIP→32列CSV) 均取通；赛狐店名↔渠道账号写入共享表；多账期迟交审计跑通(2026-09-09 导出, 全平台1528行/Amazon ~660行)。
