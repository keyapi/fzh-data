---
okf: v0.1
type: Reference
title: PB 打单后才发现无货的闭环 — invoice 清理惯例、邮件成链、两套库存不能混用
date: 2026-10-16
last_updated: 2026-10-22
category: workflow-issues
module: pb_orders
problem_type: workflow_issue
component: tooling
severity: high
applies_when:
  - "美中仓回话说某 PO 实际无货，而这批已经出件/建了 ASN/invoice 也生成了"
  - "要在月底往钉钉提交 invoice 之前把无货件摘掉"
  - "要给 Diane 发断货通知邮件，想知道主题该不该新开一封"
  - "要报 restock date，但不确定该不该先查 EN 销售订单/生产/出货与钉钉头程"
  - "想拿 EN 的库存数或 SO 的未交量判断『还有多少货、在途多少』"
tags: [pb, stockout, invoice, diane, notion, erpnext, tongtool, closed-loop]
related_components: [pb_reconciliation, ups_track, tongtu_automation]
---

# PB 打单后才发现无货的闭环

## Context

PB 走 SPS dropship，正常流水线是「库存预检 → 出件（通途 xlsx + 标签/背贴）→ 建 ASN → 出 invoice」。
但**试探性发货**是常态：订单和标签照常发给美中仓，美中有货就发走，**没货才回头通知我们**。
所以存在一条绕过预检的路径 —— 出件都做完了，才发现某几单实际无货。

这条路径此前没有成文规范：invoice 怎么改、Notion 怎么记、邮件怎么发、SPS 后台点什么，
散落在历史批次的文件名和邮件里。2026-10-16 一次实际执行（PO 138093033 / 138099748）
把它整理成文，落到 `pb_orders/docs/reference/stockout-closed-loop.md` 与 skill `pb-orders`。

## Guidance

### 1. invoice 的「总额」写在**文件名**里

每批 `<批次>/invoice/` 下有一个 **0 字节 txt，文件名就是该批 invoice 总额**（如 `1596.54.txt`）。
摘掉无货单时：

```
新总额 已去除无货N单<PO…> 之前是旧总额.txt      ← 沿用这个句式，别自创
invoice x<新PO数> 已去除无货N单 <原时间戳>.csv
NotUsed/  ← 原始 csv + 原始总额 txt 原样搬进去
```

「新总额」= 旧总额 − 被摘单的 `Invoice Total`。`Invoice Total` 是第 **79** 列（1-based），
**只累加 `Record Type = H` 的行**。

### 2. 删 invoice 明细要**整块删**（H + 它的 D）

invoice CSV 里 **H 行才带 PO 号，D 行的 PO 列是空的**（与 `check0stock` 同构）。
只匹配 PO 号删 H 行 → 留下一堆孤儿明细行。要按「H 行决定这一块删不删」逐块处理。

回写保持 **UTF-8 无 BOM + LF**，且**只做行筛选、不重新序列化**（与 checked CSV 同一套理由：
SPS 导出的列数参差，过一遍 pandas 就变形）。

### 3. 通知 Diane 的邮件是**一条链**，不是一封封新开

主题首封 `SKU:<PB买家SKU> out of stock Vendor 5806`，之后**每次都回复上一封**，
主题滚成 `Re:RE: {EXT} SKU:<旧> out of stock  SKU:<新> out of stock Vendor 5806`。
取消类另起一条链：`Re:WSI WISMO/Cancel Request/CHAD - 5806 Centrade Inc <日期>`。

从 `us@mxdeals.com`（显示名 Service U.S.）发出，收件人是 PB 采购对接人 Diane
（**邮箱地址见历史邮件 / Notion 台账，不写进仓库**）。
模板见 reference 文档 §2 第 3 步。**可以直接用 SMTP 发**：Tencent Exmail `smtp.exmail.qq.com:465`（SSL），
账号 `us@mxdeals.com`（凭据见父仓库未跟踪处）。
**⚠️ Tencent Exmail 不会把 SMTP 发出的信自动存进「已发送」** —— 发完必须再 IMAP `APPEND` 一份到
`Sent Messages`，否则自己邮箱里查不到这条线。（`pb@icentrade.com` 是**只收不发**的 AP 汇款信箱，与发信无关。）

### 4. EN 的库存数**不能当可用库存**用

EN 侧**没有对接通途库存、不做扣减**（2026-10-16 用户确认），所以：
- EN 的 Bin（如 `美中USTX到货仓`）是账面数，**不代表实际可发**；
- 判可用要看**通途**（`erp2_stocks_stocksquery`，含 `intransitStockQuantity`）。
- 实测两者差 351 件、方向还不一致（白153：通途 4 vs EN 94）。

将来考虑用**定时通途 API 同步**（赛狐侧已有每周同步通途库存的任务）。

### 5. SO 的「未交量」≠ 在途

`SO-26-00034`（194 白，60 件只交 1）看起来有 59 在途，但 **通途在途为 0**。
原因是这批货**已经出境**，在 EN 成品仓形成**预留**（预留量与未交量一一对上）——
即「SO 未交」表达的是「目的地还有多少没被消化」，不是「还在路上」。

**判在途的可靠来源 = 通途采购单**：`erp2_purchase_purchaseorderquery`（可按 `skus` 查），
看 `PONum` / 状态 / `purchaseArrivalDate`。实测该家族 55 张 PO 里只有 1 张未到货
（`PO021724`，6 件，且**通途没填到货日**）。

