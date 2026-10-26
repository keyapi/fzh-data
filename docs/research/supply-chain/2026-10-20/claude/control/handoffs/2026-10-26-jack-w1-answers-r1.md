---
okf: v0.1
type: Handoff
title: Jack W1 首轮 8 问答复（2026-10-26）
date: 2026-10-26
owner: claude-foreman
channel: docs/jack-w1-channel
questions: PR #311 comment 2026-10-26T03:02:30Z
---

# Jack W1 首轮 8 问答复

> **本文件是 R1 的详细存档；当前有效结论速查见 [`JACK_QA.md`](JACK_QA.md)。**
> 对应 PR #311 里 `[W1-Q01]`–`[W1-Q08]`。本文件是正式答复；聊天里未进入本分支的内容不算。
> 行级 CSV/JSON 仍留本地；这里只写字段、口径、聚合计数与可复核路径。

## 0. 本轮先做的一件事：SC14 已扩阶段

`experiments/sc14/contract.py` 的 `STAGES` 已从 5 个扩为 **7 个**：

```
on_hand / po_open / in_production / shipped_in_transit / received
/ partially_received / unknown
```

`test_contract.py` 新增 5 条用例，现为 **21/21 passed**。规则见 Q01。

---

## [W1-Q01] 阶段枚举：更新 contract.py，还是只放 exceptions？

**结论：更新 `contract.py`；两个阶段都是一等公民，但都不进 confirmed/expected。**

已落地规则：

| 阶段 | 允许条件 | 汇总去向 |
|---|---|---|
| `partially_received` | **只用于分配未知的部分签收**：给 `received_qty / remaining_qty / doc_qty`，且三者满足 `received + remaining = doc_qty`；`qty=null + qty_status='unknown'`；`date_confidence='unknown' + available_date=null`；`allocation_unknown=true` 或 `allocation_known=false` | 只进 `supply_unknown` |
| `unknown` | 知道数量、但不知道处于哪一段（例如 DN 状态缺失）；`qty` 可以是 known；`date_confidence='unknown' + available_date=null` | 只进 `supply_unknown` |

补充：

- **分配已知的部分签收不要用 `partially_received`**，按 spec §2.2 拆成 `received` + `shipped_in_transit` 两行。
- `partially_received` 的 `qty` 必须是 `null`，不能用 40/60 猜一个数；`received_qty/remaining_qty` 是拆分证据，不是主表 `qty`。
- 新增错误码：`E_PARTIAL_ALLOCATION_REQUIRED`、`E_PARTIAL_QTY_UNKNOWN`、`E_PARTIAL_DATE_UNKNOWN`、`E_UNKNOWN_STAGE_DATE`。
- 你的 1 张部分签收 + 1 张状态未知可以进正式 supply 表（分别为 `partially_received` / `unknown`），不再只留在 `exceptions.csv`；但它们不增加 B_min。

## [W1-Q02] 本机没有 10-22 快照，实时库存对不上

**结论：正式 recon 用 sample10 的 10-22 冻结值；你本轮 10-26 实时库存只作 provisional，不得用于数量结论。**

事实：

- `stock_latest` 就是 **2026-10-22** 的完整批次（`stock_run` 10-22 完整、5,314 行）；
  DuckDB sha256 = `0919dd8c852df51ee085f1e9019c59c156bd3d3fb9d9465a798e7ac15fc53ca6`
  ——与 sample10 报告记录的输入 hash 一致。
- 10-22 关键值（sample10 §2/§3，可直接用作 recon 基准）：
  - `TT0031038K0062927`：波兰 157（待发 5）/ Wayfair 153 / 美中-DANEEY 40 + 在途 **201**
  - `C/Linen-Natural-100-688-wow`：美东-CENTRADE 21 + 在途 **121** / Wayfair 34
  - `TT0312701K0064561`：美东-CENTRADE 181 + 在途 **480**
  - `C/Cord-White-100-706-wow`：美东-CENTRADE 2 + 在途 **112**
  - `C/Velvet-White-100-664-wow`：两仓 0 / 在途 0
  - `TT0031010K0062880`：三仓 0 / 在途 0
  - `CEN1607NLinen-Ivory-194`：美中-DANEEY 224 / Wayfair 2
  - `CENKZ1323-LTGrey-97`：WayfairCG-Cranbury 17
  - `CENCord995-DKGrey-97`：美东-CENTRADE 1
- 你的实时值（TT0031038 在途 496、PL 146、C/Linen CENTRADE 20）是 **10-26** 的，晚 4 天，漂移正常。
  `snapshot_mismatch=true` 要保留；**不要用实时值去改 sample10 的 B_min/B_max**。

做法：

