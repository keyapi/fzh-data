---
okf: v0.1
type: Report
title: 第三轮复审 R3 元数据收口（2026-10-27）
description: 预测行数契约严格化与 verified/pin 状态真实化；r5 重跑数字不变
tags: [acceptance, forecast, review-fix, metadata]
date: 2026-10-27
status: verified
---

# 第三轮复审 R3 元数据收口

来源：`C:/Users/zhang/.agent-ops/fzh-data/reviews/supply-review3-989dc16f.md`
（verdict=reject，仅针对“R1–R3 完整闭环”声明；R1/R2 已通过）。
本轮只修 R3 的两项 P2 元数据问题，不动其他逻辑。

## 1. 修复

### #1 行数声明缺失/null 仍被接受

位置：`supply_netting/forecast.py`（`_declared_rows` + `load_forecast`）。

- 新增 `_declared_rows()`：`outputs[].rows` 必须是**显式正整数**；
  缺失、`null`、bool、小数、字符串、`≤0` 一律 `ForecastContractError`，
  不再走 `int()` 截断，也不会漏出普通 `ValueError`。
- 校验对象是**未按 lead_days 筛选的完整窗口表**行数，避免用筛选后行数掩盖声明。

### #2 未提供预期 manifest 哈希仍记 verified=true

位置：`forecast.py`（`ForecastInput.manifest_pinned` / `pinned_sha256`）/ meta 输出。

| 场景 | `manifest_sha256_verified` | `manifest_sha256_verification` | `manifest_sha256_pinned` |
|---|---|---|---|
| 传了预期哈希且匹配 | `true` | `pinned_match` | 该哈希 |
| 传了预期哈希但不匹配 | 抛错、不产出 | — | — |
| 没传预期哈希 | **`false`** | **`unpinned`** | `null` |

`windows_sha256_verified` 仍恒为 `true`：它只证明「窗口文件 = 上游 manifest 声明」，
不证明「manifest 就是调用方期望的版本」。两类证据在文档里分开说明。

## 2. 回归

| 用例 | 断言 |
|---|---|
| `test_missing_or_null_row_count_is_refused` | rows 缺失、rows=null（哈希本身正确）都抛 `ForecastContractError` |
| `test_non_integer_row_count_is_refused` | 13554.75 / "13554" / True / -1 / 0 全部拒绝 |
| `test_declared_row_count_mismatch_is_refused` | 整数 999 与实测不符被拒 |
| `test_pin_state_is_recorded_truthfully` | pin → true/pinned_match；无 pin → false/unpinned/null |
| `test_wrong_pin_is_refused` | 错误 pin 直接抛错 |

测试总数：**163 通过**（`supply_netting` 140 + 上游 23），无 skip、无失败。

## 3. 真实预测验证（只读，内存）

| 调用 | `manifest_pinned` | verified | verification | 预测量 |
|---|---|---|---|---|
| 传 `7a41755d…9efc` | true | true | `pinned_match` | 2,378.272644 |
| 不传 pin | false | false | `unpinned` | 2,378.272644 |

两种调用预测量相同——pin 只影响「证据强度」，不改变数字。

## 4. r5 复算

代码变化只影响预测入口的校验与元数据，不改净额口径，因此重跑确认而非改写：

| 项 | 值 |
|---|---|
| 代码/文档提交 | `2dcf0ba5`（运行时代码）+ `dc3e17e0`（文档），manifest 记录 `dc3e17e0`、`git_dirty=false` |
| 净额键 / 行 | 545 / 5,450 |
| 期初 / 保护期缺口 / 缺口键 | 17,689 / 34.867936 / 71 |
| 视界末累计未满足 | 449.966544 |
| 供应事实 / outside | 9,827 / 2,609 |
| 已证到货 | 0 |
| 预测 | forecast-20261027-r2，2,378.272644，`pinned_match` |
| checks | 恒等式通过、`opening_rows_unproven=0`、`batch_split_conflicts=0` |
| pack | 545 行 / 71 缺口键（分布不变） |

manifest 新增可见字段：`manifest_sha256_pinned`、`manifest_sha256_verification`；
`manifest_sha256_verified` 只有在本次 CLI 传了 `--forecast-manifest-sha256` 时才为 true。

## 5. 仍然存在的缺口（不变）

历史订单全部早于 as_of（2.779 天预测起点盲区）、在途/PO 无 ETA 故已证到货为 0、
未履约 SO 未接入、预测仅覆盖 582 销售键、阶段余额仅通途在途且无已证批次、
F5 estimated 日期规则未做。`partial=true`（6 条原因）；
r5 仍是条件情景附件，不是采购指令，也不是供应功能验收。
