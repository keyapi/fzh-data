# -*- coding: utf-8 -*-
"""Analyze Amazon online products that are on-sale but unpaired.

Uses the raw Sellfox pageList cache under out/pairing_cache/ and the latest
Tongtu alias export. It produces a focused operations workbook:
  - Amazon在售未配对全量
  - 三角靠枕候选
  - 汇总

This script is read-only: it never calls a pairing write endpoint.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

from tongtu_data import latest_tongtu_zip_path, load_tongtu_aliases, norm

CACHE_DIR = OUT / "pairing_cache"

TRIANGLE_KEYWORDS = ("triangle", "triangular")


def load_rows(name: str) -> list[dict]:
    path = CACHE_DIR / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(f"缺少缓存: {path}；先运行 fetch_sellfox_pairing.py")
    return json.loads(path.read_text(encoding="utf-8"))


def is_triangle(row: dict) -> bool:
    title = (row.get("title") or "").lower()
    sku = (row.get("sku") or "").lower()
    has_triangle_word = any(k in title for k in TRIANGLE_KEYWORDS)
    has_floor_or_corner = any(k in title for k in ("floor pillow", "corner pillow", "triangular cushion"))
    has_headboard = "headboard" in title or "bed wedge" in title
    return (has_triangle_word and not has_headboard) or has_floor_or_corner or sku.startswith("cenkz")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    rows = load_rows("amazon_unmatched")
    print(f"Amazon 未配对缓存: {len(rows)}")

    aliases = load_tongtu_aliases(latest_tongtu_zip_path()) if latest_tongtu_zip_path() else pd.DataFrame()
    tt_keys = set()
    for _, row in aliases.iterrows():
        tt_keys.add(norm(row.get("通途SKU")))
        tt_keys.add(norm(row.get("SKU别名")))
    print(f"通途别名键: {len(tt_keys)}")

    active = [r for r in rows if (r.get("onlineStatus") or "").upper() == "ACTIVE"]
    print(f"在售未配对: {len(active)}")

    records = []
    for r in active:
        sku = norm(r.get("sku"))
        records.append(
            {
                "店铺ID": norm(r.get("shopId")),
                "站点": norm(r.get("marketplaceId")),
                "平台SKU": sku,
                "ASIN": norm(r.get("asin")),
                "父ASIN": norm(r.get("parentAsin")),
                "配送方式": norm(r.get("switchFulfillmentTo")),
                "FNSKU": norm(r.get("fnsku")),
                "标题": norm(r.get("title")),
                "通途别名匹配": "是" if sku in tt_keys else "否",
                "建议": "可按通途别名直接配对" if sku in tt_keys else "待人工/后续模型",
            }
        )
    df = pd.DataFrame(records)
    tri = df[df.apply(lambda r: is_triangle({"title": r["标题"], "sku": r["平台SKU"]}), axis=1)].copy()

    summary = pd.DataFrame(
        [
            ("Amazon 未配对总数", len(rows)),
            ("在售未配对", len(active)),
            ("在售未配对且通途别名命中", int((df["通途别名匹配"] == "是").sum())),
            ("在售未配对 FBA(AFN)", int((df["配送方式"].str.upper() == "AFN").sum())),
            ("在售未配对 MFN", int((df["配送方式"].str.upper() == "MFN").sum())),
            ("三角靠枕候选", len(tri)),
            ("通途别名来源", latest_tongtu_zip_path().name if latest_tongtu_zip_path() else "未找到"),
            ("生成时间", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        ],
        columns=["指标", "值"],
    )

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = args.out or (OUT / f"Amazon在售未配对分析_{stamp}.xlsx")
    OUT.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        summary.to_excel(writer, sheet_name="汇总", index=False)
        df.to_excel(writer, sheet_name="Amazon在售未配对全量", index=False)
        tri.to_excel(writer, sheet_name="三角靠枕候选", index=False)

    print(f"已生成: {out_path}")
    print(
        f"在售未配对={len(df)} 别名命中={int((df['通途别名匹配'] == '是').sum())} "
        f"FBA={int((df['配送方式'].str.upper() == 'AFN').sum())} MFN={int((df['配送方式'].str.upper() == 'MFN').sum())} "
        f"三角候选={len(tri)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
