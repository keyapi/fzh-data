---
okf: v0.1
type: Log
title: sellfox_settlement 变更日志
tags: [sellfox, amazon, settlement, okf, log]
---

# 变更日志

## 2026-11-18
- **新增账期业绩设计**：`docs/research/2026-11-18-account-period-performance-report-design.md`——OA 应收/销售额两套基准、通途四段成本、Tax/附加费双列、04–03 期间对齐、边界矩阵、202608–202610 只读核对、Colab 上线 diff。
- **新增只读脚本**：`scripts/build_account_period_performance.py`——读 OA 外币层/人民币层/原始、渠道账号主表、通途写回（含次月 1–3 日）、`账号` ws 对照；输出本地 xlsx/json，不写 GS。
- **核对结论**：202609 与并行 A/B 双算对齐到 0.03 元；主成本改用 `写回`（`账号` ws 为旧快照，差约 −55.6 万）；四段成本用各自系数列；附加费只单列；Tax 含税未证实；FBA 无发货日期、窗口按整月计入。

## 2026-09-09
- **补齐发现链与 OKF**：调研文加 YAML `type: Research`；新建 `docs/lessons/`（踩坑 Lesson）；`docs/reference/how-we-tested-2026-09.md`（可复跑测试方法+断言）；AGENT_HANDOFF §9 更正钉钉跨月导出已落地事实；AGENTS.md 模块索引 + skill 触发词（迟交/错位/钉钉账期等）；CONCEPTS 钉清两套「账期月」归属；根 `index.md` 经 `scripts/update_index.py` 同步。
- **初始化 OKF bundle**: 建 `docs/`（index.md/log.md）`docs/research/` `docs/reference/`；`AGENT_HANDOFF.md`；`docs/research/saihu-amazon-settlement-autofetch-2026-09-09.md`（从 `docs/research/` 移入）。
- **新增** `docs/reference/settlement-v2-endpoints.md`、`docs/reference/column-mapping.md`、`docs/reference/gsheet-access-and-channel-account.md`——端点/字段、科目映射、谷歌表访问+渠道账号别名规则。
- **文档沉淀**：`docs/solutions/tooling-decisions/amazon-settlement-autofetch-sellfox.md`（ce-compound 知识沉淀+交接）；`docs/solutions/architecture-patterns/account-period-revenue-reconciliation-ecosystem.md`（账期/收款核算生态地图）；`docs/solutions/workflow-issues/amazon-account-period-late-submission-audit.md`（账期迟交审计+规则+最新状态多账期结果）；`CONCEPTS.md` 增「账期/回款核算」术语簇；技能 `sellfox-amazon-settlement` 入 `.agents/skills/`。
- **工具**：`reconcile_amazon.py`（shops/fetch/fetch-custom/candidates/reconcile，`--currency` 取原币）；`audit_late_submission.py`（单文件多账期桶迟交审计，`--platform` 分流）；交叉表 `out/storeName_to_account_candidates.csv`。
- **实测**：赛狐结算中心V2(6月103结算/16.8k明细)、紫鸟插件列式报表(`getPlugPageList type=3`→ZIP→32列CSV) 均取通；赛狐店名↔渠道账号写入共享表；多账期迟交审计跑通(2026-09-09 导出, 全平台1528行/Amazon ~660行)。
