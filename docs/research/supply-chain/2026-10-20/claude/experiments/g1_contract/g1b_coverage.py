#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""G1b：三角靠枕 family 出库消耗 vs 两仓库存覆盖（只读聚合）。

输入：
  - EN BOM 20261016（KS0001/KS0248 客户物料号）
  - 本地 2026-04..09 订单 order_cost（出库行）
  - g1b_stock_snapshot.py 产出的通途库存快照 JSON

输出（聚合，不含 PII）：
  - 6 个月出库消耗毛量（含补发货）
  - 当前可用 + 在途（不含次品/待发）
  - 历史 run-rate 覆盖月数；退货 5% 情境
  - SKU/分公司缺口清单

注意：这是 G1 契约回放，不是预测。美中历史受新运营 ramp 影响，覆盖月数只作指示。
"""

from __future__ import annotations

import argparse
import glob
import json
import math
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import openpyxl

BASE = Path(__file__).resolve().parent
OUT = BASE / "out"
OUT.mkdir(parents=True, exist_ok=True)

BOM = Path(r"D:/Work/王忠于/成本核算/EN产品BOM成本列表20261016.xlsx")
ORDER_GLOB = r"D:/Work/王忠于/成本核算/2026年{month}月订单_order_cost_*.xlsx"
MONTHS = list(range(4, 10))
FAMILIES = ("KS0001", "KS0248")
RETURN_RATE = 0.05
REQUIRED_SUPPLY_WAREHOUSES = {
    "USNJ": ("美东-CENTRADE",),
    "USTX": ("美中-FZH-DANEEY",),
    "PL": ("波兰-FZHPoland-covers",),
}


def cell(row, idx):
    if idx is None or idx >= len(row):
        return None
    return row[idx]


def load_bom():
    wb = openpyxl.load_workbook(BOM, read_only=True, data_only=True)
    ws = wb[wb.sheetnames[0]]
    rows = ws.iter_rows(values_only=True)
    hdr = list(next(rows))
    i_item = hdr.index("产品编号")
    i_code = hdr.index("客户物料号")
    code2item: dict[str, str] = {}
    ambiguous: set[str] = set()
    for r in rows:
        item = str(cell(r, i_item) or "").strip()
        code = str(cell(r, i_code) or "").strip()
        if not item.startswith(FAMILIES):
            continue
        if not code or "已删除" in code:
            continue
        if code in code2item and code2item[code] != item:
            ambiguous.add(code)
            code2item.pop(code, None)
            continue
        if code not in ambiguous:
            code2item[code] = item
    wb.close()
    return code2item, sorted(ambiguous)


def latest_order_file(month: int):
    files = sorted(glob.glob(ORDER_GLOB.format(month=month)))
    return files[-1] if files else None


def normalize_warehouse(wh: str) -> str:
    w = (wh or "").strip().upper()
    if "CENTRADE" in w:
        return "美东-CENTRADE"
    if "DANEEY" in w:
        if "退货" in w:
            return "DANEEY-退货仓"
        if "皮壳" in w or "半成品" in w:
            return "DANEEY-皮壳/半成品"
        return "美中-FZH-DANEEY"
    if "POLAND" in w or "波兰" in w:
        return "波兰"
    if "WAYFAIR" in w:
        return "WayfairCG"
    return "其他"


def branch_of_wh(wh: str) -> str:
    if wh == "美东-CENTRADE":
        return "USNJ"
    if wh in ("美中-FZH-DANEEY", "DANEEY-皮壳/半成品"):
        return "USTX"
    if wh == "DANEEY-退货仓":
        return "USTX-return"
    if wh == "波兰":
        return "PL"
    if wh == "WayfairCG":
        return "3PL"
    return "OTHER"


REQUIRED_ORDER_COLS = ("发货日期", "通途SKU", "发货数量", "发货仓库")


def load_orders(code2item: dict[str, str], ambiguous_codes: list[str]):
    ambiguous_set = set(ambiguous_codes)
    by_month: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    by_branch: Counter = Counter()
    by_warehouse: Counter = Counter()
    by_sku_branch: dict[tuple[str, str], dict] = defaultdict(
        lambda: {"gross": 0.0, "reissue": 0.0, "rows": 0, "reissue_rows": 0}
    )
    family_rows = 0
    family_qty = 0.0
    reissue_rows = 0
    reissue_qty = 0.0
    files = []
    missing_months = []
    missing_columns = []
    bad_qty_rows = 0
    negative_qty_rows = 0
    non_integer_qty_rows = 0
    zero_qty_rows = 0
    missing_sku_rows = 0
    missing_wh_rows = 0
    non_family_rows = 0
    pending_text_tri_rows = 0
    pending_text_tri_qty = 0.0
    ambiguous_rows = 0
    ambiguous_qty = 0.0
    bad_samples = []
    months_observed = 0
    for m in MONTHS:
        p = latest_order_file(m)
        month = f"2026-{m:02d}"
        if not p:
            missing_months.append(month)
            files.append({"month": month, "file": None, "status": "missing"})
            continue
        wb = openpyxl.load_workbook(p, read_only=True, data_only=True)
        ws = wb[wb.sheetnames[0]]
        rows = ws.iter_rows(values_only=True)
        hdr = list(next(rows))
        missing = [c for c in REQUIRED_ORDER_COLS if c not in hdr]
        if missing:
            missing_columns.append({"month": month, "missing": missing})
            files.append({"month": month, "file": Path(p).name, "status": "invalid_columns"})
            wb.close()
            continue
        months_observed += 1
        files.append({"month": month, "file": Path(p).name, "status": "ok"})
        ix = {name: (hdr.index(name) if name in hdr else None) for name in
              ("发货日期", "通途SKU", "发货数量", "发货仓库", "渠道", "是否补发货",
               "产品名称", "品类orig", "品类", "品类统一名")}
        for row_no, r in enumerate(rows, start=2):
            sku = str(cell(r, ix["通途SKU"]) or "").strip()
            if not sku:
                missing_sku_rows += 1
                continue
            if sku in ambiguous_set:
                ambiguous_rows += 1
                try:
                    ambiguous_qty += float(cell(r, ix["发货数量"]) or 0)
                except (TypeError, ValueError):
                    pass
                continue
            if sku not in code2item:
                texts = [str(cell(r, ix[k]) or "") for k in
                         ("产品名称", "品类orig", "品类", "品类统一名") if ix.get(k) is not None]
                if any("三角" in t for t in texts):
                    pending_text_tri_rows += 1
                    try:
                        pending_text_tri_qty += float(cell(r, ix["发货数量"]) or 0)
                    except (TypeError, ValueError):
                        pass
                else:
                    non_family_rows += 1
                continue
            raw_qty = cell(r, ix["发货数量"])
            try:
                qty = float(raw_qty)
            except (TypeError, ValueError):
                bad_qty_rows += 1
                if len(bad_samples) < 20:
                    bad_samples.append({"file": Path(p).name, "row": row_no, "reason": "bad_qty",
                                        "value": str(raw_qty)[:40]})
                continue
            if qty < 0:
                negative_qty_rows += 1
                continue
            if not math.isfinite(qty):
                bad_qty_rows += 1
                if len(bad_samples) < 20:
                    bad_samples.append({"file": Path(p).name, "row": row_no,
                                        "reason": "non_finite_qty"})
                continue
            if qty == 0:
                zero_qty_rows += 1
                continue
            if qty != int(qty):
                non_integer_qty_rows += 1
                if len(bad_samples) < 20:
                    bad_samples.append({"file": Path(p).name, "row": row_no,
                                        "reason": "non_integer_qty", "value": qty})
                continue
            wh_raw = str(cell(r, ix["发货仓库"]) or "").strip()
            if not wh_raw:
                missing_wh_rows += 1
                continue
            wh = normalize_warehouse(wh_raw)
            branch = branch_of_wh(wh)
            flag = str(cell(r, ix["是否补发货"]) or "").strip()
            is_reissue = flag in ("是", "Y", "y", "1", "true", "TRUE")
            family_rows += 1
            family_qty += qty
            by_month[branch][month] += qty
            by_branch[branch] += qty
            by_warehouse[wh] += qty
            entry = by_sku_branch[(branch, sku)]
            entry["gross"] += qty
            entry["rows"] += 1
            if is_reissue:
                entry["reissue"] += qty
                entry["reissue_rows"] += 1
                reissue_rows += 1
                reissue_qty += qty
        wb.close()
    return {
        "files": files,
        "months_observed": months_observed,
        "window_complete": (months_observed == len(MONTHS) and not missing_columns),
        "missing_months": missing_months,
        "missing_columns": missing_columns,
        "family_rows": family_rows,
        "family_qty": round(family_qty, 2),
        "reissue_rows": reissue_rows,
        "reissue_qty": round(reissue_qty, 2),
        "bad_qty_rows": bad_qty_rows,
        "negative_qty_rows": negative_qty_rows,
        "non_integer_qty_rows": non_integer_qty_rows,
        "zero_qty_rows": zero_qty_rows,
        "missing_sku_rows": missing_sku_rows,
        "missing_wh_rows": missing_wh_rows,
        "non_family_rows": non_family_rows,
        "pending_text_tri_rows": pending_text_tri_rows,
        "pending_text_tri_qty": round(pending_text_tri_qty, 2),
        "ambiguous_rows": ambiguous_rows,
        "ambiguous_qty": round(ambiguous_qty, 2),
        "bad_samples": bad_samples,
        "by_month": {b: {m: round(v, 2) for m, v in sorted(ms.items())} for b, ms in by_month.items()},
        "by_branch": {b: round(v, 2) for b, v in by_branch.items()},
        "by_warehouse": {w: round(v, 2) for w, v in by_warehouse.items()},
        "by_sku_branch": by_sku_branch,
    }


def wh_branch_and_kind(wh: str):
    u = (wh or "").upper()
    if "CENTRADE" in u:
        return "USNJ", "shell" if "皮壳" in wh or "半成品" in wh else "finished"
    if "DANEEY" in u:
        if "退货" in wh:
            return "USTX-return", "return"
        if "皮壳" in wh or "半成品" in wh:
            return "USTX", "shell"
        return "USTX", "finished"
    if "POLAND" in u or "波兰" in wh:
        return "PL", "finished"
    if "WAYFAIR" in u:
        return "3PL", "3pl"
    return "OTHER", "other"


def load_stock(paths: list[Path]):
    by_branch = defaultdict(lambda: {"available": 0.0, "intransit": 0.0, "defects": 0.0,
                                     "waiting": 0.0, "skus": set(), "rows": 0, "warehouses": set()})
    by_wh = defaultdict(lambda: {"available": 0.0, "intransit": 0.0, "defects": 0.0,
                                 "waiting": 0.0, "skus": set(), "rows": 0})
    by_sku_branch = defaultdict(lambda: {"available": 0.0, "intransit": 0.0,
                                         "defects": 0.0, "waiting": 0.0})
    metas = []
    payloads = []
    for path in paths:
        data = json.loads(path.read_text(encoding="utf-8"))
        metas.append({
            "path": str(path),
            "fetched_at": data.get("fetched_at"),
            "source": data.get("source"),
            "warehouses": data.get("warehouses", []),
            "complete": data.get("complete"),
        })
        payloads.append((path, data))

    # 同一仓在多个快照里出现时，只取 fetched_at 最新的一个；complete 必须绑定这个选中文件。
    selected_file_per_wh: dict[str, Path] = {}
    selected_fetched: dict[str, str] = {}
    selected_complete: dict[str, bool] = {}
    for path, data in payloads:
        fetched = str(data.get("fetched_at") or "")
        for wh in data.get("warehouses", []):
            if wh not in selected_file_per_wh or fetched > selected_fetched.get(wh, ""):
                selected_file_per_wh[wh] = path
                selected_fetched[wh] = fetched
                wh_complete = (data.get("by_warehouse", {}).get(wh, {})
                               .get("complete"))
                if wh_complete is None:
                    wh_complete = data.get("complete") is True
                selected_complete[wh] = wh_complete is True

    seen: dict[tuple[str, str], dict] = {}
    presence: dict[str, set[str]] = defaultdict(set)
    duplicate_conflicts = 0
    duplicates_ignored = 0
    bad_values = 0
    ignored_warehouses = []
    incomplete_warehouses: set[str] = set()
    bad_samples = []
    conflict_samples = []
    for path, data in payloads:
        for row in data.get("by_sku", []):
            sku = row.get("sku", "")
            for wh, vals in (row.get("warehouses") or {}).items():
                if selected_file_per_wh.get(wh) != path:
                    if wh not in ignored_warehouses:
                        ignored_warehouses.append(wh)
                    continue
                try:
                    parsed = {
                        "available": float(vals.get("available")),
                        "intransit": float(vals.get("intransit")),
                        "defects": float(vals.get("defects")),
                        "waiting": float(vals.get("waiting")),
                    }
                except (TypeError, ValueError):
                    bad_values += 1
                    incomplete_warehouses.add(wh)
                    if len(bad_samples) < 20:
                        bad_samples.append({"warehouse": wh, "sku": sku, "reason": "bad_value"})
                    continue
                if any((not math.isfinite(v)) or v < 0 or v != int(v) for v in parsed.values()):
                    bad_values += 1
                    incomplete_warehouses.add(wh)
                    if len(bad_samples) < 20:
                        bad_samples.append({"warehouse": wh, "sku": sku, "reason": "invalid_qty",
                                            "values": parsed})
                    continue
                key = (wh, sku)
                presence[wh].add(sku)
                if key in seen:
                    if seen[key] == parsed:
                        duplicates_ignored += 1
                    else:
                        duplicate_conflicts += 1
                        incomplete_warehouses.add(wh)
                        if len(conflict_samples) < 20:
                            conflict_samples.append({"warehouse": wh, "sku": sku,
                                                     "kept": seen[key], "discarded": parsed})
                    continue
                seen[key] = parsed
                branch, _kind = wh_branch_and_kind(wh)
                b = by_branch[branch]
                for k in ("available", "intransit", "defects", "waiting"):
                    b[k] += parsed[k]
                b["skus"].add(sku); b["rows"] += 1; b["warehouses"].add(wh)
                w = by_wh[wh]
                for k in ("available", "intransit", "defects", "waiting"):
                    w[k] += parsed[k]
                w["skus"].add(sku); w["rows"] += 1
                s = by_sku_branch[(branch, sku)]
                for k in ("available", "intransit", "defects", "waiting"):
                    s[k] += parsed[k]
    incomplete_warehouses |= {
        wh for wh in selected_file_per_wh if selected_complete.get(wh) is not True
    }
    complete_warehouses = sorted(
        wh for wh in selected_file_per_wh
        if selected_complete.get(wh) is True and wh not in incomplete_warehouses
    )
    def finish(d):
        out = {}
        for k, v in d.items():
            out[k] = {
                "available": round(v["available"], 2),
                "intransit": round(v["intransit"], 2),
                "defects": round(v["defects"], 2),
                "waiting": round(v["waiting"], 2),
                "sku_count": len(v["skus"]),
                "row_count": v["rows"],
            }
            if "warehouses" in v:
                out[k]["warehouses"] = sorted(v["warehouses"])
        return out
    return {
        "files": metas,
        "requested_warehouses": sorted({wh for _, data in payloads
                                        for wh in (data.get("warehouses") or [])}),
        "selected_file_per_warehouse": {k: str(v) for k, v in selected_file_per_wh.items()},
        "selected_complete": selected_complete,
        "ignored_warehouses": ignored_warehouses,
        "duplicate_conflicts": duplicate_conflicts,
        "duplicates_ignored": duplicates_ignored,
        "bad_values": bad_values,
        "bad_samples": bad_samples,
        "conflict_samples": conflict_samples,
        "incomplete_warehouses": sorted(incomplete_warehouses),
        "complete_warehouses": complete_warehouses,
        "sku_presence": {wh: sorted(skus) for wh, skus in presence.items()},
        "by_branch": finish(by_branch),
        "by_warehouse": finish(by_wh),
        "by_sku_branch": by_sku_branch,
    }


def coverage(demand, stock):
    observations = max(1, int(demand.get("months_observed") or len(MONTHS)))
    complete_set = set(stock.get("complete_warehouses", []))
    complete_branches = {
        branch for branch, whs in REQUIRED_SUPPLY_WAREHOUSES.items()
        if all(wh in complete_set for wh in whs)
    }
    presence = {wh: set(skus) for wh, skus in stock.get("sku_presence", {}).items()}
    rows = []
    all_keys = set(demand["by_sku_branch"]) | set(stock["by_sku_branch"])
    for branch, sku in all_keys:
        d = demand["by_sku_branch"].get((branch, sku), {"gross": 0.0, "reissue": 0.0, "rows": 0,
                                                        "reissue_rows": 0})
        s = stock["by_sku_branch"].get((branch, sku), {"available": 0.0, "intransit": 0.0,
                                                       "defects": 0.0, "waiting": 0.0})
        gross = float(d.get("gross", 0) or 0)
        reissue = float(d.get("reissue", 0) or 0)
        ref_available = round(float(s.get("available", 0) or 0), 2)
        ref_intransit = round(float(s.get("intransit", 0) or 0), 2)
        ref_supply = round(ref_available + ref_intransit, 2)
        required = REQUIRED_SUPPLY_WAREHOUSES.get(branch)
        available = intransit = supply = None
        presence_status = "unknown"
        quantity_status = "unknown"
        if branch in complete_branches and required:
            observed = all(sku in presence.get(wh, set()) for wh in required)
            if observed:
                available = ref_available
                intransit = ref_intransit
                supply = ref_supply
                presence_status = "observed"
                quantity_status = "positive" if supply > 0 else "observed_zero"
            else:
                presence_status = "missing"
                quantity_status = "missing"
            supply_status = "sampled_complete"
            authority = "tongtool_api_or_browser_stock"
        elif branch in REQUIRED_SUPPLY_WAREHOUSES:
            supply_status = "sampled_incomplete"
            authority = "tongtool_api_or_browser_stock"
        elif branch == "3PL":
            supply_status = "unknown_authority"
            authority = "wayfair_backend_manual"
        elif branch == "USTX-return":
            supply_status = "demand_only"
            authority = "not_applicable"
        else:
            supply_status = "not_sampled"
            authority = "not_applicable"
        avg_gross = gross / observations
        cov_on_hand = None
        cov_incl = None
        if quantity_status in ("positive", "observed_zero") and avg_gross > 0:
            cov_on_hand = round(available / avg_gross, 2)
            cov_incl = round(supply / avg_gross, 2)
        rows.append({
            "branch": branch,
            "sku": sku,
            "supply_status": supply_status,
            "authority": authority,
            "required_warehouses": list(required or []),
            "presence": presence_status,
            "quantity_status": quantity_status,
            "gross_6m": round(gross, 2),
            "reissue_6m": round(reissue, 2),
            "avg_monthly_gross": round(avg_gross, 2),
            "available": available,
            "intransit": intransit,
            "supply": supply,
            "reference_available": ref_available,
            "reference_intransit": ref_intransit,
            "reference_supply": ref_supply,
            "coverage_months_on_hand": cov_on_hand,
            "coverage_months_incl_intransit": cov_incl,
        })
    rows.sort(key=lambda r: (r["branch"], -r["gross_6m"], r["sku"]))
    return rows


def main():
    ap = argparse.ArgumentParser(description="G1b family 出库消耗 vs 两仓库存覆盖")
    ap.add_argument("--stock", nargs="+", required=True, help="g1b_stock_snapshot.py 输出 JSON（可多个）")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    code2item, ambiguous = load_bom()
    demand = load_orders(code2item, ambiguous)
    stock = load_stock([Path(p) for p in args.stock])
    rows = coverage(demand, stock)
    observations = max(1, int(demand.get("months_observed") or len(MONTHS)))
    complete_set = set(stock.get("complete_warehouses", []))
    complete_branches = {
        branch for branch, whs in REQUIRED_SUPPLY_WAREHOUSES.items()
        if all(wh in complete_set for wh in whs)
    }

    branch_cov = {}
    for branch in sorted(set(demand["by_branch"]) | set(stock["by_branch"])):
        gross = float(demand["by_branch"].get(branch, 0) or 0)
        avg = gross / observations
        s = stock["by_branch"].get(branch, {})
        ref_available = float(s.get("available", 0) or 0)
        ref_intransit = float(s.get("intransit", 0) or 0)
        ref_supply = ref_available + ref_intransit
        complete = branch in complete_branches
        if complete:
            supply_status = "sampled_complete"
        elif branch in REQUIRED_SUPPLY_WAREHOUSES:
            supply_status = "sampled_incomplete"
        elif branch == "3PL":
            supply_status = "unknown_authority"
        elif branch == "USTX-return":
            supply_status = "demand_only"
        else:
            supply_status = "not_sampled"
        authority = "wayfair_backend_manual" if branch == "3PL" else "tongtool_api_or_browser_stock"
        branch_rows = [r for r in rows if r["branch"] == branch]
        observed_skus = sum(1 for r in branch_rows if r["presence"] == "observed")
        missing_skus = sum(1 for r in branch_rows if r["presence"] == "missing")
        unknown_skus = sum(1 for r in branch_rows if r["presence"] == "unknown")
        available = ref_available if complete else None
        intransit = ref_intransit if complete else None
        supply = ref_supply if complete else None
        branch_cov[branch] = {
            "supply_status": supply_status,
            "authority": authority,
            "gross_6m": round(gross, 2),
            "avg_monthly_gross": round(avg, 2),
            "available": round(available, 2) if available is not None else None,
            "intransit": round(intransit, 2) if intransit is not None else None,
            "supply": round(supply, 2) if supply is not None else None,
            "reference_available": round(ref_available, 2),
            "reference_intransit": round(ref_intransit, 2),
            "reference_supply": round(ref_supply, 2),
            "observed_skus": observed_skus,
            "missing_skus": missing_skus,
            "unknown_skus": unknown_skus,
            "coverage_months_on_hand": (round(available / avg, 2)
                                        if complete and available is not None and avg > 0 else None),
            "coverage_months_incl_intransit": (round(supply / avg, 2)
                                               if complete and supply is not None and avg > 0 else None),
            "coverage_eligible": bool(complete and demand.get("window_complete")),
        }

    headline_eligible = bool(demand.get("window_complete") and complete_branches)
    if headline_eligible:
        no_supply = [r for r in rows if r["supply_status"] == "sampled_complete"
                     and r["quantity_status"] == "observed_zero" and r["gross_6m"] > 0]
        missing_supply = [r for r in rows if r["supply_status"] == "sampled_complete"
                          and r["quantity_status"] == "missing" and r["gross_6m"] > 0]
        unknown_supply = [r for r in rows if r["gross_6m"] > 0
                          and r["quantity_status"] == "unknown"]
        no_demand = [r for r in rows if r["supply_status"] == "sampled_complete"
                     and r["quantity_status"] in ("positive", "observed_zero")
                     and r["gross_6m"] == 0 and (r["supply"] or 0) > 0]
        below_2 = [r for r in rows if r["supply_status"] == "sampled_complete"
                   and r["coverage_months_incl_intransit"] is not None
                   and r["coverage_months_incl_intransit"] < 2]
    else:
        no_supply, missing_supply, unknown_supply, no_demand, below_2 = [], [], [], [], []

    result = {
        "okf": "v0.1",
        "type": "Experiment-Results",
        "title": "G1b family 出库消耗 vs 两仓库存覆盖",
        "date": datetime.now().strftime("%Y-%m-%d"),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "inputs": {
            "bom": str(BOM),
            "orders": demand["files"],
            "stock": [str(p) for p in args.stock],
            "stock_files": stock.get("files"),
            "months": [f"2026-{m:02d}" for m in MONTHS],
            "months_observed": demand["months_observed"],
            "window_complete": demand["window_complete"],
        },
        "assumptions": {
            "demand": "通途出库消耗毛量，含补发货；不是会计销量",
            "returns": "库存净算不冲减退货：已回库的退货已在 available，未回库/报废也不冲减；"
                       f"5% 仅作未来需求情景参考（本期约 {demand['family_qty'] * RETURN_RATE:.0f} 件），"
                       "不得与当前库存重复抵扣",
            "supply": "on_hand 与 incl_intransit 分开报；intransit 无 ETA，不是可用服务覆盖；不含 defects/waiting",
            "coverage": "历史 run-rate 覆盖月数，不是预测；美中受新运营 ramp 影响，只作指示",
            "wayfaircg": "库存未接入（需 YTQ 后台手工导出）；3PL 需求单独列，不进入缺口统计",
        },
        "returns_scenario_only": {
            "rate": RETURN_RATE,
            "qty_if_applied_to_gross": round(demand["family_qty"] * RETURN_RATE, 2),
            "note": "仅供未来需求情景；不用于当前库存净算，避免与已回库库存双扣",
        },
        "bom": {"family_codes": len(code2item), "ambiguous_codes": ambiguous},
        "demand": {
            "family_rows": demand["family_rows"],
            "family_qty": demand["family_qty"],
            "months_observed": demand.get("months_observed"),
            "window_complete": demand.get("window_complete"),
            "missing_months": demand.get("missing_months"),
            "reissue_rows": demand["reissue_rows"],
            "reissue_qty": demand["reissue_qty"],
            "by_month": demand["by_month"],
            "by_branch": demand["by_branch"],
            "by_warehouse": demand["by_warehouse"],
            "bad_qty_rows": demand["bad_qty_rows"],
            "negative_qty_rows": demand["negative_qty_rows"],
            "non_integer_qty_rows": demand["non_integer_qty_rows"],
            "zero_qty_rows": demand["zero_qty_rows"],
            "missing_sku_rows": demand["missing_sku_rows"],
            "missing_wh_rows": demand["missing_wh_rows"],
            "non_family_rows": demand["non_family_rows"],
            "pending_text_tri_rows": demand.get("pending_text_tri_rows"),
            "pending_text_tri_qty": demand.get("pending_text_tri_qty"),
            "ambiguous_rows": demand["ambiguous_rows"],
            "ambiguous_qty": demand["ambiguous_qty"],
            "bad_samples": demand["bad_samples"],
            "missing_months": demand["missing_months"],
            "missing_columns": demand["missing_columns"],
        },
        "stock": {
            "fetched_at": [m.get("fetched_at") for m in stock.get("files", [])],
            "warehouses_requested": sorted({w for m in stock.get("files", [])
                                            for w in (m.get("warehouses") or [])}),
            "complete_warehouses": stock.get("complete_warehouses"),
            "incomplete_warehouses": stock.get("incomplete_warehouses"),
            "requested_warehouses": stock.get("requested_warehouses"),
            "selected_file_per_warehouse": stock.get("selected_file_per_warehouse"),
            "selected_complete": stock.get("selected_complete"),
            "ignored_warehouses": stock.get("ignored_warehouses"),
            "duplicate_conflicts": stock.get("duplicate_conflicts"),
            "duplicates_ignored": stock.get("duplicates_ignored"),
            "bad_values": stock.get("bad_values"),
            "bad_samples": stock.get("bad_samples"),
            "conflict_samples": stock.get("conflict_samples"),
            "by_branch": stock["by_branch"],
            "by_warehouse": stock["by_warehouse"],
        },
        "headline_eligible": headline_eligible,
        "headline_blocked_reason": (None if headline_eligible else
                                     "window_incomplete_or_no_complete_branch"),
        "coverage_by_branch": branch_cov,
        "coverage_eligible_branches": sorted(
            b for b, v in branch_cov.items() if v.get("coverage_eligible")),
        "coverage_by_sku": rows,
        "gaps": {
            "scope": "仅 window_complete 且 sampled_complete 进入 headline；未返回 SKU 记 missing，不记 observed_zero；3PL/退货仓 unknown",
            "demand_without_supply": no_supply[:200],
            "missing_supply": missing_supply[:200],
            "unknown_supply": unknown_supply[:200],
            "supply_without_demand": no_demand[:200],
            "coverage_below_2_months": below_2[:200],
            "counts": {
                "demand_without_supply_observed_zero": len(no_supply),
                "missing_supply": len(missing_supply),
                "unknown_supply": len(unknown_supply),
                "supply_without_demand": len(no_demand),
                "coverage_below_2_months": len(below_2),
                "note": "按 branch×SKU 计数；missing/unknown 不计入无供给",
            },
        },
    }

    out = Path(args.out) if args.out else OUT / f"g1b_coverage_{datetime.now():%Y%m%d_%H%M%S}.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"OK: {out}")
    print(f"  出库消耗: {demand['family_qty']:g} 件 / {demand['family_rows']} 行；"
          f"窗口 {demand['months_observed']}/{len(MONTHS)} 月 complete={demand['window_complete']}")
    print(f"  补发货: {demand['reissue_qty']:g} 件 / {demand['reissue_rows']} 行")
    for b, v in branch_cov.items():
        if v["supply"] is None:
            supply_txt = f"None（参考 {v['reference_supply']:g}）"
        else:
            supply_txt = f"{v['supply']:g}（可用 {v['available']:g} + 在途 {v['intransit']:g}）"
        print(f"  {b} [{v['supply_status']}]: 需求 {v['gross_6m']:g}，供给 {supply_txt}，"
              f"on-hand {v['coverage_months_on_hand']} 月 / 含在途 {v['coverage_months_incl_intransit']} 月，"
              f"observed/missing/unknown={v['observed_skus']}/{v['missing_skus']}/{v['unknown_skus']}")
    print(f"  headline_eligible={headline_eligible}；observed_zero {len(no_supply)}；"
          f"missing {len(missing_supply)}；unknown {len(unknown_supply)}；<2月 {len(below_2)}")


if __name__ == "__main__":
    main()
