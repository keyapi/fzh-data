"""Refresh stock/SO facts and recompute the D6-style gap for a SKU (forecast reused)."""
from __future__ import annotations
import json
from datetime import date
from pathlib import Path

import pandas as pd

from .recommend import BRANCH, _path, _need_columns
from .download import token_headers


def _tt_skus(data_root):
    path = _path(data_root, "sku_map.tsv")
    out = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        parts = line.split("\t")
        if len(parts) >= 2 and parts[0].strip() and parts[1].strip():
            out.setdefault(parts[0].strip(), []).append(parts[1].strip())
    return out


def _live_stock(data_root, sku, warehouse, env_file=None):
    from .live_stock_adapter import read_live
    try:
        rows = read_live(env_file=env_file)
    except Exception as exc:  # noqa: BLE001
        return {"status": "unavailable", "error": str(exc), "rows": []}
    keys = []
    for row in rows:
        if str(row.get("warehouse")) == warehouse and str(row.get("sku")).lower() == str(sku).lower():
            keys.append(row)
    if not keys:
        return {"status": "not_found", "rows": []}
    out = {"status": "matched", "rows": keys}
    for field in ("available", "intransit", "waiting_shipment", "defects"):
        vals = [r.get(field) for r in keys]
        out[field] = None if any(v is None for v in vals) else sum(vals)
    out["run_id"] = keys[0].get("run_id")
    out["snapshot_at"] = keys[0].get("snapshot_at")
    return out


def refresh_sku(data_root, branch, sku, env_file=None):
    pool = BRANCH.get(str(branch), str(branch))
    d6 = pd.read_excel(_path(data_root, "D6_v6_22.xlsx"), sheet_name="1_全量动作")
    d5 = pd.read_excel(_path(data_root, "D5_v6_8.xlsx"), sheet_name="1_预测")
    rows = d6[(d6["池"].astype(str) == pool) &
              (d6["product_id"].astype(str).str.upper() == str(sku).upper())].copy()
    if rows.empty:
        raise SystemExit(f"未找到 {pool}/{sku}")
    d5 = d5[(d5["horizon"].astype(str) == "97")][["product_id", "pool", "physical_form",
                                                   "canonical_uom", "p50", "q90", "q95", "model"]]
    d5 = d5.rename(columns={"pool": "池", "physical_form": "形态", "canonical_uom": "UOM",
                            "p50": "p50d5", "q90": "q90d5", "q95": "q95d5", "model": "模型"})
    rows = rows.merge(d5, on=["product_id", "池", "形态", "UOM"], how="left")
    tt = _tt_skus(data_root).get(str(sku), [])
    out = []
    for _, r in rows.iterrows():
        warehouse = {"美东USNJ": "美东-CENTRADE", "美中USTX": "美中-FZH-DANEEY",
                     "波兰": "波兰-FZHPoland-covers"}.get(pool)
        matches, partial = [], False
        for alias in sorted(set(tt)):
            live = _live_stock(data_root, alias, warehouse, env_file)
            if live["status"] == "matched":
                matches.append(live)
            else:
                partial = True
        if not matches:
            out.append({"sku": sku, "branch": pool, "warehouse": warehouse,
                        "refresh_action": "暂不能判断",
                        "reason": "EN 实时库存不可用/未匹配；未用旧快照冒充当前",
                        "live_status": "unavailable", "as_of": date.today().isoformat()})
            continue
        if len(matches) > 1:
            partial = True
        fields = {}
        for field in ("available", "intransit", "waiting_shipment", "defects"):
            vals = [m.get(field) for m in matches]
            fields[field] = None if partial or any(v is None for v in vals) else sum(vals)
        if partial or any(fields[f] is None for f in ("available", "intransit", "waiting_shipment")):
            out.append({"sku": sku, "branch": pool, "warehouse": warehouse,
                        "refresh_action": "暂不能判断", "reason": "实时库存字段未知/多别名",
                        "live_status": "partial", "live_stock": matches,
                        "as_of": date.today().isoformat()})
            continue
        q95 = float(r.get("q95d5") or r.get("q95") or 0)
        c_live = fields["available"]
        intransit = fields["intransit"]
        waiting = fields["waiting_shipment"]
        po = float(r.get("PO追加(去重)") or 0)
        so = float(r.get("SO已下") or 0)
        cg = float(r.get("CG可调拨抵扣") or 0)
        supply = c_live + intransit + po + so - cg
        net = max(0.0, q95 - supply)
        action = "补" if net > 0 and waiting <= 0 else ("催已有/待核" if net > 0 else "不补")
        out.append({
            "sku": sku, "tt_skus": tt, "branch": pool, "warehouse": warehouse,
            "forecast_source": "D5_v6_8 (reused, not retrained)",
            "q50": r.get("p50d5"), "q90": r.get("q90d5"), "q95": q95,
            "replay_action": r.get("建议动作"), "replay_new": r.get("新补数量"),
            "live_stock": matches, "C_live": c_live, "intransit": intransit,
            "waiting": waiting, "PO": po, "SO": so, "CG": cg,
            "net_refresh": net, "refresh_action": action,
            "warning": "forecast reused from pack; stock refreshed from EN; not a full D5 recompute",
            "as_of": date.today().isoformat(),
        })
    return out
