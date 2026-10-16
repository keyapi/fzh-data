---
okf: v0.1
type: Reference
title: SPS 门户的 IA 与 AKN 操作 — 断货后重发 Inventory Advice / PO Acknowledgement
date: 2026-10-16
category: workflow-issues
module: pb_orders
problem_type: workflow_issue
component: tooling
severity: high
applies_when:
  - "PB 断货后要在 SPS 上给某个 PO 重发 PO Acknowledgement（EDI 855 / AKN），填新的 expected ship date"
  - "要把断货 SKU 的库存 / 在途 / 到货日同步进每天自动发的 IA"
  - "发现已经发出去的 IA 报的库存是错的，要补一批纠正"
tags: [pb, sps, inventory-advice, acknowledgement, edi, stockout, sps-portal]
related_components: [pb_orders, ups_track]
---

# SPS 门户的 IA 与 AKN 操作

## Context

PB 断货后有两条必须在 **SPS 门户**上做的动作，此前**全无步骤记录**（`sps_automation.py` 只会每天自动发 IA，
不做 AKN）。2026-10-16 实际操作两单（`138093033` 楔形枕白194、`138099748` 三角靠枕黄60）把两条都跑通了。

两条动作对应的 EDI：

| 简称 | EDI | 作用 |
|---|---|---|
| **IA** | 846 Inventory Advice | 告诉 PB「我们各 SKU 有多少可发」 |
| **AKN** | 855 PO Acknowledgement | 对某个 PO 回复「确认 + 新的预计发货日」 |

门户入口：`https://commerce.spscommerce.com/fulfillment/transactions/list/`，partner = `WILLIAMS SONOMA INC`，
登录账号 `us@mxdeals.com`。

## Guidance

### 1. 重发 AKN（PO Acknowledgement，填新 expected ship date）

```
交易列表搜 PO 号 → 打开该 PO（Order 单据）
→ Workflow 面板「Order Status → Acknowledgement」旁的 New
→ 弹窗 Step 3/4：Type = PO Acknowledgement，Document Creation = Auto Fill - Recommended
→ Create New → 进 Data Entry
→ 卡片右侧「Expand for full view」
→ 改两个字段：
     Current Schedule Ship Date     = 下一批发货日
     Current Schedule Delivery Date = Ship + 7 天
→ Save（**只存草稿**）
→ 点 Send Document → 确认 Continue
```

**⚠️ 最大的坑：一次 Send 不会真的发出去。** 实测两次都是同一个模式：

```
点 Send Document → Continue
   → 当前单据变成 "Overwritten Draft"（Send 按钮消失）
   → 同时冒出一条**新的 Saved 草稿**（日期已带过去）
   → 打开那条新草稿 → 再 Send Document → Continue
   → 状态变 In Transit   ← 这才是真发出
```

**判据**：单据状态从 `Saved` → **`In Transit`** 才算发出（`Accepted` 是 PB 侧回执后的状态）。

### 2. IA 每天自动发，模板就是「内容」

每天的定时任务从模板 **`IA Template 20250605 x100`** 建一份 IA 发出去。
**改模板 = 改以后每一天发的 IA**，比一次性的补发更根本。

```
交易列表搜 "IA Template"，打开状态为 Template 的那条
→ Create New → Expand for full view → Detail 标签（表格虚拟化，要滚动才渲染）
→ 逐行改：Stock Quantity / On Order Quantity / On Order date
→ 【不要点 Save】← 那是保存单据
→ 右上 ⋮（More Actions）→ Manage Templates
→ ● Overwrite an Existing Template → 下拉选 IA Template 20250605 x100 → Save
→ 绿条 "Template of this document has been overwritten."
```

**⚠️ 覆盖模板不是原地改，而是生成一个新的模板文档**顶替旧的（旧的那份变成 `UNDEFINED / Saved` 草稿）。
所以「打开原文档看内容」会看到**旧值** —— 要**从列表点开状态为 `Template` 的那份**才准。

### 3. ⚠️ IA 的关键特性：**单日、且日期 = 发送日 + 7**

实测今天发出的那份：

```
Inventory Advice #:        IA7_20261016_124353      ← 编号里的 20261016 = 发送日
Inventory Advice Date/Time: 10/23/2026              ← = 发送日 + 7
Report Start Date / End Date: 空
```

