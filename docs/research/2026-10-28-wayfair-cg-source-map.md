---
okf: v0.1
type: Research
title: Wayfair CG 仓来源归类（worker E，给 YTQ 核对）
description: 2026-08-01..10-28 Wayfair 自发货订单的 SKU 来源仓归因——数据可得性、判定口径、结果与缺口
tags: [wayfair, castlegate, warehouse, source-attribution, ytq]
date: 2026-10-28
status: confirmed-by-ytq-2026-10-28
---

# Wayfair CG 仓来源归类（2026-08-01..10-28）

> **2026-10-28 11:40 更新：YTQ 已对《来源归类》49 个 SKU 与《例外清单》32 个全部“同意”。**
> 补充：部分 SKU 被平台批量加 `OLD_` 前缀；美东涤麻没卖完前确实从美东补过 CG；当前只判断 CG 现售 SKU，后续可能有新的美东/美中 SKU 发到 CG。
> 已填版：`D:/Work/fzh-order-store/analysis/wf-cg-source-map-2026-10-28-YTQ核对版已填.xlsx`。

> 目的：回答 backlog `CG-EXTENSION-DECISION` 的前置问题——CG 仓（Castlegate）库存，
> 每个 SKU 到底是**从美东-CENTRADE 还是美中-FZH-DANEEY 发过去的**。
> 确认后，CG 需求才能视为对应分公司仓的“延伸”参与净额，而不是 unknown。
>
> 交付物：`D:/Work/fzh-order-store/analysis/wf-cg-source-map-2026-10-28.xlsx`
> （+ 同名 `.json` 汇总）；脚本 `scripts/wf_cg_source_map.py`。
> **只读分析**：不改主表、不合并、不 push；行级数据留本地，本文件只写聚合与口径。

## 1. 数据字段实查（先查再用）

| 数据 | 实际字段 | 能回答什么 | 关键限制 |
|---|---|---|---|
| GS 月表 `gs_orders.parquet` | `order_id / sku_tongtool / qty / sale_date / warehouse / channel / account` | Wayfair 自发货订单行；`account=WFCastleGateUS` 且 `warehouse=WayfairCG-Cranbury仓` | 只到 2026-09-30；CG 单实际到 **09-18** |
| EN `Tongtool Order`（en-demand-v1 parquet） | 订单头 `warehouse_name/order_type/sale_date` + 行 `tongtool_sku/erp_item_code/quantity/shipping_method` | 10 月 CG 单；带 item_code 与发货形态 | 覆盖 **08-26..10-26**（10 月 modified 窗口）；CG 仓同样只有 Cranbury |
| 通途库存 2026-08-07 合并结存 | `SKU/仓库/可用库存/在途库存`（6 个仓） | 期初美东/美中（含皮壳/成品/半成品子仓）位置 | 不含 CG 仓与退货仓 |
| 通途库存 2026-10-23 美东/美中（YTQ 导出） | 同上（每文件单仓） | 期末两池位置 | 单时点 |
| `tongtool_stock`（2026-10-21） | `warehouse_name/goods_sku/available/intransit` | CG 五个仓：Cranbury 92 SKU/1,760 件；Perris、Romeoville 各几行为 0；McDonough、PortWentworth 当次无行 | 单时点；CG 仓库存与 Wayfair 自有库存不一一对应 |
| Wayfair `AllInventoryExport_2026-10-23` | `Part Number / Warehouse Name / Warehouse Type / In Stock / Available / Order Past 90 Days` | CG 各仓在库（9 个 Castlegate）+ Dropship 两仓（NJ/TX） | 单快照；部分皮壳仍用 `OLD_` 旧料号 |
| 通途「库存变动明细」API | `erp2_stocks_stockschangedetailquery` | 调拨/出入库流水 | **`updatedDateFrom` 只能查最近 7 天**，8–9 月调拨单回查不了 |

## 2. 判定口径

来源仓**不是**调拨凭证（拿不到），用三层证据：

1. **主证据：窗口出库路径**——2026-08-01..10-26 该 SKU 从美东池 / 美中池实际出库
   的件数（GS+EN 合并，CG/波兰/退货仓不计）。窗口内每个 SKU 只从一个池出库。
