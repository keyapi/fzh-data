---
okf: v0.1
type: Review
title: 外部 SO 的 DN 关联核对（只读，74 GET）
date: 2026-10-22
owner: claude-worker
status: 完成；只读；三类计数与逐行清单
artifacts:
  - experiments/auto_order/check_dn_linkage.py
  - out/auto_order/dn_linkage_check.csv
  - out/auto_order/dn_linkage_check.md
---

# 外部 SO 的 DN 关联核对

> 回答“外部逾期是真缺货，还是出库未回写”。只读；预算 ≤80 GET，本轮 **74 次**，
> 0 错误、无写入。**无 DN 不等于真缺货**（可能线下发货）。

## 1. 范围与预算

| 项 | 值 |
|---|---|
| 外部 SO（V0.2 22 个） | **22** |
| 外部 SO 行 | **212** |
| 请求 / 耗时 | **74 / 约 34 s**（≤80） |
| 写入 | 无（全部 GET） |

## 2. 三类计数（SO 级，行数为对应 SO 的行数）

| 类别 | SO | 行 | 含义 |
|---|---:|---:|---|
| **a. `dn_submitted`** | **13** | 164 | 至少有一张已提交 DN（docstatus=1） |
| **b. `dn_unsubmitted`** | **0** | 0 | 只有 draft/cancelled DN |
| **c. `none`** | **8** | 42 | 无任何 DN 与 DP |
| 补充：`dp_only` | 1 | 6 | 有 DP、无 DN（待出库） |

- 部分 `dn_submitted` SO 同时含 docstatus=2 的 cancelled DN；判定按“至少一张已提交”。
- `none` 的 8 个 SO **不等于真缺货**：系统内无 DP/DN，可能是线下发货或未建单。

## 3. per_delivered 与实际 DN 的对照

- 13 个 `dn_submitted` SO **全部 per_delivered<100**：
  - `per_delivered≥99`：**4** 个（残余 <1%）；
  - `<99`：**9** 个；
  - 对应 164 行中，**54 行仍有未履约量**。
- 单据显示 DN 已提交，但 SO 的 `per_delivered` 未达 100。差额**可能是未交付剩余，
  也可能是未回写**——DN 本身不能区分。
- `per_delivered` 与 DN 不一致的 SO 行见 `dn_linkage_check.csv`（逐行含
  SO 哈希、物品、数量、已交付、未履约、交期、仓、DP/DN 状态）。

## 4. 能证明什么 / 不能证明什么

- **能证明**：系统内是否存在 DP/DN、DN 的 docstatus；对已提交 DN 的 SO，可对照
  `per_delivered` 是否同步。
- **不能证明**：无 DN 的 SO 是否线下发货；DN 未提交/`dp_only` 是否已实物出库；
  DN 已提交但 `per_delivered<100` 的差额是未交付还是未回写。
- **不得**把“无 DN”直接等同于“真缺货”；需仓储/财务按实物与出库记录确认。

## 5. 逐行清单

- `dn_linkage_check.csv`：212 行，一行一个 SO 行，字段：
  `so_hash, so_status, per_delivered, line_idx, item_code, qty, delivered,
  unfulfilled, delivery_date, warehouse, dp_exists, dp_flags, dn_exists,
  dn_statuses, class_, note`。
- SO 级摘要见 `dn_linkage_check.md §3`（22 行）。
- 仅哈希 id，无客户名/原始单据名。

## 6. V0.1/V0.2 数字未变

- V0.1：classes **1/481/1**、483 行；V0.2 外部 81 行 / 内部 75 SO——**未改**。
- 本轮只新增本核对产物，未回写任何既有文件。

## 7. 复现

```bash
uv run python docs/research/supply-chain/2026-10-20/claude/experiments/auto_order/check_dn_linkage.py
uv run python scripts/check_secrets.py   # 无 finding、退出码 0
```

## 8. 约束自检

| 约束 | 结果 |
|---|---|
| 只新增脚本、`dn_linkage_check.*`、本记录 | ✅ |
| 只读；无写入/下单/配置变更 | ✅ |
| ≤80 GET、单线程、200 ms | ✅（74 次） |
| 不提交原始明细；客户名不含；SO 哈希 | ✅ |
| 不改既有产物与 control 受保护文件 | ✅ |
| 未 push；只提交自己新增文件 | ✅ |
| `check_secrets.py` 无 finding | ✅ |
| 不留临时文件（含 `__pycache__`） | ✅ |
