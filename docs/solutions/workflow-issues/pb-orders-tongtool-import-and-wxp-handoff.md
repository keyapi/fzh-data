---
okf: v0.1
type: Reference
title: PB 订单导入通途 + WXP 交接 — 模板/渠道/账号、核查顺序、钉钉消息
date: 2026-11-19
category: workflow-issues
module: pb_orders
problem_type: workflow_issue
component: tooling
severity: medium
applies_when:
  - "网页出件生成通途导入 xlsx 后，要导入通途「自定义渠道订单」"
  - "导入后要按销售渠道筛选本页并重新核查 SKU/仓库"
  - "要把标签/背贴与今日建单数量交接给 WXP（吴晓鹏）"
  - "需要核对导入是否重号、是否全部匹配通途 SKU/仓库"
tags: [pb, tongtool, import, wxp, dingtalk, fulfillment]
related_components: [pb_orders, tongtool_automation]
---

# PB 订单导入通途 + WXP 交接

## Context

PB 网页出件会生成通途导入 xlsx；随后要在通途「订单管理 → 自定义渠道订单」导入，
再让仓库按标签/背贴发货。2026-11-19 实际批次：xlsx 41 行 / 38 个 PO 基号，
导入后 41 单全部匹配 SKU 与美中-DANEEY 仓库，再交接 WXP。

## Guidance

### 1. 导入前先做重号预检

- 通途按**完整订单号**判重；有重复号会**整批拒绝**，不是只跳过一行。
- 从 xlsx 取 `PO Number` 列，先查 EN `Tongtool Order`（`order_id_code = PBUS-<号>`）
  或通途 API；本次 41 行全部不存在，才导入。
- 同一 PO 多明细在 xlsx 里可能重复 PO Number；通途会落成 `-1/-2` 子号（本次
  137828896、138350793、138367587），这是正常多行，不是重号。

### 2. 通途导入入口与选项

```
订单管理 → 自定义渠道订单
https://erp102.tongtool.com/order/privatequerysalemake.htm
→ 导入
→ 选择模板：PotteryBarnFromOrder
→ 选择渠道：PotteryBarn
→ 选择账号：账号PBUS
→ 订单多SKU导入方式：每行一个
→ 选择私有订单 Excel：本地 PB_0_导入_原始_*.xlsx
→ 开始导入
```

导入成功后弹窗关闭、列表刷新；有重号/格式错误时弹窗会留下来报错。

### 3. 导入后的核查顺序（顺序很重要）

1. **先选销售渠道 = PotteryBarn**（不是先勾选）；
2. 列表只剩本批（本次 `共41条/1页`）；
3. 勾选**本页全选**（不是「所有页全选」）；
4. 点 **重新核查**；
5. 逐行确认 `SKU`、`仓库`（本次全部 `美中-FZH-DANEEY`）、`邮寄方式` 非空。

先选渠道再勾选，是为了避免把页面上其他渠道的订单一起带进核查；重新核查会把
渠道 SKU 匹配到通途 SKU/仓库。

### 4. 钉钉交接 WXP：一条短消息，不要刷屏

用 DWS 单聊（`dws chat +dm --to 吴晓鹏 --content "..." -y`），只发一条：

```
PB 美中 41单，通途已建单
备注：今天包含之前断货刚到货的补发单
```

- 标签/背贴 PDF 需要时单独发文件（`dws chat +messages-send --as user --user-query 吴晓鹏 --msg-type file --file ...`）；
- 一次发太多条会被要求撤回重发；先发一条摘要，文件按需补；
- 用 `dws chat +messages-query-send-status` 确认 `sendStatus=SUCCESS`。

### 5. 日期/数量的来源必须写清楚

交接和 Notion 里报日期时，必须标来源，不能把不同系统的值混成一句：

| 值 | 来源 |
|---|---|
| `Ship No Later` / `Requested Delivery` | **PB/SPS Order 明细行** |
| `01/19/2027` 等「计划到货」 | **IA 模板/补货计划**（估算，不等于 EN 出货） |
| SO 交期 / PP / WO 状态 / DN / Shipment ETA | **EN**（SO、Production Plan、Work Order、Delivery Note、Shipment） |
| 通途在途/可用 | **通途库存/采购 API** |

实例：楔形白色153/194 在 EN 同属 `SO-26-00125` / `PP-26-00040`，WO 仍 Draft、
无 DN/Shipment；01/19/2027 只是 IA 计划值，不是 EN 出货 ETA。

## Why This Matters

- 通途重号是**整批失败**，预检能避免白导一次；
- 不先选销售渠道就全选/核查，会把别的渠道订单混进来；
- 钉钉一次发太多条会刷屏，需要撤回重发；
- 把 IA 计划值说成 EN 出货 ETA，会误导补货和 AKN 判断。

## When to Apply

- 网页出件完成、准备导入通途时 → §1 + §2；
- 导入后核查 → §3；
- 交接 WXP / 发钉钉 → §4；
- 向 PB/Notion 报日期或解释「计划到货」→ §5。

## Examples

**2026-11-19**

- xlsx 41 行 / 38 个 PO 基号；导入 41 单，无重号。
- 销售渠道 PotteryBarn → 本页全选 → 重新核查：41/41 有 SKU、仓库、邮寄方式。
- 钉钉给吴晓鹏只发一条：`PB 美中 41单，通途已建单` + 补发备注；`sendStatus=SUCCESS`。

## Related

- [pb-stockout-post-shipment-closed-loop.md](pb-stockout-post-shipment-closed-loop.md) —— 断货闭环（restock date 来源）
- [pb-partial-package-unshipped-invoice-paid.md](pb-partial-package-unshipped-invoice-paid.md) —— 部分包裹/旧标签
- [../../../.agents/skills/pb-orders/SKILL.md](../../../.agents/skills/pb-orders/SKILL.md) —— 触发词与铁律
- [../../../web_automation/AGENT_HANDOFF.md](../../../web_automation/AGENT_HANDOFF.md) —— 通途网页自动化基座
