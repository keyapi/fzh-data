---
okf: v0.1
type: Review
title: SC04 供应阶段守恒：PO→WO→DN→运输→接收，一货一阶段
date: 2026-10-23
owner: claude-worker-2
status: 完成；39 张 DN 各归一个阶段，对账闭合；未改 forward_net
basis: 复用 59c4e5ec 的 DN 桥 + dn_status（未重复查生产）
artifacts:
  - experiments/sc04/sc04_supply_stage.py
  - out/business_phase/sc04/sc04_supply_stage.csv   (39 行，每 DN 一阶段)
  - out/business_phase/sc04/sc04_supply_lines.csv   (4,279 行，本地)
  - out/business_phase/sc04/sc04_supply.json
---

# SC04 供应阶段守恒

> **一句话**：该链的前两段（**PO / WO**）在本地**没有任何证据**（forward_net 里 `wo_status`
> 全部 `not_observed`），所以本轮**不假设**它们；有证据的是**DN → 运输 → 接收**三段。
> 39 张 DN **每张只归一个阶段**，同一批货不会既算在途又算在手；对账 39 / 47 / 4,279 全部闭合。

## 0. 摘要

| 阶段 | 含义 | DN | 运单号 | 物料行 |
|---|---|---:|---:|---:|
| `received_before_snapshot` | 已签收/入仓 且 签收日 ≤ 2026-10-20 → **已在手，不再计在途** | **6** | 10 | 854 |
| `received_unknown_date` | 已签收/入仓 但**无签收日期** | **1** | 1 | 41 |
| `in_transit` | 全部为在途节点（订舱/报关/离港/转运/到港/清关） | **30** | 30 | 2,763 |
| `partially_received` | 多号 DN **部分签收**（分配未知） | **1** | 5 | 452 |
| `unknown_status` | 状态缺失 / 未匹配 | **1** | 1 | 169 |
| 合计 | | **39** | **47** | **4,279** |

- **范围**：22 张属我方追踪仓（DANEEY / CENTRADE / 波兰），17 张属**外部 FBA**。
  `DN-26-00062`（FBA，已签收）**既不算我方在手、也不算我方在途**——货已出我方控制。
- **PO / WO**：本地无证据 → 本表**不出现**这两个阶段，也不把"没有 WO 记录"当成"没有在制"。

## 1. 阶段定义与「只计一次」规则

| 规则 | 实现 |
|---|---|
| **一张 DN 只进一个阶段** | 按状态优先级判定（未知 > 全签收 > 全在途 > 部分），互斥 |
| **已签收且 ≤ cutoff 的不再计在途** | `received_before_snapshot` 行 `count_once_rule = 不计在途（已在手）` |
| **外部 FBA 的已签收货两边都不计** | `stock_scope=external_fba` 的已签收行 → 「不计在途/在手」 |
| **多号部分签收不摊** | `partially_received` 保留 `allocation=分配未知`，不给分号数量 |
| **同批可疑不折算** | 前向账 `S_*_same_batch / diff_batch` 情景里的到货属"疑似同批"，本表**保留并列**，不并入在途 |

去重键（供下游）：**`batch_id(DN) + item_code + uom`**。

## 2. 阶段分布与数量向量（分 UOM，不合计）

| 阶段 | DN | 个 | 套 |
|---|---:|---:|---:|
| `received_before_snapshot` | 6 | 11,177 | 0 |
| `received_unknown_date` | 1 | 1,682 | 580 |
| `in_transit` | 30 | 61,487 | 30,701 |
| `partially_received` | 1 | 1,475 | 0 |
| `unknown_status` | 1 | 1,515 | 18,154 |

> 个与套**不相加**（不同单位）。同一 DN 的物料按 `(item_code, uom)` 保留向量，行级见 `sc04_supply_lines.csv`。

## 3. 未知分布（不静默）

| 未知类型 | 对象 | 说明 |
|---|---|---|
| **状态缺失** | `DN-26-00112`（CENTRADE，19,669 件，含 18,154 套） | 运单号 `Unmatched`、`status11` 为空 → 阶段 unknown，**不猜在途也不猜已到** |
| **无签收日期** | `DN-26-00100`（波兰，2,262 件） | 状态 `已入仓` 但无 `dlvr` → 无法与快照比较 |
| **部分签收** | `DN-26-00069`（FBA，1,475 件） | 5 号中 1 已上传 POD、1 已清关、3 已离港 → 到货分配未知 |
| **外部不可追踪** | 17 张 FBA DN | 目的仓不在本地任何库存口径 |

