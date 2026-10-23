---
okf: v0.1
type: Reference
title: 通途库存每日备份：两条线会静默失败，体检脚本如何兜底
date: 2026-10-23
last_updated: 2026-10-23
category: workflow-issues
module: inventory-daily-health
problem_type: workflow_issue
component: inventory-backup
severity: high
applies_when:
  - "要确认通途库存每天是否正常落到本地"
  - "浏览器导出或 API 备份当天没有产物"
  - "需要判断两条线的数据是否互相对得上"
tags: [tongtool, inventory, backup, scheduling, dingtalk, parity, windows-task-scheduler]
related_components: [web_automation, stock_daily_backup, archive_stock_run, dingtalk_robot, tongtool_api]
---

# 通途库存每日备份：两条线会静默失败

## 1. 先认清：两条线都已经存在

| 线 | 定时任务 | 实现 | 产物 |
|---|---|---|---|
| Excel（浏览器） | 02:17 `FZH-TongtuAutoExport-stock` | `web_automation/legacy-compatible/tongtu_auto_export.py` | `web_automation/output/通途合并库存结存清单 YYYYMMDD_HHMM.xlsx`（4 个有数据仓，约 4,575 行） |
| API（全量） | 05:17 `FZH-TongtuStockApiDaily` | 仓库外 `D:\Work\fzh-stock-backup\stock_daily_backup.py` + `archive_stock_run.py` | `D:\Work\库存备份\YYYY-MM-DD\warehouse=*.jsonl` + `manifest.json`，封存到 `runs/YYYY-MM-DD/<run_id>/` |

**不要再写第三个取数器。** 两条线的数据口径已经对齐：2026-10-22 按（仓库 + SKU）内连接，
重叠 **4,575 行**，可用/在途/待发/故障品四列差异 **全为 0**；API 多出 412 个 SKU，其中
44 个有库存（43 个真实 SKU + `TEST-1`），是浏览器导出状态/FBA 过滤造成的已知差异。

API 线额外覆盖 5 个 WayfairCG 仓和 2 个长期空仓；Excel 线不含这些仓。

## 2. 问题：手工补跑会掩盖定时任务长期失败

2026-10-20 到 10-23 的真实证据：

| 日期 | 浏览器 02:17 | API 05:17 | 数据来源 |
|---|---|---|---|
| 10-20 | 成功 | 未按点跑 | `legacy` 手工 |
| 10-21 | 成功 4/6 仓 | 未按点跑（09:46 补） | `legacy` 手工 |
| 10-22 | 成功 4/6 仓 | 未按点跑（07:06 补） | `manual` 手工 |
| 10-23 | **BLOCKED**（OCR 登录误判） | **退出码 4**，无目录 | 无 |

`runs/` 里没有一条 `source=scheduled` 的成功记录。也就是说：**看“今天有没有数据”不够，
必须看“定时任务自己有没有成功”**。否则一次手工补跑就能让监控安心好几天。

同理，浏览器线的日志里如果出现 `status=BLOCKED`，即使 `downloads/` 里还有前几天的文件，
也不能当成今天成功——合并步骤曾按 mtime 取“最新文件”，会静默复用旧文件。

## 3. 体检脚本

`scripts/inventory_daily_health.py` 只读产物，不调通途、不写库存：

```bash
# 历史回放：只打印结论
uv run python scripts/inventory_daily_health.py --date 2026-10-22 --dry-run
# 正式：写 D:\Work\库存备份\health\YYYY-MM-DD.json + health.log；FAIL/WARN 推钉钉
uv run python scripts/inventory_daily_health.py
# 主仓库根执行，注册每天 07:17
powershell -ExecutionPolicy Bypass -File scripts/install_inventory_health_schedule.ps1 -AtTime "07:17"
```

检查项：

1. **Excel 线**：当天合并清单存在且日期正确；必需列齐全；4 个预期有数据仓齐全；
   每仓行数 vs 最近 7 日中位数（>20% WARN、>50% 或归零 FAIL）；2 个空仓若出现库存 → WARN；
   `export-stock.log` 末尾 `status=READY`；Windows 任务 `LastTaskResult` 非 0 → FAIL。
