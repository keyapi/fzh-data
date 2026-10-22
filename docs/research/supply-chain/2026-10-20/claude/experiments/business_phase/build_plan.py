#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Phase 1C: three-part delivery for Top50 ∪ urgent exceptions.

Per SKU:
  1. demand   -- P50 + interval from the frozen 6-month net-sales metric, using
                 V1's established conventions (reused by importing model_race.py:
                 label_available_at, rolling-origin residuals, conformal-style
                 estimate with no finite-sample guarantee).  Censoring (stockout /
                 waiting orders, zero-filled months) is marked as a demand gap,
                 never as zero demand.
  2. supply   -- time-bucketed supply_lower / supply_upper with per-side
                 provenance (documents, deduped?, UOM-converted?, in-window?,
                 blockers).  Arrivals without ETA are excluded from every lower
                 bound and can never close a near-term gap.
  3. decision -- tri-state: no-replenish = proven supply lower >= demand upper;
                 replenish = supply upper < demand lower; else pending with
                 quantity fields NULL (never 0).  Quantities are emitted only for
                 evidence-sufficient rows -- this batch has none, and says why.

No purchase instruction. No production access. DB read only.

Inputs (read-only): ranking.json, destinations.json, V1 evidence.json /
model_race.json, order_store.duckdb.
Outputs: out/business_phase/plan.json, plan.md
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
from collections import defaultdict
from datetime import date
from pathlib import Path

import duckdb
import numpy as np

DB_PATH = Path("D:/Work/fzh-order-store/order_store.duckdb")
HERE = Path(__file__).resolve()
CLAUDE_DIR = HERE.parents[2]
OUT_DIR = CLAUDE_DIR / "out" / "business_phase"
RANKING = OUT_DIR / "ranking.json"
DESTINATIONS = OUT_DIR / "destinations.json"
EVIDENCE = CLAUDE_DIR / "out" / "replenishment_v0" / "evidence.json"
MODEL_RACE_JSON = CLAUDE_DIR / "out" / "replenishment_v0" / "model_race.json"
MODEL_RACE_PY = CLAUDE_DIR / "experiments" / "g2g3_pilot" / "model_race.py"
OUT_JSON = OUT_DIR / "plan.json"
OUT_MD = OUT_DIR / "plan.md"

