---
okf: v0.1
type: Reference
title: PB 断货闭环 — 打单后才发现无货的四步操作
tags: [pb, stockout, invoice, notion, diane, sps, closed-loop, reference]
timestamp: 2026-10-16
---

# PB 断货闭环（打单后才发现无货）

出件（`run_pb_orders.py`）做完、ASN 也建了，**之后**美中仓才回话说某 PO 实际无货 —— 这条路径
不走「库存预检」（预检是出件**前**的事），走本文的四步。

> 触发词与路由见 [skill `pb-orders`](../../../.agents/skills/pb-orders/SKILL.md)。
> 断货的**判据**与陷阱（别用通途库存判、只认 UPS 取件）见
> [docs/solutions/workflow-issues/pb-out-of-stock-notification-and-zero-stock-orders.md](../../../docs/solutions/workflow-issues/pb-out-of-stock-notification-and-zero-stock-orders.md)。

## 1. 先查清（每次都要）

| 要查 | 怎么查 |
|---|---|
| 是哪个 SKU | PB 批次目录的 `check0stock / checked0stock` CSV 的 `Vendor Style`（按 PO 找明细行） |
| SPS 打没打单 | 批次目录的 `shipment x*.csv` 里有没有该 PO（有 = 建了 ASN）。**≠ 真发货** |
| 有没有 invoice | `invoice/invoice x*.csv` 里有没有该 PO 的 H 行；记下 `Invoice Number` 与 `Invoice Total` |
| 追踪号是否真走 | `ups_track` 查 `Carrier Tracking`，只看「除 MP 外有没有节点」 |

## 2. 四步

### 第 1 步：清 invoice（**月底钉钉提交前必做**）

钉钉提交的 invoice 一旦提交**无法撤销**；若下批到货前顾客取消，会很麻烦。所以打单后才发现无货的，
必须**当天**从当批 invoice 里摘掉。

惯例（2026-09/10 实测，`D:\Work\美国\Tracy Miller\PB orders\<批次>\invoice\`）：

```
invoice/
├── <新总额> 已去除无货<N>单<PO1> <PO2> … 之前是<旧总额>.txt     ← 0 字节，**总额只写在文件名里**
├── invoice x<新PO数> 已去除无货<N>单 <原时间戳>.csv              ← 去掉无货单的 H+D 行
└── NotUsed/
    ├── <旧总额>.txt
    └── invoice x<原PO数> <原时间戳>.csv                          ← 原始备份，原样不动
```

实例：

| 批次 | 新 | 旧 |
|---|---|---|
| 20260921 | `2765.66 已去除无货2单137924672 137940567 之前是2916.96.txt` + `invoice x38 已去除无货2单 …csv` | `2916.96.txt` + `invoice x40 …csv` |
| 20260924 | `931.01 去除无货137951856 INV0580626000012224 1018.96.txt` | `1018.96.txt` |
| 20261015 | `1526.05 已去除无货2单138093033 138099748 之前是1596.54.txt` + `invoice x20 …csv` | `1596.54.txt` + `invoice x22 …csv` |

**口径要点**

- `Invoice Total` 是第 79 列（**表头从 1 数**；0-based index 78），只累加 `Record Type = H` 的行。
  新总额 = 旧总额 − 被摘掉那几单的 `Invoice Total`。
- **H 行才带 PO 号，D 行的 PO 是空的** —— 只删 H 行会留下孤儿明细，必须**连它的 D 行一起删**。
- 回写时保持源文件格式：**UTF-8 不带 BOM、LF**、逐行照搬（只做行筛选，不重新序列化）。
- 顺手核一遍新文件：记录数 = 2×PO 数、H/D 各半、总额对得上文件名。

### 第 2 步：登记 Notion

库 **「PB 无货未发（一行一个 PO）」**，列契约与半自动流程见
[pb_orders/docs/reference/notion-stockout.md](notion-stockout.md)。

```bash
cd pb_orders
uv run python notion_stockout.py --xlsx "<批次>/SPS库存检查操作表-*.xlsx" --out rows.json
```

> 本路径（打单后才发现）**没有操作表**，所以直接把 `--xlsx` 换成新批次的操作表会拿到别的数据 ——
> 这种情况按 notion-stockout.md §2 手工组行，字段口径照那张表。
> 登记完把新 PO 追加进 `pb_orders/data/notion_pb_nostock_pos.json`。

### 第 3 步：通知 Diane（邮件）

| | |
|---|---|
| 发件 | `us@mxdeals.com`（显示名 **Service U.S.**） |
| 收件 | PB 采购对接人 Diane（**具体邮箱见历史邮件 / Notion 台账，不写进仓库**） |
| 工具 | **SMTP 直发**：`smtp.exmail.qq.com:465`（SSL），账号 `us@mxdeals.com`。**⚠️ 发完要 IMAP `APPEND` 一份到「已发送」** —— Tencent Exmail 不自动保存 SMTP 发出的信 |

**主题规律**（2026-09/10 实测）：

```
SKU:<PB买家SKU> out of stock Vendor 5806            ← 新开链时
Re:RE: {EXT} SKU:<旧SKU> out of stock  SKU:<新SKU> out of stock Vendor 5806   ← 后续都是「回复上一封」
```

`Vendor 5806` = Centrade Inc，固定。**一封只报一个 SKU**，多个 SKU 靠回复串成一条链。

**正文模板**（两条口径，任选其一，与历史邮件一致）：

```
Hi Diane