2. **API 线**：`manifest.complete=true`、`missing_warehouses=[]`；14 个启用仓齐全
   （5 个 WayfairCG 缺失只 WARN）；`runs/` 已封存且 `exit_code=0`；
   `.lock` 对应进程仍活 → 视为“仍在运行”而非失败；`.last_failure.json` 提供失败阶段。
3. **离线互证**：仅当两条线都有当天完整产物时，按（仓库+SKU）比较四个数量字段。
   差异 SKU >0.5% WARN、>5% FAIL；可用合计 >1% WARN、>10% FAIL；
   Excel-only >0 → WARN；API 独有有库存 SKU >1% → WARN（基线约 1%）。
4. **状态记录**：`health/YYYY-MM-DD.json` 一天一文件，`health.log` 追加一行；
   全正常不推钉钉，异常才推，正文带两条补救命令。
   根 `.env` 缺 `DINGTALK_WEBHOOK` / `DINGTALK_SECRET`（或 `*_STOCK` 覆盖键）时，
   脚本只写状态并打印警告，不会静默假装已推送。

历史回放基线：10-22 `overall=OK`；10-21 `WARN`（API 09:46 补跑，与 02:22 的 Excel 差 104 个 SKU，
属快照时间差，不是数据损坏）；10-23 `FAIL`（两条线均无产物）。

## 4. 两个已修故障

### 4.1 浏览器登录误判（10-23 02:17）

`passport` 的记住密码 cookie 仍有效时，会经 `j_security_check` 直接跳到
`erp102.../dashboard`，不会出现用户名框；旧代码硬等 `input[name=username]` 15 秒后抛错。

修复：
- `web_automation/legacy-compatible/tongtu_urls.py` 新增 `looks_like_erp_url()`；
- `tongtu_login_ocr.login()` 等不到用户名框时，若 URL 已在 ERP 域 → 视为会话有效；
- `tongtu_auto_export._try_login()` 先等 5 秒重查会话，登录后若不在 `goodsbalance` 页则重新打开；
- 登录超时输出 `FAILURE_CODE=LOGIN_TIMEOUT`，dispatcher 归类为登录失败而不是未知错误。

### 4.2 API wrapper 静默失败（10-23 05:17，退出码 4）

旧 wrapper 在写日志前就失败，日志/状态/目录全无。加固（`D:\Work\fzh-stock-backup\run_stock_daily_backup.cmd`）：

- `OUTDIR` 改用 ASCII junction `D:\Work\fzh-inventory`，`.cmd` 内不再有 GBK 中文字节；
- 第一行就写 `[start]`，Python 用 `-u` + `PYTHONIOENCODING=utf-8`，避免被杀时日志全丢；
- 预检 Python / 脚本 / `.env` 凭证，失败写 `.last_failure.json` 并退出 2；
- 任何非 0 退出写 `.last_failure.json`（日期、阶段、退出码、token），成功时删除；
- `stock_daily_backup.py` 清理死进程留下的 `.lock`（PID 存活检查），活进程则跳过本轮。

## 5. 排障顺序

1. 先看 `D:\Work\库存备份\health\YYYY-MM-DD.json` 的 `reasons`，它已经指明是 Excel 还是 API。
2. Excel：`tail web_automation/logs/export-stock.log`；`status=BLOCKED` → 手动跑一次
   `uv run python web_automation/scripts/dispatch.py tongtu.stock.export -- --auto-login`。
3. API：`tail D:\Work\库存备份\stock_daily_backup.log`；`.last_failure.json` 看阶段；
   手动跑 `D:\Work\fzh-stock-backup\run_stock_daily_backup.cmd`（约 15 分钟、64 次 API 调用）。
4. 互证 WARN 先看快照时间差（Excel 02:xx vs API 05:xx）；差异只在少数 SKU 且可用合计差 <1%，
   通常是夜间调拨/发货，不是管道坏了。
5. 任务本身：`schtasks /Query /TN FZH-TongtuInventoryHealth /V /FO LIST`。

## 6. 相关

- 浏览器导出与调度：`web_automation/docs/reference/scheduling-exports.md`
- 通途 API 限流与字段：`tongtool_api/docs/reference/authentication-and-errors.md`
- 通途“可用 0”不可信：`docs/solutions/workflow-issues/cargo-location-tracking-source-reliability.md`
- 每日库存备份的历史方案（未合并分支）：`docs/research/supply-chain/2026-10-20/claude/14-daily-inventory-backup.md`
