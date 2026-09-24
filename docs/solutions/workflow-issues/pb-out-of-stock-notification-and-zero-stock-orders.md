---
okf: v0.1
type: Reference
title: PB 断货通知与 0 库存订单处理 — 数据来源、PO 映射与三个反直觉陷阱
date: 2026-09-16
last_updated: 2026-09-16
category: workflow-issues
module: pb_orders
problem_type: workflow_issue
component: out-of-stock-notification
severity: medium
applies_when:
  - "美国仓某 SKU 断货，要通知 PB 并重发 PO Acknowledgement"
  - "需要知道 PB 的哪些订单因无货卡住"
  - "需要把 PB 的 PO 号 / SKU 对回 EN 内部单据"
tags: [pb, pottery-barn, sps, dropship, out-of-stock, tongtool-order, acknowledgement, edi-855]
related_components: [pb_reconciliation, en_api, tongtool_order, missing-products]
---

# PB 断货通知与 0 库存订单处理

## Context

Pottery Barn (PB) 通过 SPS 下单，**Dropship**（一单一件，直发消费者）。当美国仓（美中/美东）某 SKU
无货时，这批订单会卡住不能发。业务处理两步：

1. **邮件通知 PB 采购对接人** —— 说明哪个 SKU 断货、预计何时恢复；
2. **在 SPS 门户为受影响的 PO 重发 Acknowledgement（EDI 855）**，填新的 expected ship date。

## 1. 判断「哪些订单因无货未发」—— 用 PB 订单目录里的 0 库存导出

**不需要自己推断。** PB 订单目录里每期都有一份导出，直接给出卡住的订单。

目录约定（根目录见 `pb-reconciliation-monthly-update.md`）：

```text
<PB orders 根>/<YYYYMMDD>/
    checked0stock order xNN <YYYYMMDD>_<HHMM>_<id>.csv    ← 0 库存订单（本期卡住的）
    shipment xNN <YYYYMMDD>_<HHMM>_<id>.csv               ← 已发货 ASN 明细
    invoice/                                              ← 发票
    NotUsed/                                              ← 备用/作废的导出
```

实测日期目录：`20260903` / `20260907` / `20260910` / `20260914` —— 每期一份，取**最新日期目录**。

### 关键列

| 列 | 含义 |
|----|------|
| `PO Number` | **PB 的 PO 号**（如 `137892570`） |
| `Buyers Catalog or Stock Keeping #` | **PB 的 SKU**（如 `8147053`） |
| `Vendor Style` | **我们的码**，大写形式（如 `CEN961NLINEN-SAGEGREEN-138`） |
| `Qty Ordered` | 数量 —— Dropship 实测多为 `1.0` |
| `Product/Item Description` | 品名 |
| `PO Type` | `Dropship` |
| `Cancel Date` / `Ship No Later Date` | 取消/最迟发货约束 |

### 解析要点

**一个 PO 在 CSV 里占两行**：第一行是 PO 表头（`Buyers Catalog` / `Vendor Style` / `Qty` 都为空），
第二行才是明细。**必须按 `PO Number` 向下填充**，否则会解析出「有 PO 但没 SKU」。

比对多期导出可以区分「新断」与「持续断」—— 但**只用于看断货持续时间，不能用来判断补货是否漏排**（见 §4）。

### 大小写

PB 侧用**大写**（`CEN961NLINEN-SAGEGREEN-138`），通途/EN 侧是驼峰（`CEN961NLinen-SageGreen-138`）。
对齐时统一 `upper()`。

## 2. PB PO ↔ EN 内部单据的映射

PB 的 PO 在 EN 里是 **Tongtool Order**，命名规则 `PBUS-<PB的PO号>`：

```text
PB PO 137892570
  └─ EN Tongtool Order  name = PBUS-137892570
       ├─ platform_sku  : CEN961NLINEN-SAGEGREEN-138   ← PB 侧的码（大写）
       ├─ tongtool_sku  : CEN961NLinen-SageGreen-138   ← 通途码
       └─ erp_item_code : KS0001-DM-140-GRASSGREEN     ← EN 物料
```

由此一条链打通：**PB PO → PB SKU → 我们的码 → EN 物料**。

### 2.1 拆单后缀 `-N`：一个 PB PO 可能拆成多单

**一个 PB PO 可能拆成多个 EN 单**，命名是 `PBUS-<PO>-1` / `-2` / `-3`…：

| PO | EN 单 | 包裹数（实测） |
|----|-------|----------------|
| 137899362 | `-1`、`-2` | 2 |
| 137887647 | `-1`、`-2` | 2 |
| 137879782 | `-1`、`-2` | 2 |
| 137770200 | `-1`、`-2` | 2（`-1` 已发货） |
| 137892570 | 无后缀（单包裹） | 1 |

