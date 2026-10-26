---
okf: v0.1
type: Handoff
title: Jack W1 唯一问答日志
date: 2026-10-26
owner: claude-foreman
channel: docs/jack-w1-channel
---

# Jack W1 唯一问答日志

> **这是 Jack 的唯一问答日志。** 当前有效结论在 §1；每轮详细答复在 §2。
> 新答复只追加到本文件；PR 评论只发短指针。以本文件为准，不要从 commit/评论里找口径。

## 1. 当前有效结论（速查）

| ID | 结论 |
|---|---|
| **Q01 阶段** | `contract.py` 已扩为 **7 阶段**：`on_hand / po_open / in_production / shipped_in_transit / received / partially_received / unknown`。`partially_received` **只用于分配未知**：给 `received_qty/remaining_qty/doc_qty`（和=总量），`qty=null + qty_status='unknown'`、日期 unknown；只进 `supply_unknown`。分配已知 → 拆 `received + shipped_in_transit`。`unknown` 可带 known qty，但日期必须 unknown；只进 `supply_unknown`。**21/21 passed。** |
| **Q02 库存基准** | 正式 recon 用 **sample10 的 10-22 冻结值**（`stock_latest`，DuckDB sha `0919dd8c…`）。10-26 实时只作 `provisional_live`，标 `snapshot_mismatch=true`，不得用于 B_min/B_max。 |
| **Q03 WO** | 只纳入 `creation <= 2026-10-20` 的 WO。`WO-26-03110`：`produced_qty=0` vs JC 首工序 `sum_qty=110 > qty=100` = **数据冲突**，标 `production_conflict`、**不计供给**、进 exceptions。 |
| **Q04 PO021735** | 不是日期问题，是 **status=`4`**（另两条 `0`）。按 PO 号单查；查不到标 `source_missing`，不写 0；冻结 recon 只放 B_max。 |
| **Q05 overlap** | `same_batch_suspected` = 同 `(sku, warehouse)` 且 `open_po_qty == intransit`（只是嫌疑）；`proven` 需 `batch_key`。B_min 只排除 `suspected`，B_max 全保留；`unknown` 两边都保留。`dedup_assumed` 单值可加但必须标注。 |
| **Q06 映射角色** | 9 个 SKU 的映射对在 `sku_item`，可升 `proven`；但 **6 个皮壳 → `cover`**（C/Cord-White、C/Linen、C/Velvet、CEN1607、CENCord995、CENKZ1323），**2 个成品 → `finished`**（TT0031010、TT0031038），**TT0312701 → `component`**。`scope` 仍只表示 `in_house/external_fba`，不要加 `scope=component`。 |
| **Q07 仓库** | **可以相加**：不同 `warehouse_id` 且未重复上报即可加；同 ID/别名/同量重复只算一次。`component->main` 只是本地 `warehouse_map` 清洗标签，**不是业务规则**。`FZH-DANEEY-成品仓/半成品仓` status=0、`stock_history` 无 `warehouse_id`、9 SKU 快照 0。皮壳/半成品经海外分公司填充压缩后可发成品 → 算可用供给，但标 `conversion_assumed=true`；B_min 只放已证转换，B_max 可放假设。 |
| **Q08 received** | `received_evidenced` 保持 `qty=null + qty_status='unknown'` 可接受，只进 `supply_unknown`；分 `received_booked`（Stock Entry）与 `received_evidenced`（签收）。9 SKU 覆盖 8/39 DN、1,516/4,279 行是预期，不是 39/39。 |

## 2. 轮次记录（只追加）

| 轮次 | 日期 | 内容 | 详细答复 |
|---|---|---|---|
| R1 | 2026-10-26 | Q01–Q08 首轮；SC14 扩 7 阶段、21/21 | [`2026-10-26-jack-w1-answers-r1.md`](2026-10-26-jack-w1-answers-r1.md) |

### R1 更正记录

| 日期 | 更正 | 说明 |
|---|---|---|
| 2026-10-26 | **Q07** | 上一版“`FZH-DANEEY-成品仓/半成品仓` 不能与主仓相加”**说过头了**。更正为：不同 `warehouse_id` 且未重复上报**可以相加**；`component->main` 只是本地映射清洗标签。 |

## 3. 更早的问答（归档）

| 日期 | 内容 | 文档 |
|---|---|---|
| 2026-10-23 | 第一轮七问（PO/在途、WO、海外入库、SKU 映射、仓库、PO ETA、本地数据） | [`2026-10-23-jack-w1-answers.md`](2026-10-23-jack-w1-answers.md) |

## 4. 提问格式

```text
[W1-Q09] 2026-10-27
问题：……
证据：文件/行/命令输出
影响：字段/阶段/验收
```

- 发在 PR #311 评论，或你自己的 `feature/jack-supply-timeline` PR 评论。
- 答复追加到本文件 §2；PR 评论只发「已答复，见 JACK_QA.md 第 N 条」。
- 公开侧不放行级 CSV/JSON；行级路径 + sha256 走本地或私有通道。