## 4. 到货时间：只认已证节点

| 项 | 结果 |
|---|---|
| 已证到货（`proven_arrival_date`） | **6** 张（用实际 `dlvr`） |
| 在途但**无** ETA | **2** 张 |
| 在途**有** ETA（`eta_unproven`，仅供敏感性） | **28** 张 |
| **ETA 已过期**（在途却 ETA < 2026-10-20） | **4** 张：`DN-26-00065`(10-15)、`00066`(10-06)、`00087`(10-13)、`00088-1`(10-18) |
| 证据等级 | `E1_node_proven` **27** ／ `E2_status_only` **11** ／ `E3_unknown` **1** |

- **在途一律不给"可用日"**：`proven_arrival_date` 对在途为空；ETA 单列在 `eta_unproven`，
  **不默认及时到货**——这 4 张过期 ETA 就是最直接的证据：按 ETA 它们早该到了。

## 5. 与 SC02 前向账对齐的字段建议（**本轮不改 forward_net**）

建议 forward_net 的供给侧接受如下行（每行 = 一个批次×物料×单位）：

| 字段 | 类型 | 取值 / 说明 |
|---|---|---|
| `stage` | enum | `received_before_snapshot` / `received_unknown_date` / `received_after_snapshot` / `in_transit` / `partially_received` / `unknown_status` |
| `batch_id` | string | DN 单号（去重键第一段） |
| `item_code` | string | EN 物料码（与 BOM/映射同键） |
| `uom` | string | **必带**；跨 UOM 不得合并 |
| `qty` | number | 该 (batch,item,uom) 的数量 |
| `proven_arrival_date` | date\|null | **只有 received_\*** 才给；在途恒为 null |
| `eta_unproven` | date\|null | 承运商 ETA；**不得**当可用日 |
| `evidence_level` | enum | `E1_node_proven` / `E2_status_only` / `E3_unknown` |
| `dedupe_key` | string | `batch_id + item_code + uom` |

**兼容性说明**：forward_net 现在用 `wo_qty/wo_status`（全 `not_observed`）与 receipts 情景（0/129/258）；
本建议**不改变其计算**，只提供可被其消费的字段形状。本轮**未修改** `forward_net.py` 与 `forward_net_rows.csv`。

## 6. 对账（入 N → 出 M，差额为零）

| 口径 | 入 | 出 | 差额 |
|---|---:|---:|---:|
| 运单号 → 阶段 | **47** | 10+1+30+5+1 = **47** | **0** |
| DN → 阶段 | **39** | 6+1+30+1+1 = **39** | **0** |
| 物料行 → 阶段 | **4,279** | 854+41+2,763+452+169 = **4,279** | **0** |

（`reconciliation.ok = true`，见 `sc04_supply.json`。）

## 7. 必须上报的一个发现（未修）

`dn_split.py` 的 `route_state` 在状态为空字符串时会被判成"已签收/已入仓"：
`all(s in SIGNED for s in statuses if s)` 在 `statuses = ['']` 时对空序列求值为 `True`。
结果：**`DN-26-00112`（19,669 件）在 `dn_split_dn.csv` 里被标成"已签收/已入仓"**，
而它实际是 `Unmatched`、状态全空。

- 本轮 **SC04 没有继承这个字段**，而是直接用 `dn_status_recon.csv` 的原始 `status11` 重新判阶段，
  因此 00112 在本表是 `unknown_status`。
- **我没有修改 `dn_split.py`**（那是已 PASS 的 59c4e5ec 产物）；请工头决定是否开一张单点返修。

## 8. 边界

1. 只读；复用本地 DN/Shipment 证据，未重复查生产；未改 forward_net；不出补货量。
2. **PO / WO 无证据**：不能据此说"没有在途 PO"或"没有在制"。
3. 到货时间只认已证节点；ETA 未证的单列，且已发现 4 张 ETA 过期。
4. 多号 DN 分配未知；外部 FBA 不可追踪；跨 UOM 不合计。
5. 覆盖仅 8/1 后 39 张有号 DN；8/1 前 803 张未覆盖。

## 9. 复现

```bash
uv run python docs/research/supply-chain/2026-10-20/claude/experiments/sc04/sc04_supply_stage.py
```

- 只读 4 个本地 CSV；无生产访问、无预测。耗时 < 1 s。