→ 查 PO 时要**同时试无后缀和 `-1/-2/-3`**，只试无后缀会漏。
包裹数与拆单数一一对应，可与 shipment csv 的跟踪号数量互相印证。

### 2.2 `PBUS-<PO>` 是否存在 ⟺ 是否已打单（生成面单）

实测对照（2026-09-16）：

| PO | 打单状态 | EN 有记录 |
|----|----------|-----------|
| 137682252 / 137770200 / 137874674 / 137892570 / 137887120 | 已打单 | ✅ |
| 137695876（顾客取消）/ 137794886 / 137814551 / 137828896 / 137886498 | 未打单 | ❌ |

→ **`PBUS-<PO>` 查得到 = 已生成面单；查不到 = 未打单**（或订单未导入）。
这是从 EN 侧快速判断「打过单没有」的口径。

### 2.3 ⚠️ `items` 子表读取不稳定

同一单 `PBUS-137892570` 早先能读到 `items[]`（含 `platform_sku` / `erp_item_code`），
后来同样查询返回 `items=0`。**子表字段不一定随单文档返回**，取 SKU 映射时：
优先用 `platform_sku`（如果返回），否则回退到 PB 订单目录的 csv（`Vendor Style` 列）。

> **不要走 `Sales Order.po_no`** —— 那个字段是内部自编的流转号，且实测为空，
> 与 PB 的 PO 无关（见 `erpnext-so-closed-unshipped-and-unstarted-work-orders.md` 第 10 条）。
> 查 PB 的 PO 一律走 **Tongtool Order**。

实测（2026-09-16）：`137892570` / `137887120` / `137874674` 都能查到；
`137886498` 查不到（可能尚未导入）。

## 3. 通知邮件模板（实测已用）

```text
主题： SKU:<PB SKU> out of stock Vendor 5806
收件人：<PB 采购对接人>

Hi <对接人>

another SKU is out of stock, restock date: <MM/DD/YYYY>

SKU: <PB SKU>
Vendor SKU: <Vendor Style，大写>

N POs with this SKU are out of stock and cannot be shipped until <MM/DD/YYYY>. (New PO Acknowledgements were sent with new expected ship date)

<PO 1> (ASN already generated)
<PO 2> (ASN already generated)

Best Wishes
Key
```

- `Vendor 5806` = Centrade Inc（我们的 PB 供应商号），固定。
- 已生成 ASN 的 PO 后面标 `(ASN already generated)`；没有的不标。
- 同一封里只报一个 SKU；多个 SKU 分开发（后续可用 `Re: <上一封主题>` 关联）。

## 4. restock date 的来源，以及三个反直觉陷阱

「restock date」用的是**内部粗估口径**：**EN 销售订单下单日期 + 3 个月**。
它是约定，不是到仓事实，也不是 PB 侧字段。

来源是补货 SO 的 `transaction_date`。例：`SO-26-00101` 下单 `2026-08-17` → 报 **`11/17/2026`**。

**⚠️ 一个 SKU 可能有多张未发补货单，+3 月结果不同。**
例：同一 SKU 另有 `SO-26-00110`（下单 `2026-09-02` → `12-02`）。
**报给 PB 之前必须确认这次的货来自哪张单** —— 报错日期会让 PB 按错误预期排计划。

### 陷阱（三个都在 2026-09-16 这次踩过）

1. **❌ 不要用「某 SKU 不在补货单上」推断「补货漏排」。**
   补货依据是 **通途库存 + 销量**：**有货够卖一段时间就不补，也不是一次把所有货补全**。
   某个尺寸不在补货单上是正常状态，不是计划漏了。这是本次最严重的误判。

2. **❌ 不要用供应链登记表的批次反推「接近断货」。**
   批次数据只能给出「上次到仓是什么时候」，**推不出「还剩多少、还能卖几天」**。
   判断「已经断了」用 §1 的 0 库存导出；判断「快断了」必须用库存 + 销量。

3. **❌ 不要从单张订单的字段反推没有的数量规模。**
   PB 是 Dropship，`Qty Ordered` 实测为 `1.0`。凭想象假设「PO 合计超过 N 件」会直接导致错判。

4. **⚠️ 目录里既有的库存/销量导出可能过期**（实测有 6 月的），要用需重新导出。

## 5. 库存 / 销量的数据来源

补货决策依据是 **通途库存 + 销量**。

### 5.1 ⚠️ 前提：通途「库存 0」不等于断货（2026-09-16 经发货同事确认）

