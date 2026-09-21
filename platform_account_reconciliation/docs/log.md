---
okf: v0.1
type: Log
title: 变更日志
description: 平台账期对账模块的时序变更记录
tags: [platform, reconciliation, changelog]
timestamp: 2026-08-17
---

# 变更日志

## 2026-09-21

- **新增 Walmart 线路**：数据源**不再是财务手工 xlsx**，改为赛狐 API 直拉账期结算行（`SELLFOX_API/probe_walmart_settlement.py`），再与 EN / `platform_code=walmart_api` 的 Tongtool Order 勾稽。
- **脚本**：新增 `scripts/reconcile_walmart.py` —— 跨账期合并勾稽 + 平台费口径判定，输出 `账期总览/订单级勾稽/账期费用分类/账期明细`。
- **实测结果**：Walmart 是**双周账期（14 天）**；最近 3 个账期销售额**分毫不差**（1317.28 / 1511.75 / 4346.60），订单级 73/77 精确一致。
- **口径结案**：`赛狐佣金 = (商品价 + 沃尔玛补贴) × 15%` vs `EN platform_fee = 商品价 × 15%`，差额 = 补贴 × 15%，逐单 64/64 命中。**EN 漏算补贴基数**，赛狐对。为 §7 那笔未结案的 OSTKUS 同型差额提供了复查方法。
- **修复**：`reconcile_ostkus.py` 的 `ENV_FILE` 改为向上搜索，修掉「worktree 里因凭证只在主仓库而跑不起来」。
- **文档**：`AGENT_HANDOFF.md` 增补 §10 Walmart 章节；调研全记录见 `docs/research/2026-09-21-sellfox-walmart-settlement-api.md`。

## 2026-09-20

- **修复（链接）**：`index.md` 指向模块 `AGENT_HANDOFF.md` 的链接多退一级（`../../` → `../`），修正为模块内相对路径。

## 2026-08-17

- **初始化模块**：新建 `platform_account_reconciliation/`，覆盖 Overstock/OSTK 账期与 EN/Tongtool Order 费用级对账，预留 Wayfair 扩展。
- **脚本**：新增 `scripts/reconcile_ostkus.py`，支持多账期文件、Payment Summary 解析、EN 只读拉取、拆单/重复主单识别和工作簿生成。
- **文档**：新建 OKF bundle、AGENT_HANDOFF、README、Skill，并记录 07-01/07-16 对账结果与字段口径。
- **本次结果**：350 个基础 OS 订单全部覆盖；销售金额两期差异 0；4 个跨期退单；EN 平台费与账期营销扣点差异待确认。
