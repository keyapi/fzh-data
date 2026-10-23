---
okf: v0.1
type: Review
title: EN “该下什么单”离线算例（10 例 + 规则草图）
date: 2026-10-22
owner: claude-worker
status: 完成；只读，103 GET；无写入
artifacts:
  - experiments/auto_order/order_examples.py
  - out/auto_order/order_examples.md
  - out/auto_order/order_examples.csv
  - out/auto_order/order_examples.json（脚本附带的机器可读汇总）
---

# EN 下单算例（草稿）

> 只读生产 REST + 本地 BOM/库存旁证；预算 ≤120 GET、单线程、200 ms 间隔。
> **只出建议草稿，不自动提交、不下单。** 未知写“未取得/未证”，不填 0。

## 1. 预算

| 项 | 值 |
|---|---|
| 请求 | **103** / 120 |
| 耗时 | **20.6 s** |
| 间隔 / page_length | 0.2 s / ≤100 |
| 停止 / 错误 | 无 / 0 |
| 写入 | 无（全部 GET） |

路径：Sales Order 列表 2、SO 文档 60、Delivery Plan 2、Purchase Order 13、
Work Order 13、Bin 13。

## 2. 选样与覆盖（10 例）

| 例 | 段 | 状态 | 行数 | 覆盖标签 |
|---|---|---|---|---|
| E01 | C | Closed | 38 | both、dp |
| E02 | C | Cancelled | 63 | both、cancelled、lines50、no_dp |
| E03 | C | Cancelled | 63 | both、cancelled、lines50、no_dp |
| E04 | C | Closed | 103 | both、lines50、dp |
| E05 | C | Cancelled | 8 | neither、cancelled、no_dp |
| E06 | D | To Deliver and Bill | 1 | cover_only、no_dp |
| E07 | D | Closed | 77 | cover_only、lines50、no_dp |
| E08 | D | To Deliver and Bill | 24 | cover_only、dp |
| E09 | D | To Deliver and Bill | 1 | neither、no_dp |
| E10 | D | To Bill | 19 | neither、no_dp |

- 五类情形均覆盖：both（E01–E04）、cover_only（E06–E08）、cancelled（E02/E03/E05）、
  ≥50 行（E02–E04/E07）、有 DP（E01/E04/E08）与无 DP（其余）。
- D 段候选里没有 cancelled（脚本已记 note）；cancelled 由 C 段覆盖。
- **已取消单**：未履约量按 0 计，不产生建议（E02/E03/E05 的 net 全为 0）。

## 3. 每例输出字段（md/csv 一致）

每例含：SO 哈希、状态/docstatus、下单日、行项目（物料/数量/已交付/未履约/交期/仓）、
按仓库存、已知 PO/在产、配套规则、L15/L30/L60 净需求、L30 建议量与需要日、
假设与缺证项。CSV 一行一个 `target_item × SO line`（469 行），字段：
`example_id, segment, coverage, so_hash, so_status, so_docstatus, transaction_date,
line_idx, src_item, qty, delivered, unfulfilled, delivery_date, warehouse, target_item,
rule, qty_per, due_L15/30/60, stock, stock_status, po_L15/30/60, wo_L15/30/60,
net_L15/30/60, need_date, cancelled`。

## 4. 数据与规则落地

| 项 | 本轮做法 | 结果 |
|---|---|---|
| 库存 | EN `Bin.actual_qty`（同仓；只读） | 374 行有记录；**95 行无 Bin 记录 → “未取得”、净需求 null（不按 0）** |
| PO | `Purchase Order` + child filter（item_code in，status 未结） | 查询成功；有记录时按 `schedule_date` 落入 horizon |
| 在产 | `Work Order`（production_item in，status 未结） | 查询成功；按 `planned_end_date` 落入 horizon |
| 配套 | 本地 `bom`/`bom_item`：唯一 BOM 且含 PK#+ND# | 144 行 BOM 拆解；318 行直接物料；**7 行“规则未证”**（无唯一 BOM） |
| 净需求 | `max(0, due_H − 同仓库存 − 同仓 PO_due_H − WO_due_H)` | L30 有 49 行净需求 >0；95 行因库存未取得 → null |
| 建议 | 按 target 汇总 net_L30；需要日 = 最早交期（已过则今天） | 草稿，不提交 |

- 配套口径：`PK#`=皮壳、`ND#`=内胆；仅当 BOM 唯一且同时含两者时拆解，
  否则只对成品/直接物料给建议，写“规则未证”。
- 样本之间不共享库存预留；库存/PO/WO 均按**同仓**匹配，不跨仓。

## 5. 规则草图（计算顺序与证据）

```text
1) 需求：unfulfilled = max(0, qty − delivered)；已取消单=0
2) 时窗：due_H = unfulfilled if delivery_date <= today+H else 0，H ∈ {15,30,60}
3) 供给：stock_same_wh（EN Bin）、open_PO_due_H、open_WO_due_H（同物料/同仓，按日期）
4) 净需求：net_H = max(0, due_H − stock − PO − WO)
5) 配套：若 BOM 唯一且含 PK#+ND#：comp_due_H = due_H × qty_per，
   comp_net_H = max(0, comp_due_H − comp_stock − comp_PO/WO)；否则“规则未证”不拆
6) 建议：按 target 汇总 net_H；需要日 = 最早交期（已过则 today）
证据要求：库存记录、PO/WO 物料+数量+仓库+日期、BOM 唯一性与版本、库存快照时点。
首期只出草稿；人工审批后才可提交。
```

## 6. 能算到哪一步 / 缺什么

- **能算**：未履约量、EN Bin 同仓库存、已知 PO/在产（有日期者）、L15/L30/L60 净需求、
  BOM 唯一时的 PK#/ND# 配套建议、按需要日的草稿数量。
- **必须人工/补证**：PO 到货日与去重、在产完工日、BOM 唯一性/版本、库存快照时点、
  MOQ/包装/成本、跨仓调拨规则；缺这些时只能出“待补证”草稿。
- **不自动提交**：本轮只出建议草稿，不下单、不写单据。

## 7. 复现

```bash
uv run python docs/research/supply-chain/2026-10-20/claude/experiments/auto_order/order_examples.py
uv run python scripts/check_secrets.py   # 无 finding、退出码 0
```

- 凭证从 `EN_API/.env` 读取，不打印/不落盘；输出无客户名/原始明细，SO 用哈希 id。

## 8. 约束自检

| 约束 | 结果 |
|---|---|
| 只新增 `order_examples.py`、`order_examples.md/csv`（+ json 汇总）、本记录 | ✅ |
| 只读；无写入/下单/配置变更 | ✅ |
| ≤120 GET、单线程、200 ms、page_length ≤100 | ✅（103 次） |
| 超时/5xx 即停 | 代码已实现；本轮 0 错误 |
| 不提交原始明细；客户名不含；SO 哈希 | ✅ |
| 不改主表与既有产物；未改 control 受保护文件 | ✅ |
| 未 push；只提交自己新增文件 | ✅ |
| `check_secrets.py` 无 finding | ✅ |
| 不留临时文件（含 `__pycache__`） | ✅ |
