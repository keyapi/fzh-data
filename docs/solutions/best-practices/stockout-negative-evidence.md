---
okf: v0.1
type: Reference
title: 断货负证据——没检查记录/消失的 SKU 什么时候能当 0
date: 2026-10-27
category: best-practices
module: demand_forecast
problem_type: best_practice
component: tooling
severity: medium
applies_when:
  - "用 PB checked0stock 或稀疏库存报表判断断货"
  - "构建删失/断货标签"
  - "遇到报表勾了‘隐藏库存为 0’但想利用缺少的行"
tags: [stockout, censoring, negative-evidence, pb, inventory-report]
---

# 断货负证据：没检查记录/消失的 SKU 什么时候能当 0

## Context

做销量删失时，需要知道“哪些天是因为没货才没销量”。手里的历史数据大多不是每日全量：

- PB 的 `check0stock` / `checked0stock` 是**订单级零库存记录**，只在怀疑断货时才导出；
- 同事的通途报表勾了“隐藏所有库存为 0 的货品”，零库存 SKU 大多**消失**而不是显式 0；
- WX 的宽表每个仓都有全量 SKU 行，0 可能只是“这个仓不放这个 SKU”。

如果简单地把“没查到”当 0，会制造假断货；一律当 unknown，又会漏掉真正的断货。

## Guidance（本学习沉淀的做法）

### 1. PB：`checked0stock` 才是阻塞证据

- 核验过：`checked0stock` 是 `check0stock` 的**子集**；后者还包含检查通过的订单。
- **只有 `checked0stock` 的明细算 `reported_shortage`**；`check0stock` 只用于补 SKU 清单。
- **没有检查记录 = 没有报告断货**：业务流程是“怀疑断货才 check，来货后停止检查”。空档期按负证据处理。
- 只有 `check0stock`、没有 `checked0stock` 的日期 = `check_result_missing`（检查跑了但结果缺失），不参与需求拟合。
- 2023-09-08 之前无数据，不外推。

### 2. 稀疏库存报表：显式 0 + “曾出现后消失”

- 报表有行且可用=0 → `present_zero_checkpoint`（该仓显式 0）。
- 以前在该仓出现过、本日无行 → `absent_after_presence`：
  - `prior_status=在售` → 该仓 likely 0，可作断货候选；
  - `prior_status=清仓/停售` → `delisted`，不算断货；
  - 同日其它仓有正库存 → 对**当前渠道仓**仍不可售，但对全局 SKU 不是 0（转仓）。
- **从未在该仓出现过 → `not_carried/unknown`，绝不当 0**。
- 美中 2026-09 仓库合并前后要分开，避免把改名/合并当断货。

### 3. WX 宽表的 0 只能低置信

WX 的 canonical 宽表对每个仓都有全量 SKU；`nonpositive_observed` 很可能是“这个仓不放这个 SKU”。只作 `review_candidate`，不进 `likely_unavailable`。

### 4. 先定义 SKU 宇宙，再用“缺失”

“没有记录”只有在**已知该 SKU 应该出现在这个仓**时才有意义。做法：用历史所有快照的并集构建每个仓的 ever-seen SKU 集合；只对集合内的 SKU 使用消失规则。

## Why This Matters

- 把“没查到”当 0 → 假断货，需求被错误删失。
- 把“消失”一律当 unknown → 漏掉真正断货，模型仍被 0 销量拉低。
- 区分 `在售` 与 `清仓/停售`、区分“该仓 0”与“全局 0”，是删失模型可信的前提。

## When to Apply

- 用 PB `checked0stock` 做 PB/美中断货标签；
- 用同事/运营导出的稀疏库存报表补历史；
- 设计 `stock_status.daily` 的 `present_zero` / `absent_after_presence` / `likely_unavailable`。

## Examples

实测口径（2026-10）：

- PB：81 个 `checked0stock` / 68 个检查日 / 2,145 条阻塞明细；4 个只有 `check0stock` 的日期标 `check_result_missing`。
- PJ：美东 2026-10-09 消失 153 个 SKU，其中 139 个最后状态是“在售”；119 个在所有仓都无记录，30 个仍有美中库存。

标签建议：

| 状态 | 用法 |
|---|---|
| `present_positive` | 有货 |
| `present_zero` | 该仓显式 0 |
| `absent_after_presence` + prior 在售 | 断货候选 |
| `absent_after_presence` + prior 清仓/停售 | 下架，不算断货 |
| `never_present` | 不参与 |
| WX `nonpositive` | 低置信复核，不算断货 |

## Related

- `docs/research/2026-10-23-stockout-censoring-model.md` — §1.3/§3.3
- `docs/research/2026-10-26-pengjian-inventory-backup-review.md` — §3
- `docs/solutions/architecture-patterns/tongtool-inventory-semantics-and-snapshot-timing.md`
