---
okf: v0.1
type: Log
title: architecture-patterns — 变更日志
tags: [solutions, architecture-patterns, log]
---

# architecture-patterns 变更日志

## 2026-10-14

- **更新**: `office-egress-fallback-chain.md`（`last_updated: 2026-10-14`）—— ① 新增「主线路内部还分了两条」：通用线 `BoostNet → 自动选择`(url-test) **会自愈**，而 AI 域名走的 `AI 出口 → 区域组 → 节点` **三层全是手动 select、无自动故障转移** ⇒ 症状是「通用线自己好了、AI 线还卡着」；同一节点名在 `proxies:` 里只有一个定义、可被多个组引用 ⇒ **两条线常常是同一台服务器**。② 「怎么判断走哪条线」补**分应用判线法**（按域名 grep 日志看 `using 组[节点]`）与「日志被 watchdog 按大小清空、历史留不住」。③ 补日常维护窗口（每天 04:30 路由器重启 / 07:00 OpenClash 重启）与订阅自动更新关闭的现状。④ **订正**原文「已在 OpenClash 侧修正优先级」—— 2026-10-13 复查发现 `Emergency` 组同时入向引用为零，「修过优先级」≠「接上了」。⑤ 记录当日变更：`AI 出口` 末尾接入 `Emergency` 作人工兜底。

## 2026-09-22

- **新增**: `public-private-agent-knowledge-split.md` — 公开仓、私有 Markdown 知识仓与 secret manager 三层分离；普通 clone + bootstrap 代替 submodule，保留 Agent 检索和非技术同事使用体验。
