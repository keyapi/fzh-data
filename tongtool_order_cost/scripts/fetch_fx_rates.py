# -*- coding: utf-8 -*-
"""导出某月汇率表（和财务部共享 / 汇率）为本地 CSV。

用法：
  uv run python tongtool_order_cost/scripts/fetch_fx_rates.py --month 202608 \
      --out tongtool_order_cost/out/fx_202608.csv
"""
from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

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
    ap.add_argument("--month", required=True, help="汇率列名，如 202608")
    ap.add_argument("--book", default="和财务部共享")
    ap.add_argument("--ws", default="汇率")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    gc = _retry(gsheets.client)
    sh = _retry(lambda: gc.open(args.book))
    vals = _retry(lambda: sh.worksheet(args.ws).get_all_values())
    if not vals:
        raise SystemExit("汇率表为空")
    hdr = vals[0]
    if args.month not in hdr:
        raise SystemExit(f"汇率表没有月份列 {args.month}；现有: {hdr[-8:]}")
    ci_month = hdr.index(args.month)
    ci_cur = hdr.index("收款币种") if "收款币种" in hdr else 0
    rows = []
    for row in vals[1:]:
        cur = row[ci_cur].strip() if ci_cur < len(row) else ""
        rate = row[ci_month].strip() if ci_month < len(row) else ""
        if cur and rate:
            rows.append({"收款币种": cur, "汇率": rate})
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["收款币种", "汇率"])
        w.writeheader()
        w.writerows(rows)
    print(f"saved {out} rows={len(rows)} month={args.month}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
