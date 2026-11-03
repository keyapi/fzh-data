# -*- coding: utf-8 -*-
"""US demand owner-migration diagnostic (read-only).

Compares historical warehouse pool (USNJ/USTX) with the current B r10 owner
for every US order line, and writes a per-product migration table.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

BASE = Path("D:/Work/fzh-order-store/analysis")
BRIDGE = BASE / "codex-repair-20261102/D_历史归一与回测_D3b_v3_4_2026-11-02.xlsx"
B_FILE = BASE / "仓库归属_A337_v6r10_2026-10-30.xlsx"
ORDERS = Path("D:/Work/fzh-order-store/orders_unified.parquet")
OUT_CSV = BASE / "us_owner_migration_20261102.csv"
OUT_JSON = BASE / "us_owner_migration_20261102.json"

POOL = {
    "CENTRADE": "美东USNJ", "美东-CENTRADE": "美东USNJ", "北美之路-NJ02": "美东USNJ",
    "FZH-DANEEY-皮壳仓库": "美中USTX", "FZH-DANEEY": "美中USTX",
    "FZH-DANEEY-成品仓": "美中USTX", "FZH-DANEEY-半成品仓": "美中USTX",
    "FZH-DANEEY-退货产品仓": "美中USTX", "美中-FZH-DANEEY": "美中USTX",
    "美中-FZH-DANEEY-皮壳仓库": "美中USTX", "美中-FZH-DANEEY-退货产品仓": "美中USTX",
    "休斯顿1号仓": "美中USTX", "休斯顿1号备用仓库": "美中USTX",
    "海外仓美中仓库备用仓": "美中USTX", "北美之路-LA01": "美中USTX",
}


def main() -> int:
    br = pd.read_excel(BRIDGE, sheet_name="1_映射桥")
    sku_map = dict(zip(br["sku_tongtool"].astype(str).str.lower(), br["product"].astype(str)))
    b = pd.read_excel(B_FILE, sheet_name="主表")
    bd = b[b["是否需求行"] == "Y"].copy()
    owner = bd.groupby("产品键")["美国责任方"].agg(lambda s: next((str(v) for v in s if pd.notna(v)), None)).to_dict()
    basis = bd.groupby("产品键")["最强证据层级"].agg(lambda s: next((str(v) for v in s if pd.notna(v)), None)).to_dict()

    o = pd.read_parquet(ORDERS)
    o["product"] = o["sku_tongtool"].astype(str).str.lower().map(sku_map)
    o["hist_pool"] = o["warehouse"].map(POOL)
    o["owner"] = o["product"].map(owner)
    o["year"] = pd.to_datetime(o["sale_date"], errors="coerce").dt.year
    u = o[(o["hist_pool"].isin(["美东USNJ", "美中USTX"])) & (o["owner"].isin(["美东USNJ", "美中USTX"]))].copy()

    rows = []
    for product, g in u.groupby("product"):
        pools = sorted(set(g["hist_pool"]))
        owner_v = g["owner"].iloc[0]
        hist = g.groupby("hist_pool")["qty"].sum().to_dict()
        moved = g[g["hist_pool"] != g["owner"]]
        direction = moved.groupby(["hist_pool", "owner"])["qty"].sum()
        rows.append({
            "product_id": product,
            "current_owner": owner_v,
            "owner_basis": basis.get(product),
            "hist_pools": ";".join(pools),
            "hist_qty_total": float(g["qty"].sum()),
            "hist_qty_USNJ": float(hist.get("美东USNJ", 0)),
            "hist_qty_USTX": float(hist.get("美中USTX", 0)),
            "moved_qty": float(moved["qty"].sum()),
            "moved_rows": int(len(moved)),
            "direction": ";".join(f"{a}->{b}:{v:.0f}" for (a, b), v in direction.items()),
            "both_pools": len(pools) > 1,
            "exception_current_USNJ_hist_USTX": bool(owner_v == "美东USNJ" and "美中USTX" in pools),
            "first_year": int(g["year"].min()) if g["year"].notna().any() else None,
            "last_year": int(g["year"].max()) if g["year"].notna().any() else None,
        })
    out = pd.DataFrame(rows).sort_values("moved_qty", ascending=False)
    out.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")

    summary = {
        "generated_at": pd.Timestamp.now().isoformat(),
        "us_qty_total": float(u["qty"].sum()),
        "us_rows": int(len(u)),
        "by_hist_pool": {k: float(v) for k, v in u.groupby("hist_pool")["qty"].sum().items()},
        "by_owner": {k: float(v) for k, v in u.groupby("owner")["qty"].sum().items()},
        "moved_qty": float(u.loc[u["hist_pool"] != u["owner"], "qty"].sum()),
        "moved_rows": int((u["hist_pool"] != u["owner"]).sum()),
        "moved_products": int(out[out["moved_qty"] > 0]["product_id"].nunique()),
        "both_pools_products": int(out["both_pools"].sum()),
        "exception_current_USNJ_hist_USTX_products": int(out["exception_current_USNJ_hist_USTX"].sum()),
        "directions": {
            f"{a}->{b}": float(v)
            for (a, b), v in u[u["hist_pool"] != u["owner"]].groupby(["hist_pool", "owner"])["qty"].sum().items()
        },
    }
    OUT_JSON.write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
