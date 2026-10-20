# -*- coding: utf-8 -*-
"""订单历史分析库（试点）

把 GS 月表（通途订单YYYYMM / YYYY年M月订单）解析成统一订单明细，
写入 DuckDB，并与 EN 的 Tongtool Order 做并集/去重与覆盖核对。

设计要点
- 只读：不写 EN、不调通途 API（EN 侧仅按订单号抽样查询，走 order_id_code 索引）。
- 口径：GS 是发货口径，但带「销售日期」列，统一表以 sale_date 为主、保留 despatch_date。
- 并集 precedence：同一 order_id 两边都有时以 EN 为准（明细/匹配更完整）。
- 产物落在 --out 指定目录（默认系统临时目录），不进入 git。

用法：
  uv run python scripts/forecast_order_store.py --months 202507,202608 --en-sample 200
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from pathlib import Path

import duckdb
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = Path("D:/Work/赛狐/Cursor/EN_API/.env")
SA_FILE = "D:/Work/赛狐/Cursor/secrets/gsheets-service-account.json"

GS_COLS = {
    "order_id": "订单号",
    "platform_sku": "平台SKU",
    "sku_tongtool": "通途SKU",
    "qty": "发货数量",
    "sale_date": "销售日期",
    "despatch_date": "发货日期",
    "channel": "渠道",
    "account": "渠道账号",
    "warehouse": "发货仓库",
    "package_id": "包裹号",
    "tracking": "跟踪号",
    "currency": "收款币种",
    "amount_raw_cny": "订单总售价(人民币)",
    "freight_estimated": "通途运费",   # 通途预估运费（2024 起）
    "freight_actual": "物流商运费",   # 真实运费（2024 起）
    "freight_legacy": "运费",         # 2023 唯一的运费列
}


def load_env(path: Path) -> dict:
    vals = {}
    if not path.exists():
        return vals
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        vals[k.strip()] = v.strip().strip('"').strip("'")
    return vals


def gs_client():
    os.environ["GSPREAD_SERVICE_ACCOUNT_FILE"] = SA_FILE
    sys.path.insert(0, str(REPO_ROOT))
    from tongtool_order_cost.tongtool_order_cost.gsheets import client
    return client()


def retry(fn, tries=8, delay=4):
    last = None
    for i in range(tries):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(delay)
    raise last


def fetch_gs_month(gc, ym: str, raw_dir: Path | None = None) -> pd.DataFrame:
    y, m = int(ym[:4]), int(ym[4:])
    sh = retry(lambda: gc.open(f"通途订单{ym}"))
    ws = retry(lambda: sh.worksheet(f"{y}年{m}月订单"))
    rows = retry(lambda: ws.get_all_values())
    if not rows:
        raise RuntimeError(f"{ym}: empty worksheet")
    hdr = rows[0]
    raw = pd.DataFrame(rows[1:], columns=hdr)
    if raw_dir is not None:
        raw_dir.mkdir(parents=True, exist_ok=True)
        raw.to_parquet(raw_dir / f"raw_{ym}.parquet", index=False)

    out = pd.DataFrame()
    for target, src in GS_COLS.items():
        out[target] = raw[src].astype(str).str.strip() if src in raw.columns else pd.NA
    out["month"] = ym
    out["source"] = "gs"
    out = out[out["order_id"].notna() & (out["order_id"] != "")]

    # 运费口径：2024 起 物流商运费=真实、通途运费=预估；2023 只有 运费（legacy，语义存疑）
    has_actual = raw["物流商运费"].notna() if "物流商运费" in raw.columns else pd.Series(False, index=raw.index)
    out["freight_actual"] = out["freight_actual"].where(out["freight_actual"].notna(), out["freight_legacy"])
    out["freight_semantics"] = "carrier" if "物流商运费" in raw.columns else ("legacy" if "运费" in raw.columns else pd.NA)
    out = out.drop(columns=["freight_legacy"])

    if "售价(人民币)" in raw.columns:
        fallback = pd.to_numeric(out.get("amount_raw_cny"), errors="coerce")
        per_unit = pd.to_numeric(raw["售价(人民币)"], errors="coerce")
        qty = pd.to_numeric(out["qty"], errors="coerce")
        out["amount_raw_cny"] = fallback.where(fallback.notna(), per_unit * qty)

    out["qty"] = pd.to_numeric(out["qty"], errors="coerce")
    out["amount_raw_cny"] = pd.to_numeric(out["amount_raw_cny"], errors="coerce")
    for c in ("freight_actual", "freight_estimated"):
        out[c] = pd.to_numeric(out[c], errors="coerce")
    out["line_id"] = [f"{ym}:{i}" for i in range(len(out))]
    return out.reset_index(drop=True)


def fetch_en_orders(ids: list[str], chunk: int = 40) -> pd.DataFrame:
    import requests

    env = load_env(ENV_FILE)
    base = "https://erpnext.vilavi.cn"
    auth = {"Authorization": f"token {env['ERP_API_KEY']}:{env['ERP_API_SECRET']}"}
    fields = ["name", "order_id_code", "sale_time", "despatch_complete_time",
              "platform_code", "sale_account", "warehouse_name", "order_status",
              "channel_account_en"]
    rows = []
    for i in range(0, len(ids), chunk):
        flt = [["Tongtool Order", "order_id_code", "in", ids[i:i + chunk]]]
        for _ in range(4):
            try:
                r = requests.get(f"{base}/api/resource/Tongtool%20Order", headers=auth,
                                 params={"filters": json.dumps(flt), "fields": json.dumps(fields),
                                         "limit_page_length": 0}, timeout=120)
                if r.status_code == 200:
                    rows.extend(r.json().get("data", []))
                    break
                raise RuntimeError(r.status_code)
            except Exception:
                time.sleep(3)
        time.sleep(0.2)
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df = df.rename(columns={"order_id_code": "order_id", "sale_time": "sale_date",
                            "despatch_complete_time": "despatch_date", "platform_code": "channel",
                            "sale_account": "account", "warehouse_name": "warehouse"})
    df["source"] = "en"
    df["month"] = pd.NA
    return df[["order_id", "sale_date", "despatch_date", "channel", "account",
               "warehouse", "order_status", "source", "month"]]


FBA_COLS = {
    "msku": "MSKU",
    "sku": "SKU",
    "category": "品类",
    "product_name": "产品名称",
    "site": "站点",
    "developer": "开发人员",
    "order_count": "订单数量",
    "sales_qty": "销量",
    "sales_amount": "销售额",
    "cost": "成本",
    "order_fee": "订单费用",
    "first_leg_fee": "头程费用",
    "custom_fee": "自定义费用",
    "profit": "利润",
    "profit_margin": "利润率",
}


def fetch_fba_month(gc, ym: str) -> pd.DataFrame | None:
    y, m = int(ym[:4]), int(ym[4:])
    sh = retry(lambda: gc.open(f"通途订单{ym}"))
    titles = retry(lambda: [w.title for w in sh.worksheets()])
    wsname = f"{y}年{m}月FBA订单"
    if wsname not in titles:
        return None
    ws = retry(lambda: sh.worksheet(wsname))
    rows = retry(lambda: ws.get_all_values())
    if len(rows) < 2:
        return None
    raw = pd.DataFrame(rows[1:], columns=rows[0])
    out = pd.DataFrame()
    for target, src in FBA_COLS.items():
        out[target] = raw[src].astype(str).str.strip() if src in raw.columns else pd.NA
    out["month"] = ym
    for c in ("order_count", "sales_qty", "sales_amount", "cost", "order_fee",
              "first_leg_fee", "custom_fee", "profit", "profit_margin"):
        out[c] = pd.to_numeric(out[c], errors="coerce")
    out = out[(out["msku"].notna() & (out["msku"] != "")) | (out["sku"].notna() & (out["sku"] != ""))]
    return out.reset_index(drop=True)


def write_table(con, name: str, df: pd.DataFrame, month_col: str = "month", replace_all: bool = False):
    """建表/增量写入：删掉本次涉及的月份再插入，避免重复。"""
    if df is None or df.empty:
        return
    con.register("_new_df", df)
    con.execute(f"CREATE TABLE IF NOT EXISTS {name} AS SELECT * FROM _new_df WHERE 1=0")
    if replace_all or month_col is None or month_col not in df.columns:
        con.execute(f"DELETE FROM {name}")
    else:
        con.execute(f"DELETE FROM {name} WHERE {month_col} IN (SELECT DISTINCT {month_col} FROM _new_df)")
    con.execute(f"INSERT INTO {name} SELECT * FROM _new_df")
    con.unregister("_new_df")


def fetch_en_sku_map() -> pd.DataFrame:
    """EN 客户物料号 → 物料编码（通途SKU 在 EN 的登记处之一）。"""
    import requests

    env = load_env(ENV_FILE)
    base = "https://erpnext.vilavi.cn"
    auth = {"Authorization": f"token {env['ERP_API_KEY']}:{env['ERP_API_SECRET']}"}
    rows, start = [], 0
    while True:
        page, ok = [], False
        for _ in range(5):
            try:
                r = requests.get(f"{base}/api/resource/Item%20Customer%20Detail", headers=auth,
                                 params={"fields": json.dumps(["parent", "ref_code", "customer_name"]),
                                         "limit_start": start, "limit_page_length": 2000}, timeout=180)
                if r.status_code == 200:
                    page = r.json().get("data", [])
                    ok = True
                    break
                raise RuntimeError(f"HTTP {r.status_code}: {r.text[:120]}")
            except Exception:
                time.sleep(3)
        if not ok:
            raise RuntimeError("fetch Item Customer Detail failed")
        rows.extend(page)
        if len(page) < 2000:
            break
        start += 2000
    df = pd.DataFrame(rows).rename(columns={"parent": "item_code", "ref_code": "tongtool_sku"})
    df["tongtool_sku"] = df["tongtool_sku"].astype(str).str.strip()
    df = df[df["tongtool_sku"] != ""].drop_duplicates(subset=["tongtool_sku"])
    return df


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--months", default="202507,202608")
    ap.add_argument("--en-sample", type=int, default=200,
                    help="每个 GS 月抽样多少订单号去 EN 核对（0=不查 EN）")
    ap.add_argument("--out", default=os.path.join(tempfile.gettempdir(), "order_store"))
    ap.add_argument("--fba-only", action="store_true", help="只抓 FBA 报表，不抓订单")
    ap.add_argument("--with-fba", action="store_true", help="同时抓 FBA 报表")
    ap.add_argument("--sku-map", action="store_true", help="抓 EN 客户物料号映射")
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    db_path = out_dir / "order_store.duckdb"
    con = duckdb.connect(str(db_path))
    gc = gs_client()
    report = []
    gs_frames, en_frames, fba_frames = [], [], []
    months = [m.strip() for m in args.months.split(",") if m.strip()]
    for ym in months:
        if args.with_fba or args.fba_only:
            fba = fetch_fba_month(gc, ym)
            if fba is not None and not fba.empty:
                fba_frames.append(fba)
                report.append({"month": ym, "kind": "fba", "rows": len(fba),
                               "msku": fba["msku"].nunique()})
            else:
                report.append({"month": ym, "kind": "fba", "rows": 0})

        if args.fba_only:
            continue

        gs = fetch_gs_month(gc, ym, raw_dir=out_dir / "raw_wide")
        gs_frames.append(gs)

        n_rows = len(gs)
        n_orders = gs["order_id"].nunique()
        accts = gs["account"].nunique()

        matched = None
        n_sample = 0
        if args.en_sample and args.en_sample > 0:
            uniq = gs["order_id"].drop_duplicates()
            sample = list(uniq.sample(min(args.en_sample, n_orders), random_state=42))
            n_sample = len(sample)
            en = fetch_en_orders(sample)
            if not en.empty:
                en_frames.append(en)
                matched = len(set(en["order_id"]))
        report.append({"month": ym, "kind": "orders", "gs_rows": n_rows, "gs_orders": n_orders,
                       "accounts": accts, "en_sample": n_sample, "en_matched": matched})

    if args.sku_map:
        sm = fetch_en_sku_map()
        write_table(con, "sku_map", sm, month_col=None, replace_all=True)
        report.append({"kind": "sku_map", "rows": len(sm)})

    if fba_frames:
        write_table(con, "fba_demand", pd.concat(fba_frames, ignore_index=True))

    if gs_frames:
        gs_all = pd.concat(gs_frames, ignore_index=True)
        write_table(con, "gs_orders", gs_all)

    if en_frames:
        en_all = pd.concat(en_frames, ignore_index=True).drop_duplicates(subset=["order_id"])
        con.register("en_all", en_all)
        con.execute("CREATE OR REPLACE TABLE en_orders AS SELECT * FROM en_all")
        con.unregister("en_all")
    else:
        con.execute("""CREATE TABLE IF NOT EXISTS en_orders (
            order_id VARCHAR, sale_date VARCHAR, despatch_date VARCHAR, channel VARCHAR,
            account VARCHAR, warehouse VARCHAR, order_status VARCHAR, source VARCHAR, month VARCHAR)""")

    # 统一视图（订单级）：同一 order_id 两边都有时以 EN 为准；GS 只补 EN 没有的
    con.execute("""
        CREATE OR REPLACE VIEW orders_unified AS
        SELECT order_id,
               any_value(sale_date) AS sale_date,
               any_value(despatch_date) AS despatch_date,
               any_value(channel) AS channel,
               any_value(account) AS account,
               any_value(warehouse) AS warehouse,
               'en' AS source
        FROM en_orders
        GROUP BY order_id
        UNION ALL
        SELECT g.order_id,
               any_value(g.sale_date) AS sale_date,
               any_value(g.despatch_date) AS despatch_date,
               any_value(g.channel) AS channel,
               any_value(g.account) AS account,
               any_value(g.warehouse) AS warehouse,
               'gs' AS source
        FROM gs_orders g
        LEFT JOIN en_orders e ON g.order_id = e.order_id
        WHERE e.order_id IS NULL
        GROUP BY g.order_id
    """)
    con.execute(f"COPY gs_orders TO '{(out_dir / 'gs_orders.parquet').as_posix()}' (FORMAT PARQUET)")
    con.execute(f"COPY en_orders TO '{(out_dir / 'en_orders.parquet').as_posix()}' (FORMAT PARQUET)")
    con.close()

    print(json.dumps({"db": str(db_path), "report": report}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