**这是本主题最重要的一条。** 通途美中仓显示可用库存 0，**不能直接判定断货**，原因：

| 为什么通途库存会不准 | 说明 |
|---|---|
| **通途为标记发货必须先「报溢」** | 库存不够扣减时，操作同事**先报溢把库存加上**、再做出库。所以系统里会出现「出库 N 件 + 报溢 +N 件」一一抵消、可用库存恒为 0 的现象 |
| 退货 / 发货数量本身不准 | 库存记录与实际不符（这种情况下真实余量通常也不多） |
| 刚到仓、通途还没加库存 | 货已在仓但系统未入账 |

**实际发货流程是「试探性发货」**：PB 订单（已生成的 PDF Label + 背贴）**照常发给美中仓**，
美中有货就发走；没货才回头通知发货同事。所以**「发过去没被退回来」才是实际有货的证据**。

→ **判断断货的可靠来源是 §1 的 PB 0 库存订单导出 + 美中仓的人工回话**，
不是通途可用库存。用通途库存判断会**系统性地把「有货但系统显示 0」误判为断货**。

### 5.2 数据源清单

| 途径 | 内容 | 状态 |
|------|------|------|
| 网页自动化 `tongtu.stock.export` | 通途**库存结存**，支持 **6 仓**切换 | ✅ 已具备（`web_automation/`，Playwright，ExtJS） |
| 网页自动化 `tongtu.sales.export` | 通途**销售报表**（长区间销量走这条） | ✅ 已具备；有「提交互斥」，间隔建议 ≥1h |
| 通途 API `erp2_stocks_stocksquery` | 按仓库取库存，**`warehouseName` 必填**，含 `intransitStockQuantity`（在途） | ✅ 已实测（见 §5.3） |
| 通途 API `erp2_stocks_stockschangedetailquery` | 库存变动明细，可推近期销量 | ⚠️ **`updatedDateFrom` 只能 7 天内** |
| `PB orders` 目录旧导出 | 可能过期，用前先看日期 | ⚠️ |
| 赛狐库存 | **不可用** —— 安全冗余数量，非真实可售 | ❌ |

### 5.3 通途 API 实测（2026-09-16）

- 美中仓名 = **`美中-FZH-DANEEY`**（另有 `美中-FZH-DANEEY-退货产品仓`）；同批还有 `美东-CENTRADE`、`波兰-FZHPoland-covers` 等，全量 58 个。
- `erp2_stocks_stocksquery` 返回：`availableStockQuantity` / `intransitStockQuantity` /
  `defectsStockQuantity` / `waitingShipmentStockQuantity` + `goodsAvgCost` / `goodsCurCost`。
- 实测 `CEN961NLinen-SageGreen-138 @ 美中-FZH-DANEEY` → 可用 0、在途 0。
- 日期参数格式必须是 `yyyy-MM-dd HH:mm:ss`（`yyyy-MM-dd` 报 525）。
- **同一商户 5 次 ERP2 调用/分钟**，MCP 也绕不过；524=无权限、525=参数错、526=超频。

## 6. 实测：2026 年 8–9 月美中断货 SKU

**经确认断货（4 个通途 SKU）**：

```
CENKZ1324-SkyBlue-97
CENKZ1325-Yellow-97
CENKZ1325-YELLOW-138
CEN961NLinen-SageGreen-138
```

**9 月初通途显示库存 0、但后来「报溢发货」且未收到未发货通知（4 个，已核实）**：

```
CEN961NLinen-SageGreen-153
CEN1607NLinen-Ivory-153
CENKZ1324-SkyBlue-153
CENKZ1325-Yellow-153
```

> 这 4 个正是 §5.1 的典型：通途 0 但实际有货。

### 6.1 ⚠️ 核实必须走 UPS 跟踪，不能只看 shipment 导出

**`shipment xNN *.csv` 只是我们「标记发出」（生成 ASN + 面单），不等于 UPS 实际揽收。**
必须用 UPS Track API 查节点，确认已离开「Shipper created a label」。

实测这 4 个 SKU 在 2026-09（PB 侧 ASN 记录 22 单）：

| 结果 | 单数 | 说明 |
|------|------|------|
| **已交付（真实发出）** | **19** | UPS `DELIVERED` |
| 在途 | 2 | `Arrived at Facility` / `The delivery will be rescheduled` |
| **只建标、UPS 未揽收** | **1** | `Shipper created a label, UPS has not received the package yet` |

结论：4 个 SKU **大部分确实发出**（19/22 已交付），但**不是全部** ——
有 1 单（PO 137883758 / Ivory-153）当时停在 Label Created。

