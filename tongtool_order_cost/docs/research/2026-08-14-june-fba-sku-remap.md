---
okf: v0.1
type: Research
title: 2026-06 AMZBAINAUS FBA 尾程差与通途 SKU 改名
description: 井估算约 1800 美元与引擎只打上约 666 美元之间的缺口；旧名/新名、规则笔误、Google Sheet 替换
tags: [fba, last-mile, sku-rename, amzbainaus, 202606]
timestamp: 2026-08-14
---

# 2026-06 AMZBAINAUS FBA 尾程差与通途 SKU 改名

## 背景

同事（Jeck / 井）对 AMZBAINAUS 六月「无规则 vs 有规则」总成本有异议。六月规则主要是 **ref 模式**（USD 参考值 × 汇率 → 人民币），不是在旧成本结构上打折。皮壳成本可能上升，同时尾程/头程下降。

FBA 尾程：Amazon 账期已含 FBA fulfillment。井在规则里填的是**负数差额**（账期尾程 − 目标尾程）。引擎（PR #171）对 FBA 仅在参考值 `< 0` 时写 `运费`；`≥ 0` 仍跳过以免重复计入。

井用新 SKU 做的 FBA 订单明细：100CM + 153CM 合计数量约 301，尾程差合计约 **−$1,801**。本地 1.7.0 最初只打上 Foam Grey-100 / Grey-150 / BLACK-153（名称未改），FBA 运费 Δ 约 **−¥4,541 ≈ −$666**。

## 根因

通途允许改主档 SKU。特殊规则与井明细用**新名**；8/6 订单成本与 7 月初销量报表多为**旧名**。精确匹配漏掉大部分 Velvet FBA 行。

方向确认（2026-08-14）：井只维护新名 → **替换订单侧旧名**。

## 阶段性结果

1. 确认 4 对 Velvet 旧→新（见 [sku-remap.md](../reference/sku-remap.md)）。
2. `Foam…BLACK-97` 在通途订单中不存在，只有 `…BLACK-100`；规则第 820 行笔误。`CENKZ…BLACK-97` 是另一件自发货货。
3. `BNFBAvelvetgray60` 经 `erp2_product_goodsquery` 确认存在：`三角无扣 60CM 灰色 荷兰绒 靠枕CEN`，别名 `BNvelvetgray60fba`。不是 gray-100 笔误。
4. 只读预检后，用户确认：三张 FBA 相关表都改，只改 SKU 单元格。
5. 已写回 gs `通途订单202606-特殊规则` 与 `通途订单202606` 各 3 张表（4 + 168 + 168 格）。gray60 未动。
6. gs `和财务部共享` / ws `Jeck特殊规则-订单改销售额成本`：井已改 Velvet 新名，Foam 已是 BLACK-100。旧 ws `特殊规则-订单改销售额成本`（notebook 不用）：用户已改 2 处 Foam 97→100；Velvet 新旧各 1 行仍并存。

## 汇率

本次对账使用 USD **6.8167**。

## 后续

- 当时 Cursor 未装通途 MCP，SKU 校验走 `tongtool_api/mcp_http.py`。Cursor MCP 安装见 `tongtool_api/docs/research/2026-08-14-cursor-mcp-install.md`。
- 长期：通途改名会打断精确匹配管道，需要别名表或「按导出日 SKU」约定。
