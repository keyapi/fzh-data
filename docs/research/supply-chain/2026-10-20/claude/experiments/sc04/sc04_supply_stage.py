#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""SC04 供应阶段守恒（只读，复用已接入的 DN + Shipment 证据）。

回答：**某批货现在处于哪个阶段、何时可用**；并且**同一批货只计一次**。

数据（全部已在本地，不再重复查生产）：
  out/business_phase/dn_bridge_rows.csv   47 个运单号 ↔ DN
  out/business_phase/dn_status_recon.csv  每号：status11 / atd / ata / dlvr / eta / match_status / 节点数
  out/business_phase/dn_split_dn.csv      39 张 DN：目的仓、库存归属候选
  out/business_phase/dn_split_lines.csv   4,279 行物料（item_code / qty / uom）

阶段（互斥，每张 DN 恰好一个）：
  received_before_snapshot  已签收/已入仓 且 签收日 ≤ CUTOFF(2026-10-20) -> 已在手，**不再计在途**
  received_unknown_date     已签收/已入仓 但无签收日期
  in_transit                全部为在途节点（订舱/报关/离港/转运/到港/清关）
  partially_received        多号 DN 部分签收（分配未知）
  unknown_status            状态缺失或未匹配

到货时间只认**已证节点**：received_* 用实际 `dlvr`；in_transit 一律不给可用日，
ETA 单列在 `eta_unproven`，**不默认及时到货**。

红线：只读；不改 forward_net；不出补货量；跨 UOM 不合计。

输出：
  out/business_phase/sc04/sc04_supply_stage.csv   (39 行 / 每 DN 一阶段)
  out/business_phase/sc04/sc04_supply_lines.csv   (4,279 行，行级本地)
  out/business_phase/sc04/sc04_supply.json        (阶段/未知分布 + 对账 + 字段建议)
