# -*- coding: utf-8 -*-
"""全量替换 Google Sheet 的 8/9 月三张写回表（build-order-tabs 产物）。

默认 dry-run：只比对，不写；`--apply` 才备份 + 整表写入 + 回读。

用法（在 tongtool_order_cost 目录）：
  uv run python scripts/gs_full_replace.py --month 202609 --label all
  uv run python scripts/gs_full_replace.py --month 202609 --label all --apply

依赖：
- 父仓库 secrets/gsheets-service-account.json（或环境变量 GSPREAD_SERVICE_ACCOUNT_FILE）
- out/build_tabs/<月>/self_build|fba_build|merged_build_<月>.csv
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

import pandas as pd
import requests
import urllib3
from google.auth.transport.requests import Request
from google.oauth2 import service_account
from openpyxl.utils import get_column_letter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
urllib3.disable_warnings()

from tongtool_order_cost import gsheets  # noqa: E402

CHUNK = 500
METRICS_SELF = ["发货数量", "售价", "售价(人民币)", "售价*汇率", "运费", "皮壳成本",
                "绍兴二次加工成本", "二次加工成本", "头程运费金额", "1件产品成本",
                "产品成本*数量", "订单总成本", "订单利润"]
METRICS_FBA = ["销量", "销售额", "发货数量", "皮壳成本", "绍兴二次加工成本",
               "二次加工成本", "头程运费金额", "产品成本*数量", "订单总成本", "订单利润"]


def cfg(month: str, book: str | None = None) -> dict:
    year, mon = month[:4], str(int(month[4:]))
    book = book or f"通途订单{month}"
    return {
        "self": dict(book=book, ws=f"写回{year}年{mon}月订单",
                     local=f"out/build_tabs/{month}/self_build_{month}.csv",
                     keys=["订单号", "平台SKU", "通途SKU"], metrics=METRICS_SELF),
        "fba": dict(book=book, ws=f"写回{year}年{mon}月FBA订单",
                    local=f"out/build_tabs/{month}/fba_build_{month}.csv",
                    keys=["站点", "MSKU", "SKU"], metrics=METRICS_FBA),
        "merged": dict(book=book, ws=f"写回{year}年{mon}月FBA订单和非FBA订单",
                       local=f"out/build_tabs/{month}/merged_build_{month}.csv",
                       keys=["订单号", "平台SKU", "通途SKU"], metrics=METRICS_SELF),
    }


def retry(fn, n: int = 8):
    for i in range(n):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001
            print("retry", i, type(exc).__name__, flush=True)
            time.sleep(min(3 * (i + 1), 20))
    return fn()


def norm(k) -> tuple:
    return tuple("".join(ch for ch in str(x).upper() if ch.isalnum()) for x in k)


def num(v) -> float:
    try:
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return 0.0


def totals(df: pd.DataFrame, metrics: list[str]) -> dict:
    return {m: round(pd.to_numeric(df[m], errors="coerce").fillna(0.0).sum(), 4)
            for m in metrics if m in df.columns}


def run(month: str, label: str, apply: bool, book: str | None = None) -> None:
    c = cfg(month, book)[label]
    local_path = ROOT / c["local"]
    if not local_path.exists():
        raise SystemExit(f"本地表不存在: {local_path}")
    gc = retry(gsheets.client)
    sh = retry(lambda: gc.open(c["book"]))
    w = retry(lambda: sh.worksheet(c["ws"]))
    vals = retry(lambda: w.get_all_values())
    hdr, rows = vals[0], vals[1:]
    local = pd.read_csv(local_path, dtype=str, low_memory=False).fillna("")
    print(f"== {month} {label}: sheet {len(rows)} local {len(local)} "
          f"header_equal {hdr == list(local.columns)}")
    if hdr != list(local.columns):
        raise SystemExit("HEADER MISMATCH")
    old_df = pd.DataFrame(rows, columns=hdr).fillna("")
    old_keys = Counter(
        norm([r[hdr.index(x)] if hdr.index(x) < len(r) else "" for x in c["keys"]])
        for r in rows)
    new_keys = Counter(norm([r[x] for x in c["keys"]]) for _, r in local.iterrows())
    old_only = sum((old_keys - new_keys).values())
    new_only = sum((new_keys - old_keys).values())
    print(f"   keys: old {len(old_keys)} new {len(new_keys)} "
          f"old_only {old_only} new_only {new_only}")
    ot, nt = totals(old_df, c["metrics"]), totals(local, c["metrics"])
    for m in c["metrics"]:
        if m in ot or m in nt:
            print(f"   {m:<22} old {ot.get(m, 0):15,.2f} new {nt.get(m, 0):15,.2f} "
                  f"Δ {nt.get(m, 0) - ot.get(m, 0):+15,.2f}")
    suffix = "" if c["book"] == f"通途订单{month}" else "_" + "".join(
        ch if ch.isalnum() else "_" for ch in c["book"])
    out_dir = ROOT / "out" / f"gs_full_replace_{month}{suffix}"
    out_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([
        {"metric": m, "old": ot.get(m, 0), "new": nt.get(m, 0),
         "diff": round(nt.get(m, 0) - ot.get(m, 0), 4)}
        for m in c["metrics"]
    ]).to_csv(out_dir / f"{label}_totals.csv", index=False, encoding="utf-8-sig")
    (out_dir / f"{label}_rows.txt").write_text(
        f"sheet_rows={len(rows)}\nlocal_rows={len(local)}\n"
        f"old_only={old_only}\nnew_only={new_only}\n", encoding="utf-8")
    if not apply:
        print(f"   DRY-RUN (no write) -> {out_dir}")
        return

    sa_path = gsheets.service_account_path()
    creds = service_account.Credentials.from_service_account_file(
        str(sa_path), scopes=["https://www.googleapis.com/auth/spreadsheets"])
    creds.refresh(Request())
    headers = {"Authorization": "Bearer " + creds.token}
    run_dir = out_dir / f"run_{time.strftime('%Y%m%dT%H%M%S')}"
    run_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=hdr).to_csv(
        run_dir / "backup_full.csv", index=False, encoding="utf-8-sig")
    if len(local) + 1 > len(rows) + 1:
        retry(lambda: w.resize(rows=len(local) + 1, cols=len(local.columns)))
    last_col = get_column_letter(len(local.columns))
    data_to_write = [list(local.columns)] + local.values.tolist()
    for a in range(0, len(data_to_write), CHUNK):
        b = min(a + CHUNK, len(data_to_write)) - 1
        rng = f"'{c['ws']}'!A{a + 1}:{last_col}{b + 1}"
        rr = retry(lambda: requests.post(
            f"https://sheets.googleapis.com/v4/spreadsheets/{sh.id}/values:batchUpdate",
            headers=headers,
            json={"valueInputOption": "RAW",
                  "data": [{"range": rng, "values": data_to_write[a:b + 1]}]},
            timeout=300, verify=False,
        ))
        print("chunk", a, b, "status", rr.status_code)
        if rr.status_code != 200:
            print(rr.text[:300])
            raise SystemExit(3)
    if len(rows) > len(local):
        retry(lambda: w.delete_rows(len(local) + 2, len(rows) + 1))
        print("deleted rows", len(local) + 2, len(rows) + 1)
    elif len(rows) < len(local):
        w.resize(rows=len(local) + 1, cols=len(local.columns))
    back = retry(lambda: w.get_all_values())
    print("readback rows", len(back) - 1, "expected", len(local))
    errs = 0
    for i, row in local.iterrows():
        if i + 1 >= len(back):
            errs += 1
            continue
        for j, v in enumerate(row):
            got = back[i + 1][j] if j < len(back[i + 1]) else ""
            try:
                if abs(float(str(v)) - float(got)) > 0.01:
                    errs += 1
            except (TypeError, ValueError):
                if str(v).strip() != str(got).strip():
                    errs += 1
        if errs > 20:
            break
    print("readback errors", errs, "run", run_dir)
    (run_dir / "result.json").write_text(json.dumps(
        {"month": month, "label": label, "readback_errors": errs,
         "rows": len(local)}, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--month", required=True, help="YYYYMM，如 202607/202608/202609")
    ap.add_argument("--label", default="all", choices=["self", "fba", "merged", "all"])
    ap.add_argument("--book", default=None,
                    help="工作簿名覆盖（默认 通途订单<月>；如 通途订单202607-特殊规则）")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    labels = ["self", "fba", "merged"] if args.label == "all" else [args.label]
    for label in labels:
        run(args.month, label, args.apply, args.book)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
