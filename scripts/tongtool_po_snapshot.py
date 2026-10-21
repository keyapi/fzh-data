# -*- coding: utf-8 -*-
"""通途采购在途快照（只读）

按采购日期窗口拉取 PO，计算未入库量 = quantity - in_quantity，
按 (goods_sku, warehouseName) 汇总写入 DuckDB `tongtool_po_open`。

限流 5 次/分钟，12 秒间隔。

用法：
  uv run python scripts/tongtool_po_snapshot.py --from 2026-06-01 --max-pages 10
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
from pathlib import Path

import duckdb
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = Path("D:/Work/赛狐/Cursor/tongtool_api/.env")
PACE = 12


def load_env(path: Path) -> dict:
    vals = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            vals[k.strip()] = v.strip().strip('"').strip("'")
    return vals


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="D:/Work/fzh-order-store")
    ap.add_argument("--from", dest="date_from", default="2026-06-01")
    ap.add_argument("--to", dest="date_to", default=dt.date.today().isoformat())
    ap.add_argument("--max-pages", type=int, default=10)
    args = ap.parse_args()

    sys.path.insert(0, str(REPO_ROOT))
    from tongtool_api.mcp_http import McpClient
    env = load_env(ENV_FILE)
    client = McpClient(env["TONGTOOL_ERP2_PRIMARY_KEY"], env["TONGTOOL_ERP2_PRIMARY_SECRET"])

    def call(name, payload, tries=6):
        last = None
        for i in range(tries):
            try:
                r = client.call(name, payload)
                txt = r.get("result", {}).get("content", [{}])[0].get("text", "{}")
                return json.loads(txt)
            except Exception as e:
                last = e
                time.sleep(20)
        raise RuntimeError(f"MCP {name} failed: {str(last)[:120]}")

    rows = []
    for p in range(1, args.max_pages + 1):
        time.sleep(PACE)
        d = call("erp2_purchase_purchaseorderquery", {
            "pageNo": p, "pageSize": 100,
            "purchaseDateFrom": f"{args.date_from} 00:00:00",
            "purchaseDateTo": f"{args.date_to} 23:59:59",
        })
        arr = (d.get("datas") or {}).get("array") or []
        if not arr:
            break
        for x in arr:
            qty = x.get("quantity") or 0
            inc = x.get("in_quantity") or 0
            open_qty = max(0, float(qty) - float(inc))
            rows.append({
                "ponum": x.get("PONum"), "goods_sku": x.get("goods_sku"),
                "warehouse": x.get("warehouseName"),
                "quantity": qty, "in_quantity": inc, "open_qty": open_qty,
                "status": x.get("status"), "purchase_date": x.get("purchaseDate"),
                "will_arrive_date": x.get("willArriveDate"),
                "supplier_code": x.get("supplier_code"),
            })
        if len(arr) < 100:
            break

    df = pd.DataFrame(rows)
    con = duckdb.connect(str(Path(args.out) / "order_store.duckdb"))
    if not df.empty:
        con.register("_po", df)
        con.execute("CREATE OR REPLACE TABLE tongtool_po AS SELECT * FROM _po")
        con.execute("""CREATE OR REPLACE TABLE tongtool_po_open AS
            SELECT goods_sku AS sku, warehouse, SUM(open_qty) AS on_order
            FROM _po WHERE open_qty > 0 GROUP BY 1, 2""")
        con.unregister("_po")
    n_open = con.execute("SELECT COUNT(*), SUM(on_order) FROM tongtool_po_open").fetchone() if not df.empty else (0, 0)
    con.close()
    print(json.dumps({"po_rows": len(rows), "open_sku_wh": n_open[0], "open_qty": n_open[1],
                      "window": [args.date_from, args.date_to]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
