---
okf: v0.1
type: Handoff
title: tongtool_order_shipping — Agent 交接说明
description: 通途订单导出的发货侧处理：组合件合并、字段上限、背贴查名链、迁移落点
updated: 2026-09-22
---

# tongtool_order_shipping — Agent 交接说明

> 人读文档: [README.md](README.md) ｜ OKF: [docs/index.md](docs/index.md)

## 一句话

**通途订单导出 → 组合件合并成「每包裹一行」的承运商批量导入 csv/xlsx + 仓库背贴 PDF。**

## ⚠️ 先读这条：本模块现在没有代码

流水线本体是**同事的一个 Google Colab notebook**（Overstock 订单处理）。本模块目前只承载
**这条线的硬约束与知识**，并作为将来迁入仓库时的落点（先例：`pb_orders/` 是把另一个
Colab notebook「PB 订单处理」迁进来的）。

**所以：不要在这个目录下找实现，也不要假设有什么脚本可跑。**
要改流水线 → 用 `.agents/skills/colab-kit/` 那套工具去改那个 notebook。

## 数据流（现状，在 Colab 里）

```
通途订单导出 xls（每货品一行）
  → 按 `Description of Goods`（= 订单号，可能带拆单后缀）分组合并
  → 每组取首行的收件人/重量/尺寸（模板在每行都重复包裹级重量，取首行正确）
  → 组内各 SKU 拼进承运商批量模板的一个字段
  → 背贴 PDF：每包裹一页，页内逐 SKU 一行
```

## 三条硬约束（迁移时必须遵守）

### 1. 承运商字段上限 —— 合并后必须主动截断

| 承运商 | 字段 | 上限 | 超限行为 |
|---|---|---|---|
| UPS | `Reference 1~5` | **各 35** | **整批被拒**（`Invalid Package Reference Value`） |
| FedEx | `poNumber` | **String(30)** | 承运商侧静默按上限切 |
| FedEx | `itemDescription` | **String(450)** | 余量极大 |

- 上限**从官方模板自带的字段定义表读**（FedEx 那张在模板 xlsx 的 `Available headers` sheet），
  再用「承运商**已接受**历史文件的最长值」交叉验证。
- 同一个拼接串放进不同字段**要用不同上限**。
- 这类风险是「每包裹一行」→「每货品一行」的模板变更**新引入**的：旧模板下每包裹只 1 个 SKU、
  合并是空操作（最长 32 字符），历史里找不到先例。

→ [`docs/solutions/integration-issues/carrier-label-batch-field-length-limits.md`](../docs/solutions/integration-issues/carrier-label-batch-field-length-limits.md)

### 2. 背贴品名 —— 查名键是导出里的原样字符串

- 查名键 = 通途导出 `Reference 2` 的**原样字符串**（两侧 `strip().upper()` 后匹配），
  数据在 `US SKU Name` sheet（**不是** `sellfox_shipping/sku_label/name_lookup.py` 走的 `item_languages`）。
- 通途SKU 在 EN 存于 `Item.customer_code` / `customer_items[].ref_code`，**不在** `item_languages.tt_sku`
  （后者只存 `-Cover` 成品码，海绵件为空）。
- 访问性坑（实测）：`Item Language` 子表**不能 list**（403，可逐 Item 读带出）、
  `commodity_sku` **不能当过滤字段**、`Item.name` 是物料编码搜不到 TT 号。
- 尺寸↔序号**不同序**（153→`...4183`、160→`...4182`），必须逐条从 EN 读。
- PIM API `vilavi_pim.api.pim_api.get_sku_item_itemgroup_mapping` 可一把映射，
  **但必须先做假阳性测试**（丢不存在的 SKU 应返回 `not_found`）并横验同族自洽。
- 品名缺失时该行**留白且不报错** ⇒ 流水线必须有「背贴缺名」报告行。

→ [`docs/solutions/integration-issues/sku-name-backfill-via-en-customer-code.md`](../docs/solutions/integration-issues/sku-name-backfill-via-en-customer-code.md)

### 3. notebook 里别用 `!shell` 做文件操作

文件名可能含空格 → `!zip` 被 shell 分词 → `zip error: Nothing to do!`（非零退出但不抛异常）
→ 压缩包没生成 → `files.download` 抛 `FileNotFoundError`。**报错点离根因很远**。
改用 Python `zipfile`。

→ [`docs/solutions/developer-experience/colab-shell-out-filename-spaces.md`](../docs/solutions/developer-experience/colab-shell-out-filename-spaces.md)

## 包裹号语义（别搞错）

- 通途导出 `Description of Goods` 列放的是**订单号（可能带拆单后缀 `_1/_2` 或 `-M####`）**，
  **不是**真实通途包裹号（P 号）。
- 对 Overstock：**一个订单 = 一个包裹**（需拆包的订单，负责同事已拆成独立订单）
  ⇒ 「同一个 `Description of Goods` 值 = 同一个包裹」成立。
- **不要**用正则剥掉后缀去合并 —— 会把拆单后的两个包裹并成一个。
- 背贴的 PO 与条码直接用这一整串（含 `-M####` 后缀）是**有意的**。

## 迁移落点

| 要搬什么 | 搬到哪 |
|---|---|
| 背贴 PDF 生成 | 复用 `sellfox_shipping/sku_label/pdf_generator.py`（4×2" + Code128 + 中/西语名，需调用方先按包裹分组） |
| 品名查询 | `sellfox_shipping/sku_label/name_lookup.py`（走 EN `item_languages`）**或**继续读 `US SKU Name` sheet —— 两者覆盖不同 SKU，迁移时要先对账 |
| 组合 SKU 炸开 | `multi_attr_saihu/tongtu_sku_explode.py`（那是「通途普通商品」导出用的，不含包裹/数量列） |
| 参考先例 | `pb_orders/`（PB 打包单 + UPS 标签 → 通途 Excel + 标签/背贴 PDF，已本地化） |

## 不要做

- 不要把它和 `sellfox_shipping` 混起来（那是**赛狐侧**尾程打单）。
- 不要用它做承运商轨迹跟踪（`fedex_track` / `gls_track` / `parcel_track`）。
- 不要用它做通途订单成本（`tongtool_order_cost`）。
- 不要在没有「背贴缺名」报告的情况下跑 —— 品名缺失是静默的。
