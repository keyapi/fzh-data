---
okf: v0.1
type: Reference
title: 独立站同步每 8 小时「超时」——默认队列 300 秒上限被 429 退避正好睡光
date: 2026-10-12
category: integration-issues
module: vilavi_pim
problem_type: integration_issue
component: erpnext-rq-scheduler
severity: high
applies_when:
  - "Error Log 反复出现 `Task exceeded maximum timeout value (300 seconds)`，间隔等距（本例每 8 小时）"
  - "报错时刻 = 任务启动时刻 + 5 分钟（300 秒），不是任务跑完的时刻——说明是被 RQ 掐死，不是自己结束"
  - "任务里有阻塞式重试退避（`time.sleep`），退避总和逼近或超过任务预算"
  - "`frappe.enqueue` / 调度器注册的任务没显式传 `queue=` 和 `timeout=`，落在 default 队列"
  - "外部置站点（Shopify `/products.json` 等）从一个数据中心 IP 拉取，返回 429 而代码里加多少重试都没用"
tags: [vilavi_pim, daneey, shopify, erpnext, frappe, rq, scheduler, default-queue, timeout, rate-limit, 429, cloudflare, item-group, silent-data-loss]
---

# 独立站同步每 8 小时「超时」——默认队列 300 秒上限被 429 退避正好睡光

## Context

2026-10-12 排查生产 `erpnext.vilavi.cn` 上「独立站」同步模块的反复超时。

现象（生产 Error Log 实测，2026-10-09 ~ 10-12 每天都有）：

```
独立站 API 分页请求失败   →  Task exceeded maximum timeout value (300 seconds)
```

观测到的复发时刻是 **05:45 / 13:45 / 21:45**，几乎每 8 小时一次。

关键误读：这三个时刻**不是任务跑完的时刻**，而是**任务启动后 5 分钟**——也就是 RQ 把任务掐死的那一刻。任务真正启动在 05:40 / 13:40 / 21:40。

出问题的不是通途模块（`tongtool_integration`），而是 **`vilavi_pim` app 的独立站同步任务**：

```
apps/vilavi_pim/vilavi_pim/tasks/daneey_sync.py  →  sync_daneey_products()
apps/vilavi_pim/vilavi_pim/hooks.py:  "cron": { "40 5,13,21 * * *": [ ... ] }
```

## 根因

外部 API 分页拉取 + 落在 RQ **默认队列**（硬上限 300 秒）。但这次的扳机不是数据量大，而是**独立站已经在对生产服务器返回 HTTP 429**，而代码里的重试退避**恰好也是 300 秒**——退避还没走完，RQ 就把任务掐了。

## 证据链

### 1. 生产直接探测独立站（只读）

```bash
curl -s -o /dev/null -w "HTTP %{http_code} time=%{time_total}s\n" --max-time 60 \
  -A "Mozilla/5.0 ..." "https://daneey.com/collections/all/products.json?limit=250&page=1"
# HTTP 429 time=1.06s
# page=2 同样 HTTP 429 time=0.80s
```

两个分页都秒回 429 —— 是 Cloudflare 按 IP 挡，不是网络慢。

### 2. 当天 Error Log 时间线（05:40 那班）

| 时刻 | 日志 |
|---|---|
| 05:40:52 | 独立站 API 限流 — 第1页被限流，第1次重试，等待 30 秒 |
| 05:41:23 | 第2次重试，等待 60 秒 |
| 05:42:23 | 第3次重试，等待 90 秒 |
| 05:43:54 | 第4次重试，等待 120 秒 |
| **05:45:51** | **独立站 API 分页请求失败 — Task exceeded maximum timeout value (300 seconds)** |
| 05:45:51 | 独立站同步 — 未获取到任何产品数据 |

05:40:52 + 30+60+90+120 = **正好 05:45:52**。

## 机制：为什么恰好卡在 300 秒

1. **队列决定超时**。生产 `config/supervisor.conf` 里 worker 是 `bench worker --queue short,default`；frappe `frappe/utils/background_jobs.py` 里 `get_queues_timeout()` 写死 `default_timeout = 300`，`short` / `default` 都是 300，只有 `long` 是长超时（默认 1500）。`frappe.enqueue(timeout=None)` 就取 `queue` 对应的这个值，兜底 300。
2. **任务没显式指定队列/超时**。`daneey_sync` 只是注册成 scheduler cron，没有 `frappe.enqueue(queue=..., timeout=...)`，于是落在 default → 300 秒。
3. **退避是阻塞式 `time.sleep`**。`daneey_sync.py` 的 429 分支累加 30+60+90+120 = 300 秒纯睡眠，把任务预算一分不剩地睡光。第 300 秒 RQ 抛 `JobTimeoutException`，被那个宽泛的 `except Exception` 接住，落成一条「分页请求失败」。

