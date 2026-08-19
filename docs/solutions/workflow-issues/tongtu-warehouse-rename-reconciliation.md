---
okf: v0.1
type: Reference
title: 通途自发货仓库改名后的对账与登记（ERPNext + 财务共享表）
date: 2026-08-19
category: workflow-issues
module: tongtu_shipping_warehouse
problem_type: workflow_issue
component: erpnext-configuration
severity: medium
applies_when:
  - "通途自发货仓库改名/新增（出现美东-/美中-/波兰- 前缀），需要在生产 ERPNext 与财务共享表补登记"
  - "生产 ERPNext `Tongtu Shipping Warehouse` 缺记录，需按分公司分类/成本列照抄新建"
  - "给「和财务部共享」→ ws「订单发货仓库对应成本来源」加行"
tags: [tongtu, warehouse, rename, reconciliation, erpnext, gspread, google-sheet, finance]
related_components: [tongtool_api, erpnext, tongtool_order_cost]
---

# 通途自发货仓库改名后的对账与登记

## Context

通途（ERP2.0）自发货仓库近期改名：主仓加了 `美东-`/`美中-`/`波兰-` 前缀（如 `CENTRADE` → `美东-CENTRADE`），并新增了两个退货仓（`美东-CENTRADE-退货产品仓`、`波兰-FZHPoland-退货产品仓`，2026-08-14 建）。总体原则是 **3 家国外分公司（USNJ 美东 / USTX 美中 / PL 波兰）各保留 1 个普通仓 + 1 个退货仓**；**旧仓库名（不带前缀）必须保留**，因为历史订单（Tongtool Order）仍引用旧名。

生产 ERPNext 只有旧名登记，新前缀名全部缺失；财务共享表「订单发货仓库对应成本来源」也只有旧名行。本次会话完成了「通途 → 生产 ERPNext Tongtu Shipping Warehouse → 财务共享表」三处的对账与补登记。

## 现状（2026-08-19）

| 分公司 | 通途当前启用（普通+退货） | ERPNext 旧名登记（保留） | ERPNext 新前缀名（本次补建/核对） |
|---|---|---|---|
| 美东 USNJ | 美东-CENTRADE、美东-CENTRADE-退货产品仓 | CENTRADE、WayfairCG-Cranbury仓 | 美东-CENTRADE、美东-CENTRADE-退货产品仓 |
| 美中 USTX | 美中-FZH-DANEEY、美中-FZH-DANEEY-退货产品仓、FZH-DANEEY-成品仓、FZH-DANEEY-半成品仓 | FZH-DANEEY、FZH-DANEEY-皮壳仓库/成品仓/半成品仓/退货产品仓 | 美中-FZH-DANEEY、美中-FZH-DANEEY-退货产品仓、美中-FZH-DANEEY-皮壳仓库 |
| 波兰 PL | 波兰-FZHPoland-covers、波兰-FZHPoland-退货产品仓 | FZHPoland-covers、FZHPoland-finished、波兰公司 | 波兰-FZHPoland-covers、波兰-FZHPoland-退货产品仓 |

> 皮壳仓注意：通途当前仓库清单里**没有** `美中-FZH-DANEEY-皮壳仓库` 任何形态，但生产订单里新前缀名仍有 149 条、旧名 2145 条（同事确认通途曾短暂把该仓改成前缀名）。旧名 `FZH-DANEEY-皮壳仓库` 保留；新前缀 `美中-FZH-DANEEY-皮壳仓库` 需补建（本会话已建）。

## 过程（可复跑）

### 1. 查通途当前仓库

MCP 工具 `erp2_basedata_warehousequery`，参数 `pageNo/pageSize`（可带 `warehouseName`，但该参数是精确匹配，搜「皮壳」搜不到）。凭证在父仓库 `tongtool_api/.env`（`TONGTOOL_ERP2_PRIMARY_KEY/SECRET`）。**中文名注意 GBK 编码**：直接把返回打印到控制台会乱码，先写 UTF-8 文件再用 Read 读。

```python
# uv run python ... （见 tongtool_api/test_mcp_rate_limit.py 的 McpClient 骨架）
# 调用 erp2_basedata_warehousequery pageNo=1 pageSize=200
# status==1 是启用，status==0 停用
```

### 2. 查生产 ERPNext `Tongtu Shipping Warehouse`

凭证 `EN_API/.env` 的 `ERP_API_KEY/ERP_API_SECRET`（生产 erpnext.vilavi.cn）。关键字段：

- `warehouse_name`（Data）
- `warehouse_classification`（**Link → Tongtu Shipping Warehouse Classification**，值如 `USNJ美东分公司`/`USTX美中分公司`/`PL波兰分公司`，不是自由文本）
- `shipping_region`（Select：美国/欧洲/英国/日本/加拿大）
- `warehouse_code`（Select：USNJ/USTX/PL/…）
- 成本列：`shell_cost_column_name`/`shaoxing_*_cost_*`/`processing_cost_name`/`first_leg_*_freight_name`

```bash
# 复用 erpnext/scripts/fetch.py 的 api_get 模式
GET https://erpnext.vilavi.cn/api/resource/Tongtu%20Shipping%20Warehouse
# 新建:
POST /api/resource/Tongtu Shipping Warehouse   # body 见下
```

**新建记录照抄同分公司现有记录的 12 个成本列**（不要自己编）。示例 `美中-FZH-DANEEY-皮壳仓库`（照抄 `美中-FZH-DANEEY`）：

