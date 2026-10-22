---
okf: v0.1
type: Review
title: 归档器第二次复审
date: 2026-10-22
reviewer: codex
verdict: fail-3
---

**FAIL；(a)(b)均不放行。**

1. 元数据篡改、已封存未知 tmp 已拦截；但未封存目录的任意 tmp 仍被放过（archive:599）。
2. 缺仓、缺文件、truncated/bad_rows 已闭环。
3. 穿越及仓库文件越界链接已有拒绝检查。
4. 互斥未闭环：锁超600秒即删除，活进程长读/复制可被抢锁；旧持有者还会删除新锁。
5. cmd 退出码、跨日绑定逻辑已修复。

run-state 单写者 replace 原子，但固定 tmp 并发不安全；缺 run_id/date 仍被接受，日期绑定可绕过。

最小修复：拒绝未知 tmp；使用进程级锁；状态改唯一临时文件并 fsync，强校验日期/run_id。

只读内存反例已验证；未运行会落盘的31项测试。
