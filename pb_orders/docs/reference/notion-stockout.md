---
okf: v0.1
type: Reference
title: PB 断货登记 — 库存预检缺货 → Notion「PB 无货未发」库
tags: [pb, notion, stockout, no-stock, sps, stock-precheck, reference]
timestamp: 2026-10-15
---

# PB 断货登记

每批 SPS 库存预检（`stock_precheck.py`）会筛出一批**整单缺货**的 PO。这些无货件要登记到
Notion，用来跟踪「谁还没发、什么时候到货、通途建没建单、invoice 处理没处理」。

## 1. Notion 库

| | |
|---|---|
| 名称 | **PB 无货未发（一行一个 PO）** |
| 库 URL | <https://app.notion.com/p/988bce5435e246559f585fa5ef32a60b> |
| data source id | `collection://fa2f272d-289a-4a88-88eb-9ef39be00e43` |
| 位置 | 「任务202408-」→ 页「！！！无货未发 蓝色97+黄色97…」下 |

> 2026-10-08 从一张手写表格迁过来（原页保留不动作参照）。一行 = 一个 PO（部分缺货的 PO
> 也只有一个「无货件」行，那一行 `打单=部分`，细节写进 `备注`）。

### 列契约

| 列 | 类型 | 取值 / 说明 |
|----|------|-------------|
| `PO` | title | PB 的 PO 号（光号；已建通途单的个别行会写成 `PBUS-…`） |
| `SKU` | select | 我方简称：`蓝色97` `黄色97` `黄色138` `黄194` `草绿138` `草绿153` `绿100` |
| `通途SKU` | text | 通途里的规范大小写，如 `CEN961NLinen-SageGreen-153` |
| `对方SKU` | text | SPS 的 `Buyers Catalog or Stock Keeping #`，在 SPS 界面定位明细行用 |
| `打单` | select | `未打单` / `已打单` / `部分`（部分 = 该 PO 只给有货明细打了） |
| `通途建单` | checkbox | 是否已在通途建过单 |
| `通途单号` | text | 已建号 + 下次可用后缀（通途不允许重复订单号） |
| `状态` | select | `待到货` / `已到货待发` / `已发货` / `顾客取消` |
| `invoice` | select | `未处理` / `已去除` / `已处理` / `不适用` |
| `顾客` | select | `正常` / `取消` / `改地址` |
| `新地址` | text | `顾客=改地址` 时填 |
| `到货日期` | date | 预计/实际到货日期（**跟 SKU 走**，同 SKU 各行应一致） |
| `SPS操作日期` | date | 在 SPS 上操作（导出/打单）的日期，一般周一、周四 |
| `通知Diane` | date | 通知 Diane 的日期 |
| `检出批次` | text | 哪次预检发现的（源导入文件名） |
| `备注` | text | 自由文本 |

## 2. 半自动流程（重要）

Notion 的写入**走交互式 MCP**（`notion-personal`）——它的 OAuth 凭证只对 MCP 服务器有效，
脚本复用不了（实测把缓存的 token 打 REST API 返回 **401**）。所以是「**脚本算、Agent 推**」：

```
uv run python notion_stockout.py --xlsx "<SPS库存检查操作表-*.xlsx>" --out rows_to_add.json
        ↓  产出 JSON（parent + pages + summary）
Agent 用 notion-create-pages 把 pages 推上去
        ↓
把新 PO 追加进 data/notion_pb_nostock_pos.json（下次去重就不会重复推）
```

脚本本身**只读 xlsx、只产出 JSON，不连 Notion**（`--out` 缺省打到 stdout）。

### 命令

```bash
cd pb_orders
uv run python notion_stockout.py \
  --xlsx "D:\Work\美国\Tracy Miller\PB orders\20261012\SPS库存检查操作表-order x24 20261012_0102_199800.xlsx" \
  --out rows_to_add.json
```

| 参数 | 默认 | 说明 |
|------|------|------|
| `--xlsx` | 必填 | 预检产出的 `SPS库存检查操作表-*.xlsx` |
| `--sku-map` | `data/notion_sku_map.json` | Vendor Style → Notion 取值映射 |
| `--known-pos` | `data/notion_pb_nostock_pos.json` | 已有 PO 快照（去重）；传 `''` 关闭 |
| `--sps-date` | 从文件名取 `YYYYMMDD` | 覆盖 SPS 操作日期 |
| `--batch` | 自动拼 | 覆盖「检出批次」文案 |

