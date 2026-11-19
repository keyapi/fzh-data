---
okf: v0.1
type: Reference
title: PB 部分包裹未发 — 看 Pack Level 跟踪号、已付发票不重开、旧 UPS 标签 90 天
date: 2026-11-19
category: workflow-issues
module: pb_orders
problem_type: workflow_issue
component: tooling
severity: high
applies_when:
  - "一个 ASN/PO 有多个包裹，只知道主跟踪号，不确定到底发了几个"
  - "部分包裹已投递、另一部分只建标未揽收，要判断还欠几件"
  - "invoice 已按多件开票并被 PB 付款，补发缺件时犹豫要不要再开票"
  - "几个月前的 UPS 标签还能不能用；要从 Packslip PDF 里把旧标签找出来"
tags: [pb, shipment, ups, invoice, label, partial-shipment, pack-level-tracking]
related_components: [pb_orders, ups_track]
---

# PB 部分包裹未发：三个容易混的口径

## Context

PB dropship 的一个 PO 可能拆成多个包裹；SPS 的 ASN 也可能把多件放在同一个 ASN 下。
2026-08-27 的 ASN 12262（PO 137770200，2 件）就是典型：第一件 8/28 揽收、9/1 签收；
第二件只建了 UPS 标签、从未揽收。当时 invoice 按 2 件开了 $103.40，PB 在 9/25 按整张
发票付了款。到 11/19 才回头补发缺的那一件，同时要处理旧标签与「不能重复开票」。

## Guidance

### 1. shipment CSV 的包裹数看 `Pack Level Carrier Tracking ID`

`shipment x*.csv` 里有两列跟踪号，**不要看错**：

| 列 | 含义 |
|---|---|
| `Carrier Tracking` | 主跟踪号，一单多件时也可能只有一个 |
| `Pack Level Carrier Tracking ID` | **逐包裹的完整列表**（空格分隔） |

实例（ASN 12262）：

```
Carrier Tracking            = 1ZC0019E0314807245
Pack Level Carrier Tracking = 1ZC0019E0314807245 1ZC0019E0315985060
```

只看 `Carrier Tracking` 会误判「只发了一个包裹」；`Pack Level` 才证明 ASN 里是 2 件。
（同一口径已写进 `pb-orders` skill 与 `AGENT_HANDOFF.md` 坑 47。）

### 2. 每个包裹真发没发，只认 UPS 取件

`Pack Level` 只说明「建了几个标」，不说明「UPS 收没收」。对每个跟踪号查 UPS：

- 有 `Arrived at Facility` / `Out For Delivery` / `DELIVERED` → 真发；
- 一直停在 `Shipper created a label, UPS has not received the package yet` → **未发**。

本例：`1ZC0019E0314807245` 9/1 已签收；`1ZC0019E0315985060` 无任何揽收节点。

### 3. invoice 按整张票付款，补发缺件不得再开票

PB 的 ACH 是按**发票**付款，不是按包裹：

- invoice H 行总额 `$103.40`；
- D 行 `Qty 2 × $51.70 = $103.40`；
- PB 2026-09-25 付 `$103.40`（Payment Ref 1117563）。

所以「2 件只收到 1 件」时，**钱已经收了 2 件**，欠的是 1 件货，不是 1 笔应收。
补发时：

- 不要新建 invoice；
- 不要把该 PO 再从账上开一次；
- 若必须新建 ASN、而 SPS 的自动 ASN→Invoice 规则会生成发票，**先拦截/取消该发票**，
  或改为在原 ASN 下补打标签，避免重复收款。

### 4. 美国 UPS 标签按 90 天窗口用，旧标签先查 UPS 状态

- 美国 UPS 面单通常按 **90 天**有效期；UPS 官方口径是 90 天内可作废、180 天后不再处理作废；
- 本例标签 2026-08-27 创建，11-19 已 84 天，UPS 仍显示 `Label created`、未 Voided
  → 还在有效期内，但只剩约 6 天（约 11-25 到期），应优先直接用旧标签补发；
- 若标签已过期/被 Voided，才重新出标；重新出 ASN 时同时处理「不重复开票」。

