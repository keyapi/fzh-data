---
okf: v0.1
type: Reference
title: V0.1 复审包（Codex #301 / Codex1）
date: 2026-10-22
commit: 98e1c664
---

# V0.1 复审包

## 固定版本
`98e1c664`（on top of V0 `7c1102d4`）

## 产物
- `control/reviews/2026-10-22-supply-demand-replenishment-v0.md`
- `control/reviews/2026-10-22-sample-2sku.md`
- `experiments/g2g3_pilot/build_v0.py`
- `experiments/g2g3_pilot/out/sample_2sku.json`
- `out/replenishment_v0/evidence.json`

## 上一轮 FAIL 的 5 项（V0 review1）
1. SO 超发抵消其他行需求：应逐行正向求和；正向合计 2,924，超发 -907 单列。
2. 无证据扣 PO/在产/在途：应改为 B_min（最大重叠）/ B_max（完全不重叠）；PO 重复候选单列。
3. 60/90 天 ROP 未按日历窗口积分；应明确决策时点并积分剩余预测。
4. 月度/累计 P90 误差模型不一致；应统一并区分目标 90% 与实测覆盖。
5. 零需求单元被排除；应保留。

## 复审要求
- 用固定 commit 读取，不要用工作区后续改动。
- 重点：需求正向求和、B_min/B_max 边界、时间窗积分、P90 一致性与 coverage、零单元。
- **允许并鼓励派一个子 Agent 独立复算**：至少核对一个 SKU 的正向需求与一个供给边界。
- 输出 PASS/FAIL + 分级问题（blocking/major/minor）+ 最小修复。
- 只读；不访问生产、不改文件、不合并 PR。
- 完成即回报，不设固定钟点。
