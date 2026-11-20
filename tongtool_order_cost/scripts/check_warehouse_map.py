# -*- coding: utf-8 -*-
"""检查月度 raw 订单的发货仓库是否都在 wh_map.tsv 中（EN Tongtu Shipping Warehouse）。

用法：
  uv run python tongtool_order_cost/scripts/check_warehouse_map.py --month 202608 \
      --raw tongtool_order_cost/out/snapshots/202608/raw_202608.csv \
      --wh-map tongtool_order_cost/out/snapshots/202608/wh_map.tsv
"""
from __future__ import annotations

import argparse

import pandas as pd


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--month", required=True)
    ap.add_argument("--raw", required=True)
    ap.add_argument("--wh-map", required=True)
    args = ap.parse_args()
    raw = pd.read_csv(args.raw, dtype=str, low_memory=False, keep_default_na=False)
    wh = pd.read_csv(args.wh_map, sep="\t", dtype=str, keep_default_na=False)
    if "发货仓库" not in raw.columns or "name" not in wh.columns:
        raise SystemExit("列不存在：raw.发货仓库 / wh_map.name")
    raw_set = {x.strip() for x in raw["发货仓库"].astype(str) if x.strip()}
    map_set = {x.strip() for x in wh["name"].astype(str) if x.strip()}
    missing = sorted(raw_set - map_set)
    print(f"{args.month}: raw 仓库 {len(raw_set)} 个 / wh_map {len(map_set)} 个 / 未映射 {len(missing)}")
    for x in missing:
        print("  MISSING", x)
    return 0 if not missing else 1


if __name__ == "__main__":
    raise SystemExit(main())