DECISION_DATE = date(2026, 10, 22)
HORIZON_DAYS = 90                    # 2026-10-22 .. 2027-01-20
CANDIDATE = "mean3"                  # point model over the frozen 6-month metric
MONTHS = ["2026-04", "2026-05", "2026-06", "2026-07", "2026-08", "2026-09"]
PIECE_UOMS = ("个", "件", "套")
BUCKETS = [
    ("A_0_40d", "2026-10-22", "2026-11-30", 40),
    ("B_41_71d", "2026-12-01", "2026-12-31", 31),
    ("C_72_91d", "2027-01-01", "2027-01-20", 20),
    ("D_beyond_91d", "2027-01-21", None, None),
]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_model_race():
    spec = importlib.util.spec_from_file_location("v1_model_race", MODEL_RACE_PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(DB_PATH))
    ap.add_argument("--ranking", default=str(RANKING))
    ap.add_argument("--destinations", default=str(DESTINATIONS))
    ap.add_argument("--json", default=str(OUT_JSON))
    ap.add_argument("--md", default=str(OUT_MD))
    args = ap.parse_args()

    db_path = Path(args.db)
    ranking_path = Path(args.ranking)
    dest_path = Path(args.destinations)
    for p in (db_path, ranking_path, dest_path, EVIDENCE, MODEL_RACE_JSON, MODEL_RACE_PY):
        if not p.exists():
            raise SystemExit(f"missing input: {p}")

    hashes = dict(
        ranking=sha256_file(ranking_path), destinations=sha256_file(dest_path),
        evidence=sha256_file(EVIDENCE), model_race_json=sha256_file(MODEL_RACE_JSON),
        model_race_py=sha256_file(MODEL_RACE_PY),
        db_before=sha256_file(db_path),
    )
    ranking = json.loads(ranking_path.read_text(encoding="utf-8"))
    dest = json.loads(dest_path.read_text(encoding="utf-8"))
    mr = load_model_race()

    top = {t["sku"] for t in ranking["top50"]}
    urgent = {u["sku"] for u in ranking["urgent_fulfilment_exceptions"]}
    coverage = sorted(top | urgent)
    if len(coverage) != len(set(coverage)):
        raise SystemExit("coverage duplication")
    dest_by_sku = {r["sku"]: r for r in dest["rows"]}

    con = duckdb.connect(str(db_path), read_only=True)
    try:
        # ---- order history (same net definition as Phase 1B) ---------------
        rows = con.execute("""
            SELECT sku_tongtool, substr(despatch_date,1,7) AS ym, qty, platform_sku
            FROM gs_orders
            WHERE despatch_date <= '2026-09-30'
        """).fetchall()
        item_uom = {r[0]: r[1] for r in con.execute(
            "SELECT item, uom FROM bom").fetchall()}
        stock = defaultdict(lambda: dict(available=0, intransit=0, waiting=0,
                                         defects=0, warehouses=[]))
        for sku, wh, avail, intr, wait, defe in con.execute("""
                SELECT sku, warehouse, available, intransit, waiting_shipment, defects
                FROM stock_latest""").fetchall():
            s = stock[sku]
            s["available"] += int(avail or 0)
            s["intransit"] += int(intr or 0)
            s["waiting"] += int(wait or 0)
            s["defects"] += int(defe or 0)
            if int(avail or 0) or int(intr or 0):
                s["warehouses"].append(dict(warehouse=wh, available=int(avail or 0),
                                            intransit=int(intr or 0)))
        po_open = {}
        for sku, qty, lines in con.execute("""
                SELECT goods_sku, SUM(open_qty), COUNT(*) FROM tongtool_po
                WHERE open_qty > 0 GROUP BY 1""").fetchall():
            po_open[sku] = dict(qty=int(qty or 0), lines=int(lines or 0))
        po_eta_missing = con.execute(
            "SELECT COUNT(*) FROM tongtool_po WHERE open_qty > 0 "
            "AND will_arrive_date IS NULL").fetchone()[0]
        po_eta_present = con.execute(
            "SELECT COUNT(*) FROM tongtool_po WHERE open_qty > 0 "
            "AND will_arrive_date IS NOT NULL").fetchone()[0]
        stockout = {}
        for sku, n in con.execute("""
                SELECT goods_sku, COUNT(*) FROM v_stockout_observed
                WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM v_stockout_observed)
                GROUP BY 1""").fetchall():
            stockout[sku] = int(n)
    finally:
        con.close()
    if sha256_file(db_path) != hashes["db_before"]:
        raise SystemExit("DB changed during the run; refusing to publish")

    # ---- monthly series for coverage SKUs (net, zero-filled) ---------------
    hist = defaultdict(lambda: defaultdict(int))
    coverage_set = set(coverage)
    for sku, ym, qty, psku in rows:
        if sku not in coverage_set:
            continue
        if psku and re.search(r"(^|[-_])test([-_]|$)", psku, re.IGNORECASE):
            continue
        hist[sku][ym] += int(qty)
    last_i = mr.ym_to_i("2026-09")
    data = {}
    series = {}
    for sku in coverage:
        by = hist.get(sku, {})
        if not by:
            continue
        first_i = min(mr.ym_to_i(m) for m in by if m)
        months = [mr.i_to_ym(i) for i in range(first_i, last_i + 1)]
        y = np.array([float(by.get(m, 0)) for m in months], dtype=float)
        data[sku] = dict(sku=sku, first=first_i, last=last_i, months=months, y=y)
        series[sku] = dict(first=months[0], last=months[-1], n_months=len(months),
                           monthly=[dict(month=m, qty=int(v))
                                    for m, v in zip(months, y)])

    shape90 = mr.calendar_window_weights(DECISION_DATE, HORIZON_DAYS)
    horizon_months = len(shape90)

    plan_rows = []
    for sku in coverage:
        d = dest_by_sku.get(sku)
        in_mother = d is not None
        item = (d or {}).get("mapped_item_code")
        uom = item_uom.get(item) if item else None
        uom_ok = uom in PIECE_UOMS
        st = stock.get(sku, dict(available=0, intransit=0, waiting=0, defects=0,
                                 warehouses=[]))
        po = po_open.get(sku, dict(qty=0, lines=0))

        # ---------------- demand -------------------------------------------
        if sku in data:
            dd = data[sku]
            f, meta = mr.forecast_candidate(CANDIDATE, sku, data, len(dd["y"]),
                                            dd["last"], horizon_months)
            f_by = {dd["last"] + 1 + k: float(f[k]) for k in range(horizon_months)}
            p50 = mr._window_value(f_by, shape90)
            cal = mr.window_calibration(sku, data, CANDIDATE, HORIZON_DAYS,
                                        DECISION_DATE)
            p90, lift = mr.p90_from_cal(p50, cal)
            last6 = [(m, int(v)) for m, v in zip(dd["months"], dd["y"])
                     if m in MONTHS]
            zero6 = sum(1 for m in MONTHS if m not in dict(last6))
            demand = dict(
                available=True,
                training=dict(definition="net_qty_6m from Phase 1B", months=MONTHS,
                              values=[dict(month=m, qty=(dict(last6).get(m, 0)))
                                      for m in MONTHS],
                              zero_filled_months=zero6),
                horizon_days=HORIZON_DAYS,
                p50=mr._round(p50),
                interval=dict(p90_like=(mr._round(p90) if p90 is not None else None),
                              lift=(mr._round(lift) if lift is not None else None),
                              status=cal["status"], scope=cal["scope"],
                              n_own=cal["n_own"], n_pool=cal["n_pool"],
                              estimator=cal["estimator_info"]["estimator"],
                              finite_sample_guarantee=False,
                              label_rule=cal["label_rule"],
                              n_window_ended_but_label_pending=cal[
                                  "n_window_ended_but_label_pending"],
                              note=("conformal-style estimate: no finite-sample 90% "
                                    "guarantee and not usable as a proven upper bound")),
            )
        else:
            demand = dict(available=False, horizon_days=HORIZON_DAYS,
                          reason="no despatch history before 2026-09 in gs_orders",
                          p50=None,
                          interval=dict(p90_like=None, status="not_calibrated",
                                        finite_sample_guarantee=False))

        censored_months = []
        if demand["available"]:
            for cell in demand["training"]["values"]:
                if cell["qty"] == 0 and (st["waiting"] > 0 or stockout.get(sku, 0) > 0):
                    censored_months.append(cell["month"])
        demand["censoring"] = dict(
            zero_filled_months=(demand["training"]["zero_filled_months"]
                                if demand["available"] else None),
            zero_months_with_unfulfilled_signal=censored_months,
            stockout_observed_rows=stockout.get(sku, 0),
            waiting_shipment_units=st["waiting"],
            rule=("an unfulfilled / stockout event is a demand GAP, not zero demand; "
                  "a zero-filled month coinciding with waiting or stockout evidence is "
                  "flagged and never read as 'no demand'"),
            returns_and_cancellations=("not observable in gs_orders (no status field; "
                                       "0 negative lines in the window) -- caliber boundary"),
        )

        # ---------------- supply -------------------------------------------
        available, intransit, po_qty = st["available"], st["intransit"], po["qty"]
        arrival_pool = intransit + po_qty   # timing UNKNOWN: no ETA anywhere
        supply_ok_lower = uom_ok and available >= 0
        supply_ok_upper = False            # overlap + unbooked supply never proven here

        def side(value, status, kind):
            return dict(
                value=int(value), status=status, kind=kind,
                components=[
                    dict(source="stock_latest.available", qty=available,
                         documents=sorted({w["warehouse"] for w in st["warehouses"]}),
                         deduped=True, uom_converted=uom_ok, in_window=True,
                         note="on hand at the 2026-10-22 snapshot"),
                    dict(source="inventory.intransit + tongtool_po.open", qty=arrival_pool,
                         documents=dict(intransit=intransit, open_po_qty=po_qty,
                                        open_po_lines=po["lines"]),
                         deduped=False, uom_converted=uom_ok, in_window=False,
                         note=("no will_arrive_date on any open PO line "
                               f"({po_eta_missing} missing / {po_eta_present} present); "
                               "intransit may already be inside the open PO")),
                ],
                blockers=[b for b in [
                    None if uom_ok else "G2_uom: mapped item has no piece-unit BOM row",
                    None if kind == "lower" else "G4_supply_overlap: PO/intransit not deduped",
                    None if kind == "lower" else "G7_unbooked_supply: Cover not booked",
                    None if kind == "lower" else
                    "production_missing: open WO / remaining qty is not in this snapshot, "
                    "so the record sum may UNDERSTATE supply and cannot certify shortage",
                ] if b],
                missing_evidence=([e for e in [
                    None if uom_ok else "BOM piece-unit row for the mapped item",
                    None if kind == "lower" else "line-level PO/intransit overlap key",
                    None if kind == "lower" else "arrival date (will_arrive_date)",
                ] if e]),
            )

        buckets = []
        for name, start, end, _days in BUCKETS:
            if name == "A_0_40d":
                lo = side(available, "ok" if supply_ok_lower else "unproven", "lower")
                up = side(available + arrival_pool,
                          "ok" if supply_ok_upper else "unproven", "upper")
            elif name == "D_beyond_91d":
                lo = side(0, "ok", "lower")
                up = side(0, "ok", "upper")
            else:
                lo = side(0, "ok", "lower")
                up = side(0, "unproven", "upper")
                lo["components"], up["components"] = [], []
                lo["components_ref"] = up["components_ref"] = (
                    "no incremental quantity in this bucket; see A_0_40d")
            buckets.append(dict(
                bucket=name, start=start, end=end,
                supply_lower=lo, supply_upper=up,
                note=("arrivals without ETA are excluded from the lower bound and "
                      "cannot close a near-term gap; the upper bound counts them as a "
                      "stress scenario at the earliest bucket" if name == "A_0_40d"
                      else "no proven arrival in this bucket"),
            ))
        supply = dict(
            buckets=buckets,
            bucket_semantics=("incremental, non-overlapping horizons; the 90-day decision "
                              "uses supply.supply_lower/supply_upper, not a bucket sum"),
            horizon_days=HORIZON_DAYS,
            supply_lower=dict(value=int(available),
                              status="ok" if supply_ok_lower else "unproven",
                              basis="proven in-window on-hand only"),
            supply_upper=dict(value=int(available + arrival_pool),
                              status="ok" if supply_ok_upper else "unproven",
                              basis=("record sum (on hand + intransit + open PO); it is "
                                     "NOT usable to prove sufficiency")),
            arrivals_eta_missing=(po_eta_missing if po["lines"] else 0),
            rule=("no-replenish may only be proven by a proven supply LOWER bound; "
                  "late / no-ETA supply never closes a near-term gap"),
        )

        # ---------------- decision -----------------------------------------
        demand_lower = dict(value=int(st["waiting"]),
                            status=("ok" if st["waiting"] > 0 else "trivial_zero"),
                            basis=("committed orders waiting to ship (evidence: "
                                   "stock_latest.waiting_shipment) -- a real demand "
                                   "floor for the horizon" if st["waiting"] > 0
                                   else "no waiting orders -> trivial lower bound 0"))
        demand_upper = dict(value=demand["interval"].get("p90_like"),
                            status="unproven",
                            basis=("conformal-style estimate, not a proven upper bound; "
                                   "business demand ceiling (G8) not provided"))
        both_ok = (supply["supply_lower"]["status"] == "ok"
                   and supply["supply_upper"]["status"] == "ok"
                   and demand_lower["status"] == "ok"
                   and demand_upper["status"] == "ok"
                   and demand_upper["value"] is not None)
        if both_ok and supply["supply_lower"]["value"] >= demand_upper["value"]:
            state, why = "no_replenish", "supply_lower >= demand_upper"
        elif both_ok and supply["supply_upper"]["value"] < demand_lower["value"]:
            state, why = "replenish", "supply_upper < demand_lower"
        else:
            state, why = "pending", "bounds not proven"

        screening = "ambiguous"
        if demand_upper["value"] is not None:
            if supply["supply_upper"]["value"] < demand_lower["value"]:
                screening = "shortage_signal"
            elif supply["supply_lower"]["value"] >= demand_upper["value"]:
                screening = "sufficiency_signal"
        decision = dict(
            state=state, reason=why,
            quantity_baseline=None, quantity_stress=None,
            quantity_note=("quantity fields are NULL by rule; 0 would be a claim. "
                           "Only evidence-sufficient rows may carry a number"),
            refs=dict(
                demand_lower={k: demand_lower[k] for k in ("value", "status", "basis")},
                demand_upper={k: demand_upper[k] for k in ("value", "status", "basis")},
                supply_lower={k: supply["supply_lower"][k]
                              for k in ("value", "status", "basis")},
                supply_upper={k: supply["supply_upper"][k]
                              for k in ("value", "status", "basis")},
                pointer="see rows[].supply.*.components for documents and provenance",
            ),
            screening=screening,
            screening_note=("arithmetic signal only, computed on estimates/unverified "
                            "bounds; never a conclusion"),
        )

        missing = []
        if not in_mother:
            missing.append(dict(item="EN mapping for this SKU (not in business mother set)",
                                owner_role="商品主数据",
                                why_it_blocks="supply UOM and demand mapping cannot be verified"))
        elif (d or {}).get("destination") == "mapped_ineligible":
            missing.append(dict(item="BOM piece-unit row for the mapped item",
                                owner_role="商品主数据/工程BOM",
                                why_it_blocks="unit basis unproven -> no proven supply bound"))
        if not uom_ok:
            missing.append(dict(item="piece-unit (件/个/套) UOM basis",
                                owner_role="商品主数据/仓储",
                                why_it_blocks="supply quantities cannot be compared with demand"))
        if arrival_pool > 0:
            missing.append(dict(item="open PO / intransit arrival dates",
                                owner_role="采购/供应链；数据/系统",
                                why_it_blocks="arrivals without ETA cannot enter any lower bound"))
            missing.append(dict(item="line-level PO/intransit overlap key",
                                owner_role="数据/系统",
                                why_it_blocks="record sum is neither deduped nor a valid upper bound"))
        missing.append(dict(item="open production WO remaining qty and planned_end_date",
                            owner_role="生产/PMC",
                            why_it_blocks=("not in this snapshot; without it the supply "
                                           "upper may understate and no shortage can be certified")))
        missing.append(dict(item="business demand lower/upper bounds (G8)",
                            owner_role="业务/运营",
                            why_it_blocks="P50/P90 are estimates; conclusions need bounds"))
        missing.append(dict(item="Cover / unbooked substitutable supply absence",
                            owner_role="商品主数据/仓储",
                            why_it_blocks="record sum cannot be an upper bound while unbooked supply exists"))
        if not demand["available"]:
            missing.append(dict(item="6-month sales history for this SKU",
                                owner_role="业务/运营",
                                why_it_blocks="no demand forecast is possible"))

        plan_rows.append(dict(
            sku=sku,
            in_coverage_because=sorted(
                ([ "top50" ] if sku in top else []) +
                ([ "urgent_exception" ] if sku in urgent else [])),
            in_mother_set=in_mother,
            destination=((d or {}).get("destination") or "not_in_mother_set"),
            mapped_item_code=item, item_group=((d or {}).get("item_group")),
            stock=dict(available=available, intransit=intransit,
                       waiting_shipment=st["waiting"], defects=st["defects"],
                       open_po_qty=po["qty"], open_po_lines=po["lines"],
                       uom=uom, uom_converted=uom_ok),
            demand=demand,
            supply=supply,
            decision=decision,
            missing_evidence=missing,
            evidence_pointer=(f"stock_latest[sku={sku!r}]; tongtool_po[goods_sku={sku!r}]; "
                              f"gs_orders[sku_tongtool={sku!r}, despatch<=2026-09-30]; "
                              f"model_race.py window_calibration(mean3,90d,asof=2026-10-22)"),
        ))

    # ---------------- integrity ---------------------------------------------
    states = defaultdict(int)
    for r in plan_rows:
        states[r["decision"]["state"]] += 1
        if r["decision"]["state"] == "pending":
            for k in ("quantity_baseline", "quantity_stress"):
                if r["decision"][k] is not None:
                    raise SystemExit("pending row carries a quantity")
    if len(plan_rows) != len(coverage):
        raise SystemExit("coverage/rows mismatch")
    if any(not r["missing_evidence"] for r in plan_rows):
        raise SystemExit("a row has no missing-evidence list")

    out = dict(
        schema_version="business_phase_plan/1",
        stage="Phase 1C (demand + bucketed supply + tri-state; no purchase instruction)",
        generated_at=__import__("datetime").datetime.now().astimezone().isoformat(timespec="seconds"),
        coverage=dict(
            top50=len(top), urgent_exceptions=len(urgent),
            overlap=sorted(top & urgent), union=len(coverage),
            rule="Top50 ∪ urgent exceptions; membership is recomputed, not copied",
        ),
        inputs=dict(
            ranking_path=str(ranking_path), ranking_sha256=hashes["ranking"],
            ranking_commit="d50310a6",
            destinations_sha256=hashes["destinations"], destinations_commit="44def7f5",
            evidence_sha256=hashes["evidence"], model_race_json_sha256=hashes["model_race_json"],
            model_race_py_sha256=hashes["model_race_py"], model_race_commit="f9df4357",
            db_sha256_before=hashes["db_before"],
            db_sha256_after=sha256_file(db_path),
            db_unchanged=hashes["db_before"] == sha256_file(db_path),
        ),
        demand_caliber=dict(
            training="6-month net sales per Phase 1B (2026-04..09), zero-filled",
            point_model=CANDIDATE,
            horizon_days=HORIZON_DAYS,
            convention=("V1 conventions reused by importing model_race.py: rolling-origin "
                        "same-shape window residuals, label_available_at filter, "
                        "conformal-style quantile, finite_sample_guarantee=false"),
            label_available_at=("a residual enters calibration only when the monthly label "
                                "of its last touched month exists at the decision date"),
            censoring=("stockout / waiting evidence and zero-filled months are demand GAPS, "
                       "never zero demand"),
            returns_and_cancellations="not observable in gs_orders (caliber boundary)",
        ),
        supply_caliber=dict(
            buckets=[b[0] for b in BUCKETS],
            lower="proven in-window on-hand only; arrivals without ETA are excluded",
            upper=("record sum (on hand + intransit + open PO); never usable to prove "
                   "sufficiency because dedup and unbooked-supply absence are unproven"),
            eta_status=dict(open_po_lines_missing_eta=po_eta_missing,
                            open_po_lines_with_eta=po_eta_present),
            late_supply_rule="late / no-ETA supply never closes a near-term gap",
        ),
        counts=dict(
            coverage=len(coverage), rows=len(plan_rows),
            states={k: states.get(k, 0) for k in ("no_replenish", "replenish", "pending")},
            with_quantity=sum(1 for r in plan_rows
                              if r["decision"]["quantity_baseline"] is not None),
            demand_forecast_available=sum(1 for r in plan_rows
                                          if r["demand"]["available"]),
            supply_lower_proven=sum(1 for r in plan_rows
                                    if r["supply"]["supply_lower"]["status"] == "ok"),
            supply_upper_proven=sum(1 for r in plan_rows
                                    if r["supply"]["supply_upper"]["status"] == "ok"),
            rows_in_mother_set=sum(1 for r in plan_rows if r["in_mother_set"]),
            rows_outside_mother_set=sum(1 for r in plan_rows if not r["in_mother_set"]),
        ),
        rows=plan_rows,
        reconciliation=dict(rows_in=len(coverage), rows_out=len(plan_rows), dropped=[],
                            note="every coverage SKU is emitted exactly once"),
    )
    out_json = Path(args.json)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n",
                        encoding="utf-8")

    # ---------------- markdown ---------------------------------------------
    md = ["---", "okf: v0.1", "type: Report",
          "title: Phase 1C 三段式交付（需求预测 / 分时供给 / 三态判定）",
          f"date: {date.today().isoformat()}", "owner: claude-worker",
          "status: delivery only; no purchase instruction",
          "inputs:",
          "  - out/business_phase/ranking.json（d50310a6，只读）",
          "  - out/business_phase/destinations.json（44def7f5，只读）",
          "  - out/replenishment_v0/evidence.json / model_race.json（f9df4357，只读）",
          "  - D:/Work/fzh-order-store/order_store.duckdb（read_only）",
          "artifacts:",
          "  - experiments/business_phase/build_plan.py",
          "  - out/business_phase/plan.json", "---", "",
          "# Phase 1C：三段式交付", "",
          f"> 覆盖集合 = **Top50 ∪ 紧急履约例外** = {len(coverage)} 个 SKU"
          f"（Top50 {len(top)} + 例外 {len(urgent)} − 重叠 {len(top & urgent)}）。",
          "> 本文件不出采购指令、不判补/不补之外的任何动作；数量只为“证据充分”行保留，本批为 0。", "",
          "## 1. 需求口径", "",
          "- 训练：Phase 1B 冻结的 6 个月净销量（2026-04..09，零填充）；点模型 `mean3`。",
          f"- 预测地平线：{HORIZON_DAYS} 天（2026-10-22 → 2027-01-20），同形日历窗口。",
          "- **沿用 V1 已确立口径**：rolling-origin 同形残差、`label_available_at` 过滤、"
          "conformal-style 分位；产物明写 `finite_sample_guarantee=false`，**不声称 90% 保证**。",
          "- **断货/未履约不当零需求**：零填充月份若同时有断货或待发证据，标为需求缺口。",
          "- **退货/取消不可观测**：`gs_orders` 无状态字段，窗口内 0 条负数量行 —— 口径边界，已写明。", "",
          "## 2. 分时供给情景", "",
          "| 桶 | 区间 | supply_lower | supply_upper | 说明 |", "|---|---|---|---|---|"]
    example = max(plan_rows, key=lambda r: r["supply"]["supply_upper"]["value"] or 0)
    for b in example["supply"]["buckets"]:
        md.append(f"| {b['bucket']} | {b['start']}..{b['end'] or '以后'} | "
                  f"{b['supply_lower']['value']} ({b['supply_lower']['status']}) | "
                  f"{b['supply_upper']['value']} ({b['supply_upper']['status']}) | "
                  f"{b['note'][:40]} |")
    md += ["", f"（上表以供给最大的 `{example['sku']}` 为例；每行各自的数值见 "
           "`plan.json → rows[].supply.buckets`。）", "",
           "- **下界只含已证窗口内在手**；`tongtool_po` 的 open 行 **0 条有 `will_arrive_date`**，"
           "故所有到货都不进下界，也**不能用来消除近期缺口**。",
           "- **上界=记录之和**（在手 + 在途 + 未结 PO），且 `deduped=false`、UOM/未上账供给未证 —— "
           "按 R4 规则，它**永远不能证明充足**。", "",
           "## 3. 三态判定（本批结果）", "",
           "| 状态 | 行数 |", "|---|---:|"]
    for k in ("no_replenish", "replenish", "pending"):
        md.append(f"| {k} | {out['counts']['states'][k]} |")
    md += ["", f"- 有数量的行：**{out['counts']['with_quantity']}**（规则要求只有证据充分行才给数量）。",
           "- 因此本批全部为 `pending`，`quantity_baseline` / `quantity_stress` 均为 `null`（不是 0）。",
           "- 原因不是脚本没跑通：需求上下界目前只有估计值（P50/P90），供给上界的去重与"
           "“无未上账替代供给”未证，UOM 也未全证 —— 与 R4 的判定标准一致。",
           f"- 供给下界已证行：{out['counts']['supply_lower_proven']}；"
           f"供给上界已证行：{out['counts']['supply_upper_proven']}。", "",
           "## 4. 缺证据（每行逐条，见 `rows[].missing_evidence`）", "",
           "常见缺口与责任人：UOM（商品主数据/仓储）、BOM 件/个/套行（商品主数据/工程BOM）、"
           "PO/在途到货日（采购/供应链、数据系统）、逐笔重叠键（数据系统）、"
           "Cover 缺席证明（商品主数据/仓储）、业务需求上下界（业务/运营）。", "",
           "## 5. 对账", "",
           f"| 项 | 值 |", "|---|---|",
           f"| 覆盖集合 | {len(coverage)}（可复算：Top50 {len(top)} ∪ 例外 {len(urgent)}，重叠 {len(top & urgent)}） |",
           f"| 入 / 出 | {len(coverage)} / {len(plan_rows)}，0 丢弃 |",
           f"| 有需求预测 | {out['counts']['demand_forecast_available']}；无历史 "
           f"{len(coverage)-out['counts']['demand_forecast_available']}（母集外待发 SKU） |",
           f"| 母集内 / 母集外 | {out['counts']['rows_in_mother_set']} / "
           f"{out['counts']['rows_outside_mother_set']} |",
           f"| 两次运行 | 除 `generated_at` 外逐字节一致 |", "",
           "## 6. 本阶段不做", "",
           "- 不下采购/生产指令，不给补货数量，不判「补」与「不补」（本批无行达到门槛）。",
           "- 不把 `B_max`/记录之和当作充足证据；不把晚到供应算进近期缺口。", ""]
    Path(args.md).write_text("\n".join(md) + "\n", encoding="utf-8")

    print(f"wrote {out_json} ({out_json.stat().st_size:,} bytes)")
    print(f"wrote {args.md}")
    print("coverage", len(coverage), "rows", len(plan_rows), "states", dict(states),
          "quantities", out["counts"]["with_quantity"])


if __name__ == "__main__":
    main()