→ **IA 只覆盖「一个日期」，而且那个日期是发送日往后 7 天。**

**推论（重要）**：**PB 对某一天 X 的库存认知 = 第 X−7 天发出的那份 IA 决定的。**
所以**改了模板或补了库存，只能影响 7 天后的那一天**；**已经发出的那 7 天（今天 ~ 今天+6）仍然带着旧值。**

### 4. 补发 IA 纠正错误窗口 —— SPS 支持一次发多条

改完模板后，把「已经报错的窗口」按天补一遍：

```
交易列表 → 右上 Create New
→ 1 Select Trading Partner: WILLIAMS SONOMA INC
→ 2 Select Document type: 「I don't have a source document.」→ Inventory Advice
→ 3 Select an existing template → IA Template 20250605 x100
     并填 【Number of Documents】(最多 100)   ← 关键：一次建 N 份
→ Create New → 进 Data Entry（N 份草稿）
→ 逐份改 Inventory Advice #（编号）与 Inventory Advice Date（日期）
→ 勾选 N 份 → **底部悬浮工具条的 ✈**（不是卡片上那个）→ 确认 "send all N documents"
```

**几个坑**：

- 批量建的 N 份**日期全都继承模板里的旧日期**（本次是模板里存的 `07/09/2024`），**必须逐份改**。
- 编号：手工补发时不必沿用脚本的 `IA7_{发送日}_{时分秒}` —— 直接用 **advice date**（如 `20261016`）更好认。
- 日期字段是 date-picker，`fill()` 能直接写；也可点开日历选（`>` 翻月）。
- 编辑后**表格会滚回顶部**，要重新滚到底才能看到目标行。
- 发送按钮在**底部悬浮工具条的 ✈**，前提是**先把卡片勾选**（勾选后底部才会出现 `N Items Selected`）。

### 5. 每次改动后要核对

- AKN：状态 `In Transit`
- IA：模板列表里那份 `Template` 的**内容**（用它的 Content 视图逐行核）—— 注意别读成旧文档
- 都可在交易列表按 PO 号 / 编号搜出来回查

## 6. 给 Agent 的可执行细节（Playwright MCP）

**这套流程 Agent 可以自己点**（本次就是这么做的）。以下是复现所必需的选择器与坑，省得下次重新摸。

### 6.1 页面结构：两层 iframe，且**跨域**

```
page
└─ iframe[data-testid="app-frame"]        ← SPS 应用壳
   └─ iframe(再一层)                       ← 单据内容渲染在这里（blob:…sps-cdn.com）
```

**⚠️ 跨域**：`page.evaluate` 进不去内层（`contentDocument` 为 `null`）。**只能用 Playwright 的
`page.frameLocator('[data-testid="app-frame"]')`** 定位；要读单据内容时遍历 `page.frames()` 找含目标文本的那个 frame。

### 6.2 常用选择器

| 用途 | 选择器 |
|---|---|
| 文档搜索框 / 搜索按钮 | `searchField__input` / `advancedSearchToolbarSearchBtn` |
| 交易列表行 | `table tbody tr`（`filter({hasText})` 定位） |
| Create New（列表右上 / 模板文档） | `getByRole('button', {name:'Create New'})` |
| 展开卡片 | `dataEntryCard__expanding` |
| Detail 标签 | `getByRole('tab', {name:'Detail'})` |
| **IA 编号 / IA 日期**（卡片头部） | `inventoryAdvice.header.reference-input__input` / `inventoryAdvice.header.reportDate-input_date_input` |
| AKN 的两个日期（展开后） | `poAck.header.scheduleShipDate-input_date_input` / `poAck.header.scheduleDeliveryDate-input_date_input` |
| 单据 ⋮（More Actions） | `dataEntry_document-actions-dropdown` |
| **批量发送（底部工具条）** | `dataEntry_document-actions-send`，**且 boundingBox().y > 900** 才是底部那条 |
| 确认弹窗的「继续」 | `modalOkBtn` |
| 覆盖模板的 radio | `radioBtnOverwriteTemplate__radio-input`（用 `.check({force:true})`，直接被 label 挡住） |

### 6.3 三个操作层面的坑

