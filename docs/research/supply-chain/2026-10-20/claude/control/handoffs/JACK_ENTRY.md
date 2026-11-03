---
okf: v0.1
type: Index
title: Jack Agent 唯一入口
date: 2026-10-26
owner: claude-foreman
channel: docs/jack-w1-channel
---

# Jack Agent 唯一入口

> **从这一个文件开始，不要从 commit / PR 评论里找规则。**
> 本文件是固定入口；它链到当前有效的问答日志、样本、契约、数据地图。
> 最后更新：2026-10-26（以本分支最新提交为准）。

## 1. 三步开始

> **2026-10-26 Codex 新交接优先**：先读 [原生报表与 PO 入库时间交接](2026-10-26-codex-native-report-handoff.md)，位于 `feature/en-native-supply-report-plan`；下方切旧 docs 分支步骤仅用于原 W1 冻结复现，不要因此漏读新交接。生产库存/Parquet 已运行，新报表仅测试部署。

```bash
git fetch origin
git switch docs/jack-w1-channel
git pull
```

1. 读本文件 §2 的 **4 个固定链接**（按顺序）。
2. 跑 `experiments/sc14/test_contract.py`，确认 **21/21**。
3. 用 9 个冻结 SKU + **10-22 冻结库存**重算正式 recon。

> **每次开始任务前都重复这 3 步；不要等用户转述。**
> 如果 Agent 支持定时轮询，设 15–30 分钟检查一次 `JACK_QA.md` 的新条目。
> 代码只在 `feature/jack-supply-timeline`；docs 分支只放文档/契约。

## 2. 固定必读（4 个）

| # | 文档 | 用途 |
|---:|---|---|
| 1 | [`JACK_QA.md`](JACK_QA.md) | **唯一问答日志**：当前有效结论速查 + 每轮答复 |
| 2 | [`../reviews/2026-10-23-jack-sample10.md`](../reviews/2026-10-23-jack-sample10.md) | 9 个冻结 SKU + 1 个缺额；不要用旧 8+2 |
| 3 | [`../reviews/2026-10-23-sc14-spec.md`](../reviews/2026-10-23-sc14-spec.md) | 7 个阶段、字段、五条红线、21 条验收用例 |
| 4 | [`2026-10-23-jack-data-map.md`](2026-10-23-jack-data-map.md) | DuckDB/每日备份/EN 证据、能读什么、缺什么 |

延伸阅读（按需）：[`2026-10-23-jack-reading-list.md`](2026-10-23-jack-reading-list.md)、
[`2026-10-23-jack-supply-timeline.md`](2026-10-23-jack-supply-timeline.md)。

## 3. 硬规则

- **只读本分支**，不要改 `docs/jack-w1-channel`；代码在你的 `feature/jack-supply-timeline` 分支/PR。
- **行级业务 CSV/JSON 留本地**，不进公开仓库（D33）；公开侧只放文档、代码、聚合计数。
- **未知不写 0**；未证日期不当到货；同一批只计一次；个/套不合计。
- **先读 #291**：`EN_API/fulfillment_query.py` + `supply_chain_visibility/AGENT_HANDOFF.md`；
  不要重写查询入口。工序进度取第一道工序完成量、不跨工序求和；`WO.status/produced_qty` 不可信；
  `Closed ≠ 已发完`。
- **业务决策**（服务水平、预算、交期假设、采购授权）由用户拍板；技术口径可直接对话。

## 4. 沟通规则（工头 ↔ Jack Agent）

### 4.1 唯一位置

- 入口：**本文件**；问答：**[`JACK_QA.md`](JACK_QA.md)**。
- 提问用 `[W1-Qxx]`，答复用 `[W1-Axx]`；**PR 评论只发短指针**。
- 不要从 commit 历史、零散 PR 评论里找口径；以 `JACK_ENTRY.md` + `JACK_QA.md` 为准。

### 4.2 分支所有权

- `docs/jack-w1-channel`（PR #311）：**只放文档/契约，不放代码**；保持 **draft**，不合并。
- `feature/jack-supply-timeline`：**代码、脚本、W1-RESULTS 放这里**；开 draft PR 供工头复审。
- 代码误放 docs 分支 → 工头 **revert**，并指向 feature 分支；不改写历史、不 force-push、不删旧记录。
- 行级 CSV/JSON 留本地；公开侧只放文档、代码、聚合计数、路径/hash。

### 4.3 复审与交付

- 工头**只审 feature PR**；复审结论写进 `JACK_QA.md`（`[W1-Qxx]` / `[W1-Axx]`），不在评论里长篇往返。
- 每轮必须给：SC14 errors/warnings、SC04 对账、B_min/B_max 桥接、exceptions、unknowns。
- 业务决策（SLA/预算/交期假设/采购授权）仍由用户拍板；技术口径可直接对话。

### 4.4 触发

- Jack 把问题/结果写到 `JACK_QA.md` 或 feature PR；工头在下次被调度时读。
- 需要实时响应时，由用户/审核会话触发定时检查；**不要求用户转述技术内容**。

## 5. 当前状态（2026-10-26）

- W1 v0 结果在 `feature/jack-supply-timeline`（`9aea4cb6`）；`docs/jack-w1-channel` 上的代码提交 `140bbee6` **已 revert**（`bb87549a`）。
- **PR #311 保持 draft，不合并**；它是 docs-only 通道。
- 首轮 8 问已答复（Q01–Q08）；SC14 已扩 7 阶段，**21/21 passed**。
- **Q07 已更正**：不同 `warehouse_id` 且未重复上报的**可以相加**；`component->main` 只是本地映射清洗标签。
- 9 SKU 的映射角色：**6 个皮壳（cover）/ 2 个成品（finished）/ 1 个组件（component）**，不能全写 finished。
- W1 v0 复审结论见 `JACK_QA.md` 的 `[W1-Q09]`。
- **A09 已收**（feature `f63af171` + `40d74491`，draft PR #312）；`[W1-Q10]` 复审：**1 个阻塞**
  （`config/frozen_20261022.json` 行级业务 JSON 进公开仓库，违反 D33）+ 4 项必改。
- **A10 已收**（feature `62546ea7`）：数量 JSON 已移出、SC14 同步 19/0、WO 时点/per-PO/received 字段已补。
  `[W1-Q11]`：用户已决定**保留** `sample_skus/warehouse_map`（无数量）；剩余 2 项必改（仓库 confidence/scope、SC14 同步默认）。
- **A11 已验收通过**（feature `e15b1b91`）：仓库 `scope=operator`、波兰 `assumed`、SC14 离线同步 19/0；
  **#312 技术上可进合并评审**。下一动作：`#311 → rebase #312 → #312`；等用户/审核会话批准。
