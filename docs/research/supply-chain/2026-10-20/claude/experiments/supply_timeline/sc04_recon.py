#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SC04 对账（只读）：重新拉 8/1 后有运单号的 DN，按 SC04 阶段规则复算，
并与 SC04 报告基线（39 DN / 47 号 / 4,279 行）比较；同时给出 9 SKU 样本覆盖。

注意：SC04 的行级 CSV 与 order_store.duckdb 不在本机，本脚本从 EN 生产只读重算；
差异需结合 as_of / 生产漂移解释，不能当作 SC04 原产物被改。
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from w1_supply_timeline import Cache, EnClient, build, fetch_shipments, fetch_shipments_by_name, chunks

HERE = Path(__file__).resolve().parent
CFG = json.loads((HERE / "config" / "sample_skus.json").read_text(encoding="utf-8"))

BASELINE = {
    "as_of": "2026-10-22",
    "dns": 39,
    "numbers": 47,
    "lines": 4279,
    "stages": {
        "received_before_snapshot": 6,
        "received_unknown_date": 1,
        "in_transit": 30,
        "partially_received": 1,
        "unknown_status": 1,
    },
    "fba_dns": 17,
    "tracked_dns": 22,
}
SIGNED = {"已签收", "已上传POD", "已入仓"}
TRANSIT = {"已订舱", "已报关", "已离港", "已转运", "已到港", "清关中", "已清关"}
CUTOFF = "2026-10-20"


def stage_of(statuses, dlvrs):
    if not statuses or any(not str(s).strip() for s in statuses):
        return "unknown_status"
    if any(s not in SIGNED | TRANSIT for s in statuses):
        return "unknown_status"
    if all(s in SIGNED for s in statuses):
        if not dlvrs:
            return "received_unknown_date"
        return "received_before_snapshot" if max(dlvrs) <= CUTOFF else "received_after_snapshot"
    if all(s in TRANSIT for s in statuses):
        return "in_transit"
    return "partially_received"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(HERE / "out"))
    ap.add_argument("--as-of", default=CFG.get("as_of"))
    args = ap.parse_args()
    cache = Cache(HERE / "cache")
    en = EnClient(cache)

    heads = en.get_list("Delivery Note",
                        [["docstatus", "in", [1, 2]], ["creation", ">=", "2026-08-01"],
                         ["creation", "<=", (args.as_of or "2026-10-23") + " 23:59:59"]],
                        ["name", "status", "docstatus", "posting_date", "customer", "company"],
                        order_by="creation asc")
    heads = list({h["name"]: h for h in heads}.values())
    docs = [en.get_doc("Delivery Note", h["name"]) for h in heads]
    numbers_by_dn = {}
    all_numbers = []
    for d in docs:
        nums = [r.get("logistic_number") for r in (d.get("custom_zmt_logistic_numbers") or [])
                if r.get("logistic_number")]
        if not nums and d.get("custom_zmt_shipment"):
            nums = []
        numbers_by_dn[d["name"]] = nums
        all_numbers.extend(nums)
    shipments = fetch_shipments(en, all_numbers)
    names = [d.get("custom_zmt_shipment") for d in docs if d.get("custom_zmt_shipment")]
    if names:
        shipments.update(fetch_shipments_by_name(en, [n for n in names if n not in shipments]))

    sample_items = {it["item_code"] for s in CFG["slots"] for it in (s.get("items") or [])}
    sample_skus = [s["sku"] for s in CFG["slots"] if s.get("sku")]

    stage_counts = Counter()
    stage_qty = defaultdict(lambda: Counter())
    stage_dns = defaultdict(list)
    fba_dns = 0
    sample_dns = []
    total_lines = 0
    for d in docs:
        nums = numbers_by_dn[d["name"]]
        lines = d.get("items") or []
        if not nums:
            continue
        total_lines += len(lines)
        if "FBA" in str(d.get("customer") or ""):
            fba_dns += 1
        ships = [shipments.get(n) for n in nums if shipments.get(n)]
        statuses = [str(s.get("custom_zmt_status11") or "").strip() for s in ships]
        dlvrs = sorted(str(s.get("custom_zmt_dlvr"))[:10] for s in ships if s.get("custom_zmt_dlvr"))
        stage = stage_of(statuses, dlvrs)
        stage_counts[stage] += 1
        stage_dns[stage].append(d["name"])
        for line in lines:
            uom = line.get("uom") or "(unknown)"
            stage_qty[stage][uom] += float(line.get("qty") or 0)
        sample_hit = any(line.get("item_code") in sample_items for line in lines)
        if not sample_hit:
            sample_hit = any(str(line.get("customer_item_code") or "") == sku
                             or sku.lower() in str(line.get("customer_item_code") or "").lower()
                             for line in lines for sku in sample_skus)
        if sample_hit:
            sample_dns.append({"dn": d["name"], "stage": stage, "numbers": nums,
                               "lines": len(lines)})

    with_numbers = [d for d in docs if numbers_by_dn[d["name"]]]
    computed = {
        "as_of": args.as_of,
        "dns_total": len(docs),
        "dns_with_numbers": len(with_numbers),
        "numbers": len(all_numbers),
        "lines": total_lines,
        "stages": dict(stage_counts),
        "stage_qty_by_uom": {k: dict(v) for k, v in stage_qty.items()},
        "fba_dns": fba_dns,
        "tracked_dns": len(with_numbers) - fba_dns,
        "sample_9sku_coverage": {
            "dns": len(sample_dns),
            "numbers": sum(len(x["numbers"]) for x in sample_dns),
            "lines": sum(x["lines"] for x in sample_dns),
            "stage_counts": dict(Counter(x["stage"] for x in sample_dns)),
            "detail": sample_dns,
        },
    }
    diff = {
        "dns_with_numbers": computed["dns_with_numbers"] - BASELINE["dns"],
        "numbers": computed["numbers"] - BASELINE["numbers"],
        "lines": computed["lines"] - BASELINE["lines"],
        "stages": {k: computed["stages"].get(k, 0) - BASELINE["stages"].get(k, 0)
                   for k in set(computed["stages"]) | set(BASELINE["stages"])},
        "fba_dns": computed["fba_dns"] - BASELINE["fba_dns"],
    }
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    result = {
        "baseline_source": "2026-10-23-sc04-supply-stage.md (228bef77)",
        "baseline": BASELINE,
        "computed": computed,
        "difference": diff,
        "source_missing": [
            "SC04 行级 CSV（sc04_supply_stage.csv / sc04_supply_lines.csv）不在本机；",
            "order_store.duckdb 与 D:/Work/库存备份 不在本机；",
            "本结果是 EN 生产只读重算，非 SC04 原产物。",
        ],
        "en_calls": en.calls,
    }
    (out / "sc04_recon.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print("SC04_COMPUTED", json.dumps({k: computed[k] for k in ("dns_total", "dns_with_numbers", "numbers", "lines", "stages", "fba_dns")}, ensure_ascii=False))
    print("SC04_DIFF", json.dumps(diff, ensure_ascii=False))
    print("SC04_SAMPLE", json.dumps(computed["sample_9sku_coverage"], ensure_ascii=False)[:800])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
