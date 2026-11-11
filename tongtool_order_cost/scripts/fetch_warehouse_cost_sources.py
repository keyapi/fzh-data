# -*- coding: utf-8 -*-
"""导出「和财务部共享 / 订单发货仓库对应成本来源」为本地 TSV。

这张表是仓库 → 成本来源编码的唯一事实源（对应成本工作簿 / 成本来源编码 /
头程运费来源编码 / 二次加工成本来源编码 / 发货区域 / 发货仓按销售汇总分类）。
本地 build-order-tabs 不再依赖 Colab 里的仓库映射逻辑。

用法：
  uv run python tongtool_order_cost/scripts/fetch_warehouse_cost_sources.py \
      --out tongtool_order_cost/out/warehouse_cost_sources.tsv
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

COLUMNS = (
    "发货仓库",
    "对应成本工作簿",
    "成本来源编码",
    "发货仓分类",
    "头程运费来源编码",
    "二次加工成本来源编码",
    "发货区域",
    "发货仓按销售汇总分类",
)


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
    ap.add_argument("--book", default="和财务部共享")
    ap.add_argument("--ws", default="订单发货仓库对应成本来源")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    gc = _retry(gsheets.client)
    sh = _retry(lambda: gc.open(args.book))
    vals = _retry(lambda: sh.worksheet(args.ws).get_all_values())
    if not vals:
        raise SystemExit("仓库成本来源表为空")
    header = [h.strip() for h in vals[0]]
    missing = [c for c in COLUMNS if c not in header]
    if missing:
        raise SystemExit(f"仓库成本来源表缺列: {missing}; 现有: {header}")
    idx = {c: header.index(c) for c in COLUMNS}
    rows = []
    for raw in vals[1:]:
        wh = raw[idx["发货仓库"]].strip() if idx["发货仓库"] < len(raw) else ""
        if not wh:
            continue
        rows.append({c: (raw[idx[c]].strip() if idx[c] < len(raw) else "") for c in COLUMNS})
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(COLUMNS), delimiter="\t")
        w.writeheader()
        w.writerows(rows)
    print(f"saved {out} rows={len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
