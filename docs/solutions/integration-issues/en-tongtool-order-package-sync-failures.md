---
okf: v0.1
type: Reference
title: EN 通途订单/包裹同步为什么会漏与空壳——300s 掐断/526/任务重叠/仓库不回写/精确匹配
date: 2026-10-12
category: integration-issues
module: EN_API
problem_type: integration_issue
component: integration-sync
severity: high
applies_when:
  - "排查 EN 里 Tongtool Order / Tongtool Package 漏单、拆单缺父单、或『有单但成本全 0』的空壳单"
  - "给 tongtool_integration 这个自定义 app 改同步/限流/回填相关代码"
  - "想知道 7 天回溯窗口到底兜住了什么、漏掉了什么"
tags: [tongtool, erpnext, sync, rate-limit, job-timeout, warehouse, sku-match]
related_components: [EN_API, tongtool_api, erpnext]
---

# EN 通途订单/包裹同步：五类缺陷与修复

EN 生产（`erpnext.vilavi.cn`）的 `Tongtool Order` / `Tongtool Package` 由**独立自定义 app `tongtool_integration`**（仓库 `keyapi/tongtool_integration`，不在本仓库）每晚从通途 API 拉取。2026-10 一次专项排查确认：**数量覆盖其实是 100%，真正的病在"质量"**——以及同步作业本身会被掐断。

## Context

排查前的前提修正（**先别按直觉下结论**）：

- **不能用月表时间口径判漏单**。`通途订单YYYYMM` 的月表是**账期/发货**口径，而 EN `sale_time` 是**下单时间**：按 `sale_time` 落在当月比对会得出大量"假漏"。要用**发货口径**（`despatch_complete_time`）或干脆**不带时间窗、按 `order_id_code` 存在性**比对。
- 实测 2026-08 覆盖：订单 10,737 唯一号 **缺 0**；包裹 10,726 **缺 0**（双向相等）。**订单号覆盖不是问题。**
- 月表里**没有裸单、只有 `_N` 拆单**是那张表的性质，不是 EN 的 bug；裸单只在 EN。别把"只有拆单没有原始单"当成漏数据。

## Guidance（本学习沉淀的做法）

沿用既有 7 天滚动重扫**不要动**——它刻意兜住三类缺口：通途侧抖动、分页中断（一页失败即 `break`，当天剩余页丢失）、以及**晚到的更新**（尾程费等由同事手工后补，近单后 `updatedTime` 会变）。要提速只能从别处着手。真正修的是下面五条：

**① 默认队列 300s 掐断（症状：Error Log 全是 `Task exceeded maximum timeout`）**
cron 触发的定时任务由 `ScheduledJobType.get_queue_name()` 决定队列，**frequency 不含 "Long" 就一律走 `default` = 300s**。而通途限额让 7 天回溯必然 >300s → `JobTimeoutException` 掐断。
→ 入口只做"投递"，真正执行体 `frappe.enqueue(..., queue="long", timeout=5400)`；并在日循环里加**软闸门**（过 06:30 不再开新的一天，宁可少跑一天让回溯窗口次日补，也不压上班时段的扫码报工）。

**② 限流器是"实例级"→ 并发作业集体超频（526）**
`TongToolClient` 原先用实例内 `request_times` 记录，多个作业各算各的预算。
→ 改 **Redis 全局滑动窗口**（Lua 原子、时钟取 `redis TIME`），全商户共用一个 5 次/分钟预算。

**③ 滑窗允许"瞬时连发"，仍会撞 526（实测翻到第 36 页必挂）**
滑动窗口只保证"任意 60s ≤5 次"，却允许 **1 秒内连发 5 个再歇 55 秒**；通途按自己的整分钟计数，连发容易踩线。深分页时 3 次重试耗尽 → 丢掉当天剩余页（错误信息还会显示成 `None`）。
→ 在窗口之外**再加"最短间隔 = 窗口/限额"（60/5 = 12s）**：永不连发，把速度从"贴着实线"变成"留余量"。顺带把 526 重试耗尽时的 `last_exception` 补上，别打印 `None`。