### 硬约束（都不静默）

- **Vendor Style 不在映射表 → 退出码 2，不产出半成品**（提示去补 `data/notion_sku_map.json`）。
- **「缺货明细」里标 `全部缺货` 的行 必须与「全部缺货PO」sheet 完全一致**，不一致报错。
- 命中去重的 PO、以及同一 PO 有多条缺货明细（只记一行）的情况，都写进 `summary` 报告出来。

## 3. 字段对应（操作表 → Notion）

| 操作表（缺货明细 sheet） | Notion |
|---|---|
| `PO Number` | `PO` |
| `Vendor Style` | 经 `data/notion_sku_map.json` → `SKU` + `通途SKU` + `到货日期` |
| `Buyers Catalog or Stock Keeping #` | `对方SKU` |
| `PO 库存状态` = `部分缺货` | `打单=部分`；否则 `打单=未打单` |
| 其余 | 固定 `通途建单=false`、`状态=待到货`、`invoice=不适用`、`顾客=正常`、`备注=库存预检自动登记；SPS 未打单` |

## 4. SKU 映射表 `data/notion_sku_map.json`

键 = Vendor Style **大写去空白**；值 = `{sku, tongtu_sku, eta}`。

- **到货日期是唯一会随时间变的字段** —— 变了只改这一个文件，不用动代码。
- `eta` 允许为 `null`（老表里没记，例如黄色97）→ 该行不写 `到货日期`，并记进 `summary.无到货日期`。
- 出现新 SKU：先在映射表加一条，再跑脚本。

## 5. 操作登记惯例（用户要求：**所有操作的过程都要记录到 Notion**）

推到 Notion 只是「开了个头」。**每一行都要随操作往后追加「备注」**，形成这条 PO 的时间线：

```
【<日期> 操作记录】
① …（做了哪一步、结果）
② …
```

- **只追加、不覆盖**；同一天多次操作分开列；
- **待定/存疑也要记**（例：*WX 反馈最快到货 2 月，今日 IA/AKN 暂不改，等确认*）；
- 除了 `备注`，对应的**结构化列**也要同步（`打单`、`通途建单`、`状态`、`invoice`、`通知Diane`、
  `到货日期`、`顾客`/`新地址`）—— 口径见 §1 的列契约与
  [stockout-closed-loop.md](stockout-closed-loop.md) §3「到货之后」。
- 常用列的更新入口：`mcp__notion-personal__notion-update-page`（`command: update_properties`）。

> **为什么写死这条**：Notion 台账是这条闭环唯一的**跨批次记忆**。不记过程，下次（或换个 Agent）
> 只看到一堆字段，不知道该 PO 走到哪一步、为什么是现在这个状态。

### 5.1 落点规则：**单行的记进该行备注；跨单/非单的建「任务页」**

不是所有操作都挂得上某个 PO。分两种落点：

| 操作类型 | 记在哪 |
|---|---|
| **只涉及某几个 PO**（清 invoice、重发 AKN、改 IA 里这几款、发断货邮件） | **追加到该行「备注」**（§5 的格式） |
| **跨单 / 不挂在任何 PO 上**（BOM 成本刷新、补货量决策、断货预警、流程本身的改动） | **在 `任务202408-` 库新建一页**（`Name` + `Status` + `标签`），正文用 Markdown 写「操作清单」 |

**任务页的写法**（2026-10-16 实测）：页名带日期与范围（例：`PB 断货处理 2026-10-16（2 单：… ）`），
正文分四块 —— **事件表 / 操作清单（逐条 ①②③）/ 其他操作（非本单）/ 待办**。
这样「跨单的事」也有落点，不会被塞进某一条 PO 的备注里。

### 5.2 ⚠️ 富文本换行的坑：要真换行，别写 `\n` 字面量

通过 MCP 写 `备注` 时，**换行必须是真正的换行符**。实测把 `\n` 写成了**字面量 `n`** 存进 Notion，
整段变成 `…下单。n【操作记录】n① …`。**写完后回读一次确认换行正常。**

## 6. 边界 / 不做

- **不接**网页服务 / worker / 定时任务（本模块的网页版没有 Notion 凭证）。
- **不自动**跳过人工判断：新缺货推完后，`到货日期`、`通途单号`、`invoice`、`顾客` 这些
  仍需人在 Notion 上维护。
- 脚本不写 Notion，因此 `data/notion_pb_nostock_pos.json` 的快照需要推完后手工追加
  （或让 Agent 追加）。
