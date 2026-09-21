---
okf: v0.1
type: Research
title: 赛狐 Walmart 账期（结算明细）API 实测可行性
description: 赛狐公开 OpenAPI 的 Walmart 结算明细端点实测打通记录 —— periodStartDate/periodEndDate 账期字段真实可用，且 purchaseOrder 与 EN Tongtool Order platform_order_id 100% 匹配；含分页、限流、拆单等实测坑
tags: [sellfox, walmart, settlement, account-reconciliation, en, research]
timestamp: 2026-09-21
---

# 赛狐 Walmart 账期 API 实测可行性

调研动机：`platform-account-reconciliation` 模块的账期数据源一直是**财务同事手工提供的平台 xlsx**，
想做自动化就需要一条能通过 API 拉平台账期的路。本文验证赛狐是否为 Walmart 提供了这条路。

一句话结论：**能。而且是目前唯一能自动化的平台账期数据源，且与 EN `Tongtool Order` 100% 对得上。**

## 1. 结论摘要

| 问题 | 实测结论 |
|---|---|
| 赛狐有 Walmart 账期端点吗 | 有，公开 OpenAPI（非私有接口），无需 cookie |
| App 权限开通了吗 | 已开通，`code=0`，无需单独申请 |
| `periodStartDate`/`periodEndDate` 真有值吗 | **真有，200/200 行非空** |
| 能对到 EN 订单吗 | **44/44（100%）命中**，`purchaseOrder` == EN `platform_order_id` |
| 商品级能对上吗 | 能，赛狐 `partnerItemId` == EN `Item.platform_sku` |
| 销售额能勾稽吗 | **能，3 个账期分毫不差**（1317.28 / 1511.75 / 4346.60 全部 0.00） |
| 平台费口径差查清了吗 | **查清了** —— 差 = 沃尔玛补贴 × 15%，EN 漏算补贴基数（详见 §3.4） |
| 其他平台也能这样拉吗 | **不能**。Wayfair 无任何财务端点；Overstock 在赛狐平台枚举里不存在 |
| 需要通途 API 辅助吗 | **不需要**。销售额 100% 一致已证明 EN 快照忠实；且通途限速 5 次/分钟 |

## 2. 端点

主端点（行级结算明细）：

```
POST /api/financial/walmartReport/queryStatementDetail.json
```

- 必填：`transactionPostedStartDate` / `transactionPostedEndDate`（`yyyy-MM-dd`，按**结算时间**过滤）
- 可选：`marketplaceCode`、`shopId[]`、`fulfillmentType[]`（`Seller Fulfilled` / `Walmart-fulfilled(WFS)`）、
  `searchType`(`msku|orderId|partnerGtin`) + `searchMode`(`exact|blur`) + `searchContents[]`、
  `orderBy`(`transaction_posted_date|amount|ship_qty`)、`desc`、`pageNo`、`pageSize`（默认 20，**最大 200**）
- 返回 `data.rows[]`，行字段：`periodStartDate` / `periodEndDate`（**账期**）、`transactionPostedDate`（结算时间）、
  `transactionType`、`amountType`、`transactionDescription`、`amount`、`currency`、`shipQty`、
  `purchaseOrder`、`partnerItemId`、`partnerGtin`、`fulfillmentType`、`shopId/shopName`、`marketplaceCode/marketplaceName`

同族聚合视角（同一 `/api/financial/walmartReport/` 前缀，均按 `transactionPostedStartDate/EndDate` 过滤）：

| 端点 | 文档 | Apifox |
|---|---|---|
| `queryPageShop.json` | 查询店铺（返回 70+ 财务字段：回款额/佣金净额/WFS 费用/广告费/毛利…） | api-365907921 |
| `queryPageSku.json` | 查询 SKU | api-365907922 |
| `queryPageMsku.json` | 查询 MSKU | api-365907919 |
| `queryPageSalesMan.json` | 查询业务员 | api-365907920 |
| `queryPageDeveloper.json` | 查询开发员 | api-365907918 |

## 3. 实测证据

环境：代理模式（`api.vilavi.cn/sellfox/v1/sellfox-main`），凭证取父仓库 `D:/Work/赛狐/Cursor/.env` 的 `SELLFOX_PROXY_API_KEY`。

### 阶段 1 — 店铺

`POST /api/multiplatform/shop/list.json` body `{"platformType":"WALMART","pageNo":1,"pageSize":100}` → `code=0`，**1 家**：