> **但不要一看到 Label Created 就报警**：那单是 09-14 下午才生成面单、交给美中，
> 到 09-16（美中当地还是 09-16）**才过 2 天**，属正常等待（见 §6.4 的间隔分布）。
> 而且 09-15 美中回话时**只提了 SageGreen-138 的 2 单没货，没提别的单** → 该单应假设有货。
> 判断异常要结合「已过几天」和「该 SKU 是否已确认断货」，不能只看状态名。

**只看 ASN 会把停在 Label Created 的单误判为已发。**

工具：`ups_track/`（UPS 官方 Track API，凭证 `UPS_CLIENT_ID/SECRET` 在本机 `.env`）。

```bash
uv run python -m ups_track.cli query --input <跟踪号.csv> --env prod --out <前缀>
# summary.csv: 当前状态 / 已交付 / 交付日期 / 建标时间 …（含客户姓名，勿入库）
```

**隐私**：UPS 输出含收货人姓名与城市，**只在本机看，不要提交进仓库**。

### 6.3 只看两个状态：`Label Created` vs `UPS 已收到包裹`

**PB 拿「UPS 站点收到我们包裹」的日期作为付款依据（账期约 1 个月）。**
所以跟踪状态只需要区分两档，**后续的运输/交付节点不关心**：

| 档 | UPS 状态表现 | 含义 |
|---|---|---|
| ❌ **未收到** | `Shipper created a label, UPS has not received the package yet`（状态码 `MP`） | 我们只建了标，货还在美中，**PB 不会开始算账期** |
| ✅ **已收到** | 首个实体节点 `Drop-Off`（`XD`），之后 `Arrived/Departed from Facility`、`DELIVERED` | 美中已交给 UPS，**这一天就是 PB 的起算日** |

**判断口径**：时间线里除 `MP` 外是否还有节点。有 =UPS 已收到。

### 6.4 实测：2026 年 9 月全量（120 个跟踪号）

扫 `202609*/*shipment*.csv` 全部单元格取 `1Z` 号（**号可能不在 `Carrier Tracking` 列；
一个 PO 可能有多个包裹号**，实测 `137887647`、`137879782` 各 2 个），用 `ups_track` 实查：

| 结果 | 数量 |
|------|------|
| **UPS 已收到包裹** | **110**（87 DELIVERED + 11 Arrived + 11 Departed + 1 rescheduled） |
| **仍停在 Label Created** | **10** |

**建标 → UPS 揽收 间隔（110 单）**：

| 最小 | 最大 | 中位 | 均值 |
|------|------|------|------|
| 0 天 | 2 天 | **0 天** | 0.5 天 |

分布：`0天×62 / 1天×44 / 2天×4` —— **近期美中发货基本当天或隔天交给 UPS**。

> ⚠️ 不要拿 2026-08 那份「标签建好后 1–7 周才交给 UPS」当常态。那是**未付发票**的样本，
> 本身就是因为迟发才未付 —— 选择性样本，不代表整体。

**10 个未揽收的分布**（截至 2026-09-16）：

| 建标日 | 单数 | 已过 | 备注 |
|--------|------|------|------|
| 2026-09-10 | 1 | **6 天** | PO 137874674 / `CENKZ1325-Yellow-138` —— 正是已确认断货的 SKU |
| 2026-09-14 | 9 | 2 天 | 含今天发邮件的 2 单（`137892570`、`137887120`，均 SageGreen-138） |

两档的差别有实际后果：**建标 09-14 那批才过 2 天，属正常等待**（美中发货偏慢，且有时差），
不能当异常；而 **09-10 那单已过 6 天**，结合该 SKU 已确认断货，才值得跟进。

### 6.5 可复用命令

```bash
# 1) 从 PB orders 的 shipment csv 提取全部 1Z 号（扫所有单元格，按号去重）
# 2) 批量查 UPS
uv run python -m ups_track.cli query --input <跟踪号.csv> --env prod --out <前缀> --workers 6
# 3) summary.csv 看「当前状态」；timeline.csv 找首个非 MP 节点的时间 = UPS 起算日
```

**隐私**：UPS 输出含收货人姓名/城市，**只在本机看，不要提交进仓库**。


19 单已交付样本（该批全是 UPS Ground，`UPSC`）：

| 统计 | 值 |
|------|----|
| 最小 / 最大 | 1 / 7 天 |
| 中位 | **3 天** |
| 均值 | 3.5 天 |
| 分布 | 1天×2 / 2天×3 / 3天×5 / 4天×4 / 5天×4 / 7天×1 |

