---
okf: v0.1
type: Reference
title: 生产 2核4G 无 swap 上跑批量回填会把机器压死——瓶颈是内存不是限流，且别在网页进程里啃大表
date: 2026-10-12
category: developer-experience
module: EN_API
problem_type: developer_experience
component: tooling
severity: high
applies_when:
  - "要在 EN 生产（2 核 4G、无 swap）上对成百上千条订单/物料跑批量刷新或回填"
  - "生产服务器突然 SSH banner 超时 / HTTPS 无响应（疑似被压死）"
  - "考虑调小 innodb_buffer_pool_size 或减少 gunicorn / RQ worker 数量"
tags: [erpnext, production, oom, swap, background-jobs, throttling]
related_components: [EN_API, erpnext]
---

# 生产小机器上的批量回填：内存才是瓶颈

EN 生产只有 **2 核 / 3.5GB 内存 / 无 swap**。2026-10 一次回填把服务器**三次压到失联**（SSH `banner exchange` 超时、HTTPS 也超时），同为 `阿里云-FZH-ERPNext-frappe` 这台机。

## Context

起因：`Tongtool Order` 有一批"空壳单"（有仓库但子表成本全 0），想用 app 的 `refresh_order_from_raw_data` 批量补成本。

第一次做法：把 912 单作为**单个 long 作业**一次塞进去 —— 45 秒内 load 冲到 ~7.9，随后失联。
第二次做法（以为瓶颈是"节奏太猛"）：改成**小批 40 单 + 停 30 秒** —— **照样死**。

**第二次失败是关键证据**：40 单/批 + 30 秒停顿意味着机器大部分时间是空闲的。既然限流没用，说明**瓶颈不是吞吐/限流**。

## Guidance（本学习沉淀的做法）

**1. 先量内存，别猜。** 崩溃后重启，实测读数：
`total 3576MB / used 1491MB / available 1798MB / Swap 0`（刚开机）。
而**作业跑起来之后**的读数是 `used 2918MB / available 412MB`。
→ 差异说明**内存是被作业瞬间吃掉的**，不是基线就紧。（**注意**：若在作业运行期间采样，读到的是"作业的占用"，不能当基线结论——我第一次就是这么误判的。）

**2. 真正的内存大头是"在网页进程里加载整张表"。**
- app 的价值链要用一张 BOM 成本表，`_load_bom_cost_data()` 用 **pandas** 读整份 gz 再逐列处理；
- 我的做法是**先用 console 脚本**在 `bench console`（**即一个 gunicorn/网页进程**）里加载这张表 + 扫数千条子表来**拼出目标名单**，然后才 enqueue 作业；
- 于是同一时刻既有"网页进程里的一份 pandas"，又有"RQ worker 里的一份"，**还要和用户的扫码报工抢内存**。无 swap ⇒ 一顶破就**直接卡死**（不是变慢）。

**3. 反证：app 自带的 refresh 按钮从没压垮过机器。**
内置入口只做 `enqueue`、**不加载 BOM、不扫全表**。所以"按钮没事、我一跑就死"这件事本身就指向：**问题在我的做法（网页进程啃大表 + 大批），不在 app 或机器。**

**4. 因此不要为了迁就一次性任务去改系统调优。**
逐条实测/权衡：
- `innodb_buffer_pool_size`：配置里是**注释掉的**（用 MariaDB 默认 128MB，mariadbd 总 RSS 才 ~386MB）——**已是最小，无可再降**，压它只会让 ERPNext 查询变慢；
- `gunicorn_workers 5→2`：能省约 400–500MB，但**网页并发砍半**，工厂扫码报工是并发的 ⇒ 牺牲日常业务换一次性回填，不划算；
- RQ worker 4→2：只省 ~150MB，还降后台吞吐 ⇒ 不值。
- **这台机器日常稳定 2 个多月只挂过 1 次** ⇒ 容量是按日常负载配的；崩溃是**我引入的异常负载**造成的。

**5. 只加 swap 当保险，并保留机器原有调优。**
`fallocate -l 4G /swapfile` + `mkswap` + `swapon` + 写 `/etc/fstab`。磁盘有 300GB+ 富余。
**`vm.swappiness` 保持机器原有的 `0`**（`/etc/sysctl.conf` 里本来就是 0，别擅自改成 10；新内核下 0 仍会在快 OOM 时启用 swap，应急阀照样有效）。
swap 只把"OOM 直接失联"变成"变慢但进得去"，**不会让大批回填变安全**。

**6. 真要回填时的正确姿势**（若必须做）：
- **用 app 内置入口**（只 enqueue），**不要在 `bench console` 里加载大表拼名单**；
- 小批 + 停顿，**夜里低峰**，全程盯 `uptime` / `free -m`；
- 一旦 SSH 变慢就停手——**失联时你连不进去也停不了作业**，只能等人重启。

## Why This Matters

- 无 swap 的小机器上，"内存顶破"的表现是**整机失联**，不是变慢——恢复只能靠重启，期间业务全停。生产上这是最贵的故障形态。
- 误判成因（以为是限流/吞吐）会让人反复用错方法去试，**每试一次就再挂一次**。
- 为了一个一次性任务去减少网页/后台 worker，是**拿日常业务的稳定性去换**，本末倒置。

## When to Apply

- 任何"在 EN 生产跑批量"的念头出现时，先读本篇。
- 生产失联时：先确认是 SSH banner 超时 + HTTPS 也超时（典型被压死），请用户重启；**重启后先只读核对** RQ 队列/注册表是否清空（`rq:queue:*`、`rq:registry:started|failed` 应为 0），确认没有作业会自己重跑，再谈下一步。

## Examples

只读核对（重启后第一件事）：

```bash
ssh 阿里云-FZH-ERPNext-frappe "uptime; free -m; \
  for q in long default short; do echo -n \"q.\$q=\"; redis-cli -p 11000 llen rq:queue:\$q; done; \
  for r in started failed; do echo -n \"reg.\$r=\"; redis-cli -p 11000 zcard rq:registry:\$r; done"
```

加 swap（一次性）：

```bash
sudo fallocate -l 4G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

## Related

- [EN 通途订单/包裹同步为什么会漏与空壳](../integration-issues/en-tongtool-order-package-sync-failures.md) — 本次想回填的对象与它们的真因
- [EN 服务器与环境访问](../../../EN_API/docs/reference/en-server-access.md) — SSH 别名、bench 路径、常见坑