**④ 多个凌晨任务会重叠 → 必须互斥**
任务改长后，01:00 订单导入可能还在跑 02:45 的更新同步就起来了：并发写同一批 `Tongtool Order`，且**各自持有一份 5 次/分钟预算** → 又是 526。
→ `frappe.cache().lock()` 跨进程互斥（TTL 防死锁、等不到就跳过并留痕）。**注意生产实际有 2 个 long worker，靠"单 worker 自然串行"不可靠。**

**⑤ 空壳单的真因：`_update_order` 不回写 `warehouse_name`**
建单路径与手动 refresh 路径都会写 `warehouse_name`，**唯独"更新"路径不写**。订单常在"尚未分配仓库"时首次建单，此后每天同步都补不上 → 字段永久为 `null` → 找不到 `Tongtu Shipping Warehouse` 成本配置 → 子表 `shipping_method`/绍兴成本/头程/皮壳成本**全 0**。修：更新路径在入参非空时回写（别用空值覆盖）。

**⑥ SKU 匹配是精确串匹配，无容错**
`_find_erp_item_by_tongtool_sku` 是 `Item Customer Detail.ref_code = %s` **等值查询**：不剥后缀（`-Cover`/`-Foam`/`-N`）、不去 `删除` 前缀、不回退基码。实测全库有数千子表行 `erp_item_code` 为空，但只对应很少的 distinct 通途SKU，其中**约 1/5 是"EN 里其实已登记、只是订单没被重新匹配"**（跑 rematch 即可修，零 API），**约 4/5 是 EN 里根本没登记**（属建物料范畴）。**别一律当成"没登记"。**

**⑦ 历史回溯：开放 API 的可见性是"部分"的（2026-10 实测）**
- 不带 `accountCode` 查某月，**第 60 页即空**（约 5–6 千条）；按账号查能翻更深（某大账号到第 40 页，与其月量吻合）→ **必须按账号查**。
- 可见性**跟"最近更新时间"走，不是销售日期**：查 2025-06 只返回少数近期被更新过的单；大部分老单已不可见。
- 因此：**API 适合近期补漏，不能完整重建 2025-07 以前的历史**；历史真源是 GS 月表。详见 [订单历史分析库](../architecture-patterns/order-history-duckdb-store.md)。

## Why This Matters

- 300s + 限流 + 重叠是**同一根因链**（外部 5 次/分钟 × Frappe 默认队列），只修一处仍会以另一种形式复发。
- 空壳单不是量的问题而是**成本/利润问题**：字段全 0 会直接污染下游成本核算，且**每天还在新增**（只要更新路径不回写）。
- 分不清"已登记未匹配"与"未登记"，会让人去补一堆其实已存在的客户物料号。

## When to Apply

- 动 `tongtool_integration` 的同步/限流/回填代码前先读本篇；改完走 EN 自定义 app 标准发布链路（测试系统建分支→实测→合 main→push→生产 `pull upstream` + `clear-cache` + `restart`）。**改 cron 时间光 pull 不够**：hooks 里的 `scheduler_events` 要 `bench execute ...scheduled_job_type.sync_jobs` 才会写进 `Scheduled Job Type`。
- 判"某月漏没漏"一律用发货口径或存在性比对，**不要用 `sale_time`**。

## Examples

诊断取数（只读，可直接复用）：

```python
# 真源（GS 月表）唯一订单号/包裹号
sh = gc.open("通途订单202608"); ws = sh.worksheet("2026年8月订单")
# EN 侧按发货口径取同期，做集合差
GET /api/resource/Tongtool%20Order?filters=[["Tongtool Order","despatch_complete_time",">=","2026-08-01"], ...]
```

实测结论：**通途有 / EN 无 = 0**（订单与包裹皆然）；`sync_status` 字段恒为「已同步」，**不能用来判失败**；失败只在 `Error Log` 里。

## Related

- [Tongtool ERP2 MCP 共享限流](../integration-issues/tongtool-erp2-mcp-shared-rate-limit.md) — 5 次/分钟是"全商户共享"的实验证据
- [背贴品名缺失怎么补——通途SKU 在 EN 有两种登记写法](../integration-issues/sku-name-backfill-via-en-customer-code.md) — 通途SKU 在 EN 的存放位置（`customer_code` / `customer_items[].ref_code`）
- [生产 2核4G 上跑批量回填会把机器压死](../developer-experience/prod-batch-backfill-oom-small-box.md) — 同一次排查踩到的运维坑