→ **`发货日 + 7 天` 是安全上限**（覆盖全部样本），但**典型只要 3 天**。
给 PB 回填日期时用 +7 偏保守；想贴合实际可用 +3。

## 7. PB 侧「open order」表（PB 对接人发来的待填表）

命名模式：`5806 open order <PB对接人> <YYYYMMDD>.xlsx`（放在 `PB orders` 根目录）。
**文件名含 PB 对接人姓名，不要原样抄进仓库或对外文档。**

格式（实测一份 41 单的表）：

| 列 | 说明 |
|----|------|
| `VENDOR_ID` / `VENDOR_DESC` | `5806` / `CENTRADE INC` |
| `SALES_ORDER_ID` | PB 的销售单号 |
| `PO_ID` | **PB 的 PO 号**（= EN `PBUS-<PO_ID>`） |
| `ITEM_ID` | **PB 的 SKU** |
| `PO_CREATE_DATE` / `ORIGINAL_SHIPMENT_DATE` | 建单日 / 原要求发货日 |
| `UPDATED_REQUESTED_SHIP_DATE` | **待我们回填的更新发货日** |
| `ORDERED_QTY` | 数量（Dropship 多为 1） |
| `can ship by 10/05`、`UPS can ship by 10/26` | **待我们回填的两列** |

回填依据 = 该 SKU 的 restock 估算（补货 SO 下单日 + 3 个月，见 §4）与实际发货确认。

## 8. SPS 操作

Acknowledgement = EDI **855（PO Acknowledgment）**。重发动作在 **SPS 门户手动**完成，
填新的 expected ship date。

**SPS API 已确认为收费项，暂缓推进**（原可行性论证见
`architecture-patterns/sps-commerce-api-automation.md`，当时结论即「瓶颈在商务开通而非技术」）。

## Why This Matters

- **「通途库存 0」不是断货判据**（§5.1）。通途为标记发货必须先报溢，实际流程是「试探性发货」——
  照常把 PB 订单发给美中仓，有货就发走、没货才回话。把通途 0 当断货会系统性误判。
  本次实测：某 SKU 可用库存 0、近 7 天却实际发出 3 件，出库数与报溢数一一抵消。
- 「哪些订单卡住」在 PB 侧已有现成导出，**自己推断既慢又容易错** —— 先用供应链批次反推，
  折腾半小时没得到结论，用户指到 PB 订单目录后十分钟就查清。
- PB 的 PO 与 SKU **不在** EN 的销售订单上，只在 Tongtool Order 里。不知道这条链就会误以为
  「我们系统里查不到 PB 的单」。
- **补货逻辑（库存+销量、不够才补、不一次补全）是判断的前提**。不了解它就会把
  「某 SKU 不在补货单上」误读成「计划漏排」—— 这是一个会误导同事的结论。

## When to Apply

- 美国仓报某 SKU 断货，要判断影响哪些 PB 订单、通知 PB 时。
- 需要用 PB 的 PO 号或 SKU 反查我们内部单据/物料时。
- 看到「断货清单」想做结论、或想评价补货计划时 —— 先读 §4 的陷阱。

## Examples

**2026-09-16 实测**：SKU `8147053` / `CEN961NLINEN-SAGEGREEN-138` 在美中断货。

- 0 库存导出里 `137892570`、`137887120` 两单命中，各 1 件。
- 补货单 `SO-26-00101`（下单 2026-08-17）→ restock `11/17/2026`。
- 通知邮件按 §3 模板发出，两个 PO 都标注 ASN already generated。

同一批数据还显示：该 SKU 只在本期（0914）出现，属**新断**；而 `CEN1607NLINEN-IVORY-*`
等 SKU 已连续 4 期出现（**持续断**）—— 但按 §4 陷阱 1，**不能据此判断补货是否漏排**。

## Related

- `docs/solutions/workflow-issues/pb-reconciliation-monthly-update.md` — PB 对账表月度更新（同一数据根目录）
- `docs/solutions/architecture-patterns/sps-commerce-api-automation.md` — SPS API 可行性论证（API 为收费项，暂缓）
- `docs/solutions/workflow-issues/erpnext-so-closed-unshipped-and-unstarted-work-orders.md` — 第 10 条：EN `po_no` 不是客户 PO
- `dingtalk/dingtalk_sheet/AGENT_HANDOFF.md` — 供应链登记表只读读取
- `.agents/skills/tongtu-automation/SKILL.md` — 通途库存结存 / 销售报表导出（6 仓切换）
- `tongtool_api/AGENT_HANDOFF.md` — 通途 ERP2 API / MCP 与限流
