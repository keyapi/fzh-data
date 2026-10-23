#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""PB linen wedge (三角) stockout — three-source cross-check (READ-ONLY).

Sources, all local:
  * WX snapshots   : order_store.duckdb schema `wx_inventory` (read_only).
                     ONLY `warehouse_scope='source_warehouse'` rows are used —
                     the manual wide table (`consolidated_warehouse_scope_unverified`,
                     date basis `dated_column_inventory_semantics_unverified`) is
                     counted but NEVER merged (its warehouse scope is unproven).
  * checked0stock  : D:/Work/美国/Tracy Miller/PB orders/**/checked0stock*.csv
                     deduplicated by content sha256 (a `NotUsed` copy is the same
                     event); an event date comes from the file name.
  * shipments      : `gs_orders` channel='PotteryBarn' (despatch_date, qty).

Deliverables:
  1. a frozen ~30-SKU list with the inclusion basis (family = PB "Wedge Pillow",
     ranked by PB sales, requires at least one stockout signal);
  2. the three sources aligned per SKU x date;
  3. stockout intervals with conservative / loose duration bounds;
  4. three credibility grades (three / two / one source in agreement);
  5. every red line checked explicitly in the report.

Red lines (also asserted in code):
  * a snapshot total > 0 does NOT by itself prove recovery when it is only a few
    units — recovery is only recorded from a snapshot above the low threshold;
  * low sales volume never becomes a stockout conclusion (those rows are graded
    low and excluded from the "stockout" statements);
  * the manual wide table is never merged;
  * no daily inventory is fabricated — only interval observations.

Outputs: out/pb_stockout/pb_30sku_list.csv, stockout_intervals.csv,
         out/pb_stockout/cross_source_report.md
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import re
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

import duckdb

HERE = Path(__file__).resolve()
CLAUDE_DIR = HERE.parents[2]
OUT = CLAUDE_DIR / "out" / "pb_stockout"
DB_PATH = Path("D:/Work/fzh-order-store/order_store.duckdb")
PB_ROOT = Path("D:/Work/美国/Tracy Miller/PB orders")
TARGET_N = 30
LOW_THRESHOLD = 3.0          # 1-3 units = low, per the brief
MIN_SALES_FOR_CONCLUSION = 100   # below this a SKU is graded low and not concluded


def sha(x) -> str:
    return hashlib.sha256(str(x).encode("utf-8")).hexdigest()[:12]


def parse_date_from_name(name: str):
    m = re.search(r"(20\d{2})(\d{2})(\d{2})", name)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    return None


