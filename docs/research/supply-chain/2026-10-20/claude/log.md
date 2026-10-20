---
okf: v0.1
type: Log
title: 供应链整合 — Claude 独立调研过程日志
description: 每个阶段做了什么、用了哪些检索命令、失败与放弃的方向
date: 2026-10-20
tags: [supply-chain, research, log]
---

# 过程日志

## 2026-10-20 — Phase 0 脚手架

- 用户确认 4 项范围决策：历史记录挖掘优先；分阶段汇报；允许装包 + 只读拉数；验证切片 = PB 楔形枕 × 美中 Daneey。
- 新建独立 worktree `D:/Work/赛狐/Cursor/.claude/worktrees/supply-chain-claude`，
  分支 `research/supply-chain-claude`，基线 `origin/main` @ `e5d07c9d`。
- 交接包参考：`origin/docs/supply-chain-integration-handoff` @ `de899f4b`（PR #300，未合并）。
- 建立目录与 `index.md` / `00-plan.md` / `sources.md` / `log.md` / `experiments/`。

### Phase 0 已核实的事实（与交接包的差异）

| 事项 | 交接包说法 | 本次复核 |
|---|---|---|
| 端到端履约蓝图 | 未合并分支 | 蓝图**已在 main**（`docs/solutions/architecture-patterns/en-end-to-end-supply-chain-fulfillment-visibility.md`）；未合入的是实现 `EN_API/fulfillment/`（PR #291） |
| 网页 Agent demo | 未定位 | 找到 `ops_assistant_demo/`（PR #288，银行竞赛演示，治理模式可迁移） |
| 实时库存预警 | 未列 | PR #298 已含 `stock_alert/`（通途库存快照 + 阈值 + 钉钉通知，27 测试） |
| 多方法销量预估 | 未定位 | 本机有输出 `D:/Work/美国/Tracy Miller/PB orders/sales_forecast/`；生成脚本 `pb_reconciliation/sku_forecast.py` **未入库** |
| demand_forecast 子项目 | 未定位 | 继续挖（Cursor 对话库 / Notion / 本机目录） |

## 2026-10-20 — Phase 1 项目内资产与历史资料

- 三路并行：历史记录挖掘、仓库/PR 代码级复核、外部数据源侦察（只读）。
- 产出 `01-existing-assets.md` 与 `sources.md` 的 S1-001–S1-015、N-001–N-005。

### 关键发现

- **PR #304（2026-10-20 新建，keyapi）**：已归档 demand_forecast 阶段 A 三篇调研 +
  `pb_reconciliation/sku_forecast.py` + 口径文档。原会话转录已被 30 天清理。
- `demand_forecast/` 代码目录确认不存在于任何 ref；只有文档与 PB 脚本。
- 「上周网页 Agent demo」更可能是 `D:/Work/web-ai-assistant-review-20261012`（2026-10-15，`acb2dd8`），
  不是 PR #288（2026-10-11）。
- 通途×EN BOM 成本切换确实存在，集中在 PR #295/#294/#280，未进 main。
- PB 10-16 决策包（楔形枕补货 257 件）可作为 E1/E2 对拍基准。

### 副作用说明

- 历史挖掘子 Agent 早期误用 `uv run python`，在本 worktree 生成 `.venv` 并安装 101 个包；
  未跟踪、已 gitignore，不影响提交。后续实验可直接复用该环境。

### 检查点 1 后的用户更正（2026-10-20）

- `demand_forecast`：已由用户另一会话恢复到 PR #304；阶段 A 完成，阶段 B 未启动、未建目录。
- 多方法对比：实现 `pb_reconciliation/sku_forecast.py`，输出在本机 PB 目录，不入库。
- PR #304 纪要更正：`practical-paths.md` 创建于 2026-09-02 17:35，不是「9/2 没有产出」。
- 已写入 `01-existing-assets.md` §10；#300 的 §6 由维护者后续同步，本 PR 不改。

## 模板（后续阶段）

```text
## YYYY-MM-DD — Phase N
- 做了什么：
- 检索命令：
- 结果/发现：
- 失败或放弃的方向 + 原因：
```
