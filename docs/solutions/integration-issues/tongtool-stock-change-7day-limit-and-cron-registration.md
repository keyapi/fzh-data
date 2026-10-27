---
okf: v0.1
type: Reference
title: 通途库存变动任务的两个静默失效点——API 严格 7 天 + Frappe cron 方法名唯一
date: 2026-10-27
category: integration-issues
module: tongtool_integration
problem_type: integration_issue
component: tooling
severity: high
applies_when:
  - "用 erp2_stocks_stockschangedetailquery 回看多天库存变动"
  - "在 hooks.py 给同一个方法注册多个 cron 时间"
  - "排查定时任务明明写了却没执行"
tags: [tongtool, stock-change, api-limit, frappe-scheduler, cron, erpnext]
---

# 通途库存变动任务的两个静默失效点

## Context

EN 的 `tongtool_integration` 每天 05:47 抓库存变动（退货/盘点/调拨/包裹），并原计划在 06:17 / 07:17 做快照失败重试。实际排查发现两处**不报错、但任务没按预期工作**的坑：

1. 想一次性回看 7 天，结果 14 个仓全部返回 `code 527`，Run 日志是 `Partial / row_count=0`；
2. 06:17 的重试在 `Scheduled Job Type` 里根本不存在，实际只有 07:17。

## Guidance（本学习沉淀的做法）

### 1. 通途 `updatedDateFrom` 必须严格小于 7 天

通途返回：

```json
{"code": 527, "message": "updatedDateFrom只能是距当前时间7天内的值!"}
```

即使传“正好 7 天前”的时间戳也会被拒。代码里留 1 天余量：

```python
MAX_LOOKBACK_DAYS = 6  # API rejects >7 days; keep a 1-day margin
```

- 日常 05:47 只回看 1–2 天，不受影响；
- 一次性补数最多 6 天；要更早的数据只能靠每天累积，或另找历史导出。
- 不要用“7 天窗口”做文档口径，写 **6 天**。

### 2. Frappe `Scheduled Job Type` 以 method 为唯一键

`hooks.py` 里两条 cron 指向同一个方法时，数据库只会保留一条：

```python
# 反例：两条都指向 retry_stock_snapshot_if_needed
"17 6 * * *": ["...retry_stock_snapshot_if_needed"],
"17 7 * * *": ["...retry_stock_snapshot_if_needed"],
```

结果 `tabScheduled Job Type` 只剩 `17 7`，06:17 实际不会跑。修法：给其中一条一个**独立方法名**（包装函数），保留另一条原方法，避免动已有记录：

```python
def retry_stock_snapshot_0617() -> None:
    """06:17 retry wrapper: Scheduled Job Type is keyed by method name."""
    retry_stock_snapshot_if_needed()
```

```python
"17 6 * * *": ["...retry_stock_snapshot_0617"],
"17 7 * * *": ["...retry_stock_snapshot_if_needed"],
```

改完 `clear-cache + restart`，查 `Scheduled Job Type` 确认两条都在。

## Why This Matters

- 527 的失败是**整批 0 行**，但 Run 状态只显示 `Partial`；如果不看 `error_summary`，很容易以为“跑过了”。
- 重试缺失是**静默**的：代码、日志、文档都说有 06:17，实际调度表里没有；只有直接查 `Scheduled Job Type` 才能发现。
- 这两类问题都会让“每天都有备份”这个承诺在故障日失效。

## When to Apply

- 任何用 `erp2_stocks_stockschangedetailquery` 做多天回填/补数的任务；
- 任何在 `hooks.py` 给同一方法注册多个时间的 Frappe app；
- 排查“定时任务没跑”时，先查 `Scheduled Job Type`，不要只看代码。

## Examples

验证调度表：

```bash
bench --site <site> execute frappe.client.get_list --kwargs '{
  "doctype": "Scheduled Job Type",
  "filters": {"method": ["like", "%stock%"], "stopped": 0},
  "fields": ["name", "method", "frequency", "cron_format"]
}'
```

期望同时看到：

- `...retry_stock_snapshot_0617` → `17 6 * * *`
- `...retry_stock_snapshot_if_needed` → `17 7 * * *`

失败 Run 的 `error_summary` 会逐仓列出 `527`；不要只看 `status`。

## Related

- `docs/reference/tongtool-stock-en-operations.md` — 6 天窗口与重试的手册
- `docs/handoffs/2026-10-23-jack-en-stock-sync.md` — §12/§13
- app PR #9（06:17 重试 + 6 天回看上限）
