---
okf: v0.1
type: Reference
title: PB 楔形枕补货量估算 — 美中 Daneey 口径、剔除断货月、6 个月覆盖
date: 2026-10-16
category: workflow-issues
module: pb_orders
problem_type: workflow_issue
component: tooling
severity: high
applies_when:
  - "要给某几个 PB 物料算「下多少货」并交同事下单"
  - "要拿通途订单表统计某仓库/某渠道的销量"
  - "要判断某 SKU 现在到底有没有在途"
  - "断货期的销量被低估，需要还原真实需求"
tags: [pb, wedge-pillow, replenishment, tongtool, gsheet, stockout, daneey]
related_components: [pb_reconciliation, tongtu_automation, tongtool_api]
---

# PB 楔形枕补货量估算

## Context

PB 走 SPS dropship，补货靠内部在 ERPNext 下销售订单，下单 → 到货约 **3 个月**。
2026-10 出现「某个物料家族连续几个月没下过单、已经断货」的情况（床楔形枕头 8 款），
需要在**当天**算出建议下单量交同事 WX。此前没有成文的估算方法。

本文沉淀那次估算的**口径、数据源与陷阱**。交付物本身（Excel）是业务文件、不入库；
方法论入库。

## Guidance

### 1. 只算「美中 Daneey 仓」，且仓名有一套别名要一起收

我们只从那一个仓发给终端。**波兰（`FZHPoland-*`）与 FBA 是别的渠道，必须排除**。
美中 Daneey 在通途/EN 里的仓名经历过多次改名，过滤时要把整族都收进来：
`美中-FZH-DANEEY`、`美中-FZH-DANEEY-退货产品仓`、`FZH-DANEEY-成品仓`、
`FZH-DANEEY-半成品仓`，以及历史名 `FZH-DANEEY`、`FZH-DANEEY-皮壳仓库` 等。

### 2. 销量读「通途订单YYYYMM」Google Sheet —— 读法要照着来

- 每个月份一个 **Spreadsheet**，名 `通途订单YYYYMM`；数据在名为 **`2026年X月订单`** 的 tab。
- 关键列：`发货日期` / `通途SKU` / `产品名称` / `发货数量` / `渠道` / `发货仓库`。
- `渠道` 里 **`PotteryBarn` 就是 PB**；其余（`OSTK`/`亚马逊`/`Wayfair`/`Walmart`/`tiktok`…）算非 PB。
- ⚠️ **`通途订单202610` 不存在 / 未共享给服务账号** —— 当月数据只能退回用 PB 的 ASN CSV。
- ⚠️ 网络到 Google 偶发 SSL EOF，**读表要带重试**。
- ⚠️ 通途订单表里 **`通途SKU` 是统一的，没有别名**。同一 SKU 的 `平台SKU` 列会出现各店自有写法
  （如 `DDE-CYWedge-White100`），那只是平台侧别名，**不影响按 `通途SKU` 统计**。

### 3. ⚠️ 别信子代理的「否定结论」—— 自己读原表

本次子代理两次报「某 SKU 在整张表里查不到 / 从未发货」，据此我下了「有别名导致匹配不上」的
结论。**用户当场质疑（通途 SKU 进库后统一，哪来别名），我自己读原表后发现数据一行不少。**

→ 凡是「查不到 / 不存在 / 从来没有」这类**否定结论**，落到文档或交给别人之前，
**必须自己用原始数据复核一遍**（哪怕只是抽一个月的 tab 数一下命中行数）。
子代理的检索广度值得用，但它的**漏读会被表述成事实**。

### 4. 库存与在途：只用通途，两个字段都要看

| 数据 | 怎么看 | 注意 |
|---|---|---|
| 可用库存 | 通途 API `erp2_stocks_stocksquery`（按 `warehouseName`） | **不要用 EN 的 Bin** —— EN 不扣减通途库存（2026-10 确认），实测两套差 351 件 |
| 在途 | **通途采购单** `erp2_purchase_purchaseorderquery`（可按 `skus`） | 看 `PONum` / 状态 / `purchaseArrivalDate`；**SO 的「未交量」不是这个** |
| 备用 | 通途门户导《销售及库存报表》（多选美中仓 + 填 SKU） | 能一次给出 7/15/30/90 天销量 + 可用/待发/在途 |

