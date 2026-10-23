---
okf: v0.1
type: Report
title: SO 与采购/生产的真实关联路径
date: 2026-10-22
owner: claude-worker
status: 只读完成；只写 schema 与样本计数，不推断
artifacts:
  - experiments/auto_order/check_po_link.py
---

# SO 与采购/生产的真实关联路径

> 目标：解释 T40「`po_no` 解析到 Purchase Order 命中 0」，并列出**实际存在**的显式关联路径。只读 schema 与样本计数；`po_no` 只显示前缀与掩码格式，不显示原值。

## 0. 预算与样本

- 请求 **37** / 60；耗时 **7.3 s**；单线程；间隔 0.2 s；停止原因：无（正常完成）
- SO 样本：2026-01-01..2026-09-30 已提交 SO 按单号升序取前 **30** 张（外部 8 / 内部 22）
- 命中探测用 SO：**4** 张（哈希 `453f016ebf6c`, `0c568b41c40c`, `a6e449757d72`, `e13d0511c978`）

## 1. `po_no` 是什么

- DocType `Sales Order.po_no`：**fieldtype = `Data`**，label = `Customer's Purchase Order`。**不是 Link→Purchase Order**，所以它不可能承载内部采购单号。

- 30 张 SO 中 `po_no` **非空 30** 条；前缀分布：`TXHY`×8、`PLHY`×5、`NJHY`×4、`BNUSFBA`×2、`DAUSFBA`×2、`TXKY`×2、`（无字母前缀）`×2、`PL`×1、`LEFBAUK`×1、`LEUSFBA`×1、`STFBADE`×1、`RSUSFBA`×1
- 掩码格式（字母→A、数字→9、其他→?）：`AAAA99999999`×13、`AAAAAAA99999999`×8、`AAAA99999999?9`×2、`AAAA99999999??`×1、`AA99999999`×1、`AAAA99999999??9`×1、`AAAA99999999???`×1、`?????AA`×1、`AAAA99999999????`×1、`?????AA??`×1
- 用这 30 个值对 `Purchase Order.name` 精确匹配：命中 **0** 行。

> 仅据 fieldtype 与匹配数：`po_no` 是**客户自己的采购单号**（Data 文本），不是指向 EN Purchase Order 的引用；T40 的「未解析」是**字段语义不同**，不是「PO 单据缺失」。

## 2. 候选显式关联路径：字段是否存在

| 对象 | 引用字段 | fieldtype | 存在 |
|---|---|---|---|
| Work Order | `sales_order` (Link→Sales Order) | `Link`→`Sales Order` | 是 |
| Material Request | `Material Request Item.sales_order` (Link→Sales Order) | `Link`→`Sales Order` | 是 |
| Production Plan | `Production Plan Sales Order.sales_order` (Link→Sales Order) | `Link`→`Sales Order` | 是 |
| Delivery Plan | `Delivery Plan Item.sales_order` (Link→Sales Order) + `so_detail` (Data) | `Link`→`Sales Order` | 是 |
| Delivery Note | `Delivery Note Item.against_sales_order` (Link→Sales Order) + `so_detail` (Data) | `Link`→`Sales Order` | 是 |
| Purchase Order | `Purchase Order Item.sales_order` (Link→Sales Order) | `Link`→`Sales Order` | 是 |

## 3. 候选显式关联路径：样本命中数

> 每格是「用该 SO 单号过滤该 doctype 得到的行数」，单次查询上限 20 行；只说明**样本内**有没有显式引用。

| 路径 | SO `453f016ebf6c` | SO `0c568b41c40c` | SO `a6e449757d72` | SO `e13d0511c978` | 合计 | 备注 |
|---|---:|---:|---:|---:|---:|---|
| Work Order | 0 | 20（上限） | 0 | 0 | 20 |  |
| Material Request | 0 | 0 | 0 | 10 | 10 |  |
| Production Plan | 1 | 4 | 1 | 1 | 7 |  |
| Delivery Plan | 8 | 20（上限） | 20（上限） | 20（上限） | 68 |  |
| Delivery Note | 8 | 20（上限） | 20（上限） | 20（上限） | 68 |  |
| Purchase Order | 0 | 0 | 0 | 0 | 0 |  |

## 3b. Purchase Order 全局对照

- 全库（不限样本）查 `Purchase Order Item.sales_order is set`（limit 5）：返回 **0** 行。
- 同一查询形状在 `Delivery Plan Item.sales_order is set` 上返回 5 行，说明「is set」过滤本身可用；因此 PO 的 0 不是查询写法造成的。

## 3c. 查询陷阱（影响可复现性，须记录）

- 在 `Delivery Plan` 上，字段清单**同时包含表头 `status` 与子表字段**时，接口静默返回 0 行（不报错）；去掉 `status` 后同一过滤返回 **20** 行（带 `status`：0 行）。
- 影响：上一轮 T40 时点的“Delivery Plan 关联 0 行”是**该字段组合造成的假阴性**，不是 DP 真的没有关联；DP 只被当作“关联证据”，所以当时的守恒恒等式与比值不受影响，但「未观测」行数可能偏高。

## 4. 结论

1. **有实际命中的显式路径**：`Work Order.sales_order`（样本合计 20 行，20 为单次查询上限）、`Material Request Item.sales_order`（10 行）、`Production Plan Sales Order.sales_order`（7 行）、`Delivery Plan Item.sales_order`（68 行）、`Delivery Note Item.against_sales_order`（68 行）。这五条路径的字段在 schema 中都是 `Link → Sales Order`，本轮样本都能查到记录。样本只有 4 张 SO，命中的是「有没有」不是「有多少」。
2. **Purchase Order 这条路不通**：字段 `Purchase Order Item.sales_order` 存在且是 Link，但 4 张样本 SO 命中 0 行，且全库 `is set` 查询也是 0 行。也就是说：**schema 允许 PO 引用 SO，但 EN 里没有任何 PO 这样做**。
3. **T40 的「po_no 未解析」是两个独立原因叠加**：① `po_no` 的 fieldtype 是 `Data`（label「Customer's Purchase Order」），存的是客户采购单号，本就不指向 Purchase Order；② 即使想走 PO→SO 的 Link，全库也没有一条 PO 设置了 `sales_order`。因此「有 po_no 却没有对应 PO」是预期，不是漏单，也不是 PO 单据缺失。

## 5. 方法与复现

- 只读：schema 读 `/api/resource/DocType/<name>.fields`；数据读 `/api/resource/<doctype>`；无任何写操作。
- 单号哈希化（sha256 前 12 位）；`po_no` 只输出前缀与掩码格式，不输出原值。
- 样本固定：SO 按单号升序前 30 张，命中探测取前 2 张外部 + 前 2 张内部，可复现。

```bash
uv run python docs/research/supply-chain/2026-10-20/claude/experiments/auto_order/check_po_link.py
```

