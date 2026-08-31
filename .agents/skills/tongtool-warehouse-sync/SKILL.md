---
name: tongtool-warehouse-sync
description: >
  通途自发货仓库改名/新增后的三处对账登记：通途当前仓库清单 → 生产 ERPNext Tongtu
  Shipping Warehouse 记录 → 财务共享表「订单发货仓库对应成本来源」。用户提到 通途仓库改名、
  Tongtu Shipping Warehouse、通途发货仓库、财务共享表、订单发货仓库对应成本来源、
  发货仓库加行、仓库对账 时触发。不要用于订单成本规则/SKU 改名（那是 tongtool-order-cost）。
metadata:
  module: tongtu_shipping_warehouse
  docs: docs/solutions/workflow-issues/tongtu-warehouse-rename-reconciliation.md
  updated: 2026-08-19
---

# 通途发货仓库改名对账与登记

完整流程见 `docs/solutions/workflow-issues/tongtu-warehouse-rename-reconciliation.md`。这里是可复跑清单。

## 必须先做

1. 读 `docs/solutions/workflow-issues/tongtu-warehouse-rename-reconciliation.md`。
2. 凭证在**父仓库** `D:\Work\赛狐\Cursor`，不在 worktree：`tongtool_api/.env`（通途 MCP）、`EN_API/.env`（生产 ERPNext）、`secrets/gsheets-service-account.json`（Google Sheet）。worktree 里跑脚本要 `GSPREAD_SERVICE_ACCOUNT_FILE` 指到父仓库路径，或从父仓库 cwd 运行。
3. **一律 `uv run python`**，不要在本机系统 python 上 pip 装包。
4. 通途中文名控制台会乱码（GBK/UTF-8）——写 UTF-8 文件再 Read。
5. 写财务共享表前先 dry-run 给用户确认。

## 管道

| 目的 | 方式 |
|------|------|
| 查通途当前仓库 | MCP `erp2_basedata_warehousequery`（pageNo/pageSize，`warehouseName` 是精确匹配）；凭证 `tongtool_api/.env` |
| 查生产 ERPNext 登记 | `GET /api/resource/Tongtu Shipping Warehouse`（`EN_API/.env` 凭证，erpnext.vilavi.cn） |
| 建 ERPNext 记录 | `POST /api/resource/Tongtu Shipping Warehouse`，**照抄同分公司现有记录的 12 个成本列** |
| 交叉核对订单 | 生产 `Tongtool Order.warehouse_name` 分布（旧名量大→旧记录保留；新前缀名出现→需登记） |
| 财务表加行 | gspread `gsheet2df`/`append_rows`（参考旧名行、只改第一列；先 dry-run） |

## 铁律

- **旧仓库名绝不删**：历史订单（Tongtool Order）大量引用旧名（不带前缀）。
- 新建 ERPNext 记录：`warehouse_classification` 是 **Link** 字段（USNJ美东分公司/USTX美中分公司/PL波兰分公司），成本列照抄，不要自造。
- 财务表 8 列编码口径：CENTRADE→HEAD-US/2CJG-US；FZH-DANEEY 主仓/皮壳→HEAD-USTX-PK/2CJG-SX；成品/半成品/退货→HEAD-USTX/2CJG-SX；FZHPoland-covers→HEAD-PL/2CJG-PL。
- 美东/波兰退货仓无旧名行可参考 → 按分公司主仓口径推断，**必须经用户确认**再写。
- 不把 service account / notebook 私钥写进文档或 commit。

## 不要做

- 不要全量导入赛狐。
- 不要用本机系统 python。
- 不要在 worktree 里找凭证。