**为什么不能拿通途可用库存判「断货」**：通途为标记发货要先「报溢」，可用 0 是常态。
**为什么不能拿 SO 未交量当在途**：那批货往往**已经出境**，在 EN 成品仓形成预留
（预留量与未交量一一对上），不是还在路上。

### 5. 剔除断货影响再算月需求率

断货月（以及到货后的**冲量月**）的出货**不能代表真实需求**。做法：

```
月需求率 = 该 SKU「干净月份」的出货合计 ÷ 干净月份数
下单量   = 月需求率 × 覆盖期 − 通途可用 − 在途 → 向上取整
覆盖期   = 生产/运输 3 个月 + 到下一批到货的余量（本次取 6 个月）
```

**断货窗口从哪来**（三源交叉，缺一不可）：

| 来源 | 拿到什么 |
|---|---|
| Notion「任务202408-」库的**任务页** | 断货事实 + 当时处理（改 IA / 已通知 / 到货日） |
| `us@mxdeals.com` 的**已发送邮件** | 精确日期链（`SKU:<买家SKU> out of stock`） |
| 逐批 `PB orders\<批次>\check0stock*.csv` 前后置**差分** | 逐月、逐 SKU 的缺货清单 |

> 注：楔形枕家族的断货**不在**「PB 无货未发」那个台账库里（那库只收另外几个 SKU）——
> 别只在库里翻。

### 6. 交付物形态

**给同事下单用 Excel，不要 md**；且 **第一张 sheet 就是结论**：
顶部一行总建议（合计 + 逐款），表头前几列 = `通途SKU / EN物料号 / 物料名称 / ★建议下单`，
后面才放推导列；行按建议下单量降序。每个 sheet 都带完整 SKU/物料号/物料名称，
别人不用回头翻对照表。EN SO 号、通途 PO 号都要带在表里供回查。

## Why This Matters

- **口径错一层，数字差一倍**：不加「美中 Daneey」限制、或把 FBA/波兰算进来，补货量直接失真。
- **拿 EN 库存或在途判货**会系统性高估在手量 → 该补的不补 → 继续断货（本次实测差 351 件）。
- **不剔断货月**会系统性**低估**需求（销量前二的两个 SKU 恰好是断货最久的）。
- **下单到到货 3 个月**，所以「今天不下单」= 三个月后继续断货；这类判断有时效性，
  要能当天出数。
- **否定结论传出去代价大**：同事按「这个 SKU 查不到」去做决定，会漏掉销量最大的一款。

## When to Apply

- 要给 PB 某物料家族算补货量、并交同事在 EN 下单时 → 全流程。
- 要按仓库/渠道统计通途销量时 → §1、§2。
- 要判断某 SKU 有没有在途时 → §4。
- 拿到子代理「查不到 / 从未发货」的结论时 → §3。

## Examples

**2026-10-16 床楔形枕头 8 款**（TT0031010K0062870–62881，EN `KS0121-KQC-{100,138,153,194}-{WHITE,GREY}`）

- 美中 Daneey 仓 2026-03~09 全渠道出货 **404**（PB 268 / 非 PB 136）。
- 断货窗口（三源确认）：**2880** 2026-03-12→05-08、**2878** 2026-06-11→07-20、**2876** 2026-05。
- 通途在途**只有 6 件**（`PO021724`，属 2876，未填到货日）。
- EN 近 5.5 个月（2026-04-28 起）**未下过任何补货单**；历史单笔 8–60 件、常见 16/20/40。
- 6 个月覆盖建议：**2880=110、2878=88、2881=33、2879=19、2876=7**，合计 **257**；
  2870/2871/2877 库存够 → 0。
- 交付：Excel 8 个 sheet（结论/SKU对照/逐月销量/PB与非PB/断货记录/剔除后月需求/库存与在途/EN SO/说明）。

## Related

- [.agents/skills/pb-orders/SKILL.md](../../../.agents/skills/pb-orders/SKILL.md) —— 触发词与可复跑清单
- [pb-stockout-post-shipment-closed-loop.md](pb-stockout-post-shipment-closed-loop.md) —— 断货发生后的四步闭环（清 invoice / 登记 / 通知 / SPS）
- [pb-out-of-stock-notification-and-zero-stock-orders.md](pb-out-of-stock-notification-and-zero-stock-orders.md) —— 断货判据与反直觉陷阱
- [tongtu-warehouse-rename-reconciliation.md](tongtu-warehouse-rename-reconciliation.md) —— 美中 Daneey 仓名变更的登记口径
