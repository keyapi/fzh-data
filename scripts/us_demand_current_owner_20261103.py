# -*- coding: utf-8 -*-
"""Build current-owner vs as-of US demand monthly series (diagnostic, read-only).

Current-owner restatement follows Codex guidance:
- only proven unique B owner absorbs the product's US demand;
- historical warehouse is kept as evidence/migration flag;
- raw orders, inventory and supply are not modified;
- weak/ambiguous owner -> US_unassigned;
- returns follow the original order/product, not the return warehouse.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

BASE = Path("D:/Work/fzh-order-store/analysis")
BRIDGE = BASE / "codex-repair-20261102/D_历史归一与回测_D3b_v3_4_2026-11-02.xlsx"
B_FILE = BASE / "仓库归属_A337_v6r10_2026-10-30.xlsx"
ORDERS = Path("D:/Work/fzh-order-store/orders_unified.parquet")
MIG = BASE / "us_owner_migration_20261102.csv"
OUT_PARQUET = BASE / "us_demand_current_owner_monthly_20261103.parquet"
OUT_CSV = BASE / "us_demand_current_owner_monthly_20261103.csv"
OUT_JSON = BASE / "us_demand_current_owner_summary_20261103.json"

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
    # Unique proven owner only; if a product has multiple owners, leave unassigned.
    owners = bd.groupby("产品键")["美国责任方"].agg(
        lambda s: tuple(sorted({str(v) for v in s if pd.notna(v)}))
    ).to_dict()
    owner = {k: (v[0] if len(v) == 1 else None) for k, v in owners.items()}
    basis = bd.groupby("产品键")["最强证据层级"].agg(
        lambda s: next((str(v) for v in s if pd.notna(v)), None)
    ).to_dict()
    mig = pd.read_csv(MIG, encoding="utf-8-sig")
    both = set(mig.loc[mig["both_pools"], "product_id"])
    exc = set(mig.loc[mig["exception_current_USNJ_hist_USTX"], "product_id"])

    o = pd.read_parquet(ORDERS)
    o["sale_date"] = pd.to_datetime(o["sale_date"], errors="coerce")
    o["month"] = o["sale_date"].dt.strftime("%Y%m")
    o["product"] = o["sku_tongtool"].astype(str).str.lower().map(sku_map)
    o["hist_pool"] = o["warehouse"].map(POOL)
    o["owner"] = o["product"].map(owner)
    o = o[(o["hist_pool"].isin(["美东USNJ", "美中USTX"])) & o["product"].notna()].copy()
    o["current_pool"] = o.apply(
        lambda r: r["owner"] if r["owner"] in ("美东USNJ", "美中USTX") else "US_unassigned",
        axis=1,
    )
    o["migration"] = o.apply(
        lambda r: "moved" if r["owner"] in ("美东USNJ", "美中USTX") and r["hist_pool"] != r["owner"]
        else ("same" if r["owner"] in ("美东USNJ", "美中USTX") else "owner_unknown"),
        axis=1,
    )
    o["is_return"] = o["qty"] < 0
    o["both_pools"] = o["product"].isin(both)
    o["exception"] = o["product"].isin(exc)
    o["owner_basis"] = o["product"].map(basis)

    # as-of series: historical warehouse
    asof = (o.groupby(["product", "hist_pool", "month"], dropna=False)["qty"]
            .sum().reset_index().rename(columns={"hist_pool": "pool", "qty": "qty_asof"}))
    # current-owner series: current owner (or unassigned)
    cur = (o.groupby(["product", "current_pool", "month"], dropna=False)["qty"]
           .sum().reset_index().rename(columns={"current_pool": "pool", "qty": "qty_current_owner"}))
    # combine on product/pool/month; same pool may have as-of qty
    out = cur.merge(asof, on=["product", "pool", "month"], how="outer")
    out["qty_current_owner"] = out["qty_current_owner"].fillna(0.0)
    out["qty_asof"] = out["qty_asof"].fillna(0.0)
    out["owner_basis"] = out["product"].map(basis)
    out["both_pools"] = out["product"].isin(both)
    out["exception"] = out["product"].isin(exc)
    out["source"] = "EN orders_unified; current owner B r10"
    out.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")
    try:
        out.to_parquet(OUT_PARQUET, index=False)
    except Exception as e:  # noqa: BLE001
        print(f"parquet write failed: {e}")

    summary = {
        "generated_at": pd.Timestamp.now().isoformat(),
        "rows": int(len(out)),
        "products": int(out["product"].nunique()),
        "qty_total": float(o["qty"].sum()),
        "qty_current_owner": float(out["qty_current_owner"].sum()),
        "qty_asof": float(out["qty_asof"].sum()),
        "owner_unknown_qty": float(o.loc[o["owner"].isna(), "qty"].sum()),
        "moved_qty": float(o.loc[o["migration"] == "moved", "qty"].sum()),
        "return_rows": int(o["is_return"].sum()),
        "return_qty": float(o.loc[o["is_return"], "qty"].sum()),
        "both_pools_products": len(both),
        "exception_products": len(exc),
        "pools_current": {k: float(v) for k, v in o.groupby("current_pool")["qty"].sum().items()},
        "pools_asof": {k: float(v) for k, v in o.groupby("hist_pool")["qty"].sum().items()},
    }
    OUT_JSON.write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
