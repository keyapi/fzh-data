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
    ambiguous = 0
    for r in rows:
        item = str(cell(r, i_item) or "").strip()
        code = str(cell(r, i_code) or "").strip()
        if not item.startswith(FAMILIES):
            continue
        if not code or "已删除" in code:
            continue
        if code in code2item and code2item[code] != item:
            ambiguous += 1
            continue
        code2item[code] = item
    wb.close()
    return code2item, ambiguous


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


def load_orders(code2item: dict[str, str]):
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
    for m in MONTHS:
        p = latest_order_file(m)
        if not p:
            files.append({"month": f"2026-{m:02d}", "file": None})
            continue
        files.append({"month": f"2026-{m:02d}", "file": Path(p).name})
        wb = openpyxl.load_workbook(p, read_only=True, data_only=True)
        ws = wb[wb.sheetnames[0]]
        rows = ws.iter_rows(values_only=True)
        hdr = list(next(rows))
        ix = {name: (hdr.index(name) if name in hdr else None) for name in
              ("发货日期", "通途SKU", "发货数量", "发货仓库", "渠道", "是否补发货")}
        for r in rows:
            sku = str(cell(r, ix["通途SKU"]) or "").strip()
            item = code2item.get(sku)
            if not item:
                continue
            try:
                qty = float(cell(r, ix["发货数量"]) or 0)
            except (TypeError, ValueError):
                continue
            if qty <= 0:
                continue
            wh = normalize_warehouse(str(cell(r, ix["发货仓库"]) or ""))
            branch = branch_of_wh(wh)
            flag = str(cell(r, ix["是否补发货"]) or "").strip()
            is_reissue = flag in ("是", "Y", "y", "1", "true", "TRUE")
            month = f"2026-{m:02d}"
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
        "family_rows": family_rows,
        "family_qty": round(family_qty, 2),
        "reissue_rows": reissue_rows,
        "reissue_qty": round(reissue_qty, 2),
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
    for path in paths:
        data = json.loads(path.read_text(encoding="utf-8"))
        metas.append({
            "path": str(path),
            "fetched_at": data.get("fetched_at"),
            "source": data.get("source"),
            "warehouses": data.get("warehouses", []),
        })
        for row in data.get("by_sku", []):
            sku = row.get("sku", "")
            for wh, vals in (row.get("warehouses") or {}).items():
                branch, _kind = wh_branch_and_kind(wh)
                av = float(vals.get("available") or 0)
                it = float(vals.get("intransit") or 0)
                de = float(vals.get("defects") or 0)
                wa = float(vals.get("waiting") or 0)
                b = by_branch[branch]
                b["available"] += av; b["intransit"] += it; b["defects"] += de; b["waiting"] += wa
                b["skus"].add(sku); b["rows"] += 1; b["warehouses"].add(wh)
                w = by_wh[wh]
                w["available"] += av; w["intransit"] += it; w["defects"] += de; w["waiting"] += wa
                w["skus"].add(sku); w["rows"] += 1
                s = by_sku_branch[(branch, sku)]
                s["available"] += av; s["intransit"] += it; s["defects"] += de; s["waiting"] += wa
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
        "by_branch": finish(by_branch),
        "by_warehouse": finish(by_wh),
        "by_sku_branch": by_sku_branch,
    }


def coverage(demand, stock):
    rows = []
    all_keys = set(demand["by_sku_branch"]) | set(stock["by_sku_branch"])
    for branch, sku in all_keys:
        d = demand["by_sku_branch"].get((branch, sku), {"gross": 0.0, "reissue": 0.0, "rows": 0,
                                                        "reissue_rows": 0})
        s = stock["by_sku_branch"].get((branch, sku), {"available": 0.0, "intransit": 0.0,
                                                       "defects": 0.0, "waiting": 0.0})
        gross = float(d.get("gross", 0) or 0)
        reissue = float(d.get("reissue", 0) or 0)
        supply = float(s.get("available", 0) or 0) + float(s.get("intransit", 0) or 0)
        avg_gross = gross / len(MONTHS)
        cov = round(supply / avg_gross, 2) if avg_gross > 0 else None
        rows.append({
            "branch": branch,
            "sku": sku,
            "gross_6m": round(gross, 2),
            "reissue_6m": round(reissue, 2),
            "avg_monthly_gross": round(avg_gross, 2),
            "available": round(float(s.get("available", 0) or 0), 2),
            "intransit": round(float(s.get("intransit", 0) or 0), 2),
            "supply": round(supply, 2),
            "coverage_months_gross": cov,
        })
    rows.sort(key=lambda r: (r["branch"], -r["gross_6m"], r["sku"]))
    return rows


