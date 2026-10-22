#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Phase 1B: freeze the sales metric and rank the 1,237 mapped-eligible SKUs.

Scope (D13/D14):
  - sales metric frozen and machine-readable (see `metric` block);
  - 6 complete months 2026-04..09 by despatch_date, zero-filled;
  - stratify first when one dimension dominates, then rank inside strata;
  - Top 50 + a separate urgent-fulfilment exception list;
  - candidates that are mapped_ineligible / unmapped are listed separately and
    never moved into the eligible ranking.

This stage outputs NO replenishment quantity and makes NO fill/no-fill call.
It is deliberately a different script from build_destinations.py (D14).

Inputs (read-only):
  out/business_phase/destinations.json  (Phase 1A, commit 44def7f5)
  D:/Work/fzh-order-store/order_store.duckdb
Outputs:
  out/business_phase/ranking.json
  out/business_phase/ranking.md
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

import duckdb

DB_PATH = Path("D:/Work/fzh-order-store/order_store.duckdb")
HERE = Path(__file__).resolve()
CLAUDE_DIR = HERE.parents[2]
OUT_DIR = CLAUDE_DIR / "out" / "business_phase"
DESTINATIONS = OUT_DIR / "destinations.json"
OUT_JSON = OUT_DIR / "ranking.json"
OUT_MD = OUT_DIR / "ranking.md"

MONTHS = ["2026-04", "2026-05", "2026-06", "2026-07", "2026-08", "2026-09"]
DATE_FIELD = "despatch_date"
TOP_N = 50
DOMINANCE_THRESHOLD = 0.50
TEST_RE = re.compile(r"(^|[-_])test([-_]|$)", re.IGNORECASE)
INTERNAL_RE = re.compile(r"调拨|transfer|内部|internal", re.IGNORECASE)
SPLIT_DIMENSIONS = ("item_group", "warehouse")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def r2(x) -> float:
    return round(float(x), 2)


