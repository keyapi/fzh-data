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
| 最后活动 | **2026-09-02 17:33**（UTC+8）。当天 17:33:30 有一条 160 字消息，17:35 创建了 `practical-paths.md` |
| Desktop 会话 | `local_c4491a55-e5b9-4a1c-bc17-6dde9116abd0`（清单里 `isArchived: false`） |
| CLI 会话 | `fc0170d0-a5c6-40eb-822c-284be1e5d4a2` |
| 当时 worktree | `.claude/worktrees/sharp-shannon-a0be9b`，分支 `claude/sharp-shannon-a0be9b`，停在 `8c133d9b` |
| 当时 PR | 无 |

日志（`Claude-3p\logs\main1.log`）在 2026-08-31 14:07 记录该会话的 `ExitPlanMode`，14:08 切到 `acceptEdits`。计划文件路径写在会话元数据里（`~\.claude\plans\d-work-tracy-miller-pb-orders-payment-ad-delightful-crown.md`），2026-10-20 磁盘上已没有这个文件。

本地没有 `fc0170d0` 的 jsonl。2026-10-20 时 `~/.claude/projects` 现存最老的转录大约是 2026-09-16。Desktop 会话条目还在，点开标题能否从云端拉回原文尚未试成。Codex 没有 `sessions/2026/08/31` 目录。Cursor 对话库没有这场专题。

## 可还原的时间线（文件创建时间 + 日志里的消息长度）

| 时间（UTC+8） | 事件 |
|---|---|
| 2026-08-31 13:50 | 会话创建（标题自动生成） |
| 2026-08-31 14:16–14:17 | `sku-forecast.md`、`sku_forecast.py` 创建 |
| 2026-08-31 14:25 | 用户消息，288 字（原文未留） |
| 2026-08-31 14:26 | `ts-forecast-methods.md` 创建 |
| 2026-08-31 14:34 | 用户消息，212 字（原文未留） |
| 2026-08-31 14:43 | `data-feasibility.md` 创建 |
| 2026-09-02 17:33 | 用户消息，160 字（原文未留）；会话最后活动 |
| 2026-09-02 17:35 | **`practical-paths.md` 创建**（不是修改） |

> 三篇文档 frontmatter 的 `date` 都写 2026-08-31，但 `practical-paths.md` 的**创建时间**是 9 月 2 日 17:35，紧跟在最后一条 160 字消息之后。因此 9/2 并非“没有产出”，它产出的是实用技术路线对比。

消息原文、工具调用、Claude 的中间推理都没有留下；只能还原“PB 基线 → 方法现状 → 数据可行性 → 落地路线”这条四段式顺序，不能还原讨论过程。

## Prophet 在哪

用户约 2020 年用过 Prophet/ARIMA，并做过每日库存备份、把 0 库存当特殊情况。这句话在 Claude 记忆 `user_sales_forecast_background.md`，`originSessionId` 就是 `fc0170d0`。

三篇调研正文没有 Prophet 这个词。它们把同一件事写成：断货月是截断需求，间歇需求用 Croston/SBA/TSB，不把 Prophet 当作 2026 年的推荐模型。

## 交接时必须说明的事实（三篇正文没写）

- **为什么开这个项目**：PB 的单 SKU 预估（`CENKZ1325-YELLOW-97`）已经交给同事，但被其他渠道的补货覆盖了；PB 单渠道量太小，不能代表全公司需求，所以才要公司级 `demand_forecast`。这条只在 Claude 项目记忆里，三篇正文没写。
- **进度边界**：阶段 A（数据可行性）完成；阶段 B（建模）**未启动、未拍板**，不是已排期；`demand_forecast/` 目录从未创建。下一步清单见 `data-feasibility.md` §6。
- **PB 基线不是公司级模型**：M1 运行率 / M2 同比 / M3 趋势 / M3b 季节平均只针对 PB 单 SKU；2026-08-31 的输出是推荐约 15 件、建议备货约 19 件。脚本按运行当天日期计算窗口，重跑数字会变，不能当固定结论。
- **已定的产品决定**：现阶段不上 Chronos 等 TSFM；断货月必须打标、不当普通 0；补货同事的特殊情况要做成可录入的例外层。
- **时效**：三篇是 2026-08-31 的结论。2026 方法 SOTA 以 PR #301 的 `forecasting-agents.md` 为准（Chronos-2 / TimesFM-3 / Moirai 2.0 及许可边界已更新），但“现阶段不采用 TSFM”的决定不变。
- **凭证与复用入口**：凭证只在父仓库 `D:\Work\赛狐\Cursor` 的 `secrets/gsheets-service-account.json`、`EN_API/.env`、`tongtool_api/.env`，worktree 里没有；读表用 `tongtool_order_cost/tongtool_order_cost/gsheets.py`，EN 用 `missing_products/audit_three_systems.py`。
- **脚本定位**：`sku_forecast.py` 是硬编码本机路径的一次性 PB 脚本，不是可复用的公司级数据层；阶段 B 需要重写订单读取层。

## 仓库外的那份交付

`D:\Work\美国\Tracy Miller\PB orders\sales_forecast\sales_forecast_CENKZ1325-YELLOW-97_20260831_141542.md`（及同名 xlsx）是 `sku_forecast.py` 的业务输出，不入库。口径和数字以 `pb_reconciliation/docs/reference/sku-forecast.md` 为准。
