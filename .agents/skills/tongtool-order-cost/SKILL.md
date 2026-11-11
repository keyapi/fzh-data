---
name: tongtool-order-cost
description: >
  通途订单特殊规则 1.7.0 本地审计、Google Sheet 订单 SKU 改名替换、通途 goodsQuery 校验。
  用户提到特殊规则、订单改销售额成本、黄-特殊规则、Jeck特殊规则（旧表只读）、1.7.0、通途订单202606、
  Google Sheet 通途SKU 替换、gspread、FBA 尾程、账期差异时触发。
  不要用于赛狐打单或 ERPNext 工单排查。
metadata:
  module: tongtool_order_cost
  docs: tongtool_order_cost/docs/index.md
  updated: 2026-11-10
---

# 通途订单特殊规则 / Google Sheet SKU 改名

## 必须先做

1. 读 `tongtool_order_cost/AGENT_HANDOFF.md`。
2. Google Sheet 读写前确认本机有 `secrets/gsheets-service-account.json`（gitignored）。没有则运行 bootstrap，**不要**把 notebook 里的私钥提交进 git。
3. 写回 Google Sheet 必须用户确认：工作表名单、只改哪一列、dry-run 计数。默认 `--dry-run`。
4. 井维护**新**通途 SKU。订单表里的旧名才替换；不要把规则表改回旧名。
5. 替换前用通途 `erp2_product_goodsquery`（或本模块 `lookup_tongtool_sku.py`）确认「像旧名」的 SKU 是不是主档里真实存在的另一件货。
6. 1.7.0 默认读 ws「黄-特殊规则-订单改销售额成本」；旧「Jeck特殊规则-订单改销售额成本」只读留存。

## 管道

| 目的 | 命令 |
|------|------|
| 1.7.0 本地审计 | `uv run python tongtool_order_cost/scripts/run_audit_170.py ...` |
| 抽出 gspread 凭证 | `uv run python tongtool_order_cost/scripts/bootstrap_gsheets_credentials.py` |
| SKU 替换预检 | `uv run python tongtool_order_cost/scripts/remap_gsheet_sku.py --sheet 通途订单202606` |
| 确认后写回 | 同上加 `--apply` |
| 通途主档是否存在 | `uv run python tongtool_order_cost/scripts/lookup_tongtool_sku.py SKU1 SKU2` |

## 铁律

- FBA 尾程参考值：`>0`/`=0` 跳过；`<0` 写入 `运费`（账期差异）。详见 AGENT_HANDOFF。
- 系数与参考值同时出现 → **参考值优先**，系数忽略；引擎打印 `⚠️ ... 按参考值优先`，并计入 `meta["n_mixed_ref_priority"]`；不要整行跳过。
- FBA 28 条规则：`二次加工=0`，`绍兴二次` 承接绍兴包装；参考值数值不变（老板 2026-11-10 确认按现有参考值执行）。
- `BNFBAvelvetgray60` 是 60CM 独立货，不是 gray-100 笔误。
- `FoamFBAKZ159410287-BLACK-97` 是规则笔误，订单侧是 `...-BLACK-100`。`CENKZ159410287-BLACK-97` 是自发货 CEN，不要改。
- 只改 SKU 列（`通途SKU` 优先，否则 `SKU`）。不改 MSKU / 平台 SKU / 成本列。
- Cursor Agent 查主档：用 MCP `user-tongtool_erp2_primary` / `erp2_product_goodsquery`。工具目录没有通途 MCP 时先跑 `uv run python tongtool_api/setup_cursor_mcp.py`，不要静默 HTTP。CLI `lookup_tongtool_sku.py` 仍走 `mcp_http.py`。

## 不要做

- 不要全量导入赛狐。
- 不要把 service account JSON / notebook 私钥写进文档或 commit。
- 不要在未 dry-run 的情况下 `--apply`。
- 不要修改旧 ws「Jeck特殊规则-订单改销售额成本」（只读留存）。
- 不要把新 ws 第 511–516、610–614、776–777 行的系数重新填回；参考值优先，系数只作历史对照。

## 相关经验（docs/solutions）

踩过的坑与设计取舍，动手前先读：

- `docs/solutions/workflow-issues/tongtool-sku-rename-gsheet-remap.md` —— 通途主档 SKU 改名后用本地 gspread 对齐订单 Google Sheet
- `docs/solutions/workflow-issues/tongtool-special-rule-ref-priority-and-bom-caliber.md` —— 特殊规则换表：参考值优先、FBA 列对齐、旧/新 BOM 口径差
