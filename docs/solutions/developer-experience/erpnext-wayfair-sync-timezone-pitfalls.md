---
okf: v0.1
type: Reference
title: ERPNext 每日同步的时区与批量写入坑（Wayfair CG 实测）
date: 2026-10-29
category: developer-experience
module: wayfair-api-proxy
problem_type: developer_experience
component: data-pipeline
severity: medium
applies_when:
  - "在 Frappe/ERPNext 里写每日 API 同步（日期窗、事件时间、批量 upsert）"
  - "遇到 MariaDB 1292 Incorrect datetime value、时间整体差 8 小时"
  - "需要远程在 bench 里跑一次性脚本并拿到结果"
tags: [frappe, erpnext, timezone, duckdb, bulk-insert]
---

# ERPNext 每日同步的时区与批量写入坑

## Context

为 `tongtool_integration` 增加 Wayfair CG 变动流水同步时，连续踩了几个“代码看起来对、
数据就是不对”的坑。都发生在 Frappe + DuckDB + MariaDB 这条链路上，与 Wayfair 本身无关。

## Guidance

### 1. Frappe 的 `now_datetime()` 是站点本地 naive 时间

`now_datetime()`（以及 `now()`）返回的是 Asia/Shanghai 的 naive datetime。代理侧用
`datetime.isoformat()` 原样下发时，会把“北京时间”标记成 UTC，查询窗口整体后移 8 小时。
实测表现：30 天窗口里漏掉最早 8 小时的事件。

```python
# 错：本地 naive 被当成 UTC
window_to = now_datetime()

# 对：API 窗口一律用真实 UTC
window_to = datetime.now(timezone.utc)
```

数据库里存的历史时间（如 `finished_at`）也是站点本地 naive，需要先按站点时区转 UTC：

```python
from zoneinfo import ZoneInfo
def as_utc(value):
    if value.tzinfo is None:
        value = value.replace(tzinfo=ZoneInfo(get_system_timezone() or "UTC"))
    return value.astimezone(timezone.utc)
```

### 2. tz-aware datetime 不能直接进 MariaDB

上游 `eventDate` 形如 `2026-09-29T16:39:04.000Z`，`get_datetime()` 解析后仍带 `tzinfo`。
PyMySQL 会序列化成 `2026-09-29T16:39:04+00:00`，MariaDB 报
`1292 Incorrect datetime value`。

```python
def event_datetime(value):
    parsed = get_datetime(value)
    if isinstance(parsed, datetime) and parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed
```

### 3. DuckDB 的 TIMESTAMP 也按会话时区解释 tz-aware 值

同样的 tz-aware datetime 写入 DuckDB `TIMESTAMP` 列，会按服务器本地时区存储（+8h）。
之后按 `event_key` 去重时，如果规则是“保留 event_date 较大的一行”，被污染的行会
永久压过正确值。两条一起修：

- 写 Parquet 前先归一化成 naive UTC；
- 去重时让**本次拉取覆盖历史**，而不是按时间取最大：

```sql
COPY (
  SELECT * FROM new_rows
  UNION ALL
  SELECT * FROM read_parquet('...') WHERE event_key NOT IN (SELECT event_key FROM new_rows)
) TO 'tmp.parquet' (FORMAT PARQUET)
```

### 4. `json.dumps` 不认 `Path`

Parquet 写入函数返回 `Path`，直接放进结果 dict 再 `json.dumps` 会抛
`TypeError: Object of type PosixPath is not JSON serializable`。而且这次异常发生在
“运行记录已写成 Success 之后”，会额外补一条 Failed，污染 Run 日志。写入后立刻转 `str`。

### 5. 新增字段的默认值不会回填到已存在的 Single DocType

`Tongtool Settings` 是 Single。给 JSON 加 `enable_wayfair_stock_txn_sync: default 1`
后 migrate，已有记录的该字段仍是 0；调度函数读到 0 就静默不跑。上线时必须显式 set + save：

```python
doc = frappe.get_single("Tongtool Settings")
doc.enable_wayfair_stock_txn_sync = 1
doc.wayfair_txn_lookback_days = 7
doc.save(ignore_permissions=True)
frappe.db.commit()
```

### 6. `bulk_insert` 绕过文档校验，必须自己补系统字段

`frappe.db.bulk_insert(doctype, fields, values)` 不触发 validate、命名规则和钩子。
用 `autoname: field:xxx` 的 DocType 也必须显式给 `name`，并补齐
`creation/modified/owner/modified_by/docstatus/idx`。发布前先自己校验唯一键和必填。

### 7. 远程执行一次性脚本

- `echo y | bench --site <site> console < script.py` 在 IPython 下不可靠（多行块可能
  根本没执行，且不报错）。
- 可用单行 `exec`：`echo "exec(open('/tmp/script.py').read())" | bench --site <site> console`，
  并让脚本把结果写 JSON 文件，再 `cat` 文件——不要依赖 console 的 stdout。
- 直接 `./env/bin/python` 可能因日志文件属主/路径报权限错；`bench console` 才是正常入口。

## Why This Matters

这些坑的共同点是**不报错或报在别处**：窗口偏移只表现为“少了几条”，DuckDB 时区偏移
只在对比历史时发现，Single 默认值只表现为“定时任务不跑”。靠“看日志没报错”无法发现，
需要把“总数对账 + 时间一致性”写进每次运行的核对脚本。

## When to Apply

- 新建 Frappe 每日同步、把第三方事件时间写入 DocType/Parquet 时；
- 排查“数量对但时间差 8 小时”“同一事件出现两次不同时间”“调度钩子明明加载了却不执行”时；
- 需要在生产/测试站远程跑一次性回填脚本时。

## Examples

对账脚本应同时检查：

```text
DocType event_date == Parquet event_date（同一条 event_key）
Run.row_count == 本次拉取行数
总计行 == 分仓行求和
重新跑一遍 inserted == 0（幂等）
```

## Related

- [Wayfair CastleGate API 契约与分页坑](../integration-issues/wayfair-castlegate-inventory-api.md)
- [Wayfair CG 库存表与 Parquet 粒度设计](../architecture-patterns/wayfair-cg-stock-table-and-parquet-grain.md)
- `tongtool_integration/docs/wayfair_cg_stock_sync.md` — 配置、调度、排错