```json
{
  "warehouse_name": "美中-FZH-DANEEY-皮壳仓库",
  "warehouse_classification": "USTX美中分公司",
  "shipping_region": "美国",
  "warehouse_code": "USTX",
  "shell_cost_column_name": "皮壳成本",
  "shaoxing_semi_finished_cost_column_name": "绍兴包装半成品成本",
  "shaoxing_finished_cost_name": "绍兴包装成品成本",
  "shaoxing_total_cost_name": "绍兴总成本",
  "processing_cost_name": "美中加工成本<br>USTX",
  "first_leg_shell_freight_name": "头程皮壳运费<br>美中USTX",
  "first_leg_semi_finished_freight_name": "头程半成品运费<br>美中USTX",
  "first_leg_finished_freight_name": "头程成品运费<br>美中USTX"
}
```

### 3. 用生产订单交叉核对

生产 `Tongtool Order.warehouse_name` 分布（近 1 万条）同时出现旧名（`CENTRADE`×2698、`FZH-DANEEY-皮壳仓库`×2145…）和新前缀名（`美东-CENTRADE`×557、`美中-FZH-DANEEY`×380…）。**旧名量大 → 旧记录绝不可删**；新前缀名已在订单出现 → 需登记。

### 4. 财务共享表加行

「和财务部共享」→ ws「订单发货仓库对应成本来源」，8 列：

`发货仓库 | 对应成本工作簿 | 成本来源编码 | 发货仓分类 | 头程运费来源编码 | 二次加工成本来源编码 | 发货区域 | 发货仓按销售汇总分类`

新前缀仓库**参考已有旧名行、只改第一列**。编码口径（现有行规律）：

| 仓库族 | 对应成本工作簿 | 成本来源编码 | 头程 | 二次加工 | 汇总分类 |
|---|---|---|---|---|---|
| CENTRADE（美东主仓） | 美国公司 | COST-US | HEAD-US | 2CJG-US | USNJ分公司 |
| FZH-DANEEY / 皮壳 | 美国公司 | COST-US | HEAD-USTX-PK | 2CJG-SX | USTX分公司 |
| FZH-DANEEY 成品/半成品/退货 | 美国公司 | COST-US | HEAD-USTX | 2CJG-SX | USTX分公司 |
| FZHPoland-covers | 波兰公司 | COST-PL | HEAD-PL | 2CJG-PL | 波兰分公司 |
| FZHPoland-finished | 欧洲海外仓 | COST-EUHWC | HEAD-EUHWC | 2CJG-SX | 波兰分公司 |

美东/波兰退货仓无旧名行可参考 → 按分公司主仓口径推断（美东→HEAD-US/2CJG-US，波兰→HEAD-PL/2CJG-PL），**加行前向用户确认**。写回用 gspread `ws.append_rows(rows, value_input_option="USER_ENTERED")`，先 `get_all_values()` 防重复。

```bash
# 本机凭证在父仓库 secrets/gsheets-service-account.json；worktree 里没有，要指过去
GSPREAD_SERVICE_ACCOUNT_FILE='D:\Work\赛狐\Cursor\secrets\gsheets-service-account.json' \
  uv run python <脚本>   # 复用 tongtool_order_cost/gsheets.py 的 client()
```

## 经验教训

1. **凭证在父仓库不在 worktree**。本项目开 git worktree；`EN_API/.env`、`tongtool_api/.env`、`secrets/gsheets-service-account.json` 全部 gitignore，只存在于 `D:\Work\赛狐\Cursor`。在 worktree 里跑脚本要设置 `GSPREAD_SERVICE_ACCOUNT_FILE` 指到父仓库路径，或直接 `uv run` 时从父仓库 cwd 运行（`gsheets.py` 的 `REPO_ROOT = parents[2]` 会解析到运行处）。
2. **一律 `uv run`，不要在本机系统 python 上 pip 装包**。系统 python 没有项目依赖（gspread/google-auth 等）；pyproject 已声明。
3. **控制台中文乱码（GBK/UTF-8）**：把结果写 UTF-8 文件再 Read，不要靠 print 到终端。
4. **写财务共享表前先 dry-run**：先展示要追加的行（含推断编码），用户确认后再 `append_rows`。财务共享表是共享外部系统，宁可多确认一次。
5. **`warehouse_classification` 是 Link 字段**，值来自 `Tongtu Shipping Warehouse Classification` doctype（USNJ美东分公司/USTX美中分公司/PL波兰分公司/FBA 类/海外仓类），新建记录不要自造。
6. **新旧名关系是 1:1 映射**：新前缀名照抄旧名行；旧名行保留给历史订单。除非通途明确合并/停用（皮壳仓例外，需人工确认）。

## When to Apply

- 通途再次改名/新增自发货仓库时，重跑本流程（通途清单 → ERPNext 记录 → 财务共享表）。
- 用户提到「Tongtu Shipping Warehouse」「通途发货仓库」「财务共享表」「订单发货仓库对应成本来源」「仓库改名」。

## Related

- [通途主档 SKU 改名后用本地 gspread 对齐订单 Google Sheet](tongtool-sku-rename-gsheet-remap.md) — SKU 改名（非仓库）；gspread 凭证用法相同
- [Google Sheet 凭证](../../../tongtool_order_cost/docs/reference/gsheets-credentials.md) — service account 分层
- [ERPNext Workflow 配置指南](../erpnext-workflow-configuration.md) — ERPNext 侧 DocType 概念
- [Tongtool ERP2 MCP 共享限流](../integration-issues/tongtool-erp2-mcp-shared-rate-limit.md) — 通途 API 5 次/分钟
- [通途有库存 SKU 三方主线](../conventions/tongtu-en-sellfox-instock-sku-mainline.md) — 另一条主线，不要和仓库登记混用
