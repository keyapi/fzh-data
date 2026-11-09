# -*- coding: utf-8 -*-
"""D5 v6.7: apply 11/1-8 same-store nowcast factors to 21 keys only."""
from __future__ import annotations
from pathlib import Path
import hashlib, json
import pandas as pd

BASE = Path("D:/Work/fzh-order-store/analysis")
D5 = BASE / "D5v6_6-60cm/D_概率与服务_D5_v6_6_2026-11-07.xlsx"
NC = BASE / "nov_nowcast_20261109.csv"
OUTDIR = BASE / "D5v6_7-novcast"
OUT = OUTDIR / "D_概率与服务_D5_v6_7_2026-11-09.xlsx"
MANIFEST = OUTDIR / "D_概率与服务_D5_v6_7_2026-11-09.manifest.json"
KEYS = ["product_id", "pool", "physical_form", "canonical_uom"]


def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main() -> int:
    OUTDIR.mkdir(exist_ok=True)
    sheets = pd.read_excel(D5, sheet_name=None)
    pred = sheets["1_预测"].copy()
    nc = pd.read_csv(NC)
    nc["mkt"] = nc["mkt"].map({"US": "US", "PL": "PL"})
    pred["mkt"] = pred["pool"].map(
        lambda x: "US" if x in ("美东USNJ", "美中USTX") else ("PL" if x == "波兰" else "OTHER"))
    merged = pred.merge(nc[["mkt", "product_id", "hist_avg_3y", "nov1_8", "ratio",
                            "adjust_factor"]],
                        on=["mkt", "product_id"], how="left")
    merged["novcast_factor"] = pd.to_numeric(merged["adjust_factor"], errors="coerce").fillna(1.0)
    affected = merged["novcast_factor"].ne(1.0) & merged["novcast_factor"].notna()
    for c in ("p50", "q95"):
        merged.loc[affected, c] = pd.to_numeric(merged.loc[affected, c], errors="coerce") * merged.loc[affected, "novcast_factor"]
    merged["novcast_note"] = ""
    merged.loc[affected, "novcast_note"] = (
        "11/1-8同店修正 ×" + merged.loc[affected, "novcast_factor"].round(3).astype(str))
    pred_out = merged.drop(columns=["mkt"]).copy()
    note = merged.loc[affected, ["product_id", "pool", "physical_form", "canonical_uom",
                                 "horizon", "p50", "q95", "hist_avg_3y", "nov1_8",
                                 "ratio", "novcast_factor"]].copy()
    with pd.ExcelWriter(OUT, engine="openpyxl") as w:
        pred_out.to_excel(w, sheet_name="1_预测", index=False)
        for sn, df in sheets.items():
            if sn != "1_预测":
                df.to_excel(w, sheet_name=sn, index=False)
        note.to_excel(w, sheet_name="6_近期修正", index=False)
    m = {"rule_version": "D5-v6.7-novcast-2026-11-09",
         "base": {"path": str(D5), "sha256": sha(D5)},
         "nowcast": {"path": str(NC), "sha256": sha(NC)},
         "output": {"path": str(OUT), "sha256": sha(OUT)},
         "affected_rows": int(affected.sum()),
         "affected_keys": int(merged.loc[affected, "product_id"].nunique())}
    MANIFEST.write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8")
    print("wrote", OUT, "affected rows", int(affected.sum()),
          "keys", int(merged.loc[affected, "product_id"].nunique()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
