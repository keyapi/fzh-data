---
okf: v0.1
type: Reference
title: 通途主档 SKU 改名后用本地 gspread 对齐订单 Google Sheet
date: 2026-08-14
category: workflow-issues
module: tongtool_order_cost
problem_type: workflow_issue
component: tooling
severity: high
applies_when:
  - "1.7.0 特殊规则精确匹配漏行，井规则是新通途 SKU、订单导出是旧名"
  - "需要用 Colab 同款 service account 读写 Google Sheet"
  - "不能确定某个像旧名的 SKU 是笔误还是通途主档里另一件货"
tags: [tongtool, sku-rename, gspread, google-sheet, special-rule, fba]
related_components: [tongtool_api, development_workflow]
---

# 通途主档 SKU 改名后用本地 gspread 对齐订单 Google Sheet

## Context

Colab **1.7.0** 对订单 `通途SKU` 与规则表做精确匹配。通途允许改主档 SKU 名：井只维护**新名**，1.4 / Google Sheet 订单常仍是**导出当时的旧名**。2026-06 AMZBAINAUS FBA 因此漏掉大部分 Velvet 行——井明细尾程差约 −$1800，引擎最初只打上名称未改的 Foam 三款（约 −$666）。FBA 负数尾程写入本身已在 PR #171；本条记录的是**改名导致的匹配失败**以及项目里原先没有的 **Google Sheet 本地凭证读写**。

## Guidance

1. **不要改井的新名迁就导出。** 把订单 Google Sheet（以及如需的 1.4 xlsx）旧名换成新名。
2. **凭证按项目分层。** 从 notebook cell 0 抽出 service account 到 `secrets/gsheets-service-account.json`（gitignore），路径写在 `tongtool_order_cost/.env`。不要把私钥提交进 git 或写进 SKILL。
3. **先 dry-run 再 `--apply`。** 只改 SKU 列（优先 `通途SKU`，否则 `SKU`）。不改 MSKU、平台 SKU、成本列。
4. **像旧名的字符串先查通途主档。** Agent 用 Cursor MCP `erp2_product_goodsquery`；CLI 用 `lookup_tongtool_sku.py`（`mcp_http.py`）。配额仍是商户合计 5 次/分钟。
5. **笔误和真 SKU 分开。** `BNFBAvelvetgray60` 是 60CM 真货；`FoamFBA…BLACK-97` 是规则笔误（订单是 100）；`CENKZ…BLACK-97` 是自发货 CEN。

已确认的 2026-06 Velvet 四对映射在 `tongtool_order_cost/tongtool_order_cost/sku_map.py`。

## Why This Matters

精确匹配管道在通途改名后会静默漏规则，表现为「特殊规则没效果」而不是报错。把 gspread 私钥留在 notebook 里也无法给其他 Agent 复用，且容易进 git。本地 SA + dry-run CLI + goodsQuery 把「改哪张表、改哪一列、哪个 SKU 是真货」变成可重复步骤。

## When to Apply

- 1.7.0 / 特殊规则命中行数远小于井明细数量，且漏掉的 SKU 在通途能搜到新名。
- 需要在 Cursor / 其他 Agent 读写与 Colab 相同的 Google Sheet。
- 用户说「通途搜不到这个 SKU」——先 goodsQuery，再决定改规则还是改订单。

## Examples

预检（不写回）：

```bash
uv run python tongtool_order_cost/scripts/bootstrap_gsheets_credentials.py
uv run python tongtool_order_cost/scripts/remap_gsheet_sku.py --sheet 通途订单202606
uv run python tongtool_order_cost/scripts/lookup_tongtool_sku.py BNFBAvelvetgray60
```

用户确认三张表、只改 SKU 列之后：

```bash
uv run python tongtool_order_cost/scripts/remap_gsheet_sku.py --sheet 通途订单202606 --apply
```

2026-08-14 已对 `通途订单202606-特殊规则` 与 `通途订单202606` 各 3 张 FBA 相关表 apply；gray60 计数未变。Notebook 1.7.0 读 gs「和财务部共享」→ ws「Jeck特殊规则-订单改销售额成本」。

## Related

- [tongtool_order_cost 六月调研](../../../tongtool_order_cost/docs/research/2026-08-14-june-fba-sku-remap.md)
- [Google Sheet 凭证](../../../tongtool_order_cost/docs/reference/gsheets-credentials.md)
- [Tongtool ERP2 MCP 共享限流](../integration-issues/tongtool-erp2-mcp-shared-rate-limit.md)
- [通途有库存 SKU 三方主线](../conventions/tongtu-en-sellfox-instock-sku-mainline.md) — 另一条 SKU 主线，不要和本订单成本改名混用