```
id=598030  站点(空)  币种(空)  状态=0  Centrade
```

> 注意：首次调用时 `marketplaceCode` / `currency` 为**空**，再次调用返回 `US` / `空` —— 该字段不稳定，
> **不要依赖店铺列表拿站点**，站点/币种以结算明细返回的 `marketplaceCode`/`marketplaceName`/`currency` 为准（实测 `US` / 美国 / `USD`）。

### 阶段 2 — 结算明细（关键）

`shopId=[598030]`、`2026-08-01 → 2026-09-21`、`pageSize=200`：

- 第 1 页 200 行（打满上限），第 2 页 63 行 → **共 263 行**
- **`periodStartDate`/`periodEndDate` 非空 200/200** ← 决定性指标
- 该窗口内**只有 1 个账期**：`2026-08-08 → 2026-09-05`

取值分布（263 行窗口内一页 200 行）：

| 维度 | 取值 |
|---|---|
| `transactionType` × `transactionDescription` | `Sale`/`Purchase`(168)、`Refund`/`Return Refund`(26)、`Refund`/`Seller Initiated Returns`(2)、`Service Fee`/`Walmart Return Shipping Charge`(3)、`Service Fee`/`Walmart Product Advertising`(1) |
| `amountType` | `Commission on Product`(47)、`Product Price`(46)、`Product tax withheld`(44)、`Product tax`(44)、`Total Walmart Funded Savings`(15)、`Item Fees`(3)、`Fee/Reimbursement`(1) |
| `fulfillmentType` | `Seller Fulfilled`(199/200，1 行为空) |
| `currency` / 站点 | `USD` / `US`（商店名「美国」） |

样本行：

```json
{"currency":"USD","shopId":598030,"shopName":"Centrade","marketplaceCode":"US","marketplaceName":"美国",
 "periodStartDate":"2026-08-08","periodEndDate":"2026-09-05","purchaseOrder":"129124814640462",
 "amount":-10.5,"partnerItemId":"WMDog-Car-Seat-L","shipQty":1,"transactionType":"Sale",
 "transactionDescription":"Purchase","amountType":"Commission on Product",
 "transactionPostedDate":"2026-09-04","partnerGtin":"06920529215065","fulfillmentType":"Seller Fulfilled"}
```

### 阶段 3 — EN 对账

EN 生产 ERPNext 的 Walmart 单：

| 属性 | 值 |
|---|---|
| `platform_code` | **`walmart_api`** |
| `name` | **`WM-{platform_order_id}`** |
| `platform_order_id` | **就是赛狐的 `purchaseOrder`** |
| `sale_account` | `WM-CtrdUS` |
| item 级 `platform_sku` | **就是赛狐的 `partnerItemId`** |

匹配率：**44/44 = 100%**（`filters=[["Tongtool Order","platform_order_id","in",pos]]`）。
44 单 `order_status`：已发货 42 / 等待配货 2；`sale_time` 分布 2026-07-14 ~ 2026-09-04。

EN WM 单规模：`name like 'WM-%'` 共 **459 条**，去重 **442 个 PO 号**。

### 3.4 账期勾稽（跨账期合并，最近 3 个账期）

**关键前提：必须先摸清账期节奏。** Walmart 是**双周账期（14 天）**，2026 年共 15 段，
从 `2026-01-24` 起每 14 天一档。用 `--discover-periods` 翻全窗口即可列出（见 §7）。
唯一异常：`2026-08-08 → 2026-09-05` 是 **28 天**（正好两个 14 天期），220 行，是常规期的 2~3 倍 —— 疑似两期合并，待确认。

**必须跨账期合并看，否则必然错位。** 赛狐按 `periodStart/End` 分账期，而 EN 的订单只有一条。
同一 PO 的销售行与后续退货/费用行常落在相邻账期（实测 58 单里有 12 单如此）。

拉最近 3 个账期（`2026-07-11→07-25` 80 行 / `07-25→08-08` 84 行 / `08-08→09-05` 220 行，共 384 行 / 78 单）：

| 账期 | 赛狐销售额 | EN 商品额 | 差异 |
|---|---|---|---|
| 2026-07-11 → 07-25 | 1,317.28 | 1,317.28 | **0.00** |
| 2026-07-25 → 08-08 | 1,511.75 | 1,511.75 | **0.00** |
| 2026-08-08 → 09-05 | 4,346.60 | 4,346.60 | **0.00** |

