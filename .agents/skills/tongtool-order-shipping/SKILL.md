---
name: tongtool-order-shipping
description: >
  通途订单导出的**发货侧**处理：组合件（皮壳 -Cover + 海绵 -Foam）合并成「每包裹一行」的
  UPS/FedEx 批量导入 csv + 美中仓库背贴 PDF。用户提到 Overstock 订单处理、组合件合并、
  每包裹一行、每货品一行、背贴、UPS 批量导入 csv、FedEx 批量模板、OSTK-Fedex、
  OS- 订单导出发货、通途订单导出、美中仓库背贴 时触发。
  不要用于赛狐侧尾程打单（那是 sellfox-shipping）、不要用于承运商轨迹跟踪
  （fedex-track / gls-track / parcel-track）、不要用于通途订单成本（tongtool-order-cost）、
  也不要用于改 Colab notebook 本身（那是 colab-kit）。
metadata:
  module: tongtool_order_shipping
  docs: docs/solutions/integration-issues/carrier-label-batch-field-length-limits.md
  updated: 2026-09-22
---

# 通途订单发货处理

完整知识见 `tongtool_order_shipping/AGENT_HANDOFF.md`。这里是可复跑清单。

## 必须先做

1. 读 `tongtool_order_shipping/AGENT_HANDOFF.md`（数据流 + 三条硬约束 + 包裹号语义）。
2. **知道代码在哪**：流水线本体在同事的 **Google Colab notebook** 里，**不在本仓库**。要改它用 `.agents/skills/colab-kit/`。
3. **一律 `uv run python`**；凭证在父仓库。

## 三条硬约束（改这条线之前先看）

| # | 约束 | 一句话 |
|---|------|--------|
| 1 | 承运商字段有上限 | UPS `Reference 1~5` 各 **35**（超了**整批被拒**）；FedEx `poNumber` **30** / `itemDescription` **450**。合并成一行后必须截断，且**不同字段用不同上限** |
| 2 | 背贴品名查名键 | = 通途导出 `Reference 2` 的**原样字符串**；表是 `US SKU Name`；品名缺失**留白且不报错** ⇒ 必须有「背贴缺名」报告行 |
| 3 | 别用 `!shell` 做文件操作 | 文件名可能含空格 → `!zip` 静默失败 → `files.download` 抛 FileNotFoundError。用 Python `zipfile` |

## 包裹号语义（最容易搞错的一条）

- 通途导出 `Description of Goods` 列 = **订单号**（可能带拆单后缀 `_1/_2` / `-M####`），**不是**通途 P 号。
- Overstock：**一个订单 = 一个包裹**（需拆包的订单，负责同事已拆成独立订单）
  ⇒ 「同一个 `Description of Goods` 值 = 同一个包裹」成立。
- **不要**用正则剥掉后缀去合并 —— 会把拆单后的两个包裹并成一个。背贴 PO 保留整串是**有意的**。

## 不要做

- 不要把它和 `sellfox_shipping` 混起来（那是**赛狐侧**尾程打单）。
- 不要用它做轨迹跟踪（`fedex_track` / `gls_track` / `parcel_track`）或通途订单成本（`tongtool_order_cost`）。
- 不要在 `tongtool_order_shipping/` 目录里找脚本 —— 那里现在只有文档。
- 不要在没有「背贴缺名」报告的情况下跑完整流程。