> 对照：**同仓库的 `tongtool_integration` 早就绕开了这个坑**——它每处 `frappe.enqueue` 都显式写 `queue="long", timeout=5400`（见 `sync/order_sync.py`、`sync/package_sync.py`）。`daneey_sync` 是唯一没这么做的。

## 次生问题

1. **宽泛 `except Exception` 把 RQ 的超时异常也吞了**。任务被掐死时看起来像「只是没数据」，不像硬失败——所以它能安静地每 8 小时复发而没人察觉。
2. **半截数据冒充成功，会被「全量覆盖」误清**。取数只拿到第 1 页（250 个产品）也会正常返回；随后 `_write_to_item_groups` 的「全量覆盖」会把**不在本次结果里的物料组清空**。10-11 21:45 那次就是「第 2 页被限流 → 但仍写入 158 个组」（当天侥幸「清空 0」）。只要第 2 页里有产品对应着一个已有物料组，它就会被误清成空。
3. **两个实现抢同一个字段**。本仓库 `EN_shopify/shopify_to_en.py`（工作站跑，出口 IP 能拉到）写的是同一个 `Item Group.daneey_product_details`，同样是全量覆盖，但 HTML 格式不同（本地是 `<div class="daneey-products">` 块，服务器是逐行 `<a>`）。两个 writer 谁后跑谁赢，格式会来回翻。

## 正确做法（可复用清单）

排查任何「外部 API + 定时/批量」任务时问这几条：

- [ ] **跑在哪个队列、超时多少？** `bench worker --queue ...` 决定；`short`/`default` = 300 秒，`long` = 1500 秒。
- [ ] **阻塞退避总和是否远小于任务预算？** 总和不小于预算时，失败会被超时掩盖，且表现成「等距复发」而非「立即报错」。
- [ ] **`except Exception` 有没有连 `JobTimeoutException` 一起吞？** 吞了就等于把硬失败伪装成软失败。
- [ ] **全量覆盖型写入，是否先确认「数据源是完整的」？** 半截数据 + 全量覆盖 = 静默清空。
- [ ] **取数出口 IP 是关键变量。** 数据中心 IP 会被 Cloudflare / Shopify 的公开 `products.json` 挡成 429，代码里加多少重试都没用；换出口（非数据中心 IP / 代理 / 带 token 的 Admin API）才是正解。
- [ ] **报错时刻是不是「启动 + 超时值」？** 是的话直接查队列超时，不要查业务逻辑。

## 修复选项（按优先级）

1. **首选：让取数不再从这台服务器出门。** 429 是 Cloudflare 按 IP 挡数据中心出口。可选：把取数挪到能拉到的出口机器、给服务器配代理、或改用带 token 的 Shopify Admin API（有明确配额，不走被挡的公开 `products.json`）。
2. **兜底（不管取数怎么修都该做）：别再死等。** 退避压到远小于任务预算；或 `frappe.enqueue(queue="long", timeout=...)`；并让失败快速落一条明显错误。
3. **顺带：给全量覆盖加「本次取数是否完整」的闸门**，不完整就不清空。
4. **顺带：两个 writer 二选一**，别再互相覆盖。

## 未做 / 待办

- 本次只做只读诊断，未改任何生产代码或数据。
- 代码侧改动需走 EN 自定义 app 标准链路（测试系统建分支 → 测 → 合 main → push → 生产 pull upstream + migrate / clear-cache / restart）；见 `docs/...`（`EN_API/AGENT_HANDOFF.md` → en-server-access）。
- 生产机近期频繁自动重启（与本次报错无关），另行排查。

## 相关

- 任务源码：`vilavi_pim/tasks/daneey_sync.py`（server-side，本仓库不含）
- 同字段的本地实现：[EN_shopify/shopify_to_en.py](../../../EN_shopify/shopify_to_en.py)、[EN_API/AGENT_HANDOFF_独立站产品链接.md](../../../EN_API/AGENT_HANDOFF_独立站产品链接.md)
- 同仓库已规避此坑的对照：`tongtool_integration/sync/order_sync.py`（`queue="long", timeout=5400`）
