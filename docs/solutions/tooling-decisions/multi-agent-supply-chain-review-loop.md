---
okf: v0.1
type: Reference
title: 工头 + 只读打工仔 + Codex gate — 供应链交付的并行审计回路
date: 2026-11-07
category: tooling-decisions
module: supply_chain
problem_type: tooling_decision
component: tooling
severity: medium
applies_when:
  - "老板/运营交付需要同时做可读性、业务复算、底层审计"
  - "不想让用户当 Claude 与 Codex 之间的传声筒"
  - "一个审计子代理卡住/未落盘，主线程需要继续推进"
  - "交付件已发给老板，后续只能出补充页不能改原数字"
tags: [multi-agent, subagent, codex-gate, audit, supply-chain]
---

# 工头 + 只读打工仔 + Codex gate

## Context

2026-11 供应链交付同时有多个独立问题：老板表可读性、4 个首批晚于停工键、60cm 4,001 键与 DN/PO 全链路。用户明确说“你自己找工头/子进程继续完善，减少我做传声筒”。实际试过：只派 1 个 Claude 审计子代理、没有另起 Orca 工头/打工仔；子代理一度没落盘，主线程自查后它才返回。后来用 3 个只读 worker 并行，效率明显提高。

## Guidance（本学习沉淀的做法）

1. **工头维护一个队列文件**（如 `docs/supply-chain-round15-queue.md`），写清 worker、输入、输出、验收和 gate；不要口头分派。
2. **worker 只读源数据，只写自己的输出文件**（独立 md/csv/xlsx）。不要让两个 worker 改同一个交付包。
3. **交付件已发出后，只做补充页/新版本**：老板已收到的 v2 不改数字；v3b 用 `9_`/`10_` 追加，不覆盖 v2。
4. **Codex gate 只审“新产出 + 契约”**，不重开已交付数字；gate 输入是文件路径 + 复核包，输出 PASS/PARTIAL/FAIL + P0/P1。
5. **并行任务要互不重叠**：可读性表、业务复算、底层审计分开；一个 worker 卡住不阻塞其他。
6. **主线程保留判断权**：worker 的结论要抽查原始表/CSV 再合并；不能把子代理摘要当证据。
7. **Orca 真实工头/打工仔只在契约/数据冻结后启动**；否则先 Claude 子代理 + `codex exec`，避免开一堆空闲 terminal。

## Why This Matters

- 用户不应承担 Claude ↔ Codex 的传声筒；队列 + 文件 + gate 能让双方直接读写；
- 并行只读 worker 能把“可读性、业务、底层”三件事同时推进，且不互相踩文件；
- 子代理会卡住/超时，主线程必须能自查继续，不能全局等待；
- 交付后改数字会造成老板手里的表与内部表不一致，必须版本化/补充页。

## When to Apply

- 交付件已发老板、还有 P1 要补；
- 同时有多个独立审计/复算；
- 需要 Codex 审核但不想人工转述；
- 工作区有多个 Agent 并行，必须按文件边界隔离。

## Examples

- W1 老板表 v3：从 v2 生成，增加三家公司分桶、本周行动清单、使用说明；不改 v2。
- W2 首批空运复算：4 键改空运后可执行；KS0321 换运输无效，需加约 18 件。
- W3 60cm/DN-PO 审计：20 键/4,001 件，C/EN 20/20，PO 3/20 缺 2,417；DN 到货/入仓字段为空。
- 主线程把 W2/W3 并入 v3b 的 `9_`/`10_` 补充页，而不是改 v2。

## Related

- [Round15 队列](../../supply-chain-round15-queue.md)
- [补货交付状态与批次口径](../workflow-issues/supply-chain-delivery-batch-status.md)
- [预测对照观测契约](../best-practices/forecast-benchmark-observation-contract.md)
