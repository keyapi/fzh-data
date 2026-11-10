# -*- coding: utf-8 -*-
"""Pull EN Tongtool Order 2026-11-09 and combine with the existing 11/01-08 file.

Read-only. Uses parent docs for the day (list without raw_data, then parallel raw_data)
to avoid the slow full-range raw_data query.
"""
from __future__ import annotations
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import pandas as pd
import requests
from dotenv import dotenv_values

BASE = Path("D:/Work/fzh-order-store/analysis")
PRIOR = BASE / "tongtool_orders_20261101_20261108.parquet"
OUT = BASE / "tongtool_orders_20261101_20261109.parquet"
ORDERS_OLD = Path("D:/Work/fzh-order-store/orders_unified.parquet")
ORDERS_NEW = Path("D:/Work/fzh-order-store/orders_unified_20261110.parquet")
D3B = BASE / "D_历史归一与回测_D3b_v3_8_2026-11-07.xlsx"
API = "https://erpnext.vilavi.cn"
ENV = Path("D:/Work/赛狐/Cursor/EN_API/.env")


def main() -> int:
    env = dotenv_values(ENV)
    key = env.get("ERP_API_KEY") or env.get("PROD_ERP_API_KEY")
    sec = env.get("ERP_API_SECRET") or env.get("PROD_ERP_API_SECRET")
    if not key or not sec:
        raise ValueError("EN credentials unavailable")
    s = requests.Session()
    s.headers["Authorization"] = f"token {key}:{sec}"
    r = s.get(API + "/api/resource/Tongtool Order", params={
        "fields": json.dumps(["name", "order_id_code", "sale_time"]),
        "filters": json.dumps([["sale_time", ">=", "2026-11-09 00:00:00"],
                               ["sale_time", "<", "2026-11-10 00:00:00"]]),
        "limit_page_length": 1000,
    }, timeout=120)
    r.raise_for_status()
    docs = r.json().get("data", [])
    print("11/09 orders", len(docs), flush=True)

    def fetch(d):
        n = d["name"]
        rr = s.get(API + "/api/resource/Tongtool Order/" + n,
                   params={"fields": json.dumps(["name", "order_id_code", "sale_time",
                                                 "order_status", "platform_code", "sale_account",
                                                 "warehouse_name", "package_id",
                                                 "tracking_number", "raw_data"])}, timeout=60)
        rr.raise_for_status()
        return rr.json()["data"]

    with ThreadPoolExecutor(max_workers=20) as ex:
        full = list(ex.map(fetch, docs))
    print("fetched raw", len(full), flush=True)

    out = []
    for d in full:
        try:
            raw = json.loads(d.get("raw_data") or "{}")
        except Exception:
            raw = {}
        items = raw.get("orderItem") or []
        if not items:
            out.append({
                "order_id": d.get("order_id_code") or d.get("name"),
                "sale_time": d.get("sale_time"), "order_status": d.get("order_status"),
                "platform_code": d.get("platform_code"), "sale_account": d.get("sale_account"),
                "warehouse_name": d.get("warehouse_name"), "package_id": d.get("package_id"),
                "platform_sku": None, "tongtool_sku": None, "erp_item_code": None,
                "qty": 0.0, "item_name": None, "error": "no orderItem",
            })
            continue
        for it in items:
            out.append({
                "order_id": d.get("order_id_code") or d.get("name"),
                "sale_time": d.get("sale_time"), "order_status": d.get("order_status"),
                "platform_code": d.get("platform_code"), "sale_account": d.get("sale_account"),
                "warehouse_name": d.get("warehouse_name"), "package_id": d.get("package_id"),
                "platform_sku": it.get("sku"), "tongtool_sku": it.get("goodsSku"),
                "erp_item_code": None, "qty": it.get("quantityPurchased"),
                "item_name": it.get("productName"), "error": None,
            })
    new = pd.DataFrame(out)
    bridge = pd.read_excel(D3B, sheet_name="1_映射桥")
    bridge = bridge[bridge["status"].astype(str).eq("唯一")][["sku_tongtool", "product"]]
    bridge = bridge.drop_duplicates("sku_tongtool").rename(
        columns={"sku_tongtool": "tongtool_sku", "product": "erp_item_code"})
    new = new.merge(bridge, on="tongtool_sku", how="left", suffixes=("", "_m"))
    new["erp_item_code"] = new["erp_item_code_m"].combine_first(new["erp_item_code"])
    new = new.drop(columns=["erp_item_code_m"], errors="ignore")
    prior = pd.read_parquet(PRIOR)
    allorders = pd.concat([prior, new], ignore_index=True)
    allorders.to_parquet(OUT, index=False)
    print("wrote", OUT, len(allorders), "rows; 11/09 qty", new.qty.fillna(0).sum(),
          "mapped", int(new.erp_item_code.notna().sum()), flush=True)

    # Append 11/09 rows to orders_unified for D6 CG sales (only warehouse/sku/qty used).
    old = pd.read_parquet(ORDERS_OLD)
    add = new.copy()
    add["sale_date"] = pd.to_datetime(add["sale_time"], errors="coerce").dt.strftime("%Y-%m-%d")
    add["despatch_date"] = add["sale_date"]
    add["qty"] = pd.to_numeric(add["qty"], errors="coerce").fillna(0).astype("int64")
    add["channel"] = add["platform_code"]
    add["account"] = add["sale_account"]
    add["warehouse"] = add["warehouse_name"]
    add["amount_raw_cny"] = 0.0
    add["freight_estimated"] = None
    add["freight_actual"] = None
    add["currency"] = "USD"
    add["month"] = pd.to_datetime(add["sale_time"], errors="coerce").dt.strftime("%Y%m")
    add["source"] = "en_20261110"
    add["freight_semantics"] = "unknown"
    add["line_id"] = [f"20261110:{i}" for i in range(len(add))]
    add = add.rename(columns={"order_id": "order_id", "tongtool_sku": "sku_tongtool"})
    cols = list(old.columns)
    add = add.reindex(columns=cols)
    merged = pd.concat([old, add], ignore_index=True)
    merged.to_parquet(ORDERS_NEW, index=False)
    print("wrote", ORDERS_NEW, len(merged), "rows; appended", len(add), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