订单级：**销售额精确一致 73/77**；4 单标「本期无销售行(跨期)」——
它们的销售行落在本次未拉的更早账期，不是差异。

**平台费口径之谜解开（本次最重要的发现）**

销售额一致的 73 单里，平台费差都**不是费率问题**，而是**佣金基数不同**：

```
赛狐 Commission on Product = (商品价 + Total Walmart Funded Savings) × 15%
EN   platform_fee          =  商品价 × 15%
                            差额 = 沃尔玛补贴 × 15%
```

验证：逐单 **64/64 命中**（残差全为 ±0.00，纯四舍五入）；
汇总差 **28.28** vs 沃尔玛补贴合计 × 15% = **28.32**（差 0.04 来自逐单取整）。

> **结论：赛狐是对的，EN 的 `platform_fee` 漏算了 Walmart Funded Savings 基数。**
> 该类目佣金率就是 15%，恒定 —— 之前看到的「15%~17% 飘忽」全部由补贴基数差异造成。
>
> **对 OSTKUS 的启示**：OSTKUS 那笔至今未结案的 `platform_fee vs 营销扣点` 差额
> （-25.73 / -36.52）很可能是**同一类问题** —— EN `platform_fee` 漏了某个基数项，
> 值得用同样方法回去查。

另有 9 单标「佣金已退货冲平(EN未冲)」：赛狐本账期佣金净额为 0（销售佣金被退货冲回），
而 EN `platform_fee` 仍是订单发生时的原值、不随退货调整 —— 这是**时点口径差异**，非错误。

判定结果：**无口径异常**，所有差异都被上述两条解释完。

## 4. 实测踩到的坑（后续实现必读）

1. **`data` 没有分页元信息** —— 只返回 `rows`，**没有 `totalSize`/`totalPage`**。
   必须一直翻页直到某页返回条数 < `pageSize` 为止，不能靠元数据判断结束。
2. **代理限流有两种响应形态** —— `SELLFOX_API/client.py:114` 的 `is_rate_limited_response()`
   只认 `code == 40019`，但实际还会遇到 HTTP 层 `{"detail": "Global rate limited. Retry after 0.3s"}`（**没有 `code` 字段**）。
   探针 `raw_post()` 已两种都识别并退避重试；模块化时要么复用这个判断，要么补进 client.py。
3. **`requests.Session()` 复用会静默返回空** —— EN 侧查询整批 44 个 PO 时，用 `Session()` 返回 0 条，
   换裸 `requests.get`（与 `reconcile_ostkus.py` 一致）立刻 44/44。**不要图省事用 Session。**
4. **EN 拆单，同 OSTKUS 一样** —— 459 条 WM 单里 9 个 PO 有多条记录，典型形态是
   `WM-{po}` + `WM-{po}_1` + `WM-{po}_2` 同时存在（主单 + 拆单），另有 2 个 PO **只有 `_1`/`_2` 没有裸单**。
   直接按 `platform_order_id = po` 查会拿到裸单，拆单会被漏掉 —— 需要像 `mark_duplicate_masters()` 那样处理重复主单。
5. **`Tongtool Order Item` 不能直接查列表** —— `GET /api/resource/Tongtool Order Item` 返回 403 `PermissionError`。
   item 级数据只能从父单 `GET /api/resource/Tongtool Order/{name}` 的 `order_items` 里读（`fetch_en_docs()` 就是这么做的）。
6. **结算行按账期而非自然月，取数必须按账期** —— 见 §3.4；
   用 `periodStartDate`/`periodEndDate` 当 `transactionPosted` 区间去查，
   否则相邻账期的退货/费用行会混进来，聚合到 PO 必然错位。Walmart 是 14 天双周账期。
7. **费用口径已查清，不要再当谜题** —— 赛狐佣金 = (商品价 + 沃尔玛补贴) × 15%，
   EN `platform_fee` = 商品价 × 15%。差 = 补贴 × 15%，**EN 少算了基数**，见 §3.4。

## 5. 与 `platform-account-reconciliation` 的关系

现有模块的数据源是「财务手工 xlsx + EN 只读 REST」。赛狐这条路提供的是**另一种可能的数据源**：

```
赛狐 queryStatementDetail (账期+行级费用)
        ↓ purchaseOrder == platform_order_id  (100%)
        ↓ partnerItemId == Item.platform_sku  (商品级)
EN 生产 ERPNext Tongtool Order (platform_code=walmart_api)
```