Another SKU is out of stock, restock date: <MM/DD/YYYY>
/ 或：Unfortunately, the 3rd SKU is out of stock, next batch of stock will arrive on <Month DD>, too.

Although Inventory Advices has already made quantity adjustments, based on our old
experience, we still needed to notify SPS via email, which may be handled by SPS
regarding the availability of the SKU and new expected ship date of POs.

SKU: <PB 买家 SKU>
Vendor SKU: <Vendor Style，大写>

Restock Date: <MM/DD/YYYY>

These orders with this SKU are out of stock and cannot be shipped until <MM/DD/YYYY>.
(New PO Acknowledgements were sent with new expected ship date)

PO            PO Date      New PO Acknowledgement Expected Ship Date
<PO…>         <MM/DD/YYYY> <MM/DD/YYYY>

Best
Key
```

- 已建 ASN 的 PO 在正文里标 `(ASN already generated)`。
- 顾客取消类走另一条链：`Re:WSI WISMO/Cancel Request/CHAD - 5806 Centrade Inc <日期>`，
  如 `PO 137892570 Cancel accepted`。
- ⚠️ 邮件里**不要出现** Tracy / 中间人 / 5% 佣金（见 pb-reconciliation 的规矩）。

### 第 4 步：SPS 后台（IA + AKN）

**完整点法见 [docs/solutions/workflow-issues/sps-portal-ia-akn-operations.md](../../../docs/solutions/workflow-issues/sps-portal-ia-akn-operations.md)。** 要点：

| 动作 | 怎么做 |
|---|---|
| 在指定 PO 上重发 **Acknowledgement（855 / AKN）** | 打开 PO → Workflow「Order Status → Acknowledgement」旁 **New** → Type 选 PO Acknowledgement、Auto Fill - Recommended → Expand → 改 `Current Schedule Ship Date`（下一批发货日）与 `Current Schedule Delivery Date`（+7 天）→ Save → **Send Document**。⚠️ **一次 Send 发不出去**：会生成一条新草稿，要**对新草稿再 Send 一次**，状态变 `In Transit` 才算发出 |
| 重提 **Inventory Advice（IA）** | 每天由 `SPS_Selenium_Local/sps_automation.py` 定时发（模板 `IA Template 20250605 x100`）。**改模板 = 改以后每天的 IA**：Create New → Detail 改行 → ⋮ → Manage Templates → Overwrite → 选该模板 → Save（**不是** 单据的 Save） |

**⚠️ IA 是「发送日 + 7 天」的单日报告** —— PB 对某一天的认知由「那天往前 7 天」发出的 IA 决定。
所以改完模板**只影响 7 天后**；**已经发出去的 7 天窗口要逐天补发**（Create New 时填 `Number of Documents`
一次建 N 份，逐份改日期/编号，勾选后用底部工具条的 ✈ 批量发）。

SPS 门户入口 `commerce.spscommerce.com/fulfillment/transactions/list/`，partner `WILLIAMS SONOMA INC`，
账号 `us@mxdeals.com`。

## 3. 到货之后

按 Notion 里的记录补发。**变化要回写 Notion**：

| 变化 | 改哪些列 |
|---|---|
| 到货了 | `状态` 待到货 → 已到货待发；`到货日期` 填实际 |
| 补发建了通途单 | `通途建单` 勾上；`通途单号` 写 `已用号 → 下次可用后缀` |
| 真发出去了 | `状态` → 已发货 |
| 顾客取消 | `顾客=取消` + `状态=顾客取消` |
| invoice 处理完 | `invoice` → 已去除 / 已处理 |
| 通知过 Diane | `通知Diane` 填日期 |

> 补发时**通途不允许重复订单号**，要换一个没用过的后缀 `-N`。
> 下次可用 = **该 PO 已用过的最大 `-N` + 1**（拆单与补发共用同一命名空间）。
> 查法：扫历史 `PB_*导入*.xlsx` 的 `PO Number-Line` 列，或通途模糊搜 `PBUS-{PO}`。
> CLI：`--reorder PO`（见 workflow.md §10）。

## 4. 已知缺口

1. **SPS 后台动作已全部成文**（AKN 重发、IA 模板覆盖、IA 批量补发）→ 见
   [sps-portal-ia-akn-operations.md](../../../docs/solutions/workflow-issues/sps-portal-ia-akn-operations.md)。
   仍未脚本化（靠人工点）。
2. **邮件**：已可用 SMTP 直发（见 §2 第 3 步），**发完要 IMAP APPEND 到「已发送」**。
3. **EN 的 Bin 数量不能当库存用**（EN 不扣减通途库存，2026-10 确认）。