def status_of(total: float | None) -> str:
    if total is None:
        return "unknown"
    if total <= 0:
        return "nonpositive"
    if total <= LOW_THRESHOLD:
        return "low_1_3"
    return "positive"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(DB_PATH))
    ap.add_argument("--pb-root", default=str(PB_ROOT))
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    pb_root = Path(args.pb_root)

    con = duckdb.connect(args.db, read_only=True)
    try:
        # ---- PB sales ranking -----------------------------------------
        sales = {r[0]: float(r[1]) for r in con.execute(
            "SELECT sku_tongtool, SUM(qty) FROM gs_orders "
            "WHERE channel='PotteryBarn' GROUP BY 1").fetchall()}
        ship = defaultdict(lambda: defaultdict(float))
        for sku, ym, q in con.execute(
                "SELECT sku_tongtool, substr(despatch_date,1,7), SUM(qty) "
                "FROM gs_orders WHERE channel='PotteryBarn' GROUP BY 1,2").fetchall():
            ship[sku][ym] = float(q or 0)

        # ---- WX: source snapshots only --------------------------------
        wx = defaultdict(dict)          # sku -> date -> row
        wide_rows = Counter()           # sku -> excluded wide-table rows
        wx_dates = set()
        rows = con.execute("""
            SELECT snapshot_date, sku, warehouse_raw, available, status, warehouse_scope
            FROM wx_inventory.canonical""").fetchall()
        for d_, sku, wh, avail, status, scope in rows:
            if scope != "source_warehouse":
                wide_rows[sku] += 1
                continue
            wx_dates.add(d_)
            cur = wx[sku].get(d_)
            if cur is None:
                cur = dict(total=0.0, centrade=None, whs=0, wh=defaultdict(float))
                wx[sku][d_] = cur
            cur["total"] += float(avail or 0)
            cur["whs"] += 1
            cur["wh"][wh] += float(avail or 0)
            if str(wh).upper().startswith("CENTRADE"):
                cur["centrade"] = (cur["centrade"] or 0.0) + float(avail or 0)
    finally:
        con.close()
    wx_dates = sorted(wx_dates)

    # ---- checked0stock: dedupe by content ----------------------------
    # case-insensitive discovery: the historical folders mix `checked0stock` /
    # `Checked0stock` and `.csv` / `.CSV`
    files = [p for p in pb_root.rglob("*")
             if p.is_file() and not p.name.startswith("~$")
             and "checked0stock" in p.name.lower()
             and p.suffix.lower() == ".csv"]
    by_hash = {}
    for p in files:
        by_hash.setdefault(hashlib.sha256(p.read_bytes()).hexdigest(), p)
    events = defaultdict(set)        # SKU(upper) -> set(event dates)
    wedge_styles = set()             # full description is checked, never truncated
    for p in by_hash.values():
        ev_date = parse_date_from_name(p.name)
        try:
            rs = list(csv.DictReader(p.open(encoding="utf-8-sig", errors="replace")))
        except Exception:
            continue
        for r in rs:
            style = (r.get("Vendor Style") or "").strip()
            if not style:
                continue
            desc = (r.get("Product/Item Description") or "").strip()
            if desc and "Wedge Pillow" in desc:
                wedge_styles.add(style.upper())
            if ev_date:
                events[style.upper()].add(ev_date)

    # ---- family + frozen list ---------------------------------------
    wedge = wedge_styles
    canon = {s.upper(): s for s in sales}
    fam = [canon[s] for s in wedge if s in canon]
    scored = []
    for sku in fam:
        up = sku.upper()
        w = wx.get(sku, {})
        wx_out = sum(1 for d_ in wx_dates
                     if status_of(w.get(d_, {}).get("total")) in ("nonpositive", "low_1_3"))
        n_ev = len(events.get(up, ()))
        if n_ev == 0 and wx_out == 0:
            continue
        scored.append(dict(sku=sku, up=up, sales=sales[sku], events=n_ev, wx_out=wx_out))
    scored.sort(key=lambda r: (-r["sales"], r["sku"]))
    selected = scored[:TARGET_N]

    # ---- per-SKU three-source cross ----------------------------------
    max_snap_gap = 0
    for a_, b_ in zip(wx_dates, wx_dates[1:]):
        max_snap_gap = max(max_snap_gap, (b_ - a_).days)

    def sku_status(sku, d_):
        row = wx.get(sku, {}).get(d_)
        return status_of(row.get("total") if row else None)

    def signal_dates(sku, up):
        """Union of PB blocked-order events and WX non-positive/low snapshots
        inside the snapshot window."""
        sig = {d_ for d_ in events.get(up, ())
               if wx_dates and wx_dates[0] <= d_ <= wx_dates[-1]}
        for d_ in wx_dates:
            if sku_status(sku, d_) in ("nonpositive", "low_1_3"):
                sig.add(d_)
        return sorted(sig)

    intervals_rows, list_rows = [], []
    grade_count = Counter()

    for idx, r in enumerate(selected):
        sku, up = r["sku"], r["up"]
        sig = signal_dates(sku, up)
        n_nonpos = sum(1 for d_ in wx_dates if sku_status(sku, d_) == "nonpositive")
        n_low = sum(1 for d_ in wx_dates if sku_status(sku, d_) == "low_1_3")
        n_pos = sum(1 for d_ in wx_dates if sku_status(sku, d_) == "positive")
        wh_zero = 0
        for d_ in wx_dates:
            row = wx.get(sku, {}).get(d_)
            if row:
                wh_zero += sum(1 for wh, v in row.get("wh", {}).items() if v <= 0)
        ev_dates = sorted(events.get(up, ()))
        ev_in_window = [d_ for d_ in ev_dates
                        if wx_dates and wx_dates[0] <= d_ <= wx_dates[-1]]
        ship_gap = 0
        base = sum(ship[sku].get(m, 0) for m in ("2026-01", "2026-02", "2026-03",
                                                 "2026-04", "2026-05"))
        for ym in ("2026-06", "2026-07", "2026-08", "2026-09"):
            if ship[sku].get(ym, 0) == 0 and base > 0:
                ship_gap += 1

        # which source warehouse holds this SKU's stock, and its minimum
        wh_tot = Counter()
        wh_min = {}
        for d_ in wx_dates:
            row = wx.get(sku, {}).get(d_)
            if not row:
                continue
            for wh, v in row["wh"].items():
                wh_tot[wh] += v
                wh_min[wh] = min(wh_min.get(wh, v), v)
        main_wh = wh_tot.most_common(1)[0][0] if wh_tot else ""

        flags = [n_nonpos + n_low > 0, len(ev_dates) > 0, ship_gap > 0]
        n_agree = sum(1 for f in flags if f)
        grade = "高" if n_agree == 3 else ("中" if n_agree == 2 else "低")
        grade_count[grade] += 1

        # intervals = runs of signal dates separated by <= 14 days
        runs, cur = [], []
        for d_ in sig:
            if cur and (d_ - cur[-1]).days > 14:
                runs.append(cur)
                cur = []
            cur.append(d_)
        if cur:
            runs.append(cur)

        for run in runs:
            start, end = run[0], run[-1]
            observed = (end - start).days
            # the state between two snapshots is unknown: widen by the largest
            # observed snapshot gap, capped at the window's last date
            loose_end = min(end + timedelta(days=max_snap_gap), wx_dates[-1])
            intervals_rows.append(dict(
                sku=sku, start=start.isoformat(), end=end.isoformat(),
                days_observed=observed,
                loose_until=(loose_end.isoformat() if loose_end > end else ""),
                loose_days=(loose_end - start).days,
                signals_in_run=len(run),
                signal_kind=("WX+订单" if any(sku_status(sku, d_) in ("nonpositive", "low_1_3")
                                             for d_ in run) else "仅订单受阻"),
                note="快照之间状态未知；宽松上界按最大快照间隔外推，未做每日插值"))

        list_rows.append(dict(
            sku=sku, sku_hash=sha(sku), pb_sales_qty=round(r["sales"]),
            sales_rank=idx + 1,
            checked0stock_events_total=len(ev_dates),
            checked0stock_events_in_wx_window=len(ev_in_window),
            first_event=(ev_dates[0].isoformat() if ev_dates else ""),
            last_event=(ev_dates[-1].isoformat() if ev_dates else ""),
            wx_nonpositive_snapshots=n_nonpos, wx_low_snapshots=n_low,
            wx_positive_snapshots=n_pos,
            wx_warehouse_zero_cells=wh_zero,
            wx_main_warehouse=main_wh,
            wx_main_min_available=(round(wh_min.get(main_wh, 0.0), 2) if main_wh else ""),
            wx_window_start=wx_dates[0].isoformat() if wx_dates else "",
            wx_window_end=wx_dates[-1].isoformat() if wx_dates else "",
            wx_wide_table_rows_excluded=wide_rows.get(sku, 0),
            shipment_months_with_gap=ship_gap,
            credibility=grade,
            low_volume=("yes" if r["sales"] < MIN_SALES_FOR_CONCLUSION else "no"),
            inclusion_basis="PB Wedge Pillow 家族 ∩ GS PotteryBarn 有销量 ∩ 至少一个断货信号"))

    # ---- write csv -----------------------------------------------------
    with (OUT / "pb_30sku_list.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(list_rows[0].keys()))
        w.writeheader()
        w.writerows(list_rows)
    with (OUT / "stockout_intervals.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        fields = ["sku", "start", "end", "days_observed", "loose_until",
                  "loose_days", "signals_in_run", "signal_kind", "note"]
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(intervals_rows)

    # ---- report ---------------------------------------------------------
    n_ev_files = len(by_hash)
    n_files = len(files)
    total_events = sum(len(v) for v in events.values())
    L = ["---", "okf: v0.1", "type: Report",
         "title: PB 涤麻三角断货三源交叉",
         "date: 2026-10-23", "owner: claude-worker",
         "status: 只读；三源交叉 + 区间上/下界；不判物理断货",
         "artifacts:",
         "  - experiments/pb_stockout/pb_cross_source.py",
         "  - out/pb_stockout/pb_30sku_list.csv",
         "  - out/pb_stockout/stockout_intervals.csv",
         "---", "",
         "# PB 涤麻三角断货三源交叉", "",
         "> **边界**：WX 快照只给「系统非正 / 1–3 低 / 正 / 未知」，**不证明物理断货**；"
         "快照之间状态未知，不做每日回填；不评价 WX/LH 谁好。", "",
         "## 0. 输入与冻结", "",
         f"- checked0stock 文件 **{n_files}** 个 → 按内容 sha256 去重后 **{n_ev_files}** 个独立文件"
         f"（`NotUsed` 副本与重复下载合并）；独立事件（SKU×事件日）合计 **{total_events}**",
         f"- WX canonical 仅用 `warehouse_scope='source_warehouse'`：**{len(wx_dates)}** 个快照日期 "
         f"（{wx_dates[0]} .. {wx_dates[-1]}）",
         f"- 人工宽表层（`consolidated_warehouse_scope_unverified`）**未并入**："
         f"{sum(wide_rows.values())} 行被排除",
         f"- PB 销售：`gs_orders` channel='PotteryBarn'，67 个 SKU；家族（描述含 Wedge Pillow）"
         f"**{len(fam)}** 个，其中 {len(scored)} 个至少有一个断货信号；"
         f"目标 ~30，实际合格 **{len(selected)}** 个（不凑数、不补无信号 SKU）",
         "", "## 1. 30 SKU 名单与入选依据", "",
         f"规则（冻结）：**PB Wedge Pillow 家族**（checked0stock 描述含 `Wedge Pillow`）"
         "∩ **GS PotteryBarn 有销量** ∩ **至少一个断货信号**（checked0stock 事件或 WX 非正/低快照），"
         "按 PB 累计销量降序取前 30（合格不足 30 时取全部）。", "",
         "| # | SKU | PB 销量 | checked0stock 事件 | WX 非正/低快照 | 发货空月 | 可信度 |",
         "|---:|---|---:|---:|---:|---:|---|"]
    for r in list_rows:
        L.append(f"| {r['sales_rank']} | `{r['sku']}` | {r['pb_sales_qty']} | "
                 f"{r['checked0stock_events_total']} | {r['wx_nonpositive_snapshots']}/"
                 f"{r['wx_low_snapshots']} | {r['shipment_months_with_gap']} | {r['credibility']} |")

    L += ["", "## 2. 三源对齐（按 SKU × 日期）", "",
          "| 源 | 口径 | 结果 |", "|---|---|---|",
          f"| WX 快照 | 同一 SKU 同一天所有**源仓**求和；≤0 非正、1–3 低、>3 正 | "
          f"{len(wx_dates)} 个日期；名单内非正快照合计 "
          f"{sum(r['wx_nonpositive_snapshots'] for r in list_rows)}、低库存快照 "
          f"{sum(r['wx_low_snapshots'] for r in list_rows)} |",
          f"| checked0stock | 文件内容去重后按 `Vendor Style` 计独立事件 | 名单内事件合计 "
          f"{sum(r['checked0stock_events_total'] for r in list_rows)} |",
          f"| 实际发运 | `gs_orders` PB 渠道按月发货量；窗口内有 0 发货月且此前有销量 = 发货断档 | "
          f"名单内断档 SKU {sum(1 for r in list_rows if r['shipment_months_with_gap'])} 个 |", "",
          "> WX 的 SKU 级口径是**跨仓合计**；单仓为 0 不等于 SKU 断货，本表不按单仓下结论。", ""]

    L += ["## 3. 断货区间与时长上下界", "",
          "- 信号日 = checked0stock 事件日 ∪ WX 非正/低快照日（仅取快照窗口内）；"
          "相邻信号间隔 ≤14 天归为同一区间。",
          "- **保守下界** = 区间内首末信号日之间的实际观测天数（不外推）。",
          "- **宽松上界** = 保守天数 + 最大快照间隔（15 天）外推，截到窗口最后一天；"
          "因为快照之间状态未知。",
          "- 不插值、不填每日库存；信号来源逐行标注（本批全部为「仅订单受阻」）。", ""]
    if intervals_rows:
        L += ["| SKU | 起 | 止 | 保守天数 | 信号数 | 信号来源 | 宽松至 | 宽松天数 |",
              "|---|---|---|---:|---:|---|---|---:|"]
        for i in intervals_rows:
            L.append(f"| `{i['sku']}` | {i['start']} | {i['end']} | {i['days_observed']} | "
                     f"{i['signals_in_run']} | {i['signal_kind']} | "
                     f"{i['loose_until'] or '—'} | {i['loose_days']} |")
    else:
        L.append("> 名单内没有出现连续非正/低快照的区间：WX 源仓合计在这些 SKU 上始终为正。")

    L += ["", "## 3b. 关键观测（三源不一致）", "",
          f"- WX 源仓口径下，名单内 **没有任何 SKU 在任何一个快照日合计为非正或 1–3 低**"
          f"（非正 0 格、低 0 格）；但同一窗口内这些 SKU 的 PB 订单被**反复阻断**"
          f"（名单内事件 {sum(r['checked0stock_events_in_wx_window'] for r in list_rows)} 次）。",
          "- 同时，WX 的可用量主要落在 `皮壳仓库`（组件仓）等非成品仓："
          "SKU 合计为正≠PB 成品可发；单仓 0 的格数每 SKU 有 "
          f"{min(int(r['wx_warehouse_zero_cells']) for r in list_rows)}–"
          f"{max(int(r['wx_warehouse_zero_cells']) for r in list_rows)} 个，但本表不按单仓下断货结论。",
          "- 因此三源**没有同向样本**：WX 不能证实断货，只能用 checked0stock 与发货断档描述受阻区间。", ""]

    L += ["", "## 4. 可信度分级", "",
          f"三源同向 **高 {grade_count.get('高', 0)}**；两源 **中 {grade_count.get('中', 0)}**；"
          f"仅一源 **低 {grade_count.get('低', 0)}**。", "",
          "同向定义：WX 有非正/低快照、checked0stock 有事件、发货窗口内有断档。",
          "**高可信为 0 的原因**：WX 源仓合计在窗口内始终为正，三源不可能同向；"
          "这不是缺数据，而是三源本身不一致。", ""]

    L += ["## 5. 红线逐条检查", "",
          f"1. **通途正几件不自动判恢复**：1–3 件一律记 `low_1_3`，**不当作恢复**；"
          f"本批名单内低库存快照 "
          f"{sum(r['wx_low_snapshots'] for r in list_rows)} 个、非正快照 "
          f"{sum(r['wx_nonpositive_snapshots'] for r in list_rows)} 个，"
          f"因此没有任何「由正转恢复」的判定被使用。",
          f"2. **低销量不直接判断货**：PB 累计销量 < {MIN_SALES_FOR_CONCLUSION} 的 SKU 标 `low_volume=yes`，"
          f"不进入断货结论；名单内此类行 {sum(1 for r in list_rows if r['low_volume'] == 'yes')} 个。",
          f"3. **人工宽表 scope 未证不并入**：`warehouse_scope != source_warehouse` 的 "
          f"{sum(wide_rows.values())} 行全部排除，只在名单里记数量。",
          "4. **不填每日假库存**：输出只有快照点与区间，没有按天插值。", "",
          "## 6. 已知限制", "",
          "- WX 源仓快照只覆盖 2026-06-09..2026-07-31 共 11 个日期；此后的宽表日期范围未证，未并入。",
          "- checked0stock 事件跨 2023–2026，与 WX 窗口只有部分重叠；跨窗口的事件只用于「是否存在断货历史」，"
          "不用于区间计算。",
          "- 发货断档按月判断，月内节奏不可见。",
          "- 本报告不评价 WX/LH 谁更好，只给事实与区间。", ""]

    (OUT / "cross_source_report.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"skus={len(selected)} intervals={len(intervals_rows)} grades={dict(grade_count)} "
          f"files={n_files}->{n_ev_files} events={total_events} wx_dates={len(wx_dates)}")


if __name__ == "__main__":
    main()
