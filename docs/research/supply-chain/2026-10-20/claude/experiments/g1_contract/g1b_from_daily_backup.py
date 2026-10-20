#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 stock_daily_backup.py 的 JSONL 备份转成 g1b_coverage.py 可读的快照 JSON。

输入：D:/Work/库存备份/YYYY-MM-DD/warehouse=*.jsonl + manifest.json
输出：out/stock_snapshot_from_daily.json（聚合，无 PII）

这样 G1b 覆盖使用每日 API 备份的 complete 结果，不用再重复打通途 API。
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backup-dir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--warehouses", default="", help="逗号分隔仓名；空=manifest 全部")
    args = ap.parse_args()

    root = Path(args.backup_dir)
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    wanted = {w.strip() for w in args.warehouses.split(",") if w.strip()}
    entries = manifest.get("warehouses", [])
    if wanted:
        entries = [e for e in entries if e.get("warehouseName") in wanted]

    by_sku: dict[str, dict] = {}
    by_wh: dict[str, dict] = {}
    selected = []
    for e in entries:
        name = e.get("warehouseName")
        path = Path(e.get("file") or "")
        if not path.is_file():
            continue
        selected.append(name)
        wh = by_wh.setdefault(name, {"available": 0.0, "intransit": 0.0, "defects": 0.0,
                                     "waiting": 0.0, "rows": 0, "complete": e.get("complete")})
        with path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                r = json.loads(line)
                sku = str(r.get("goodsSku") or "").strip()
                if not sku:
                    continue
                vals = {
                    "available": float(r.get("availableStockQuantity") or 0),
                    "intransit": float(r.get("intransitStockQuantity") or 0),
                    "defects": float(r.get("defectsStockQuantity") or 0),
                    "waiting": float(r.get("waitingShipmentStockQuantity") or 0),
                }
                entry = by_sku.setdefault(
                    sku, {"sku": sku, "warehouses": {}, "available": 0.0, "intransit": 0.0,
                          "defects": 0.0, "waiting": 0.0}
                )
                if name in entry["warehouses"]:
                    # JSONL 内同仓同 SKU 重复：保留首个，不累加
                    continue
                entry["warehouses"][name] = vals
                for k in vals:
                    entry[k] += vals[k]
                wh["rows"] += 1
                for k in vals:
                    wh[k] += vals[k]

    result = {
        "fetched_at": manifest.get("snapshot_at"),
        "capture_start": min((e.get("capture_start") for e in entries if e.get("capture_start")),
                             default=None),
        "capture_end": max((e.get("capture_end") for e in entries if e.get("capture_end")),
                           default=None),
        "source": "stock_daily_backup.py (tongtool API)",
        "warehouses": selected,
        "complete": all(e.get("complete") for e in entries),
        "complete_warehouses": [e.get("warehouseName") for e in entries if e.get("complete")],
        "bad_rows_total": sum(int(e.get("bad_rows") or 0) for e in entries),
        "by_warehouse": {
            k: {**v, **{f: round(v[f], 2) for f in ("available", "intransit", "defects", "waiting")}}
            for k, v in by_wh.items()
        },
        "by_sku": sorted(by_sku.values(), key=lambda x: x["sku"]),
        "notes": [
            "由每日 API JSONL 聚合；不重复请求通途。",
            "同仓同 SKU 重复行保留首个，不累加。",
            "complete 来自 manifest；未完成仓不应进入缺口统计。",
        ],
    }
    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"OK: {args.out}")
    print(f"  warehouses={len(selected)} skus={len(by_sku)} complete={result['complete']}")


if __name__ == "__main__":
    main()