1. 正式 recon 用 10-22 值，逐数对齐；实时跑另存 `provisional_live`，不作为结论。
2. 不要把 DuckDB / 行级 CSV 放公开仓库；需要原始行时走私有通道或本地路径 + sha256。
3. 如果一定要用实时库存，标 `as_of=2026-10-26`，并说明无法与 10-22 样本逐数对齐。

## [W1-Q03] 多出 3 张开放 WO；produced_qty 与 JC 冲突

**结论：只把 `creation <= 2026-10-20` 的 WO 纳入本轮；冲突的 WO 不计供给，进 exceptions。**

- sample10 的 WO 快照是 **2026-10-20**；你多出的 3 张（`WO-26-03110` / `WO-26-03118` / `WO-26-03664`）
  先查 `creation` / `modified`：
  - `creation > 2026-10-20` → 标 `post_as_of_wo`，**不进本轮冻结 recon**；
  - `creation <= 2026-10-20` → 可进 `in_production`，但 `date_confidence=unknown`、`available_date=null`，只进 B_max/unknown，不进 confirmed。
- `WO-26-03110`：`produced_qty=0` 但 JC 首工序 `sum_qty=110 > qty=100`，是**数据冲突**，不是“还剩 100”。
  处理：`production_conflict=true`，**不计入 remaining 供给**，放 `exceptions.csv`，需 EN 侧核对 JC 归属/报工。
- 另外 2 张 Not Started（C/Cord-White 70、TT0031010 110）：可作 `remaining_estimated`，但不进 confirmed；
  它们是零库存样本的交叉标签，不改变 9 SKU 的冻结主类别。
- 口径沿用 #291：`WO.status/produced_qty` 不可信；JC 首工序完成量只作 `production_progress`，不跨工序求和。

## [W1-Q04] 少一条 PO021735

**结论：不是日期过滤，是 **status=4**。`PO021735` 在 10-19 导出里存在，但状态与 0 不同。**

本地 `tongtool_po` 事实：

| PO | SKU | 仓 | qty | open_qty | status | purchase_date |
|---|---|---|---:|---:|---|---|
| PO021717 | C/Cord-White | 美东-CENTRADE | 10 | 10 | `0` | 2026-09-09 09:22 |
| PO021733 | C/Cord-White | 美东-CENTRADE | 102 | 102 | `0` | 2026-10-12 16:15 |
| PO021735 | C/Cord-White | 美东-CENTRADE | 102 | 102 | **`4`** | 2026-10-13 16:26 |

- `purchase_date` 在 10-19 之前，**不是日期过滤问题**；`will_arrive_date` 仍为空。
- sample10 §6 记录：status 0=206 行 / 3=276 行 / 4=42 行；**本地无状态字典**，status 4 按 `open_qty>0` 暂记为未结，
  但 API 很可能把 4 当关闭/已处理，所以你的 `purchaseOrderQuery` 少返回这一条。
- 处理：
  1. 用 `ponum=PO021735` 单独查一次（不带日期/状态过滤）；能返回就保留 `po_status=4` + `po_status_semantics=unproven`。
  2. 仍查不到 → 标 `source_missing`，**不要写 0、不要删行**；冻结 recon 用 sample10 的 7 条 PO 总数，但 `PO021735` 只进 B_max，不进 B_min。
  3. 业务侧确认 status=4 的语义；确认前不得把它当已关闭。
- 这不是你代码的 bug；是状态码未映射。

## [W1-Q05] overlap_status 与 B_min/B_max

**结论：三条都按你当前做法，只补一条“单值必须标注”。**

1. **是**：`same_batch_suspected` = 同 `(sku, warehouse)`，`open_po_qty>0 ∧ intransit>0 ∧ open_po_qty == intransit`。
   它只是**数值嫌疑**；`same_batch_proven` 必须有 `batch_key`（PO 外部单号 / 运单号 / DN-PO 关联）。
2. **是**：B_min 只排除 `same_batch_suspected` 的 PO；B_max 全部保留。
   `unknown` **两边都保留**（没有证据说它是同批）；不要因为 `unknown` 就排除。
3. **可以**，但 `dedup_assumed` 只能是**第三列单值**，必须写 `dedup_assumed=true` + assumption 文本；
   不得作为唯一数字，也不得覆盖 B_min/B_max。
- 你本轮 201 PO vs 496 在途 → `unknown`，PO 进 B_min，正确；10-22 冻结值会回到 201=201 → `same_batch_suspected`。

## [W1-Q06] 映射全是 derived；PK# / 组件怎么标

**结论：9 个 SKU 的映射对已在 `sku_item` 里，可升 `proven`；但 **role 不能全部写 finished**。**

