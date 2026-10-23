---
okf: v0.1
type: Review
title: EN 逾期积压与重复下单风险（只读，8 GET）
date: 2026-10-22
owner: claude-worker
status: 完成；只读，复用 V0.1/V0.2，未改任何数字
artifacts:
  - experiments/auto_order/check_backlog.py
  - out/auto_order/overdue_backlog.csv
  - out/auto_order/double_order_check.md
---

# 逾期积压与重复下单风险

> 只读；复用 V0.1/V0.2 输出，仅补充 SO 状态/`per_delivered`/DP 标志/PO-WO。
> 只写可观测事实；不判断对错、不写改进承诺、不写单据。
> 本轮 **8 次 GET**（≤80），0 错误、无写入。

## 1. 逾期积压分布（need_by < 2026-10-23）

### V0.2 外部视图（81 行，逾期 71 行）

| 桶 | 行数 | L30 建议合计 |
|---|---:|---:|
| 1–7 天 | 0 | 0 |
| 8–30 天 | 15 | 50 |
| 31–90 天 | 8 | 735 |
| >90 天 | 48 | 4,707 |

按仓：成品仓-FZH **65**、半成品仓-FZH 4、仓库-FZH 1、包材仓-FZH 1。
按类型：**PK# 56 / ND# 13 / other 2**。

### V0.1 全量（对照，原文件未改）

| 桶 | 行数 | L30 建议合计 |
|---|---:|---:|
| 1–7 天 | 1 | 0 |
| 8–30 天 | 109 | 3,772 |
| 31–90 天 | 88 | 3,247 |
| >90 天 | 269 | 19,983 |

## 2. 真实逾期 vs 可能出库未回写（仅可观测判据）

| 可观测判据 | 行数 |
|---|---:|
| `real_overdue`：open SO + `per_delivered<100` + 无 DN 已生成标志 | **71** |
| `possibly_not_written_back`：`per_delivered=100` 或 DP `is_dn_pending=0` | **0** |
| `undetermined`：无 SO 元数据 | 0 |

| 观测项（外部逾期行） | 行数 |
|---|---:|
| `per_delivered` 全部 <100 | 71 |
| `per_delivered` 全部 =100 | 0 |
| 有 DP 关联标志 | 13 |
| 无 DP 关联标志 | 58 |
| DP 标志中出现 `is_dn_pending=0` | 0 |

- **观测事实**：本轮外部逾期 71 行全部满足 `real_overdue` 的可观测标签；
  **0 行**出现 `per_delivered=100` 或 DP 已生成标志；58 行没有 DP 关联标志（无法据此判断）。
- 这不是“业务上全部真实缺货”，只是“按现有可观测字段没有发现已出库/已生成 DN 的迹象”。
- D 段 93.9% 未发货来自 linkage 报表口径；本表只覆盖外部 backlog 行（71/81 逾期），
  两者口径不同，不能直接等同。

## 3. 重复下单风险（外部 81 行）

- 建议量 L30 >0 且同物料同仓**已有 open PO/WO** 的行：**23**
- L30 建议合计 **4,283**；同物料同仓既有 **PO 0 / WO 3,803**
- 既有供给中**无日期**：PO 0 个 item、**WO 48 个 item**（计入 any，不计入 dated）
- 23 行全部标为 **“需人工确认是否重复下单”**；表见 `double_order_check.md §3`（Top20）。

| 示例 target | 仓 | L30 建议 | 既有 WO(any/dated) |
|---|---|---:|---|
| `ND#KS0001-153-CYF-WHITE` | 成品仓-FZH | 1,423 | 440 / 0 |
| `ND#KS0001-100-CYF-WHITE` | 成品仓-FZH | 332 | 245 / 0 |
| `PK#KS0230-WGMSRKQCLG-60-WHITE` | 成品仓-FZH | 300 | 206 / 0 |

> 观察事实：这些 WO 的完工日为空，无法判断是否在 15/30/60 窗口内；
> 因此“建议量与既有供给并存”只能标待确认，不能据此增减建议量。

## 4. V0.1/V0.2 数字未变

- V0.1 classes **B 481 / A 1 / C 1**，总建议 **483** 行（`order_suggestions.json` 原样读取）。
- V0.2 外部 **81** 行、内部 **75** SO 原账（`external_view.csv` / `internal_pending.csv` 原样读取）。
- 本轮只新增 `overdue_backlog.csv` 与 `double_order_check.md`，**未回写、未重算** V0.1/V0.2。

## 5. 可验证事实与仍需业务回答

- 可验证事实：
  1. 外部逾期 71 行，>90 天占 48 行（L30 建议 4,707）；
  2. 按可观测字段，无一行显示已交付/已生成 DN；58 行无 DP 关联可查；
  3. 23 行与既有 open WO（3,803 件，全部无完工日）并存，需人工确认是否重复下单。
- 仍需业务回答：`per_delivered` 与实际出库是否一致？DP `is_dn_pending` 的业务语义？
  无日期的 PO/WO 是否已到货/完工？内部 SO 如何处置（补货/调拨/履约）？

## 6. 复现

```bash
uv run python docs/research/supply-chain/2026-10-20/claude/experiments/auto_order/check_backlog.py
uv run python scripts/check_secrets.py   # 无 finding、退出码 0
```

## 7. 约束自检

| 约束 | 结果 |
|---|---|
| 只新增脚本、`overdue_backlog.csv`、`double_order_check.md`、本记录 | ✅ |
| 只读；无写入/下单/配置变更 | ✅ |
| ≤80 GET、单线程、200 ms | ✅（8 次） |
| 不提交原始明细；客户名不含；SO 哈希 | ✅ |
| 不改 V0.1/V0.2 既有产物；未改 control 受保护文件 | ✅ |
| 未 push；只提交自己新增文件 | ✅ |
| `check_secrets.py` 无 finding | ✅ |
| 不留临时文件（含 `__pycache__`） | ✅ |
