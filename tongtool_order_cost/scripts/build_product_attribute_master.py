# -*- coding: utf-8 -*-
"""从历史 self 166 表抽取「以 SKU 为键」的产品主数据，生成 product_attributes.tsv。

用途：`build-order-tabs` 不再运行 Colab，但产品展示属性（品类/面料/尺寸/编码等）
仍需要一份稳定的本地主数据。本脚本把历史上已经由 Colab 解析好的属性固化成 TSV；
新月份遇到新 SKU 时，builder 会回落到原始订单 / EN BOM，缺失项在报告里列出。

用法：
  uv run python tongtool_order_cost/scripts/build_product_attribute_master.py \
      --fresh tongtool_order_cost/out/wb_fresh_202608.csv \
              tongtool_order_cost/out/wb_fresh_202609.csv \
      --out tongtool_order_cost/out/product_attributes.tsv
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from tongtool_order_cost.tongtu_cost_engine.domain.split_merge import normalize_sku  # noqa: E402
from tongtool_order_cost.tongtu_cost_engine.domain.tab_contracts import (  # noqa: E402
    PRODUCT_ATTR_COLUMNS,
)

KEY_COLUMNS = ("通途SKU", "平台SKU_统一", "品类尺寸面料编码")


def _empty(v: object) -> bool:
    s = str(v).strip() if v is not None else ""
    return s in ("", "nan", "None", "NULL")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fresh", nargs="+", required=True, help="历史 self 166 CSV")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    frames = []
    for p in args.fresh:
        path = Path(p)
        if not path.exists():
            raise SystemExit(f"文件不存在: {path}")
        frames.append(pd.read_csv(path, dtype=str, low_memory=False, keep_default_na=False))
    df = pd.concat(frames, ignore_index=True)

    # (键类型, 键值) → 列 → 候选值计数
    acc: dict[tuple[str, str], dict[str, Counter]] = {}
    for rec in df.to_dict("records"):
        sku = normalize_sku(rec.get("通途SKU"))
        keys: list[tuple[str, str]] = []
        if sku:
            keys.append(("sku", sku))
        plat = normalize_sku(rec.get("平台SKU_统一") or rec.get("平台SKU"))
        if plat and plat != sku:
            keys.append(("platform", plat))
        for key in keys:
            bucket = acc.setdefault(key, {c: Counter() for c in PRODUCT_ATTR_COLUMNS})
            for col in PRODUCT_ATTR_COLUMNS:
                val = str(rec.get(col) or "").strip()
                if not _empty(val):
                    bucket[col][val] += 1

    rows = []
    conflicts = []
    for (kind, key), bucket in sorted(acc.items()):
        row = {"键类型": kind, "键值": key}
        for col in PRODUCT_ATTR_COLUMNS:
            vals = bucket[col]
            if not vals:
                row[col] = ""
                continue
            value, n = vals.most_common(1)[0]
            row[col] = value
            if len(vals) > 1:
                conflicts.append({
                    "键类型": kind, "键值": key, "列": col,
                    "取值数": len(vals), "占比": f"{n}/{sum(vals.values())}",
                })
        rows.append(row)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    cols = ["键类型", "键值", *PRODUCT_ATTR_COLUMNS]
    with out.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, delimiter="\t")
        w.writeheader()
        w.writerows(rows)
    print(f"saved {out} rows={len(rows)} conflicts={len(conflicts)}")
    if conflicts:
        cpath = out.with_suffix(".conflicts.csv")
        pd.DataFrame(conflicts).to_csv(cpath, index=False, encoding="utf-8-sig")
        print(f"conflicts -> {cpath}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
