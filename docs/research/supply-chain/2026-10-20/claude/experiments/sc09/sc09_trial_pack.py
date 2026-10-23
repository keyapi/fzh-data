#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""SC09 业务试用包（只读汇总，不造新数字）。

只用两个已 PASS 的产物：
  * 前向账 `19fb2c6e` → `out/business_phase/forward_net_rows.csv`（2,309 = 条件 2,058 + HOLD 251）
  * 分路核验 `59c4e5ec` → `out/business_phase/dn_split*.csv`（本轮只引用其结论，不重算）

本脚本只做三件事：
  1) 把前向账转成**业务可复核的条件清单**（SKU×仓逐行），补：需要时间 / 能否赶上 / 解释 / 缺证项 / 复核人空栏；
  2) 报覆盖：全母集覆盖 + 销量覆盖（按 条件 / HOLD 分）；
  3) 把 SC10 的 271 个扩展候选做成**三项评审状态表**（映射/UOM/库存），未过单列，
     **绝不**把 271 合成任何可执行数量。

不重算预测、不改任何上游产物、不出采购量。

输出（本地）：
  out/business_phase/sc09/sc09_trial_rows.csv
  out/business_phase/sc09/sc09_extension_candidates.csv
  out/business_phase/sc09/sc09_trial_pack.json
