---
okf: v0.1
type: Reference
title: 起点核对与续接
date: 2026-10-20
---

# 起点核对与续接

## 本轮完成与边界

已 fetch 当前配置的所有远端（仅 origin/GitHub），读取 PR #300 的简报/能力地图/研究计划，扫描开放 PR 元数据及相关分支路径。尚未完整审计代码、运行实验、深度外部检索，也未连接 Notion/Drive 或读取 Claude 历史会话。

用户粘贴的 Claude 回复是上下文，不等于代码验证。Codex 不采纳其跨软件分工；独立覆盖全题。当前为规划保存点。

## 已核对的快照（2026-10-20）

| 线索 | ref / 提交 SHA | 核对结果及下一步 |
|---|---|---|
| main | origin/main / e5d07c9dfb181e102dd4ef990fe3271246527f74 | 本研究分支基点 |
| Claude 交接包，PR #300 | origin/docs/supply-chain-integration-handoff / 88ad11068f12fa8bf03770a9189f9b1541785809 | OPEN；可按分支读取，不必先合并 |
| 履约蓝图 | main 的 docs/solutions/architecture-patterns/en-end-to-end-supply-chain-fulfillment-visibility.md；最近该路径提交 a1946f193bfd38825ad039083b9dca22c43e3724 | **文档已经在 main**，纠正交接中“蓝图不在 main”的概括 |
| 履约实现，PR #291 | origin/claude/frosty-hellman-58de7a / 4e4316c52313f86a40ea5e3ee110263e9a5a8c93 | OPEN；分支有 EN_API/fulfillment/、fulfillment_query.py、tests/test_fulfillment.py；main 路径扫描未见这些文件。未验证运行效果 |
| 成本引擎与拆包裹，PR #295 | origin/feature/ustx-cost-compare / 7d9c49f89e085960eff6c0c71491290fb76b31be | OPEN；tongtool_order_cost/docs/reference/cost-engine-spec/30-design-merge-split-no-double-count.md 与 31-handoff-merge-split-B.md 是重点；未完成代码审计 |
| Colab 成本链，PR #280 | origin/docs/colab-cost-current-state / b90c79ecfb619921fcc4eb68379aaf16253a8162 | OPEN；找到 colab-cost-pipeline-current-state/data-flow、2026-10-09-en-tongtool-sync-coverage-open-issues、read-en-as-cost-authority-plan 等资料。部分组件 quantity 相加不能直接当成品件数，是优先复核线索 |
| 网页 Agent demo，PR #288 | origin/claude/ce-okf-branch-param-desk / 765f36933776963341ef0385dd2a009ebaa577a8 | OPEN；有 ops_assistant_demo/AGENT_HANDOFF.md、agent_runtime.py 等；可能对应用户描述，未确认就是同一次探索 |
| PB 断货与补货，PR #297 | origin/claude/vigorous-lehmann-889bf7 / e9e92e4fbbe1ebdb1b1be2917fb3d9ab02580750 | OPEN；PR 元数据指向断货闭环、Notion、补货估算；后续核对具体文档与计算，不视为已上线 |
| 订单侧输入，PR #294 | origin/feature/en-order-side-input | OPEN；待固定 SHA、检查订单事实和盈利审计的复用边界 |

以上状态仅是核对时快照，后续启动必须刷新。相关链接：[交接](https://github.com/keyapi/fzh-data/pull/300)、[履约](https://github.com/keyapi/fzh-data/pull/291)、[成本](https://github.com/keyapi/fzh-data/pull/295)、[Colab](https://github.com/keyapi/fzh-data/pull/280)、[demo](https://github.com/keyapi/fzh-data/pull/288)、[PB](https://github.com/keyapi/fzh-data/pull/297)、[订单输入](https://github.com/keyapi/fzh-data/pull/294)。

## 尚未定位或核实

- 历史多方法销量预测对比与 demand_forecast 的真实位置；main 文件名扫描无匹配不能证明不存在。
- 用户提到的 EN BOM 成本替换工作是否完整落在 #280/#294/#295；必须逐项追踪。
- PJ/Jack 的头程大屏在 [Gitee 仓库](https://gitee.com/keyapi/fzh-data) 的提交与接口，目前尚未查询该站。
- 老板实际批准的 2026-10-16 计划样例、目标函数与审批抓手。

## 额度与接续

2026-10-20 本轮读取的账户额度快照：5 小时窗口已用 5%，周窗口已用 30%；后续以实时工具为准。没有启动后台研究/自动化，也未使用额度重置。

下一步是 P1：刷新远端与 PR 列表，核对本表所列 ref/SHA，建立 assets.md 与 coverage.md；再按 research-plan.md 启动三个便宜模型研究子 Agent。先固定独立首轮结论，再与其他软件调研比较。

本分支与 #300 均会生成根 index.md，并新建 docs/plans/index.md；合并时保留双方导航条目并重新运行 scripts/update_index.py，不能用整文件覆盖丢掉另一方索引。当前不修改 #300 分支。

可复制的续接提示：

> 按 docs/plans/2026-10-20-codex-supply-chain-research/index.md 接续供应链整合独立调研。先读 research-plan.md 与 checkpoint.md，刷新 main/开放 PR/分支快照，从 P1 执行。Codex 自己覆盖完整研究范围，不采用 Claude/Codex/Cursor 的 A/B/C 分工。允许 gpt-6-luna 子 Agent，最多三个并发；主 Agent 负责证据核实和综合。按成果与额度阈值阶段提交到本研究分支/PR；先研究，不改业务代码或生产数据。Astra 留作可选人工审查节点。
