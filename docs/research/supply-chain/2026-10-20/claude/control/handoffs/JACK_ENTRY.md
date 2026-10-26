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

```bash
git fetch origin
git switch docs/jack-w1-channel
git pull
```

1. 读本文件 §2 的 **4 个固定链接**（按顺序）。
2. 跑 `experiments/sc14/test_contract.py`，确认 **21/21**。
3. 用 9 个冻结 SKU + **10-22 冻结库存**重算正式 recon。

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

## 4. 提问与答复

- **提问**：PR #311 评论用 `[W1-Qxx]`；或在你自己的 `feature/jack-supply-timeline` PR 里评论。
- **答复**：统一追加到 [`JACK_QA.md`](JACK_QA.md)；PR 评论只发「已答复，见 JACK_QA.md 第 N 条」的短消息。
- **不要**在东一个 commit、西一个 PR 评论里找口径；**以 `JACK_QA.md` 当前有效结论为准**。
- 详细长答复按轮次存档（如 `2026-10-26-jack-w1-answers-r1.md`），但速查表在 `JACK_QA.md` 顶部。

## 5. 当前状态（2026-10-26）

- 首轮 8 问已答复（Q01–Q08）；SC14 已扩 7 阶段，**21/21 passed**。
- **Q07 已更正**：不同 `warehouse_id` 且未重复上报的**可以相加**；`component->main` 只是本地映射清洗标签。
- 9 SKU 的映射角色：**6 个皮壳（cover）/ 2 个成品（finished）/ 1 个组件（component）**，不能全写 finished。
- 下一步：用 10-22 冻结值重算正式 recon；实时 10-26 只作 `provisional_live`；开自己的 draft PR。
