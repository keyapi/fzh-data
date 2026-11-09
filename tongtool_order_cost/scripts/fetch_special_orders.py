# -*- coding: utf-8 -*-
"""导出某月「处理特殊订单」删除清单，并可选过滤 raw 订单 CSV。

用法：
  uv run python tongtool_order_cost/scripts/fetch_special_orders.py --book 通途订单202608 \
      --out tongtool_order_cost/out/special_orders_202608.csv
  uv run python tongtool_order_cost/scripts/fetch_special_orders.py --book 通途订单202608 \
      --raw tongtool_order_cost/out/snapshots/202608/raw_202608.csv \
      --out-filtered tongtool_order_cost/out/snapshots/202608/raw_202608_filtered.csv
"""
from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tongtool_order_cost import gsheets  # noqa: E402


def _retry(fn, n=6):
    for i in range(n):
        try:
            return fn()
        except Exception:
            if i == n - 1:
                raise
            time.sleep(5)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", required=True, help="如 通途订单202608")
    ap.add_argument("--ws", default="处理特殊订单")
    ap.add_argument("--out", help="删除清单 CSV")
    ap.add_argument("--raw", help="要过滤的 raw 订单 CSV")
    ap.add_argument("--out-filtered", help="过滤后的 raw CSV")
    args = ap.parse_args()

    gc = _retry(gsheets.client)
    sh = _retry(lambda: gc.open(args.book))
    vals = _retry(lambda: sh.worksheet(args.ws).get_all_values())
    hdr = vals[0] if vals else []
    if "通途订单号" not in hdr or "处理方式" not in hdr:
        raise SystemExit(f"{args.ws} 缺列: {hdr}")
    ci_id, ci_action = hdr.index("通途订单号"), hdr.index("处理方式")
    ci_note = hdr.index("备注") if "备注" in hdr else None
    deleted = []
    for row in vals[1:]:
        oid = row[ci_id].strip() if ci_id < len(row) else ""
        act = row[ci_action].strip() if ci_action < len(row) else ""
        if oid and act == "删除":
            deleted.append({"通途订单号": oid,
                            "备注": row[ci_note].strip() if ci_note is not None and ci_note < len(row) else ""})
    print(f"{args.book}: 删除 {len(deleted)} 单")
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["通途订单号", "备注"])
            w.writeheader()
            w.writerows(deleted)
        print("saved", out)
    if args.raw and args.out_filtered:
        raw = pd.read_csv(args.raw, dtype=str, low_memory=False, keep_default_na=False)
        before = len(raw)
        ids = {x["通途订单号"] for x in deleted}
        filtered = raw[~raw["订单号"].astype(str).str.strip().isin(ids)]
        out = Path(args.out_filtered)
        out.parent.mkdir(parents=True, exist_ok=True)
        filtered.to_csv(out, index=False, encoding="utf-8-sig")
        print(f"filtered raw {before} -> {len(filtered)} (removed {before-len(filtered)}) -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
