---
okf: v0.1
type: Reference
title: 通途统计导出下载识别——按「最上行 = 本次提交」锚定（替代 href 基线差集）
date: 2026-09-09
category: architecture-patterns
module: web_automation
problem_type: architecture_pattern
component: browser-automation
severity: medium
applies_when:
  - "写通途「统计报表」类页面（订单详情/销售库存等）的自动导出下载轮询"
  - "该页面历史任务列表按提交时间倒序展示，任务状态不自动刷新"
  - "发现 href 基线差集在历史表晚渲染 / 小范围快任务两端都有竞态"
  - "要在异步任务 + 异步渲染的列表里可靠识别「我自己这次提交的那一条」"
tags: [web-automation, tongtu, playwright, export, polling, row-anchor]
---

# 通途统计导出下载识别：按「最上行 = 本次提交」锚定

## Context

写 `tongtu.orderdetail.export`（订单详情统计月度导出）时，要从通途「统计导出」历史任务列表里
可靠识别**本次提交的任务**并下载其结果。列表里同时存在大量历史任务；任务异步生成，
且页面不会自动刷新状态——要往返 数据查询/统计导出 两个 tab 才能强制刷新出新结果。

第一版抄了同族 `tongtu_sales_report.py` 的做法（`tongtu-pitfalls.md` 坑 17）：提交前收集
所有已完成任务的下载 href 作为**基线**，提交后轮询，凡出现 `href not in 基线` 的链接即当作本次结果。
该做法在两个方向上都出过竞态：
- **历史表晚渲染**：提交前表还没加载完 → 基线拿到 0 条 → 提交后旧的下载链接出现，被误认为"新结果"；
- **小范围快任务被吞**：提交后才采基线（等 3s）→ 快的任务已完成，新链接已进基线 → 永远等不到"新 href"，`DOWNLOAD_TIMEOUT`。

根因：只认「href 没见过」，不认「这个链接属于哪一行/是不是我这次提交的」。

## Guidance（本学习沉淀的做法）

**把识别锚定到行身份，而不是 href 差集。**

1. **依赖列表天然按提交时间倒序**：统计导出数据表**第一行永远是最新提交的任务**——本次提交后，它就会是那一行。
2. 提交前读数据表第一行的**提交时间**（`prev_top_ts`）作为旧基线。
3. 提交后往返两个 tab 刷新，轮询最上行提交时间：
   - 还是 `prev_top_ts` → 本次行还没插入，继续等；
   - 变为新值 → **锁行**（记住 `my_ts`），这一行就是本次任务；
   - 锁行后，只要**那一行**出现「点击下载统计结果」链接，就点它下载。
4. 不再需要任何 href 集合：旧行晚渲染（它们的提交时间 ≠ 新值）和小范围快任务（等的是行、不是 href）
   两种竞态同时消除。

**通途该页的结构坑（探路实测）**：
- 历史表是 fixedHeadFoot 滚动表格：header 表（含「统计条件」`<th>`）与其后的数据表**不是 sibling**；
  数据表定位用 `header.locator("xpath=following::table[1]")`。
- 数据表**首行是空 spacer 行**，要跳过；真实数据从第二条 `tr` 起。
- 一行内条件文本会含 `发货时间:YYYY-MM-DD HH:MM:SS` 等多个 datetime；**行文本最后一个
  `YYYY-MM-DD HH:MM:SS` = 该行提交时间**（条件列在前、状态列无此格式），可作行的稳定身份。

代码落地见 `web_automation/legacy-compatible/tongtu_orderdetail_report.py`：
`capture_prev_top_ts` → `submit_statistic` → `wait_for_my_download`（配合 `_first_data_row` / `_row_datetime`）。

## Why This Matters

href 差集是"全局去重"思维，行锚定是"身份识别"思维。异步任务 + 异步渲染的列表里，全局去重总是
依赖"基线完整/时序正确"这类你不一定能保证的前提；把判定收敛到"我提交的那一行"则前提只剩一个
明确事实（提交时间倒序、最上行是我刚提交的），鲁棒得多。若不改，月导出这类正常耗时任务尚可，
但小范围快任务（单日验证）和重跑场景会随机 `DOWNLOAD_TIMEOUT` 或**下到旧文件**——后者是静默错数据，更危险。

## When to Apply

- 通途任何「统计报表 → 历史任务列表 → 点下载」的自动导出；**复用优先于重造**（本实现已抽象为通用 helper）。
- 其它系统若满足「任务列表按提交/创建时间倒序 + 状态不自动刷新」也可套用：把"最上行"换成"我创建的那一行，
  用行内时间/状态字段做身份"。
- 若页面没有可靠的行身份字段、且历史表不含旧行晚渲染风险，href 差集（坑 17 思路）仍可作轻量兜底。

## Examples

- 失败（href 差集，PR #220 前）：单日 `--range-start/--range-end 2026-07-15` 实测，等 3s 采基线后
  `DOWNLOAD_TIMEOUT`——快任务链接已进基线。
- 成功（行锚定，并入 PR #220）：提交前最上行 `17:55:30`，提交后锁到本次行 `17:59:56`，
  下载该行链接；单日 07-15 得 306 行、发货日期全 07-15；全月 07 得 9604 行、07-01~07-31。

## 关联

- 能力/入口：`web_automation/capabilities.yaml` `tongtu.orderdetail.export`（BROWSER_ONLY/read）
- 模块专题：`web_automation/docs/reference/orderdetail-export.md`（选择器/踩坑/核验）
- 同族旧做法（通途销售报表仍用 href 差集）：`tongtu-pitfalls.md` 坑 17、`tongtu_sales_report.py`
