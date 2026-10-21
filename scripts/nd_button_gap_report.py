# -*- coding: utf-8 -*-
"""内胆数据质量报告：BOM vs 销售订单「增加配套物料」按钮

输出 `nd_button_gaps.csv`，列出每个含皮壳的成品 BOM：
  - status = both / neither / button_only / bom_only
  - bom_nd / button_nd
  - reason（bom_only 时给出根因：内胆停用、尺寸取错等）

只读本地 TSV，不调 API。用法：
  uv run python scripts/nd_button_gap_report.py
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

DEFAULT_OUT = Path("D:/Work/fzh-order-store")


def read_tsv(path: Path, names: list[str]) -> pd.DataFrame:
    return pd.read_csv(path, sep="\t", header=None, names=names, dtype=str, encoding="utf-8").fillna("")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    args = ap.parse_args()
    out = Path(args.out)

    ks = read_tsv(out / "ks_items.tsv", ["item_code", "item_group", "item_name"])
    grp = read_tsv(out / "item_groups_full.tsv", ["item_group", "ship_type", "replaced_by"])
    nd = read_tsv(out / "nd_items.tsv", ["item_code", "item_group", "has_variants", "disabled", "variant_of"])
    va = read_tsv(out / "variant_attrs.tsv", ["item_code", "attribute", "attribute_value"])
    bom = read_tsv(out / "bom.tsv", ["bom", "item", "quantity", "uom"]).sort_values("bom").drop_duplicates("item")
    bi = read_tsv(out / "bom_items.tsv",
                  ["parent", "idx", "item_code", "item_name", "qty", "uom", "source_warehouse", "rate"])
    bi = bi[bi["parent"].isin(set(bom["bom"]))].merge(bom[["bom", "item"]], left_on="parent", right_on="bom")

    size = (va[va["attribute"].str.contains("尺寸", na=False)]
            .drop_duplicates("item_code").set_index("item_code")["attribute_value"].to_dict())
    pk = ks[ks["item_code"].str.startswith("PK#")].copy()
    pk["size"] = pk["item_code"].map(size)
    pk["base"] = pk["item_group"].str.split("#", n=1).str[-1]
    pk["target"] = "内胆#" + pk["base"]
    remap = dict(zip(grp["item_group"], grp["replaced_by"]))
    pk["target"] = pk["target"].map(lambda g: remap.get(g) or g)
    nd_valid = nd[(nd["has_variants"] == "0") & (nd["disabled"] == "0")].copy()
    nd_valid["size"] = nd_valid["item_code"].map(size)
    lookup = {(r.item_group, r.size): r.item_code for r in nd_valid.itertuples() if r.size}
    pk["button_nd"] = [lookup.get((g, s)) for g, s in zip(pk["target"], pk["size"])]
    pk_by = {r.item_code: r for r in pk.itertuples()}
    nd_by = {r.item_code: r for r in nd.itertuples()}

    rows = []
    for fin, sub in bi[bi["item"].str.startswith("KS")].groupby("item"):
        pks = [x for x in sub["item_code"] if x.startswith("PK#")]
        if not pks:
            continue
        bom_nd = sorted(set(x for x in sub["item_code"] if x.startswith("ND#")))
        button_nd = sorted(set(pk_by[p].button_nd for p in pks
                               if p in pk_by and isinstance(pk_by[p].button_nd, str)))
        status = ("both" if bom_nd and button_nd else
                  "bom_only" if bom_nd else
                  "button_only" if button_nd else "neither")
        reason = ""
        if status == "bom_only":
            pk_item = pk_by[pks[0]]
            n = nd_by.get(bom_nd[0])
            if n is None:
                reason = "内胆物料不在 ND# 主数据"
            elif n.has_variants == "1":
                reason = "BOM 内胆是变体模板"
            elif n.disabled == "1":
                reason = "BOM 内胆已停用"
            elif not n.item_code or not size.get(n.item_code):
                reason = "BOM 内胆无尺寸属性"
            elif size.get(n.item_code) != pk_item.size:
                reason = f"尺寸不一致: 内胆={size.get(n.item_code)!r} / 皮壳={pk_item.size!r}"
            elif n.item_group != pk_item.target:
                reason = f"物料组不一致: {n.item_group!r} vs {pk_item.target!r}"
            else:
                reason = "按钮查找遗漏"
        rows.append({
            "finished_item": fin, "pk_items": ",".join(pks),
            "bom_nd": ",".join(bom_nd), "button_nd": ",".join(button_nd),
            "status": status, "reason": reason,
        })

    df = pd.DataFrame(rows).sort_values(["status", "finished_item"])
    path = out / "nd_button_gaps.csv"
    df.to_csv(path, index=False, encoding="utf-8-sig")
    print(df["status"].value_counts().to_string())
    print(df[df.status == "bom_only"]["reason"].value_counts().to_string())
    print(f"written: {path}")


if __name__ == "__main__":
    main()
