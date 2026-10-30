---
okf: v0.1
type: Spec
title: 第四步：最终物流状态裁决（双线 + 事件 + 阶段）
date: 2026-10-29
updated: 2026-10-30
owner: claude-worker
status: implemented locally (Codex rework); test-station re-verification pending; production not deployed
scope: read-only; no business data writes; no permission changes
tags: [supply-chain, shipment, logistics, evidence, adjudication]
---

# 第四步：最终物流状态裁决

## 1. 输入（双线 + 事件，原值全部保留）

每条进度证据保留：

`raw_status`、`normalized_status`、`effective_status`、`event_kind`
（actual/estimated/raw_event）、`event_at`、`source_updated_at`、`source`、
`source_record`、`timezone_status`、`line`、`granularity`、`vote`、
`normalization`、`unmapped_manual`。

Shipment 适配器来源（三类，缺一不可）：

- `custom_zmt_status11`（爬虫实际线，fine）→ `line=status11`；
- `custom_zmt_status4`（人工粗线，coarse）→ `line=status4`；
- `Shipment Logistics Event` 子表（`seq/event_time/event_name/event_date/description`）
  → `line=event`；描述命中 ETA/预计 → estimated，其余按事件映射；无法映射的事件保留
  raw、`vote=false`，只进入候选；
- `custom_zmt_atd/ata/dlvr`（实际节点）→ `carrier_field`；
- `custom_zmt_eta`（预计）→ `carrier_eta`；
- `modified` → `source_updated_at`。

### 1.1 人工状态 normalization map（显式、可审计）

版本：`status4-manual/v1`。只映射语义已证的值；其余保留 raw 并冲突化。

```text
在途→运输中  到港→已到港  离港→已离港  签收→已签收
STATUS_ORDER 内的规范值保持恒等
```

- 未命中的值（例如 `待发`）：`normalized_status=null`、`vote=false`，裁决输出
  `manual_status_unmapped` 冲突原因，交人工复核；不得猜测成“已入仓”。
- `status4` 非终态只在**没有** status11/事件等 fine actual 证据时投票；否则仅作佐证，
  避免粗粒度 `在途` 把细粒度 `已离港` 顶成 `运输中`。
- `status4` 终态（签收/POD）仍参与终态粘性；与 status11 矛盾时输出终态 + conflict。

### 1.2 事件映射

版本：`event-logistics/v1`。先做精确匹配，再做唯一 token 匹配；多 token 命中或未知描述
不投票、保留 raw。`ETA`/`预计` 只进入预计证据，事件时间不等于 ETA 日期，不据此伪造。

## 2. 裁决优先级

1. 有效实际终态（`已签收` / `已上传POD` / `已完结`）粘性最高；
2. 实际事件优先于预计事件；
3. 非终态按物流阶段顺序比较（订舱→入仓→装柜→报关→离港→运输→到港→清关→转运→派送）；
4. `event_at` 只用于同一阶段内选择更晚的实际事件；
5. `source_updated_at` 只用于同来源、同事件的修订，**不能提升物流阶段**。

冲突/异常/撤销/退回/修正/缺时间/同时间不同载荷/阶段回退/人工值未映射
→ `unknown` 或带 `conflict_flag` 的结果，保留全部候选原值。

关键语义（本轮复审修正）：

- **阶段回退**（后发生的更早阶段事件）→ `latest_progress_status=null` + `stage_regression`，
  不再输出确定阶段；
- **终态缺 `dlvr`** → `latest_progress_at=null`（`shipment_signed_at` 随之为 null），
  **不得**用 `ata` 冒充签收时间；事件行里的签收事件时间是合法证据；
- **ETA-only** → `latest_progress_kind=estimated`，`classify_stage` 返回 `unknown`，
  不得证明实际 `shipped_in_transit`；
- 多套 ETA → 全部保留 + `eta_conflict`，不自动选一个当实际；
- 同一物流号命中多条 Shipment → `shipment_identity_conflict`，禁止 last-write-wins。

## 3. 输出

`latest_progress_status`、`latest_progress_at`、`latest_progress_kind`、
`progress_source`、`is_final`、`conflict_flag`、`conflict_reasons`、
`progress_candidates`（含 status11、status4、事件原值）。

`shipment_progress` 行另带 `status4_normalized`、`status4_normalization`、
`identity_conflict`、`shipment_candidates`；同一 DN/物流号/Shipment 去重，退货 DN 不生成
进度行。

## 4. 阶段修正（相对 STEP1）

- 到港/清关/转运/派送仍属于 **运输过程**（`shipped_in_transit`），但 only when actual；
- 只有实际已签收/POD 才进入 `signed_pending_tongtool_receipt`；
- 多 Shipment 的 DN：
  - 全部签收 → DN 阶段为待通途入库，但每条 Shipment 不得复制 DN 数量；
  - 部分签收/部分在途/部分状态未知 → 保守留在途，并标注分配未知；
  - 任一冲突 → `unknown`；
- 同号多 Shipment → `unknown + shipment_identity_conflict`。

## 5. 必测反例（`key_test/tests/test_shipment_progress.py`）

- 昨天签收 + 今天人工在途 → 签收、final、conflict；
- `status4=签收` + `status11=已离港` → 签收、final、conflict；
- `status4=在途` 有 status11 时不投票；无 status11 时才作为唯一证据投票；
- `status4=待发`（未映射）→ raw 保留 + `manual_status_unmapped`；
- 事件 `已到港` 参与实际候选；未知事件保留 raw 且不投票；
- 后录入开船 + 已签收 → 签收；
- 晚 ETA + 已发生实际节点 → 实际节点；ETA-only → unknown；
- 两套 ETA → `eta_conflict`；
- 同阶段两条实际 → event_at 更晚者；
- 同时间冲突、异常/撤销、缺时间、阶段回退 → unknown/conflict；
- 终态无 dlvr → `latest_progress_at=null`；
- 输入顺序互换 → 稳定。

`key_test/tests/test_supply_facts.py` 另覆盖：同 DN 多明细/退货去重、同号多 Shipment
identity conflict、ETA-only 阶段 unknown、终态无 dlvr `shipment_signed_at=null`。

## 6. 仍为 unknown

- `custom_zmt_status4` 的业务字典未完整证实；只有上表列出的值被映射；
- Shipment 日期字段时区未证（`timezone_status=unverified`），仅按日期排序，不升级为精确时刻；
- 两套 ETA 冲突保留原值，不自动选一个当实际；
- `status=4`、`warehousingNum`（本次/累计）、稳定行身份继续 unknown。