### 5. 从 Packslip PDF 里提取旧标签

旧批次的 `Packslip 美中 xNN YYYYMMDD.pdf` 每页通常是 **Packing Slip + UPS 标签**。
找标签页的方法：

1. 用 PyMuPDF 按 PO 搜文本，定位该 PO 的 Packing Slip 页；
2. 渲染页面确认 UPS 标签上的跟踪号（标签上的 1Z 号可能是图片，不一定能文本抽取）；
3. 用 `fitz.open()` + `insert_pdf(from_page=..., to_page=...)` 把该页原样抽成单页 PDF；
4. 在目标批次目录写一份说明 txt：来源文件/页码、ASN、两个跟踪号、发票已付事实、标签有效期。

**命名**：Packslip 文件名 `xN` 的 N 是**真实标签页数（包裹数）**，不是 shipment 数。
实例：37 个 shipment 的 Packing Slip PDF 是 40 页 → `x40`；把 137770200 的旧标签 1 页
合并到第一页后是 41 页 → `x41`。不要按 shipment 数量命名。

本例：`Packslip 美中 x25 20260827.pdf` 第 9 页 = 已发件 `…14807245`，第 10 页 = 未发件
`…15985060`；第 10 页已抽到 20261119 批次目录。

### 6. 补发数据只加缺的件数，并走 reorder 后缀

- 原订单 `Qty 2`，已发 1 件 → 补发 CSV 的 D 行 `Qty Ordered = 1`，H 行总额改为 `$51.70`；
- 用 `--reorder PO=-3` 生成 `PO-3`，不要手改 CSV 的 PO 号后再叠加后缀；
- 若同批还有「旧的已标发未发」单，先查 UPS 确认没发，再按正常缺货补发。

## Why This Matters

- **看错 `Carrier Tracking`** 会把 2 个包裹当成 1 个，误判「已发完」，缺件永远补不出去。
- **已付款的发票再开一次** = 重复收款，月底对账/客户投诉都很难解释；PB 是按发票付款，
  不会因为「只到 1 件」自动退一半。
- **旧标签过期后再用** 会被 UPS/仓库拒收，重新出标又可能触发自动 invoice，形成二次问题。
- **不提取旧标签** 就只能重新建 ASN，进一步增加重复开票风险。

## When to Apply

- 一个 ASN/PO 有多个包裹，需要确认实际发了几个 → §1 + §2。
- 部分包裹签收、部分只建标 → §2 + §3。
- PB 已按整张 invoice 付款，准备补发缺件 → §3。
- 需要复用几个月前的 UPS 标签 → §4 + §5。
- 补发数量/后缀/CSV 构造 → §6。

## Examples

**2026-08-27 → 2026-11-19（PO 137770200 / ASN 12262）**

- ASN 12262，Lading Qty 2；`Pack Level = 1ZC…14807245 1ZC…15985060`。
- 第 1 件 8/28 揽收、9/1 签收；第 2 件只建标未揽收。
- invoice `INV0580626000011991`：H $103.40，D Qty 2 × $51.70；PB 9/25 ACH 付 $103.40。
- 旧标签 8/27 创建，11/19 仍有效（约 11/25 到期）；从 8/27 Packslip PDF 第 10 页抽出。
- 补发 CSV 只加缺失的 1 件（H $51.70 / D Qty 1），用 `--reorder 137770200=-3` 生成 `137770200-3`。

## Related

- [pb-stockout-post-shipment-closed-loop.md](pb-stockout-post-shipment-closed-loop.md) —— 打单后才发现无货的五步闭环
- [pb-out-of-stock-notification-and-zero-stock-orders.md](pb-out-of-stock-notification-and-zero-stock-orders.md) —— 断货判据 / PO→Tongtool Order 映射 / UPS 才算真发
- [../../../pb_orders/docs/reference/stockout-closed-loop.md](../../../pb_orders/docs/reference/stockout-closed-loop.md) —— 可执行版
- [../../../.agents/skills/pb-orders/SKILL.md](../../../.agents/skills/pb-orders/SKILL.md) —— 触发词与铁律
