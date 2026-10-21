---
okf: v0.1
type: Review
title: 库存入库代码第二次复审（571929fa）
date: 2026-10-22
reviewer: codex
verdict: fail-1-rollback
---

**FAIL，暂不放行 (a)/(b)。**

六项均有实现及测试断言，但内存库复现回滚漏洞：A 发布→B 替换→重导 A（哈希相同、外部基线校验失败），A 被改为 `integrity_ok=false`，回滚随即失败。

最小修复：`stock_history_ingest.py:1359` 将失败重导保护扩至所有已存 run；在 `:1368` 删除前拒绝，保留旧行、元数据及指针。补上述序列测试。

26 条测试确有断言，锁测试含跨进程竞争及强杀恢复；但依赖临时文件、锁和临时库，严格只读下不能原样运行，本轮未跑全套。两天原文件与 dry-run 哈希基线一致。未访问通途/EN、未写 order_store。