2. **旁证 A：库存位置**——2026-08-07 与 2026-10-23 两池的可用+在途。
3. **旁证 B：Wayfair dropship 位置**——Wayfair 自己把两个发货点登记为
   `CENTRADE INC. NJ 07936`（美东）与 `CENTRADE INC. TX 77099`（美中），
   每个 SKU 只在一个点有可用库存。

置信度：**强**＝窗口单侧出库且另一池前 6 月（<3 件视为个案）与期末库存均无；
**中**＝窗口单侧但另一池有实质库存/出库；**弱**＝窗口无来源池出库、仅靠历史或库存推断。

退货例外：退货只回 `FZH-DANEEY-退货产品仓`（美中），订单侧 2025-08 起 1,530 单/1,565 件。
无退货仓库存快照，只能按 **SKU 级退货仓出库件数**标“退货重发候选”，不扣减件数、不替代 YTQ 判断。

## 3. 结果（聚合）

| 来源仓 | SKU 数 | 订单数 | 件数 |
|---|---:|---:|---:|
| 美东-CENTRADE | 26 | 146 | 146 |
| 美中-FZH-DANEEY | 23 | 447 | 531 |
| **合计** | **49** | **593** | **677** |

- 期间覆盖：订单 2026-08-01..10-26（10-27..10-28 无数据）；49 个 SKU、593 单、677 件。
- 置信度：强 45（美东 25 / 美中 20）、中 4；**无法判断 0**。
- 交叉验证：39 个 SKU 有 Wayfair dropship 位置信息，与通途窗口出库路径 **39/39 一致，0 冲突**；
  余 10 个为小量 SKU（单 SKU ≤8 件），仅有通途侧证据（已在例外清单标注）。
- 例外标记 32 个 SKU（同 SKU 可带多条）：**仅通途侧证据**（Wayfair dropship 无位置信息）10；
  美中退货仓窗口出库 22；CG 仓超出五项清单（Lathrop/Jacksonville/Lancaster/Aberdeen）7；
  前 6 月两池均有出库 4；Wayfair 用 `OLD_` 旧料号匹配 4；退货仓历史出库 1。
- CG 仓：订单字段只有 Cranbury；Wayfair 10-23 在库分布在 9 个 Castlegate 仓，
  其中用户点名的 5 仓（Cranbury/McDonough/Perris/PortWentworth/Romeoville）均有覆盖，
  另有 Jacksonville/Lancaster/Aberdeen/Lathrop 四仓也持有我们的货。

## 4. 明确缺口（不猜、不写 0）

| 缺口 | 事实 | 影响 |
|---|---|---|
| 调拨凭证 | 通途库存变动 API 仅 7 天，无 8–9 月调拨单 | 来源仓是推断，不是凭证；YTQ 需按 Excel 逐 SKU 确认 |
| 订单 CG 仓字段 | GS/EN 都只有 `WayfairCG-Cranbury仓` | 无法按 McDonough/Perris/PortWentworth/Romeoville 拆订单 |
| CG 库存历史 | Wayfair 导出仅 2026-10-23 单快照 | 无法做 CG 各仓的去程/时效/断货分析 |
| 退货仓库存 | 无快照 | 退货重发只能标 SKU 候选，无法量化“哪几件是退货” |
| 期间尾部 | 10-27..10-28 无订单数据 | 月末两天缺失 |

## 5. 复现

```bash
uv run --with duckdb python scripts/wf_cg_source_map.py
# 默认读：D:/Work/fzh-order-store/*、D:/Work/赛狐/网页自动化/output/通途合并库存结存清单 20260807_1631.xlsx
#        D:/Work/尹/wayfair/库存结存清单2026-10-23*.xlsx、AllInventoryExport_2026-10-23 (1)(1).csv
# 输出：D:/Work/fzh-order-store/analysis/wf-cg-source-map-2026-10-28.xlsx / .json
```

## 6. 下一步（需用户/YTQ）

1. YTQ 核对 49 行「来源仓」，重点看 4 个“中”置信度与 28 条例外。
2. 若 CG 需求按“延伸仓”参与净额，需确认：退货重发件是否从来源仓需求中剔除口径。
3. 若要凭证级结论，需从通途网页端导出 8–10 月「库存变动明细」（API 回查不了）。