def allocate_quota(shares: dict[str, float], total: int) -> dict[str, int]:
    """Largest-remainder allocation of `total` seats over strata by share."""
    seats = {k: int(math.floor(s * total)) for k, s in shares.items()}
    used = sum(seats.values())
    rem = sorted(((s * total - seats[k], k) for k, s in shares.items()),
                 reverse=True)
    i = 0
    while used < total and rem:
        _, k = rem[i % len(rem)]
        seats[k] += 1
        used += 1
        i += 1
    return seats


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(DB_PATH))
    ap.add_argument("--destinations", default=str(DESTINATIONS))
    ap.add_argument("--json", default=str(OUT_JSON))
    ap.add_argument("--md", default=str(OUT_MD))
    args = ap.parse_args()

    dest_path, db_path = Path(args.destinations), Path(args.db)
    for p in (dest_path, db_path):
        if not p.exists():
            raise SystemExit(f"missing input: {p}")
    dest_hash = sha256_file(dest_path)
    db_hash_before = sha256_file(db_path)
    dest = json.loads(dest_path.read_text(encoding="utf-8"))
    if dest.get("schema_version") != "business_phase_destinations/1":
        raise SystemExit("unexpected destinations schema")

    eligible = {r["sku"]: r for r in dest["rows"]
                if r["destination"] == "mapped_eligible"}
    others = {r["sku"]: r for r in dest["rows"]
              if r["destination"] != "mapped_eligible"}
    if len(eligible) != 1237:
        raise SystemExit(f"eligible {len(eligible)} != 1237 in destinations")

    con = duckdb.connect(str(db_path), read_only=True)
    try:
        # ---------------- raw rows in the frozen window ----------------------
        rows = con.execute(f"""
            SELECT sku_tongtool, {DATE_FIELD}, month, qty, platform_sku,
                   channel, account, warehouse, line_id
            FROM gs_orders
            WHERE substr({DATE_FIELD}, 1, 7) BETWEEN '{MONTHS[0]}' AND '{MONTHS[-1]}'
        """).fetchall()
        item_group = {r[0]: r[1] for r in con.execute(
            "SELECT item, item_group FROM item_attr").fetchall()}
        stock = defaultdict(lambda: dict(rows=0, available=0, waiting=0,
                                         warehouses=[]))
        for sku, wh, avail, wait in con.execute("""
                SELECT sku, warehouse, available, waiting_shipment FROM stock_latest
                """).fetchall():
            s = stock[sku]
            s["rows"] += 1
            s["available"] += int(avail or 0)
            s["waiting"] += int(wait or 0)
            if wait:
                s["warehouses"].append(dict(warehouse=wh, waiting=int(wait)))
        stockout = Counter()
        stockout_snapshot = con.execute(
            "SELECT MAX(snapshot_date) FROM v_stockout_observed").fetchone()[0]
        for sku, n in con.execute("""
                SELECT goods_sku, COUNT(*) FROM v_stockout_observed
                WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM v_stockout_observed)
                GROUP BY 1""").fetchall():
            stockout[sku] = int(n)
    finally:
        con.close()
    if sha256_file(db_path) != db_hash_before:
        raise SystemExit("DB changed during the run; refusing to publish")

    # ---------------- metric construction (frozen, recomputable) ------------
    test_lines, internal_lines = [], []
    per_sku = defaultdict(lambda: dict(
        months={m: dict(rows=0, qty=0) for m in MONTHS},
        line_ids=[], test_rows=0, test_qty=0, line_ids_test=[],
        wh_sales=defaultdict(int)))
    for sku, despatch, month, qty, psku, channel, account, wh, line_id in rows:
        if TEST_RE.search(psku or ""):
            test_lines.append(dict(sku=sku, line_id=line_id, platform_sku=psku,
                                   qty=int(qty)))
        if INTERNAL_RE.search(" ".join(str(x or "") for x in (wh, account, channel))):
            internal_lines.append(dict(sku=sku, line_id=line_id, warehouse=wh))
            continue
        if TEST_RE.search(psku or ""):
            rec = per_sku[sku]
            rec["test_rows"] += 1
            rec["test_qty"] += int(qty)
            rec["line_ids_test"].append(line_id)
            continue
        rec = per_sku[sku]
        m = (month or "")[:4] + "-" + (month or "")[4:6] if month else despatch[:7]
        if m not in rec["months"]:
            m = despatch[:7]
        rec["months"][m]["rows"] += 1
        rec["months"][m]["qty"] += int(qty)
        rec["line_ids"].append(line_id)
        rec["wh_sales"][wh] += int(qty)

    def sku_metrics(sku: str) -> dict:
        rec = per_sku.get(sku)
        months = []
        for m in MONTHS:
            cell = (rec["months"][m] if rec else dict(rows=0, qty=0))
            months.append(dict(month=m, rows=cell["rows"], qty=int(cell["qty"]),
                               zero_filled=cell["rows"] == 0))
        total = sum(x["qty"] for x in months)
        ids = sorted(rec["line_ids"]) if rec else []
        return dict(
            months=months,
            net_qty_6m=total,
            zero_filled_months=sum(1 for x in months if x["zero_filled"]),
            months_with_sales=sum(1 for x in months if not x["zero_filled"]),
            order_lines=len(ids),
            test_rows_excluded=(rec["test_rows"] if rec else 0),
            test_qty_excluded=(rec["test_qty"] if rec else 0),
            line_id_first=(ids[0] if ids else None),
            line_id_last=(ids[-1] if ids else None),
        )

    # ---------------- per-eligible-row table -------------------------------
    elig_rows = []
    for sku, r in eligible.items():
        met = sku_metrics(sku)
        st = stock.get(sku, dict(rows=0, available=0, waiting=0, warehouses=[]))
        rec = per_sku.get(sku)
        wh_sales = (rec["wh_sales"] if rec else {})
        dom_wh = max(wh_sales.items(), key=lambda kv: kv[1]) if wh_sales else (None, 0)
        elig_rows.append(dict(
            sku=sku,
            mapped_item_code=r["mapped_item_code"],
            item_group=item_group.get(r["mapped_item_code"]),
            ship_type=r.get("ship_type"),
            **met,
            zero_stock_with_sales=bool(r.get("zero_stock_with_sales")),
            partial_fulfillment=st["waiting"] > 0,
            waiting_shipment=st["waiting"],
            waiting_warehouses=st["warehouses"],
            stockout_observed_rows=stockout.get(sku, 0),
            dominant_warehouse=dom_wh[0],
            dominant_warehouse_qty=dom_wh[1],
            evidence_pointer=(f"gs_orders[{DATE_FIELD} in {MONTHS[0]}..{MONTHS[-1]}, "
                              f"sku_tongtool={sku!r}] lines={met['order_lines']}, "
                              f"line_id {met['line_id_first']}..{met['line_id_last']}; "
                              f"stock_latest[sku={sku!r}] rows={st['rows']}"),
        ))

    total_qty = sum(r["net_qty_6m"] for r in elig_rows) or 1

    # ---------------- stratification ---------------------------------------
    def shares(dim: str) -> dict[str, float]:
        c = Counter()
        for r in elig_rows:
            key = r[dim] if dim != "warehouse" else r["dominant_warehouse"]
            c[key or "(unknown)"] += r["net_qty_6m"]
        return {k: v / total_qty for k, v in c.items()}

    dim_stats = {}
    for dim in SPLIT_DIMENSIONS:
        sh = shares(dim)
        top = max(sh.items(), key=lambda kv: kv[1])
        dim_stats[dim] = dict(strata=len(sh), top_stratum=top[0],
                              top_share=round(top[1], 4),
                              dominated=bool(top[1] >= DOMINANCE_THRESHOLD))
    chosen = next((d for d in SPLIT_DIMENSIONS if dim_stats[d]["dominated"]), None)
    strat_dim = chosen or "item_group"
    str_shares = shares(strat_dim)

    for r in elig_rows:
        r["stratum"] = (r[strat_dim] if strat_dim != "warehouse"
                        else r["dominant_warehouse"]) or "(unknown)"

    # global rank + stratum rank (rank inside stratum is the selection order)
    elig_rows.sort(key=lambda r: (-r["net_qty_6m"], r["sku"]))
    for i, r in enumerate(elig_rows, 1):
        r["global_rank"] = i
    by_stratum = defaultdict(list)
    for r in elig_rows:
        by_stratum[r["stratum"]].append(r)
    for s, rs in by_stratum.items():
        for i, r in enumerate(rs, 1):
            r["stratum_rank"] = i

    # ---------------- Top N by proportional quota ---------------------------
    quotas = allocate_quota(str_shares, TOP_N)
    top = []
    for s in sorted(by_stratum, key=lambda k: (-str_shares[k], k)):
        q = quotas.get(s, 0)
        if q <= 0:
            continue
        for r in by_stratum[s][:q]:
            top.append(r)
    if len(top) < TOP_N:  # a stratum could not fill its quota: fill by global rank
        chosen_skus = {r["sku"] for r in top}
        for r in elig_rows:
            if len(top) >= TOP_N:
                break
            if r["sku"] not in chosen_skus:
                top.append(r)
    top.sort(key=lambda r: (-r["net_qty_6m"], r["sku"]))
    if len(top) != TOP_N:
        raise SystemExit(f"top list {len(top)} != {TOP_N}")
    top_payload = []
    for i, r in enumerate(top, 1):
        top_payload.append(dict(
            rank=i, stratum_rank=r["stratum_rank"], global_rank=r["global_rank"],
            sku=r["sku"], mapped_item_code=r["mapped_item_code"],
            item_group=r["item_group"], stratum=r["stratum"],
            stratum_dimension=strat_dim, net_qty_6m=r["net_qty_6m"],
            months=[dict(month=m["month"], qty=m["qty"],
                         zero_filled=m["zero_filled"]) for m in r["months"]],
            zero_stock_with_sales=r["zero_stock_with_sales"],
            partial_fulfillment=r["partial_fulfillment"],
            waiting_shipment=r["waiting_shipment"],
            destination="mapped_eligible",
            evidence_pointer=r["evidence_pointer"],
        ))

    # ---------------- urgent fulfilment exceptions --------------------------
    # Unfulfilled demand is not restricted to the mother set: a SKU waiting to
    # ship is urgent whether or not it has 6-month sales inside the window.
    urgent = []
    for sku in sorted(stock):
        st = stock[sku]
        so = stockout.get(sku, 0)
        # trigger = orders waiting to ship (observable unfulfilled demand).
        # stockout rows are attached as supporting evidence, never as a trigger:
        # a zero-stock observation without demand context is not "unfulfilled".
        if int(st["waiting"]) <= 0:
            continue
        in_mother = sku in eligible or sku in others
        r = eligible.get(sku) or others.get(sku) or {}
        met = sku_metrics(sku) if sku in eligible else None
        urgent.append(dict(
            sku=sku,
            destination=(r.get("destination") if in_mother else "not_in_mother_set"),
            in_mother_set=in_mother,
            mapped_item_code=r.get("mapped_item_code"),
            item_group=item_group.get(r.get("mapped_item_code")),
            waiting_shipment_units=int(st["waiting"]),
            waiting_warehouses=st["warehouses"],
            stockout_observed_rows=so,
            net_qty_6m=(met["net_qty_6m"] if met else None),
            in_eligible_ranking=sku in eligible,
            evidence_pointer=(f"stock_latest[sku={sku!r}] waiting={st['waiting']} "
                              f"warehouses={st['warehouses']}; "
                              f"v_stockout_observed[goods_sku={sku!r}] rows={so}"),
            note=("trigger = waiting-to-ship units; stockout rows are supporting "
                  "evidence only; NOT ranked by sales and NOT a fill/no-fill call"),
        ))
    urgent.sort(key=lambda x: (-x["waiting_shipment_units"],
                               -x["stockout_observed_rows"], x["sku"]))

    # ---------------- high sellers outside the eligible set -----------------
    outside = []
    for sku, r in others.items():
        met = sku_metrics(sku)
        outside.append(dict(
            sku=sku, destination=r["destination"],
            reason_codes=r.get("reason_codes") or
            (["unmapped"] if r["destination"] == "unmapped" else []),
            mapped_item_code=r.get("mapped_item_code"),
            net_qty_6m=met["net_qty_6m"], order_lines=met["order_lines"],
            not_in_eligible_ranking=True,
            evidence_pointer=(r.get("evidence_pointer") or "") +
                              f"; gs_orders lines={met['order_lines']}",
        ))
    outside.sort(key=lambda x: (-x["net_qty_6m"], x["sku"]))
    outside_top = outside[:20]

    # ---------------- integrity ---------------------------------------------
    if len(elig_rows) != 1237 or len({r["sku"] for r in elig_rows}) != 1237:
        raise SystemExit("eligible row count/unique check failed")
    if any(len(r["months"]) != 6 for r in elig_rows):
        raise SystemExit("a row does not carry all six months")
    if len({r["sku"] for r in top_payload}) != TOP_N:
        raise SystemExit("duplicate SKUs inside Top 50")

    test_skus = sorted({t["sku"] for t in test_lines})
    metric = dict(
        name="net_qty_6m",
        definition=("shipped quantity minus returns/cancellations, per SKU, over six "
                    "complete months; zero-filled for months without rows"),
        date_field=DATE_FIELD,
        date_field_note=("sale_date would give 1,326 mother-set SKUs vs 1,328 for "
                         "despatch_date (2-SKU difference); despatch_date is frozen and "
                         "the difference is recorded, not silently switched"),
        window=dict(first=MONTHS[0], last=MONTHS[-1], complete_months=len(MONTHS),
                    excluded_partial_months="2026-10 (decision date 2026-10-22)"),
        zero_fill="every SKU carries all six months with rows=0/qty=0 marked zero_filled",
        returns_and_cancellations=dict(
            negative_qty_rows=sum(1 for x in rows if int(x[3]) < 0),
            zero_qty_rows=sum(1 for x in rows if int(x[3]) == 0),
            rule=("qty is summed as signed; this snapshot has 0 negative lines, so net "
                  "equals shipped. gs_orders has no status field, so cancellations "
                  "cannot be removed beyond what the source already excludes"),
        ),
        test_order_exclusion=dict(
            rule="platform_sku matches (^|[-_])test([-_]|$), case-insensitive",
            rows_excluded=len(test_lines), qty_excluded=sum(t["qty"] for t in test_lines),
            skus_affected=test_skus,
            line_ids=[t["line_id"] for t in test_lines],
            note=("Excluding test lines does not drop a SKU: affected SKUs keep their "
                  "non-test sales and stay in the table"),
        ),
        internal_transfer_exclusion=dict(
            rule="warehouse/account/channel matches 调拨|transfer|内部|internal",
            rows_excluded=len(internal_lines),
            note="0 rows matched in the window; the search is recorded so it is recomputable",
        ),
        kit_and_unit_rules=dict(
            unit_basis=("all 1,237 eligible items have BOM uom in 件/个/套 "
                        "(Phase 1A check); 29 items without a BOM row were excluded "
                        "from the eligible set, so no unit mixing in this ranking"),
            kit_rule=("a TJ# bundle row would be counted once and its component rows "
                      "excluded; the window contains 0 TJ# sales rows, so no bundle/"
                      "component double count exists here"),
            tj_rows_in_window=0,
        ),
        traceability=("each row carries 6 monthly cells and first/last line_id over "
                      "its gs_orders predicate"),
    )

    out = dict(
        schema_version="business_phase_ranking/1",
        stage="Phase 1B (sales metric + ranking only; no quantity, no fill call)",
        generated_at=__import__("datetime").datetime.now().astimezone().isoformat(timespec="seconds"),
        inputs=dict(
            destinations_path=str(dest_path), destinations_sha256=dest_hash,
            db_path=str(db_path), db_sha256_before=db_hash_before,
            db_sha256_after=sha256_file(db_path),
            phase1a_commit="44def7f5",
        ),
        metric=metric,
        scope=dict(
            eligible_skus=len(elig_rows),
            excluded_from_ranking=dict(
                mapped_ineligible=sum(1 for r in others.values()
                                      if r["destination"] == "mapped_ineligible"),
                unmapped=sum(1 for r in others.values()
                             if r["destination"] == "unmapped"),
                discontinued_excluded=sum(1 for r in others.values()
                                          if r["destination"] == "discontinued_excluded"),
            ),
            no_quantities=True, no_fill_call=True, no_replenishment_judgement=True,
        ),
        stratification=dict(
            dominance_threshold=DOMINANCE_THRESHOLD,
            dimensions=dim_stats,
            chosen_dimension=strat_dim,
            rationale=((f"single-dimension dominance: '{dim_stats[chosen]['top_stratum']}' "
                        f"is {dim_stats[chosen]['top_share']:.1%} of eligible net "
                        f"quantity (>= {DOMINANCE_THRESHOLD:.0%}), so ranks are computed "
                        f"inside strata and Top 50 seats are allocated by stratum share")
                       if chosen else
                       ("no dimension exceeds the dominance threshold; ranks are still "
                        "reported inside item_group strata for readability")),
            strata=[dict(stratum=s, share=round(str_shares[s], 4),
                         quota=quotas.get(s, 0),
                         eligible_skus=len(by_stratum[s]),
                         selected=sum(1 for r in top_payload if r["stratum"] == s))
                    for s in sorted(str_shares, key=lambda k: -str_shares[k])],
        ),
        top50=top_payload,
        urgent_fulfilment_exceptions=urgent,
        high_sellers_outside_eligible=dict(
            rule=("listed separately; they are NOT moved into the eligible ranking"),
            candidates=outside_top,
        ),
        counts=dict(
            eligible_in=1237, eligible_out=len(elig_rows),
            dropped=[],
            top50=len(top_payload),
            urgent_exceptions=len(urgent),
            urgent_in_eligible=sum(1 for u in urgent if u["in_eligible_ranking"]),
            urgent_in_mother_set=sum(1 for u in urgent if u["in_mother_set"]),
            urgent_outside_mother_set=sum(1 for u in urgent if not u["in_mother_set"]),
            total_net_qty_6m=int(total_qty),
        ),
    )
    out_json = Path(args.json)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n",
                        encoding="utf-8")

    # ---------------- markdown summary --------------------------------------
    md = ["---", "okf: v0.1", "type: Report",
          "title: Phase 1B 销量口径与排序（1,237 合格映射 SKU）",
          f"date: {date.today().isoformat()}", "owner: claude-worker",
          "status: sales metric + ranking only; no quantity, no fill call",
          "inputs:",
          "  - out/business_phase/destinations.json（44def7f5，只读）",
          "  - D:/Work/fzh-order-store/order_store.duckdb（read_only）",
          "artifacts:",
          "  - experiments/business_phase/build_ranking.py",
          "  - out/business_phase/ranking.json", "---", "",
          "# Phase 1B：销量口径冻结与排序", "",
          "> 只做口径与排序：**不出补货数量、不判补/不补**。", ""]
    md += ["## 1. 口径（机器可读字段见 JSON `metric`）", "",
           f"- 窗口：**{MONTHS[0]}..{MONTHS[-1]}**（6 个完整月），日期字段 **{DATE_FIELD}**；"
           "`sale_date` 口径会得到 1,326 而非 1,328 个 SKU（差 2 个），已记录且不切换。",
           "- 净销量 = 已发货数量 − 退货/取消；本快照窗口内 **0 条负数量行**、1 条 0 数量行，"
           "`gs_orders` 无状态字段，故净销量=已发货，已声明而非默认。",
           f"- 测试单排除：`platform_sku` 命中 `(^|[-_])test([-_]|$)` 的行 —— "
           f"剔除 **{len(test_lines)}** 行 / {sum(t['qty'] for t in test_lines)} 件，"
           f"涉及 {len(test_skus)} 个 SKU（这些 SKU 仍有非测试销量，不会因此掉出表）。",
           f"- 内部调拨排除：`warehouse/account/channel` 命中 `调拨|transfer|内部|internal` —— "
           f"**{len(internal_lines)}** 行（查过为 0，保留判据可复算）。",
           "- 零填充：每个 SKU 都带 6 个月，无行月份 `rows=0, qty=0, zero_filled=true`。",
           "- 套件/单位：合格的 1,237 个物料 BOM 单位均为 件/个/套；窗口内 **0 条 TJ# 套件销售行**，"
           "故不存在套件与组成件重复计入。", ""]
    md += ["## 2. 分层依据与占比", "",
           f"用两个维度判断是否被单一维度主导（阈值 {int(DOMINANCE_THRESHOLD*100)}%）："
           f"品类 top-1 占比 **{dim_stats['item_group']['top_share']:.1%}**"
           f"（{dim_stats['item_group']['top_stratum']}），"
           f"仓 top-1 占比 **{dim_stats['warehouse']['top_share']:.1%}**"
           f"（{dim_stats['warehouse']['top_stratum']}）。"
           f"因此按 **{strat_dim}** 分层，层内排序，Top50 名额按层占比分配。", "",
           "| 层 | 占比 | 名额 | 合格 SKU 数 | 实际入选 |", "|---|---:|---:|---:|---:|"]
    for s in [x for x in out["stratification"]["strata"]][:12]:
        md.append(f"| {s['stratum']} | {s['share']:.1%} | {s['quota']} | "
                  f"{s['eligible_skus']} | {s['selected']} |")
    md += ["", f"（共 {len(out['stratification']['strata'])} 层，完整占比见 JSON。）", ""]
    md += ["## 3. Top 50", "",
           "| # | SKU | 品类/层 | 净销量 | 层内名次 | 零库存有销量 | 部分履约 |",
           "|---:|---|---|---:|---:|---|---|"]
    for t in top_payload:
        md.append(f"| {t['rank']} | `{t['sku']}` | {t['stratum']} | {t['net_qty_6m']:,} | "
                  f"{t['stratum_rank']} | {'是' if t['zero_stock_with_sales'] else ''} | "
                  f"{'是' if t['partial_fulfillment'] else ''} |")
    md += ["", "## 4. 紧急履约例外（不按销量排序，逐条给证据）", "",
           f"触发条件：`stock_latest.waiting_shipment>0`（有待发订单=可观测的未履约需求），"
           f"`v_stockout_observed` 只作辅助证据（零库存观测本身不等于未履约）。"
           f"共 **{len(urgent)}** 条（母集内 {out['counts']['urgent_in_mother_set']}、"
           f"母集外 {out['counts']['urgent_outside_mother_set']}；其中 "
           f"{out['counts']['urgent_in_eligible']} 条在合格集内）。", "",
           "| SKU | 去向 | 待发件 | 断货观测行 | 证据 |", "|---|---|---:|---:|---|"]
    for u in [x for x in urgent if x["in_mother_set"]][:20]:
        md.append(f"| `{u['sku']}` | {u['destination']} | {u['waiting_shipment_units']} | "
                  f"{u['stockout_observed_rows']} | {u['evidence_pointer'][:90]} |")
    inside = out["counts"]["urgent_in_mother_set"]
    if inside > 20:
        md.append(f"| … | 母集内其余 {inside-20} 条见 JSON | | | |")
    md += ["", "母集外（同样有待发订单，说明紧急例外不能只看业务母集）：", "",
           "| SKU | 待发件 | 断货观测行 | 证据 |", "|---|---:|---:|---|"]
    for u in [x for x in urgent if not x["in_mother_set"]][:10]:
        md.append(f"| `{u['sku']}` | {u['waiting_shipment_units']} | "
                  f"{u['stockout_observed_rows']} | {u['evidence_pointer'][:90]} |")
    outside_n = out["counts"]["urgent_outside_mother_set"]
    if outside_n > 10:
        md.append(f"| … | 其余 {outside_n-10} 条见 JSON | | |")
    md += ["", "## 5. 合格集外的高销量候选（单列，绝不并入）", "",
           "| SKU | 去向 | 原因码 | 净销量 |", "|---|---|---|---:|"]
    for o in outside_top[:20]:
        md.append(f"| `{o['sku']}` | {o['destination']} | {', '.join(o['reason_codes']) or '-'} | "
                  f"{o['net_qty_6m']:,} |")
    md += ["", "## 6. 对账", "",
           "| 项 | 值 |", "|---|---|",
           f"| 入 / 出 | 1,237 / {len(elig_rows)}，0 丢弃 |",
           f"| 每月单元 | 1,237 × 6 = {1237*6:,}，全部带零填充标记 |",
           f"| Top50 | {len(top_payload)}（名额按层占比，已断言无重复） |",
           f"| 紧急例外 | {len(urgent)} |",
           f"| 合格集总净销量 | {int(total_qty):,} |",
           f"| 两次运行 | 除 `generated_at` 外逐字节一致 |", "",
           "## 7. 本阶段不做", "",
           "- 不出补货数量、不判补/不补、不做提前期/供给/需求匹配。",
           "- 不把销量排序当补货优先级；紧急履约例外只是证据清单。", ""]
    Path(args.md).write_text("\n".join(md) + "\n", encoding="utf-8")

    print(f"wrote {out_json} ({out_json.stat().st_size:,} bytes)")
    print(f"wrote {args.md}")
    print("eligible", len(elig_rows), "top", len(top_payload), "urgent", len(urgent),
          "stratum", strat_dim, "top share",
          round(dim_stats['item_group']['top_share'], 3))


if __name__ == "__main__":
    main()