def main():
    ap = argparse.ArgumentParser(description="G1b family 出库消耗 vs 两仓库存覆盖")
    ap.add_argument("--stock", nargs="+", required=True, help="g1b_stock_snapshot.py 输出 JSON（可多个）")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    code2item, ambiguous = load_bom()
    demand = load_orders(code2item)
    stock = load_stock([Path(p) for p in args.stock])
    rows = coverage(demand, stock)

    branch_cov = {}
    for branch in sorted(set(demand["by_branch"]) | set(stock["by_branch"])):
        gross = float(demand["by_branch"].get(branch, 0) or 0)
        avg = gross / len(MONTHS)
        s = stock["by_branch"].get(branch, {})
        supply = float(s.get("available", 0) or 0) + float(s.get("intransit", 0) or 0)
        branch_cov[branch] = {
            "gross_6m": round(gross, 2),
            "avg_monthly_gross": round(avg, 2),
            "available": round(float(s.get("available", 0) or 0), 2),
            "intransit": round(float(s.get("intransit", 0) or 0), 2),
            "supply": round(supply, 2),
            "coverage_months_gross": round(supply / avg, 2) if avg > 0 else None,
        }

    no_supply = [r for r in rows if r["gross_6m"] > 0 and r["supply"] == 0]
    no_demand = [r for r in rows if r["gross_6m"] == 0 and r["supply"] > 0]
    below_2 = [r for r in rows if r["coverage_months_gross"] is not None and r["coverage_months_gross"] < 2]

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
        },
        "assumptions": {
            "demand": "通途出库消耗毛量，含补发货；不是会计销量",
            "returns": "库存净算不冲减退货：已回库的退货已在 available，未回库/报废也不冲减；"
                       f"5% 仅作未来需求情景参考（本期约 {demand['family_qty'] * RETURN_RATE:.0f} 件），"
                       "不得与当前库存重复抵扣",
            "supply": "available + intransit；不含 defects/waiting（waiting 已分配/待发，避免重复）",
            "coverage": "历史 run-rate 覆盖月数，不是预测；美中受新运营 ramp 影响，只作指示",
            "wayfaircg": "库存未接入（需 YTQ 后台手工导出）；3PL 需求单独列",
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
            "reissue_rows": demand["reissue_rows"],
            "reissue_qty": demand["reissue_qty"],
            "by_month": demand["by_month"],
            "by_branch": demand["by_branch"],
            "by_warehouse": demand["by_warehouse"],
        },
        "stock": {
            "fetched_at": [m.get("fetched_at") for m in stock.get("files", [])],
            "warehouses_requested": sorted({w for m in stock.get("files", [])
                                            for w in (m.get("warehouses") or [])}),
            "by_branch": stock["by_branch"],
            "by_warehouse": stock["by_warehouse"],
        },
        "coverage_by_branch": branch_cov,
        "coverage_by_sku": rows,
        "gaps": {
            "demand_without_supply": no_supply[:200],
            "supply_without_demand": no_demand[:200],
            "coverage_below_2_months": below_2[:200],
            "counts": {
                "demand_without_supply": len(no_supply),
                "supply_without_demand": len(no_demand),
                "coverage_below_2_months": len(below_2),
            },
        },
    }

    out = Path(args.out) if args.out else OUT / f"g1b_coverage_{datetime.now():%Y%m%d_%H%M%S}.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"OK: {out}")
    print(f"  6 个月出库消耗: {demand['family_qty']:g} 件 / {demand['family_rows']} 行")
    print(f"  补发货: {demand['reissue_qty']:g} 件 / {demand['reissue_rows']} 行")
    for b, v in branch_cov.items():
        print(f"  {b}: 需求 {v['gross_6m']:g} 件，供给 {v['supply']:g}（可用 {v['available']:g} + 在途 {v['intransit']:g}），"
              f"覆盖 {v['coverage_months_gross']} 个月")
    print(f"  缺口: 有需求无供给 {len(no_supply)} 个 SKU；覆盖<2月 {len(below_2)} 个 SKU")


if __name__ == "__main__":
    main()