好处是不再依赖财务手工导出，账期与费用行可自动拉取。
代价是要新增一条赛狐数据路径 —— 已落地为 `platform_account_reconciliation/scripts/reconcile_walmart.py`。

**注意**：现有模块设计文档 [2026-08-17-platform-account-reconciliation-design.md](../../platform_account_reconciliation/docs/specs/2026-08-17-platform-account-reconciliation-design.md)
计划扩展的是 **Wayfair WFUS** —— 但 Wayfair 在赛狐**没有任何财务结算端点**
（`多平台利润报表` 的 `platformTypes` 枚举为 `HALF_TEMU, ALL_TEMU, WALMART, TIKTOK, HALF_SHEIN, SELF_SHEIN, AGENT_SHEIN, SHOPIFY, ALIEXPRESS_POP_CHOICE, EBAY, MERCADO, SHOPEE`，**无 WAYFAIR**）。
也就是说：**Walmart 走得通，Wayfair 走不通** —— 与既有扩展计划的假设相反。

### 顺带发现：`reconcile_ostkus.py` 在 worktree 里跑不起来

`ENV_FILE` 原为 `ROOT / "EN_API" / ".env"`（写死仓库根），但**凭证只在主仓库、git worktree 里没有**。
已改为向上搜索 `EN_API/.env`（`_resolve_env_file()`），两个脚本都受益。

## 6. 备选/排除

- **任务式报告中心不可用于 Walmart 结算**：`/api/report/center/task/createTask.json` 当前只支持
  `PRODUCT_SALE_REPORT` 一种报告类型。不要再往这个方向试。
- **通用结算中心 V2 未验证**：`/api/financial/v2/settlementSummary/{detailPage,groupPage}.json`、
  `/api/financial/v2/accountReceivable/pageList.json`。文档示例的 `marketplaceId` 是 Amazon 的
  `ATVPDKIKX0DER`，语义偏 Amazon；本次 Walmart 专用端点已通，故未测。需要跨平台统一口径时可再探。

## 7. 复现

```bash
# 阶段 1：列 Walmart 店铺
uv run python SELLFOX_API/probe_walmart_settlement.py --list-shops

# 阶段 2：单店铺窄窗口拉结算明细
uv run python SELLFOX_API/probe_walmart_settlement.py \
    --shop-id 598030 --start 2026-08-01 --end 2026-09-21 --page-size 200

# 阶段 3：翻窗口列出所有账期（摸节奏，约 6 次调用翻完 9 个月）
uv run python SELLFOX_API/probe_walmart_settlement.py \
    --shop-id 598030 --start 2026-01-01 --end 2026-09-21 --discover-periods

# 阶段 4：按账期整期拉全量行
uv run python SELLFOX_API/probe_walmart_settlement.py \
    --shop-id 598030 --pull-period 2026-08-08:2026-09-05
```

取到账期行后做勾稽（跨账期合并，否则错位）：

```bash
uv run python platform_account_reconciliation/scripts/reconcile_walmart.py \
    --sellfox-json "<repo_root>/out/sellfox_walmart_probe/period_598030_*.json" \
    --out "<repo_root>/out/sellfox_walmart_probe/Walmart账期勾稽.xlsx"
```

输出 sheet：`账期总览` / `订单级勾稽` / `账期费用分类` / `账期明细`。
样本 JSON 与 xlsx 都落在 `<repo_root>/out/sellfox_walmart_probe/`（gitignored）。

## 8. 来源

- 本地文档镜像（Apifox）：`SELLFOX_API/docs/api-reference/多平台/财务/Walmart利润报表-查询结算明细.md`
  （Apifox run 入口 <https://app.apifox.com/web/project/1827046/apis/api-426460712-run>）
- `.../Walmart利润报表-查询店铺.md`（<https://app.apifox.com/web/project/1827046/apis/api-365907921-run>）
- `.../多平台/设置/多平台店铺列表.md`
- `SELLFOX_API/docs/api-reference/财务/结算中心V2/查询结算明细-分页查询.md`
  （<https://app.apifox.com/web/project/1827046/apis/api-399397941-run>）
- 代理约定：`SELLFOX_API/AGENT_HANDOFF.md`（Key 读根 `.env` 的 `SELLFOX_PROXY_API_KEY`）
- EN 侧复用：`platform_account_reconciliation/scripts/reconcile_ostkus.py`
- 实测脚本：`SELLFOX_API/probe_walmart_settlement.py`（取数）
- 勾稽脚本：`platform_account_reconciliation/scripts/reconcile_walmart.py`（比对）
