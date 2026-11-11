# -*- coding: utf-8 -*-
"""从月度 Google Sheet 导出原始订单 / FBA 销量表到本地快照（Colab 4.1.0 / 4.7.1 的读取步骤）。

Colab 直接 `gc.open(通途订单YYYYMM).worksheet('YYYY年M月订单')` 读；本脚本把同一动作落成本地
CSV，供 `build-order-tabs` 使用，并写 manifest 记录来源/行数/sha256。

用法（在 tongtool_order_cost 目录）：
  GSPREAD_SERVICE_ACCOUNT_FILE=<父仓库>/secrets/gsheets-service-account.json \
  uv run python scripts/fetch_month_orders.py --month 202609
  ... --kind raw    # 只导非 FBA 订单
  ... --kind fba    # 只导 FBA 销量表

输出：
  out/snapshots/<月>/raw_<月>.csv
  out/snapshots/<月>/raw_fba_<月>.csv
  out/snapshots/<月>/fetch_month_orders_manifest.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tongtool_order_cost import gsheets  # noqa: E402


def names(month: str) -> tuple[str, str, str]:
    y, m = int(month[:4]), int(month[4:6])
    if not (1 <= m <= 12):
        raise ValueError(f"月份非法: {month}")
    return f"通途订单{month}", f"{y}年{m}月订单", f"{y}年{m}月FBA订单"


def _retry(fn, n: int = 6):
    for i in range(n):
        try:
            return fn()
        except Exception:  # noqa: BLE001 - www.googleapis.com 偶发 SSL EOF
            if i == n - 1:
                raise
            time.sleep(4)


def clean_rows(rows: list[list[str]]) -> list[list[str]]:
    """去掉末尾全空行、行尾全空单元格；保留表头。"""
    out: list[list[str]] = []
    for row in rows:
        vals = ["" if v is None else str(v) for v in row]
        while vals and vals[-1] == "":
            vals.pop()
        out.append(vals)
    while out and not any(c.strip() for c in out[-1]):
        out.pop()
    return out


def require_columns(headers: list[str], required: tuple[str, ...], label: str) -> None:
    missing = [c for c in required if c not in headers]
    if missing:
        raise SystemExit(f"{label} 缺列 {missing}；实际表头 {headers}")


def sha256_rows(rows: list[list[str]]) -> str:
    h = hashlib.sha256()
    for row in rows:
        h.update(("\x1f".join(row) + "\n").encode("utf-8"))
    return h.hexdigest()


def export(kind: str, month: str, book: str, ws_name: str, out_path: Path,
           required: tuple[str, ...]) -> dict:
    gc = _retry(gsheets.client)
    sh = _retry(lambda: gc.open(book))
    ws = _retry(lambda: sh.worksheet(ws_name))
    rows = clean_rows(_retry(lambda: ws.get_all_values()))
    if not rows:
        raise SystemExit(f"{book}/{ws_name} 为空")
    require_columns(rows[0], required, f"{book}/{ws_name}")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    import csv

    with out_path.open("w", encoding="utf-8-sig", newline="") as f:
        csv.writer(f).writerows(rows)
    return {
        "kind": kind,
        "spreadsheet": book,
        "worksheet": ws_name,
        "path": str(out_path),
        "rows": len(rows) - 1,
        "columns": len(rows[0]),
        "sha256": sha256_rows(rows),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--month", required=True, help="如 202609")
    ap.add_argument("--spreadsheet", default=None, help="缺省 通途订单<月>")
    ap.add_argument("--kind", choices=["raw", "fba", "all"], default="all")
    ap.add_argument("--out-dir", default=None, help="缺省 out/snapshots/<月>")
    args = ap.parse_args()

    book, raw_ws, fba_ws = names(args.month)
    book = args.spreadsheet or book
    out_dir = Path(args.out_dir) if args.out_dir else ROOT / "out" / "snapshots" / args.month

    records = []
    if args.kind in ("raw", "all"):
        records.append(export(
            "raw", args.month, book, raw_ws,
            out_dir / f"raw_{args.month}.csv", ("订单号", "通途SKU"),
        ))
    if args.kind in ("fba", "all"):
        records.append(export(
            "fba", args.month, book, fba_ws,
            out_dir / f"raw_fba_{args.month}.csv", ("站点", "MSKU", "SKU"),
        ))

    manifest = {
        "month": args.month,
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
        "sources": records,
    }
    path = out_dir / "fetch_month_orders_manifest.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    for r in records:
        print(f"{r['kind']}: {r['worksheet']} -> {r['path']} ({r['rows']} 行)")
    print("manifest:", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
