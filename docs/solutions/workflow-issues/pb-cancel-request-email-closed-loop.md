---
okf: v0.1
type: Reference
title: PB 顾客取消（CANCEL）邮件闭环 —— 定位、核实、回复与 Notion 登记
date: 2026-10-26
category: workflow-issues
module: pb_orders
problem_type: workflow_issue
component: tooling
severity: medium
applies_when:
  - "PB 采购对接人发来 WSI WISMO/Cancel Request/CHAD 邮件，要求填 Vendor Comment"
  - "要判断某个 PB PO 的 CANCEL 能不能接受"
  - "收件箱按主题搜不到邮件，需要按日期范围逐封扫"
  - "同一天的汇总邮件重复列出前几天的 CANCEL 请求，不知道要不要回"
  - "接受取消后要把过程写回 Notion「PB 无货未发」台账"
tags: [pb, pottery-barn, cancel, imap, smtp, notion, closed-loop, vendor-comment]
related_components: [pb_reconciliation, tongtool_order, en_api]
---

# PB 顾客取消（CANCEL）邮件闭环

## Context

Pottery Barn 走 SPS Commerce 下单。顾客取消时，PB 采购对接人会发来主题形如
`WSI WISMO/Cancel Request/CHAD - 5806 Centrade Inc <YYYY-MM-DD>` 的邮件，正文是一张
HTML 表格，每行一个请求，最后一列 **Vendor Comment** 空着等供应商填。邮件要求 **24 小时内**回复。

Request Type 有四类：

| 类型 | 含义 | 回什么 |
|---|---|---|
| `CANCEL` | 顾客要取消 | `Cancel accepted`；已发货则 `Cancel not accepted - already shipped` + 追踪号 |
| `WISMO` | 问货到哪了 | 已发给追踪号；未发给预计发货日 + 原因 |
| `CHAD` | 改地址 | 确认能否改 / 已改 |
| `FORCE BILL` / `Partial RP` | 已收货未开票 / 部分补发 | 给追踪号或处理结论 |

2026-10-22 / 10-23 各有一封单行 CANCEL；10-26 又发来一封**汇总提醒**，把前两封的 PO 合并重复列出。
本次三封都不涉及刚到货的两个 SKU，核实后全部接受并回复。

### 与既有记录的关系

此前**不是完全没有记录**，但都不足以直接照做：

- 未合并分支上的 stockout 文档只有一行旁注：`取消类另起一条链：Re:WSI WISMO/Cancel Request/CHAD - 5806 Centrade Inc <日期>`，
  另给过一个例子 `PO 137892570 Cancel accepted`；Notion 状态映射也只有 `顾客=取消 + 状态=顾客取消` 一行。
- **实际处理早就有**：Sent 里能看到 2026-09-23「CANCEL impossible, already on the way」、
  10-12「PO 138039519 CANCEL not accepted」、10-15「PO 137892570 Cancel accepted」、
  10-19「PO 137987968 Cancel accepted」。

缺的是**可执行的全流程**：怎么在多个文件夹里找全邮件、按哪四项核实「从未发货」、汇总提醒怎么处理、
HTML 表格最后一列怎么填、SMTP 后怎么归档、Notion 备注怎么写。这篇把这些补齐。
旧 stockout 分支合并后，两篇互相链接即可，不需要重复正文。

## Guidance

### 1. 先把邮件找全 —— 按日期范围扫，不要只按主题过滤

| 项 | 做法 |
|---|---|
| 账号 | `us@mxdeals.com`（Tencent Exmail，`imap.exmail.qq.com:993` SSL） |
| 凭证 | 内部 Notion 页面 / 父仓库未跟踪处；**绝不写进仓库** |
| 文件夹 | `INBOX` / `Junk` / `Sent Messages` / `Drafts` / `Deleted Messages`，以及一个非 select 的中文文件夹 |
| 检索 | 先 `SEARCH SINCE <date> BEFORE <date>` 取日期范围内全部邮件，再在本地按主题过滤；**不要只靠 `SEARCH SUBJECT`** |
| 正文 | 同时取 `text/plain` 与 `text/html`；HTML 表格才是回复时要保留的原件 |