"""
from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

BP = Path(__file__).resolve().parents[2] / "out" / "business_phase"
OUT = BP / "sc04"
OUT.mkdir(parents=True, exist_ok=True)
CUTOFF = "2026-10-20"
SIGNED = {"已入仓", "已签收", "已上传POD"}
TRANSIT = {"已订舱", "已报关", "已离港", "已转运", "已到港", "清关中", "已清关"}


def main() -> None:
    bridge = list(csv.DictReader((BP / "dn_bridge_rows.csv").open(encoding="utf-8-sig", newline="")))
    recon = {r["logistic_number"]: r for r in csv.DictReader(
        (BP / "dn_status_recon.csv").open(encoding="utf-8-sig", newline=""))}
    split_dn = {r["dn"]: r for r in csv.DictReader(
        (BP / "dn_split_dn.csv").open(encoding="utf-8-sig", newline=""))}
    lines = list(csv.DictReader((BP / "dn_split_lines.csv").open(encoding="utf-8-sig", newline="")))

    by_dn = defaultdict(list)
    for r in bridge:
        by_dn[r["dn"]].append(r["logistic_number"])

    stage_rows = []
    for dn, numbers in sorted(by_dn.items()):
        recs = [recon.get(n, {}) for n in numbers]
        st = [(r.get("status11") or "").strip() for r in recs]
        dlvr = sorted(r["dlvr"] for r in recs if r.get("dlvr"))
        etas = sorted(r["eta"] for r in recs if r.get("eta"))
        atd = sorted(r["atd"] for r in recs if r.get("atd"))

        if any(s not in SIGNED | TRANSIT for s in st):          # 含空/未知
            stage, reason = "unknown_status", "状态缺失或未匹配"
        elif all(s in SIGNED for s in st):
            if not dlvr:
                stage, reason = "received_unknown_date", "已签收/入仓但无签收日期"
            elif max(dlvr) <= CUTOFF:
                stage, reason = "received_before_snapshot", "签收日 ≤ 快照日，已在手"
            else:
                stage, reason = "received_after_snapshot", "签收日晚于快照日"
        elif all(s in TRANSIT for s in st):
            stage, reason = "in_transit", "全部为在途节点"
        else:
            stage, reason = "partially_received", "多号部分签收，分配未知"

        # 证据等级
        if stage.startswith("received"):
            ev = "E1_node_proven" if dlvr else "E2_status_only"
        elif stage == "in_transit":
            ev = "E1_node_proven" if atd else "E2_status_only"
        elif stage == "partially_received":
            ev = "E2_status_only"
        else:
            ev = "E3_unknown"

        dest = split_dn.get(dn, {}).get("dest", "")
        scope = "external_fba" if dest == "美国FBA仓" else "tracked"
        stage_rows.append(dict(
            dn=dn, n_numbers=len(numbers),
            stock_scope=scope,
            statuses="|".join(sorted(set(st))),
            stage=stage, stage_reason=reason,
            dest=dest,
            stock_inclusion=split_dn.get(dn, {}).get("stock_inclusion", ""),
            proven_arrival_date=(max(dlvr) if stage.startswith("received") and dlvr else ""),
            etd_proven=(max(atd) if atd else ""),
            eta_unproven=(min(etas) if stage == "in_transit" and etas else ""),
            evidence_level=ev,
            count_once_rule=("不计在途（已在手）" if stage == "received_before_snapshot" and scope == "tracked"
                             else "不计在途/在手（外部 FBA 不可追踪）" if stage.startswith("received") and scope == "external_fba"
                             else "不计在途（已在手）" if stage == "received_before_snapshot" else
                             "计在途一次" if stage == "in_transit" else
                             "保留 unknown，不折算"),
            allocation=("整单" if len(numbers) == 1 else "分配未知（多号）"),
        ))

    with (OUT / "sc04_supply_stage.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(stage_rows[0].keys()))
        w.writeheader()
        w.writerows(stage_rows)

    stage_of = {r["dn"]: r["stage"] for r in stage_rows}
    line_rows = [dict(dn=x["dn"], item_code=x["item_code"], uom=x["uom"], qty=x["qty"],
                      stage=stage_of.get(x["dn"], "unknown_status")) for x in lines]
    with (OUT / "sc04_supply_lines.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(line_rows[0].keys()))
        w.writeheader()
        w.writerows(line_rows)

    # ---- 分布与对账 ---------------------------------------------------------
    by_stage_dn = Counter(r["stage"] for r in stage_rows)
    by_stage_num = Counter()
    for r in stage_rows:
        by_stage_num[r["stage"]] += r["n_numbers"]
    by_stage_lines = Counter(r["stage"] for r in line_rows)
    qty_by_stage_uom = defaultdict(float)
    for r in line_rows:
        qty_by_stage_uom[(r["stage"], r["uom"])] += float(r["qty"] or 0)

    recon_block = dict(
        numbers=len(bridge), dns=len(by_dn), lines=len(lines),
        stage_dn_sum=sum(by_stage_dn.values()),
        stage_number_sum=sum(by_stage_num.values()),
        stage_line_sum=sum(by_stage_lines.values()),
        ok=(len(by_dn) == sum(by_stage_dn.values())
            and len(bridge) == sum(by_stage_num.values())
            and len(lines) == sum(by_stage_lines.values())),
    )

    payload = dict(
        schema_version="sc04_supply_stage/1",
        cutoff=CUTOFF,
        inputs=["dn_bridge_rows.csv", "dn_status_recon.csv", "dn_split_dn.csv", "dn_split_lines.csv"],
        stage_definition={
            "received_before_snapshot": "已签收/入仓且签收日 ≤ cutoff -> 已在手，**不再计在途**",
            "received_unknown_date": "已签收/入仓但无签收日期 -> 保留 unknown",
            "received_after_snapshot": "签收日晚于快照 -> 未入账",
            "in_transit": "全部为在途节点 -> 计在途一次；可用日不给（只认已证节点）",
            "partially_received": "多号部分签收 -> 分配未知",
            "unknown_status": "状态缺失/未匹配 -> unknown",
        },
        distribution=dict(
            by_stage_dn=dict(by_stage_dn),
            by_stage_numbers=dict(by_stage_num),
            by_stage_lines=dict(by_stage_lines),
            qty_by_stage_uom={f"{k[0]}|{k[1]}": round(v, 2) for k, v in sorted(qty_by_stage_uom.items())},
        ),
        unknown=dict(
            unknown_status=[dict(dn=r["dn"], statuses=r["statuses"], reason=r["stage_reason"])
                            for r in stage_rows if r["stage"].startswith("unknown")],
            received_unknown_date=[r["dn"] for r in stage_rows
                                   if r["stage"] == "received_unknown_date"],
            partially_received=[r["dn"] for r in stage_rows if r["stage"] == "partially_received"],
            eta_unproven_count=sum(1 for r in stage_rows if r["eta_unproven"]),
            eta_missing_in_transit=sum(1 for r in stage_rows
                                       if r["stage"] == "in_transit" and not r["eta_unproven"]),
            eta_stale_in_transit=[dict(dn=r["dn"], eta=r["eta_unproven"])
                                  for r in stage_rows
                                  if r["stage"] == "in_transit" and r["eta_unproven"]
                                  and r["eta_unproven"] < CUTOFF],
            eta_stale_note="在途但 ETA 早于快照日 -> ETA 已过期，不能当可用日",
        ),
        scope=dict(by_scope=dict(Counter(r["stock_scope"] for r in stage_rows)),
                   received_external=[r["dn"] for r in stage_rows
                                      if r["stock_scope"] == "external_fba" and r["stage"].startswith("received")],
                   note="外部 FBA 的已签收货既不在我方在手、也不应算我方在途"),
        evidence=dict(by_level=dict(Counter(r["evidence_level"] for r in stage_rows)),
                      note="E1=有该阶段的已证节点日期；E2=只有状态没有日期；E3=无状态"),
        suspected_same_batch=dict(
            note=("前向账 S_*_same_batch / diff_batch 情景里的到货属「疑似同批」，"
                  "本表不折算、保留并列；同一批货只按一个阶段计一次"),
            forward_ref="forward_net.json.scenario_totals（receipts 0 / 129 / 258 三种）",
        ),
        proposal_for_forward_net=dict(
            fields=[
                dict(name="stage", type="enum", values=list(stage_definition_keys := [
                    "received_before_snapshot", "received_unknown_date", "received_after_snapshot",
                    "in_transit", "partially_received", "unknown_status"]),
                     note="供应项所处阶段；一张 DN 只取一个"),
                dict(name="batch_id", type="string", note="DN 单号；去重键的第一段"),
                dict(name="item_code", type="string", note="EN 物料码；与 BOM/映射同键"),
                dict(name="uom", type="string", note="**必带**：跨 UOM 不得合并"),
                dict(name="qty", type="number", note="该 (batch,item,uom) 的数量；不跨 UOM 求和"),
                dict(name="proven_arrival_date", type="date|null",
                     note="只有 received_* 才给（实际签收日）；in_transit 一律 null"),
                dict(name="eta_unproven", type="date|null",
                     note="承运商 ETA；**不得**当可用日，仅供敏感性"),
                dict(name="evidence_level", type="enum", values=["E1_node_proven", "E2_status_only", "E3_unknown"]),
                dict(name="dedupe_key", type="string", note="batch_id + item_code + uom，保证同一批只计一次"),
            ],
            compatibility=("forward_net 当前的供给口径是 wo_qty/wo_status（not_observed）与 receipts 情景；"
                           "本建议不改变其计算，只提供可被其消费的字段形状"),
            not_changed="本轮未修改 forward_net.py / forward_net_rows.csv",
        ),
        reconciliation=recon_block,
        boundaries=[
            "只读；未查生产（复用 59c4e5ec 的 DN/Shipment 证据）；未改 forward_net；不出补货量。",
            "到货时间只认已证节点；ETA 单列且不默认及时到货。",
            "同一批货只计一次：已签收且 ≤ cutoff 的不再计在途。",
            "多号 DN 分配未知；跨 UOM 不合计。",
        ],
    )
    (OUT / "sc04_supply.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps({k: payload[k] for k in ("distribution", "unknown", "evidence", "reconciliation")},
                     ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