本地 `sku_item` 结果（sku, item_code, ship_type）：

| SKU | item_code | ship_type | 正确 role |
|---|---|---|---|
| `C/Cord-White-100-706-wow` | `KS0001-CMKTR-100-WHITE` | 皮壳 | `cover` |
| `C/Linen-Natural-100-688-wow` | `KS0001-XMMBS-100-HEMPNATURAL` | 皮壳 | `cover` |
| `C/Velvet-White-100-664-wow` | `KS0001-PR-100-WHITE` | 皮壳 | `cover` |
| `CEN1607NLinen-Ivory-194` | `KS0001-DM-194-IVORY` | 皮壳 | `cover` |
| `CENCord995-DKGrey-97` | `KS0001-QDKTR-100-DEEPGREY` | 皮壳 | `cover` |
| `CENKZ1323-LTGrey-97` | `KS0001-DM-100-GREY` | 皮壳 | `cover` |
| `TT0031010K0062880` | `KS0121-KQC-194-WHITE` | 成品 | `finished` |
| `TT0031038K0062927` | `KS0156-NYBDSFH-52x52x5-BLACK` | 成品 | `finished` |
| `TT0312701K0064561` | `ZTGJ5525-SOFALSHAPEDBRACKET-IRON-55x45x45` | （空） | `component` |

规则：

- `identity_confidence=proven` 只表示**这个 sku↔item_code 对**在 `sku_item` 里；**不等于它是成品**。
  `role` 由 `ship_type` 决定：皮壳→`cover`，成品→`finished`，空/支架→`component`。
- `CENCord995`：成品行与 `PK#KS0001-QDKTR-100-DEEPGREY` 皮壳行分开；WO 产的是皮壳，**不能 1:1 当成品供给**。
- `TT0312701` 是主体骨架组件，不是成品；不要放到 `finished`。
- `scope` 只表示 `in_house / external_fba`；**不要**新增 `scope=component`。组件用 `role=component` 表达，维度不要混。
- `parent_sku`：能由 `bom_exploded` 证明就填；不能就 null + `allocation_unknown=true`，不要强并。
- `E_REQUIRED_NULL` 必须保持 0；组件行不能丢，用 `role`/`parent_sku` 显式隔离。
- 需要原始 `sku_item`/`bom_exploded` 行，走私有通道；上表是 9 个 SKU 的权威映射。

## [W1-Q07] 6 个仓的 scope / confidence

**结论（2026-10-26 更正）：可以相加，前提是同一批货没有被重复报两次。**
上一版写的“`FZH-DANEEY-成品仓/半成品仓` 不能与主仓相加”**说过头了**，更正如下。

先把 `component->main` 说清楚：它是我们**本地 `warehouse_map` 的清洗/改名标签**（GS 仓库名 → 当前通途仓名），
**不是业务规则**。它可能表示旧名已并入主仓，也可能是历史遗留名；不能据此断言“子池不能加”。

### 6 个仓

| 仓库 | `warehouse_scope` | `warehouse_confidence` | 依据 / 备注 |
|---|---|---|---|
| `美东-CENTRADE` | `3pl` | `confirmed` | `warehouse_map`: CENTRADE → 美东-CENTRADE (renamed)；status=1；有 `warehouse_id` |
| `美中-FZH-DANEEY` | `3pl` | `confirmed` | `warehouse_map`: FZH-DANEEY → 美中-FZH-DANEEY (renamed)；status=1；有 `warehouse_id` |
| `波兰-FZHPoland-covers` | `own` | `assumed` | `FZHPoland-finished → 波兰-FZHPoland-covers`；status=1；归属未证 |
| `WayfairCG-Cranbury仓` | `3pl` | `assumed` | `current`；归属未证 |
| `FZH-DANEEY-成品仓` | `3pl` | `assumed` / `inactive` | `component->main` 只是改名提示；status=0；`stock_history` **无 warehouse_id**；9 SKU 快照 0 |
| `FZH-DANEEY-半成品仓` | `3pl` | `assumed` / `inactive` | 同上；9 SKU 快照 0 |

### 加总规则（按优先级）

1. **同一物理仓只算一次**：同一 `warehouse_id`、或明确是旧名/别名的，不重复加。
2. **不同 `warehouse_id`、且不是同一批货的重复上报 → 可以相加**（作为不同库位）。
   不要因为名字不同就拒绝相加；也不要因为 `component->main` 标签就禁止相加。
3. **停用仓（status=0）有库存时保留行**，标 `warehouse_status=inactive`；是否计入主供给，
   看它是否与主仓重复（同 SKU、同量、同快照）——重复就不加，独立就加。