"""
from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

import duckdb

CLAUDE = Path(__file__).resolve().parents[2]
BP = CLAUDE / "out" / "business_phase"
OUT = BP / "sc09"
OUT.mkdir(parents=True, exist_ok=True)
SC10_ROWS = CLAUDE / "out" / "sc10" / "sc10_catalog_rows.csv"
DB = Path("D:/Work/fzh-order-store/order_store.duckdb")
PERIODS = ["2026-10 剩余", "2026-11", "2026-12"]


def main() -> None:
    rows = list(csv.DictReader((BP / "forward_net_rows.csv").open(encoding="utf-8-sig", newline="")))
    buckets = list(csv.DictReader((BP / "forward_net_buckets.csv").open(encoding="utf-8-sig", newline="")))

    # 每个 (sku, warehouse) 首个未履约桶 = 需要时间
    first_gap = {}
    for b in buckets:
        key = (b["sku"], b["warehouse"], b["scenario_id"])
        if float(b["unserved"] or 0) > 0:
            cur = first_gap.get(key)
            if cur is None or PERIODS.index(b["bucket"]) < PERIODS.index(cur):
                first_gap[key] = b["bucket"]

    def gap_of(r):
        """空值 = 不可算（HOLD 证据不足），绝不能当 0。"""
        if r["gap_low"] in ("", None) or r["gap_high"] in ("", None):
            return None, None
        # 先按展示精度取整，保证「显示 0.0」与「判定为无缺口」一致
        return round(float(r["gap_low"]), 2), round(float(r["gap_high"]), 2)

    def needs_time(r):
        k = (r["sku"], r["warehouse"], r["scenario_id"])
        low, high = gap_of(r)
        if high is None:
            return "不可算（证据不足）"
        if high <= 0:
            return "窗口内无缺口"
        return first_gap.get(k, "2026-12（累计）")

    def missing(r):
        m = []
        if r["inventory_basis"] == "unknown":
            m.append("库存口径未证(physical/net 并列)")
        if r["wo_status"] == "not_observed":
            m.append("无 WO/在制证据")
        if r["overlap_proven"] == "unknown":
            m.append("SO 与预测重叠未证")
        if r["dedupe_state"] == "none_recorded":
            m.append("PO/WO/在途去重无记录")
        if r["rate_clamped"] == "1":
            m.append("负率已钳 0（原值见 forecast_rate_raw）")
        return "；".join(m) or "无"

    pack = []
    for r in rows:
        low, high = gap_of(r)
        # 上游语义：gap_low = max(onhand) = 悲观端（更大）；gap_high = min(onhand) = 乐观端（更小）。
        # 对外一律按**数值升序**展示，避免出现 "42.4 ~ 38.4" 的倒挂。
        if high is None:
            qmin = qmax = None
            suggested = "不可算（证据不足）"
        else:
            qmin, qmax = min(low, high), max(low, high)
            suggested = f"{qmin:.1f}" if abs(qmax - qmin) < 1e-9 else f"{qmin:.1f} ~ {qmax:.1f}"
        pack.append(dict(
            sku=r["sku"], warehouse=r["warehouse"],
            suggested_qty_or_range=suggested,
            qty_min=(round(qmin, 2) if qmin is not None else ""),
            qty_max=(round(qmax, 2) if qmax is not None else ""),
            gap_low_raw=(round(low, 2) if low is not None else ""),
            gap_high_raw=(round(high, 2) if high is not None else ""),
            need_time=needs_time(r),
            can_make_it="无法判断（无 ETA/在途证据，WO not_observed）",
            forecast_basis=f"{r['demand_source']} / {r['method']} / {r['version']}",
            forecast_rate=float(r["forecast_rate"] or 0),
            rate_clamped=r["rate_clamped"],
            fallback_reason=r["fallback_reason"],
            stock_basis=f"{r['inventory_basis']} (available={r['stock_available']}, physical={r['stock_physical']})",
            so_unfulfilled=float(r["so_unfulfilled"] or 0),
            so_allocation=r["so_allocation"],
            scenario_id=r["scenario_id"],
            assumptions=r["assumptions"],
            missing_evidence=missing(r),
            readiness=r["readiness"],
            reviewer="",                     # 复核人空栏
            reviewer_note="",
        ))
    with (OUT / "sc09_trial_rows.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(pack[0].keys()))
        w.writeheader()
        w.writerows(pack)

    # ---- 覆盖：全母集 SKU + 销量 -------------------------------------------
    con = duckdb.connect(str(DB), read_only=True)
    try:
        sales = {r[0]: float(r[1] or 0) for r in con.execute("""
            SELECT sku_tongtool, sum(qty) FROM gs_orders
            WHERE channel IS NOT NULL AND despatch_date >= '2026-04-01' AND despatch_date <= '2026-09-30'
            GROUP BY 1""").fetchall()}
        bom_uom = defaultdict(set)
        for it, u in con.execute("SELECT item, uom FROM bom").fetchall():
            bom_uom[it].add(u)
        dis = {r[0] for r in con.execute(
            "SELECT item_code FROM nd_status WHERE CAST(disabled AS VARCHAR) IN ('1','True','true')").fetchall()}
    finally:
        con.close()

    mother = {r["sku"] for r in rows}
    total_sales = sum(sales.get(s, 0) for s in mother)
    cond_skus = {r["sku"] for r in rows if r["readiness"] == "条件"}
    hold_skus = {r["sku"] for r in rows if r["readiness"] == "HOLD"}
    coverage = dict(
        mother_skus=len(mother),
        covered_skus=len(mother),                       # 母集 100% 有行
        rows=len(rows),
        warehouses=len({r["warehouse"] for r in rows}),
        conditional=dict(rows=sum(1 for r in rows if r["readiness"] == "条件"),
                         skus=len(cond_skus),
                         sales_qty=round(sum(sales.get(s, 0) for s in cond_skus), 1),
                         sales_share=(round(sum(sales.get(s, 0) for s in cond_skus) / total_sales, 4)
                                      if total_sales else None)),
        hold=dict(rows=sum(1 for r in rows if r["readiness"] == "HOLD"),
                  skus=len(hold_skus),
                  sales_qty=round(sum(sales.get(s, 0) for s in hold_skus), 1),
                  sales_share=(round(sum(sales.get(s, 0) for s in hold_skus) / total_sales, 4)
                               if total_sales else None)),
        mother_sales_qty_2026_04_09=round(total_sales, 1),
        note="销量 = gs_orders 全渠道 despatch 2026-04-01..2026-09-30；同一 SKU 可能同时出现在两档",
    )

    # ---- SC10 的 271 个扩展候选：三项评审（只准备，不并入） -------------------
    ext_lines = []
    if SC10_ROWS.exists():
        sc10 = list(csv.DictReader(SC10_ROWS.open(encoding="utf-8-sig", newline="")))
        cands = [r for r in sc10 if r["enter_next_mother"] == "yes"]
        for c in cands:
            ics = [x for x in c["item_codes"].split("|") if x]
            m_ok = (len(ics) == 1 and ics[0] not in dis)
            uoms = set()
            for ic in ics:
                uoms |= bom_uom.get(ic, set())
            u_ok = bool(uoms) and uoms <= {"个", "件", "套"}
            s_ok = float(c["stock_available"] or 0) > 0 and False   # uom_basis 全 unknown -> 不过
            ext_lines.append(dict(
                sku=c["sku"], item_code="|".join(ics), stock_available=c["stock_available"],
                review_mapping=("pass" if m_ok else "FAIL" +
                                ("(多码)" if len(ics) > 1 else "(停用/无码)")),
                review_uom=("pass:" + "|".join(sorted(uoms)) if u_ok else
                            ("FAIL(无BOM单位)" if not uoms else "FAIL(非件类:" + "|".join(sorted(uoms)) + ")")),
                review_stock=("FAIL(单位口径未证)" if s_ok is False else "pass"),
                all_pass=("no" if not (m_ok and u_ok and s_ok) else "yes"),
                note="只做准备；未过项不并入任何可执行数量",
            ))
    with (OUT / "sc09_extension_candidates.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(ext_lines[0].keys()))
        w.writeheader()
        w.writerows(ext_lines)

    ext = dict(
        n=len(ext_lines),
        mapping_pass=sum(1 for r in ext_lines if r["review_mapping"] == "pass"),
        uom_pass=sum(1 for r in ext_lines if r["review_uom"].startswith("pass")),
        stock_pass=sum(1 for r in ext_lines if r["review_stock"] == "pass"),
        all_pass=sum(1 for r in ext_lines if r["all_pass"] == "yes"),
        failed_uom=[dict(sku=r["sku"], why=r["review_uom"]) for r in ext_lines
                    if not r["review_uom"].startswith("pass")][:50],
        note="271 个候选**不并入**可执行数量；库存项因 uom_basis 全 unknown 一律未过",
    )

    payload = dict(
        schema_version="sc09_trial_pack/1",
        sources=dict(forward="forward_net_rows.csv @19fb2c6e (2,309 = 条件2,058 + HOLD251)",
                     split="dn_split @59c4e5ec（只引用结论）",
                     extension="sc10_catalog_rows.csv（271 候选）"),
        coverage=coverage,
        readiness=dict(Counter(r["readiness"] for r in rows)),
        gaps=dict(rows_with_gap=sum(1 for r in pack
                                    if r["qty_max"] != "" and float(r["qty_max"]) > 0),
                  rows_with_range=sum(1 for r in pack
                                      if r["qty_min"] != "" and r["qty_min"] != r["qty_max"]),
                  rows_not_computable=sum(1 for r in pack if r["qty_max"] == ""),
                  max_gap=round(max(float(r["qty_max"]) for r in pack if r["qty_max"] != ""), 2),
                  need_time=dict(Counter(r["need_time"] for r in pack
                                         if r["qty_max"] != "" and float(r["qty_max"]) > 0))),
        scenario=dict(Counter(r["scenario_id"] for r in rows)),
        missing_evidence=dict(Counter(r["missing_evidence"].split("；")[0] for r in pack)),
        extension=ext,
        boundaries=[
            "只汇总已 PASS 产物，未重算预测、未改上游文件。",
            "B 情景 ≠ 采购批准：本清单一律是条件/研究口径，不含可下单量。",
            "能否赶上：全部为无法判断——无 ETA/在途/WO 证据。",
            "271 个扩展候选只作准备，未过项单列，未合成任何数量。",
        ],
    )
    (OUT / "sc09_trial_pack.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps({k: payload[k] for k in ("coverage", "readiness", "gaps", "scenario", "extension")},
                     ensure_ascii=False, indent=1)[:3500])


if __name__ == "__main__":
    main()