### 6. 别用通途库存判「断货」

通途为标记发货要先「报溢」，所以**可用库存恒 0 是常态**。断货判据是
PB 的 0 库存导出 + 美中仓人工回话；「真发」只认 UPS 取件。详见
[pb-out-of-stock-notification-and-zero-stock-orders.md](pb-out-of-stock-notification-and-zero-stock-orders.md)。

### 7. restock date 必须先查上游（EN SO/生产/DN + 钉钉头程）

**2026-10-22 补。** 断货不等于「没库存 → 拍一个 +3 个月」。给 Diane / Notion 的日期
必须从下面六处推出来，否则会把「其实有在途」「其实工厂已经做了」的货重复下单或报错日期：

| 要回答 | 查哪里 | 陷阱 |
|---|---|---|
| 有没有已下单未交 | EN **Sales Order** | SO 未交量 ≠ 在途（§5） |
| 生产做到哪 | EN **Production Plan / Work Order / Job Card** | 工单头部状态会滞后，看最后一道真实扫码 |
| 工厂出了没有 | EN **Delivery Note** | 部分出库按行看 |
| 在海上吗 / 何时到 | 钉钉 `2026年下单表`（`2026年度订单明细` + `物流信息表`→ZMT 号）+ `发货信息总表`（`物流跟踪Tracking`） | **用 EN 销售订单编号匹配，不是 `po_no`**；批次号只在首行有值，要向下填充 |
| 有没有采购在途 | 通途**采购单**（§5） | 通途可用库存恒 0 是常态（§6） |
| 海外仓还有没有 | 通途对应仓可用 | EN Bin 不能当可用库存（§4） |

**判定**：有在途且 ETA 早于客户最晚发货日 → 以在途 ETA 为准，不重复下单；
没有在途 → 用「补货下单日 + 采购/生产提前期」推，并**明确标注 TBC**。
所有日期按 `事实 / 推导 / 估算 / 人工判断` 标注来源，别把估算写成事实
（参见 `docs/solutions/architecture-patterns/en-end-to-end-supply-chain-fulfillment-visibility.md`）。

## Why This Matters

- **invoice 提交到钉钉后无法撤销**。月底固化之后再发现无货、或顾客取消，就会挂着一笔收不回的账。
  所以「打单后才发现无货」必须**当天**清 invoice —— 这是这条流程存在的唯一理由。
- **删错 invoice 明细**（只删 H 不删 D）会让整批发票总额对不上，且要到对账时才暴露。
- **拿 EN 的 Bin 当库存**会系统性高估在手量 → 该补的货不补 → 继续断货（本次实测差 351 件）。
- **拿 SO 未交量当在途**会重复订货；反过来以为没在途又会漏补。
- **不查 EN 上游与钉钉头程就拍 restock date**：会把「其实已在生产/已在海上」的货报成「还要等 3 个月」，
  导致 PB 侧重新排期、内部重复下单，或者反过来漏掉真正能赶上客户最晚发货日的在途批次。
- **邮件新开一封**（而不是回复上一封）会打断 Diane 侧的线索，历史邮件明确是串成链的。

## When to Apply

- 美中仓回话某 PO 无货，而这批已经出件 / 已建 ASN / invoice 已生成时 → 四步全走。
- 月底要对 invoice 做「去除无货」处理时 → 只看 §1、§2。
- 任何「我们还有多少货 / 有多少在路上」的判断 → 先读 §4、§5，别信 EN Bin 与 SO 未交量。
- 要给 Diane 发断货通知时 → §3 的主题句式与回复链。

## Examples

**2026-10-16 实测（PO 138093033 / 138099748）**

- 两单都在 `20261015` 批里**已打单**（ASN 12618 / 12617，Ship Date 10/16）、**已有 invoice**
  （`INV…12348` $37.99、`INV…12365` $32.50，挂在 `invoice x22 …csv`，批总额 1596.54）。
- 清 invoice → 摘掉两单的 H+D（22 → 20 单），新总额 **1526.05**，
  文件落成 `1526.05 已去除无货2单138093033 138099748 之前是1596.54.txt`，
  原件搬进 `NotUsed/`；回读校验 40 条记录、H/D 各 20、总额对得上。
- 登记 Notion：`SKU` 列新增 `白色194` / `黄色60` 两个选项，两行分别写入
  `打单=已打单`、`invoice=已去除`、`通途建单=✓`、备注含 ASN / 追踪号 / 原始发票号。

## Related

- [pb_orders/docs/reference/stockout-closed-loop.md](../../../pb_orders/docs/reference/stockout-closed-loop.md) —— 可执行版四步（本文是学习记录）
- [pb_orders/docs/reference/notion-stockout.md](../../../pb_orders/docs/reference/notion-stockout.md) —— Notion 台账列契约与半自动推送
- [.agents/skills/pb-orders/SKILL.md](../../../.agents/skills/pb-orders/SKILL.md) —— 触发词与可复跑清单
- [pb-out-of-stock-notification-and-zero-stock-orders.md](pb-out-of-stock-notification-and-zero-stock-orders.md) —— 断货判据 / PO↔EN 映射 / UPS 复核
- [pb-reconciliation-monthly-update.md](pb-reconciliation-monthly-update.md) —— PB 月度对账（同一数据目录）
