---
okf: v0.1
type: Spec
title: 第四步：最终物流状态裁决（证据等级 + 物流阶段）
date: 2026-10-29
updated: 2026-10-29
owner: claude-worker
status: implemented; test-station read-only acceptance pending restart; production not deployed
scope: read-only; no business data writes; no permission changes
tags: [supply-chain, shipment, logistics, evidence, adjudication]
---

# 第四步：最终物流状态裁决

## 1. 输入（原值保留）

每条进度证据保留：

`raw_status`、`normalized_status`、`event_kind`（actual/estimated）、`event_at`、
`source_updated_at`、`source`、`source_record`、`timezone_status`。

Shipment 适配器来源：

- `custom_zmt_status11`（爬虫实际线）→ `carrier_status`；
- `custom_zmt_atd/ata/dlvr`（实际节点）→ `carrier_field`；
- `custom_zmt_eta`（预计）→ `carrier_eta`；
- `modified` → `source_updated_at`。

## 2. 裁决优先级

1. 有效实际终态（`已签收` / `已上传POD` / `已完结`）粘性最高；
2. 实际事件优先于预计事件；
3. 非终态按物流阶段顺序比较（订舱→入仓→装柜→报关→离港→运输→到港→清关→转运→派送）；
4. `event_at` 只用于同一阶段内选择更晚的实际事件；
5. `source_updated_at` 只用于同来源、同事件的修订，**不能提升物流阶段**。

冲突/异常/撤销/退回/修正/缺时间/同时间不同载荷/阶段回退 → `unknown` + `conflict_flag`，
保留全部候选原值，不强行排序。

## 3. 输出

`latest_progress_status`、`latest_progress_at`、`progress_source`、`is_final`、
`conflict_flag`、`conflict_reasons`、`progress_candidates`。

## 4. 阶段修正（相对 STEP1）

- 到港/清关/转运/派送仍属于 **运输过程**（`shipped_in_transit`）；
- 只有已签收/POD 才进入 `signed_pending_tongtool_receipt`；
- 多 Shipment 的 DN：
  - 全部签收 → DN 阶段为待通途入库，但每条 Shipment 不得复制 DN 数量；
  - 部分签收/部分在途/部分状态未知 → 保守留在途，并标注分配未知；
  - 冲突 → `unknown`。

## 5. 必测反例（已由 `key_test/tests/test_shipment_progress.py` 覆盖）

- 昨天签收 + 今天人工在途 → 签收、final、conflict；
- 后录入开船 + 已签收 → 签收；
- 晚 ETA + 已发生实际节点 → 实际节点；
- 同阶段两条实际 → event_at 更晚者；
- 同时间冲突、异常/撤销、缺时间、输入顺序互换 → 稳定且冲突可见。

## 6. 仍为 unknown

- `custom_zmt_status4` 语义未证（`status_semantics=unproven`），不据此关闭/作废/进入已证下限；
- Shipment 日期字段时区未证（`timezone_status=unverified`），仅按日期排序，不升级为精确时刻；
- 两套 ETA 冲突保留原值，不自动选一个当实际。