4. **3PL / 自有**用于归属与可见性分列，不等于不能加。只要都是我方拥有、同一 SKU、同一 UOM、
   未被重复上报，就可以加；跨 UOM（个/套）仍不合计。
5. **皮壳 / 半成品 / 成品**：通途面向销售平台，历史上不严格区分；**仓库名不能当 stage 真值**。
   用 EN `sku_item.ship_type` + 运营填的客户物料号判断角色。皮壳/半成品在海外分公司可**填充压缩后发成品**，
   所以它们是**可用供给**；但要标 `conversion_assumed=true`（默认 1:1 只是假设，未证）。
   - B_min：只放**转换已证**的数量；
   - B_max：可放**转换假设**的数量，并注明 `conversion_assumed=true`。
6. 样本事实：`TT0031010` 在 `FZH-DANEEY-成品仓/半成品仓/美中-FZH-DANEEY` 三处都是 **0**；
   `TT0031038` 在 `FZH-DANEEY-成品仓` 是 **0**、主仓是 40 + 在途 201。
   所以这批样本加不加都不变；但规则不能再写成“永远不能加”。

### 口径提醒

- SC09 的 `supply_own_*` 里 “own” 指我方拥有的库存（含 3PL 中我方货），FBA 另列；
  `warehouse_scope` 是另一维，不能替代 `scope`。
- 如果同一 SKU 在主仓和子仓都出现非零，先做**重复上报检查**（同量、同快照、同 ID/别名），再决定加不加；
  不确定就出“加/不加”两个情景，不要单值。

## [W1-Q08] received 全是 evidenced、qty=null

**结论：可接受；分 `received_booked` 与 `received_evidenced` 两列；9 SKU 覆盖 8/39 DN 是预期。**

1. `received_evidenced` 数量保持 `null + qty_status='unknown'` **可接受**；它只进 `supply_unknown`，不进 confirmed/expected，也不写 0。
   有签收节点时 `date_confidence=confirmed` + `date_proof=shipment.signed`；数量仍可 null。
2. **建议**主表之外单独输出：
   - `received_booked.csv`：Stock Entry 实收（本轮 0，正常，3PL 不落 EN）；
   - `exceptions.csv`：状态冲突、无父 SKU、仓库未映射等；
   - `sc04_recon.json`：与 SC04 的 39 DN / 47 号 / 4,279 行逐阶段对账。
   主表可保留 `stage=received` 的 evidenced 行，但不要与 booked 混算。
3. **是预期**：9 SKU 样本只覆盖 8/39 DN、1,516/4,279 行；SC04 的 6 张已收 DN 里只有 1 张（DN-26-00067）在样本内。
   recon 只比较重叠 DN；其余 31 张是 out-of-sample，不要声称 39/39。
- `received_booked=0` 不等于 received=0；缺 Stock Entry 是 3PL 的记账现实，不是业务事实。

---

## 本轮硬指标对照

| 项 | 你的结果 | 结论 |
|---|---|---|
| SC14 | 0 error / 136 warning；16/16 | 升级为 **21/21**；warning 是 UOM 未证，正常 |
| SC04 对账 | 39 DN / 47 号 / 4,279 行 / 5 阶段 / FBA 17，全差 0 | 通过 |
| W1 | 236 supply 行；B_min 2,645+533；B_max 3,358+533 | 仅作 provisional（实时库存）；正式 recon 用 10-22 |
| 9 SKU 覆盖 | 8 DN / 8 号 / 1,516 行（6 在途、1 已收、1 未知） | 符合 9 SKU 样本预期，不是 39/39 |

## 下一步（按顺序）

1. 拉最新分支：`git fetch origin && git switch docs/jack-w1-channel && git pull`；跑 `experiments/sc14/test_contract.py`，确认 21/21。
2. 用 10-22 冻结值重算正式 recon；实时 10-26 另存 `provisional_live`。
3. WO：先按 `creation <= 2026-10-20` 过滤；`WO-26-03110` 标 `production_conflict`，不计供给。
4. PO021735：按 PO 号单查；查不到标 `source_missing`，只进 B_max。
5. 映射：按上表把 6 个皮壳改 `role=cover`、TT0312701 改 `component`、2 个成品保持 `finished`；`identity_confidence=proven`（基于 `sku_item`）。
6. 仓库：按上表填 `warehouse_scope`/`confidence`；**不同 `warehouse_id` 且未重复上报的可以相加**；同 ID/别名/同量重复只算一次；皮壳/半成品的转换标 `conversion_assumed`（B_min 只放已证，B_max 可放假设）。
7. received：分 `received_booked` / `received_evidenced`；主表不混算。
8. 开 `feature/jack-supply-timeline` draft PR；把本文件的 8 个结论跑成计数，贴 PR 评论。