1. **表格是 Handsontable**：点单元格进编辑态后，会出现一个 `textarea.handsontableInput` 浮层**盖住该格**。
   直接 `cell.click()` 会被这个浮层**拦截报 "intercepts pointer events"** → 正确做法是**先点一次进编辑态，
   再对 textarea 键盘输入**（或 `textarea.focus()` 后 `keyboard.type`）。
   清空再填：`Ctrl+A` → `Delete` → 输入 → `Enter`。
2. **编辑后表格会滚回顶部**：行是虚拟化的，目标行会离开 DOM。**每次改完要重新 `mouse.wheel` 滚下去**
   才能再定位到它 —— 所以「定位行」要写成一个可复用的「滚到出现为止」的小函数。
3. **日期字段是 date-picker**：`fill('MM/DD/YYYY')` 能直接写；但若键盘输入没提交上，
   可以点开日历用坐标点（`>` 翻月）—— 坐标**每次都可能变**，点前先截图量。

### 6.4 建议的执行顺序（一次跑完）

```python
# 伪代码
fr = page.frame_locator('[data-testid="app-frame"]')
# A. 改 IA 模板
进模板文档 → Create New/Expand → Detail → 逐行 find-and-edit → ⋮ → Manage Templates → Overwrite → Save
# B. 批量补发
列表 → Create New → Partner → "I don't have a source document." → Inventory Advice
     → Select an existing template → 填 Number of Documents
     → 逐份改 reference / reportDate
     → 勾全选 → 底部 ✈ → modalOkBtn
# C. 核对
列表搜索编号/PO，看状态是 In Transit（AKN）或 Accepted（IA）
```


- **IA 是「发送日 + 7」的单日报告**，这个特性决定了「改了模板为什么不等于改了一切」：
  已经发出去的那 7 天窗口**不会自动回填**，必须**逐天补发**。不知道这点就会以为改完模板就完事。
- **一次 Send 发不出去**这件事很反直觉：界面上会显示成功样式的状态变化，但单据其实还是草稿；
  不认「`In Transit` 才算发」就会把「没发出去」当成「发出去了」。
- **覆盖模板生成新文档**这个行为会让人误判「改动没生效」（打开旧文档看还是旧值）。
- 这两条动作**每天/每批都要做**，且都作用在**发给零售商**的单据上，做错的代价由对方承担。

## When to Apply

- 断货件要改 SPS 侧的预计发货日 → §1（AKN）
- 断货/到货导致可发库存变化 → §2（改模板）
- 发现 IA 报错了库存 → §3 先算窗口，再 §4 批量补发
- 任何一次 SPS 操作之后 → §5 核对

## Examples

**2026-10-16 实测（两单）**

- **AKN**：`138093033`（白194）填 Ship `01/19/2027` / Delivery `01/26/2027`；`138099748`（黄60）填
  `12/02/2026` / `12/09/2026`。两单都经历「第一次 Send 没发出去 → 对新草稿再 Send」才变 `In Transit`。
- **IA 模板**：把 `TT0031010K0062880` 改成 Stock 0 / On Order 50 / 01/19/2027；`CENC/Linen-Yellow-60`
  改成 Stock 0 / On Order 50 / 12/02/2026。其余 SKU 不动。
- **补发**：实测今天那份 IA 的 date 是 `10/23/2026`，而此前 8 天（10/16–10/23）报的都是旧值
  → `Number of Documents = 8` 一次建 8 份，日期分别 `10/16`…`10/23`，编号用 `20261016`…`20261023`，
  底部工具条一次发出 → 列表里 8 份全部 `Accepted`。

## Related

- [pb-stockout-post-shipment-closed-loop.md](pb-stockout-post-shipment-closed-loop.md) —— 断货后的四步闭环（清 invoice / Notion / 邮件 / SPS）
- [pb_orders/docs/reference/stockout-closed-loop.md](../../../pb_orders/docs/reference/stockout-closed-loop.md) —— 可执行版
- [.agents/skills/pb-orders/SKILL.md](../../../.agents/skills/pb-orders/SKILL.md) —— 触发词与可复跑清单
- `SPS_Selenium_Local/sps_automation.py` —— 每天自动发 IA 的脚本（只发 IA，不碰 AKN）