> 实测：两封 CANCEL 就在 `INBOX`，但只看「最近几封」或只按主题搜会漏掉。日期范围
> `18-Oct-2026 .. 27-Oct-2026` 一次列出 50 封，主题过滤后稳定命中。

### 2. 读表，把 Buyer SKU 映射成我方 SKU

每行至少抽出：

```text
Order Number | Buyer SKU | SKU Description | Reason | Request Type | PO Number | Vendor Comment(空)
```

Buyer SKU → 我方 SKU 的可靠来源是 Notion 台账的 `对方SKU` / `通途SKU` 两列，或
`pb_orders/data/notion_sku_map.json`（Vendor Style 大写规范化后查）。本次两条：

| Buyer SKU | 我方 SKU | 通途 SKU |
|---|---|---|
| `1890744` | 黄色138 | `CENKZ1325-Yellow-138` |
| `2017724` | 白色153 | `TT0031010K0062878` |

### 3. 核实「能不能接受」—— 只认「有没有真的发出去」

按下面四条查，**任意一条显示已发/已开票就不要接受**：

| 检查 | 怎么查 | 接受取消的判据 |
|---|---|---|
| 打单 / ASN | PB 批次目录的 `shipment*.csv` 里有没有该 PO | 没有 |
| invoice | `invoice*.csv` 里有没有该 PO 的 H 行 | 没有 |
| 通途建单 | `erp2_orders_ordersquery`，`accountCode=PBUS`、`orderId=PBUS-<PO>`；`datas.array=null` = 未建单 | 未建单 |
| Notion 台账 | `打单` / `状态` / `invoice` / `通途建单` | 未打单、invoice=不适用、未建单 |

`check0stock*.csv` 里出现该 PO 只能说明**当时缺货**，不能说明没发货；必须和上面三项交叉。
反过来，`shipment*.csv` 有记录也只能说明**建了 ASN**，不等于 UPS 真的取件（口径见
[pb-out-of-stock-notification-and-zero-stock-orders.md](pb-out-of-stock-notification-and-zero-stock-orders.md) §6.1）。

### 4. 回复：挂在原线程，保留她的表格

| 项 | 做法 |
|---|---|
| 线程 | `In-Reply-To` / `References` 都填原邮件 `Message-ID`；**不要新开一封** |
| 主题 | `PO <PO> Cancel accepted Re:<原主题>`；多个 PO 用 `PO <A> & <B> Cancel accepted Re:...` |
| 正文 | `Hi <对接人>` → `PO <PO> Cancel accepted` → `Best / Key` → 引用原文 |
| 表格 | 保留原 HTML；把数据行最后一个空 `<td></td>` 填成 `Cancel accepted` |
| 发件 | `Service U.S. <us@mxdeals.com>`；SMTP `smtp.exmail.qq.com:465` SSL |
| 归档 | **Tencent Exmail 不会自动保存 SMTP 发出的信** → 发完 `IMAP APPEND` 原始 MIME 到 `Sent Messages`，再回读确认 |
| 禁止 | 邮件里不出现中间人 / 佣金 / 本地文件名 |

### 5. 汇总邮件也要回

采购对接人可能在几天后发一封新的 `... <新日期>` 邮件，把尚未闭环的请求**合并重复列出**。
如果只回了最初两封，她的跟踪表仍会把这些 PO 当成未答复。

**判据**：新邮件里的 PO 集合 ⊆ 已处理集合，且行内容一致 → 在原线程回完后，再对汇总邮件回一封，
把**所有行**的 Vendor Comment 一次填完；主题用 `PO <A> & <B> Cancel accepted Re:<汇总主题>`。
这是一次判断，不是固定规则 —— 如果汇总邮件里混入了新 PO，按新请求逐条核实。

### 6. 写回 Notion

