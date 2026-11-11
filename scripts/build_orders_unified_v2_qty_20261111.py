# -*- coding: utf-8 -*-
"""给 orders_unified 增加 qty_pieces：平台套件按 pcs_per_set 换算成件。"""
from pathlib import Path
import json
import pandas as pd

ROOT = Path("D:/Work/fzh-order-store")
AN = ROOT / "analysis"
o = pd.read_parquet(ROOT / "orders_unified_20261111.parquet")
mp = pd.read_csv(AN / "platform_unit_map_20261111.csv")
mp = mp.groupby(["platform_sku", "sku_tongtool"]).agg(
    pcs_per_set=("pcs_per_set", "max"), qty_basis=("qty_basis", "first"), factor=("factor", "max")).reset_index()
o = o.merge(mp, on=["platform_sku", "sku_tongtool"], how="left")
o["pcs_per_set"] = o["pcs_per_set"].fillna(1)
o["qty_basis"] = o["qty_basis"].fillna("pieces")
o["factor"] = o["factor"].fillna(1)
o["qty"] = pd.to_numeric(o["qty"], errors="coerce").fillna(0)
o["qty_pieces"] = o["qty"] * o["factor"]
out = ROOT / "orders_unified_20261111_v2.parquet"
o.to_parquet(out, index=False)
s = o[o.factor > 1]
rep = {"rows": len(o), "qty": float(o.qty.sum()), "qty_pieces": float(o.qty_pieces.sum()),
       "delta": float(o.qty_pieces.sum() - o.qty.sum()),
       "affected_rows": len(s), "affected_qty": float(s.qty.sum()), "affected_pieces": float(s.qty_pieces.sum()),
       "factor_distribution": o.factor.value_counts().head(10).to_dict()}
AN.joinpath("orders_unified_20261111_v2_report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(rep, ensure_ascii=False, indent=2))
