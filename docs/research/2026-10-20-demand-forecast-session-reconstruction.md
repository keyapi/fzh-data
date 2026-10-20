---
okf: v0.1
type: Reference
title: 销量预估会话检索证据（补 PR 里的三篇调研）
description: 2026-08-31 Claude 会话的位置、Prophet 背景落点、会话结束时间与仍缺的转录；方法结论以同目录三篇调研为准
tags: [demand-forecast, prophet, claude-session]
date: 2026-10-20
---

# 销量预估会话检索证据

方法结论在同目录三篇 2026-08-31 调研和 `pb_reconciliation/docs/reference/sku-forecast.md`。本文只记那三篇正文里没有的检索事实，避免以后再把「仓库里没有」当成「没做过」。

## 会话

| 项 | 值 |
|---|---|
| 宿主 | Claude Desktop（3P） |
| 标题 | `Estimate CE from 2025-2026 sales data`（自动标题） |
| 创建 | 2026-08-31 13:50（UTC+8） |
| 最后活动 | **2026-09-02 17:33**（UTC+8）。产物文件日期仍是 8 月 31 日，9 月 2 日没有另写的预测文档 |
| Desktop 会话 | `local_c4491a55-e5b9-4a1c-bc17-6dde9116abd0`（清单里 `isArchived: false`） |
| CLI 会话 | `fc0170d0-a5c6-40eb-822c-284be1e5d4a2` |
| 当时 worktree | `.claude/worktrees/sharp-shannon-a0be9b`，分支 `claude/sharp-shannon-a0be9b`，停在 `8c133d9b` |
| 当时 PR | 无 |

日志（`Claude-3p\logs\main1.log`）在 2026-08-31 14:07 记录该会话的 `ExitPlanMode`，14:08 切到 `acceptEdits`。计划文件路径写在会话元数据里（`~\.claude\plans\d-work-tracy-miller-pb-orders-payment-ad-delightful-crown.md`），2026-10-20 磁盘上已没有这个文件。

本地没有 `fc0170d0` 的 jsonl。2026-10-20 时 `~/.claude/projects` 现存最老的转录大约是 2026-09-16。Desktop 会话条目还在，点开标题能否从云端拉回原文尚未试成。Codex 没有 `sessions/2026/08/31` 目录。Cursor 对话库没有这场专题。

## Prophet 在哪

用户约 2020 年用过 Prophet/ARIMA，并做过每日库存备份、把 0 库存当特殊情况。这句话在 Claude 记忆 `user_sales_forecast_background.md`，`originSessionId` 就是 `fc0170d0`。

三篇调研正文没有 Prophet 这个词。它们把同一件事写成：断货月是截断需求，间歇需求用 Croston/SBA/TSB，不把 Prophet 当作 2026 年的推荐模型。

## 仓库外的那份交付

`D:\Work\美国\Tracy Miller\PB orders\sales_forecast\sales_forecast_CENKZ1325-YELLOW-97_20260831_141542.md`（及同名 xlsx）是 `sku_forecast.py` 的业务输出，不入库。口径和数字以 `pb_reconciliation/docs/reference/sku-forecast.md` 为准。