单个 PO → 追加到该行「备注」，同时改结构化列：

```text
【YYYY-MM-DD 操作记录】
① 哪天收到哪封请求（Order / Buyer SKU / PO / CANCEL / 原因）；是否被汇总邮件重复列出
② 核实结果：打单 / 通途 / shipment / invoice 各是什么，结论「从未发货」
③ 回复记录：发送日期、主题、Vendor Comment 填了什么
④ 状态与顾客列改成了什么
```

| 列 | 改成 |
|---|---|
| `状态` | `顾客取消` |
| `顾客` | `取消` |
| `通知Diane` | 实际回复日期 |
| `备注` | **追加**，不要覆盖旧记录 |

跨 PO / 台账里没有对应行 → 按既有惯例在 `任务202408-` 库建任务页（事件表 / 操作清单 / 其他操作 / 待办）。
Notion 写入走 `notion-personal` MCP；CLI 会话里没有该工具时，见
[notion-mcp-direct-access.md](../developer-experience/notion-mcp-direct-access.md)。

## Why This Matters

- **已发货却接受取消** → 货已出门、invoice 已开，后续要么退回要么坏账。
- **没发货却拒绝取消** → 一张永远不会发的订单继续占着台账和 invoice，月底对账时才暴露。
- **只回最初两封、漏掉汇总提醒** → 对方系统里请求仍是 Open，会继续每天重发，双方都以为对方没处理。
- **新开主题而不是回复原线程** → 丢失原始 Message-ID 链，后续追查「这封是回哪条请求」只能靠人翻。
- **SMTP 发完不 APPEND** → 自己邮箱 `Sent` 里查不到，下一次 Agent 会误判「没回过」再发一遍。
- **台账不记过程** → 换一个 Agent 只看到「顾客取消」，不知道是凭什么判断能取消的。

## When to Apply

- 收到任何 `WSI WISMO/Cancel Request/CHAD` 邮件，尤其是 `Request Type=CANCEL`。
- 要判断某个 PB PO「到底发没发」时 —— 先按 §3 四项交叉，不要只看单一来源。
- 同一批请求被新日期的汇总邮件重复列出时。
- 处理完后要把过程沉淀到 Notion 台账时。

## Examples

**2026-10-26 实测（两封原始 + 一封汇总）**

| 邮件 | PO | Buyer SKU / 我方 SKU | 核实 | 回复 |
|---|---|---|---|---|
| 2026-10-22 | `137999043` | `1890744` / 黄色138 | 未打单、无 ASN、无 invoice、通途无 `PBUS-137999043`，仅见于 20261001 `check0stock` | `PO 137999043 Cancel accepted Re:...2026-10-22` |
| 2026-10-23 | `138136920` | `2017724` / 白色153 | 同上；仅见于 20261022 `check0stock`（全部缺货） | `PO 138136920 Cancel accepted Re:...2026-10-23` |
| 2026-10-26 | 两个 PO | — | 汇总重复前两行 | `PO 137999043 & 138136920 Cancel accepted Re:...2026-10-26` |

三封均保留原 HTML 表格、Vendor Comment 填 `Cancel accepted`、SMTP 后 APPEND 到 `Sent Messages`；
Notion 两行分别追加操作记录并改为 `顾客取消` / `取消` / `通知Diane=2026-10-26`。

## Related

- [pb-out-of-stock-notification-and-zero-stock-orders.md](pb-out-of-stock-notification-and-zero-stock-orders.md) —— 断货判据、PO↔通途映射、「真发」只认 UPS 取件
- [../developer-experience/notion-mcp-direct-access.md](../developer-experience/notion-mcp-direct-access.md) —— CLI 会话里没有 `notion-personal` 工具时怎么直接写 Notion
- `pb_orders/AGENT_HANDOFF.md` —— PB 订单履约模块交接（文件位置、批次目录、库存预检）
- `pb_orders/docs/reference/workflow.md` —— 批次文件命名、PO/SKU 列映射
