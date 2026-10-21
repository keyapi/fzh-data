---
okf: v0.1
type: Reference
title: 多 Agent 返修—复审循环：worker 完成 ≠ 评审完成 ≠ 验收通过
date: 2026-10-21
category: best-practices
module: development_workflow
problem_type: best_practice
component: tooling
severity: high
applies_when:
  - "一个 Agent 实现、另一个 Agent 独立复审，需要多轮返修才能收敛"
  - "任务状态显示 completed，但还不确定能否算验收"
  - "评审给出大量 P1/P2，需要决定先修哪一轮、什么时候停止"
  - "证据包/哈希/行级去向需要经得起独立复算"
tags: [multi-agent, code-review, rework-loop, status-model, evidence-gate, acceptance]
---

# 多 Agent 返修—复审循环：worker 完成 ≠ 评审完成 ≠ 验收通过

## Context

2026-10-21 的 DN/WO/JC/SE 窄样本任务跑了四轮：

| 轮次 | 产物 | 复审结论 | 问题数 |
|---|---|---|---|
| v1 | `22ae9a1e` | Adapter Review FAIL | 6 P1 + 3 P2 |
| v2 | `49a142e0` | Cross-Review FAIL | 2 P1 + 1 P2 |
| v3 | `e6b3cc9a` | Cross-Review FAIL | 1 P2 |
| v4 | `4b7ec55f` | Cross-Review **PASS** | 1 个非阻塞 P3（文档计数） |

v1 的 `audit_ok=true` / `evidence_complete=true` 看起来全绿，但复审用内存反例证明：
C1 的正负差异可在 UOM 内相互抵消、DN 的显式引用失效会回退到物料匹配、
不同 SE 单位仍被相加。**“自测全绿”与“契约成立”是两件事。**

## Guidance

### 1. 状态分三层，永远不要合并

- **worker 完成**：进程退出、提交了代码/证据。
- **评审完成**：独立评审给出 PASS/FAIL 和可复现理由。
- **业务验收**：范围和口径被业务确认。

任务状态里用 `completed` 只表示第一层；控制页必须单列“待复审/已验收”，
并把评审结论与 commit 绑定。worker 自己写的 `audit_ok` 不能代替复审。

### 2. 每次返修都新建 commit，不 amend

返修提交必须是新 commit（`v1 → v2 → v3 → v4`），保留完整历史。
这样评审可以固定在某个 hash 上复算，也能在出现回归时定位是哪一轮引入的。
证据包同样换版本号（`evidence_v1..v4`），v1/v2/v3 明确标注作废，
但**不要删除历史**，否则无法解释为什么早期结论不成立。

### 3. 评审意见必须可复现，且带 file:line

有效的 P1 长这样：

- 文件与行号：`g1b_dn_wo_jc_se.py:611,657`
- 合成输入：`10 EA + 2 BOX`
- 实际结果：`se_finished_qty=12`，`C2 complete=true`
- 期望：按 UOM 分区，禁止跨单位求和

只有“建议加强校验”的评论无法验收，也无法判断返修是否真的关闭。
返修侧要为新反例补回归测试（本例从 35 条涨到 84 条）。

### 4. 每轮只修“当前阻断项”，不趁机扩大范围

- v2 只修 adapter 的 6 P1 + 3 P2。
- v3 只修 cross-review 的 2 P1 + 1 P2。
- v4 只修剩余的 1 P2。
- 每一轮都重跑全套离线测试、重生成证据、重算哈希。

WIP 限制为 1 个主线实现 + 1 个独立评审；不同时改同一 worktree。
范围扩大（如从 5 个 SKU 扩到 100/全 family）必须单独授权。

### 5. 非阻塞 P3 可以“验收 + 明确修文档”

v4 只剩一个 P3：文档把 **516 条工序行**误写成 **516 个 JC 组**，实际是
**105 组**（19+18+16+32+20）。这属于文档计数，不影响代码与证据。

处置：评审给 PASS 并标明“非阻塞”；验收绑定 `4b7ec55f` 的代码与证据；
文档修正单独提交，注明“仅文档改动，代码/证据未变”。
不要为了一个文档错字把整个任务再跑一轮返修。

### 6. 停止条件要事先写清

本轮停止线：**无 P1/P2 阻断项 + 证据可独立复算 = 通过**。
不因为“还能再优化”无限返修；也不因为“已经跑了很多轮”降低验收标准。
复审通过后立即停用周期 automation，避免验收后空跑。

## Why This Matters

- 只看 worker 的 `completed`，会把“自测绿但契约不成立”当成完成。
- 不保留历史 commit/证据，返修后无法解释旧结论为何失效。
- 评审意见不可复现，返修只能靠猜，轮次会失控。
- 顺手扩大范围，会让“修一个 P2”变成“重做整个样本”。

四轮收敛的关键不是“更努力地写”，而是**每轮只关闭可复现的阻断项，
并把验收证据固定在不可变 commit 与哈希上**。

## When to Apply

- 两个 Agent 分别实现与评审，且任务有明确的证据/数量契约。
- 数据管道、对账、库存/订单关联等“全绿也可能错”的场景。
- 需要向业务解释“为什么还不能上线/为什么现在可以验收”时。

## Examples

- Adapter Review 用两个相反差异的行证明 C1 可在聚合层抵消；
  返修改为逐行全精度比较，任一行失败即 C1 失败。
- Cross-Review 用 `10 EA + 2 BOX` 证明跨单位求和；
  返修改为按 `(WO, UOM)` 分桶，混单位即 `unverified`。
- Cross-Review 用 `operations={"CUT": null}` 证明畸形 payload 仍计 matched；
  返修逐个校验工序对象与 `sum_qty`，整组 invalid 且不出 progress。
- v4 复审独立复算：zip 成员哈希、五份输入哈希、2,040 行两轮回放、
  79 条只读测试 + 8 个畸形 payload 探针，全部一致后才给 PASS。

## Related

- 调度层机制（领取锁、超时、额度探针）：`docs/solutions/workflow-issues/orca-multi-agent-automation-claims-and-quota.md`
- 控制页与四轮评审归档（本轮产物）：PR #300 / PR #301；
  `docs/research/supply-chain/2026-10-20/claude/control/CONTROL.md`
- 证据门与历史边界：同目录 `history-evidence-boundary-2026-10-21.md`（Codex #301）
